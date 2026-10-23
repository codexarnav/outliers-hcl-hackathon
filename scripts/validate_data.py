#!/usr/bin/env python3
"""Validate the synthetic academic dataset CSV files.

Usage:
    python validate_data.py
    python validate_data.py --dir data
    python validate_data.py --dir data --as-of 2026-10-23

Exit code: 0 = no errors; 1 = one or more errors.
Warnings (such as missing edge-case examples) do not fail validation.
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REQUIRED_COLUMNS = {
    "students.csv": ["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"],
    "courses.csv": ["course_code", "course_name", "programme", "semester", "credits"],
    "attendance.csv": ["student_id", "course_code", "classes_held", "classes_attended"],
    "results.csv": ["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks", "total_marks", "max_marks", "result"],
    "rule_registry.csv": ["rule_id", "description", "parameter", "operator", "value", "scope_programmes", "scope_batches", "effective_from", "effective_to", "source_doc_id", "source_section"],
    "source_register.csv": ["source_doc_id", "document_title", "document_type", "issued_on", "description"],
}
VALID_EXAM_TYPES = {"REGULAR", "SUPPLEMENTARY"}
VALID_RESULTS = {"PASS", "FAIL", "ABSENT", "DETAINED"}


def read_csv(path, filename, errors):
    file_path = path / filename
    if not file_path.exists():
        errors.append(f"Missing required file: {file_path}")
        return []
    try:
        with file_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            missing = [c for c in REQUIRED_COLUMNS[filename] if c not in headers]
            if missing:
                errors.append(f"{filename}: missing required columns: {', '.join(missing)}")
            rows = list(reader)
            for line_no, row in enumerate(rows, start=2):
                for col in REQUIRED_COLUMNS[filename]:
                    if col in row and row[col] is None:
                        errors.append(f"{filename} row {line_no}: malformed row / missing value for {col}")
            return rows
    except (OSError, csv.Error) as exc:
        errors.append(f"Could not read {file_path}: {exc}")
        return []


def num(row, key, filename, row_no, errors, integer=False):
    try:
        value = float(row[key])
        if integer and not value.is_integer():
            raise ValueError
        return int(value) if integer else value
    except (KeyError, TypeError, ValueError):
        errors.append(f"{filename} row {row_no}: {key} must be {'an integer' if integer else 'numeric'}; got {row.get(key)!r}")
        return None


def in_scope(rule, programme, batch):
    programmes = (rule.get("scope_programmes") or "ALL").split(";")
    batches = (rule.get("scope_batches") or "ALL").split(";")
    p_ok = "ALL" in programmes or programme in programmes
    b_ok = "ALL" in batches or str(batch) in batches
    return p_ok and b_ok


def main():
    parser = argparse.ArgumentParser(description="Validate synthetic academic CSV data.")
    parser.add_argument("--dir", default=None, help="Directory containing the six CSV files (default: ./data if it exists, otherwise script directory).")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="Date for evaluating effective rules, in YYYY-MM-DD format (default: today).")
    args = parser.parse_args()

    try:
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        print("ERROR: --as-of must use YYYY-MM-DD format.")
        return 1

    script_dir = Path(__file__).resolve().parent
    data_dir = Path(args.dir).resolve() if args.dir else (script_dir / "data" if (script_dir / "data").is_dir() else script_dir)
    errors, warnings = [], []
    tables = {name: read_csv(data_dir, name, errors) for name in REQUIRED_COLUMNS}
    students = tables["students.csv"]
    courses = tables["courses.csv"]
    attendance = tables["attendance.csv"]
    results = tables["results.csv"]
    rules = tables["rule_registry.csv"]
    sources = tables["source_register.csv"]

    # Primary keys and reserved identifiers.
    student_by_id, course_by_code, rule_by_id, source_ids = {}, {}, {}, set()
    for i, row in enumerate(students, 2):
        sid = row.get("student_id", "")
        if sid in student_by_id:
            errors.append(f"students.csv row {i}: duplicate student_id {sid}")
        student_by_id[sid] = row
        if not re.fullmatch(r"S\d{4}", sid or ""):
            errors.append(f"students.csv row {i}: student_id must match Sdddd; got {sid!r}")
        elif 9000 <= int(sid[1:]) <= 9999:
            errors.append(f"students.csv row {i}: reserved student_id {sid} must not be used")
        if not row.get("full_name", "").strip():
            errors.append(f"students.csv row {i}: full_name cannot be empty")
        batch = num(row, "batch_year", "students.csv", i, errors, True)
        sem = num(row, "current_semester", "students.csv", i, errors, True)
        cgpa = num(row, "cgpa", "students.csv", i, errors)
        backlogs = num(row, "active_backlogs", "students.csv", i, errors, True)
        if sem is not None and not 1 <= sem <= 10:
            errors.append(f"students.csv row {i}: current_semester must be 1..10")
        if cgpa is not None and not 0 <= cgpa <= 10:
            errors.append(f"students.csv row {i}: cgpa must be 0..10")
        if backlogs is not None and backlogs < 0:
            errors.append(f"students.csv row {i}: active_backlogs cannot be negative")

    for i, row in enumerate(courses, 2):
        code = row.get("course_code", "")
        if code in course_by_code:
            errors.append(f"courses.csv row {i}: duplicate course_code {code}")
        course_by_code[code] = row
        if (code or "").startswith("JDG"):
            errors.append(f"courses.csv row {i}: reserved course-code prefix JDG is not allowed ({code})")
        sem = num(row, "semester", "courses.csv", i, errors, True)
        credits = num(row, "credits", "courses.csv", i, errors, True)
        if sem is not None and not 1 <= sem <= 10:
            errors.append(f"courses.csv row {i}: semester must be 1..10")
        if credits is not None and credits <= 0:
            errors.append(f"courses.csv row {i}: credits must be positive")

    for i, row in enumerate(sources, 2):
        sid = row.get("source_doc_id", "")
        if sid in source_ids:
            errors.append(f"source_register.csv row {i}: duplicate source_doc_id {sid}")
        source_ids.add(sid)

    for i, row in enumerate(rules, 2):
        rid = row.get("rule_id", "")
        if rid in rule_by_id:
            errors.append(f"rule_registry.csv row {i}: duplicate rule_id {rid}")
        rule_by_id[rid] = row
        if row.get("source_doc_id") not in source_ids:
            errors.append(f"rule_registry.csv row {i}: source_doc_id {row.get('source_doc_id')!r} missing from source_register.csv")
        try:
            start = date.fromisoformat(row.get("effective_from", ""))
            end_text = (row.get("effective_to") or "").strip()
            end = date.fromisoformat(end_text) if end_text else None
            if end and end < start:
                errors.append(f"rule_registry.csv row {i}: effective_to is before effective_from")
        except ValueError:
            errors.append(f"rule_registry.csv row {i}: invalid effective_from/effective_to date")
        if row.get("operator") not in {">=", ">", "<=", "<", "==", "!="}:
            errors.append(f"rule_registry.csv row {i}: unsupported operator {row.get('operator')!r}")

    # Active policy values are read from the registry, not hardcoded as the rule source.
    def active_rule(parameter, student=None):
        matching = []
        for rule in rules:
            if rule.get("parameter") != parameter:
                continue
            try:
                start = date.fromisoformat(rule.get("effective_from", ""))
                end_text = (rule.get("effective_to") or "").strip()
                end = date.fromisoformat(end_text) if end_text else None
            except ValueError:
                continue
            if start <= as_of and (end is None or as_of <= end):
                if student is None or in_scope(rule, student.get("programme", ""), student.get("batch_year", "")):
                    matching.append((start, rule))
        return max(matching, key=lambda item: item[0])[1] if matching else None

    attendance_rule = active_rule("min_attendance_pct")
    pass_rule = active_rule("min_total_marks")
    placement_rule = active_rule("placement_min_cgpa")
    attendance_threshold = None
    pass_threshold = None
    placement_threshold = None
    if attendance_rule:
        try: attendance_threshold = float(attendance_rule["value"])
        except (ValueError, TypeError): errors.append("Active min_attendance_pct rule has a non-numeric value")
    else:
        warnings.append(f"No active min_attendance_pct rule found for {as_of}")
    if pass_rule:
        try: pass_threshold = float(pass_rule["value"])
        except (ValueError, TypeError): errors.append("Active min_total_marks rule has a non-numeric value")
    else:
        warnings.append(f"No active min_total_marks rule found for {as_of}")
    if placement_rule:
        try: placement_threshold = float(placement_rule["value"])
        except (ValueError, TypeError): errors.append("Active placement_min_cgpa rule has a non-numeric value")

    # Foreign keys, attendance values, duplicate composite keys.
    attendance_by_pair, attendance_pct = {}, {}
    for i, row in enumerate(attendance, 2):
        sid, code = row.get("student_id", ""), row.get("course_code", "")
        key = (sid, code)
        if key in attendance_by_pair:
            errors.append(f"attendance.csv row {i}: duplicate student_id/course_code key {key}")
        attendance_by_pair[key] = row
        if sid not in student_by_id:
            errors.append(f"attendance.csv row {i}: unknown student_id {sid}")
        if code not in course_by_code:
            errors.append(f"attendance.csv row {i}: unknown course_code {code}")
        held = num(row, "classes_held", "attendance.csv", i, errors, True)
        attended = num(row, "classes_attended", "attendance.csv", i, errors, True)
        if held is not None and held <= 0:
            errors.append(f"attendance.csv row {i}: classes_held must be greater than 0")
        if attended is not None and attended < 0:
            errors.append(f"attendance.csv row {i}: classes_attended cannot be negative")
        if held is not None and attended is not None:
            if attended > held:
                errors.append(f"attendance.csv row {i}: classes_attended exceeds classes_held")
            if held > 0 and attended >= 0:
                attendance_pct[key] = attended / held * 100

    # Results: keys allow separate REGULAR and SUPPLEMENTARY attempts.
    result_keys, results_by_pair = set(), defaultdict(list)
    for i, row in enumerate(results, 2):
        sid, code = row.get("student_id", ""), row.get("course_code", "")
        exam_session = row.get("exam_session", "")
        exam_type = row.get("exam_type", "")
        key = (sid, code, exam_session, exam_type)
        if key in result_keys:
            errors.append(f"results.csv row {i}: duplicate attempt key {key}")
        result_keys.add(key)
        results_by_pair[(sid, code)].append(row)
        if sid not in student_by_id:
            errors.append(f"results.csv row {i}: unknown student_id {sid}")
        if code not in course_by_code:
            errors.append(f"results.csv row {i}: unknown course_code {code}")
        if exam_type not in VALID_EXAM_TYPES:
            errors.append(f"results.csv row {i}: exam_type must be one of {sorted(VALID_EXAM_TYPES)}")
        result = row.get("result", "")
        if result not in VALID_RESULTS:
            errors.append(f"results.csv row {i}: invalid result {result!r}")
        internal = num(row, "internal_marks", "results.csv", i, errors)
        external = num(row, "external_marks", "results.csv", i, errors)
        total = num(row, "total_marks", "results.csv", i, errors)
        maximum = num(row, "max_marks", "results.csv", i, errors)
        if None not in (internal, external, total, maximum):
            if min(internal, external, total) < 0:
                errors.append(f"results.csv row {i}: marks cannot be negative")
            if maximum <= 0:
                errors.append(f"results.csv row {i}: max_marks must be positive")
            if internal + external != total:
                errors.append(f"results.csv row {i}: total_marks ({total:g}) != internal_marks + external_marks ({internal + external:g})")
            if total > maximum:
                errors.append(f"results.csv row {i}: total_marks ({total:g}) exceeds max_marks ({maximum:g})")
            if internal > maximum or external > maximum:
                errors.append(f"results.csv row {i}: a component mark exceeds max_marks")
            if result == "PASS" and pass_threshold is not None and total < pass_threshold:
                errors.append(f"results.csv row {i}: PASS has total {total:g}, below active pass threshold {pass_threshold:g}")
            if result == "FAIL" and pass_threshold is not None and total >= pass_threshold:
                errors.append(f"results.csv row {i}: FAIL has total {total:g}, meeting active pass threshold {pass_threshold:g}")
            if result in {"ABSENT", "DETAINED"} and (internal != 0 or external != 0 or total != 0):
                warnings.append(f"results.csv row {i}: {result} record has non-zero marks; confirm this matches the stated policy")

        student = student_by_id.get(sid)
        course = course_by_code.get(code)
        if student and course and student.get("programme") != course.get("programme"):
            errors.append(f"results.csv row {i}: student programme {student.get('programme')!r} does not match course programme {course.get('programme')!r}")
        if student and course:
            try:
                if int(student["current_semester"]) != int(course["semester"]):
                    warnings.append(f"results.csv row {i}: student {sid} semester {student['current_semester']} differs from course {code} semester {course['semester']}")
            except (ValueError, TypeError, KeyError):
                pass

        pct = attendance_pct.get((sid, code))
        if result != "ABSENT" and pct is not None and attendance_threshold is not None and pct < attendance_threshold and result != "DETAINED":
            errors.append(f"results.csv row {i}: attendance is {pct:.2f}% (<{attendance_threshold:g}%) but result is {result}; check detention policy")
        if result == "DETAINED" and pct is not None and attendance_threshold is not None and pct >= attendance_threshold:
            warnings.append(f"results.csv row {i}: DETAINED result despite attendance {pct:.2f}% meeting threshold; verify another detention rule applies")

    # Programme matching for course registrations and attendance records.
    for filename, rows in (("attendance.csv", attendance),):
        for i, row in enumerate(rows, 2):
            student = student_by_id.get(row.get("student_id", ""))
            course = course_by_code.get(row.get("course_code", ""))
            if student and course and student.get("programme") != course.get("programme"):
                errors.append(f"{filename} row {i}: student programme {student.get('programme')!r} does not match course programme {course.get('programme')!r}")

    # active_backlogs must equal distinct courses whose LATEST attempt is not PASS
    # (supplementary attempts are later than regular ones).
    for sid, student in student_by_id.items():
        pending = 0
        for (s2, code), attempts in results_by_pair.items():
            if s2 != sid or not attempts:
                continue
            latest = sorted(attempts, key=lambda r: (r.get("exam_type") == "SUPPLEMENTARY", r.get("exam_session", "")))[-1]
            if latest.get("result") != "PASS":
                pending += 1
        declared = num_for_check(student.get("active_backlogs"))
        if declared is not None and int(declared) != pending:
            errors.append(f"students.csv {sid}: active_backlogs={int(declared)} but results imply {pending}")

    # Basic size/coverage requirements.
    if len(students) < 30: errors.append(f"Expected at least 30 students; found {len(students)}")
    programmes = {r.get("programme", "") for r in students if r.get("programme", "")}
    batches = {r.get("batch_year", "") for r in students if r.get("batch_year", "")}
    if len(programmes) < 2: errors.append(f"Expected at least 2 programmes; found {len(programmes)}")
    if len(batches) < 2: errors.append(f"Expected at least 2 batches; found {len(batches)}")
    if len(courses) < 6: errors.append(f"Expected at least 6 courses; found {len(courses)}")
    if len(rules) == 0: errors.append("rule_registry.csv is empty")

    # Required edge-case coverage checks (warnings so they can be deliberately reviewed).
    if not any(abs(p - 75.0) < 1e-9 for p in attendance_pct.values()):
        warnings.append("Edge case missing: attendance exactly 75% (e.g. 15/20); check against the intended snapshot policy")
    if not any(abs(p - 70.0) < 1e-9 for p in attendance_pct.values()):
        warnings.append("Edge case missing: one class below 75% for 20 held (14/20 = 70%)")
    if not any(p == 0 for p in attendance_pct.values()): warnings.append("Edge case missing: zero attendance")
    if not any(abs(p - 100.0) < 1e-9 for p in attendance_pct.values()): warnings.append("Edge case missing: full attendance")
    if not any(r.get("result") == "FAIL" and str(r.get("total_marks", "")).strip() == "39" and str(r.get("max_marks", "")).strip() == "100" for r in results):
        warnings.append("Edge case missing: failed course with total_marks=39 and max_marks=100")
    if not any(r.get("result") == "ABSENT" for r in results): warnings.append("Edge case missing: ABSENT result")
    if not any(r.get("result") == "DETAINED" for r in results): warnings.append("Edge case missing: DETAINED result")
    if not any(r.get("exam_type") == "SUPPLEMENTARY" for r in results): warnings.append("Edge case missing: SUPPLEMENTARY examination attempt")
    if not any((num_for_check(r.get("cgpa")) == 7.0) for r in students): warnings.append("Edge case missing: CGPA exactly 7.00 placement cutoff")
    if not any((num_for_check(r.get("active_backlogs")) is not None and num_for_check(r.get("active_backlogs")) >= 2) for r in students): warnings.append("Edge case missing: student with multiple active backlogs")

    print(f"Dataset directory: {data_dir}")
    print(f"Rules evaluated as of: {as_of.isoformat()}")
    print("\nRecord counts:")
    for filename, rows in tables.items():
        print(f"  {filename}: {len(rows)}")
    print(f"\nErrors: {len(errors)}")
    for message in errors:
        print(f"  ERROR: {message}")
    print(f"\nWarnings: {len(warnings)}")
    for message in warnings:
        print(f"  WARNING: {message}")
    if errors:
        print("\nVALIDATION FAILED")
        return 1
    print("\nVALIDATION PASSED (review warnings before submission)")
    return 0


def num_for_check(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    sys.exit(main())
