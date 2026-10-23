# Annex E — Synthetic Data Card: DTU Student Services Dataset

**Dataset Version:** 2.0.0 (Full 60-Student Corpus)  
**Target Institution:** Delhi Technological University (DTU)  
**Schema Compliance:** Annex C Fixed Schema (SQLite / CSV)  
**Validation Status:** Passed all logical and relational invariant checks (`scripts/validate_students.py` and `scripts/validate_data.py`)

---

## 1. Purpose
This synthetic dataset simulates undergraduate student academic records for Delhi Technological University. It is engineered specifically to exercise deterministic rule evaluation tools (attendance eligibility, supplementary exam qualification, promotion criteria, and CWS marks calculation) while strictly adhering to the prohibition against using real student personal data (§4.2, §10).

---

## 2. Generator & AI Usage
* **Primary Generator:** Structured algorithmic generator paired with LLM prompt design (`scripts/generate_students.py` and `prompts/dataset_generation.txt`).
* **Model:** Claude 3.5 Sonnet / Gemini 1.5 Pro assisted prompt engineering.
* **Temperature:** 0.2 (low temperature for deterministic structural adherence).
* **Generation Method:** LLM prompt-driven specification with deterministic post-generation assembly and targeted edge-case assignment.
* **Verbatim Prompts:** Documented below in Section 3 and preserved in `prompts/dataset_generation.txt`.

---

## 3. Prompts Used for Data Generation
```text
System: You are an expert data engineer generating synthetic university student databases adhering strictly to Annex C of the HCLTech Hackathon specification.
User: Generate 60 undergraduate students for Delhi Technological University across 2 programmes (B.Tech CSE, B.Tech IT) and 2 admission batches (2023, 2024).
Include deliberate boundary conditions:
- Exactly 75.0% attendance
- Attendance one class below threshold (attendance_one_below_70)
- Zero attendance (0 classes attended)
- Full 100% attendance
- Fail boundary at exactly 39/100 total marks
- Pass boundary at exactly 40/100 total marks
- Absent result in external examination
- Detention due to attendance shortage
- Supplementary exam attempt preserving regular internal marks
- Multiple backlogs (up to 3 backlogs)
- Placement cut-off boundary at exactly 7.00 CGPA, with off-by-one test cases (6.99 and 7.01)
Output must strictly respect invariants: attended <= held, total = internal + external, max marks = 100.
```

---

## 4. Schema Enforcement & Invariants
* **Deterministic Invariant Validation:** Both `scripts/validate_students.py` and `scripts/validate_data.py` run pre-load sanity checks:
  - $0 \le \text{classes\_attended} \le \text{classes\_held}$ and $\text{classes\_held} > 0$.
  - $\text{total\_marks} = \text{internal\_marks} + \text{external\_marks} \le \text{max\_marks}$.
  - Logical alignment between marks, attendance status, and pass/fail verdicts.
  - Reserved Judge Range Guard: Strictly blocks student IDs `S9000`–`S9999` and course codes starting with `JDG`.
* **Database Constraints:** SQLite foreign keys (`ON DELETE CASCADE`), `CHECK` constraints on CGPA `[0.0, 10.0]`, backlogs `(>= 0)`, credits `(> 0)`, and attendance.
* **Derived Views:** Implemented in `sql/derived_features.sql` to dynamically compute attendance percentages, shortfall, backlog counts, and placement eligibility.

---

## 5. Row Counts & Distributions
* **Students:** 60 total records.
  - `B.Tech CSE`: 30 students (50.0%)
  - `B.Tech IT`: 30 students (50.0%)
  - Batches: 2023 (Semester 7, 50.0%), 2024 (Semester 5, 50.0%)
  - CGPA Range: 5.92 to 9.20 (mean: 7.28, std: 0.94)
