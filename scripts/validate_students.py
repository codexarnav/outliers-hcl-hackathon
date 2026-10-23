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

REQUIRED_COLUMNS = {
    "students.csv": ["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"],
    "courses.csv": ["course_code", "course_name", "programme", "semester", "credits"],
    "attendance.csv": ["student_id", "course_code", "classes_held", "classes_attended"],
    "results.csv": ["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks", "total_marks", "max_marks", "result"],
}

VALID_EXAM_TYPES = {"REGULAR", "SUPPLEMENTARY", "MAKEUP"}
VALID_RESULTS = {"PASS", "FAIL", "ABSENT", "DETAINED"}

def validate_students_data(data_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    
    # 0. Check required files exist and verify headers
    files = {}
    for filename, req_cols in REQUIRED_COLUMNS.items():
        file_path = data_dir / filename
        if not file_path.exists():
            errors.append(f"Missing required CSV file: {filename}")
            return False, errors
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            missing = [c for c in req_cols if c not in headers]
            if missing:
                errors.append(f"{filename}: missing required columns: {', '.join(missing)}")
            files[filename] = list(reader)

    if errors:
        return False, errors

    # 1. Validate Courses
    courses = {}
    for i, row in enumerate(files["courses.csv"], start=2):
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
        except (ValueError, TypeError):
            errors.append(f"[courses.csv:L{i}] Non-integer credits: {row.get('credits')}")
        courses[cc] = row

    if len(courses) < 6:
        errors.append(f"Course count violation: Found {len(courses)} courses, minimum 6 required by Section 4.2.")

    # 2. Validate Students
    students = {}
    programmes = set()
    batches = set()
    for i, row in enumerate(files["students.csv"], start=2):
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
        except (ValueError, TypeError):
            errors.append(f"[students.csv:L{i}] Non-float CGPA: {row.get('cgpa')}")

        try:
            backlogs = int(row.get("active_backlogs", -1))
            if backlogs < 0:
                errors.append(f"[students.csv:L{i}] Active backlogs must be >= 0: {backlogs}")
        except (ValueError, TypeError):
            errors.append(f"[students.csv:L{i}] Non-integer active_backlogs: {row.get('active_backlogs')}")

        try:
            sem = int(row.get("current_semester", 0))
            if sem <= 0 or sem > 12:
                errors.append(f"[students.csv:L{i}] Invalid current_semester: {sem}")
        except (ValueError, TypeError):
            errors.append(f"[students.csv:L{i}] Non-integer current_semester: {row.get('current_semester')}")

        try:
            batch_yr = int(row.get("batch_year", 0))
            if batch_yr < 2000 or batch_yr > 2030:
                errors.append(f"[students.csv:L{i}] Invalid batch_year: {batch_yr}")
        except (ValueError, TypeError):
            errors.append(f"[students.csv:L{i}] Non-integer batch_year: {row.get('batch_year')}")

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
    for i, row in enumerate(files["attendance.csv"], start=2):
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
        except (ValueError, TypeError):
            errors.append(f"[attendance.csv:L{i}] Non-integer attendance figures")

    # 4. Validate Results
    for i, row in enumerate(files["results.csv"], start=2):
        sid = row.get("student_id", "").strip()
        cc = row.get("course_code", "").strip()
        if sid not in students:
            errors.append(f"[results.csv:L{i}] Unknown student_id: {sid}")
        if cc not in courses:
            errors.append(f"[results.csv:L{i}] Unknown course_code: {cc}")

        exam_type = row.get("exam_type", "").strip().upper()
        if exam_type not in VALID_EXAM_TYPES:
            errors.append(f"[results.csv:L{i}] Invalid exam_type '{exam_type}'; must be one of {sorted(VALID_EXAM_TYPES)}")

        try:
            internal = int(row.get("internal_marks", 0))
            external = int(row.get("external_marks", 0))
            total = int(row.get("total_marks", -1))
            max_marks = int(row.get("max_marks", 0))
            res = row.get("result", "").strip().upper()

            # Non-negative marks validation (Comment 5)
            if internal < 0:
                errors.append(f"[results.csv:L{i}] internal_marks cannot be negative: {internal}")
            if external < 0:
                errors.append(f"[results.csv:L{i}] external_marks cannot be negative: {external}")
            if total < 0:
                errors.append(f"[results.csv:L{i}] total_marks cannot be negative: {total}")
            if max_marks <= 0:
                errors.append(f"[results.csv:L{i}] max_marks must be positive: {max_marks}")

            if total != internal + external:
                errors.append(f"[results.csv:L{i}] Total marks mismatch: internal ({internal}) + external ({external}) != total ({total})")
            if total > max_marks:
                errors.append(f"[results.csv:L{i}] Total marks ({total}) exceeds max_marks ({max_marks})")

            if res not in VALID_RESULTS:
                errors.append(f"[results.csv:L{i}] Invalid result value: {res}")
            
            # Pass percentage evaluation against max_marks (Comment 4)
            pass_pct = (total / max_marks * 100.0) if max_marks > 0 else 0.0
            if pass_pct >= 40.0 and res == 'FAIL':
                errors.append(f"[results.csv:L{i}] Logical inconsistency: scored {pass_pct:.1f}% >= 40% but marked FAIL")
            if pass_pct < 40.0 and res == 'PASS':
                errors.append(f"[results.csv:L{i}] Logical inconsistency: scored {pass_pct:.1f}% < 40% but marked PASS")
        except (ValueError, TypeError):
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
