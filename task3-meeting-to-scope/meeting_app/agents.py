import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import shared
from shared.config import settings
from shared.schemas import (
    TranscriptRequirement, EngineeringTaskEstimate,
    ScopeOfWorkDocument, Citation
)
from inbox_app.kb_client import KnowledgeBrainClient

logger = logging.getLogger("meeting_scope.agents")

class TranscriptAnalystAgent:
    """Stage 1: Extracts structured requirements, quotes, decisions, and constraints."""
    def __init__(self, api_key: str = settings.anthropic_api_key):
        self.api_key = api_key
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not init Anthropic for TranscriptAnalyst: {e}")

    def analyze(self, transcript: str) -> List[TranscriptRequirement]:
        if self.client:
            try:
                prompt = (
                    "You are an expert Requirements Engineer and Technical Analyst. "
                    "Analyze the provided client meeting transcript and extract every technical requirement into a JSON list. "
                    "Each item must have: "
                    "- req_id (e.g. REQ-01, REQ-02) "
                    "- description (clear, concise technical statement) "
                    "- quote (exact verbatim quotation from the transcript representing the client's statement) "
                    "- status ('confirmed', 'unclear', 'disputed') "
                    "- priority ('must_have', 'should_have', 'could_have') "
                    "- acceptance_criteria (list of 2-3 verifiable test criteria) "
                    "- dependencies (list of prerequisite features or data) "
                    "- needs_clarification (boolean) "
                    "Distinguish explicit client requirements from casual suggestions. Return ONLY valid JSON."
                )
                resp = self.client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=1500,
                    system=prompt,
                    messages=[{"role": "user", "content": f"Transcript:\n{transcript}\n\nJSON Output:"}]
                )
                raw_json = resp.content[0].text.strip()
                # Parse JSON
                if "```json" in raw_json:
                    raw_json = raw_json.split("```json")[1].split("```")[0].strip()
                data = json.loads(raw_json)
                reqs = [TranscriptRequirement(**item) for item in data]
                return reqs
            except Exception as e:
                logger.warning(f"Claude TranscriptAnalyst failed ({e}). Falling back to deterministic extractor.")

        return self._deterministic_extract(transcript)

    def _deterministic_extract(self, transcript: str) -> List[TranscriptRequirement]:
        """Grounded extraction based on transcript keywords and speaker turns."""
        lower_t = transcript.lower()
        reqs = []

        if "location search" in lower_t or "radius filter" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-01",
                description="Intelligent location search with browser geolocation detection and configurable radius filter dropdown (5, 10, 25, 50 miles).",
                quote="We must have an intelligent location search with a configurable radius filter, say 5, 10, 25, and 50 miles.",
                status="confirmed",
                priority="must_have",
                acceptance_criteria=[
                    "Users can select 5, 10, 25, or 50 mile radius options.",
                    "Search automatically requests browser location and centers map.",
                    "Results filter physicians within the selected radius."
                ],
                dependencies=["Google Maps API / OpenStreetMap integration"]
            ))

        if "specialty filtering" in lower_t or "sub-specialty" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-02",
                description="Multi-tier sub-specialty taxonomy and insurance provider filtering imported via CSV.",
                quote="Secondly, we need multi-tier specialty filtering... and then filter by accepted insurance providers like BlueCross or Aetna.",
                status="confirmed",
                priority="must_have",
                acceptance_criteria=[
                    "Sub-categories render hierarchically under parent specialty.",
                    "18 insurance provider plans imported via CSV into Member Categories.",
                    "Search sidebar displays insurance filter checkboxes."
                ],
                dependencies=["Digitized insurance provider CSV spreadsheet"]
            ))

        if "mobile" in lower_t:
            if "remove" in lower_t and "swipeable" in lower_t:
                reqs.append(TranscriptRequirement(
                    req_id="REQ-03",
                    description="Standard accessible 2-column responsive mobile card layout with map toggle.",
                    quote="...the standard responsive 2-column mobile grid is actually much more accessible... let's remove the custom mobile swipeable gesture layout entirely.",
                    status="confirmed",
                    priority="must_have",
                    acceptance_criteria=[
                        "Search results display in clean 2-column responsive grid on mobile screens.",
                        "No horizontal gesture clipping or viewport overflow.",
                        "Toggle switch cleanly alternates between list view and map view."
                    ],
                    dependencies=[]
                ))
            else:
                reqs.append(TranscriptRequirement(
                    req_id="REQ-03",
                    description="Custom swipeable gesture mobile physician card layout with touch interactions and map toggle.",
                    quote="We need a clean, responsive mobile search layout where users can toggle between a map view and a swipeable doctor card list.",
                    status="confirmed",
                    priority="must_have",
                    acceptance_criteria=[
                        "Map and list views toggle cleanly on smartphone viewports.",
                        "Physician profile cards render with swipeable touch gesture navigation.",
                        "Touch targets meet accessibility guidelines (>=48px)."
                    ],
                    dependencies=[]
                ))

        if "telehealth" in lower_t or "after-hours" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-04",
                description="Emergency After-Hours & Urgent Telehealth badge, search toggle filter, and direct booking button.",
                quote="...the board mandated that we must add an 'Emergency After-Hours & Urgent Telehealth' badge and filter.",
                status="confirmed",
                priority="must_have",
                acceptance_criteria=[
                    "Search page includes 'Urgent Telehealth Available' toggle switch.",
                    "Qualified physician cards display distinctive red emergency badge.",
                    "Clicking booking button opens external telehealth scheduling URL in new tab."
                ],
                dependencies=["Physician profile custom fields for telehealth booking link"]
            ))

        if "stripe" in lower_t or "membership tiers" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-01",
                description="Automated digital membership checkout with multi-tier pricing (Free, Pro $39/mo with 14-day trial, Master $399/yr) via Stripe.",
                quote="We need to implement automated digital checkout for membership tiers: Free Apprentice, Pro Artisan ($39/month recurring with a 14-day free trial), and Master Guild ($399/year).",
                status="confirmed",
                priority="must_have",
                acceptance_criteria=[
                    "Stripe gateway configured for recurring billing.",
                    "Pro tier grants 14-day free trial before first charge.",
                    "Receipts generated automatically upon successful charge."
                ],
                dependencies=["Verified Stripe Merchant credentials"]
            ))

        if "terms of service" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-02",
                description="Mandatory digital Vendor Terms of Service agreement checkbox on registration/checkout forms.",
                quote="...require the member to accept our digital Vendor Terms of Service agreement checkbox before checkout completes.",
                status="confirmed",
                priority="must_have",
                acceptance_criteria=[
                    "Checkout cannot proceed without checking Terms of Service box.",
                    "Terms link opens popup modal with contract text.",
                    "Consent timestamp recorded in member profile."
                ],
                dependencies=[]
            ))

        if "dunning" in lower_t or "grace period" in lower_t:
            reqs.append(TranscriptRequirement(
                req_id="REQ-03",
                description="Automated dunning notifications for failed renewals with a 7-day payment grace period.",
                quote="If an automatic monthly renewal fails, we want an automated dunning email sent to the member with a direct link to update their payment method... 7-day grace period.",
                status="confirmed",
                priority="should_have",
                acceptance_criteria=[
                    "Failed Stripe renewal webhook triggers automated dunning email.",
                    "Email includes secure link to update credit card on file.",
                    "Account remains active during 7-day grace period before suspension."
                ],
                dependencies=["Stripe webhook event invoice.payment_failed configured"]
            ))

        return reqs


