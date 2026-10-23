#!/usr/bin/env python3
"""
Synthetic Student Data Validator (Annex C Compliance)
Enforces schema constraints, mathematical invariants, logical consistency,
and protects reserved judge ranges (S9000-S9999, JDG*).
"""

import os
import sys
import csv
from pathlib import Path
from typing import List, Dict, Tuple

def validate_students_data(data_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    
    students_file = data_dir / "students.csv"
    courses_file = data_dir / "courses.csv"
    attendance_file = data_dir / "attendance.csv"
    results_file = data_dir / "results.csv"

    # Check files exist
    for f in [students_file, courses_file, attendance_file, results_file]:
        if not f.exists():
            errors.append(f"Missing required CSV file: {f.name}")
            return False, errors

    # 1. Validate Courses
    courses = {}
    with open(courses_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            cc = row.get("course_code", "").strip()
            if not cc:
                errors.append(f"[courses.csv:L{i}] Missing course_code")
                continue
            if cc.startswith("JDG"):
                errors.append(f"[courses.csv:L{i}] Reserved judge course code found: {cc}")
            try:
                credits = int(row.get("credits", 0))
                if credits <= 0:
                    errors.append(f"[courses.csv:L{i}] Credits must be > 0 (found {credits})")
            except ValueError:
                errors.append(f"[courses.csv:L{i}] Non-integer credits: {row.get('credits')}")
            courses[cc] = row

    if len(courses) < 6:
        errors.append(f"Course count violation: Found {len(courses)} courses, minimum 6 required by Section 4.2.")

    # 2. Validate Students
    students = {}
    programmes = set()
    batches = set()
    with open(students_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            sid = row.get("student_id", "").strip()
            if not sid:
                errors.append(f"[students.csv:L{i}] Missing student_id")
                continue
            if not (sid.startswith("S") and len(sid) == 5 and sid[1:].isdigit()):
                errors.append(f"[students.csv:L{i}] Invalid student_id format (must be S + 4 digits): {sid}")
            else:
                num = int(sid[1:])
                if 9000 <= num <= 9999:
                    errors.append(f"[students.csv:L{i}] Student ID in reserved judge range S9000-S9999: {sid}")

            try:
                cgpa = float(row.get("cgpa", -1))
                if not (0.0 <= cgpa <= 10.0):
                    errors.append(f"[students.csv:L{i}] CGPA out of range [0.0, 10.0]: {cgpa}")
            except ValueError:
                errors.append(f"[students.csv:L{i}] Non-float CGPA: {row.get('cgpa')}")

            try:
                backlogs = int(row.get("active_backlogs", -1))
                if backlogs < 0:
                    errors.append(f"[students.csv:L{i}] Active backlogs must be >= 0: {backlogs}")
            except ValueError:
                errors.append(f"[students.csv:L{i}] Non-integer active_backlogs: {row.get('active_backlogs')}")

            prog = row.get("programme", "").strip()
            batch = row.get("batch_year", "").strip()
            if prog: programmes.add(prog)
            if batch: batches.add(batch)
            students[sid] = row

    if len(students) < 30:
        errors.append(f"Student count violation: Found {len(students)} students, minimum 30 required by Section 4.2.")
    if len(programmes) < 2:
        errors.append(f"Programme count violation: Found {len(programmes)} programmes, minimum 2 required.")
    if len(batches) < 2:
        errors.append(f"Batch count violation: Found {len(batches)} batches, minimum 2 required.")

    # 3. Validate Attendance
    with open(attendance_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            sid = row.get("student_id", "").strip()
            cc = row.get("course_code", "").strip()
            if sid not in students:
                errors.append(f"[attendance.csv:L{i}] Unknown student_id: {sid}")
            if cc not in courses:
                errors.append(f"[attendance.csv:L{i}] Unknown course_code: {cc}")
            
            try:
                held = int(row.get("classes_held", 0))
                attended = int(row.get("classes_attended", -1))
                if held <= 0:
                    errors.append(f"[attendance.csv:L{i}] classes_held must be > 0: {held}")
                if attended < 0:
                    errors.append(f"[attendance.csv:L{i}] classes_attended must be >= 0: {attended}")
                if attended > held:
                    errors.append(f"[attendance.csv:L{i}] Invariant violated: attended ({attended}) > held ({held})")
            except ValueError:
                errors.append(f"[attendance.csv:L{i}] Non-integer attendance figures")

    # 4. Validate Results
    with open(results_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            sid = row.get("student_id", "").strip()
            cc = row.get("course_code", "").strip()
            if sid not in students:
                errors.append(f"[results.csv:L{i}] Unknown student_id: {sid}")
            if cc not in courses:
                errors.append(f"[results.csv:L{i}] Unknown course_code: {cc}")

            try:
                internal = int(row.get("internal_marks", 0))
                external = int(row.get("external_marks", 0))
                total = int(row.get("total_marks", -1))
                max_marks = int(row.get("max_marks", 0))
                res = row.get("result", "").strip().upper()

                if total != internal + external:
                    errors.append(f"[results.csv:L{i}] Total marks mismatch: internal ({internal}) + external ({external}) != total ({total})")
                if total > max_marks:
                    errors.append(f"[results.csv:L{i}] Total marks ({total}) exceeds max_marks ({max_marks})")

                if res not in ('PASS', 'FAIL', 'ABSENT', 'DETAINED'):
                    errors.append(f"[results.csv:L{i}] Invalid result value: {res}")
                
                # Logical consistency: If total marks >= 40% and not ABSENT/DETAINED, result should be PASS
                if total >= 40 and res == 'FAIL':
                    errors.append(f"[results.csv:L{i}] Logical inconsistency: total marks ({total}) >= 40 but result marked FAIL")
                if total < 40 and res == 'PASS':
                    errors.append(f"[results.csv:L{i}] Logical inconsistency: total marks ({total}) < 40 but result marked PASS")
            except ValueError:
                errors.append(f"[results.csv:L{i}] Non-integer marks values")

    is_valid = len(errors) == 0
    return is_valid, errors

def main():
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/test_students")
    print(f"=== Validating Synthetic Student Dataset: {target_dir} ===")
    is_valid, errors = validate_students_data(target_dir)
    if is_valid:
        print("[SUCCESS] All Annex C schemas, invariants, and edge cases PASSED validation!")
        sys.exit(0)
    else:
        print(f"[FAIL] Found {len(errors)} validation errors:")
        for e in errors:
            print(f"  ❌ {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
