import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import shared
from shared.config import settings

logger = logging.getLogger("inbox_agent.db")

def get_inbox_db():
    conn = sqlite3.connect(settings.inbox_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_inbox_db():
    conn = get_inbox_db()
    cur = conn.cursor()

    # Emails table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY,
        sender_name TEXT NOT NULL,
        sender_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        category TEXT,
        urgency TEXT,
        risk_level TEXT,
        risk_factors_json TEXT,
        important_facts_json TEXT,
        expected_behavior TEXT,
        requires_escalation INTEGER DEFAULT 0,
        is_synthetic INTEGER DEFAULT 1
    );
    """)

    # Drafts table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id TEXT NOT NULL,
        draft_subject TEXT NOT NULL,
        draft_reply TEXT NOT NULL,
        sources_json TEXT,
        guardrails_passed INTEGER DEFAULT 1,
        warnings_json TEXT,
        needs_human_review INTEGER DEFAULT 1,
        autonomy_eligible INTEGER DEFAULT 0,
        model_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (email_id) REFERENCES emails(id)
    );
    """)

    # Reviews & Human Feedback table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id TEXT NOT NULL,
        draft_id INTEGER NOT NULL,
        action TEXT NOT NULL, -- 'approve', 'edit', 'reject', 'escalate'
        original_draft TEXT NOT NULL,
        final_reply TEXT NOT NULL,
        is_changed INTEGER DEFAULT 0,
        reviewer TEXT NOT NULL,
        feedback_notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (email_id) REFERENCES emails(id),
        FOREIGN KEY (draft_id) REFERENCES drafts(id)
    );
    """)

    # Category Autonomy Tracker (Implements the 20-Consecutive-Draft Rule)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS category_autonomy_tracker (
        category TEXT PRIMARY KEY,
        consecutive_unchanged_count INTEGER DEFAULT 0,
        total_approved INTEGER DEFAULT 0,
        total_edited INTEGER DEFAULT 0,
        total_rejected INTEGER DEFAULT 0,
        autonomy_eligible INTEGER DEFAULT 0,
        is_autonomy_active INTEGER DEFAULT 0,
        last_reset_reason TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # Prompt Templates (Versioned prompts that learn from human edits)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prompt_templates (
        version INTEGER PRIMARY KEY AUTOINCREMENT,
        template_text TEXT NOT NULL,
        few_shot_examples_json TEXT,
        is_active INTEGER DEFAULT 1,
        notes TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # Simulated Sent Log
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sent_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id TEXT NOT NULL,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        sent_mode TEXT NOT NULL, -- 'manual_approved', 'autonomous_trial'
        sent_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()
    logger.info("Inbox Agent database initialized.")

def record_human_decision(
    email_id: str,
    draft_id: int,
    action: str,
    original_draft: str,
    final_reply: str,
    category: str,
    risk_level: str,
    reviewer: str = "Consultant Reviewer",
    feedback_notes: Optional[str] = None
) -> Dict[str, Any]:
    conn = get_inbox_db()
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()

    norm_orig = " ".join(original_draft.strip().split())
    norm_final = " ".join(final_reply.strip().split())
    is_changed = 1 if norm_orig != norm_final else 0

    # 1. Insert review record
    cur.execute(
        """INSERT INTO reviews (email_id, draft_id, action, original_draft, final_reply, is_changed, reviewer, feedback_notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (email_id, draft_id, action, original_draft, final_reply, is_changed, reviewer, feedback_notes, now_str)
    )

    # 2. Update category autonomy tracker
    cur.execute("SELECT * FROM category_autonomy_tracker WHERE category = ?", (category,))
    row = cur.fetchone()

    consecutive = row["consecutive_unchanged_count"] if row else 0
    total_app = row["total_approved"] if row else 0
    total_ed = row["total_edited"] if row else 0
    total_rej = row["total_rejected"] if row else 0
    eligible = row["autonomy_eligible"] if row else 0
    active = row["is_autonomy_active"] if row else 0
    reset_reason = None

    if action == "approve" and is_changed == 0:
        consecutive += 1
        total_app += 1
        if consecutive >= settings.consecutive_unchanged_threshold:
            eligible = 1
    elif action == "edit" or is_changed == 1:
        consecutive = 0
        eligible = 0
        active = 0
        total_ed += 1
        reset_reason = f"Draft edited by reviewer ({reviewer}): feedback noted."
    elif action == "reject":
        consecutive = 0
        eligible = 0
        active = 0
        total_rej += 1
        reset_reason = f"Draft rejected by reviewer ({reviewer})."
    elif action == "escalate":
        consecutive = 0
        reset_reason = "Escalated for senior review."

    cur.execute(
        """INSERT INTO category_autonomy_tracker 
           (category, consecutive_unchanged_count, total_approved, total_edited, total_rejected, autonomy_eligible, is_autonomy_active, last_reset_reason, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(category) DO UPDATE SET
               consecutive_unchanged_count = ?,
               total_approved = ?,
               total_edited = ?,
               total_rejected = ?,
               autonomy_eligible = ?,
               is_autonomy_active = ?,
               last_reset_reason = ?,
               updated_at = ?""",
        (category, consecutive, total_app, total_ed, total_rej, eligible, active, reset_reason, now_str,
         consecutive, total_app, total_ed, total_rej, eligible, active, reset_reason, now_str)
    )

    # 3. If approved, record simulated send
    if action in ["approve", "edit"]:
        cur.execute("SELECT sender_email, subject FROM emails WHERE id = ?", (email_id,))
        em_row = cur.fetchone()
        if em_row:
            cur.execute(
                """INSERT INTO sent_log (email_id, recipient, subject, body, sent_mode, sent_at)
                   VALUES (?, ?, ?, ?, 'manual_approved', ?)""",
                (email_id, em_row["sender_email"], f"Re: {em_row['subject']}", final_reply, now_str)
            )

    conn.commit()
    conn.close()

    return {
        "email_id": email_id,
        "action": action,
        "is_changed": bool(is_changed),
        "consecutive_unchanged_count": consecutive,
        "autonomy_eligible": bool(eligible),
        "reset_reason": reset_reason
    }

def get_tracker_stats() -> List[Dict[str, Any]]:
    conn = get_inbox_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM category_autonomy_tracker ORDER BY category")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