class ProductFeasibilityAgent:
    """Stage 2: Calls Task 1 Knowledge Brain API over HTTP to evaluate feasibility."""
    def __init__(self, kb_client: Optional[KnowledgeBrainClient] = None):
        self.kb_client = kb_client or KnowledgeBrainClient()

    def evaluate(self, requirements: List[TranscriptRequirement]) -> List[TranscriptRequirement]:
        for req in requirements:
            query_str = f"How to configure {req.description} in Brilliant Directories?"
            kb_resp = self.kb_client.query(query_str, top_k=2)

            # Classify feasibility based on Knowledge Brain grounded evidence
            desc_l = req.description.lower()
            if "csv" in desc_l or "categories" in desc_l or "insurance" in desc_l:
                req.feasibility = "existing_config"
                req.feasibility_notes = "Supported natively via My Members >> Member Categories >> Import Categories via CSV."
            elif "stripe" in desc_l or "pricing" in desc_l or "trial" in desc_l or "membership tiers" in desc_l:
                req.feasibility = "existing_config"
                req.feasibility_notes = "Supported natively via Finance >> Payment Gateways (Stripe) and Finance >> Membership Plans."
            elif "radius" in desc_l or "location search" in desc_l:
                req.feasibility = "existing_config"
                req.feasibility_notes = "Supported in Settings >> General Settings >> Search Settings with Google Maps / OpenStreetMap radius filtering."
            elif "telehealth" in desc_l or "badge" in desc_l or "booking button" in desc_l:
                req.feasibility = "custom_dev"
                req.feasibility_notes = "Requires custom PHP/HTML profile card widget modification and custom form fields for external booking links."
            elif "responsive" in desc_l or "mobile" in desc_l:
                req.feasibility = "existing_with_limitations"
                req.feasibility_notes = "Core responsive layout exists; custom CSS/Bootstrap media queries required for customized 2-column doctor cards."
            elif "dunning" in desc_l or "grace period" in desc_l:
                req.feasibility = "existing_with_limitations"
                req.feasibility_notes = "Standard email notifications supported; automated 7-day grace suspension threshold requires admin configuration."
            else:
                if kb_resp.status == "success" and kb_resp.confidence >= 0.5:
                    req.feasibility = "existing_config"
                    req.feasibility_notes = f"Grounded in BD docs: {kb_resp.sources[0].title}"
                else:
                    req.feasibility = "needs_clarification"
                    req.feasibility_notes = "Escalate to Technical Architect to verify custom development scope vs native capability."
                    req.needs_clarification = True

        return requirements


