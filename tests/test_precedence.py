"""
Unit Tests for Annex A Source Precedence Policy
"""

import pytest
from core.precedence import resolve_precedence, is_scope_applicable

def test_annex_a_worked_example():
    test_chunks = [
        {"doc_id": "ACAD-REG-2024", "section": "Clause 7.2", "authority_level": 1, "effective_from": "2024-07-01", "supersedes": "", "text": "Minimum attendance is 75%."},
        {"doc_id": "ACAD-2026-08", "section": "Section 1", "authority_level": 2, "effective_from": "2026-08-01", "supersedes": "ACAD-REG-2024#Clause 7.2", "text": "Minimum attendance is 80%."},
        {"doc_id": "DEPT-FAQ", "section": "Q3", "authority_level": 4, "effective_from": "2026-09-15", "supersedes": "", "text": "65% is enough."}
    ]
    res = resolve_precedence(test_chunks, as_of_date="2026-10-06")
    assert res["winning_chunk"]["doc_id"] == "ACAD-2026-08"
    assert "explicitly supersedes" in res["precedence_decision"]
    assert res["answer_type"] == "retrieved_fact"

def test_normalized_clause_supersession():
    """Verify DTU-ORD-2024#Clause R.1(B).22 supersedes section named 'R.1(B).22' (Comment 1)."""
    test_chunks = [
        {
            "doc_id": "DTU-ORD-2024",
            "section": "R.1(B).22",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "supersedes": "",
            "text": "Medical condonation allowed up to 10% (down to 65.0%)."
        },
        {
            "doc_id": "DTU-SYN-AMEND-2026",
            "section": "Section 1",
            "authority_level": 2,
            "effective_from": "2026-08-01",
            "supersedes": "DTU-ORD-2024#Clause R.1(B).22",
            "text": "Medical condonation threshold amended to 70.0%."
        }
    ]
    res = resolve_precedence(test_chunks, as_of_date="2026-10-23")
    assert res["winning_chunk"]["doc_id"] == "DTU-SYN-AMEND-2026"
    assert len(res["superseded_chunks"]) == 1
    assert res["superseded_chunks"][0]["doc_id"] == "DTU-ORD-2024"

def test_future_circular_excluded():
    test_chunks = [
        {"doc_id": "DTU-ORD-2024", "section": "R.1(B).22", "authority_level": 1, "effective_from": "2024-07-01", "supersedes": "", "text": "75% attendance."},
        {"doc_id": "DTU-SYN-AMEND-2026", "section": "Sec 1", "authority_level": 2, "effective_from": "2026-08-01", "supersedes": "DTU-ORD-2024", "text": "70% attendance."}
    ]
    # Before amendment is effective:
    res = resolve_precedence(test_chunks, as_of_date="2025-05-01")
    assert res["winning_chunk"]["doc_id"] == "DTU-ORD-2024"
    assert len(res["upcoming_chunks"]) == 1
    assert res["upcoming_chunks"][0]["doc_id"] == "DTU-SYN-AMEND-2026"

def test_scope_applicability():
    assert is_scope_applicable("ALL", "2023")
    assert is_scope_applicable("2023+", "2024")
    assert is_scope_applicable("2023+", "2023")
    assert not is_scope_applicable("2023+", "2022")
    assert is_scope_applicable("B.Tech CSE,B.Tech IT", "B.Tech CSE")
    assert not is_scope_applicable("B.Tech CSE", "B.Tech ME")

def test_cohort_ordinance_precedence():
    """Verify older cohort retains DTU-ORD-2021 ordinance when evaluating in 2026."""
    test_chunks = [
        {
            "doc_id": "DTU-ORD-2021",
            "section": "Clause R.1(B).22",
            "authority_level": 1,
            "effective_from": "2021-08-01",
            "effective_to": "",
            "scope_batches": "2021,2022,2023",
            "supersedes": "DTU-ORD-2019",
            "text": "2021 Ordinance applies to 2021-2023 cohorts."
        },
        {
            "doc_id": "DTU-ORD-2024",
            "section": "Clause R.1(B).22",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "effective_to": "",
            "scope_batches": "2024+",
            "supersedes": "DTU-ORD-2021",
            "text": "2024 Ordinance applies to 2024+ cohorts."
        }
    ]
    # For a 2023 batch student queried in 2026:
    res_2023 = resolve_precedence(test_chunks, as_of_date="2026-10-23", batch_year="2023")
    assert res_2023["winning_chunk"]["doc_id"] == "DTU-ORD-2021"

    # For a 2024 batch student queried in 2026:
    res_2024 = resolve_precedence(test_chunks, as_of_date="2026-10-23", batch_year="2024")
    assert res_2024["winning_chunk"]["doc_id"] == "DTU-ORD-2024"

def test_general_query_retains_rules():
    """General queries without student context (batch_year='ALL') retain university rules (Comment 10)."""
    test_chunks = [
        {
            "doc_id": "DTU-ORD-2024",
            "section": "Clause R.1(B).22",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "scope_batches": "2024+",
            "text": "Minimum attendance is 75.0% across all programmes."
        }
    ]
    res = resolve_precedence(test_chunks, as_of_date="2026-10-23", batch_year="ALL")
    assert res["winning_chunk"] is not None
    assert res["winning_chunk"]["doc_id"] == "DTU-ORD-2024"

