"""
Database Engine & SQLite Schema Manager
Implements Annex C Fixed Schema (students, courses, attendance, results, rule_registry)
and Annex D Audit Record store (audit_log).
"""

import sqlite3
import os
import sys
from pathlib import Path

# Add project root to sys.path if running directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from core.config import settings
except ImportError:
    class DummySettings:
        SQLITE_PATH = "./data/app.db"
        DATABASE_URL = "sqlite:///./data/app.db"
    settings = DummySettings()

DB_PATH = Path(settings.SQLITE_PATH)

def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    """Initializes all tables per Annex C and Annex D."""
    conn = get_connection()
    with conn:
        # 1. students (Annex C)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            programme TEXT NOT NULL,
            batch_year INTEGER NOT NULL,
            current_semester INTEGER NOT NULL,
            cgpa REAL NOT NULL CHECK(cgpa >= 0.0 AND cgpa <= 10.0),
            active_backlogs INTEGER NOT NULL CHECK(active_backlogs >= 0)
        );
        """)

        # 2. courses (Annex C)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            course_code TEXT PRIMARY KEY,
            course_name TEXT NOT NULL,
            programme TEXT NOT NULL,
            semester INTEGER NOT NULL,
            credits INTEGER NOT NULL CHECK(credits > 0)
        );
        """)

        # 3. attendance (Annex C - Percentage computed dynamically, never stored)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            student_id TEXT NOT NULL,
            course_code TEXT NOT NULL,
            classes_held INTEGER NOT NULL CHECK(classes_held > 0),
            classes_attended INTEGER NOT NULL CHECK(classes_attended >= 0 AND classes_attended <= classes_held),
            PRIMARY KEY (student_id, course_code),
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE
        );
        """)

        # 4. results (Annex C)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            student_id TEXT NOT NULL,
            course_code TEXT NOT NULL,
            exam_session TEXT NOT NULL,
            exam_type TEXT NOT NULL CHECK(exam_type IN ('REGULAR', 'SUPPLEMENTARY', 'MAKEUP')),
            internal_marks INTEGER NOT NULL,
            external_marks INTEGER NOT NULL,
            total_marks INTEGER NOT NULL,
            max_marks INTEGER NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('PASS', 'FAIL', 'ABSENT', 'DETAINED')),
            PRIMARY KEY (student_id, course_code, exam_session, exam_type),
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE
        );
        """)

        # 5. rule_registry (Annex C)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS rule_registry (
            rule_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            parameter TEXT NOT NULL,
            operator TEXT NOT NULL,
            value TEXT NOT NULL,
            scope_programmes TEXT NOT NULL,
            scope_batches TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT NOT NULL,
            source_doc_id TEXT NOT NULL,
            source_section TEXT NOT NULL
        );
        """)

        # 6. audit_log (Annex D)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            trace_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            student_id TEXT,
            question_category TEXT NOT NULL,
            question_text TEXT NOT NULL,
            sources_retrieved TEXT NOT NULL,   -- JSON array string
            precedence_decision TEXT,          -- Annex A resolution summary
            tools_invoked TEXT,                -- JSON array string
            applied_rules TEXT,                -- JSON array string
            conflicts_detected TEXT,           -- JSON array string
            answer_type TEXT NOT NULL,
            model TEXT NOT NULL,
            llm_calls INTEGER NOT NULL,
            tokens INTEGER NOT NULL,
            latency_ms INTEGER NOT NULL
        );
        """)

        # Seed rule_registry if empty
        cur = conn.execute("SELECT COUNT(*) FROM rule_registry")
        if cur.fetchone()[0] == 0:
            seed_sql_path = Path(settings.DATABASE_URL.replace("sqlite:///", "")).parent / "seed_rules.sql"
            if not seed_sql_path.exists():
                seed_sql_path = Path("data/seed_rules.sql")
            if seed_sql_path.exists():
                with open(seed_sql_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                print(f"[OK] Seeded rule_registry from {seed_sql_path}")

    conn.close()
    print("[OK] Initialized database schema successfully.")

if __name__ == "__main__":
    init_db()
