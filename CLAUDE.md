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
- [x] **PR #1 Created & Updated:** `feat/foundation-dtu-corpus-and-mock` (PR #1: https://github.com/codexarnav/outliers-hcl-hackathon/pull/1)
  - Scaffolding, `.env.example` with `MOCK_LLM=true` support, `core/config.py`.
  - Authentic DTU document acquisition (`scripts/scrape_dtu.py`), `data/source_register.csv`, `data/seed_rules.sql`.
  - **Greptile Code Review Addressed:**
    - `pyproject.toml`: Added setuptools flat-layout discovery (`[tool.setuptools.packages.find]`) to prevent editable build crashes.
    - `pyproject.toml`: Added missing script dependencies (`reportlab`, `beautifulsoup4`, `pyyaml`).
    - `data/source_register.csv`: Retained DTU-ORD-2021 validity for 2021–2023 cohorts by clearing `effective_to`.
    - `data/source_register.csv`: Updated document provenance pointers to official canonical HTTPS links.
    - `scripts/scrape_dtu.py`: Pinned SHA-256 integrity verification (`e5ce24d...`) for `DTU-ORD-2021.pdf`.
    - `data/seed_rules.sql` & circulars: Replaced discrete intervals with continuous percentage slabs (`95.0,100.0`, etc.) to eliminate undefined fractional attendance gaps.
- [x] **PR #2 Created & Updated:** `feat/sqlite-student-kit` (PR #2: https://github.com/codexarnav/outliers-hcl-hackathon/pull/2)
  - SQLite schema (`core/database.py`) for Annex C tables & Annex D `audit_log`.
  - **Synthetic Dataset Upgraded to Full 60-Student Corpus:**
    - Integrated `synthetic_student_dataset_full` (60 students across B.Tech CSE & IT, batches 2023 & 2024, 12 courses, 180 attendance records, 181 results).
    - Added comprehensive `edge_case_manifest.json` indexing all boundary conditions (75.0% cut-off, detention, supplementary attempts, 39 marks failure, 7.00 CGPA boundaries).
    - Integrated `sql/derived_features.sql` with deterministic SQL views (`v_attendance_pct`, `v_attendance_status`, `v_marks_gap`, `v_student_overview`).
    - Validated by both `scripts/validate_students.py` and `scripts/validate_data.py` (0 errors, 0 warnings).
    - Annex E Data Card (`docs/DATA_CARD.md`) fully updated.
  - **Greptile Code Review on PR #2 Addressed (All 13 findings resolved):**
    - `scripts/load_students.py`: Replaced `INSERT OR REPLACE` with `ON CONFLICT DO UPDATE` based on primary keys to prevent `ON DELETE CASCADE` deleting dependent child records during single-table reloads.
    - `scripts/load_students.py`: Wrapped directory loads in a single atomic database transaction (`with conn:`) to prevent partial commits on failure.
    - `scripts/validate_students.py`: Added checks for all required columns per table, positive `max_marks`, non-negative score components, `exam_type` validity, and proportional pass mark checking `(total / max_marks) * 100 >= 40.0%`.
    - `sql/derived_features.sql`: Fixed `classes_short_by` formula in `v_attendance_status` to account for growing total classes held (`ceil((T*held - attended)/(1 - T))`).
    - `sql/derived_features.sql`: Added `COALESCE` fallbacks for `min_pass_total_pct` and `placement_min_cgpa` in `v_marks_gap` and `v_placement_eligible`.
    - `sql/derived_features.sql`: Updated `v_latest_attempt` to sort session attempts chronologically by session year/month before exam type.
    - `scripts/validate_data.py`: Added `"MAKEUP"` to `VALID_EXAM_TYPES`, resolved active rules per-student, and sorted attempts chronologically.
    - `data/test_students/results.csv` & `synthetic_student_dataset.json`: Preserved `S1003` regular internal marks at 13 in the supplementary attempt.
    - `scripts/generate_students.py`: Updated to export and synchronize the complete 60-student dataset and edge-case manifest.
- [x] **PR #3 Created & Updated:** `feat/hybrid-retrieval-precedence` (PR #3: https://github.com/codexarnav/outliers-hcl-hackathon/pull/3)
  - Section-aware hierarchical chunking (`core/chunking.py`) extracting chunks across DTU ordinances and circulars.
  - Hybrid retrieval engine (`core/retrieval.py`): SQLite FTS5 BM25 sparse search + ChromaDB dense search + Reciprocal Rank Fusion (RRF) + Cross-Encoder reranker.
  - Annex A Source Precedence Policy engine (`core/precedence.py`): 5-step deterministic resolution, handling applicability, supersession, authority levels (1-5), recency, and cohort ordinance preservation.
  - **Greptile Code Review on PR #3 Addressed (All 10 findings resolved):**
    - `core/precedence.py`: Normalized section references (`normalize_section_ref`) so `DTU-ORD-2024#Clause R.1(B).22` supersedes chunk section `R.1(B).22`.
    - `core/precedence.py`: Enforced Level 5 informational restriction (`answer_type: informational_only`, `winning_chunk: None`) to prevent unofficial sources from becoming authoritative winners.
    - `core/precedence.py`: Refined conflict detection to require genuine contradictory claims rather than flagging equal-level agreeing circulars.
    - `core/precedence.py`: Fixed general queries (`batch_year="ALL"`) to retain university ordinances instead of dropping scoped rules.
    - `core/chunking.py`: Captured page text preceding first heading as clause continuation instead of dropping it.
    - `core/chunking.py`: Preserved page numbers from explicit text page markers instead of naive clause-index counting.
    - `core/retrieval.py`: Deleted obsolete chunk IDs for updated documents in both SQLite FTS5 and ChromaDB.
    - `core/retrieval.py`: Initialized ChromaDB collection with `settings.EMBEDDING_MODEL` embedding function.
    - `core/retrieval.py`: Implemented Cross-Encoder reranking using `settings.CROSS_ENCODER_MODEL` with heuristic fallback.
    - `tests/test_retrieval.py`: Added autouse fixture indexing test chunks to ensure isolated passes on clean checkouts.
  - Merged PR #2 and PR #1 updates into PR #3; all 36 unit tests passing cleanly!

### Team Collaboration & Merging Status
* **Teammate Scraper Merged:** Teammate branch `features/scrapper` was reviewed, enhanced to support Annex B schema and Annex A authority levels (1–5), merged into `main`, and pushed to `origin/main`.
* **Current PR Stack:**
  - PR #1: `feat/foundation-dtu-corpus-and-mock` -> `main`
  - PR #2: `feat/sqlite-student-kit` -> `feat/foundation-dtu-corpus-and-mock`
  - PR #3: `feat/hybrid-retrieval-precedence` -> `feat/sqlite-student-kit`
* **Test Suite:** 32 unit tests passing cleanly (`uv run pytest tests/`). Student validation suites passing cleanly (`validate_students.py`, `validate_data.py`).

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