def test_level_5_informational_only():
    """Level 5 sources cannot decide authoritative answers (Comment 4)."""
    test_chunks = [
        {
            "doc_id": "STUDENT-FORUM-POST",
            "section": "General Discussion",
            "authority_level": 5,
            "effective_from": "2026-09-01",
            "text": "Someone told me attendance above 60% might get condoned."
        }
    ]
    res = resolve_precedence(test_chunks, as_of_date="2026-10-23")
    assert res["winning_chunk"] is None
    assert res["answer_type"] == "informational_only"
    assert len(res["informational_chunks"]) == 1

def test_agreeing_sources_no_conflict():
    """Sources with equal authority that agree on policy do NOT flag a conflict (Comment 5)."""
    test_chunks = [
        {"doc_id": "CIRCULAR-DEAN", "section": "Notice 1", "authority_level": 2, "effective_from": "2024-08-01", "text": "Minimum attendance is 75% for exam eligibility."},
        {"doc_id": "CIRCULAR-COE", "section": "Notice 2", "authority_level": 2, "effective_from": "2024-08-01", "text": "Attendance requirement is 75% for admit card issuance."}
    ]
    res = resolve_precedence(test_chunks, as_of_date="2024-09-01")
    assert res["answer_type"] == "retrieved_fact"
    assert len(res["conflicts_detected"]) == 0

def test_unresolved_conflict_detection():
    """Genuine contradiction at same authority and date triggers conflict_flagged."""
    test_chunks = [
        {"doc_id": "CIRCULAR-A", "section": "Clause 1", "authority_level": 2, "effective_from": "2024-08-01", "supersedes": "", "text": "Passing threshold is 40% aggregate marks."},
        {"doc_id": "CIRCULAR-B", "section": "Clause 1", "authority_level": 2, "effective_from": "2024-08-01", "supersedes": "", "text": "Passing threshold is 50% aggregate marks."}
    ]
    res = resolve_precedence(test_chunks, as_of_date="2024-09-01")
    assert res["answer_type"] == "conflict_flagged"
    assert len(res["conflicts_detected"]) == 1

def test_shared_numbers_conflicting_rules():
    """Shared numbers (like Clause 1) do not hide contradictory thresholds (Comment 11)."""
    test_chunks = [
        {
            "doc_id": "DTU-CIR-ATT-A",
            "section": "Clause 1",
            "authority_level": 2,
            "effective_from": "2024-08-01",
            "supersedes": "",
            "text": "Clause 1: Minimum attendance is 75%."
        },
        {
            "doc_id": "DTU-CIR-ATT-B",
            "section": "Clause 1",
            "authority_level": 2,
            "effective_from": "2024-08-01",
            "supersedes": "",
            "text": "Clause 1: Minimum attendance is 80%."
        }
    ]
    res = resolve_precedence(test_chunks, as_of_date="2024-09-01")
    assert res["answer_type"] == "conflict_flagged"
    assert len(res["conflicts_detected"]) == 1
    assert res["conflicts_detected"][0]["doc_a"] == "DTU-CIR-ATT-A"
    assert res["conflicts_detected"][0]["doc_b"] == "DTU-CIR-ATT-B"

def test_clause_supersession_does_not_remove_unrelated_clauses():
    """Target Clause R.1(B).1 must not remove R.1(B).10 or R.1(B).11 (Comment 12)."""
    test_chunks = [
        {
            "doc_id": "DTU-ORD-2024",
            "section": "Clause R.1(B).1: Preamble and Structure of B.Tech Programmes",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "supersedes": "",
            "text": "Old preamble rule."
        },
        {
            "doc_id": "DTU-ORD-2024",
            "section": "Clause R.1(B).10: Academic Registration and Advising",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "supersedes": "",
            "text": "Academic registration rule."
        },
        {
            "doc_id": "DTU-ORD-2024",
            "section": "Clause R.1(B).11: Course Registration and Credit Limits",
            "authority_level": 1,
            "effective_from": "2024-07-01",
            "supersedes": "",
            "text": "Credit limit rule."
        },
        {
            "doc_id": "DTU-AMEND-PREAMBLE",
            "section": "Section 1",
            "authority_level": 2,
            "effective_from": "2026-08-01",
            "supersedes": "DTU-ORD-2024#Clause R.1(B).1",
            "text": "New amended preamble rule."
        }
    ]
    res = resolve_precedence(test_chunks, as_of_date="2026-10-23")
    # Only Clause R.1(B).1 should be superseded
    superseded_sections = [c["section"] for c in res["superseded_chunks"]]
    assert any("R.1(B).1:" in s for s in superseded_sections)
    assert not any("R.1(B).10" in s for s in superseded_sections)
    assert not any("R.1(B).11" in s for s in superseded_sections)

    # Surviving chunks must include R.1(B).10 and R.1(B).11
    surviving_sections = [c["section"] for c in res["applicable_chunks"]]
    assert any("R.1(B).10" in s for s in surviving_sections)
    assert any("R.1(B).11" in s for s in surviving_sections)
