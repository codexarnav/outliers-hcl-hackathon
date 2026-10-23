#!/usr/bin/env python3
"""
Test Student Data Loader (Section 4.2 Mandatory Judge Interface)
Usage:
    python scripts/load_students.py --dir data/test_students/
    python scripts/load_students.py --file data/test_students/students.csv --table students
"""

import os
import sys
import csv
import argparse
import sqlite3
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.database import get_connection, init_db

# Primary keys per table to build non-destructive upserts (avoiding ON DELETE CASCADE)
TABLE_PRIMARY_KEYS = {
    "students": ["student_id"],
    "courses": ["course_code"],
    "attendance": ["student_id", "course_code"],
    "results": ["student_id", "course_code", "exam_session", "exam_type"],
    "rule_registry": ["rule_id"],
}

def load_table_from_csv(conn: sqlite3.Connection, csv_path: Path, table_name: str, commit: bool = True) -> int:
    if not csv_path.exists():
        print(f"[SKIP] File not found: {csv_path}")
        return 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[WARN] Empty CSV file: {csv_path}")
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    
    pks = TABLE_PRIMARY_KEYS.get(table_name, [])
    update_cols = [c for c in columns if c not in pks]

    if pks and update_cols:
        pk_str = ", ".join(pks)
        update_str = ", ".join([f"{col} = excluded.{col}" for col in update_cols])
        sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({pk_str}) DO UPDATE SET {update_str}"
    elif pks:
        pk_str = ", ".join(pks)
        sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({pk_str}) DO NOTHING"
    else:
        sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"

    count = 0
    cursor = conn.cursor()
    for row in rows:
        values = [row[c] for c in columns]
        cursor.execute(sql, values)
        count += 1

    if commit:
        conn.commit()

    print(f"[OK] Loaded {count} rows into '{table_name}' from {csv_path.name}")
    return count

def load_directory(conn: sqlite3.Connection, target_dir: Path):
    table_files = [
        ("courses", target_dir / "courses.csv"),
        ("students", target_dir / "students.csv"),
        ("attendance", target_dir / "attendance.csv"),
        ("results", target_dir / "results.csv"),
        ("rule_registry", target_dir / "rule_registry.csv"),
    ]

    total_loaded = 0
    # Single atomic transaction for entire directory import
    with conn:
        for table_name, file_path in table_files:
            if file_path.exists():
                total_loaded += load_table_from_csv(conn, file_path, table_name, commit=False)
    return total_loaded

def main():
    parser = argparse.ArgumentParser(description="Load Annex C student data into SQLite database")
    parser.add_argument("--dir", type=str, help="Directory containing Annex C CSV files (students.csv, courses.csv, etc.)")
    parser.add_argument("--file", type=str, help="Path to single CSV file to load")
    parser.add_argument("--table", type=str, help="Table name for single file load (students, courses, attendance, results, rule_registry)")

    args = parser.parse_args()

    # Ensure DB and tables exist
    init_db()
    conn = get_connection()

    try:
        if args.dir:
            dir_path = Path(args.dir)
            if not dir_path.is_dir():
                print(f"[ERROR] Directory does not exist: {dir_path}")
                sys.exit(1)
            print(f"=== Loading Student Data from Directory: {dir_path} ===")
            total = load_directory(conn, dir_path)
            print(f"[SUCCESS] Completed atomic batch load. Total records processed: {total}")
        elif args.file and args.table:
            file_path = Path(args.file)
            if not file_path.is_file():
                print(f"[ERROR] File does not exist: {file_path}")
                sys.exit(1)
            print(f"=== Loading Table '{args.table}' from File: {file_path} ===")
            load_table_from_csv(conn, file_path, args.table, commit=True)
            print(f"[SUCCESS] Table '{args.table}' updated.")
        else:
            default_dir = Path("data/test_students")
            if default_dir.is_dir():
                print(f"No arguments specified. Loading default directory: {default_dir}")
                total = load_directory(conn, default_dir)
                print(f"[SUCCESS] Completed atomic batch load. Total records processed: {total}")
            else:
                parser.print_help()
                sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
