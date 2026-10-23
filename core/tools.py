"""
Deterministic Academic Service Tools (Annex C & R5 Compliance)
All calculations, thresholds, and eligibility decisions are executed in deterministic Python
over SQLite tables and the rule_registry. No LLM arithmetic or hallucinated thresholds.
"""

import sys
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.database import get_connection

MONTH_ORDER = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    "SPRING": 5, "SUMMER": 7, "AUTUMN": 11, "WINTER": 12, "FALL": 11, "MONSOON": 8
}
EXAM_TYPE_ORDER = {
    "REGULAR": 1,
    "MAKEUP": 2,
    "SUPPLEMENTARY": 3
}

def session_sort_key(session_str: str, exam_type: str = "REGULAR") -> tuple:
    """
    Parses exam_session (e.g. '2024-MAY') and exam_type chronologically (Finding #17).
    Returns (year, month_num, type_priority).
    """
    parts = str(session_str).upper().replace("_", "-").split("-")
    year = 2000
    month = 0
    for p in parts:
        if p.isdigit() and len(p) == 4:
            year = int(p)
        elif p.isdigit():
            month = int(p)
        elif p in MONTH_ORDER:
            month = MONTH_ORDER[p]
    type_priority = EXAM_TYPE_ORDER.get(str(exam_type).upper(), 0)
    return (year, month, type_priority)

