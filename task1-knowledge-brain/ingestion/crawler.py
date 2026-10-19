import time
import json
import logging
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

import shared
from shared.config import settings
from kb_app.db import get_db_connection, log_audit_event
from ingestion.sitemap_parser import SitemapParser
from ingestion.html_extractor import HTMLExtractor
from multimodal.image_analyzer import ImageAnalyzer
from retrieval.indexer import HybridIndexer

logger = logging.getLogger("knowledge_brain.crawler")

class IngestionManager:
    _instance = None
    _status = {
        "is_running": False,
        "total_discovered": 0,
        "processed": 0,
        "unchanged": 0,
        "failed": 0,
        "pending": 0,
        "last_run_at": None,
        "last_error": None
    }

    def __init__(self):
        self.sitemap_parser = SitemapParser()
        self.html_extractor = HTMLExtractor()
        self.image_analyzer = ImageAnalyzer()
        self.indexer = HybridIndexer()

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, count(*) as cnt FROM manifest GROUP BY status")
        counts = {row["status"]: row["cnt"] for row in cur.fetchall()}
        conn.close()

        total = sum(counts.values())
        processed = counts.get("processed", 0)
        unchanged = counts.get("unchanged", 0)
        failed = counts.get("failed", 0)
        pending = counts.get("pending", 0)

        cls._status["total_discovered"] = total
        cls._status["processed"] = processed
        cls._status["unchanged"] = unchanged
        cls._status["failed"] = failed
        cls._status["pending"] = pending
        return dict(cls._status)

    def run_ingestion_sync(self, max_articles: int = 15, force_refresh: bool = False, sample_only: bool = False) -> Dict[str, Any]:
        """Synchronous wrapper for ingestion job."""
        return asyncio.run(self.run_ingestion(max_articles=max_articles, force_refresh=force_refresh, sample_only=sample_only))

    async def run_ingestion(self, max_articles: int = 15, force_refresh: bool = False, sample_only: bool = False) -> Dict[str, Any]:
        """
        Executes a polite, resumable ingestion run:
        1. Checks/syncs sitemap manifest.
        2. Selects pending articles up to max_articles limit.
        3. Fetches HTML with exponential backoff and polite delay.
        4. Detects unchanged vs modified pages via SHA256 hashes.
        5. Analyzes screenshots and chunks content.
        6. Updates SQLite and rebuilds the vector & BM25 indices.
        """
        if IngestionManager._status["is_running"]:
            logger.warning("Ingestion already running.")
            return {"status": "already_running", **self.get_status()}

        IngestionManager._status["is_running"] = True
        IngestionManager._status["last_error"] = None
        start_time = datetime.now(timezone.utc)
        IngestionManager._status["last_run_at"] = start_time.isoformat()

        logger.info(f"Starting ingestion (max={max_articles}, force={force_refresh}, sample_only={sample_only})...")

        try:
            if sample_only:
                await self._ingest_seed_articles(force_refresh=force_refresh)
            else:
                # 1. Sync Sitemap with manifest
                try:
                    entries, stats = self.sitemap_parser.fetch_and_parse()
                    logger.info(f"Sitemap sync complete: {stats}")
                except Exception as e:
                    logger.warning(f"Live sitemap fetch failed: {e}. Falling back to pre-seeded articles.")
                    await self._ingest_seed_articles(force_refresh=force_refresh)
                    self.indexer.build_index_from_db()
                    IngestionManager._status["is_running"] = False
                    return self.get_status()

                # 2. Select batch of pending articles
                conn = get_db_connection()
                cur = conn.cursor()
                if force_refresh:
                    cur.execute("SELECT url, lastmod FROM manifest LIMIT ?", (max_articles,))
                else:
                    cur.execute("SELECT url, lastmod FROM manifest WHERE status = 'pending' LIMIT ?", (max_articles,))
                batch = cur.fetchall()
                conn.close()

                if not batch:
                    logger.info("No pending articles to process in manifest. Ensuring seeds are present...")
                    await self._ingest_seed_articles(force_refresh=False)
                else:
                    logger.info(f"Processing batch of {len(batch)} articles...")
                    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                        for row in batch:
                            url = row["url"]
                            lastmod = row["lastmod"]
                            await self._process_single_url(client, url, lastmod, force_refresh)
                            await asyncio.sleep(settings.ingestion_polite_delay_sec)

            # Rebuild index from database
            self.indexer.build_index_from_db()
            logger.info("Ingestion batch completed successfully.")
            log_audit_event("ingestion_batch_complete", self.get_status())

        except Exception as e:
            logger.error(f"Fatal error during ingestion: {e}", exc_info=True)
            IngestionManager._status["last_error"] = str(e)
        finally:
            IngestionManager._status["is_running"] = False

        return self.get_status()

    async def _ingest_seed_articles(self, force_refresh: bool = False):
        """Loads and indexes the high-quality Brilliant Directories seed dataset."""
        seed_path = Path(settings.data_dir) / "seed_articles.json"
        if not seed_path.exists():
            logger.warning(f"Seed file not found at {seed_path}")
            return

        with open(seed_path, "r", encoding="utf-8") as f:
            seeds = json.load(f)

        logger.info(f"Ingesting {len(seeds)} seed articles...")
        conn = get_db_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()

        for art in seeds:
            url = art["url"]
            title = art["title"]
            raw_text = art["raw_text"]
            headings = art.get("headings", [])
            images = art.get("images", [])
            
            # Compute hash
            content_hash = self.html_extractor.extract(f"<h1>{title}</h1><div>{raw_text}</div>", url)["content_hash"]

            # Check if exists
            cur.execute("SELECT id, content_hash FROM articles WHERE url = ?", (url,))
            existing = cur.fetchone()

            if existing and existing["content_hash"] == content_hash and not force_refresh:
                cur.execute(
                    "UPDATE manifest SET status = 'unchanged', updated_at = ? WHERE url = ?",
                    (now_str, url)
                )
                continue

            # Upsert article
            if existing:
                art_id = existing["id"]
                cur.execute(
                    """UPDATE articles SET title = ?, content_hash = ?, raw_text = ?, 
                       headings_json = ?, images_json = ?, is_active = 1, updated_at = ? WHERE id = ?""",
                    (title, content_hash, raw_text, json.dumps(headings), json.dumps(images), now_str, art_id)
                )
                cur.execute("DELETE FROM chunks WHERE article_id = ?", (art_id,))
            else:
                cur.execute(
                    """INSERT INTO articles (url, title, content_hash, raw_text, headings_json, images_json, is_active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (url, title, content_hash, raw_text, json.dumps(headings), json.dumps(images), now_str, now_str)
                )
                art_id = cur.lastrowid

            # Parse sections for chunking
            sections = []
            for h in headings:
                sections.append({"heading": h, "text": raw_text, "images": images})
            if not sections:
                sections = [{"heading": "Overview", "text": raw_text, "images": images}]

            article_obj = {
                "title": title,
                "url": url,
                "sections": sections,
                "images": images
            }
            chunks = self.indexer.chunk_article(article_obj, art_id)

            for c in chunks:
                cur.execute(
                    """INSERT INTO chunks (id, article_id, chunk_index, chunk_text, section, image_refs_json, token_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (c["id"], art_id, c["chunk_index"], c["chunk_text"], c["section"], json.dumps(c["images"]), c["token_count"])
                )

            # Update manifest
            cur.execute(
                """INSERT INTO manifest (url, lastmod, content_hash, status, http_status, chunk_count, fetched_at, updated_at)
                   VALUES (?, ?, ?, 'processed', 200, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET status='processed', http_status=200, chunk_count=?, content_hash=?, updated_at=?""",
                (url, now_str, content_hash, len(chunks), now_str, now_str, len(chunks), content_hash, now_str)
            )

        conn.commit()
        conn.close()

    async def _process_single_url(self, client: httpx.AsyncClient, url: str, lastmod: Optional[str], force_refresh: bool):
        """Fetches and processes a single article URL with retries and change detection."""
        conn = get_db_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()

        # Retry loop with exponential backoff
        max_retries = settings.ingestion_max_retries
        html = None
        http_status = None
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers={"User-Agent": "AITechConsultant-IngestionBot/1.0"})
                http_status = resp.status_code
                if resp.status_code == 200:
                    html = resp.text
                    break
                elif resp.status_code == 404:
                    logger.warning(f"Article 404 removed: {url}")
                    cur.execute("UPDATE manifest SET status = 'removed', http_status = 404, updated_at = ? WHERE url = ?", (now_str, url))
                    cur.execute("UPDATE articles SET is_active = 0 WHERE url = ?", (url,))
                    conn.commit()
                    conn.close()
                    return
            except Exception as e:
                wait_time = (2 ** attempt) * 0.5
                logger.warning(f"Fetch attempt {attempt+1} failed for {url}: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

        if not html:
            logger.error(f"Failed to fetch {url} after {max_retries} attempts.")
            cur.execute("UPDATE manifest SET status = 'failed', http_status = ?, error_message = 'Max retries exceeded', updated_at = ? WHERE url = ?", (http_status, now_str, url))
            conn.commit()
            conn.close()
            return

        # Extract structured content
        data = self.html_extractor.extract(html, url)
        title = data["title"]
        content_hash = data["content_hash"]

        # Check existing article
        cur.execute("SELECT id, content_hash FROM articles WHERE url = ?", (url,))
        existing = cur.fetchone()

        if existing and existing["content_hash"] == content_hash and not force_refresh:
            logger.info(f"Article unchanged: {url}")
            cur.execute("UPDATE manifest SET status = 'unchanged', http_status = 200, updated_at = ? WHERE url = ?", (now_str, url))
            conn.commit()
            conn.close()
            return

        # Enrich images with visual context
        for img in data["images"][:2]:
            img["description"] = self.image_analyzer.analyze_screenshot(
                image_url=img["url"],
                article_title=title,
                section="Overview",
                surrounding_text=img.get("surrounding_text", "")
            )

        # Upsert article record
        if existing:
            art_id = existing["id"]
            cur.execute(
                """UPDATE articles SET title = ?, content_hash = ?, raw_text = ?, headings_json = ?, 
                   images_json = ?, is_active = 1, updated_at = ? WHERE id = ?""",
                (title, content_hash, data["raw_text"], json.dumps(data["headings"]), json.dumps(data["images"]), now_str, art_id)
            )
            cur.execute("DELETE FROM chunks WHERE article_id = ?", (art_id,))
        else:
            cur.execute(
                """INSERT INTO articles (url, title, content_hash, raw_text, headings_json, images_json, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (url, title, content_hash, data["raw_text"], json.dumps(data["headings"]), json.dumps(data["images"]), now_str, now_str)
            )
            art_id = cur.lastrowid

        # Generate & store chunks
        chunks = self.indexer.chunk_article(data, art_id)
        for c in chunks:
            cur.execute(
                """INSERT INTO chunks (id, article_id, chunk_index, chunk_text, section, image_refs_json, token_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (c["id"], art_id, c["chunk_index"], c["chunk_text"], c["section"], json.dumps(c["images"]), c["token_count"])
            )

        cur.execute(
            """UPDATE manifest SET status = 'processed', http_status = 200, chunk_count = ?, 
               content_hash = ?, fetched_at = ?, updated_at = ? WHERE url = ?""",
            (len(chunks), content_hash, now_str, now_str, url)
        )
        conn.commit()
        conn.close()
        logger.info(f"Processed article: '{title}' ({len(chunks)} chunks)")
