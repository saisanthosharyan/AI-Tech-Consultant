import streamlit as st
import httpx
import json
from pathlib import Path
from datetime import datetime, timezone

import shared
from shared.config import settings

# Page configuration
st.set_page_config(
    page_title="AI Tech Consultant — Knowledge Brain & Client Workflows",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #64748B; margin-bottom: 1.5rem; }
    .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 600; margin-right: 0.4rem; }
    .badge-low { background-color: #DEF7EC; color: #03543F; }
    .badge-med { background-color: #FEF08A; color: #713F12; }
    .badge-high { background-color: #FEE2E2; color: #991B1B; }
    .badge-crit { background-color: #7F1D1D; color: #FEF2F2; }
    .card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# Helper: check Knowledge Brain API health
@st.cache_data(ttl=5)
def check_kb_health():
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.knowledge_brain_base_url}/health")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}
    return {"status": "unreachable"}

# Sidebar Navigation & System Status
st.sidebar.markdown("## 🧠 AI Tech Consultant")
st.sidebar.caption("Business Labs Capstone System")

kb_health = check_kb_health()
if kb_health.get("status") == "healthy":
    st.sidebar.success(f"● Knowledge Brain Online ({kb_health.get('articles_indexed', 0)} articles, {kb_health.get('chunks_indexed', 0)} chunks)")
else:
    st.sidebar.error("● Knowledge Brain Offline (Run API on :8000)")

app_section = st.sidebar.radio(
    "Select Application Module:",
    ["1. 🧠 Knowledge Chat & Escalations", "2. 📬 Inbox Agent Review", "3. 📋 Scope Builder & Diff Engine"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ System Settings")
st.sidebar.info(f"**Autonomous Threshold:** {settings.consecutive_unchanged_threshold} unchanged drafts")
autonomy_toggle = st.sidebar.checkbox("Enable Autonomy Trial Mode", value=settings.autonomy_trial_enabled)
if autonomy_toggle != settings.autonomy_trial_enabled:
    settings.autonomy_trial_enabled = autonomy_toggle

# ==============================================================================
# SECTION 1: KNOWLEDGE CHAT & HUMAN ESCALATIONS
# ==============================================================================
if app_section == "1. 🧠 Knowledge Chat & Escalations":
    st.markdown('<div class="main-header">🧠 Knowledge Brain Chat & Escalation Desk</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Query the grounded Brilliant Directories knowledge base, inspect source evidence & citations, and review escalated inquiries.</div>', unsafe_allow_html=True)

    chat_tab, esc_tab, crawl_tab = st.tabs(["💬 Ask Knowledge Brain", "⚠️ Human Escalation Desk", "🔄 Ingestion & Freshness"])

    with chat_tab:
        col_q, col_opt = st.columns([3, 1])
        with col_opt:
            st.markdown("##### Sample Queries")
            if st.button("CSV Category Import"):
                st.session_state["kb_query"] = "How do I import categories via CSV in Brilliant Directories?"
            if st.button("Stripe Gateway Setup"):
                st.session_state["kb_query"] = "How to connect Stripe payment gateway?"
            if st.button("Mass Email Limits"):
                st.session_state["kb_query"] = "What are the server limits for mass email newsletters?"
            if st.button("Test Unsupported (Abstain)"):
                st.session_state["kb_query"] = "How do I configure quantum teleportation engines?"

        with col_q:
            query_text = st.text_input("Enter question about Brilliant Directories:", value=st.session_state.get("kb_query", ""), placeholder="e.g. How do I configure location radius search?")
            top_k = st.slider("Max evidence chunks (top_k)", 1, 6, 3)
            min_conf = st.slider("Confidence Abstention Threshold", 0.0, 1.0, 0.35, 0.05)

            if st.button("Submit Query", type="primary"):
                if not query_text.strip():
                    st.warning("Please enter a question.")
                else:
                    with st.spinner("Retrieving evidence and synthesizing grounded response..."):
                        try:
                            with httpx.Client(timeout=12.0) as client:
                                resp = client.post(
                                    f"{settings.knowledge_brain_base_url}/query",
                                    json={"question": query_text, "top_k": top_k, "min_confidence": min_conf}
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    st.session_state["last_kb_resp"] = data
                                else:
                                    st.error(f"API Error {resp.status_code}: {resp.text}")
                        except Exception as e:
                            st.error(f"Failed to communicate with Knowledge Brain API: {e}")

        # Render Query Response
        if "last_kb_resp" in st.session_state:
            res = st.session_state["last_kb_resp"]
            st.markdown("---")
            col_ans, col_meta = st.columns([2.5, 1])

            with col_ans:
                st.markdown("### Answer")
                if res["status"] == "insufficient_evidence":
                    st.warning(f"⚠️ **Insufficient Evidence Alert**\n\n{res['answer']}")
                    st.caption(f"Reason: {res.get('reason')}")
                else:
                    st.success(res["answer"])

                if res.get("sources"):
                    st.markdown("#### 📚 Verified Source Citations")
                    for i, src in enumerate(res["sources"], 1):
                        with st.expander(f"Source {i}: {src['title']} ({src.get('section', 'Overview')})"):
                            st.markdown(f"**URL:** [{src['url']}]({src['url']})")
                            st.markdown(f"**Evidence Snippet:**\n> {src.get('snippet', '')}")
                            if src.get("images"):
                                st.markdown("**UI Screenshots / References:**")
                                for img in src["images"]:
                                    st.caption(f"🖼️ Reference Image: `{img}`")

            with col_meta:
                st.markdown("### Response Metadata")
                st.metric("Calibrated Confidence", f"{res['confidence']*100:.1f}%")
                st.metric("Latency", f"{res.get('latency_ms', 0):.0f} ms")
                st.text(f"Request ID: {res['request_id']}")
                st.text(f"Model: {res.get('model')}")
                if res["needs_human"]:
                    st.error("🚨 Escalated to Human Expert")
                else:
                    st.success("✅ Grounded & Confirmed")

    with esc_tab:
        st.markdown("### Human Escalation Resolution Desk")
        st.caption("When evidence is insufficient, questions are logged here for expert review. Approved answers are versioned and indexed.")

        try:
            with httpx.Client(timeout=4.0) as client:
                esc_resp = client.get(f"{settings.knowledge_brain_base_url}/escalations")
                escalations = esc_resp.json() if esc_resp.status_code == 200 else []
        except Exception:
            escalations = []

        if not escalations:
            st.info("No open escalation tickets currently recorded.")
        else:
            for esc in escalations:
                status_icon = "✅ Resolved" if esc.get("expert_answer") else "⚠️ Pending Review"
                with st.expander(f"Ticket #{esc['id']}: {esc['question']} [{status_icon}]"):
                    st.markdown(f"**Trigger Reason:** {esc['reason']}")
                    st.markdown(f"**Logged At:** {esc['created_at']}")
                    if esc.get("expert_answer"):
                        st.success(f"**Verified Answer by {esc.get('resolved_by')}:**\n\n{esc['expert_answer']}")
                        st.caption(f"Indexed as Knowledge: {esc.get('is_indexed')}")
                    else:
                        st.markdown("#### Enter Expert Resolution")
                        ans_input = st.text_area("Expert Verified Answer:", key=f"esc_ans_{esc['id']}")
                        reviewer_name = st.text_input("Reviewer Name:", value="Senior Technical Consultant", key=f"rev_{esc['id']}")
                        index_kb = st.checkbox("Index answer as searchable knowledge in Knowledge Brain", value=True, key=f"idx_{esc['id']}")
                        if st.button("Submit Resolution & Index", key=f"btn_res_{esc['id']}"):
                            if len(ans_input.strip()) < 5:
                                st.warning("Please provide a substantive answer.")
                            else:
                                with httpx.Client(timeout=10.0) as client:
                                    r = client.post(
                                        f"{settings.knowledge_brain_base_url}/escalations/{esc['id']}/resolve",
                                        json={"expert_answer": ans_input, "resolved_by": reviewer_name, "index_as_knowledge": index_kb}
                                    )
                                    if r.status_code == 200:
                                        st.success("Escalation resolved and successfully indexed into Knowledge Brain!")
                                        st.rerun()

    with crawl_tab:
        st.markdown("### Sitemap Ingestion & Incremental Freshness")
        try:
            with httpx.Client(timeout=4.0) as client:
                stat_resp = client.get(f"{settings.knowledge_brain_base_url}/ingestion/status")
                crawl_stats = stat_resp.json() if stat_resp.status_code == 200 else {}
        except Exception:
            crawl_stats = {}

        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.metric("Total Discovered", crawl_stats.get("total_discovered", 0))
        col_c2.metric("Processed", crawl_stats.get("processed", 0))
        col_c3.metric("Unchanged", crawl_stats.get("unchanged", 0))
        col_c4.metric("Pending", crawl_stats.get("pending", 0))

        st.markdown("---")
        st.markdown("#### Trigger Ingestion Run")
        max_batch = st.number_input("Max Articles in Batch:", min_value=1, max_value=100, value=15)
        force_ref = st.checkbox("Force re-process unchanged articles")
        if st.button("Run Polite Ingestion Batch", type="secondary"):
            with st.spinner("Connecting to Brilliant Directories sitemap and running ingestion..."):
                try:
                    with httpx.Client(timeout=30.0) as client:
                        r = client.post(
                            f"{settings.knowledge_brain_base_url}/ingestion/run",
                            json={"max_articles": max_batch, "force_refresh": force_ref, "sample_only": False}
                        )
                        st.success(f"Ingestion batch launched: {r.json()}")
                        st.rerun()
                except Exception as e:
                    st.error(f"Ingestion trigger failed: {e}")

# ==============================================================================
# SECTION 2: INBOX AGENT REVIEW
# ==============================================================================
elif app_section == "2. 📬 Inbox Agent Review":
    st.markdown('<div class="main-header">📬 Inbox Agent & 20-Draft Rule Reviewer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AI-assisted customer email triaging, grounded draft generation, safety guardrails, and human review loop.</div>', unsafe_allow_html=True)

    from inbox_app.main import (
        initialize_inbox, get_all_emails, get_email_details, process_single_email,
        submit_review, get_tracker_stats, get_sent_emails
    )

    # Ensure dataset is loaded
    initialize_inbox()
    emails = get_all_emails()

    tab_inbox, tab_tracker, tab_sent = st.tabs(["📥 Customer Email Review", "📈 20-Draft Autonomy Tracker", "📤 Sent Log (Simulated)"])

    with tab_inbox:
        # Category Filter
        categories = ["All"] + sorted(list({e["category"] for e in emails if e["category"]}))
        selected_cat = st.selectbox("Filter by Category:", categories)

        filtered_emails = emails if selected_cat == "All" else [e for e in emails if e["category"] == selected_cat]

        email_options = {f"{e['id']} — {e['sender_name']}: {e['subject'][:45]}...": e['id'] for e in filtered_emails}
        selected_label = st.selectbox("Select Customer Email to Review:", list(email_options.keys()))
        selected_email_id = email_options[selected_label]

        details = get_email_details(selected_email_id)
        em = details["email"]

        st.markdown("---")
        col_e1, col_e2 = st.columns([1.5, 2.5])

        with col_e1:
            st.markdown("### ✉️ Customer Message")
            st.markdown(f"**From:** {em['sender_name']} `<{em['sender_email']}>`")
            st.markdown(f"**Subject:** {em['subject']}")
            st.markdown(f"**Timestamp:** {em['timestamp']}")
            
            # Badges
            risk_class = f"badge-{em['risk_level'][:4]}"
            st.markdown(
                f'<span class="badge badge-med">Category: {em["category"]}</span>'
                f'<span class="badge {risk_class}">Risk: {em["risk_level"].upper()}</span>'
                f'<span class="badge badge-low">Urgency: {em["urgency"].upper()}</span>',
                unsafe_allow_html=True
            )
            
            st.markdown("#### Message Body")
            st.info(em["body"])

            if em.get("expected_behavior"):
                st.caption(f"🎯 Expected Behavior: {em['expected_behavior']}")

        with col_e2:
            st.markdown("### 🤖 Grounded Draft & Human Action")
            
            # Check if draft already generated
            draft = details["draft"]
            if not draft or st.button("Generate / Regenerate Draft"):
                with st.spinner("Calling Knowledge Brain API and generating draft..."):
                    draft_obj = process_single_email(selected_email_id)
                    details = get_email_details(selected_email_id)
                    draft = details["draft"]

            if draft:
                if draft["guardrails_passed"]:
                    st.success("🛡️ Safety Guardrails: PASSED (No unauthorized pricing, refund, or delivery promises)")
                else:
                    st.error("🚨 Safety Guardrail Alert: Blocked unauthorized commitment")
                    warnings = json.loads(draft.get("warnings_json", "[]"))
                    for w in warnings:
                        st.caption(f"- {w}")

                # Draft Editor
                st.markdown("#### Editable Draft Reply")
                edited_reply = st.text_area("Review and modify if needed before sending:", value=draft["draft_reply"], height=260, key=f"draft_{draft['id']}")

                # Action Controls
                st.markdown("#### Human Review Decision")
                rev_col1, rev_col2, rev_col3, rev_col4 = st.columns(4)

                with rev_col1:
                    if st.button("✅ Approve & Send", type="primary"):
                        res = submit_review(
                            email_id=em["id"],
                            draft_id=draft["id"],
                            action="approve",
                            original_draft=draft["draft_reply"],
                            final_reply=edited_reply,
                            category=em["category"],
                            risk_level=em["risk_level"],
                            reviewer="Consultant Lead"
                        )
                        st.success(f"Approved! Consecutive unchanged drafts for '{em['category']}': {res['consecutive_unchanged_count']}")
                        st.rerun()

                with rev_col2:
                    if st.button("✏️ Submit Edit & Send"):
                        res = submit_review(
                            email_id=em["id"],
                            draft_id=draft["id"],
                            action="edit",
                            original_draft=draft["draft_reply"],
                            final_reply=edited_reply,
                            category=em["category"],
                            risk_level=em["risk_level"],
                            reviewer="Consultant Lead",
                            notes="Custom modifications submitted."
                        )
                        st.warning(f"Sent with edits. Consecutive counter RESET to 0 for '{em['category']}'.")
                        st.rerun()

                with rev_col3:
                    if st.button("❌ Reject Draft"):
                        res = submit_review(
                            email_id=em["id"],
                            draft_id=draft["id"],
                            action="reject",
                            original_draft=draft["draft_reply"],
                            final_reply=edited_reply,
                            category=em["category"],
                            risk_level=em["risk_level"],
                            reviewer="Consultant Lead"
                        )
                        st.error(f"Draft rejected. Counter RESET to 0 for '{em['category']}'.")
                        st.rerun()

                with rev_col4:
                    if st.button("⚠️ Escalate"):
                        res = submit_review(
                            email_id=em["id"],
                            draft_id=draft["id"],
                            action="escalate",
                            original_draft=draft["draft_reply"],
                            final_reply=edited_reply,
                            category=em["category"],
                            risk_level=em["risk_level"],
                            reviewer="Consultant Lead"
                        )
                        st.info("Escalated for senior review.")
                        st.rerun()

    with tab_tracker:
        st.markdown("### 20-Consecutive-Draft Rule Scorecard")
        st.caption("A category qualifies for autonomous sending trial ONLY after 20 consecutive qualifying, unchanged drafts. Any human edit or rejection immediately resets the counter to 0.")

        tracker_rows = get_tracker_stats()
        if not tracker_rows:
            st.info("No reviews recorded yet. Approve drafts in the review tab to see live counter tracking.")
        else:
            for tr in tracker_rows:
                pct = min(tr["consecutive_unchanged_count"] / 20.0, 1.0)
                st.markdown(f"#### Category: `{tr['category']}`")
                st.progress(pct)
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                col_t1.metric("Consecutive Unchanged", f"{tr['consecutive_unchanged_count']} / 20")
                col_t2.metric("Total Approved", tr["total_approved"])
                col_t3.metric("Total Edited", tr["total_edited"])
                col_t4.metric("Total Rejected", tr["total_rejected"])
                
                if tr["autonomy_eligible"]:
                    st.success("🎉 AUTONOMY ELIGIBLE: 20 consecutive unchanged drafts achieved!")
                else:
                    st.caption(f"Status: Under Human Review. Last reset reason: {tr.get('last_reset_reason') or 'None'}")
                st.markdown("---")

    with tab_sent:
        st.markdown("### Simulated Email Dispatch Log")
        st.caption("Approved customer email replies are recorded here with timestamp and dispatch mode.")
        sent_emails = get_sent_emails()
        if not sent_emails:
            st.info("No emails sent yet.")
        else:
            for s in sent_emails:
                with st.expander(f"Sent to {s['recipient']}: {s['subject']} [{s['sent_at']}]"):
                    st.markdown(f"**Dispatch Mode:** `{s['sent_mode']}`")
                    st.markdown("**Sent Content:**")
                    st.text(s["body"])

# ==============================================================================
# SECTION 3: SCOPE BUILDER & DIFF ENGINE
# ==============================================================================
elif app_section == "3. 📋 Scope Builder & Diff Engine":
    st.markdown('<div class="main-header">📋 Meeting to Scope of Work & Diff Engine</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Convert meeting transcripts into structured requirements, verify feasibility via Knowledge Brain, generate programmatic estimates, and detect follow-up scope changes.</div>', unsafe_allow_html=True)

    from meeting_app.main import (
        process_transcript, approve_version, compare_revision,
        bootstrap_transcripts, list_all_projects
    )
    from meeting_app.db import get_project_version, get_approved_baseline

    # Ensure transcripts are bootstrapped
    bootstrap_transcripts()
    projects = list_all_projects()

    proj_map = {f"{p['id']}: {p['title']} ({p['client_name']})": p['id'] for p in projects}
    selected_p_label = st.selectbox("Select Project:", list(proj_map.keys()))
    selected_proj_id = proj_map[selected_p_label]

    tab_v1, tab_v2_diff, tab_new = st.tabs(["📜 Approved Baseline Scope", "🔄 Scope Revision Diff (Follow-Up)", "➕ Process New Transcript"])

    with tab_v1:
        v1 = get_project_version(selected_proj_id, 1)
        if v1:
            st.markdown(f"### Project Scope: {v1['scope_doc'].get('project_title', selected_proj_id)} (Version 1)")
            
            # Baseline status
            if v1["is_approved"]:
                st.success(f"🔒 **APPROVED BASELINE** — Approved by: {v1.get('approved_by')} on {v1.get('approved_at')}")
            else:
                st.warning("⚠️ Unapproved Draft")

            sub_t1, sub_t2, sub_t3 = st.tabs(["Requirements & Feasibility", "Task Hour Estimates", "Proposal Preview"])

            with sub_t1:
                st.markdown("#### Structured Technical Requirements")
                for req in v1["requirements"]:
                    with st.expander(f"{req['req_id']}: {req['description']} [{req['priority'].upper()}]"):
                        st.markdown(f"**Verbatim Quote:**\n> \"{req['quote']}\"")
                        st.markdown(f"**Feasibility:** `{req['feasibility']}` — {req.get('feasibility_notes', '')}")
                        st.markdown("**Acceptance Criteria:**")
                        for ac in req.get("acceptance_criteria", []):
                            st.markdown(f"- {ac}")

            with sub_t2:
                st.markdown("#### Engineering Work Breakdown")
                st.dataframe([
                    {
                        "Task ID": t["task_id"],
                        "Req ID": t["req_id"],
                        "Description": t["description"],
                        "Low (hrs)": t["low_hours"],
                        "Likely (hrs)": t["likely_hours"],
                        "High (hrs)": t["high_hours"],
                        "Key Assumptions": t["assumptions"]
                    } for t in v1["tasks"]
                ], use_container_width=True)

                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("Low Estimate", f"{v1['total_low']} hrs")
                col_m2.metric("Likely Estimate", f"{v1['total_likely']} hrs")
                col_m3.metric("High Estimate", f"{v1['total_high']} hrs")
                col_m4.metric("Est. Budget (@ $120/hr)", f"${v1['total_likely']*120:,.2f}")

            with sub_t3:
                st.markdown("#### Executive Proposal")
                st.markdown(v1["proposal_text"])

    with tab_v2_diff:
        st.markdown("### Scope Change Diff Report (Follow-Up Meeting vs Approved Baseline)")
        st.caption("Compares Meeting 3 follow-up revisions against the locked Version 1 baseline.")

        try:
            diff = compare_revision("PRJ-METRO-01", 2)
            st.markdown(diff.summary_report)

            col_b1, col_b2, col_b3 = st.columns(3)
            col_b1.metric("Baseline Effort (V1)", f"{diff.budget_impact.get('base_hours')} hrs")
            col_b2.metric("Revised Effort (V2)", f"{diff.budget_impact.get('new_hours')} hrs")
            col_b3.metric("Net Variance", f"{diff.budget_impact.get('net_hours'):+0.1f} hrs", delta=f"${diff.budget_impact.get('cost_impact_usd'):+,.2f}")

            st.markdown("---")
            st.markdown("#### Baseline Approval Governance")
            st.info("The Version 1 baseline remains locked. Approving Version 2 will promote it to the new active baseline.")
            if st.button("Approve Version 2 as New Baseline", type="primary"):
                approve_version("PRJ-METRO-01", 2, reviewer="Dr. Marcus Vance & Lead Consultant")
                st.success("Version 2 promoted to Official Approved Baseline!")
                st.rerun()

        except Exception as e:
            st.info(f"Diff report available for PRJ-METRO-01. Notice: {e}")

    with tab_new:
        st.markdown("### Process Custom Meeting Transcript")
        new_proj_id = st.text_input("Project ID:", value="PRJ-CUSTOM-01")
        new_proj_title = st.text_input("Project Title:", value="Custom Healthcare & Directory Scoping")
        new_client = st.text_input("Client Name:", value="Innovate Health Group")
        new_timeline = st.slider("Target Timeline (weeks):", 2, 16, 6)
        new_transcript = st.text_area("Paste Meeting Transcript:", height=200, placeholder="Paste dialogue here...")

        if st.button("Analyze & Generate Scope SOW", type="primary"):
            if len(new_transcript.strip()) < 50:
                st.warning("Please provide a substantive meeting transcript.")
            else:
                with st.spinner("Executing 5-stage agent pipeline..."):
                    doc = process_transcript(
                        project_id=new_proj_id,
                        title=new_proj_title,
                        client_name=new_client,
                        version_num=1,
                        transcript_text=new_transcript,
                        timeline_weeks=new_timeline
                    )
                    st.success(f"Scope of Work generated for {new_proj_id}! Total likely effort: {doc.total_likely_hours} hrs.")
                    st.rerun()
