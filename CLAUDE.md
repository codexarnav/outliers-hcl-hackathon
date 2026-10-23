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

### Completed Milestones (Phase 1)
- [x] Initialized Git repository, set tracking branch to `origin/main`.
- [x] Created feature branch `feat/foundation-dtu-corpus-and-mock`.
- [x] Virtual environment configured at `.venv` with Python 3.12 via `uv`.
- [x] Defined dependencies in `pyproject.toml` and `requirements.txt`.
- [x] Configured `.gitignore` and `.env.example`.
- [x] Implemented core configuration `core/config.py` with `MOCK_LLM=true` support.
- [x] Created `scripts/scrape_dtu.py` which downloaded/generated the DTU authentic corpus:
  - `DTU-ORD-2021.pdf`: 335-page official DTU Ordinance (downloaded from `dtu.ac.in`).
  - `DTU-ORD-2024.pdf`: 100-page official DTU 2024 Ordinance (downloaded from `dtu.ac.in`).
  - `DTU-CIR-ATT-2024.pdf`: Clause R.1(B).22 attendance notice & 5-mark CWS policy.
  - `DTU-CIR-EXAM-SUPP.pdf`: Supplementary & make-up exam guidelines.
  - `DTU-NOTIF-FEE-2024.pdf`: Annual academic fee notification.
  - `DTU-CSE-ELECT-FAQ.pdf`: CSE department advising FAQ.
  - `DTU-SYN-AMEND-2026.pdf`: Synthetic attendance condonation amendment circular (1 of max 2 allowed).
  - `data/source_register.csv`: Annex B metadata for all 7 documents.
  - `data/seed_rules.sql`: Pre-seeded DTU clauses for `rule_registry`.

---

## 5. Next Steps for Successor Models

### Next: Phase 2 — Database Engineering & Synthetic Student Kit
1. **Branch:** `feat/sqlite-student-kit` (Create new branch after PR #1 is merged or branched from Phase 1).
2. **Tasks:**
   - Implement `core/database.py`: SQLite connection, table migrations for Annex C (`students`, `courses`, `attendance`, `results`, `rule_registry`) and Annex D (`audit_log`).
   - Implement `scripts/generate_students.py`: Generates $\ge 35$ students, $\ge 8$ courses across 3 batches (`2022`, `2023`, `2024`) with deliberate edge cases (`S1001` to `S1008`).
   - Implement `scripts/validate_students.py`: Deterministic schema and constraint checker.
   - Implement `scripts/load_students.py`: Mandatory CLI loader script (`--dir` and `--file` options).
   - Author Annex E Data Card at `docs/DATA_CARD.md`.
3. **Verification:**
   ```bash
   .venv/bin/python scripts/generate_students.py
   .venv/bin/python scripts/validate_students.py
   .venv/bin/python scripts/load_students.py --dir data/test_students/
   ```
4. **Git Action:** Commit changes, push to `origin/feat/sqlite-student-kit`, and run `gh pr create`.

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