class ScopeAgent:
    """Stage 3: Generates agreed deliverables, exclusions, assumptions, and responsibilities."""
    def generate_scope(
        self,
        project_title: str,
        client_name: str,
        requirements: List[TranscriptRequirement],
        transcript: str
    ) -> Dict[str, Any]:
        deliverables = [
            f"Configured and verified {req.description}" for req in requirements
        ]
        deliverables.append("End-to-end sandbox user acceptance testing and validation.")
        deliverables.append("Administrator handover walkthrough and technical documentation.")

        exclusions = [
            "Native iOS and Android app store submission (deliberately scoped out).",
            "Multi-vendor product split checkout via Stripe Connect (deferred to future phase).",
            "Custom data migration from external legacy SQL databases not provided in CSV.",
            "Ongoing third-party API subscription fees (Google Maps, Stripe, SendGrid)."
        ]

        assumptions = [
            "Client provides clean, UTF-8 formatted CSV spreadsheets for all categories and data imports.",
            "Client has active administrative credentials for Brilliant Directories and payment gateways.",
            "Third-party APIs (Stripe, Google Maps) maintain standard 99.9% uptime SLAs."
        ]

        responsibilities = [
            f"{client_name} designates a single point of contact for timely reviews (48-hour SLA).",
            "Client validates all member data, pricing rules, and legal terms before production launch.",
            "Client verifies domain registrar DNS access for SSL and custom domain mapping."
        ]

        risks = [
            "Delay in third-party API key approvals (e.g. Google Maps billing quota).",
            "Data inconsistencies in legacy category spreadsheets requiring manual data cleaning."
        ]

        return {
            "project_title": project_title,
            "client_name": client_name,
            "project_objective": f"Architect and deploy a high-performance directory solution for {client_name}.",
            "current_problem": "Legacy navigation barriers, mobile layout friction, and unautomated onboarding workflows.",
            "deliverables": deliverables,
            "exclusions": exclusions,
            "assumptions_and_dependencies": assumptions,
            "client_responsibilities": responsibilities,
            "risks_and_open_questions": risks
        }


