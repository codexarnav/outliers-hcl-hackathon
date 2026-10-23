"""
FastAPI Application Entrypoint
AI-Powered University Student Services Assistant
Delhi Technological University (DTU)
"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_db, get_connection
from api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure database schema is initialized
    print(f"[*] Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"[*] Operational Mode: MOCK_LLM={settings.MOCK_LLM}")
    init_db()

    # Findings #6 & #7: Auto-seed student data and index documents on fresh startup / docker mounts
    conn = get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM students")
        student_count = cur.fetchone()[0]
        if student_count == 0:
            print("[*] Students table is empty. Auto-seeding test student data...")
            from scripts.load_students import load_directory
            load_directory(conn, Path("data/test_students"))

        from core.retrieval import init_fts_table
        init_fts_table(conn)
        cur = conn.execute("SELECT COUNT(*) FROM chunks_fts")
        chunk_count = cur.fetchone()[0]
        if chunk_count == 0:
            print("[*] Chunks FTS index is empty. Auto-indexing bundled documents...")
            from core.chunking import chunk_all_documents
            from core.retrieval import index_chunks
            chunks = chunk_all_documents()
            if chunks:
                indexed_count = index_chunks(chunks)
                print(f"[*] Successfully indexed {indexed_count} chunks.")
    except Exception as e:
        print(f"[WARN] Startup auto-initialization warning: {e}")
    finally:
        conn.close()

    yield
    print("[*] Shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Deterministic, grounded academic services assistant for Delhi Technological University (DTU).",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes matching Section 6 Contract
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
