# AI Tech Consultant — Requirements Verification Checklist

This checklist tracks every core requirement from the official Business Labs / Anthropic Applied AI Dev/Engineer capstone assignment brief.

**Status Legend:**
- [x] **IMPLEMENTED & VERIFIED**
- [/] **PARTIALLY IMPLEMENTED / IN PROGRESS**
- [ ] **PENDING**

---

## 1. Environment & Architecture
- [x] Python 3.11/3.14 runtime verified with core dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `sentence-transformers`, `faiss-cpu`, `rank-bm25`, `streamlit`, `beautifulsoup4`, `pytest`).
- [x] Clean directory structure matching task separation (`task1-knowledge-brain`, `task2-inbox-agent`, `task3-meeting-to-scope`, `frontend`, `shared`, `data`, `docs`, `scripts`, `tests`).
- [x] Git initialized, `.gitignore` created (no secrets, no database files committed), `.env.example` created with placeholders.
- [x] GitHub remote configured (`gana37/ai-tech-consultant`).

## 2. Task 1: Knowledge Brain
- [x] **Sitemap Ingestion**: XML download, parsing, URL deduplication, configurable concurrency, polite pacing, exponential backoff retries.
- [x] **Manifest & Incremental Freshness**: Persistent manifest in SQLite (`knowledge_brain.db`), content hash tracking (SHA-256), change detection (new, changed, unchanged, removed).
- [x] **HTML & Article Extraction**: Clean title, content, headings, lists, tables, source URLs, content hash, filter out navigation/ads.
- [x] **Multimodal / Screenshot Context**: Associate images with parent article & surrounding text, Claude Vision API integration with safe fallback.
- [x] **Chunking & Indexing**: Semantic chunking with overlap (250 words, 50-word overlap), persistent FAISS vector index + BM25 keyword hybrid search with Reciprocal Rank Fusion.
- [x] **RAG & Citations**: Grounded answer generation via Claude, strict citation preservation, insufficient-evidence abstention on calibrated confidence (< 0.48).
- [x] **FastAPI Endpoints**: `GET /health`, `POST /query`, `POST /ingestion/run`, `GET /ingestion/status`, `POST /escalations`, `POST /escalations/{id}/resolve`.
- [x] **Human Escalation Workflow**: Unanswered questions saved with context, expert resolution, searchable incorporation, evaluation set addition.
- [x] **Security Guardrail**: Prompt injection detection blocking adversarial system prompt overrides.

## 3. Task 2: Inbox Agent
- [x] **Dataset**: 50 realistic, varied synthetic customer emails in `customer_emails.json` across 8 categories and 4 risk levels.
- [x] **Email Pipeline**: Intent classification, multi-factor risk assessment (financial, legal, security, commercial), Task 1 HTTP API client, grounded draft reply generation.
- [x] **Guardrails**: Strict schema validation, prevention of unauthorized refunds, binding pricing promises, or unvetted delivery deadlines.
- [x] **Human Review & Feedback**: Approve, reject, edit, escalate controls with persistent SQLite audit history in `inbox_agent.db`.
- [x] **20-Consecutive-Draft Rule**: Consecutive unchanged counter enforcement, automated reset to 0 on human edits/rejections, high-risk emails blocked from autonomous sending.
- [x] **Simulated Delivery**: Auditable simulated delivery workflow.

## 4. Task 3: Meeting to Scope of Work
- [x] **Transcripts**: 3 realistic multi-turn transcripts in `transcripts/` (1: Metro Medical Search/Filters, 2: Artisan Guild E-Commerce/Checkout, 3: Follow-up scope change adding Telehealth & removing CSV).
- [x] **Multi-Stage Agents**: Transcript Analyst, Product Feasibility Agent (calling Task 1 HTTP API), Scope Agent, Programmatic Estimation Agent, Proposal Agent.
- [x] **Structured Requirements**: Stable requirement IDs, transcript quotes, priority, feasibility categorization (`existing_config`, `custom_dev`, etc.), acceptance criteria.
- [x] **Estimates & Proposal**: Programmatic 3-point estimates (PERT math: Low, Likely, High), client-ready executive proposal with timeline and assumptions.
- [x] **Scope Change Detection**: Scope Diff Engine comparing follow-up transcript against approved baseline, identifying added/modified/removed requirements, timeline delta, and budget variance.
- [x] **Approval Lock**: Baselines locked by human approval (`is_approved=1`); unapproved drafts never overwrite approved baseline.

## 5. Shared Integration & User Interface
- [x] **HTTP Integration**: Task 2 and Task 3 call Task 1 exclusively via HTTP with timeouts, retries, request IDs, and typed Pydantic contracts.
- [x] **Unified Dashboard UI**: Streamlit interface (`frontend/app.py`) featuring 3 dedicated sections (Knowledge Chat & Escalations, Inbox Review & Feedback, Scope Builder & Diff Engine).

## 6. Evaluations & Model Comparison
- [x] **Task 1 Evals**: 20 test cases (supported, multi-article, screenshot-dependent, unsupported/abstention, malformed, prompt injection).
- [x] **Task 2 Evals**: 20 test cases (classification, grounded drafts, safety blocks, feedback recording, 20-counter logic).
- [x] **Task 3 Evals**: 20 test cases (requirement extraction, feasibility mapping, PERT estimate calculation, scope diff accuracy, baseline lock).
- [x] **Model Comparison**: Rigorous comparative benchmark of Claude 3.5 Sonnet vs. Claude 3.5 Haiku on Quality, Cost ($/1M tokens), Speed (latency), Reliability, and Safety.
- [x] **Automated Evaluation Runner**: `tests/eval_runner.py` producing verified reports in `data/eval_results.json`.

## 7. Submission Documentation & Video Script
- [x] `README.md` (1-page overview, architecture, setup, startup, testing, datasets, safety).
- [x] `DESIGN.md` (detailed architectural specification, system topology, sequence flows, persistence schemas, security, and trade-offs).
- [x] `EVALS.md` (comprehensive evaluation methodology, 60 test matrices, and Sonnet vs Haiku benchmark).
- [x] `AI_LOG.md` (5 real Antigravity prompts, 1 rejected AI work proposal with technical rationale, and engineering reflection).
- [x] `DEMO_VIDEO_SCRIPT.md` (10-minute timestamped script and 30-minute live review defense guide).
- [x] One-command startup scripts (`run.bat` for Windows and `run.py` for cross-platform).
