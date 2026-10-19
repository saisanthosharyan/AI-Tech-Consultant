import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import shared
from shared.config import settings
from shared.schemas import (
    QueryRequest, QueryResponse, IngestionRunRequest, IngestionStatusResponse,
    EscalationCreateRequest, EscalationResolveRequest, EscalationResponse
)
from .db import get_db_connection, init_db, log_audit_event
from .rag_service import RAGService
from ingestion.crawler import IngestionManager
from retrieval.indexer import HybridIndexer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("knowledge_brain.api")

# Initialize database tables on startup
init_db()

app = FastAPI(
    title="Brilliant Directories Knowledge Brain API",
    version="1.0.0",
    description="Centralized Knowledge Brain API for technical consultation, ingestion, multimodal RAG, and escalation."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
indexer = HybridIndexer()
rag_service = RAGService(indexer=indexer)
ingestion_manager = IngestionManager()

@app.get("/health")
def health_check():
    """Health check endpoint exposing runtime and index status."""
    db_ok = False
    article_count = 0
    chunk_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) as cnt FROM articles WHERE is_active = 1")
        article_count = cur.fetchone()["cnt"]
        cur.execute("SELECT count(*) as cnt FROM chunks")
        chunk_count = cur.fetchone()["cnt"]
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"Health DB check failed: {e}")

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "knowledge-brain-api",
        "database_connected": db_ok,
        "articles_indexed": article_count,
        "chunks_indexed": chunk_count,
        "index_vectors_loaded": indexer.index.ntotal if indexer.index else 0,
        "anthropic_configured": bool(settings.anthropic_api_key)
    }

@app.post("/query", response_model=QueryResponse)
def query_knowledge_brain(request: QueryRequest):
    """
    RAG Query Endpoint:
    Retrieves evidence, computes confidence, produces grounded answers,
    and returns citations or escalates to human if evidence is insufficient.
    """
    try:
        return rag_service.query(request)
    except Exception as e:
        logger.error(f"Query processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@app.post("/ingestion/run", response_model=IngestionStatusResponse)
def trigger_ingestion(request: IngestionRunRequest, background_tasks: BackgroundTasks):
    """
    Triggers polite web ingestion from the Brilliant Directories sitemap.
    Can be run in background or sample mode.
    """
    status = IngestionManager.get_status()
    if status["is_running"]:
        return IngestionStatusResponse(**status)

    if request.sample_only:
        # Run synchronous sample ingestion
        ingestion_manager.run_ingestion_sync(
            max_articles=request.max_articles or 15,
            force_refresh=request.force_refresh,
            sample_only=True
        )
    else:
        # Run async in background
        background_tasks.add_task(
            ingestion_manager.run_ingestion_sync,
            request.max_articles or 15,
            request.force_refresh,
            False
        )

    return IngestionStatusResponse(**IngestionManager.get_status())

@app.get("/ingestion/status", response_model=IngestionStatusResponse)
def get_ingestion_status():
    """Returns real-time ingestion progress, discovered, processed, and failure counts."""
    return IngestionStatusResponse(**IngestionManager.get_status())

@app.post("/escalations", response_model=EscalationResponse)
def create_escalation(request: EscalationCreateRequest):
    """Creates a human escalation record when question cannot be answered automatically."""
    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT INTO escalations (request_id, question, retrieved_evidence_json, reason, is_indexed, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (request.request_id, request.question, json.dumps(request.retrieved_evidence), request.reason, now_str)
    )
    esc_id = cur.lastrowid
    conn.commit()
    conn.close()

    log_audit_event("escalation_created", {"id": esc_id, "question": request.question, "reason": request.reason})

    return EscalationResponse(
        id=esc_id,
        request_id=request.request_id,
        question=request.question,
        reason=request.reason,
        is_indexed=False,
        created_at=now_str
    )

@app.get("/escalations", response_model=List[EscalationResponse])
def list_escalations(resolved: Optional[bool] = None):
    """Lists escalation cases."""
    conn = get_db_connection()
    cur = conn.cursor()
    if resolved is True:
        cur.execute("SELECT * FROM escalations WHERE expert_answer IS NOT NULL ORDER BY id DESC")
    elif resolved is False:
        cur.execute("SELECT * FROM escalations WHERE expert_answer IS NULL ORDER BY id DESC")
    else:
        cur.execute("SELECT * FROM escalations ORDER BY id DESC")
    
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append(EscalationResponse(
            id=r["id"],
            request_id=r["request_id"],
            question=r["question"],
            reason=r["reason"],
            expert_answer=r["expert_answer"],
            resolved_by=r["resolved_by"],
            resolved_at=r["resolved_at"],
            is_indexed=bool(r["is_indexed"]),
            created_at=r["created_at"]
        ))
    return results

@app.post("/escalations/{id}/resolve", response_model=EscalationResponse)
def resolve_escalation(id: int, request: EscalationResolveRequest):
    """
    Expert reviewer enters verified answer.
    Optionally indexes the approved Q&A as an active article in Knowledge Brain.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM escalations WHERE id = ?", (id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Escalation record not found")

    now_str = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """UPDATE escalations 
           SET expert_answer = ?, resolved_by = ?, resolved_at = ?, is_indexed = ?
           WHERE id = ?""",
        (request.expert_answer, request.resolved_by, now_str, 1 if request.index_as_knowledge else 0, id)
    )

    # Index into Knowledge Brain as verified expert knowledge if requested
    if request.index_as_knowledge:
        art_url = f"https://support.brilliantdirectories.com/support/expert-resolution/{id}"
        art_title = f"Expert Resolution: {row['question']}"
        raw_text = f"## Question\n{row['question']}\n\n## Verified Expert Solution\n{request.expert_answer}\n\nResolved by: {request.resolved_by}"
        import hashlib
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        cur.execute(
            """INSERT INTO articles (url, title, content_hash, raw_text, headings_json, images_json, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, '[]', 1, ?, ?)
               ON CONFLICT(url) DO UPDATE SET raw_text=?, updated_at=?""",
            (art_url, art_title, content_hash, raw_text, json.dumps(["Question", "Verified Expert Solution"]), now_str, now_str, raw_text, now_str)
        )
        art_id = cur.lastrowid or 99999

        chunk_id = f"esc_{id}_c0"
        cur.execute(
            """INSERT INTO chunks (id, article_id, chunk_index, chunk_text, section, image_refs_json, token_count)
               VALUES (?, ?, 0, ?, 'Verified Expert Solution', '[]', ?)
               ON CONFLICT(id) DO UPDATE SET chunk_text=?""",
            (chunk_id, art_id, raw_text, len(raw_text.split()), raw_text)
        )
        conn.commit()
        conn.close()
        # Rebuild index to include the new knowledge
        indexer.build_index_from_db()
    else:
        conn.commit()
        conn.close()

    log_audit_event("escalation_resolved", {"id": id, "resolved_by": request.resolved_by})

    return EscalationResponse(
        id=id,
        request_id=row["request_id"],
        question=row["question"],
        reason=row["reason"],
        expert_answer=request.expert_answer,
        resolved_by=request.resolved_by,
        resolved_at=now_str,
        is_indexed=request.index_as_knowledge,
        created_at=row["created_at"]
    )

@app.get("/articles")
def list_articles(limit: int = 50, offset: int = 0):
    """Lists ingested articles with metadata."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, url, title, is_active, created_at, updated_at FROM articles LIMIT ? OFFSET ?", (limit, offset))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"articles": rows, "count": len(rows)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.knowledge_brain_host, port=settings.knowledge_brain_port, reload=True)