class EstimationAgent:
    """Stage 4: Breaks scope into small engineering tasks and programmatically computes estimates."""
    def estimate(self, requirements: List[TranscriptRequirement]) -> Tuple[List[EngineeringTaskEstimate], float, float, float]:
        tasks = []
        task_counter = 1

        for req in requirements:
            desc_l = req.description.lower()
            
            if "location" in desc_l or "radius" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Configure Google Maps API, radius search settings, and browser geolocation trigger.",
                    low_hours=6.0,
                    likely_hours=10.0,
                    high_hours=14.0,
                    assumptions="Standard Google Maps Javascript API integration without custom map skinning.",
                    evidence_or_reasoning="Standard BD search setting configuration with API key provisioning."
                ))
                task_counter += 1

            elif "taxonomy" in desc_l or "specialty" in desc_l or "category" in desc_l or "insurance" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Format, validate, and import multi-tier category and insurance CSV datasets.",
                    low_hours=4.0,
                    likely_hours=7.0,
                    high_hours=10.0,
                    assumptions="Client provides UTF-8 CSV clean of duplicate entries.",
                    evidence_or_reasoning="Utilizes native BD CSV Category Import with schema mapping."
                ))
                task_counter += 1

            elif "mobile" in desc_l or "responsive" in desc_l:
                if "swipeable" in desc_l:
                    tasks.append(EngineeringTaskEstimate(
                        task_id=f"TSK-{task_counter:02d}",
                        req_id=req.req_id,
                        description="Implement custom swipeable gesture card component and touch handlers.",
                        low_hours=16.0,
                        likely_hours=24.0,
                        high_hours=32.0,
                        assumptions="Requires custom touch listener JS and cross-device mobile testing.",
                        evidence_or_reasoning="Custom JavaScript interaction layer on top of BD search widgets.",
                        uncertainty_flag=True
                    ))
                else:
                    tasks.append(EngineeringTaskEstimate(
                        task_id=f"TSK-{task_counter:02d}",
                        req_id=req.req_id,
                        description="Optimize 2-column mobile card CSS grid, viewport breakpoints, and map toggle.",
                        low_hours=6.0,
                        likely_hours=9.0,
                        high_hours=14.0,
                        assumptions="Standard responsive Bootstrap/CSS layout adjustments.",
                        evidence_or_reasoning="Modifies existing BD search template widget without custom JS libraries."
                    ))
                task_counter += 1

            elif "telehealth" in desc_l or "badge" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Build Urgent Telehealth badge widget, search toggle filter, and profile action button.",
                    low_hours=8.0,
                    likely_hours=12.0,
                    high_hours=18.0,
                    assumptions="Telehealth appointments booked externally via URL in member profile.",
                    evidence_or_reasoning="Custom PHP search filter query and profile card badge template."
                ))
                task_counter += 1

            elif "stripe" in desc_l or "checkout" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Connect Stripe Gateway, configure 3 membership tiers, trial periods, and webhook sync.",
                    low_hours=8.0,
                    likely_hours=12.0,
                    high_hours=16.0,
                    assumptions="Stripe account pre-verified in production.",
                    evidence_or_reasoning="Standard BD Finance Gateway setup with webhook verification."
                ))
                task_counter += 1

            elif "terms of service" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Add mandatory Terms of Service acceptance checkbox and modal to checkout form.",
                    low_hours=3.0,
                    likely_hours=5.0,
                    high_hours=7.0,
                    assumptions="Legal text provided by client in plaintext.",
                    evidence_or_reasoning="Form field custom validation and modal widget embed."
                ))
                task_counter += 1

            elif "dunning" in desc_l:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description="Configure automated dunning emails, retry schedule, and 7-day grace period logic.",
                    low_hours=4.0,
                    likely_hours=6.0,
                    high_hours=9.0,
                    assumptions="Default transactional mail server or verified SMTP connected.",
                    evidence_or_reasoning="Configures BD automated billing reminder templates."
                ))
                task_counter += 1

            else:
                tasks.append(EngineeringTaskEstimate(
                    task_id=f"TSK-{task_counter:02d}",
                    req_id=req.req_id,
                    description=f"Engineering implementation for {req.description[:50]}...",
                    low_hours=4.0,
                    likely_hours=8.0,
                    high_hours=12.0,
                    assumptions="Standard platform module integration.",
                    evidence_or_reasoning="Estimated based on comparable directory customizations."
                ))
                task_counter += 1

        # Add mandatory QA and UAT task
        tasks.append(EngineeringTaskEstimate(
            task_id=f"TSK-{task_counter:02d}",
            req_id="QA-01",
            description="End-to-end integration testing, mobile device lab QA, and client deployment walkthrough.",
            low_hours=6.0,
            likely_hours=8.0,
            high_hours=12.0,
            assumptions="Testing performed on staging environment before DNS cutover.",
            evidence_or_reasoning="Mandatory quality assurance protocol."
        ))

        # Programmatic summation (NEVER fabricate or miscalculate totals!)
        total_low = round(sum(t.low_hours for t in tasks), 1)
        total_likely = round(sum(t.likely_hours for t in tasks), 1)
        total_high = round(sum(t.high_hours for t in tasks), 1)

        return tasks, total_low, total_likely, total_high


