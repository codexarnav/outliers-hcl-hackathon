"""
Unit Tests for LangGraph Workflow & Orchestrator
"""

import pytest
from graph.workflow import process_question
from core.database import get_connection

def test_workflow_policy_fact():
    res = process_question("What is the minimum attendance required to appear for end-semester exams?")
    assert res["answer_type"] == "retrieved_fact"
    assert len(res["citations"]) >= 1
    assert any("DTU-ORD" in c["doc_id"] or "DTU-CIR-ATT" in c["doc_id"] for c in res["citations"])
    assert "75" in res["answer"]

def test_workflow_personal_data_authenticated():
    res = process_question("What is my attendance in CO201?", student_id="S1001")
    assert res["answer_type"] == "calculated"
    assert "75.0" in res["answer"]
    assert any(t["tool"] == "get_attendance" for t in res["tools_invoked"])

def test_workflow_personal_data_unauthenticated_refusal():
    res = process_question("What is my attendance in CO201?", student_id=None)
    assert res["answer_type"] == "refused"
    assert "refused" in res["answer"].lower() or "authentication" in res["answer"].lower()

def test_workflow_foreign_student_refusal():
    # Authenticated as S1001, but asking for S1002
    res = process_question("What is S1002's attendance in CO201?", student_id="S1001")
    assert res["answer_type"] == "refused"
    assert "prohibited" in res["answer"].lower() or "refused" in res["answer"].lower()

def test_workflow_unanswerable_abstention():
    res = process_question("What is the scholarship for studying in Antarctica?")
    assert res["answer_type"] == "not_found"
    assert "I could not find this information in the authorised university sources." in res["answer"]

def test_workflow_what_if_analysis():
    res = process_question("If I pass supplementary in CO201, will I be eligible for placement?", student_id="S1004")
    assert res["answer_type"] == "calculated"
    assert any(t["tool"] == "evaluate_what_if_supplementary" for t in res["tools_invoked"])
    assert len(res["applied_rules"]) >= 1

def test_workflow_audit_log_persisted():
    res = process_question("What is the minimum attendance required for B.Tech?")
    trace_id = res["trace_id"]
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM audit_log WHERE trace_id = ?", (trace_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["trace_id"] == trace_id
        assert row["answer_type"] == "retrieved_fact"
    finally:
        conn.close()
