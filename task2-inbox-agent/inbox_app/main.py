import logging
from typing import List, Dict, Any, Optional
import shared
from shared.config import settings
from shared.schemas import ReviewActionRequest
from .db import (
    get_inbox_db, init_inbox_db, record_human_decision, get_tracker_stats
)
from .pipeline import InboxAgentPipeline

logger = logging.getLogger("inbox_agent.api")

# Initialize database
init_inbox_db()
pipeline = InboxAgentPipeline()

def initialize_inbox() -> int:
    emails = pipeline.load_seed_emails()
    return len(emails)

def get_all_emails(category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_inbox_db()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT * FROM emails WHERE category = ? ORDER BY id", (category,))
    else:
        cur.execute("SELECT * FROM emails ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_email_details(email_id: str) -> Dict[str, Any]:
    conn = get_inbox_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    email_row = cur.fetchone()
    if not email_row:
        conn.close()
        raise ValueError(f"Email {email_id} not found.")

    cur.execute("SELECT * FROM drafts WHERE email_id = ? ORDER BY id DESC LIMIT 1", (email_id,))
    draft_row = cur.fetchone()

    cur.execute("SELECT * FROM reviews WHERE email_id = ? ORDER BY id DESC", (email_id,))
    reviews = [dict(r) for r in cur.fetchall()]
    conn.close()

    return {
        "email": dict(email_row),
        "draft": dict(draft_row) if draft_row else None,
        "reviews": reviews
    }

def process_single_email(email_id: str, model_version: Optional[str] = None):
    return pipeline.process_email(email_id, model_version=model_version)

def submit_review(
    email_id: str,
    draft_id: int,
    action: str,
    original_draft: str,
    final_reply: str,
    category: str,
    risk_level: str,
    reviewer: str = "Consultant Reviewer",
    notes: Optional[str] = None
) -> Dict[str, Any]:
    return record_human_decision(
        email_id=email_id,
        draft_id=draft_id,
        action=action,
        original_draft=original_draft,
        final_reply=final_reply,
        category=category,
        risk_level=risk_level,
        reviewer=reviewer,
        feedback_notes=notes
    )

def get_sent_emails() -> List[Dict[str, Any]]:
    conn = get_inbox_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sent_log ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
