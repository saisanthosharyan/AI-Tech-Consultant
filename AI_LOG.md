# Antigravity AI Engineering Log

**Author:** [gana37](https://github.com/gana37)  
**Assistant:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Project:** AI Tech Consultant Capstone Platform  
**Date:** October 16, 2026  

---

## 1. Five Actual Prompts Used During Development

### Prompt 1: Project Scaffolding & Architecture Verification
> *"Act as a senior AI engineer and software architect. Build the complete, integrated AI Tech Consultant capstone project. Inspect the installed environment, create a modular project structure for Task 1 (Knowledge Brain), Task 2 (Inbox Agent), Task 3 (Meeting to Scope), shared schemas, and frontend. Ensure all three services communicate exclusively via HTTP REST endpoints."*
- **Outcome:** Generated directory topology, shared Pydantic schemas, isolated SQLite database contracts, and `.env.example` configuration without unnecessary dependencies.

### Prompt 2: Robust Ingestion & Hybrid RAG Engine
> *"Implement the Task 1 Knowledge Brain pipeline. Download and parse the Brilliant Directories XML sitemap, extract clean article DOM content and UI screenshot URLs, and compute SHA-256 hashes to support incremental crawling. Build a hybrid search index combining FAISS dense vector search and BM25Okapi lexical retrieval with Reciprocal Rank Fusion, plus an abstention safeguard for insufficient evidence."*
- **Outcome:** Created `sitemap_parser.py`, `html_extractor.py`, `crawler.py`, and `indexer.py` with calibrated confidence thresholds to prevent hallucinations.

### Prompt 3: Inbox Triaging & 20-Draft Rule Safeguards
> *"Build the Task 2 Inbox Agent with a dataset of 50 realistic customer emails spanning how-to questions, technical bugs, refund demands, and new project inquiries. Implement an email classification pipeline, multi-factor risk assessment, an HTTP client calling Task 1, and the mandatory 20-consecutive-unchanged-draft rule with automated safeguard counter resets on human edits."*
- **Outcome:** Created `customer_emails.json`, `pipeline.py`, `kb_client.py`, and `automation_tracker` database logic enforcing the 20-draft threshold.

### Prompt 4: 5-Stage Meeting-to-Scope & Scope Diff Engine
> *"Implement the Task 3 Meeting to Scope application with 3 realistic meeting transcripts (including a follow-up revision). Build a 5-stage agent pipeline: Transcript Analyst, Product Feasibility (calling Task 1 over HTTP), Scope Agent, Programmatic 3-point Estimator, and Proposal Agent. Lock approved baseline versions in SQLite and implement a Scope Change Diff Engine to detect added, removed, and modified requirements with timeline/budget delta."*
- **Outcome:** Delivered `agents.py`, `scope_diff.py`, `main.py`, and seeded 3 realistic multi-turn consultative dialogue transcripts.

### Prompt 5: Capstone Evaluation Runner & Comparative Model Benchmark
> *"Create a rigorous evaluation suite with at least 20 test cases per task (60 total) covering happy paths, edge cases, out-of-domain questions, and prompt injections. Implement a comparative model benchmark between Claude 3.5 Sonnet and Claude 3.5 Haiku comparing quality, cost, speed, reliability, and safety."*
- **Outcome:** Created `tests/eval_datasets.py` and `tests/eval_runner.py` producing verified benchmark reports in `data/eval_results.json`.

---

## 2. Concrete Example of Rejected AI Work & Engineering Rationale

### The Proposal
During the design of **Task 3: Meeting to Scope**, the AI suggested using a single, monolithic LLM prompt to simultaneously parse the meeting transcript, assess technical feasibility on Brilliant Directories, estimate engineering task hours, calculate project budgets, and generate the final Statement of Work (SOW) markdown text.

### The Rejection Rationale
1. **Mathematical Inconsistency:** Large language models frequently fail at basic arithmetic across long context windows. In preliminary testing of the monolithic prompt, the individual task hours (e.g. 16h + 24h + 12h) did not sum up to the reported milestone totals, and fee calculations showed inconsistent hourly multiples.
2. **Loss of Architectural Decoupling:** In a monolithic prompt, feasibility checks cannot query the live Task 1 Knowledge Brain API via real HTTP calls. The LLM simply hallucinates what it *assumes* Brilliant Directories can do, bypassing the shared Knowledge Brain requirement.
3. **Immutability & Diff Failure:** A single text block cannot be diffed programmatically against an approved baseline version without error-prone fuzzy text matching.

### The Superior Alternative Implemented
We rejected the monolithic approach and engineered a **staged 5-agent pipeline with deterministic programmatic math**:
- Stage 2 (`ProductFeasibilityAgent`) explicitly executes HTTP REST queries to `POST http://localhost:8000/query` against the live Knowledge Brain.
- Stage 4 (`EstimationAgent`) computes engineering hours using deterministic PERT 3-point estimation formulas ($E = \frac{O + 4M + P}{6}$) in pure Python, guaranteeing 100% mathematical integrity across low, likely, and high estimates.
- Structured requirement IDs enable the **Scope Change Diff Engine** to compute exact set deltas ($\Delta \text{Added}$, $\Delta \text{Removed}$, $\Delta \text{Hours}$, $\Delta \text{Cost}$) between revisions with mathematical precision.

---

## 3. Reflection on AI Pair-Programming

Utilizing Antigravity as an architectural co-pilot enabled rapid scaffolding of three production-grade microservices within a 24-hour deadline. The critical discipline was **active human verification**: refusing to accept unverified claims, enforcing hard test suites (`pytest`, `eval_runner`), and ensuring that AI components adhered strictly to decoupled HTTP network boundaries and deterministic business safeguards.
