"""
Unit Tests for Deterministic Academic Service Tools (Annex C & R5 Compliance)
"""

import pytest
from core.tools import (
    get_attendance,
    check_exam_eligibility,
    compute_cws_attendance_marks,
    get_academic_summary,
    check_promotion_eligibility,
    check_supplementary_eligibility,
    evaluate_what_if_supplementary,
    TOOL_REGISTRY,
    get_tool_schemas
)

def test_get_attendance_single_course():
    # S1001: 30 attended / 40 held in CO201 = exactly 75.0%
    res = get_attendance("S1001", "CO201")
    assert res["status"] == "ok"
    assert res["student_id"] == "S1001"
    assert res["classes_held"] == 40
    assert res["classes_attended"] == 30
    assert res["attendance_pct"] == 75.0

def test_get_attendance_all_courses():
    res = get_attendance("S1001")
    assert res["status"] == "ok"
    assert len(res["courses"]) >= 1
    assert res["overall_attendance_pct"] > 0

def test_get_attendance_invalid_student():
    res = get_attendance("S9999_NONEXISTENT", "CO201")
    assert res["status"] == "error"
    assert "not found" in res["error"].lower()

def test_check_exam_eligibility_exact_threshold():
    # S1001 attendance is 75.0% -> meets mandatory 75.0% cutoff
    res = check_exam_eligibility("S1001", "CO201", has_medical_cert=False, as_of_date="2024-10-01")
    assert res["status"] == "ok"
    assert res["result"] == "ELIGIBLE"
    assert res["attendance_pct"] == 75.0
    assert len(res["applied_rules"]) >= 1
    assert res["applied_rules"][0]["rule_id"] == "ATT-MIN-01"

def test_check_exam_eligibility_one_class_below_threshold():
    # S1002 has 29/40 = 72.5% in CO201
    # Without medical certificate: DETAINED
    res_no_med = check_exam_eligibility("S1002", "CO201", has_medical_cert=False, as_of_date="2024-10-01")
    assert res_no_med["result"] == "DETAINED"

    # With medical certificate (pre-2026): meets 65% condonation threshold -> ELIGIBLE_WITH_CONDONATION
    res_med = check_exam_eligibility("S1002", "CO201", has_medical_cert=True, as_of_date="2024-10-01")
    assert res_med["result"] == "ELIGIBLE_WITH_CONDONATION"
    assert any(r["rule_id"] == "ATT-COND-MED" for r in res_med["applied_rules"])

def test_check_exam_eligibility_amended_condonation_threshold():
    # S1003 has 26/40 = 65.0% in CO201
    # Date 2024-10-01: Rule ATT-COND-MED is active (threshold 65.0%) -> ELIGIBLE_WITH_CONDONATION
    res_2024 = check_exam_eligibility("S1003", "CO201", has_medical_cert=True, as_of_date="2024-10-01")
    assert res_2024["result"] == "ELIGIBLE_WITH_CONDONATION"

    # Date 2026-09-01: DTU-SYN-AMEND-2026 takes effect (threshold raised to 70.0%)
    # 65.0% is below 70.0% -> DETAINED!
    res_2026 = check_exam_eligibility("S1003", "CO201", has_medical_cert=True, as_of_date="2026-09-01")
    assert res_2026["result"] == "DETAINED"
    assert any(r["rule_id"] == "ATT-COND-MED-2026" for r in res_2026["applied_rules"])