* **Courses:** 12 courses across semesters 5 and 7:
  - `CS501` (Data Mining, 4 credits)
  - `CS502` (Database Systems, 4 credits)
  - `CS503` (Software Engineering, 3 credits)
  - `CS701` (Distributed Systems, 4 credits)
  - `CS702` (Machine Learning, 4 credits)
  - `CS703` (Cloud Computing, 3 credits)
  - `IT501` (Web Technologies, 4 credits)
  - `IT502` (Computer Networks, 4 credits)
  - `IT503` (Information Security, 3 credits)
  - `IT701` (Big Data Analytics, 4 credits)
  - `IT702` (Mobile Computing, 4 credits)
  - `IT703` (Internet of Things, 3 credits)
* **Attendance:** 180 records across active courses.
* **Results:** 181 examination results across regular and supplementary sessions.

---

## 6. Deliberate Edge Cases & Manifest

The dataset includes a dedicated `data/test_students/edge_case_manifest.json` indexing all test cases:

| Edge Case Scenario | Test Student(s) & Course(s) | Test Expectation |
| :--- | :--- | :--- |
| **Exact 75.0% Attendance** | `S1001` (`CS701`), `S1004` (`IT703`), `S1005` (`CS702`), `S1019` (`CS503`), `S1020` (`IT502`) | **ELIGIBLE** for End-Term Exam; 0 CWS attendance marks. |
| **Attendance Below Threshold (< 70%)** | `S1002` (`IT701`), `S1005` (`CS703`), `S1007` (`CS701`), `S1020` (`IT503`), `S1021` (`CS502`) | **DETAINED** unless condoned; requires certified medical documentation. |
| **Zero Attendance** | `S1008` (`IT701`) | **DETAINED**; 0% attendance; cannot be condoned. |
| **100% Full Attendance** | `S1003` (`CS703`), `S1004` (`IT702`), `S1009` (`CS701`), `S1011` (`CS703`), `S1012` (`IT702`) | Full 5 marks in CWS attendance component. |
| **Theory Fail Boundary (39/100)** | `S1003` (`CS701`), `S1041` (`CS702`), `S1056` (`IT503`) | **FAIL** (1 mark below 40% cut-off under Clause R.1(B).18); eligible for supplementary exam. |
| **Theory Pass Boundary (40/100)** | `S1003` (`CS702`) | **PASS** (exact minimum passing mark). |
| **Absent in Examination** | `S1004` (`IT701`) | Result labeled **ABSENT**; eligible for make-up examination under Clause R.1(B).23. |
| **Detained in Course** | `S1002` (`IT701`), `S1005` (`CS701`, `CS703`), `S1006` (`IT703`), `S1007` (`CS701`) | Result labeled **DETAINED** due to attendance shortage; barred from supplementary exam, must repeat course. |
| **Supplementary Preserving Regular Marks** | `S1003` (`CS701`) | Regular attempt was FAIL (39); supplementary attempt records updated score while preserving internal evaluation. |
| **Multiple Active Backlogs** | `S1005`, `S1006`, `S1007`, `S1021`, `S1022`, `S1041` | Multiple failed courses; tests cumulative backlog evaluation for promotion constraints. |
| **Placement Cut-off (Exact 7.00)** | `S1005`, `S1007`, `S1018`, `S1031`, `S1049` | Exactly satisfies 7.00 CGPA placement eligibility cutoff. |
| **Placement Cut-off (6.99)** | `S1013` | Fails 7.00 CGPA cutoff by 0.01; verifies precise floating-point comparison. |
| **Placement Cut-off (7.01)** | `S1014` | Clears 7.00 CGPA cutoff by 0.01. |

---

## 7. Validation Execution & Reports
Both validation suites pass cleanly:
```bash
$ uv run python scripts/validate_students.py data/test_students
=== Validating Synthetic Student Dataset: data/test_students ===
[SUCCESS] All Annex C schemas, invariants, and edge cases PASSED validation!

$ uv run python scripts/validate_data.py --dir data/test_students
Record counts:
  students.csv: 60
  courses.csv: 12
  attendance.csv: 180
  results.csv: 181
  rule_registry.csv: 4
  source_register.csv: 4
Errors: 0
Warnings: 0
VALIDATION PASSED
```

---

## 8. Limitations & Privacy
* All names, roll numbers, and academic histories are purely synthetic and generated for hackathon benchmarking.
* No personal identifiable information (PII) of real DTU students is contained within the dataset.
