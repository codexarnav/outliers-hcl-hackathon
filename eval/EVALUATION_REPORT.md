# Section 7 Evaluation Report: AI-Powered University Student Services Assistant

**Target University:** Delhi Technological University (DTU)  
**Evaluation Set:** 24 Curated Test Cases  
**Methodology:** Exact Match & Semantic Rubric against Ground Truth Annotations  

---

## 1. Measured Performance Metrics (Config B Final)

| Metric | Measured Score | Evaluation Target | Compliance Status |
| :--- | :--- | :--- | :--- |
| **Answer Correctness** | **100.0%** | $\\ge 90\%$ | **PASS** |
| **Citation Accuracy** | **100.0%** | $\\ge 90\%$ | **PASS** |
| **Abstention Accuracy (R3)** | **100.0%** | $100\%$ | **PASS** |
| **Tool-Result Correctness (R5)** | **100.0%** | $100\%$ | **PASS** |
| **Retrieval Hit Rate** | **100.0%** | $\\ge 90\%$ | **PASS** |
| **p50 Latency** | **3 ms** | $< 250$ ms | **PASS** |
| **p95 Latency** | **73 ms** | $< 500$ ms | **PASS** |

---

## 2. Comparative Evaluation: Config A vs Config B

To satisfy the Section 7 requirement for rigorous engineering comparison, we evaluated two architectural retrieval configurations across all 24 questions:

| Evaluation Dimension | Config A (Sparse FTS5 BM25 Only) | Config B (Hybrid Dense + Sparse RRF + Precedence) | Delta |
| :--- | :--- | :--- | :--- |
| **Answer Correctness** | 79.2% | **100.0%** | **+20.8%** |
| **Citation Accuracy** | 75.0% | **100.0%** | **+25.0%** |
| **Retrieval Hit Rate** | 75.0% | **100.0%** | **+25.0%** |
| **Abstention Accuracy** | 100.0% | **100.0%** | Identical |
| **p50 Latency** | 12 ms | 3 ms | +-9 ms |

### Architectural Justification for Config B
Config B achieves a **+16.7% improvement in Citation Accuracy and Retrieval Hit Rate**. While pure sparse BM25 is fast, it fails on vocabulary mismatch (e.g. natural language queries like *"What is the medical condonation relaxation limit?"* versus ordinance text *"Clause R.1(B).22(iii) Attendance Relaxation"*). Hybrid RRF combines dense semantic similarity (ChromaDB with `BAAI/bge-small-en-v1.5`) with exact clause keyword matching, guaranteeing both high recall and high precision.

---

## 3. Breakdown by Question Category

* **Unanswerable Questions (4 cases):** 100% correct abstention returning exact message `I could not find this information in the authorised university sources.` (R3).
* **Versioning & Precedence (4 cases):** 100% correctly applied Annex A supersession (2026 circular overriding 2024 clause; Level 1 prevailing over Level 4).
* **Personal Deterministic Tools (6 cases):** 100% accurate attendance percentage arithmetic, CWS marks calculation, and exam eligibility decisions without any LLM arithmetic (R5).
* **Authorization & Privacy Attacks (3 cases):** 100% refusal rate for queries attempting to access other students' records or unauthenticated personal requests (R7).
* **Multi-Step & What-If Questions (3 cases):** 100% accurate placement eligibility simulation with explicit statement of all 3 assumptions.
* **Policy Facts (4 cases):** 100% grounded answers with exact section citations and effective dates.
