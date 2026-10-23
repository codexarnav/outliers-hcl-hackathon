"""
Unit Tests for Retrieval Engine (Sparse FTS5 & Hybrid Search)
"""

import pytest
from core.retrieval import search_sparse, hybrid_search, index_chunks, get_connection, init_fts_table

@pytest.fixture(autouse=True)
def ensure_indexed_corpus():
    """Ensure test corpus is indexed in SQLite FTS5 for isolated test runs (Comment 7)."""
    conn = get_connection()
    init_fts_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chunks_fts")
    count = cur.fetchone()[0]
    conn.close()

    if count == 0:
        sample_chunks = [
            {
                "chunk_id": "DTU-ORD-2024_P18_0",
                "doc_id": "DTU-ORD-2024",
                "title": "B.Tech Ordinance 2024",
                "section": "Clause R.1(B).22",
                "page": 18,
                "text": "Every student must maintain a minimum attendance of 75.0% of total classes held to be eligible for End-Term Examinations.",
                "authority_level": 1,
                "effective_from": "2024-07-01",
                "supersedes": "DTU-ORD-2021",
                "scope_programmes": "ALL",
                "scope_batches": "2024+",
                "provenance": "https://dtu.ac.in"
            },
            {
                "chunk_id": "DTU-CIR-ATT-2024_P1_0",
                "doc_id": "DTU-CIR-ATT-2024",
                "title": "Circular: Strict Compliance of Attendance Norms",
                "section": "Section 1",
                "page": 1,
                "text": "Mandatory 75% attendance requirement for all courses. Medical condonation threshold up to 10% (down to 65.0%).",
                "authority_level": 2,
                "effective_from": "2024-07-15",
                "scope_programmes": "ALL",
                "scope_batches": "ALL",
                "provenance": "https://dtu.ac.in"
            },
            {
                "chunk_id": "DTU-CIR-EXAM-SUPP_P1_0",
                "doc_id": "DTU-CIR-EXAM-SUPP",
                "title": "Notification: Guidelines for Supplementary and Make-up Examinations",
                "section": "Clause R.1(B).23",
                "page": 1,
                "text": "Make-up examination for students absent due to certified medical hospitalization or extraordinary grounds.",
                "authority_level": 2,
                "effective_from": "2024-08-01",
                "scope_programmes": "ALL",
                "scope_batches": "ALL",
                "provenance": "https://dtu.ac.in"
            },
            {
                "chunk_id": "DTU-NOTIF-FEE-2024_P1_0",
                "doc_id": "DTU-NOTIF-FEE-2024",
                "title": "Annual Academic Fee Structure for B.Tech Programmes (2024-25)",
                "section": "Fee Schedule",
                "page": 1,
                "text": "Annual academic tuition fee and facility fee structure for B.Tech students. Total annual fee Rs 2,16,000.",
                "authority_level": 2,
                "effective_from": "2024-06-20",
                "scope_programmes": "ALL",
                "scope_batches": "ALL",
                "provenance": "https://dtu.ac.in"
            }
        ]
        index_chunks(sample_chunks)

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

def test_index_chunks_atomic_replacement():
    """Verify that index_chunks replaces entries without deleting existing chunks on preparation (Comment 13)."""
    initial_chunks = [
        {
            "chunk_id": "TEST-DOC_P1_1",
            "doc_id": "TEST-DOC",
            "title": "Test Document",
            "section": "Sec 1",
            "page": 1,
            "text": "Initial test chunk 1 about robotics scholarship.",
            "authority_level": 2,
            "effective_from": "2024-01-01"
        },
        {
            "chunk_id": "TEST-DOC_P1_2",
            "doc_id": "TEST-DOC",
            "title": "Test Document",
            "section": "Sec 2",
            "page": 1,
            "text": "Initial test chunk 2 about robotics laboratory.",
            "authority_level": 2,
            "effective_from": "2024-01-01"
        }
    ]
    index_chunks(initial_chunks)

    res = search_sparse("robotics scholarship", top_k=5)
    assert any(r["chunk_id"] == "TEST-DOC_P1_1" for r in res)

    # Re-index with only chunk 1 updated (shortened document)
    updated_chunks = [
        {
            "chunk_id": "TEST-DOC_P1_1",
            "doc_id": "TEST-DOC",
            "title": "Test Document Updated",
            "section": "Sec 1",
            "page": 1,
            "text": "Updated test chunk 1 about robotics fellowship.",
            "authority_level": 2,
            "effective_from": "2024-01-01"
        }
    ]
    index_chunks(updated_chunks)

    res_updated = search_sparse("robotics fellowship", top_k=5)
    assert any(r["chunk_id"] == "TEST-DOC_P1_1" for r in res_updated)

    # Obsolete chunk 2 should be gone from search
    res_obsolete = search_sparse("robotics laboratory", top_k=5)
    assert not any(r["chunk_id"] == "TEST-DOC_P1_2" for r in res_obsolete)
