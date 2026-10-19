# AI Tech Consultant — Integrated Capstone Platform

**Student / Engineer:** [gana37](https://github.com/gana37)  
**Project Repository:** [ai-tech-consultant](https://github.com/gana37/ai-tech-consultant)  
**Target Platform:** Brilliant Directories Solution Center Ecosystem  
**Evaluation Date:** October 16, 2026  

---

## 1. Executive Overview

The **AI Tech Consultant** is an end-to-end, multi-agent enterprise platform engineered for technical consultancy workflows on the Brilliant Directories architecture. It unites three production services connected through a central, shared HTTP API:

1. **Task 1 — Knowledge Brain:** Grounded RAG & Multimodal Knowledge Base ingesting live Brilliant Directories help-center documentation, parsing sitemaps, extracting UI screenshots, and indexing vector embeddings (FAISS) + BM25 keyword rankings. Features calibrated confidence scoring, prompt injection defense, and automated human escalation workflows with SQLite audit tracking.
2. **Task 2 — Inbox Agent:** Customer support triaging and draft generation engine processing inbound customer requests. Classifies intents, performs multi-factor risk assessment (financial, contractual, operational), queries Task 1 Knowledge Brain via HTTP for grounded resolutions, and enforces the **20-consecutive-unchanged-email-draft rule** with automatic safeguard counter resets on human edits.
3. **Task 3 — Meeting to Scope:** 5-stage consultative agent workflow (*Transcript Analyst → Product Feasibility via Task 1 HTTP API → Scope Agent → Programmatic Estimator → Proposal Agent*). Converts unstructured client discovery meetings into structured Statements of Work (SOW), locks baseline versions upon stakeholder approval, and features a **Scope Diff Engine** that computes scope delta between project revisions.
4. **Unified Streamlit Dashboard:** A unified executive interface (`frontend/app.py`) providing interactive Knowledge Brain query & escalation resolution, Customer Inbox review & feedback loops, and Scope generation & revision diff visualization.

---

## 2. Architecture & Service Topology

All three applications communicate through standard REST contracts. Task 2 and Task 3 consume Task 1 exclusively via HTTP:

```
                  +-------------------------------------------------------+
                  |               Streamlit Dashboard (UI)                |
                  |                   frontend/app.py                     |
                  +-------------------------------------------------------+
                           |                         |                 |
                           v                         v                 v
            +---------------------------+   +-------------------+  +-------------------+
            |  Task 1: Knowledge Brain  |<--| Task 2: Inbox Agt |  | Task 3: Scope Agt |
            |      FastAPI (Port 8000)  |<--| (HTTP Client)     |  | (HTTP Feasibility)|
            +---------------------------+   +-------------------+  +-------------------+
              |          |           |
              v          v           v
          FAISS/BM25   SQLite    Claude API
          (Embeddings) (Audit)   (Vision & RAG)
```

---

## 3. Prerequisites & Environment Setup

- **Python:** 3.10, 3.11, or 3.12+ (tested on Python 3.14 / 3.11 Windows).
- **Core Dependencies:** FastAPI, Uvicorn, Streamlit, FAISS-CPU, Sentence-Transformers, Rank-BM25, HTTPX, Pydantic v2, BeautifulSoup4.
- **Environment Variables:** Copy `.env.example` to `.env` (contains placeholders; all services run gracefully offline using local embeddings and extractive fallback):
  ```bash
  cp .env.example .env
  ```

### Installation
```bash
# Clone the repository
git clone https://github.com/gana37/ai-tech-consultant.git
cd AI-Tech-Consultant

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

---

## 4. Startup & Execution

### One-Command Startup
To start both the Knowledge Brain REST API (Port 8000) and the Unified Streamlit Dashboard (Port 8501) with a single command:
```bash
# Windows
run.bat

# Cross-Platform Python Launcher
python run.py
```

### Manual Service Startup
```bash
# Terminal 1: Knowledge Brain REST API
uvicorn kb_app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Unified Frontend Dashboard
streamlit run frontend/app.py
```
- **Knowledge Brain Swagger API Docs:** `http://localhost:8000/docs`
- **Streamlit Interactive UI:** `http://localhost:8501`

---

## 5. Verification & Evaluations

Run the automated test suite and Capstone Evaluation benchmark:
```bash
# Run all unit and integration tests (14 tests across Task 1, 2, 3)
pytest task1-knowledge-brain/ task2-inbox-agent/ task3-meeting-to-scope/ -v

# Run the 60-Case Capstone Evaluation Suite & Model Benchmark
python tests/eval_runner.py
```
Evaluation metrics and test case logs are saved to `data/eval_results.json`.

---

## 6. Project Datasets

- **Help Center Articles:** Real Brilliant Directories help center documentation ingested from `https://support.brilliantdirectories.com/support/sitemap.xml` with local seed fallback in `task1-knowledge-brain/data/seed_articles.json`.
- **Customer Emails (50 Synthetic Cases):** `task2-inbox-agent/data/customer_emails.json` spanning how-to queries, technical bugs, refund disputes, angry escalations, pricing inquiries, urgent outages, and spam.
- **Meeting Discovery Transcripts (3 Scenarios):** `task3-meeting-to-scope/transcripts/` featuring Discovery Meeting 1 (Metro Medical), Discovery Meeting 2 (Artisan Guild E-Commerce), and Follow-Up Revision Meeting 3 (Metro Medical Scope Creep).

---

## 7. Safety, Human Review & Safeguards

- **20-Draft Rule Safeguard:** The Inbox Agent requires manual human approval for all AI drafts. When 20 consecutive drafts are sent without human modification, an automated safeguard threshold triggers a review checklist warning and resets on any manual edit.
- **Financial & Scope Blockers:** Drafts addressing chargebacks, refunds, or contractual deadlines are hard-blocked from auto-sending and marked `needs_review=True` with high risk factor tags.
- **RAG Abstention & Human Escalation:** Queries with insufficient evidence (confidence < 0.35) or adversarial prompt injection automatically abstain, notify the user, and generate searchable human escalation records in SQLite.
