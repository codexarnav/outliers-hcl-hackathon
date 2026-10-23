"""
Unit Tests for Retrieval Engine (Sparse FTS5 & Hybrid Search)
"""

import pytest
from core.retrieval import search_sparse, hybrid_search

def test_sparse_fts_attendance_search():
    res = search_sparse("minimum attendance 75%", top_k=5)
    assert len(res) > 0, "Sparse FTS5 should return results for attendance query"
    doc_ids = [r["doc_id"] for r in res]
    assert any("DTU-ORD" in d or "DTU-CIR-ATT" in d for d in doc_ids)

def test_sparse_fts_make_up_exam():
    res = search_sparse("make-up examination medical", top_k=5)
    assert len(res) > 0
    text_content = " ".join(r["text"] for r in res).lower()
    assert "make-up" in text_content or "medical" in text_content

def test_sparse_fts_fee_schedule():
    res = search_sparse("annual tuition fee", top_k=5)
    assert len(res) > 0
    doc_ids = [r["doc_id"] for r in res]
    assert "DTU-NOTIF-FEE-2024" in doc_ids or "DTU-ORD-2021" in doc_ids
