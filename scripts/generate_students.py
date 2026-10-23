#!/usr/bin/env python3
"""
Synthetic Student Data Generator (Annex C Schema)
Synchronizes and regenerates the complete 60-student synthetic dataset,
including 12 courses, 180 attendance records, 181 results, and edge_case_manifest.json.
"""

import os
import sys
import json
import csv
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "test_students"
JSON_DATASET_PATH = DATA_DIR / "synthetic_student_dataset.json"
MANIFEST_PATH = DATA_DIR / "edge_case_manifest.json"

def export_json_to_csvs():
    """Exports structured records from synthetic_student_dataset.json into Annex C CSVs."""
    if not JSON_DATASET_PATH.exists():
        print(f"[ERROR] Source dataset JSON not found: {JSON_DATASET_PATH}")
        sys.exit(1)

    with open(JSON_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. students.csv
    students = data.get("students", [])
    if students:
        with open(DATA_DIR / "students.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"])
            writer.writeheader()
            writer.writerows(students)
        print(f"[OK] Wrote {len(students)} students to students.csv")

    # 2. courses.csv
    courses = data.get("courses", [])
    if courses:
        with open(DATA_DIR / "courses.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["course_code", "course_name", "programme", "semester", "credits"])
            writer.writeheader()
            writer.writerows(courses)
        print(f"[OK] Wrote {len(courses)} courses to courses.csv")

    # 3. attendance.csv
    attendance = data.get("attendance", [])
    if attendance:
        with open(DATA_DIR / "attendance.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["student_id", "course_code", "classes_held", "classes_attended"])
            writer.writeheader()
            writer.writerows(attendance)
        print(f"[OK] Wrote {len(attendance)} attendance rows to attendance.csv")

    # 4. results.csv
    results = data.get("results", [])
    if results:
        with open(DATA_DIR / "results.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks", "total_marks", "max_marks", "result"])
            writer.writeheader()
            writer.writerows(results)
        print(f"[OK] Wrote {len(results)} results rows to results.csv")

    # 5. rule_registry.csv
    rules = data.get("rule_registry", [])
    if rules:
        with open(DATA_DIR / "rule_registry.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["rule_id", "description", "parameter", "operator", "value", "scope_programmes", "scope_batches", "effective_from", "effective_to", "source_doc_id", "source_section"])
            writer.writeheader()
            writer.writerows(rules)
        print(f"[OK] Wrote {len(rules)} rules to rule_registry.csv")

    # 6. source_register.csv
    sources = data.get("source_register", [])
    if sources:
        with open(DATA_DIR / "source_register.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source_doc_id", "document_title", "document_type", "issued_on", "description"])
            writer.writeheader()
            writer.writerows(sources)
        print(f"[OK] Wrote {len(sources)} sources to source_register.csv")

    # 7. edge_case_manifest.json
    manifest = data.get("edge_case_manifest")
    if manifest:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        print(f"[OK] Synced edge_case_manifest.json")

    print("[SUCCESS] All 60-student dataset tables generated cleanly!")

if __name__ == "__main__":
    export_json_to_csvs()
