import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

import shared
from shared.config import settings
from shared.schemas import (
    CustomerEmail, EmailClassification, EmailDraftResponse,
    Citation, QueryResponse
)
from .db import get_inbox_db, init_inbox_db
from .kb_client import KnowledgeBrainClient

logger = logging.getLogger("inbox_agent.pipeline")

class InboxAgentPipeline:
    def __init__(self, kb_client: Optional[KnowledgeBrainClient] = None):
        self.kb_client = kb_client or KnowledgeBrainClient()
        self.api_key = settings.anthropic_api_key
        self.anthropic_client = None
        if self.api_key:
            try:
                import anthropic
                self.anthropic_client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client for Inbox Agent: {e}")

    def load_seed_emails(self) -> List[CustomerEmail]:
        data_path = Path(__file__).resolve().parent.parent / "data" / "customer_emails.json"
        if not data_path.exists():
            logger.error(f"Emails file not found at {data_path}")
            return []

        with open(data_path, "r", encoding="utf-8") as f:
            raw_list = json.load(f)

        conn = get_inbox_db()
        cur = conn.cursor()
        emails = []

        for item in raw_list:
            email_obj = CustomerEmail(
                id=item["id"],
                sender_name=item["sender_name"],
                sender_email=item["sender_email"],
                subject=item["subject"],
                body=item["body"],
                timestamp=item["timestamp"],
                expected_category=item.get("expected_category"),
                expected_risk=item.get("expected_risk"),
                expected_behavior=item.get("expected_behavior"),
                is_synthetic=True
            )
            emails.append(email_obj)

            classification = self.classify_email(email_obj)

            cur.execute(
                """INSERT INTO emails 
                   (id, sender_name, sender_email, subject, body, timestamp, category, urgency, risk_level, risk_factors_json, important_facts_json, expected_behavior, requires_escalation, is_synthetic)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(id) DO UPDATE SET
                       category = ?, urgency = ?, risk_level = ?, risk_factors_json = ?, important_facts_json = ?""",
                (
                    email_obj.id, email_obj.sender_name, email_obj.sender_email, email_obj.subject, email_obj.body, email_obj.timestamp,
                    classification.category, classification.urgency, classification.risk_level,
                    json.dumps(classification.risk_factors), json.dumps(item.get("important_facts", [])),
                    item.get("expected_behavior", ""), 1 if item.get("requires_escalation") else 0,
                    classification.category, classification.urgency, classification.risk_level,
                    json.dumps(classification.risk_factors), json.dumps(item.get("important_facts", []))
                )
            )

        conn.commit()
        conn.close()
        logger.info(f"Loaded and classified {len(emails)} customer emails.")
        return emails

    def classify_email(self, email: CustomerEmail) -> EmailClassification:
        content = f"{email.subject} {email.body}".lower()
        subj_l = email.subject.lower()
        risk_factors = []
        urgency = "low"
        risk_level = "low"

        # 1. Financial risk: actual billing disputes, refunds, or chargebacks (not routine pricing setups)
        if any(w in content for w in ["refund", "chargeback", "charged twice", "double charge", "dispute the charge", "debited", "billing error", "money-back"]):
            risk_factors.append("financial_exposure")
            risk_level = "high"

        # Legal & High Complaint
        if any(w in content for w in ["lawyer", "legal action", "furious", "unacceptable", "broken", "complaint", "embarrassment"]):
            risk_factors.append("legal_reputation_risk")
            if risk_level != "critical":
                risk_level = "high"

        # Security & Service Outage
        if any(w in content for w in ["brute force", "failed admin login", "database connection", "site down", "hacked", "hipaa", "security"]):
            risk_factors.append("security_incident_risk")
            risk_level = "critical"
            urgency = "urgent"

        # Commercial commitment
        if any(w in content for w in ["firm estimate", "fixed price", "guarantee delivery", "quote request"]):
            risk_factors.append("commercial_commitment_risk")
            if any(w in content for w in ["fixed price", "guarantee", "timeline to deliver", "deadline"]):
                risk_level = "high"
            elif risk_level == "low":
                risk_level = "medium"

        # Urgency keywords
        if any(w in content for w in ["urgent", "immediately", "help!", "asap", "today"]):
            if urgency != "urgent":
                urgency = "high"
            if risk_level == "low":
                risk_level = "medium"

        # 2. Category Classification
        if any(w in subj_l for w in ["site down", "database connection", "suspicious login"]):
            category = "urgent_ambiguous"
        elif any(w in content for w in ["refund", "cancellation", "cancel our", "money-back"]):
            category = "refund_cancellation"
        elif any(w in subj_l for w in ["custom integration", "new project", "mls data sync", "quickbooks", "room planner", "build a"]):
            category = "new_project"
        elif any(w in subj_l for w in ["quote request", "how much will it cost", "firm estimate"]):
            category = "quote_request"
        elif any(w in subj_l for w in ["complaint", "furious", "sluggish", "embarrassment"]):
            category = "complaint"
        elif any(w in subj_l for w in ["following up", "follow-up", "checking in"]):
            category = "follow_up"
        elif any(w in subj_l for w in ["cryptocurrency", "qr codes", "forum", "zoom", "multi-currency"]):
            category = "missing_kb_info"
        elif any(subj_l.startswith(p) for p in ["how to", "how do", "how does", "can we", "where do", "what is"]):
            category = "how_to"
        elif any(w in content for w in ["error", "failing", "500", "413", "not appearing", "troubleshoot", "can't load google maps"]):
            category = "technical_troubleshooting"
        elif any(w in content for w in ["cryptocurrency", "qr codes", "bulletin board", "zoom calendar", "hipaa"]):
            category = "missing_kb_info"
        elif any(w in content for w in ["new project", "build an", "hire your", "looking to contract"]):
            category = "new_project"
        elif any(w in content for w in ["quote", "estimate"]):
            category = "quote_request"
        else:
            category = "how_to"

        if category == "missing_kb_info" and risk_level == "low":
            risk_level = "medium"

        return EmailClassification(
            category=category,
            urgency=urgency,
            risk_level=risk_level,
            risk_factors=risk_factors,
            key_facts=[w for w in ["Stripe", "CSV", "Domain", "SSL", "Leads", "Members", "Map", "reCAPTCHA"] if w.lower() in content],
            requires_kb=category in ["how_to", "technical_troubleshooting", "missing_kb_info", "quote_request"],
            can_auto_send=(risk_level == "low")
        )

    def process_email(self, email_id: str, model_version: Optional[str] = None) -> EmailDraftResponse:
        conn = get_inbox_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Email with ID '{email_id}' not found.")

        email = CustomerEmail(
            id=row["id"],
            sender_name=row["sender_name"],
            sender_email=row["sender_email"],
            subject=row["subject"],
            body=row["body"],
            timestamp=row["timestamp"],
            expected_category=row["category"],
            expected_risk=row["risk_level"],
            is_synthetic=bool(row["is_synthetic"])
        )

        classification = self.classify_email(email)

        # Query Task 1 Knowledge Brain API over HTTP
        citations = []
        kb_answer_context = ""
        if classification.requires_kb:
            kb_resp = self.kb_client.query(email.subject + " " + email.body[:200])
            citations = kb_resp.sources
            if kb_resp.status == "success":
                kb_answer_context = kb_resp.answer
            elif kb_resp.status == "insufficient_evidence":
                kb_answer_context = f"[Note: Documentation does not fully cover this request. Reason: {kb_resp.reason}]"

        model_name = model_version or settings.anthropic_model
        draft_reply = self._generate_draft_reply(email, classification, kb_answer_context, citations, model_name)

        guardrails_passed, warnings = self._validate_guardrails(draft_reply, classification)

        cur.execute("SELECT consecutive_unchanged_count, autonomy_eligible, is_autonomy_active FROM category_autonomy_tracker WHERE category = ?", (classification.category,))
        cat_tracker = cur.fetchone()
        consecutive_count = cat_tracker["consecutive_unchanged_count"] if cat_tracker else 0
        autonomy_eligible = bool(cat_tracker["autonomy_eligible"]) if cat_tracker else False
        is_autonomy_active = bool(cat_tracker["is_autonomy_active"]) if cat_tracker else False

        can_auto_send = (
            guardrails_passed and
            classification.risk_level == "low" and
            autonomy_eligible and
            (is_autonomy_active or settings.autonomy_trial_enabled)
        )
        needs_human = not can_auto_send

        now_str = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """INSERT INTO drafts 
               (email_id, draft_subject, draft_reply, sources_json, guardrails_passed, warnings_json, needs_human_review, autonomy_eligible, model_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email.id,
                f"Re: {email.subject}",
                draft_reply,
                json.dumps([c.dict() for c in citations]),
                1 if guardrails_passed else 0,
                json.dumps(warnings),
                1 if needs_human else 0,
                1 if autonomy_eligible else 0,
                model_name,
                now_str
            )
        )
        draft_id = cur.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Processed email {email.id}: Draft #{draft_id} created (needs_human={needs_human}).")

        return EmailDraftResponse(
            email_id=email.id,
            classification=classification,
            retrieved_sources=citations,
            draft_subject=f"Re: {email.subject}",
            draft_reply=draft_reply,
            guardrails_passed=guardrails_passed,
            guardrail_warnings=warnings,
            needs_human_review=needs_human,
            autonomy_eligible=autonomy_eligible,
            model_version=model_name
        )

    def _generate_draft_reply(
        self,
        email: CustomerEmail,
        classification: EmailClassification,
        kb_context: str,
        citations: List[Citation],
        model_name: str
    ) -> str:
        if self.anthropic_client:
            try:
                system_prompt = (
                    "You are a professional Technical Support & Solutions Consultant for Brilliant Directories. "
                    "Draft a concise, courteous email reply to the customer's inquiry. "
                    "STRICT GUARDRAILS: "
                    "1. NEVER promise or confirm financial refunds, discounts, or waivers directly. Defer to billing review. "
                    "2. NEVER guarantee fixed pricing or binding delivery dates for custom projects. Offer a scoping call. "
                    "3. Ground all product instructions strictly in the provided Knowledge Brain context. "
                    "4. If information is missing or uncertain, state this transparently and explain that you are escalating. "
                    "5. Keep the tone warm, clear, and professional."
                )

                citation_refs = "\n".join([f"- {c.title} ({c.url})" for c in citations])
                user_msg = (
                    f"Customer: {email.sender_name} <{email.sender_email}>\n"
                    f"Subject: {email.subject}\n"
                    f"Category: {classification.category} | Risk: {classification.risk_level}\n\n"
                    f"Email Body:\n{email.body}\n\n"
                    f"Knowledge Brain Context:\n{kb_context}\n\n"
                    f"Citations:\n{citation_refs}\n\n"
                    "Draft Reply:"
                )

                resp = self.anthropic_client.messages.create(
                    model=model_name,
                    max_tokens=500,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_msg}]
                )
                return resp.content[0].text.strip()
            except Exception as e:
                logger.warning(f"Claude draft generation failed ({e}). Using grounded template.")

        return self._rule_based_draft(email, classification, kb_context, citations)

    def _rule_based_draft(
        self,
        email: CustomerEmail,
        classification: EmailClassification,
        kb_context: str,
        citations: List[Citation]
    ) -> str:
        greeting = f"Hi {email.sender_name.split()[0]},"
        signoff = "\n\nBest regards,\nTechnical Solutions Team\nBrilliant Directories Support"

        if classification.category == "refund_cancellation":
            body = (
                f"{greeting}\n\n"
                f"Thank you for contacting us regarding your account and billing. We have received your cancellation request. "
                f"Please note that all refund requests are reviewed by our billing department in accordance with our subscription terms. "
                f"I have escalated your ticket to our billing specialist team, who will verify your transaction details and follow up with you within one business day."
            )
        elif classification.category == "quote_request" or classification.category == "new_project":
            body = (
                f"{greeting}\n\n"
                f"Thank you for reaching out regarding your project: '{email.subject}'. "
                f"To provide an accurate architecture assessment and task breakdown without unexpected scope creep, "
                f"we review custom development requirements through a structured discovery process. "
                f"Our engineering team would be delighted to schedule a brief technical consultation to walk through your specifications."
            )
        elif classification.category == "complaint":
            body = (
                f"{greeting}\n\n"
                f"Thank you for bringing this to our immediate attention. We sincerely apologize for the frustration this issue has caused. "
                f"Our technical team is reviewing this with high priority to ensure your directory operation remains stable. "
                f"A senior technical specialist has been assigned to investigate and provide an update shortly."
            )
        elif classification.category == "missing_kb_info":
            body = (
                f"{greeting}\n\n"
                f"Thank you for reaching out. Regarding your inquiry on '{email.subject}', this specific capability is not a standard out-of-the-box "
                f"feature in the core Brilliant Directories platform. "
                f"I have escalated this inquiry to our technical architecture team to assess whether a custom widget or third-party integration can support your workflow."
            )
        else: # how_to & technical_troubleshooting
            source_links = "\n".join([f"- [{c.title}]({c.url})" for c in citations[:2]]) if citations else ""
            clean_kb = kb_context.replace("[Note:", "").strip() if kb_context else "Please refer to the Brilliant Directories admin panel."
            body = (
                f"{greeting}\n\n"
                f"Thank you for reaching out to Brilliant Directories support!\n\n"
                f"{clean_kb}\n\n"
                f"For full step-by-step guidance and screenshots, please see:\n{source_links}" if source_links else f"{clean_kb}"
            )

        return body + signoff

    def _validate_guardrails(self, draft: str, classification: EmailClassification) -> Tuple[bool, List[str]]:
        warnings = []
        lower_draft = draft.lower()

        refund_commitments = [
            "we have refunded", "i have refunded", "your refund has been processed",
            "we will refund your money today", "i guarantee a full refund", "here is your refund"
        ]
        if any(phrase in lower_draft for phrase in refund_commitments):
            warnings.append("BLOCKED: Draft makes an unauthorized binding refund promise.")

        if re.search(r"(fixed price is \$|we guarantee the price of \$|this will only cost \$)", lower_draft):
            warnings.append("BLOCKED: Draft makes an unauthorized fixed commercial price guarantee.")

        if re.search(r"(we guarantee delivery by tomorrow|guaranteed to launch in \d+ days|we promise completion by)", lower_draft):
            warnings.append("BLOCKED: Draft makes an unauthorized binding delivery deadline commitment.")

        passed = len(warnings) == 0
        return passed, warnings
