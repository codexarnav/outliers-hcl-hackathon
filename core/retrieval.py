"""
Hybrid Retrieval Engine
Combines SQLite FTS5 BM25 (sparse) with ChromaDB (dense), merges ranks using
Reciprocal Rank Fusion (RRF), and applies Cross-Encoder reranking (Annex B & PS §2).
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import settings
from core.database import get_connection

CHROMA_DIR = Path(settings.CHROMA_PERSIST_DIR)

_chroma_client = None
_chroma_collection = None
_embedding_fn = None
_cross_encoder = None

def get_embedding_function():
    """Initializes sentence-transformers embedding function using configured model."""
    global _embedding_fn
    if _embedding_fn is None and not settings.MOCK_LLM:
        try:
            from chromadb.utils import embedding_functions
            _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.EMBEDDING_MODEL
            )
        except Exception:
            _embedding_fn = False
    return _embedding_fn if _embedding_fn is not False else None

def get_cross_encoder():
    """Initializes Cross-Encoder model using configured model name."""
    global _cross_encoder
    if _cross_encoder is None and not settings.MOCK_LLM:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(settings.CROSS_ENCODER_MODEL)
        except Exception:
            _cross_encoder = False
    return _cross_encoder if _cross_encoder is not False else None

def get_chroma_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=ChromaSettings(anonymized_telemetry=False))
        emb_fn = get_embedding_function()
        kwargs = {
            "name": "dtu_academic_docs",
            "metadata": {"description": "Delhi Technological University Regulations and Circulars"}
        }
        if emb_fn is not None:
            kwargs["embedding_function"] = emb_fn
        _chroma_collection = _chroma_client.get_or_create_collection(**kwargs)
    return _chroma_collection

def init_fts_table(conn: sqlite3.Connection):
    with conn:
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            doc_id,
            title,
            section,
            page UNINDEXED,
            text,
            authority_level UNINDEXED,
            effective_from UNINDEXED,
            effective_to UNINDEXED,
            supersedes UNINDEXED,
            scope_programmes UNINDEXED,
            scope_batches UNINDEXED
        );
        """)

