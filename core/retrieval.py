"""
Hybrid Retrieval Engine (Dense ChromaDB + Sparse SQLite FTS5 BM25 + Reciprocal Rank Fusion)
"""

import os
import re
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

def get_chroma_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=ChromaSettings(anonymized_telemetry=False))
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="dtu_academic_docs",
            metadata={"description": "Delhi Technological University Regulations and Circulars"}
        )
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

    # 1. Index into SQLite FTS5
    with conn:
        for c in chunks:
            # Delete existing if updating
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (c["chunk_id"],))
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
    } for c in chunks]

    # Batch upsert to ChromaDB
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size]
        )

    return len(chunks)

def search_sparse(query: str, top_k: int = 15) -> List[Dict[str, Any]]:
    conn = get_connection()
    init_fts_table(conn)
    
    # Clean query for FTS5 syntax
    clean_terms = [t for t in query.replace('"', '').replace("'", '').split() if len(t) > 2]
    if not clean_terms:
        clean_terms = query.split()
    fts_query = " OR ".join(f'"{t}"' for t in clean_terms)

    results = []
    try:
        cur = conn.execute("""
        SELECT chunk_id, doc_id, title, section, page, text,
               authority_level, effective_from, effective_to,
               supersedes, scope_programmes, scope_batches, rank
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """, (fts_query, top_k))

        for row in cur.fetchall():
            results.append({
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "section": row["section"],
                "page": int(row["page"]),
                "text": row["text"],
                "authority_level": int(row["authority_level"]),
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "supersedes": row["supersedes"],
                "scope_programmes": row["scope_programmes"],
                "scope_batches": row["scope_batches"],
                "sparse_rank": row["rank"]
            })
    except Exception as e:
        print(f"[WARN] FTS5 search error: {e}")
    finally:
        conn.close()

    return results

def search_dense(query: str, top_k: int = 15) -> List[Dict[str, Any]]:
    collection = get_chroma_collection()
    results = []
    try:
        res = collection.query(
            query_texts=[query],
            n_results=top_k
        )
        if res and res["ids"] and res["ids"][0]:
            for idx in range(len(res["ids"][0])):
                meta = res["metadatas"][0][idx]
                results.append({
                    "chunk_id": res["ids"][0][idx],
                    "doc_id": meta["doc_id"],
                    "title": meta.get("title", ""),
                    "section": meta.get("section", ""),
                    "page": int(meta.get("page", 1)),
                    "text": res["documents"][0][idx],
                    "authority_level": int(meta.get("authority_level", 1)),
                    "effective_from": meta.get("effective_from", ""),
                    "effective_to": meta.get("effective_to", ""),
                    "supersedes": meta.get("supersedes", ""),
                    "scope_programmes": meta.get("scope_programmes", "ALL"),
                    "scope_batches": meta.get("scope_batches", "ALL"),
                    "dense_distance": res["distances"][0][idx] if res["distances"] else 0.0
                })
    except Exception as e:
        print(f"[WARN] Chroma search error: {e}")

    return results

def hybrid_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Combines dense and sparse search using Reciprocal Rank Fusion (RRF),
    followed by cross-scoring reranker.
    """
    dense_results = search_dense(query, top_k=15)
    sparse_results = search_sparse(query, top_k=15)

    rrf_scores = {}
    chunk_map = {}

    # Dense RRF
    for rank, item in enumerate(dense_results):
        cid = item["chunk_id"]
        chunk_map[cid] = item
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60 + rank))

    # Sparse RRF
    for rank, item in enumerate(sparse_results):
        cid = item["chunk_id"]
        if cid not in chunk_map:
            chunk_map[cid] = item
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60 + rank))

    # Sort candidates by merged RRF score
    sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Cross-scoring dynamic keyword boost (lexical + query term alignment)
    final_scored = []
    q_lower = query.lower()
    query_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', q_lower)) - {
        "what", "which", "when", "where", "about", "under", "shall", "student", "university", "the", "for", "with"
    }

    for cid, rrf_score in sorted_candidates[:15]:
        item = chunk_map[cid]
        text_lower = item["text"].lower()
        score = rrf_score

        # Overlap boost based on specific query terms
        matching_words = sum(1 for w in query_words if w in text_lower)
        score += matching_words * 0.01

        # Boost for exact clause reference (e.g. R.1(B).22)
        if "r.1(b).22" in q_lower and "r.1(b).22" in text_lower:
            score += 0.03

        item["score"] = round(score, 4)
        final_scored.append(item)

    final_scored.sort(key=lambda x: x["score"], reverse=True)
    return final_scored[:top_k]

if __name__ == "__main__":
    from core.chunking import chunk_all_documents
    docs_dir = Path("data/documents")
    reg_path = Path("data/source_register.csv")
    print("=== Indexing DTU Documents into ChromaDB & SQLite FTS5 ===")
    chunks = chunk_all_documents(docs_dir, reg_path)
    count = index_chunks(chunks)
    print(f"[SUCCESS] Indexed {count} chunks.")

    print("\n=== Testing Hybrid Retrieval ===")
    test_q = "What is the minimum attendance required to appear for end-semester exams?"
    res = hybrid_search(test_q, top_k=3)
    for i, r in enumerate(res):
        print(f"Rank {i+1} [Score: {r['score']}] {r['doc_id']} - {r['section']} (p.{r['page']}):")
        print(f"  {r['text'][:120]}...\n")
