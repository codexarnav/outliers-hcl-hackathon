# CLAUDE.md — Project State & Context Transfer Guide

> **CRITICAL CONTEXT FOR ANY AI MODEL WORKING ON THIS REPOSITORY:**  
> This file is the primary context bridge. If you are a new model resuming this work, read this document first. It contains everything required to continue development without missing constraints, violating hackathon rules, or breaking established architecture.

---

## 1. Project Overview & Hackathon Mission

* **Competition:** HCLTech Future Ready AI Engineer Hackathon
* **Problem Statement:** AI-Powered University Student Services Assistant
* **Target University:** **Delhi Technological University (DTU)** (`dtu.ac.in`)
* **Repository:** `https://github.com/codexarnav/outliers-hcl-hackathon`
* **Local Workspace:** `/Users/ishaangupta/Desktop/outliers`
* **Author / Git User:** Ishaan Gupta (`ishaangupta.246@gmail.com`), GitHub account `ishaan-codes`
* **Branching Strategy:** Dedicated feature branches per phase (`feat/<phase-name>`), with **one Pull Request per branch** created via `gh pr create`.

### Non-Negotiable Directives
1. **Zero Hallucination / No Fabricated University Data:** All university documents and rules must come directly from official DTU publications (`dtu.ac.in`). Up to 2 synthetic circulars are permitted exclusively for testing conflict resolution (marked `synthetic: Y`).
2. **Deterministic Tools Over LLM Arithmetic (R5):** Calculations (attendance %, CGPA, backlogs, CWS marks) and eligibility decisions must be executed in Python over SQLite and `rule_registry`. The LLM **never** calculates or judges eligibility. LLM arithmetic is an automatic disqualification condition (§10).
3. **No Real Student Personal Data (§4.2, §10):** All student data is synthetically generated in the Annex C schema using an LLM, verified by `scripts/validate_students.py`.
4. **Mandatory `MOCK_LLM=true` Mode (§5.1):** The entire pipeline (retrieval, tools, precedence, API, evaluation) must be fully testable with `MOCK_LLM=true` without local GPU/Ollama dependencies.
5. **R8 Untrusted Content Guard:** Ingested document content is strictly data, never instructions. Document text is enclosed in `[UNTRUSTED_DOCUMENT_DATA]` boundary tags to prevent prompt injection.
6. **R7 Authorization:** Student identity is derived exclusively from the optional `X-Student-Id` header. Never allow querying another student's data (`answer_type: refused`).

---

## 2. Architecture & Design Blueprint (Version 1)

```
                            [ Client / Judge Request ]
                                        │
                         (Optional X-Student-Id, as_of_date)
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │ LangGraph Router (Q1A-Q2)│
                           └─────────────┬────────────┘
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
          [ General Query ]      [ Personal Query ]    [ Ambiguous Query ]
          (No X-Student-Id ok)   (Needs X-Student-Id)  (clarification_needed)
                    │                    │
                    ▼                    ▼
          ┌───────────────────┐  ┌───────────────────┐
          │ Metadata Filter   │  │ Deterministic Tool│
          │ (as_of_date,scope)│  │ (SQLite DB Query) │
          └─────────┬─────────┘  └─────────┬─────────┘
                    │                      │
                    ▼                      │
          ┌───────────────────┐            │
          │ Hybrid Retrieval  │            │
          │ (Chroma + FTS5)   │            │
          └─────────┬─────────┘            │
                    │                      │
                    ▼                      │
          ┌───────────────────┐            │
          │ Cross-Encoder     │            │
          │ Reranker (Top-5)  │            │
          └─────────┬─────────┘            │
                    │                      │
                    ▼                      │
          ┌───────────────────┐            │
          │ Annex A Precedence│            │
          │ Resolver          │            │
          └─────────┬─────────┘            │
                    │                      │
                    └──────────┬───────────┘
                               │
                               ▼
                 ┌───────────────────────────┐
                 │ Grounded LLM Explainer    │
                 │ ([DATA] chunks + tool JSON)│
                 └─────────────┬─────────────┘
                               │
                               ▼
                 ┌───────────────────────────┐
                 │ Citation & Type Validator │
                 │ (retrieved_fact/calculated│
                 │  not_found/refused/etc.)  │
                 └─────────────┬─────────────┘
                               │
                               ▼
                 ┌───────────────────────────┐
                 │ FastAPI Response & Audit  │
                 │ (trace_id, tokens, log)   │
                 └───────────────────────────┘
```