def test_compute_cws_attendance_marks_tiers():
    # S1001 (75.0%): Exactly 75% cut-off earns 0 marks per DTU-CIR-ATT-2024 Section 2
    res_75 = compute_cws_attendance_marks("S1001", "CO201")
    assert res_75["cws_attendance_marks"] == 0

    # S1004 has 32/40 = 80.0% -> 76-80% tier awards 1 mark
    res_80 = compute_cws_attendance_marks("S1004", "CO201")
    assert res_80["cws_attendance_marks"] == 1
    assert any(r["rule_id"] == "CWS-ATT-1" for r in res_80["applied_rules"])

    # S1005 has 34/40 = 85.0% -> 81-85% tier awards 2 marks
    res_85 = compute_cws_attendance_marks("S1005", "CO201")
    assert res_85["cws_attendance_marks"] == 2
    assert any(r["rule_id"] == "CWS-ATT-2" for r in res_85["applied_rules"])

    # S1008 has 36/40 = 90.0% in IT201 -> 86-90% tier awards 3 marks
    res_90 = compute_cws_attendance_marks("S1008", "IT201")
    assert res_90["cws_attendance_marks"] == 3
    assert any(r["rule_id"] == "CWS-ATT-3" for r in res_90["applied_rules"])

    # S1014 has 37/40 = 92.5% in IT201 -> 91-95% tier awards 4 marks
    res_92 = compute_cws_attendance_marks("S1014", "IT201")
    assert res_92["cws_attendance_marks"] == 4
    assert any(r["rule_id"] == "CWS-ATT-4" for r in res_92["applied_rules"])

def test_get_academic_summary():
    res = get_academic_summary("S1001")
    assert res["status"] == "ok"
    assert res["full_name"] in ["Aarav Mehta", "Aarav Sharma"]
    assert res["cgpa"] >= 8.1
    assert res["earned_credits"] > 0
    assert len(res["results_history"]) >= 1

def test_check_promotion_eligibility():
    # S1006 has 4 active backlogs, current_semester = 5 (or entering sem 5)
    # Under PROMO-MAX-BACKLOG, max allowed is 4
    res = check_promotion_eligibility("S1006", target_semester=5)
    assert res["status"] == "ok"
    assert res["result"] == "ELIGIBLE"
    assert any(r["rule_id"] == "PROMO-MAX-BACKLOG" for r in res["applied_rules"])

def test_check_supplementary_eligibility():
    # S1004 has result 'FAIL' in CO201 -> ELIGIBLE
    res_fail = check_supplementary_eligibility("S1004", "CO201")
    assert res_fail["result"] == "ELIGIBLE"
    assert res_fail["prior_result"] == "FAIL"

    # S1007 has result 'DETAINED' in CO201 -> NOT_ELIGIBLE (must repeat course)
    res_detained = check_supplementary_eligibility("S1007", "CO201")
    assert res_detained["result"] == "NOT_ELIGIBLE"
    assert "barred" in res_detained["explanation"].lower() or "repeat" in res_detained["explanation"].lower()

    # S1001 has result 'PASS' in CO201 -> NOT_ELIGIBLE
    res_pass = check_supplementary_eligibility("S1001", "CO201")
    assert res_pass["result"] == "NOT_ELIGIBLE"

def test_evaluate_what_if_supplementary():
    # S1004 failed CO201
    # If student passes supplementary, active backlogs become 0
    res = evaluate_what_if_supplementary("S1004", "CO201", anticipated_total_marks=55, placement_cutoff_cgpa=6.0)
    assert res["status"] == "ok"
    assert res["result"] in ["ELIGIBLE_FOR_PLACEMENT", "NOT_ELIGIBLE_FOR_PLACEMENT"]
    assert len(res["assumptions"]) == 3
    assert res["simulated_backlogs"] == 0

    # S1007 was DETAINED -> Cannot even appear for supplementary
    res_det = evaluate_what_if_supplementary("S1007", "CO201")
    assert res_det["result"] == "INELIGIBLE_FOR_SUPPLEMENTARY"

def test_tool_registry_and_schemas():
    assert "get_attendance" in TOOL_REGISTRY
    assert "check_exam_eligibility" in TOOL_REGISTRY
    assert "compute_cws_attendance_marks" in TOOL_REGISTRY
    assert "get_academic_summary" in TOOL_REGISTRY
    assert "check_promotion_eligibility" in TOOL_REGISTRY
    assert "check_supplementary_eligibility" in TOOL_REGISTRY
    assert "evaluate_what_if_supplementary" in TOOL_REGISTRY

    schemas = get_tool_schemas()
    assert len(schemas) == 7
    for s in schemas:
        assert "name" in s
        assert "description" in s
        assert "parameters" in s
