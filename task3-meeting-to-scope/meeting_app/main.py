import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import shared
from shared.config import settings
from shared.schemas import (
    TranscriptRequirement, EngineeringTaskEstimate,
    ScopeOfWorkDocument, ScopeDiffReport
)
from .db import (
    init_meeting_db, save_project_version, approve_project_version,
    get_project_version, get_approved_baseline, get_meeting_db
)
from .agents import (
    TranscriptAnalystAgent, ProductFeasibilityAgent,
    ScopeAgent, EstimationAgent, ProposalAgent
)
from .scope_diff import ScopeChangeDetector

logger = logging.getLogger("meeting_scope.main")

# Initialize database
init_meeting_db()

analyst = TranscriptAnalystAgent()
feasibility = ProductFeasibilityAgent()
scope_agent = ScopeAgent()
estimator = EstimationAgent()
proposal_agent = ProposalAgent()
diff_detector = ScopeChangeDetector()

def process_transcript(
    project_id: str,
    title: str,
    client_name: str,
    version_num: int,
    transcript_text: str,
    timeline_weeks: int = 8
) -> ScopeOfWorkDocument:
    """
    Executes the 5-stage Meeting to Scope agent pipeline:
    1. Analyst extracts structured requirements from transcript.
    2. Feasibility agent checks Knowledge Brain API over HTTP.
    3. Scope agent defines deliverables, exclusions, assumptions.
    4. Estimator generates tasks, low/likely/high hours programmatically.
    5. Proposal agent formats executive SOW document.
    """
    logger.info(f"Processing transcript for {project_id} Version {version_num}...")

    # Stage 1: Extraction
    raw_reqs = analyst.analyze(transcript_text)

    # Stage 2: Feasibility via Task 1 HTTP API
    validated_reqs = feasibility.evaluate(raw_reqs)

    # Stage 3: Scope Document
    scope_data = scope_agent.generate_scope(title, client_name, validated_reqs, transcript_text)

    # Stage 4: Task Hour Estimates
    tasks, low_h, likely_h, high_h = estimator.estimate(validated_reqs)

    # Stage 5: Proposal Generation
    proposal_text = proposal_agent.draft_proposal(
        project_title=title,
        client_name=client_name,
        scope_data=scope_data,
        tasks=tasks,
        total_low=low_h,
        total_likely=likely_h,
        total_high=high_h,
        timeline_weeks=timeline_weeks
    )

    # Persist unapproved version in SQLite
    save_project_version(
        project_id=project_id,
        title=title,
        client_name=client_name,
        version_num=version_num,
        transcript_text=transcript_text,
        requirements=[r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in validated_reqs],
        tasks=[t.model_dump() if hasattr(t, 'model_dump') else t.dict() for t in tasks],
        scope_doc=scope_data,
        proposal_text=proposal_text,
        total_low=low_h,
        total_likely=likely_h,
        total_high=high_h
    )

    now_iso = settings.sqlite_db_path.stat().st_mtime if settings.sqlite_db_path.exists() else 0
    import datetime
    created_at_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return ScopeOfWorkDocument(
        project_id=project_id,
        version=version_num,
        project_title=title,
        client_name=client_name,
        project_objective=scope_data["project_objective"],
        current_problem=scope_data["current_problem"],
        requirements=validated_reqs,
        deliverables=scope_data["deliverables"],
        exclusions=scope_data["exclusions"],
        assumptions_and_dependencies=scope_data["assumptions_and_dependencies"],
        client_responsibilities=scope_data["client_responsibilities"],
        risks_and_open_questions=scope_data["risks_and_open_questions"],
        tasks=tasks,
        total_low_hours=low_h,
        total_likely_hours=likely_h,
        total_high_hours=high_h,
        proposal_text=proposal_text,
        is_approved=False,
        created_at=created_at_str
    )

def approve_version(project_id: str, version_num: int, reviewer: str = "Senior Technical Consultant") -> Dict[str, Any]:
    """Locks version as officially approved baseline."""
    return approve_project_version(project_id, version_num, reviewer)

def compare_revision(project_id: str, new_version_num: int) -> ScopeDiffReport:
    """Compares revision version against approved baseline."""
    new_v = get_project_version(project_id, new_version_num)
    if not new_v:
        raise ValueError(f"Version {new_version_num} for project {project_id} not found.")

    reqs = [TranscriptRequirement(**r) for r in new_v["requirements"]]
    tasks = [EngineeringTaskEstimate(**t) for t in new_v["tasks"]]

    return diff_detector.compare(
        project_id=project_id,
        new_requirements=reqs,
        new_tasks=tasks,
        new_version_num=new_version_num
    )

def bootstrap_transcripts(force: bool = False):
    """Initializes and processes all 3 realistic meeting transcripts."""
    if not force:
        v1 = get_project_version("PRJ-METRO-01", 1)
        v2 = get_project_version("PRJ-METRO-01", 2)
        va = get_project_version("PRJ-ARTISAN-02", 1)
        if v1 and v2 and va:
            logger.info("Transcripts already bootstrapped in SQLite. Skipping reprocessing.")
            return

    transcripts_dir = Path(__file__).resolve().parent.parent / "transcripts"
    
    t1_path = transcripts_dir / "meeting_1_website_improvements.txt"
    t2_path = transcripts_dir / "meeting_2_ecommerce_checkout.txt"
    t3_path = transcripts_dir / "meeting_3_followup_website_revisions.txt"

    # Process Project 1 Version 1
    if t1_path.exists():
        t1_text = t1_path.read_text(encoding="utf-8")
        process_transcript(
            project_id="PRJ-METRO-01",
            title="Metro Medical Directory Enhancement",
            client_name="Dr. Marcus Vance (Metro Healthcare)",
            version_num=1,
            transcript_text=t1_text,
            timeline_weeks=8
        )
        # Approve Version 1 as official baseline
        approve_version("PRJ-METRO-01", 1, reviewer="Alex Mercer (Solutions Architect)")

    # Process Project 2 Version 1 (E-Commerce)
    if t2_path.exists():
        t2_text = t2_path.read_text(encoding="utf-8")
        process_transcript(
            project_id="PRJ-ARTISAN-02",
            title="Artisan Guild Direct Member Checkout",
            client_name="Rebecca Thorne (Artisan Guild)",
            version_num=1,
            transcript_text=t2_text,
            timeline_weeks=6
        )
        approve_version("PRJ-ARTISAN-02", 1, reviewer="Alex Mercer (Solutions Architect)")

    # Process Project 1 Version 2 (Follow-Up Revision)
    if t3_path.exists():
        t3_text = t3_path.read_text(encoding="utf-8")
        process_transcript(
            project_id="PRJ-METRO-01",
            title="Metro Medical Directory Enhancement",
            client_name="Dr. Marcus Vance (Metro Healthcare)",
            version_num=2,
            transcript_text=t3_text,
            timeline_weeks=5
        )
        # Generate diff report against approved V1 baseline
        compare_revision("PRJ-METRO-01", 2)

    logger.info("Bootstrap of 3 transcripts complete.")

def list_all_projects() -> List[Dict[str, Any]]:
    conn = get_meeting_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