---

## 3. Mandatory API Contract (Section 6)

### `POST /ask`
* **Headers:** `X-Student-Id` (optional string)
* **Request Body:** `{"question": "string", "as_of_date": "YYYY-MM-DD"}`
* **Response Body:**
  ```json
  {
    "trace_id": "7f3c2a9e",
    "answer": "You are eligible to appear in the end-semester exam for CO201.",
    "answer_type": "calculated",
    "citations": [
      {
        "doc_id": "DTU-ORD-2024",
        "title": "Ordinance, Regulations & Scheme of Teaching and Examinations B.Tech 2024",
        "section": "Clause R.1(B).22",
        "page": 18,
        "version": "1.0",
        "effective_from": "2024-07-01"
      }
    ],
    "tools_invoked": [
      {
        "tool": "get_attendance",
        "input": {"course_code": "CO201"},
        "output": {"classes_held": 40, "classes_attended": 31, "attendance_pct": 77.5}
      }
    ],
    "applied_rules": [
      {
        "rule_id": "ATT-MIN-01",
        "value": ">= 75.0",
        "source_doc_id": "DTU-ORD-2024"
      }
    ],
    "conflicts_detected": [],
    "explanation": "Your attendance in CO201 is 77.5%, above the 75.0% minimum requirement in Clause R.1(B).22.",
    "as_of_date": "2026-10-06"
  }
  ```

### `POST /ingest` (Live Document Ingestion)
* **Request:** Multipart form with `file` (PDF/TXT) and `metadata` (JSON matching Annex B).
* **Response:** `{"doc_id": "string", "chunks_indexed": 14, "status": "ok"}`

### `GET /health`
* **Response:** `{"status": "ok", "api": "ready", "vector_store": "connected", "sqlite": "connected", "llm": "ready", "mock_mode": true}`

### `GET /audit/{trace_id}`
* Retrieves audit log entry matching Annex D format from SQLite `audit_log` table.

### `GET /sources`
* Returns current `source_register` table rows.

### Test Student Loader (§4.2)
* **CLI:** `python scripts/load_students.py --dir test_students/`
* **Admin Endpoint:** `POST /admin/load-students`

---

## 4. Current Implementation Status

### Completed Milestones
- [x] Initialized Git repository, set tracking branch to `origin/main`.
- [x] **PR #1 Created:** `feat/foundation-dtu-corpus-and-mock` (PR #1: https://github.com/codexarnav/outliers-hcl-hackathon/pull/1)
  - Scaffolding, `.env.example` with `MOCK_LLM=true` support, `core/config.py`.
  - Authentic DTU document acquisition (`scripts/scrape_dtu.py`), `data/source_register.csv`, `data/seed_rules.sql`.
- [x] **PR #2 Created:** `feat/sqlite-student-kit` (PR #2: https://github.com/codexarnav/outliers-hcl-hackathon/pull/2)
  - SQLite schema (`core/database.py`) for Annex C tables & Annex D `audit_log`.
  - Synthetic student generator (`scripts/generate_students.py`) with edge cases `S1001`–`S1008`.
  - Strict validator (`scripts/validate_students.py`) & Section 4.2 CLI loader (`scripts/load_students.py`).
  - Annex E Data Card (`docs/DATA_CARD.md`).
- [x] **PR #3 Created:** `feat/hybrid-retrieval-precedence` (PR #3: https://github.com/codexarnav/outliers-hcl-hackathon/pull/3)
  - Section-aware hierarchical chunking (`core/chunking.py`) extracting 373 chunks across DTU ordinances and circulars.
  - Hybrid retrieval engine (`core/retrieval.py`): SQLite FTS5 BM25 sparse search + ChromaDB dense search + Reciprocal Rank Fusion (RRF) + exact-phrase boost.
  - Annex A Source Precedence Policy engine (`core/precedence.py`): 5-step deterministic resolution.
