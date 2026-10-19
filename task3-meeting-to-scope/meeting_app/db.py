import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import shared
from shared.config import settings

logger = logging.getLogger("meeting_scope.db")

def get_meeting_db():
    conn = sqlite3.connect(settings.meeting_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_meeting_db():
    conn = get_meeting_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        client_name TEXT NOT NULL,
        baseline_version INTEGER DEFAULT 0,
        is_approved INTEGER DEFAULT 0,
        approved_by TEXT,
        approved_at TEXT,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_versions (
        project_id TEXT NOT NULL,
        version_num INTEGER NOT NULL,
        transcript_text TEXT NOT NULL,
        requirements_json TEXT NOT NULL,
        tasks_json TEXT NOT NULL,
        scope_doc_json TEXT NOT NULL,
        proposal_text TEXT NOT NULL,
        total_low REAL NOT NULL,
        total_likely REAL NOT NULL,
        total_high REAL NOT NULL,
        is_approved INTEGER DEFAULT 0,
        approved_by TEXT,
        approved_at TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (project_id, version_num),
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scope_diffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        baseline_version INTEGER NOT NULL,
        new_version INTEGER NOT NULL,
        added_json TEXT NOT NULL,
        removed_json TEXT NOT NULL,
        modified_json TEXT NOT NULL,
        timeline_changes TEXT,
        diff_report_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );
    """)

    conn.commit()
    conn.close()
    logger.info("Meeting to Scope database initialized.")

def save_project_version(
    project_id: str,
    title: str,
    client_name: str,
    version_num: int,
    transcript_text: str,
    requirements: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    scope_doc: Dict[str, Any],
    proposal_text: str,
    total_low: float,
    total_likely: float,
    total_high: float
) -> Dict[str, Any]:
    conn = get_meeting_db()
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()

    # Ensure project exists
    cur.execute(
        """INSERT INTO projects (id, title, client_name, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET title=?, client_name=?""",
        (project_id, title, client_name, now_str, title, client_name)
    )

    # Save version (defaults to unapproved)
    cur.execute(
        """INSERT INTO project_versions 
           (project_id, version_num, transcript_text, requirements_json, tasks_json, scope_doc_json, proposal_text, total_low, total_likely, total_high, is_approved, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
           ON CONFLICT(project_id, version_num) DO UPDATE SET
               transcript_text=?, requirements_json=?, tasks_json=?, scope_doc_json=?, proposal_text=?, total_low=?, total_likely=?, total_high=?""",
        (
            project_id, version_num, transcript_text, json.dumps(requirements), json.dumps(tasks),
            json.dumps(scope_doc), proposal_text, total_low, total_likely, total_high, now_str,
            transcript_text, json.dumps(requirements), json.dumps(tasks), json.dumps(scope_doc), proposal_text, total_low, total_likely, total_high
        )
    )

    conn.commit()
    conn.close()
    return {"project_id": project_id, "version": version_num, "status": "saved"}

def approve_project_version(project_id: str, version_num: int, approved_by: str) -> Dict[str, Any]:
    """
    Locks the specified version as the officially approved baseline!
    Crucial guardrail: unapproved follow-up drafts NEVER overwrite an approved baseline.
    """
    conn = get_meeting_db()
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()

    cur.execute(
        """UPDATE project_versions 
           SET is_approved = 1, approved_by = ?, approved_at = ?
           WHERE project_id = ? AND version_num = ?""",
        (approved_by, now_str, project_id, version_num)
    )

    cur.execute(
        """UPDATE projects 
           SET baseline_version = ?, is_approved = 1, approved_by = ?, approved_at = ?
           WHERE id = ?""",
        (version_num, approved_by, now_str, project_id)
    )

    conn.commit()
    conn.close()
    logger.info(f"Project {project_id} Version {version_num} approved by {approved_by}.")
    return {"project_id": project_id, "approved_version": version_num, "approved_by": approved_by}

def get_project_version(project_id: str, version_num: int) -> Optional[Dict[str, Any]]:
    conn = get_meeting_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM project_versions WHERE project_id = ? AND version_num = ?", (project_id, version_num))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["requirements"] = json.loads(d["requirements_json"])
    d["tasks"] = json.loads(d["tasks_json"])
    d["scope_doc"] = json.loads(d["scope_doc_json"])
    return d

def get_approved_baseline(project_id: str) -> Optional[Dict[str, Any]]:
    conn = get_meeting_db()
    cur = conn.cursor()
    cur.execute("SELECT baseline_version FROM projects WHERE id = ?", (project_id,))
    p_row = cur.fetchone()
    if not p_row or not p_row["baseline_version"]:
        conn.close()
        return None
    conn.close()
    return get_project_version(project_id, p_row["baseline_version"])
