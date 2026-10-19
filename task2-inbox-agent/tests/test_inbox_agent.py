import pytest
import shared
from inbox_app.main import (
    initialize_inbox, get_all_emails, get_email_details, process_single_email,
    submit_review, get_tracker_stats, get_sent_emails
)
from inbox_app.pipeline import InboxAgentPipeline
from shared.schemas import CustomerEmail, EmailClassification

def test_load_50_customer_emails():
    count = initialize_inbox()
    assert count == 50, f"Expected 50 customer emails loaded, got {count}"
    
    emails = get_all_emails()
    assert len(emails) == 50
    categories = {e["category"] for e in emails}
    expected_categories = {
        "how_to", "technical_troubleshooting", "new_project", "refund_cancellation",
        "complaint", "quote_request", "follow_up", "urgent_ambiguous", "missing_kb_info"
    }
    for cat in expected_categories:
        assert cat in categories, f"Category {cat} missing from loaded dataset"

def test_risk_classification():
    pipeline = InboxAgentPipeline()
    
    # High risk refund email
    refund_email = CustomerEmail(
        id="TEST-REFUND",
        sender_name="Angry Buyer",
        sender_email="buyer@test.com",
        subject="Demanding full refund on billing error or chargeback",
        body="I was charged $450 and demand an immediate refund back to my card!",
        timestamp="2026-10-16T10:00:00Z"
    )
    classif = pipeline.classify_email(refund_email)
    assert classif.risk_level in ["high", "critical"]
    assert classif.category == "refund_cancellation"
    assert "financial_exposure" in classif.risk_factors

    # Low risk how-to email
    howto_email = CustomerEmail(
        id="TEST-HOWTO",
        sender_name="Happy User",
        sender_email="user@test.com",
        subject="How to import categories with CSV file",
        body="Can you guide me on how to import categories via CSV?",
        timestamp="2026-10-16T10:00:00Z"
    )
    classif2 = pipeline.classify_email(howto_email)
    assert classif2.risk_level == "low"
    assert classif2.category == "how_to"

def test_process_email_draft_and_guardrails():
    # Process email EM-001 (Category CSV import)
    draft_res = process_single_email("EM-001")
    assert draft_res.email_id == "EM-001"
    assert draft_res.classification.category == "how_to"
    assert draft_res.guardrails_passed is True
    assert len(draft_res.draft_reply) > 50

    # Test safety guardrail catches unauthorized refund promise
    pipeline = InboxAgentPipeline()
    bad_draft = "Dear customer, we apologize and I have refunded your $450 back to your card today."
    passed, warnings = pipeline._validate_guardrails(bad_draft, draft_res.classification)
    assert passed is False
    assert any("refund" in w.lower() for w in warnings)

def test_twenty_consecutive_draft_rule_and_reset():
    category = "how_to"
    
    # 1. Simulate 20 consecutive unchanged approvals
    for i in range(1, 21):
        res = submit_review(
            email_id="EM-001",
            draft_id=1,
            action="approve",
            original_draft="Standard greeting and guidance.",
            final_reply="Standard greeting and guidance.",
            category=category,
            risk_level="low",
            reviewer="QA Senior"
        )
        assert res["is_changed"] is False

    assert res["consecutive_unchanged_count"] >= 20
    assert res["autonomy_eligible"] is True

    # 2. Simulate 1 human edit -> MUST RESET COUNTER TO 0
    edit_res = submit_review(
        email_id="EM-001",
        draft_id=1,
        action="edit",
        original_draft="Standard greeting and guidance.",
        final_reply="Standard greeting and guidance with custom technical footnote.",
        category=category,
        risk_level="low",
        reviewer="QA Senior",
        notes="Added extra troubleshooting step"
    )
    assert edit_res["is_changed"] is True
    assert edit_res["consecutive_unchanged_count"] == 0
    assert edit_res["autonomy_eligible"] is False
    assert edit_res["reset_reason"] is not None

def test_simulated_sent_log():
    submit_review(
        email_id="EM-005",
        draft_id=1,
        action="approve",
        original_draft="Hello, here are the DNS settings...",
        final_reply="Hello, here are the DNS settings...",
        category="how_to",
        risk_level="low",
        reviewer="Consultant"
    )
    sent_list = get_sent_emails()
    assert len(sent_list) > 0
    assert any(s["email_id"] == "EM-005" for s in sent_list)