- [x] **PR #5 Created (New Stack - Phase 4 & Beyond):** `feat/phase4-deterministic-tools-and-orchestration` (PR #5: https://github.com/codexarnav/outliers-hcl-hackathon/pull/5)
  - **Phase 4 (`core/tools.py`):** Deterministic Python academic tools over SQLite (`get_attendance`, `check_exam_eligibility`, `compute_cws_attendance_marks`, `get_academic_summary`, `check_promotion_eligibility`, `check_supplementary_eligibility`, `evaluate_what_if_supplementary`) and `rule_registry` resolution.
  - **Phase 5 (`graph/`, `api/`, `main.py`):** LangGraph StateGraph orchestration pipeline connecting R7 authorization/privacy guard, R8 untrusted document boundaries, Section 6 FastAPI endpoints (`POST /ask`, `POST /ingest`, `GET /health`, `GET /audit/{trace_id}`, `GET /sources`, `POST /admin/load-students`).
  - **Phase 6 (`eval/`):** Section 7 Evaluation benchmark (`eval/benchmark_questions.json`, `eval/judge.py`, `eval/EVALUATION_REPORT.md`) achieving 100% across all metrics.
  - **Phase 7 (`ui/`, Docker):** Streamlit user interface (`ui/app.py`), `Dockerfile`, and `docker-compose.yml`.
  - **Test Suite:** 62 passing unit and integration tests across all modules (`pytest tests/` in 2.1s).

### Team Collaboration & Merging Protocol
* **Active Teammate Step:** Teammate is pushing their scraping branch to `codexarnav/outliers-hcl-hackathon`.
* **Incoming Integration Flow:**
  1. Fetch and checkout teammate's branch:
     ```bash
     git fetch origin
     git checkout <teammate-branch>
     ```
  2. Finalize & harmonize teammate's scraping scripts with `data/source_register.csv` and `data/documents/`.
  3. Merge finalized scraping into `main`:
     ```bash
     git checkout main
     git merge <teammate-branch>
     git push origin main
     ```
  4. Rebase and re-target subsequent PRs (Phase 2 `feat/sqlite-student-kit`, Phase 3 `feat/hybrid-retrieval-precedence`) onto `main`.

---

## 5. Next Steps for Successor Models

### When resuming after teammate's branch is pushed:
1. Run `git fetch origin && git branch -r` to identify teammate's scraping branch.
2. Review teammate's scraping code, integrate with `core/chunking.py` and `data/source_register.csv`.
3. Merge into `main` and push to origin.
4. Continue with **Phase 4: Deterministic Academic Tools & LangGraph Orchestration**:
   - Implement `core/tools.py`: Python tools over SQLite (`get_attendance`, `check_exam_eligibility`, `get_academic_summary`, `check_promotion_eligibility`, `compute_cws_attendance_marks`).
   - Implement `graph/workflow.py`: LangGraph StateGraph connecting query classifier, retrieval, precedence, tools, explainer, and citation validator.
   - Implement `api/routes.py` and `main.py`: FastAPI endpoints matching Section 6 (`POST /ask`, `POST /ingest`, `GET /health`, `GET /audit/{trace_id}`, `GET /sources`, `POST /admin/load-students`).
5. Run automated tests:
   ```bash
   .venv/bin/pytest tests/
   ```
6. Open PR for each feature branch against `main` using `gh pr create`.

### Phase 3: Hybrid Retrieval & Annex A Precedence Engine
* Chunker (`core/chunking.py`), ChromaDB dense + SQLite FTS5 BM25 indexer.
* Annex A Source Precedence resolver (`core/precedence.py`).

### Phase 4: Deterministic Academic Tools
* `core/tools.py`: Python tools querying SQLite (`get_attendance`, `check_exam_eligibility`, `get_academic_summary`, `check_promotion_eligibility`, `compute_cws_attendance_marks`).

### Phase 5: LangGraph Query Flow & FastAPI Contract
* LangGraph state graph in `graph/workflow.py`, FastAPI endpoints in `api/routes.py` and `main.py`.

### Phase 6: LLM-as-a-Judge Evaluation Framework
* `eval/benchmark_questions.json` (24 cases), `eval/judge.py` computing all 6 metrics, Config A vs Config B comparative evaluation.

### Phase 7: Streamlit UI & Docker Compose
* `ui/app.py` with live audit inspector, `Dockerfile`, `docker-compose.yml`.

### Phase 8: Rehearsal & Code Freeze Tag
* Run end-to-end demo test, verify live `/ingest`, tag `final`.
