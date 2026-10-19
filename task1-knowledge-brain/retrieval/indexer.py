import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import shared
from shared.config import settings
from kb_app.db import get_db_connection, log_audit_event

logger = logging.getLogger("knowledge_brain.indexer")

class HybridIndexer:
    def __init__(self, index_dir: Path = settings.vector_index_dir):
        self.index_dir = index_dir
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.faiss_path = self.index_dir / "faiss.index"
        self.meta_path = self.index_dir / "chunks_metadata.json"
        
        # Load embedding model
        logger.info("Initializing SentenceTransformer model 'all-MiniLM-L6-v2'...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.embedding_dim = 384
        
        self.index = None
        self.metadata: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.bm25_corpus: List[List[str]] = []
        
        self.load_index()

    def chunk_article(self, article: Dict[str, Any], article_id: int) -> List[Dict[str, Any]]:
        """
        Splits an article into overlapping, context-rich chunks preserving title,
        URL, section headings, and image references.
        """
        chunks = []
        chunk_idx = 0
        title = article["title"]
        url = article["url"]
        sections = article.get("sections", [])

        if not sections:
            # Fallback chunking if no section headings
            text = article.get("raw_text", "")
            words = text.split()
            chunk_size = 250
            overlap = 50
            start = 0
            while start < len(words):
                end = min(start + chunk_size, len(words))
                chunk_words = words[start:end]
                body = " ".join(chunk_words)
                chunk_id = f"art_{article_id}_c{chunk_idx}"
                full_text = f"Article: {title}\nSection: Overview\nSource: {url}\n\n{body}"
                chunks.append({
                    "id": chunk_id,
                    "article_id": article_id,
                    "chunk_index": chunk_idx,
                    "title": title,
                    "url": url,
                    "section": "Overview",
                    "chunk_text": full_text,
                    "images": [img.get("url") for img in article.get("images", [])][:3],
                    "token_count": len(chunk_words)
                })
                chunk_idx += 1
                if end == len(words):
                    break
                start += (chunk_size - overlap)
            return chunks

        for sec in sections:
            heading = sec.get("heading", "Section")
            sec_text = sec.get("text", "")
            sec_images = [img["url"] if isinstance(img, dict) else str(img) for img in sec.get("images", [])][:3]
            
            words = sec_text.split()
            if not words:
                continue

            # Small section: 1 chunk
            if len(words) <= 280:
                chunk_id = f"art_{article_id}_c{chunk_idx}"
                full_text = f"Article: {title}\nSection: {heading}\nSource: {url}\n\n{sec_text}"
                chunks.append({
                    "id": chunk_id,
                    "article_id": article_id,
                    "chunk_index": chunk_idx,
                    "title": title,
                    "url": url,
                    "section": heading,
                    "chunk_text": full_text,
                    "images": sec_images,
                    "token_count": len(words)
                })
                chunk_idx += 1
            else:
                # Overlapping window for long sections
                chunk_size = 220
                overlap = 40
                start = 0
                while start < len(words):
                    end = min(start + chunk_size, len(words))
                    slice_words = words[start:end]
                    body = " ".join(slice_words)
                    chunk_id = f"art_{article_id}_c{chunk_idx}"
                    full_text = f"Article: {title}\nSection: {heading}\nSource: {url}\n\n{body}"
                    chunks.append({
                        "id": chunk_id,
                        "article_id": article_id,
                        "chunk_index": chunk_idx,
                        "title": title,
                        "url": url,
                        "section": heading,
                        "chunk_text": full_text,
                        "images": sec_images,
                        "token_count": len(slice_words)
                    })
                    chunk_idx += 1
                    if end == len(words):
                        break
                    start += (chunk_size - overlap)

        return chunks

    def build_index_from_db(self):
        """
        Reads all active chunks from SQLite and builds/persists the FAISS and BM25 indices.
        Prevents duplicate vectors and ensures perfect synchronization.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.article_id, c.chunk_index, c.chunk_text, c.section, c.image_refs_json,
                   a.title, a.url
            FROM chunks c
            JOIN articles a ON c.article_id = a.id
            WHERE a.is_active = 1
            ORDER BY c.article_id, c.chunk_index
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            logger.warning("No active chunks found in DB to index.")
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.metadata = []
            self.bm25 = None
            return

        logger.info(f"Building index from {len(rows)} database chunks...")
        metadata = []
        texts_to_embed = []
        corpus_tokens = []

        for r in rows:
            images = json.loads(r["image_refs_json"]) if r["image_refs_json"] else []
            meta = {
                "chunk_id": r["id"],
                "article_id": r["article_id"],
                "chunk_index": r["chunk_index"],
                "title": r["title"],
                "url": r["url"],
                "section": r["section"],
                "chunk_text": r["chunk_text"],
                "images": images
            }
            metadata.append(meta)
            texts_to_embed.append(r["chunk_text"])
            corpus_tokens.append(r["chunk_text"].lower().split())

        # 1. Compute Dense Embeddings
        embeddings = self.model.encode(texts_to_embed, convert_to_numpy=True, normalize_embeddings=True)
        embeddings = embeddings.astype(np.float32)

        # 2. Build FAISS Index with Inner Product (Cosine similarity on normalized vectors)
        index = faiss.IndexFlatIP(self.embedding_dim)
        index.add(embeddings)

        # 3. Build BM25 Index
        bm25 = BM25Okapi(corpus_tokens)

        # 4. Persist to disk
        faiss.write_index(index, str(self.faiss_path))
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        self.index = index
        self.metadata = metadata
        self.bm25 = bm25
        self.bm25_corpus = corpus_tokens
        logger.info(f"Indexed {len(metadata)} chunks successfully.")

    def load_index(self):
        """Loads FAISS index and metadata from disk if available."""
        if self.faiss_path.exists() and self.meta_path.exists():
            try:
                self.index = faiss.read_index(str(self.faiss_path))
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                
                # Rebuild in-memory BM25 from metadata
                corpus_tokens = [m["chunk_text"].lower().split() for m in self.metadata]
                self.bm25 = BM25Okapi(corpus_tokens) if corpus_tokens else None
                logger.info(f"Loaded existing index with {len(self.metadata)} chunks.")
            except Exception as e:
                logger.error(f"Error loading index: {e}. Index will be rebuilt when ingestion runs.")
                self.index = None
                self.metadata = []
                self.bm25 = None
        else:
            logger.info("No index files found on disk yet.")

    def query(self, question: str, top_k: int = 4, alpha: float = 0.65) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval combining Dense Semantic search (FAISS) and Sparse Keyword search (BM25).
        Hybrid Score = alpha * dense_score + (1 - alpha) * normalized_bm25_score.
        """
        if not self.index or not self.metadata or self.index.ntotal == 0:
            return []

        # 1. Dense Search
        q_emb = self.model.encode([question], convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
        dense_scores, dense_indices = self.index.search(q_emb, min(top_k * 3, len(self.metadata)))
        
        dense_score_map = {}
        for rank, idx in enumerate(dense_indices[0]):
            if idx >= 0 and idx < len(self.metadata):
                dense_score_map[idx] = float(dense_scores[0][rank])

        # 2. Sparse BM25 Search
        bm25_score_map = {}
        if self.bm25:
            q_tokens = question.lower().split()
            raw_bm25 = self.bm25.get_scores(q_tokens)
            max_bm25 = max(raw_bm25) if len(raw_bm25) > 0 and max(raw_bm25) > 0 else 1.0
            for idx, score in enumerate(raw_bm25):
                if score > 0:
                    bm25_score_map[idx] = float(score / max_bm25)

        # 3. Combine scores
        all_candidate_indices = set(dense_score_map.keys()).union(set(bm25_score_map.keys()))
        combined = []
        for idx in all_candidate_indices:
            d_score = dense_score_map.get(idx, 0.0)
            b_score = bm25_score_map.get(idx, 0.0)
            
            # If no keywords matched in corpus and dense score is moderate, damp score to prevent hallucination
            if b_score == 0.0 and d_score < 0.65:
                d_score = d_score * 0.55

            hybrid_score = (alpha * d_score) + ((1.0 - alpha) * b_score)
            
            item = dict(self.metadata[idx])
            item["score"] = round(hybrid_score, 4)
            item["dense_score"] = round(d_score, 4)
            item["bm25_score"] = round(b_score, 4)
            combined.append(item)

        # Sort descending by hybrid score
        combined.sort(key=lambda x: x["score"], reverse=True)
        return combined[:top_k]
