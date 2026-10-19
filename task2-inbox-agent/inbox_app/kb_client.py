import httpx
import logging
import uuid
from typing import Dict, Any, Optional
import shared
from shared.config import settings
from shared.schemas import QueryRequest, QueryResponse, Citation

logger = logging.getLogger("inbox_agent.kb_client")

class KnowledgeBrainClient:
    def __init__(self, base_url: str = settings.knowledge_brain_base_url):
        self.base_url = base_url.rstrip("/")
        self.timeout = 10.0

    def check_health(self) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"Knowledge Brain health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}

    def query(self, question: str, top_k: int = 4, min_confidence: float = 0.35) -> QueryResponse:
        url = f"{self.base_url}/query"
        payload = {
            "question": question,
            "top_k": top_k,
            "min_confidence": min_confidence
        }
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return QueryResponse(**data)
            except Exception as e:
                logger.warning(f"KB HTTP query attempt {attempt+1} failed: {e}")
                if attempt == max_retries:
                    return QueryResponse(
                        request_id=f"err_{uuid.uuid4().hex[:8]}",
                        question=question,
                        answer="The Knowledge Brain service is currently unreachable over HTTP. An escalation has been triggered.",
                        status="error",
                        sources=[],
                        confidence=0.0,
                        needs_human=True,
                        reason=f"HTTP connection to Knowledge Brain failed: {str(e)}",
                        model="http_fallback",
                        latency_ms=0.0
                    )
