import pytest
from pathlib import Path
import shared
from meeting_app.main import (
    process_transcript, approve_version, compare_revision,
    bootstrap_transcripts, list_all_projects
)
from meeting_app.db import get_project_version, get_approved_baseline

def test_bootstrap_and_process_transcripts():
    bootstrap_transcripts()
    projects = list_all_projects()
    assert len(projects) >= 2
    proj_ids = {p["id"] for p in projects}
    assert "PRJ-METRO-01" in proj_ids
    assert "PRJ-ARTISAN-02" in proj_ids

def test_structured_requirements_and_traceability():
    v1 = get_project_version("PRJ-METRO-01", 1)
    assert v1 is not None
    reqs = v1["requirements"]
    assert len(reqs) >= 3

    # Check requirement attributes
    for r in reqs:
        assert r["req_id"].startswith("REQ-")
        assert len(r["quote"]) > 10, "Quote must preserve verbatim transcript passage"
        assert r["status"] in ["confirmed", "unclear", "disputed"]
        assert len(r["acceptance_criteria"]) > 0
        assert r["feasibility"] in ["existing_config", "existing_with_limitations", "custom_dev", "needs_clarification"]

def test_programmatic_estimates_summation():
    v1 = get_project_version("PRJ-METRO-01", 1)
    tasks = v1["tasks"]
    assert len(tasks) >= 3

    # Verify programmatic math
    calc_low = round(sum(t["low_hours"] for t in tasks), 1)
    calc_likely = round(sum(t["likely_hours"] for t in tasks), 1)
    calc_high = round(sum(t["high_hours"] for t in tasks), 1)

    assert v1["total_low"] == calc_low, f"Mismatch in low hours: {v1['total_low']} vs {calc_low}"
    assert v1["total_likely"] == calc_likely, f"Mismatch in likely hours: {v1['total_likely']} vs {calc_likely}"
    assert v1["total_high"] == calc_high, f"Mismatch in high hours: {v1['total_high']} vs {calc_high}"

def test_scope_change_detection_followup():
    diff_report = compare_revision("PRJ-METRO-01", 2)
    assert diff_report.project_id == "PRJ-METRO-01"
    assert diff_report.baseline_version == 1
    assert diff_report.new_version == 2

    # Check added requirement: Telehealth / Urgent care
    added_descs = [r.description.lower() for r in diff_report.added_requirements]
    assert any("telehealth" in d or "urgent" in d for d in added_descs), "Added telehealth requirement not detected"

    # Check removed requirement: Swipeable gesture cards
    removed_descs = [r["description"].lower() for r in diff_report.removed_requirements]
    assert any("swipeable" in d for d in removed_descs), "Removed swipeable feature not detected"

    # Check timeline change
    assert "compressed" in diff_report.timeline_changes.lower() or "5 weeks" in diff_report.timeline_changes.lower()

    # Check budget impact calculation
    assert "net_hours" in diff_report.budget_impact
    assert "cost_impact_usd" in diff_report.budget_impact

def test_baseline_approval_guardrail():
    # V1 was approved as baseline
    baseline = get_approved_baseline("PRJ-METRO-01")
    assert baseline is not None
    assert baseline["version_num"] == 1
    assert baseline["is_approved"] == 1

    # V2 is unapproved and must NOT have overwritten the baseline
    v2 = get_project_version("PRJ-METRO-01", 2)
    assert v2["is_approved"] == 0, "Unapproved revision V2 must not be auto-marked approved"
    
    # Baseline must STILL be V1
    current_baseline = get_approved_baseline("PRJ-METRO-01")
    assert current_baseline["version_num"] == 1
