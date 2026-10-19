import pytest
from fastapi.testclient import TestClient
import shared
from kb_app.main import app
from kb_app.db import get_db_connection
client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert data["articles_indexed"] >= 10
    assert data["index_vectors_loaded"] >= 10

def test_query_supported_question():
    payload = {
        "question": "How do I import categories using a CSV file in Brilliant Directories?",
        "top_k": 3,
        "min_confidence": 0.35
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["sources"]) > 0
    assert "CSV" in data["answer"] or "category" in data["answer"].lower()
    assert data["needs_human"] is False
    assert any("import-categories" in s["url"] for s in data["sources"])

def test_query_unsupported_question_abstention_and_escalation():
    payload = {
        "question": "How do I configure quantum teleportation and warp drive engines?",
        "top_k": 3,
        "min_confidence": 0.50
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "insufficient_evidence"
    assert data["needs_human"] is True
    assert data["reason"] is not None
    assert "escalation" in data["reason"].lower()

def test_escalation_lifecycle():
    # 1. Create escalation
    esc_payload = {
        "question": "Does Brilliant Directories support cryptocurrency payments natively?",
        "reason": "Feature question outside standard knowledge documentation."
    }
    create_resp = client.post("/escalations", json=esc_payload)
    assert create_resp.status_code == 200
    esc_data = create_resp.json()
    esc_id = esc_data["id"]
    assert esc_id > 0
    assert esc_data["is_indexed"] is False

    # 2. Resolve escalation with expert answer
    resolve_payload = {
        "expert_answer": "Brilliant Directories does not support native direct cryptocurrency gateways. However, directory owners can integrate third-party payment widgets such as BitPay via custom HTML iFrames.",
        "resolved_by": "Senior Architect Alex",
        "index_as_knowledge": True
    }
    resolve_resp = client.post(f"/escalations/{esc_id}/resolve", json=resolve_payload)
    assert resolve_resp.status_code == 200
    resolved_data = resolve_resp.json()
    assert resolved_data["is_indexed"] is True
    assert resolved_data["resolved_by"] == "Senior Architect Alex"

    # 3. Verify newly indexed knowledge is retrievable
    query_resp = client.post("/query", json={"question": "Does Brilliant Directories support cryptocurrency payments?"})
    assert query_resp.status_code == 200
    q_data = query_resp.json()
    assert "cryptocurrency" in q_data["answer"].lower() or "bitpay" in q_data["answer"].lower()
