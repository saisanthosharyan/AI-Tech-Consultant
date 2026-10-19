import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import shared
from shared.config import settings

logger = logging.getLogger("knowledge_brain.db")

def get_db_connection():
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # Manifest table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS manifest (
        url TEXT PRIMARY KEY,
        lastmod TEXT,
        content_hash TEXT,
        status TEXT DEFAULT 'pending',
        http_status INTEGER,
        chunk_count INTEGER DEFAULT 0,
        error_message TEXT,
        fetched_at TEXT,
        updated_at TEXT
    );
    """)

    # Articles table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        headings_json TEXT,
        images_json TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    );
    """)

    # Chunks table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        article_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        section TEXT,
        image_refs_json TEXT,
        token_count INTEGER,
        FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
    );
    """)

    # Escalations table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS escalations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT,
        question TEXT NOT NULL,
        retrieved_evidence_json TEXT,
        reason TEXT NOT NULL,
        expert_answer TEXT,
        resolved_by TEXT,
        resolved_at TEXT,
        is_indexed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Audit log
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        details_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()
    logger.info("Knowledge Brain database initialized successfully.")

def log_audit_event(event_type: str, details: Dict[str, Any]):
    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO audit_log (event_type, details_json, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(details), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