def get_active_rule(
    parameter: str,
    as_of_date: Optional[str] = None,
    programme: str = "ALL",
    batch: str = "ALL"
) -> Optional[Dict[str, Any]]:
    """
    Deterministically queries rule_registry for the active rule matching parameter,
    scope, and effective date window per Annex A resolution order.
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        cur = conn.execute("""
            SELECT rule_id, description, parameter, operator, value,
                   scope_programmes, scope_batches, effective_from, effective_to,
                   source_doc_id, source_section
            FROM rule_registry
            WHERE parameter = ?
              AND effective_from <= ?
              AND (effective_to = '' OR effective_to IS NULL OR effective_to >= ?)
            ORDER BY effective_from DESC
        """, (parameter, as_of_date, as_of_date))
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            return None

        # Filter by programme & batch scope
        for r in rows:
            p_scope = r["scope_programmes"]
            b_scope = r["scope_batches"]
            p_match = (p_scope == "ALL" or programme == "ALL" or programme in [p.strip() for p in p_scope.split(",")])
            b_match = (b_scope == "ALL" or batch == "ALL" or batch in [b.strip() for b in b_scope.split(",")])
            if p_match and b_match:
                return r

        # Finding #22: Return None if no rule matches scope rather than applying an out-of-scope rule
        return None
    finally:
        conn.close()

def get_all_active_rules_for_param(
    parameter: str,
    as_of_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves all active rules for a parameter (e.g., CWS tiers)."""
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        cur = conn.execute("""
            SELECT rule_id, description, parameter, operator, value,
                   scope_programmes, scope_batches, effective_from, effective_to,
                   source_doc_id, source_section
            FROM rule_registry
            WHERE parameter = ?
              AND effective_from <= ?
              AND (effective_to = '' OR effective_to IS NULL OR effective_to >= ?)
            ORDER BY effective_from DESC
        """, (parameter, as_of_date, as_of_date))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_attendance(
    student_id: str,
    course_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes attendance percentage dynamically from attendance table.
    Per Annex C: Attendance % is computed by tools, NEVER stored in the database.
    """
    conn = get_connection()
    try:
        # Check student exists
        s_cur = conn.execute("SELECT student_id, full_name, programme FROM students WHERE student_id = ?", (student_id,))
        student = s_cur.fetchone()
        if not student:
            return {
                "status": "error",
                "error": f"Student '{student_id}' not found in university records."
            }

        if course_code:
            course_code_norm = course_code.strip().upper()
            cur = conn.execute("""
                SELECT a.student_id, a.course_code, c.course_name, c.credits,
                       a.classes_held, a.classes_attended
                FROM attendance a
                JOIN courses c ON a.course_code = c.course_code
                WHERE a.student_id = ? AND UPPER(a.course_code) = ?
            """, (student_id, course_code_norm))
            row = cur.fetchone()
            if not row:
                return {
                    "status": "error",
                    "error": f"No attendance record found for student '{student_id}' in course '{course_code}'."
                }

            held = row["classes_held"]
            attended = row["classes_attended"]
            pct = round((attended / held) * 100.0, 2) if held > 0 else 0.0

            return {
                "status": "ok",
                "student_id": student_id,
                "student_name": student["full_name"],
                "course_code": row["course_code"],
                "course_name": row["course_name"],
                "classes_held": held,
                "classes_attended": attended,
                "attendance_pct": pct
            }
        else:
            cur = conn.execute("""
                SELECT a.course_code, c.course_name, a.classes_held, a.classes_attended
                FROM attendance a
                JOIN courses c ON a.course_code = c.course_code
                WHERE a.student_id = ?
                ORDER BY a.course_code ASC
            """, (student_id,))
            rows = cur.fetchall()
            if not rows:
                return {
                    "status": "ok",
                    "student_id": student_id,
                    "student_name": student["full_name"],
                    "courses": [],
                    "overall_attendance_pct": 0.0,
                    "total_classes_held": 0,
                    "total_classes_attended": 0
                }

            course_list = []
            total_held = 0
            total_attended = 0
            for r in rows:
                h = r["classes_held"]
                a = r["classes_attended"]
                p = round((a / h) * 100.0, 2) if h > 0 else 0.0
                total_held += h
                total_attended += a
                course_list.append({
                    "course_code": r["course_code"],
                    "course_name": r["course_name"],
                    "classes_held": h,
                    "classes_attended": a,
                    "attendance_pct": p
                })

            overall_pct = round((total_attended / total_held) * 100.0, 2) if total_held > 0 else 0.0
            return {
                "status": "ok",
                "student_id": student_id,
                "student_name": student["full_name"],
                "courses": course_list,
                "total_classes_held": total_held,
                "total_classes_attended": total_attended,
                "overall_attendance_pct": overall_pct
            }
    finally:
        conn.close()

def check_exam_eligibility(
    student_id: str,
    course_code: str,
    has_medical_cert: bool = False,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks end-semester examination eligibility based on attendance and cited rules.
    Reads threshold from rule_registry:
      - ATT-MIN-01: min_attendance_pct >= 75.0 (DTU-ORD-2024 Clause R.1(B).22)
      - ATT-COND-MED: medical_condonation_pct >= 65.0 (DTU-ORD-2024 Clause R.1(B).22(iii), pre-2026-08-01)
      - ATT-COND-MED-2026: medical_condonation_pct >= 70.0 (DTU-SYN-AMEND-2026 Section 1, from 2026-08-01)
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    att_res = get_attendance(student_id, course_code)
    if att_res.get("status") != "ok":
        return att_res

    attendance_pct = att_res["attendance_pct"]
    course_name = att_res["course_name"]

    # 1. Fetch mandatory minimum attendance rule
    min_rule = get_active_rule("min_attendance_pct", as_of_date)
    if not min_rule:
        return {
            "status": "no_active_policy",
            "result": "NO_ACTIVE_POLICY",
            "student_id": student_id,
            "course_code": course_code.upper(),
            "course_name": course_name,
            "attendance_pct": attendance_pct,
            "as_of_date": as_of_date,
            "applied_rules": [],
            "explanation": f"As of {as_of_date}, no university attendance regulation is in effect."
        }

    min_threshold = float(min_rule["value"])

    applied_rules = [{
        "rule_id": min_rule["rule_id"],
        "parameter": min_rule["parameter"],
        "operator": min_rule["operator"],
        "value": min_rule["value"],
        "source_doc_id": min_rule["source_doc_id"],
        "source_section": min_rule["source_section"]
    }]

    # Case A: Attendance meets regular threshold
    if attendance_pct >= min_threshold:
        return {
            "status": "ok",
            "result": "ELIGIBLE",
            "student_id": student_id,
            "course_code": course_code.upper(),
            "course_name": course_name,
            "attendance_pct": attendance_pct,
            "classes_held": att_res["classes_held"],
            "classes_attended": att_res["classes_attended"],
            "required_pct": min_threshold,
            "has_medical_cert": has_medical_cert,
            "applied_rules": applied_rules,
            "explanation": (
                f"Your attendance in {course_code.upper()} is {attendance_pct}%, which satisfies "
                f"the minimum required attendance of {min_threshold}% under {min_rule['source_section']} "
                f"of {min_rule['source_doc_id']}. You are eligible to appear in the end-semester examination."
            ),
            "as_of_date": as_of_date
        }

    # Case B: Below threshold - check medical condonation
    cond_rule = get_active_rule("medical_condonation_pct", as_of_date)
    if cond_rule:
        applied_rules.append({
            "rule_id": cond_rule["rule_id"],
            "parameter": cond_rule["parameter"],
            "operator": cond_rule["operator"],
            "value": cond_rule["value"],
            "source_doc_id": cond_rule["source_doc_id"],
            "source_section": cond_rule["source_section"]
        })
        cond_threshold = float(cond_rule["value"])
    else:
        cond_threshold = 65.0

    if has_medical_cert and attendance_pct >= cond_threshold:
        return {
            "status": "ok",
            "result": "ELIGIBLE_WITH_CONDONATION",
            "student_id": student_id,
            "course_code": course_code.upper(),
            "course_name": course_name,
            "attendance_pct": attendance_pct,
            "classes_held": att_res["classes_held"],
            "classes_attended": att_res["classes_attended"],
            "required_pct": min_threshold,
            "condonation_threshold_pct": cond_threshold,
            "has_medical_cert": True,
            "applied_rules": applied_rules,
            "explanation": (
                f"Your attendance in {course_code.upper()} is {attendance_pct}%, which is below the standard "
                f"{min_threshold}% minimum, but satisfies the medical condonation threshold of {cond_threshold}% "
                f"under {cond_rule['source_section']} of {cond_rule['source_doc_id']} with approved medical certification. "
                f"You are eligible to appear in the end-semester examination."
            ),
            "as_of_date": as_of_date
        }

    # Case C: Not eligible / Detained
    detained_reason = (
        f"Your attendance in {course_code.upper()} is {attendance_pct}%, which is below the mandatory "
        f"{min_threshold}% requirement under {min_rule['source_section']} of {min_rule['source_doc_id']}."
    )
    if has_medical_cert:
        detained_reason += (
            f" Even with medical certification, attendance is below the relaxed condonation threshold "
            f"of {cond_threshold}% under {cond_rule['source_section']} of {cond_rule['source_doc_id']}."
        )
    detained_reason += " You are DETAINED from appearing in the end-semester examination and must repeat the course."

    return {
        "status": "ok",
        "result": "DETAINED",
        "student_id": student_id,
        "course_code": course_code.upper(),
        "course_name": course_name,
        "attendance_pct": attendance_pct,
        "classes_held": att_res["classes_held"],
        "classes_attended": att_res["classes_attended"],
        "required_pct": min_threshold,
        "has_medical_cert": has_medical_cert,
        "applied_rules": applied_rules,
        "explanation": detained_reason,
        "as_of_date": as_of_date
    }

def compute_cws_attendance_marks(
    student_id: str,
    course_code: str,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes awarded CWS attendance marks (0 to 5) per DTU-CIR-ATT-2024 Section 2:
      96-100% -> 5 marks (CWS-ATT-5)
      91-95%  -> 4 marks (CWS-ATT-4)
      86-90%  -> 3 marks (CWS-ATT-3)
      81-85%  -> 2 marks (CWS-ATT-2)
      76-80%  -> 1 mark  (CWS-ATT-1)
      < 76%   -> 0 marks
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    att_res = get_attendance(student_id, course_code)
    if att_res.get("status") != "ok":
        return att_res

    pct = att_res["attendance_pct"]
    course_name = att_res["course_name"]

    tier_rules = get_all_active_rules_for_param("cws_attendance_tier", as_of_date)
    
    # Finding #21: If no tier rules are active as of this date, abstain and report no active policy
    if not tier_rules:
        return {
            "status": "no_active_policy",
            "student_id": student_id,
            "course_code": course_code.upper(),
            "course_name": course_name,
            "attendance_pct": pct,
            "awarded_marks": None,
            "applied_rules": [],
            "explanation": f"As of {as_of_date}, no Continuous Work Assessment (CWS) attendance marks tier policy is in effect in university circulars."
        }

    # Dynamically parse tier thresholds from active rules in rule_registry
    parsed_tiers = []
    for r in tier_rules:
        val_str = r.get("value", "")
        parts = [float(x.strip()) for x in val_str.split(",") if x.strip()]
        if len(parts) >= 2:
            low, high = min(parts), max(parts)
        elif len(parts) == 1:
            low, high = parts[0], 100.0
        else:
            continue
        marks_match = re.search(r"\d+", r["rule_id"])
        marks = int(marks_match.group(0)) if marks_match else 0
        parsed_tiers.append((low, high, marks, r))

    parsed_tiers.sort(key=lambda x: x[0], reverse=True)

    awarded_marks = 0
    matched_rule = None
    for low, high, marks, r in parsed_tiers:
        if low <= pct <= high:
            awarded_marks = marks
            matched_rule = r
            break
        elif pct > high and marks == parsed_tiers[0][2]:
            awarded_marks = marks
            matched_rule = r
            break

    applied_rules = []
    if matched_rule:
        applied_rules.append({
            "rule_id": matched_rule["rule_id"],
            "parameter": matched_rule["parameter"],
            "operator": matched_rule["operator"],
            "value": matched_rule["value"],
            "source_doc_id": matched_rule["source_doc_id"],
            "source_section": matched_rule["source_section"]
        })

    explanation = (
        f"With an attendance of {pct}% in {course_code.upper()} ({course_name}), you are awarded "
        f"{awarded_marks} out of 5 marks for the Continuous Work Assessment (CWS) attendance component "
        f"pursuant to DTU Circular DTU-CIR-ATT-2024 Section 2."
    )

    return {
        "status": "ok",
        "student_id": student_id,
        "course_code": course_code.upper(),
        "course_name": course_name,
        "attendance_pct": pct,
        "cws_attendance_marks": awarded_marks,
        "max_cws_attendance_marks": 5,
        "applied_rules": applied_rules,
        "explanation": explanation,
        "as_of_date": as_of_date
    }

def get_academic_summary(student_id: str) -> Dict[str, Any]:
    """
    Retrieves full academic profile, student records, and results breakdown.
    Calculates total credits earned and active backlog details deterministically.
    """
    conn = get_connection()
    try:
        s_cur = conn.execute("""
            SELECT student_id, full_name, programme, batch_year, current_semester,
                   cgpa, active_backlogs
            FROM students
            WHERE student_id = ?
        """, (student_id,))
        student = s_cur.fetchone()
        if not student:
            return {"status": "error", "error": f"Student '{student_id}' not found."}

        # Query all past results
        r_cur = conn.execute("""
            SELECT r.course_code, c.course_name, c.credits, r.exam_session,
                   r.exam_type, r.internal_marks, r.external_marks, r.total_marks,
                   r.max_marks, r.result
            FROM results r
            JOIN courses c ON r.course_code = c.course_code
            WHERE r.student_id = ?
        """, (student_id,))
        raw_results = [dict(row) for row in r_cur.fetchall()]

        # Sort all historical results chronologically (Finding #17)
        results = sorted(raw_results, key=lambda x: session_sort_key(x["exam_session"], x["exam_type"]))

        # Group attempts by course to prevent retakes from distorting summaries (Finding #16)
        course_attempts: Dict[str, List[Dict[str, Any]]] = {}
        for r in results:
            cc = r["course_code"]
            if cc not in course_attempts:
                course_attempts[cc] = []
            course_attempts[cc].append(r)

        earned_credits = 0
        backlog_courses = []
        passed_courses = []

        for cc, attempts in course_attempts.items():
            # Latest attempt chronologically
            latest = attempts[-1]
            # Has the student ever passed this course?
            pass_attempt = next((a for a in attempts if a["result"] == "PASS"), None)

            if pass_attempt or latest["result"] == "PASS":
                # Course is cleared: add credits once
                earned_credits += latest["credits"]
                passed_courses.append(cc)
            else:
                # Course remains an active backlog
                backlog_courses.append({
                    "course_code": cc,
                    "course_name": latest["course_name"],
                    "status": latest["result"],
                    "total_marks": latest["total_marks"],
                    "exam_session": latest["exam_session"],
                    "exam_type": latest["exam_type"]
                })

        return {
            "status": "ok",
            "student_id": student["student_id"],
            "full_name": student["full_name"],
            "programme": student["programme"],
            "batch_year": student["batch_year"],
            "current_semester": student["current_semester"],
            "cgpa": student["cgpa"],
            "active_backlogs": student["active_backlogs"],
            "earned_credits": earned_credits,
            "passed_courses_count": len(passed_courses),
            "results_history": results,
            "backlog_details": backlog_courses
        }
    finally:
        conn.close()

def check_promotion_eligibility(
    student_id: str,
    target_semester: Optional[int] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Determines promotion eligibility to next semester/year.
    Under DTU Ordinance Clause R.1(B).15 (rule PROMO-MAX-BACKLOG):
      Registration to 5th semester (3rd year) requires active backlogs <= 4.
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        cur = conn.execute("""
            SELECT student_id, full_name, programme, batch_year, current_semester,
                   cgpa, active_backlogs
            FROM students
            WHERE student_id = ?
        """, (student_id,))
        student = cur.fetchone()
        if not student:
            return {"status": "error", "error": f"Student '{student_id}' not found."}

        current_sem = student["current_semester"]
        active_backlogs = student["active_backlogs"]
        programme = student["programme"]

        if target_semester is None:
            target_semester = current_sem + 1

        promo_rule = get_active_rule("max_backlogs_promotion", as_of_date, programme=programme)

        # Finding #15: Guard against None when as_of_date is before rule's effective date
        if not promo_rule:
            return {
                "status": "no_active_policy",
                "result": "NO_ACTIVE_POLICY",
                "student_id": student_id,
                "current_semester": current_sem,
                "target_semester": target_semester,
                "active_backlogs": active_backlogs,
                "max_allowed_backlogs": None,
                "applied_rules": [],
                "explanation": f"As of {as_of_date}, no promotion regulations are in effect.",
                "as_of_date": as_of_date
            }

        max_allowed = int(promo_rule["value"])

        applied_rules = [{
            "rule_id": promo_rule["rule_id"],
            "parameter": promo_rule["parameter"],
            "operator": promo_rule["operator"],
            "value": promo_rule["value"],
            "source_doc_id": promo_rule["source_doc_id"],
            "source_section": promo_rule["source_section"]
        }]

        # Criteria for entering 3rd year (5th semester) or beyond
        if target_semester >= 5:
            if active_backlogs <= max_allowed:
                result = "ELIGIBLE"
                explanation = (
                    f"You have {active_backlogs} active backlog(s), which does not exceed the maximum permissible "
                    f"limit of {max_allowed} under {promo_rule['source_section']} ({promo_rule['source_doc_id']}). "
                    f"You are eligible for registration and promotion to semester {target_semester}."
                )
            else:
                result = "NOT_ELIGIBLE"
                explanation = (
                    f"You have {active_backlogs} active backlog(s), which exceeds the maximum threshold of {max_allowed} "
                    f"permissible under {promo_rule['source_section']} ({promo_rule['source_doc_id']}). "
                    f"You are not eligible for promotion to semester {target_semester} until you clear surplus backlogs."
                )
        elif target_semester == 3:
            # Finding #14: Enforce >= 50% 1st year credits earned per Clause R.1(B).15
            c_cur = conn.execute("""
                SELECT SUM(credits) as total_creds
                FROM courses
                WHERE semester IN (1, 2)
                  AND (programme = ? OR programme = 'ALL')
            """, (programme,))
            c_row = c_cur.fetchone()
            prescribed_creds = c_row["total_creds"] if c_row and c_row["total_creds"] else 0

            e_cur = conn.execute("""
                SELECT DISTINCT c.course_code, c.credits
                FROM results r
                JOIN courses c ON r.course_code = c.course_code
                WHERE r.student_id = ?
                  AND r.result = 'PASS'
                  AND c.semester IN (1, 2)
            """, (student_id,))
            earned_1st_year = sum(row["credits"] for row in e_cur.fetchall())
            req_creds = 0.5 * prescribed_creds if prescribed_creds > 0 else 0

            if prescribed_creds > 0 and earned_1st_year < req_creds:
                result = "NOT_ELIGIBLE"
                explanation = (
                    f"You have earned {earned_1st_year} credits out of {prescribed_creds} prescribed credits "
                    f"for Year 1 ({round(earned_1st_year / prescribed_creds * 100, 1)}%), which is below the "
                    f"mandatory 50% minimum threshold under {promo_rule['source_section']} ({promo_rule['source_doc_id']}). "
                    f"You are not eligible for promotion to semester 3."
                )
            else:
                result = "ELIGIBLE"
                explanation = (
                    f"You have satisfied the 1st year credit requirements under {promo_rule['source_section']} "
                    f"({promo_rule['source_doc_id']}) and are eligible for registration and promotion to semester 3."
                )
        else:
            # Regular semester advancement
            result = "ELIGIBLE"
            explanation = (
                f"You are currently in semester {current_sem} and eligible to register for semester {target_semester}."
            )

        return {
            "status": "ok",
            "result": result,
            "student_id": student_id,
            "current_semester": current_sem,
            "target_semester": target_semester,
            "active_backlogs": active_backlogs,
            "max_allowed_backlogs": max_allowed,
            "applied_rules": applied_rules,
            "explanation": explanation,
            "as_of_date": as_of_date
        }
    finally:
        conn.close()

def check_supplementary_eligibility(
    student_id: str,
    course_code: str,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks eligibility to register for Supplementary Examination.
    Under DTU Guidelines (DTU-CIR-EXAM-SUPP Section 1):
      - Result == 'FAIL' -> ELIGIBLE. Internal marks from regular term are carried forward.
      - Result == 'ABSENT' -> ELIGIBLE (subject to HOD approval / medical cause under Section 3).
      - Result == 'DETAINED' -> NOT_ELIGIBLE. Detained students are strictly prohibited from
        supplementary examination and must repeat the course during regular semester.
      - Result == 'PASS' -> NOT_ELIGIBLE. Already cleared.
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        # Check student
        s_cur = conn.execute("SELECT student_id, full_name FROM students WHERE student_id = ?", (student_id,))
        student = s_cur.fetchone()
        if not student:
            return {"status": "error", "error": f"Student '{student_id}' not found."}

        cur = conn.execute("""
            SELECT r.course_code, c.course_name, r.exam_session, r.exam_type,
                   r.internal_marks, r.external_marks, r.total_marks, r.max_marks, r.result
            FROM results r
            JOIN courses c ON r.course_code = c.course_code
            WHERE r.student_id = ? AND UPPER(r.course_code) = ?
        """, (student_id, course_code.strip().upper()))
        all_attempts = [dict(r) for r in cur.fetchall()]
        if not all_attempts:
            return {
                "status": "error",
                "error": f"No examination record found for student '{student_id}' in course '{course_code}'."
            }

        # Finding #17: Chronological sort with session_sort_key and attempt tie-breaker
        sorted_attempts = sorted(all_attempts, key=lambda x: session_sort_key(x["exam_session"], x["exam_type"]))
        row = sorted_attempts[-1]

        prev_result = row["result"]
        course_name = row["course_name"]

        supp_rule = get_active_rule("supplementary_eligible_grade", as_of_date)
        detain_rule = get_active_rule("supplementary_prohibited_status", as_of_date)

        # Finding #15: Guard against None when as_of_date is before rule's effective date
        if not supp_rule:
            return {
                "status": "no_active_policy",
                "result": "NO_ACTIVE_POLICY",
                "student_id": student_id,
                "course_code": course_code.upper(),
                "course_name": course_name,
                "prior_result": prev_result,
                "prior_total_marks": row["total_marks"],
                "applied_rules": [],
                "explanation": f"As of {as_of_date}, no supplementary examination regulations are in effect.",
                "as_of_date": as_of_date
            }

        applied_rules = [{
            "rule_id": supp_rule["rule_id"],
            "parameter": supp_rule["parameter"],
            "operator": supp_rule["operator"],
            "value": supp_rule["value"],
            "source_doc_id": supp_rule["source_doc_id"],
            "source_section": supp_rule["source_section"]
        }]
        if detain_rule:
            applied_rules.append({
                "rule_id": detain_rule["rule_id"],
                "parameter": detain_rule["parameter"],
                "operator": detain_rule["operator"],
                "value": detain_rule["value"],
                "source_doc_id": detain_rule["source_doc_id"],
                "source_section": detain_rule["source_section"]
            })

        if prev_result == "FAIL":
            result = "ELIGIBLE"
            explanation = (
                f"You secured a '{prev_result}' grade in {course_code.upper()} ({course_name}) with {row['total_marks']}/100 marks. "
                f"Under {supp_rule['source_doc_id']} {supp_rule['source_section']}, you are eligible to register for the "
                f"Supplementary Examination. Your regular term internal marks ({row['internal_marks']}) will be retained."
            )
        elif prev_result == "ABSENT":
            result = "ELIGIBLE_WITH_APPROVAL"
            explanation = (
                f"Your record shows '{prev_result}' for {course_code.upper()} ({course_name}). Under {supp_rule['source_doc_id']}, "
                f"you are eligible to appear in the supplementary/make-up examination subject to Dean/HOD verification of medical hospitalization."
            )
        elif prev_result == "DETAINED":
            result = "NOT_ELIGIBLE"
            detain_doc = detain_rule['source_doc_id'] if detain_rule else "University Ordinance"
            detain_sec = detain_rule['source_section'] if detain_rule else "Clause R.1(B)"
            explanation = (
                f"You were 'DETAINED' in {course_code.upper()} ({course_name}) due to attendance shortage. "
                f"Under {detain_doc} {detain_sec}, detained students are strictly barred "
                f"from supplementary examinations and must repeat the entire course in a regular semester."
            )
        else:  # PASS
            result = "NOT_ELIGIBLE"
            explanation = (
                f"You have already passed {course_code.upper()} ({course_name}) with {row['total_marks']}/100 marks. "
                f"Supplementary examination registration is not permitted for cleared courses."
            )

        return {
            "status": "ok",
            "result": result,
            "student_id": student_id,
            "course_code": course_code.upper(),
            "course_name": course_name,
            "prior_result": prev_result,
            "prior_total_marks": row["total_marks"],
            "internal_marks_retained": row["internal_marks"],
            "applied_rules": applied_rules,
            "explanation": explanation,
            "as_of_date": as_of_date
        }
    finally:
        conn.close()

def evaluate_what_if_supplementary(
    student_id: str,
    course_code: str,
    anticipated_total_marks: int = 50,
    placement_cutoff_cgpa: float = 6.0,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Multi-step / what-if analysis tool (Problem Statement Section 2.1 & R6):
    'I failed Data Structures. If I pass the supplementary, will I be eligible for placement?'
    Combines supplementary eligibility, marks simulation, backlog reduction, and placement policy.
    Explicitly states all assumptions made.
    """
    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Check supplementary eligibility
    supp_check = check_supplementary_eligibility(student_id, course_code, as_of_date)
    if supp_check.get("status") != "ok":
        return supp_check

    if supp_check["result"] == "NOT_ELIGIBLE":
        return {
            "status": "ok",
            "result": "INELIGIBLE_FOR_SUPPLEMENTARY",
            "student_id": student_id,
            "course_code": course_code.upper(),
            "explanation": (
                f"Cannot evaluate what-if: You are not eligible for supplementary examination in {course_code.upper()} "
                f"because your status is '{supp_check.get('prior_result')}'. {supp_check.get('explanation')}"
            ),
            "assumptions": []
        }

    # Step 2: Fetch student academic summary
    summary = get_academic_summary(student_id)
    current_cgpa = summary["cgpa"]
    current_backlogs = summary["active_backlogs"]

    # Step 3: Fetch pass mark rule
    pass_rule = get_active_rule("min_pass_total_pct", as_of_date)
    min_pass = float(pass_rule["value"]) if pass_rule else 40.0

    # Step 4: Placement rules
    place_cgpa_rule = get_active_rule("placement_min_cgpa", as_of_date)
    place_backlog_rule = get_active_rule("placement_max_active_backlogs", as_of_date)

    required_cgpa = float(place_cgpa_rule["value"]) if place_cgpa_rule else placement_cutoff_cgpa
    max_place_backlogs = int(place_backlog_rule["value"]) if place_backlog_rule else 0

    applied_rules = []
    if pass_rule:
        applied_rules.append(pass_rule)
    if place_cgpa_rule:
        applied_rules.append(place_cgpa_rule)
    if place_backlog_rule:
        applied_rules.append(place_backlog_rule)

    # Finding #18: Check whether anticipated_total_marks meets min_pass standard
    if anticipated_total_marks < min_pass:
        simulated_backlogs = current_backlogs
        outcome = "NOT_ELIGIBLE_FOR_PLACEMENT"
        assumptions = [
            f"Assumption 1: Student appears in supplementary examination for {course_code.upper()} and scores {anticipated_total_marks}/100, which is BELOW the minimum passing threshold of {min_pass}% (DTU-ORD-2024 Clause R.1(B).18).",
            f"Assumption 2: Since the examination is failed, active backlogs remain unchanged at {current_backlogs}.",
            f"Assumption 3: Campus placement registration requires CGPA >= {required_cgpa} and active backlogs <= {max_place_backlogs} (DTU-ORD-2024 Clause R.1(B).28)."
        ]
        conclusion = (
            f"If you score {anticipated_total_marks}/100 in the supplementary examination for {course_code.upper()}, "
            f"you will NOT clear the course because the minimum passing standard is {min_pass}%. "
            f"Your active backlogs will remain at {current_backlogs}, and you WILL NOT BE ELIGIBLE for campus placement drives."
        )
    else:
        assumptions = [
            f"Assumption 1: Student appears in supplementary examination for {course_code.upper()} and scores {anticipated_total_marks}/100, which satisfies the {min_pass}% passing threshold (DTU-ORD-2024 Clause R.1(B).18).",
            f"Assumption 2: Clearing this course reduces active backlogs by 1 (from {current_backlogs} to {max(0, current_backlogs - 1)}).",
            f"Assumption 3: Campus placement registration requires CGPA >= {required_cgpa} and active backlogs <= {max_place_backlogs} (DTU-ORD-2024 Clause R.1(B).28)."
        ]

        simulated_backlogs = max(0, current_backlogs - 1)
        is_placement_eligible = (simulated_backlogs <= max_place_backlogs) and (current_cgpa >= required_cgpa)

        if is_placement_eligible:
            outcome = "ELIGIBLE_FOR_PLACEMENT"
            conclusion = (
                f"Yes, if you pass the supplementary examination in {course_code.upper()}, your active backlogs "
                f"will drop from {current_backlogs} to {simulated_backlogs}. Since your CGPA is {current_cgpa} "
                f"(>= {required_cgpa} cut-off) and you will have {simulated_backlogs} backlogs, you WILL BE ELIGIBLE "
                f"for campus placement drives under DTU Placement Guidelines."
            )
        else:
            outcome = "NOT_ELIGIBLE_FOR_PLACEMENT"
            reasons = []
            if simulated_backlogs > max_place_backlogs:
                reasons.append(f"you will still have {simulated_backlogs} remaining active backlogs (placement requires 0)")
            if current_cgpa < required_cgpa:
                reasons.append(f"your CGPA is {current_cgpa}, which is below the placement threshold of {required_cgpa}")
            conclusion = (
                f"Even if you pass the supplementary examination in {course_code.upper()}, you WILL NOT be eligible "
                f"for campus placement because {' and '.join(reasons)}."
            )

    return {
        "status": "ok",
        "result": outcome,
        "student_id": student_id,
        "course_code": course_code.upper(),
        "current_cgpa": current_cgpa,
        "current_backlogs": current_backlogs,
        "simulated_backlogs": simulated_backlogs,
        "placement_cgpa_cutoff": required_cgpa,
        "placement_max_backlogs": max_place_backlogs,
        "assumptions": assumptions,
        "applied_rules": applied_rules,
        "explanation": conclusion,
        "as_of_date": as_of_date
    }

# Tool Registry Map for LangGraph & Agent invocation
TOOL_REGISTRY: Dict[str, Any] = {
    "get_attendance": get_attendance,
    "check_exam_eligibility": check_exam_eligibility,
    "compute_cws_attendance_marks": compute_cws_attendance_marks,
    "get_academic_summary": get_academic_summary,
    "check_promotion_eligibility": check_promotion_eligibility,
    "check_supplementary_eligibility": check_supplementary_eligibility,
    "evaluate_what_if_supplementary": evaluate_what_if_supplementary
}

def get_tool_schemas() -> List[Dict[str, Any]]:
    """Returns OpenAI / LangGraph compatible function schemas for all deterministic tools."""
    return [
        {
            "name": "get_attendance",
            "description": "Calculates attendance percentage and retrieves classes held/attended for a student in a course or all courses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID (e.g. S1001)"},
                    "course_code": {"type": "string", "description": "Course code (e.g. CO201). Optional."}
                },
                "required": ["student_id"]
            }
        },
        {
            "name": "check_exam_eligibility",
            "description": "Checks end-semester exam eligibility based on mandatory 75% attendance and medical condonation rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"},
                    "course_code": {"type": "string", "description": "Course code"},
                    "has_medical_cert": {"type": "boolean", "description": "Whether student has approved medical certificate", "default": False},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD date context", "default": None}
                },
                "required": ["student_id", "course_code"]
            }
        },
        {
            "name": "compute_cws_attendance_marks",
            "description": "Calculates awarded Continuous Work Assessment (CWS) attendance marks (0 to 5) based on percentage slabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"},
                    "course_code": {"type": "string", "description": "Course code"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD date context", "default": None}
                },
                "required": ["student_id", "course_code"]
            }
        },
        {
            "name": "get_academic_summary",
            "description": "Retrieves comprehensive academic profile including CGPA, active backlogs, earned credits, and results history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"}
                },
                "required": ["student_id"]
            }
        },
        {
            "name": "check_promotion_eligibility",
            "description": "Checks whether a student can register / be promoted to the target semester based on backlog thresholds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"},
                    "target_semester": {"type": "integer", "description": "Target semester number (e.g. 5)"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD date context", "default": None}
                },
                "required": ["student_id"]
            }
        },
        {
            "name": "check_supplementary_eligibility",
            "description": "Checks whether student can appear in supplementary exam for a course based on previous exam result and detention status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"},
                    "course_code": {"type": "string", "description": "Course code"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD date context", "default": None}
                },
                "required": ["student_id", "course_code"]
            }
        },
        {
            "name": "evaluate_what_if_supplementary",
            "description": "Performs multi-step what-if simulation: analyzes impact of passing supplementary examination on backlogs and placement eligibility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Student ID"},
                    "course_code": {"type": "string", "description": "Course code"},
                    "anticipated_total_marks": {"type": "integer", "description": "Anticipated supplementary exam score (default 50)", "default": 50},
                    "placement_cutoff_cgpa": {"type": "number", "description": "Placement CGPA threshold (default 6.0)", "default": 6.0},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD date context", "default": None}
                },
                "required": ["student_id", "course_code"]
            }
        }
    ]
