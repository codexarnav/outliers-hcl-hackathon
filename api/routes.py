"""
FastAPI Routes implementing Section 6 Contract
- POST /ask
- POST /ingest (R11 Live Ingestion)
- GET /health
- GET /audit/{trace_id}
- GET /sources
- POST /admin/load-students
"""

import os
import csv
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Header, UploadFile, File, Form, HTTPException, Query
from pydantic import ValidationError

from api.models import (
    AskRequest,
    AskResponse,
    IngestResponse,
    HealthResponse,
    AuditRecordResponse,
    SourceRegisterRow
)
from graph.workflow import process_question
from core.database import get_connection, init_db
from core.config import settings
from core.chunking import chunk_pdf, chunk_text_file
from core.retrieval import index_chunks, get_chroma_collection
from scripts.load_students import load_directory, load_table_from_csv

router = APIRouter()

DOCUMENTS_DIR = Path(settings.DOCUMENTS_DIR)
SOURCE_REGISTER_PATH = Path(settings.SOURCE_REGISTER_PATH)

@router.post("/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,
    x_student_id: Optional[str] = Header(None, alias="X-Student-Id")
):
    """
    Primary Question-Answering Endpoint (Section 6.1).
    Accepts question, optional as_of_date, and optional authenticated student identity header.
    """
    res = process_question(
        question=req.question,
        as_of_date=req.as_of_date,
        student_id=x_student_id
    )
    return res

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    metadata: str = Form(..., description="JSON string matching Annex B Source Register schema")
):
    """
    Live Document Ingestion Endpoint (R11).
    Accepts PDF/TXT file and Annex B metadata. Indexes into ChromaDB & SQLite FTS5 immediately.
    """
    try:
        meta_dict = json.loads(metadata)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON metadata: {e}")

    # Validate required Annex B fields
    required_fields = ["doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from"]
    for f in required_fields:
        if f not in meta_dict:
            raise HTTPException(status_code=400, detail=f"Missing required metadata field: '{f}'")

    doc_id = meta_dict["doc_id"]
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    # Determine file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in (".pdf", ".txt"):
        file_ext = ".pdf"

    save_path = DOCUMENTS_DIR / f"{doc_id}{file_ext}"

    # Save uploaded file
    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    # Append to source_register.csv if not already present
    os.makedirs(SOURCE_REGISTER_PATH.parent, exist_ok=True)
    existing_rows = []
    if SOURCE_REGISTER_PATH.exists():
        with open(SOURCE_REGISTER_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)

    # Check if doc_id exists; replace or append
    headers = [
        "doc_id", "title", "issuer", "authority_level", "doc_type", "version",
        "effective_from", "effective_to", "supersedes", "scope_programmes",
        "scope_batches", "provenance", "retrieved_on", "synthetic"
    ]

    new_row = {
        "doc_id": doc_id,
        "title": meta_dict.get("title", ""),
        "issuer": meta_dict.get("issuer", ""),
        "authority_level": str(meta_dict.get("authority_level", 1)),
        "doc_type": meta_dict.get("doc_type", "regulation"),
        "version": meta_dict.get("version", "1.0"),
        "effective_from": meta_dict.get("effective_from", ""),
        "effective_to": meta_dict.get("effective_to", ""),
        "supersedes": meta_dict.get("supersedes", ""),
        "scope_programmes": meta_dict.get("scope_programmes", "ALL"),
        "scope_batches": meta_dict.get("scope_batches", "ALL"),
        "provenance": meta_dict.get("provenance", "Live Ingest"),
        "retrieved_on": meta_dict.get("retrieved_on", "2026-10-23"),
        "synthetic": meta_dict.get("synthetic", "N")
    }

    updated_rows = [r for r in existing_rows if r.get("doc_id") != doc_id]
    updated_rows.append(new_row)

    with open(SOURCE_REGISTER_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(updated_rows)

    # Chunk the newly ingested document
    if file_ext == ".pdf":
        chunks = chunk_pdf(save_path, new_row)
    else:
        chunks = chunk_text_file(save_path, new_row)

    # Index into ChromaDB and SQLite FTS5 immediately
    indexed_count = index_chunks(chunks)

    return {
        "doc_id": doc_id,
        "chunks_indexed": indexed_count,
        "status": "ok"
    }

@router.get("/health", response_model=HealthResponse)
def health_check():
    """System Health and Readiness Verification."""
    # Check SQLite
    sqlite_status = "connected"
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        sqlite_status = "error"

    # Check Vector Store
    vector_status = "connected"
    try:
        col = get_chroma_collection()
        _ = col.count()
    except Exception:
        vector_status = "error"

    llm_status = "ready"

    return {
        "status": "ok" if sqlite_status == "connected" and vector_status == "connected" else "degraded",
        "api": "ready",
        "vector_store": vector_status,
        "sqlite": sqlite_status,
        "llm": llm_status,
        "mock_mode": settings.MOCK_LLM
    }

@router.get("/audit/{trace_id}", response_model=AuditRecordResponse)
def get_audit_record(trace_id: str):
    """Retrieves full audit log entry matching Annex D format."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM audit_log WHERE trace_id = ?", (trace_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Audit trace '{trace_id}' not found.")

        d = dict(row)
        return {
            "trace_id": d["trace_id"],
            "timestamp": d["timestamp"],
            "student_id": d.get("student_id"),
            "question_category": d["question_category"],
            "question_text": d["question_text"],
            "sources_retrieved": json.loads(d["sources_retrieved"]) if d.get("sources_retrieved") else [],
            "precedence_decision": d.get("precedence_decision"),
            "tools_invoked": json.loads(d["tools_invoked"]) if d.get("tools_invoked") else [],
            "applied_rules": json.loads(d["applied_rules"]) if d.get("applied_rules") else [],
            "conflicts_detected": json.loads(d["conflicts_detected"]) if d.get("conflicts_detected") else [],
            "answer_type": d["answer_type"],
            "model": d["model"],
            "llm_calls": d["llm_calls"],
            "tokens": d["tokens"],
            "latency_ms": d["latency_ms"]
        }
    finally:
        conn.close()

@router.get("/sources", response_model=List[SourceRegisterRow])
def get_source_register():
    """Returns all rows from the Source Register (Annex B)."""
    if not SOURCE_REGISTER_PATH.exists():
        return []

    with open(SOURCE_REGISTER_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    result = []
    for r in rows:
        try:
            result.append(SourceRegisterRow(
                doc_id=r["doc_id"],
                title=r["title"],
                issuer=r["issuer"],
                authority_level=int(r["authority_level"]),
                doc_type=r["doc_type"],
                version=r["version"],
                effective_from=r["effective_from"],
                effective_to=r.get("effective_to", ""),
                supersedes=r.get("supersedes", ""),
                scope_programmes=r.get("scope_programmes", "ALL"),
                scope_batches=r.get("scope_batches", "ALL"),
                provenance=r.get("provenance", ""),
                retrieved_on=r.get("retrieved_on", ""),
                synthetic=r.get("synthetic", "N")
            ))
        except ValidationError:
            pass

    return result

@router.post("/admin/load-students")
def admin_load_students(
    directory: Optional[str] = Query(None, description="Directory containing student CSVs")
):
    """
    Admin Endpoint for Loading Judge Test Data (Section 4.2).
    """
    target_dir = Path(directory) if directory else Path("data/test_students")
    if not target_dir.exists():
        raise HTTPException(status_code=400, detail=f"Directory '{target_dir}' does not exist.")

    init_db()
    conn = get_connection()
    try:
        count = load_directory(conn, target_dir)
        return {
            "status": "ok",
            "records_loaded": count,
            "directory": str(target_dir)
        }
    finally:
        conn.close()
