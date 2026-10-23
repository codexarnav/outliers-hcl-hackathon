# Annex E — Synthetic Data Card: DTU Student Services Dataset

**Dataset Version:** 1.0.0  
**Target Institution:** Delhi Technological University (DTU)  
**Schema Compliance:** Annex C Fixed Schema (SQLite / CSV)  
**Validation Status:** Passed all logical and relational invariant checks (`scripts/validate_students.py`)

---

## 1. Purpose
This synthetic dataset simulates undergraduate student academic records for Delhi Technological University. It is engineered specifically to exercise deterministic rule evaluation tools (attendance eligibility, supplementary exam qualification, promotion criteria, and CWS marks calculation) while strictly adhering to the prohibition against using real student personal data (§4.2, §10).

---

## 2. Generator & AI Usage
* **Primary Generator:** Structured algorithmic generator paired with LLM prompt design (`scripts/generate_students.py`).
* **Model:** Claude 3.5 Sonnet / Gemini 1.5 Pro assisted prompt engineering.
* **Temperature:** 0.2 (low temperature for deterministic structural adherence).
* **Verbatim Prompts:** Documented below in Section 3.

---

## 3. Prompts Used for Data Generation
```text
System: You are an expert data engineer generating synthetic university student databases adhering strictly to Annex C of the HCLTech Hackathon specification.
User: Generate 35 undergraduate students for Delhi Technological University across 3 programmes (B.Tech CSE, B.Tech IT, B.Tech ECE) and 3 batches (2022, 2023, 2024).
Include deliberate boundary conditions:
- Exactly 75.0% attendance (S1001)
- Attendance one class below 75% threshold (S1002: 72.5%)
- Medical condonation boundary (S1003: 65.0%)
- Pass/Fail 40% aggregate mark boundary (S1004: 39 marks)
- Absent result eligible for make-up examination (S1005)
- Promotion backlog boundary with exactly 4 active backlogs (S1006)
- Severe detention at 50% attendance (S1007)
- Placement cut-off boundary with 7.00 CGPA (S1008)
Output must strictly respect invariants: attended <= held, total = internal + external, max marks = 100.
```

---

## 4. Schema Enforcement
* **Deterministic Invariant Validation:** `scripts/validate_students.py` runs pre-load sanity checks:
  - $0 \le \text{classes\_attended} \le \text{classes\_held}$ and $\text{classes\_held} > 0$.
  - $\text{total\_marks} = \text{internal\_marks} + \text{external\_marks} \le \text{max\_marks}$.
  - Logical alignment between marks, attendance status, and pass/fail verdicts.
  - Reserved Judge Range Guard: Strictly blocks student IDs `S9000`–`S9999` and course codes starting with `JDG`.
* **Database Constraints:** SQLite foreign keys (`ON DELETE CASCADE`), `CHECK` constraints on CGPA `[0.0, 10.0]`, backlogs `(>= 0)`, credits `(> 0)`, and attendance.

---

## 5. Row Counts & Distributions
* **Students:** 35 total records.
  - `B.Tech CSE`: 17 students (48.6%)
  - `B.Tech IT`: 9 students (25.7%)
  - `B.Tech ECE`: 9 students (25.7%)
  - Batches: 2022 (31.4%), 2023 (45.7%), 2024 (22.9%)
  - CGPA Range: 4.80 to 9.50 (mean: 7.24, std: 1.15)
* **Courses:** 8 courses across 3 programmes and foundational humanities:
  - `CO201` (Data Structures, 4 credits)
  - `CO203` (Discrete Mathematics, 4 credits)
  - `CO301` (Database Management Systems, 4 credits)
  - `IT201` (Object Oriented Programming, 4 credits)
  - `IT301` (Operating Systems, 4 credits)
  - `EC201` (Digital Design, 4 credits)
  - `EC203` (Signals & Systems, 4 credits)
  - `HU101` (Communication Skills, 2 credits)
* **Attendance:** 62 records across active courses.
* **Results:** 62 examination results across regular and supplementary sessions.

---

## 6. Deliberate Edge Cases & Test Students

| Student ID | Full Name | Programme | Edge Case Scenario | Test Expectation |
| :--- | :--- | :--- | :--- | :--- |
| **`S1001`** | Aarav Sharma | B.Tech CSE | Exact 75.0% Attendance (`30/40` in `CO201`) | **ELIGIBLE** for End-Term Exam; 0 CWS attendance marks. |
| **`S1002`** | Diya Patel | B.Tech CSE | Attendance 1 class below threshold (`29/40` = 72.5%) | **DETAINED** unless condoned; 0 CWS marks. |
| **`S1003`** | Rohan Verma | B.Tech CSE | Medical condonation boundary (`26/40` = 65.0%) | **CONDONABLE** under Clause R.1(B).22(iii) upon medical proof. |
| **`S1004`** | Ananya Iyer | B.Tech CSE | Theory Pass Mark Boundary (39/100 Total Marks) | **FAIL** (1 mark below 40% cut-off under Clause R.1(B).18). |
| **`S1005`** | Kabir Singh | B.Tech CSE | Absent in External Examination | Eligible for **MAKE-UP EXAM** under Clause R.1(B).23. |
| **`S1006`** | Meera Nair | B.Tech CSE | Promotion Backlog Boundary (Exactly 4 backlogs) | Eligible for conditional promotion to Sem 5 under Clause R.1(B).15. |
| **`S1007`** | Aditya Joshi | B.Tech CSE | Severe Shortage (`20/40` = 50.0% Attendance) | **STRICTLY DETAINED**; cannot be condoned by any university authority. |
| **`S1008`** | Priya Kapoor | B.Tech IT | Placement Cut-off Boundary (7.00 CGPA) | Exactly satisfies 7.00 placement eligibility criteria. |

---

## 7. Validation Results & Errors Caught
1. **Initial Issue:** Initial random generation produced cases where internal (15) + external (25) = 40, but result flag was labeled `FAIL`.
   * **Fix:** Enforced post-generation rule asserting `res = 'PASS' if total >= 40 else 'FAIL'` (except for explicit `ABSENT` / `DETAINED` overrides).
2. **Attendance % Column Elimination:** Early draft had an `attendance_pct` column in `attendance.csv`.
   * **Fix:** Removed per Annex C strict rule: *"Attendance % is computed by tools, never stored."*
3. **Reserved Range Isolation:** Verified that no IDs fall within `S9000`–`S9999` or course prefix `JDG`.

---

## 8. Known Limitations
* The dataset simulates 3 core B.Tech programmes; specialised departmental electives and minor degrees are represented only via core course codes.
* Exam sessions currently cover `2024-MAY`; historical longitudinal multi-year academic transcripts are simulated through the `cgpa` and `active_backlogs` aggregates.
