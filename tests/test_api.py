"""
Integration Tests for FastAPI Endpoints (Section 6 Contract & R11 Live Ingest)
"""

import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert data["api"] == "ready"
    assert data["sqlite"] == "connected"
    assert data["vector_store"] == "connected"
    assert data["mock_mode"] is True

def test_ask_policy_endpoint():
    payload = {
        "question": "What is the minimum attendance required to appear for end-semester exams?",
        "as_of_date": "2026-10-23"
    }
    res = client.post("/ask", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "trace_id" in data
    assert data["answer_type"] == "retrieved_fact"
    assert len(data["citations"]) >= 1
    assert "75" in data["answer"]

def test_ask_personal_endpoint_with_header():
    payload = {
        "question": "What is my attendance in CO201?",
        "as_of_date": "2026-10-23"
    }
    headers = {"X-Student-Id": "S1001"}
    res = client.post("/ask", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer_type"] == "calculated"
    assert len(data["tools_invoked"]) >= 1
    assert data["tools_invoked"][0]["tool"] == "get_attendance"
    assert "75.0" in data["answer"]

def test_ask_personal_endpoint_refusal_no_header():
    payload = {
        "question": "What is my attendance in CO201?",
        "as_of_date": "2026-10-23"
    }
    res = client.post("/ask", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["answer_type"] == "refused"

def test_ask_foreign_student_refusal():
    payload = {
        "question": "What is S1002's attendance in CO201?",
        "as_of_date": "2026-10-23"
    }
    headers = {"X-Student-Id": "S1001"}
    res = client.post("/ask", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer_type"] == "refused"

def test_ask_unanswerable_endpoint():
    payload = {
        "question": "What is the scholarship for studying in Antarctica?",
        "as_of_date": "2026-10-23"
    }
    res = client.post("/ask", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["answer_type"] == "not_found"
    assert "I could not find this information in the authorised university sources." in data["answer"]

def test_audit_endpoint():
    # First ask a question to create a trace
    ask_res = client.post("/ask", json={"question": "What is the fee for B.Tech?"})
    assert ask_res.status_code == 200
    trace_id = ask_res.json()["trace_id"]

    audit_res = client.get(f"/audit/{trace_id}")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["trace_id"] == trace_id
    assert "question_text" in audit_data
    assert "sources_retrieved" in audit_data

def test_sources_endpoint():
    res = client.get("/sources")
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) >= 5
    assert any(s["doc_id"] == "DTU-ORD-2024" for s in sources)

def test_admin_load_students():
    res = client.post("/admin/load-students?directory=data/test_students")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["records_loaded"] > 0

def test_live_ingest_and_immediate_retrieval():
    # Test R11: Live document ingestion without code change or restart
    doc_content = (
        "DELHI TECHNOLOGICAL UNIVERSITY\n"
        "OFFICE OF THE DEAN STUDENT WELFARE\n"
        "Ref: DTU/DSW/2026/SPORTS-01\n"
        "NOTIFICATION: ANNUAL INTER-COLLEGE SPORTS ADVISORY 2026\n"
        "Clause 1. Sports Participation Quota:\n"
        "Students representing the university in national athletics tournaments receive "
        "a special sports attendance credit waiver of up to 15.0% by DSW."
    )
    metadata = {
        "doc_id": "DTU-NOTIF-SPORTS-2026",
        "title": "Annual Inter-College Sports Advisory 2026",
        "issuer": "Office of the Dean Student Welfare",
        "authority_level": 2,
        "doc_type": "circular",
        "version": "1.0",
        "effective_from": "2026-08-01",
        "effective_to": "",
        "supersedes": "DTU-ORD-2024#R.1(B).22",
        "scope_programmes": "ALL",
        "scope_batches": "ALL",
        "provenance": "Judge Live Testing",
        "synthetic": "Y"
    }

    files = {
        "file": ("DTU-NOTIF-SPORTS-2026.txt", io.BytesIO(doc_content.encode("utf-8")), "text/plain")
    }
    data = {
        "metadata": json.dumps(metadata)
    }

    # 1. Ingest via POST /ingest
    ingest_res = client.post("/ingest", files=files, data=data)
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.json()
    assert ingest_data["doc_id"] == "DTU-NOTIF-SPORTS-2026"
    assert ingest_data["chunks_indexed"] >= 1

    # 2. Immediately query through POST /ask to verify live usability
    ask_payload = {
        "question": "What is the sports attendance credit waiver by DSW?",
        "as_of_date": "2026-09-01"
    }
    ask_res = client.post("/ask", json=ask_payload)
    assert ask_res.status_code == 200
    answer_data = ask_res.json()
    assert answer_data["answer_type"] == "retrieved_fact"
    assert any(c["doc_id"] == "DTU-NOTIF-SPORTS-2026" for c in answer_data["citations"])
    assert "15.0%" in answer_data["answer"] or "sports" in answer_data["answer"].lower()

    # Cleanup live test file and register
    test_file_path = Path("data/documents/DTU-NOTIF-SPORTS-2026.txt")
    if test_file_path.exists():
        test_file_path.unlink()
    # Remove from CSV
    reg_path = Path("data/source_register.csv")
    if reg_path.exists():
        import csv
        with open(reg_path, "r", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("doc_id") != "DTU-NOTIF-SPORTS-2026"]
        if rows:
            with open(reg_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