def index_chunks(chunks: List[Dict[str, Any]]):
    if not chunks:
        return 0

    conn = get_connection()
    init_fts_table(conn)

    # 1. Index into SQLite FTS5 (purging obsolete chunks for replaced documents - Comment 6)
    doc_ids = list({c["doc_id"] for c in chunks if c.get("doc_id")})
    with conn:
        for doc_id in doc_ids:
            conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))

        for c in chunks:
            conn.execute("""
            INSERT INTO chunks_fts (
                chunk_id, doc_id, title, section, page, text,
                authority_level, effective_from, effective_to,
                supersedes, scope_programmes, scope_batches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c["chunk_id"], c["doc_id"], c.get("title", ""), c.get("section", ""),
                str(c.get("page", 1)), c["text"], str(c.get("authority_level", 1)),
                c.get("effective_from", ""), c.get("effective_to", ""),
                c.get("supersedes", ""), c.get("scope_programmes", "ALL"),
                c.get("scope_batches", "ALL")
            ))

    conn.close()

    # 2. Index into ChromaDB
    collection = get_chroma_collection()
    for doc_id in doc_ids:
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [{
        "doc_id": c["doc_id"],
        "title": c.get("title", ""),
        "section": c.get("section", ""),
        "page": int(c.get("page", 1)),
        "authority_level": int(c.get("authority_level", 1)),
        "effective_from": c.get("effective_from", ""),
        "effective_to": c.get("effective_to", ""),
        "supersedes": c.get("supersedes", ""),
        "scope_programmes": c.get("scope_programmes", "ALL"),
        "scope_batches": c.get("scope_batches", "ALL"),
        "provenance": c.get("provenance", ""),
    } for c in chunks]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    return len(chunks)

def search_sparse(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Performs SQLite FTS5 BM25 search over ingested chunks."""
    conn = get_connection()
    init_fts_table(conn)

    sanitized = "".join(ch for ch in query if ch.isalnum() or ch.isspace()).strip()
    if not sanitized:
        conn.close()
        return []

    fts_query = " OR ".join(sanitized.split())

    sql = """
    SELECT chunk_id, doc_id, title, section, CAST(page AS INTEGER) AS page, text,
           CAST(authority_level AS INTEGER) AS authority_level,
           effective_from, effective_to, supersedes, scope_programmes, scope_batches,
           bm25(chunks_fts) AS bm25_score
    FROM chunks_fts
    WHERE chunks_fts MATCH ?
    ORDER BY bm25_score
    LIMIT ?;
    """

    cursor = conn.cursor()
    try:
        cursor.execute(sql, (fts_query, top_k))
        rows = [dict(r) for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    return rows

def search_dense(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Performs ChromaDB vector search over chunk embeddings."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count())
    )

    chunks = []
    if not results or not results["ids"] or not results["ids"][0]:
        return chunks

    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        chunk_id = results["ids"][0][i]
        dist = results["distances"][0][i] if results.get("distances") else 0.0

        chunks.append({
            "chunk_id": chunk_id,
            "doc_id": meta.get("doc_id"),
            "title": meta.get("title", ""),
            "section": meta.get("section", ""),
            "page": meta.get("page", 1),
            "text": doc,
            "authority_level": meta.get("authority_level", 1),
            "effective_from": meta.get("effective_from", ""),
            "effective_to": meta.get("effective_to", ""),
            "supersedes": meta.get("supersedes", ""),
            "scope_programmes": meta.get("scope_programmes", "ALL"),
            "scope_batches": meta.get("scope_batches", "ALL"),
            "provenance": meta.get("provenance", ""),
            "distance": dist
        })

    return chunks

def rerank_candidates(query: str, candidates: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Reranks candidates using Cross-Encoder model with heuristic keyword boost fallback (Comment 9)."""
    if not candidates:
        return []

    encoder = get_cross_encoder()
    if encoder:
        try:
            pairs = [[query, c["text"]] for c in candidates]
            scores = encoder.predict(pairs)
            for c, s in zip(candidates, scores):
                c["score"] = round(float(s), 4)
            return sorted(candidates, key=lambda x: x["score"], reverse=True)[:top_k]
        except Exception:
            pass

    # Heuristic scoring fallback for MOCK_LLM or offline environments
    q_lower = query.lower()
    for item in candidates:
        text_lower = item["text"].lower()
        score = item.get("score", 0.0)

        # Boost for exact clause citations
        for term in ["r.1(b).22", "attendance", "supplementary", "cws", "fee", "make-up", "fail"]:
            if term in q_lower and term in text_lower:
                score += 0.05
        
        # Boost for primary regulation level
        if item.get("authority_level") == 1:
            score += 0.01

        item["score"] = round(score, 4)

    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:top_k]

def hybrid_search(query: str, top_k: int = 5, rrf_k: int = 60) -> List[Dict[str, Any]]:
    """
    Executes Hybrid Retrieval combining Dense (ChromaDB) and Sparse (SQLite FTS5),
    fuses ranks via Reciprocal Rank Fusion (RRF), and applies Cross-Encoder reranking.
    """
    sparse_results = search_sparse(query, top_k=top_k * 2)
    dense_results = search_dense(query, top_k=top_k * 2)

    rrf_scores: Dict[str, float] = {}
    chunk_map: Dict[str, Dict[str, Any]] = {}

    for rank, item in enumerate(sparse_results):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank + 1))
        chunk_map[cid] = item

    for rank, item in enumerate(dense_results):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank + 1))
        if cid not in chunk_map:
            chunk_map[cid] = item

    if not rrf_scores:
        return []

    sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    candidate_list = []
    for cid, score in sorted_candidates[:15]:
        item = chunk_map[cid]
        item["score"] = round(score, 4)
        candidate_list.append(item)

    return rerank_candidates(query, candidate_list, top_k=top_k)