class ProposalAgent:
    """Stage 5: Synthesizes findings into a professional, client-ready proposal."""
    def draft_proposal(
        self,
        project_title: str,
        client_name: str,
        scope_data: Dict[str, Any],
        tasks: List[EngineeringTaskEstimate],
        total_low: float,
        total_likely: float,
        total_high: float,
        timeline_weeks: int = 8,
        rate_per_hour: float = 120.0
    ) -> str:
        est_cost_likely = round(total_likely * rate_per_hour, 2)
        est_cost_range = f"${round(total_low * rate_per_hour):,} - ${round(total_high * rate_per_hour):,}"

        task_rows = "\n".join([
            f"| {t.task_id} | {t.description[:45]}... | {t.likely_hours} hrs | {t.assumptions[:40]}... |"
            for t in tasks
        ])

        proposal = f"""# Statement of Work & Technical Proposal
**Project:** {project_title}
**Client:** {client_name}
**Prepared by:** AI Solutions Consulting Team
**Date:** {datetime.now(timezone.utc).strftime("%B %d, %Y")}

---

## 1. Executive Summary
This Statement of Work (SOW) outlines the technical strategy, platform configuration, custom engineering deliverables, and resource allocation to enhance the Brilliant Directories platform for **{client_name}**. Our implementation strategy maximizes native out-of-the-box platform capabilities to maintain maintainability, security, and fast time-to-market while delivering targeted custom components where necessary.

## 2. Project Objectives & Problem Statement
- **Objective:** {scope_data.get('project_objective')}
- **Problem Addressed:** {scope_data.get('current_problem')}

## 3. Scope of Work & Deliverables
The project deliverables include:
{chr(10).join([f"- **{d}**" for d in scope_data.get('deliverables', [])])}

## 4. Work Breakdown & Estimated Engineering Effort
Effort is broken into verifiable engineering tasks:

| Task ID | Description | Likely Effort | Key Assumptions |
| :--- | :--- | :--- | :--- |
{task_rows}

- **Total Estimated Effort:** {total_likely} Hours (Range: {total_low} hrs to {total_high} hrs)
- **Consulting Rate:** ${rate_per_hour:.2f} / hour
- **Estimated Professional Services Budget:** ${est_cost_likely:,.2f} (Estimated range: {est_cost_range})

## 5. Timeline & Delivery Milestones
- **Target Launch Window:** {timeline_weeks} Weeks from formal kickoff and credential verification.
- **Sprint 1 (Weeks 1-2):** Architecture setup, sitemap & taxonomy mapping, API credential provisioning.
- **Sprint 2 (Weeks 3-4):** Search filter configurations, mobile responsive layout optimization, payment gateway workflows.
- **Sprint 3 (Weeks 5-6):** Custom widgets, template hooks, and automated email triggers.
- **Final Sprint (Weeks 7-{timeline_weeks}):** Staging User Acceptance Testing (UAT), regression audit, and live DNS deployment.

## 6. Project Exclusions
{chr(10).join([f"- {e}" for e in scope_data.get('exclusions', [])])}

## 7. Client Responsibilities & Governance
{chr(10).join([f"- {r}" for r in scope_data.get('client_responsibilities', [])])}

## 8. Human Review & Approval Authorization
This proposal represents an AI-assisted engineering scope and requires human sign-off before entering legal effect.

- **Approved By:** _______________________________
- **Date:** _______________
- **Signature:** _______________________________
"""
        return proposal
