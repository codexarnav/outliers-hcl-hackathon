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

def test_unresolved_conflict_detection():
    test_chunks = [
        {"doc_id": "CIRCULAR-A", "section": "Clause 1", "authority_level": 2, "effective_from": "2024-08-01", "supersedes": "", "text": "Rule A"},
        {"doc_id": "CIRCULAR-B", "section": "Clause 1", "authority_level": 2, "effective_from": "2024-08-01", "supersedes": "", "text": "Rule B"}
    ]
    res = resolve_precedence(test_chunks, as_of_date="2024-09-01")
    assert res["answer_type"] == "conflict_flagged"
    assert len(res["conflicts_detected"]) == 1
