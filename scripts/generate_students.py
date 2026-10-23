#!/usr/bin/env python3
"""
Synthetic Student Data Generator (Annex C Schema)
Generates structured student data for DTU with deliberate boundary conditions:
- Exactly 75% attendance threshold (S1001)
- Attendance one class below threshold (S1002: 72.5%)
- Medical condonation boundary (S1003: 65.0%)
- Pass/Fail 40% mark boundary (S1004: 39 marks)
- Absent result eligible for make-up (S1005)
- Promotion backlog boundary (S1006: 4 backlogs)
- Severe detention (S1007: 50.0%)
- Placement cut-off boundary (S1008: 7.00 CGPA)
"""

import os
import csv
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "test_students"
os.makedirs(DATA_DIR, exist_ok=True)

# 8 Courses across 3 programmes
COURSES = [
    {"course_code": "CO201", "course_name": "Data Structures", "programme": "B.Tech CSE", "semester": 3, "credits": 4},
    {"course_code": "CO203", "course_name": "Discrete Mathematics", "programme": "B.Tech CSE", "semester": 3, "credits": 4},
    {"course_code": "CO301", "course_name": "Database Management Systems", "programme": "B.Tech CSE", "semester": 5, "credits": 4},
    {"course_code": "IT201", "course_name": "Object Oriented Programming", "programme": "B.Tech IT", "semester": 3, "credits": 4},
    {"course_code": "IT301", "course_name": "Operating Systems", "programme": "B.Tech IT", "semester": 5, "credits": 4},
    {"course_code": "EC201", "course_name": "Digital Design", "programme": "B.Tech ECE", "semester": 3, "credits": 4},
    {"course_code": "EC203", "course_name": "Signals & Systems", "programme": "B.Tech ECE", "semester": 3, "credits": 4},
    {"course_code": "HU101", "course_name": "Communication Skills", "programme": "B.Tech CSE", "semester": 1, "credits": 2},
]

NAMES = [
    "Aarav Sharma", "Diya Patel", "Rohan Verma", "Ananya Iyer", "Kabir Singh",
    "Meera Nair", "Aditya Joshi", "Priya Kapoor", "Vihaan Gupta", "Ishita Sen",
    "Arjun Reddy", "Kavya Menon", "Siddharth Rao", "Rhea Mukherjee", "Dhruv Malhotra",
    "Tanvi Deshmukh", "Yash Singhal", "Pooja Hegde", "Varun Bhat", "Sneha Kulkarni",
    "Nikhil Bose", "Shreya Das", "Devansh Mishra", "Riddhima Saxena", "Manish Tiwari",
    "Bhavna Chawla", "Karan Aggarwal", "Simran Gill", "Gaurav Pandey", "Nehal Shah",
    "Akash Pillai", "Aparna Sundaram", "Harsh Vardhan", "Divya Nambiar", "Ritvik Kaushik"
]

def generate_dataset():
    random.seed(42)

    students = []
    attendance = []
    results = []

    # 1. Generate deliberate edge case students S1001 - S1008
    edge_cases = [
        # S1001: Attendance exactly at 75.0% (30/40) -> ELIGIBLE
        {"id": "S1001", "name": "Aarav Sharma", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 8.10, "backlogs": 0,
         "held": 40, "attended": 30, "int": 24, "ext": 36, "res": "PASS"},

        # S1002: Attendance 1 class below threshold (29/40 = 72.5%) -> DETAINED without condonation
        {"id": "S1002", "name": "Diya Patel", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 7.40, "backlogs": 0,
         "held": 40, "attended": 29, "int": 20, "ext": 35, "res": "PASS"},

        # S1003: Attendance at medical condonation boundary (26/40 = 65.0%) -> CONDONABLE
        {"id": "S1003", "name": "Rohan Verma", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 6.85, "backlogs": 0,
         "held": 40, "attended": 26, "int": 22, "ext": 31, "res": "PASS"},

        # S1004: Marks failure boundary (total 39/100, exactly 1 mark below 40% pass mark)
        {"id": "S1004", "name": "Ananya Iyer", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 5.92, "backlogs": 1,
         "held": 40, "attended": 32, "int": 15, "ext": 24, "res": "FAIL"},

        # S1005: Absent result in external examination -> eligible for make-up exam
        {"id": "S1005", "name": "Kabir Singh", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 6.25, "backlogs": 1,
         "held": 40, "attended": 34, "int": 25, "ext": 0, "res": "ABSENT"},

        # S1006: Promotion boundary: exactly 4 active backlogs entering Sem 5 (Clause R.1(B).15 allows max 4)
        {"id": "S1006", "name": "Meera Nair", "prog": "B.Tech CSE", "batch": 2022, "sem": 5, "cgpa": 5.40, "backlogs": 4,
         "held": 40, "attended": 31, "int": 18, "ext": 28, "res": "PASS"},

        # S1007: Severe detention (20/40 = 50.0%) -> cannot be condoned by any authority
        {"id": "S1007", "name": "Aditya Joshi", "prog": "B.Tech CSE", "batch": 2023, "sem": 3, "cgpa": 4.90, "backlogs": 2,
         "held": 40, "attended": 20, "int": 12, "ext": 15, "res": "DETAINED"},

        # S1008: Placement cut-off boundary (CGPA exactly 7.00)
        {"id": "S1008", "name": "Priya Kapoor", "prog": "B.Tech IT", "batch": 2022, "sem": 5, "cgpa": 7.00, "backlogs": 0,
         "held": 40, "attended": 36, "int": 26, "ext": 42, "res": "PASS"},
    ]

    for ec in edge_cases:
        students.append({
            "student_id": ec["id"],
            "full_name": ec["name"],
            "programme": ec["prog"],
            "batch_year": ec["batch"],
            "current_semester": ec["sem"],
            "cgpa": ec["cgpa"],
            "active_backlogs": ec["backlogs"]
        })
        cc = "IT201" if ec["prog"] == "B.Tech IT" else "CO201"
        attendance.append({
            "student_id": ec["id"],
            "course_code": cc,
            "classes_held": ec["held"],
            "classes_attended": ec["attended"]
        })
        total = ec["int"] + ec["ext"]
        results.append({
            "student_id": ec["id"],
            "course_code": cc,
            "exam_session": "2024-MAY",
            "exam_type": "REGULAR",
            "internal_marks": ec["int"],
            "external_marks": ec["ext"],
            "total_marks": total,
            "max_marks": 100,
            "result": ec["res"]
        })

    # 2. Generate remaining students S1009 - S1035 across CSE, IT, ECE
    progs = ["B.Tech CSE", "B.Tech IT", "B.Tech ECE"]
    batches = [2022, 2023, 2024]

    for idx in range(8, 35):
        sid = f"S{1001 + idx}"
        name = NAMES[idx]
        prog = progs[idx % 3]
        batch = batches[idx % 3]
        sem = 1 if batch == 2024 else (3 if batch == 2023 else 5)
        cgpa = round(random.uniform(6.0, 9.5), 2)
        backlogs = random.choice([0, 0, 0, 1, 2])

        students.append({
            "student_id": sid,
            "full_name": name,
            "programme": prog,
            "batch_year": batch,
            "current_semester": sem,
            "cgpa": cgpa,
            "active_backlogs": backlogs
        })

        # Select relevant courses for student
        rel_courses = [c["course_code"] for c in COURSES if c["programme"] == prog or c["course_code"] == "HU101"]
        for cc in rel_courses[:2]:
            held = 40
            pct = random.uniform(0.70, 0.98)
            attended = int(held * pct)
            attendance.append({
                "student_id": sid,
                "course_code": cc,
                "classes_held": held,
                "classes_attended": attended
            })

            int_marks = random.randint(18, 28)
            ext_marks = random.randint(25, 45)
            total = int_marks + ext_marks
            res = "PASS" if total >= 40 else "FAIL"
            results.append({
                "student_id": sid,
                "course_code": cc,
                "exam_session": "2024-MAY",
                "exam_type": "REGULAR",
                "internal_marks": int_marks,
                "external_marks": ext_marks,
                "total_marks": total,
                "max_marks": 100,
                "result": res
            })

    # Write CSV files
    # 1. students.csv
    with open(DATA_DIR / "students.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"])
        w.writeheader()
        w.writerows(students)

    # 2. courses.csv
    with open(DATA_DIR / "courses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["course_code", "course_name", "programme", "semester", "credits"])
        w.writeheader()
        w.writerows(COURSES)

    # 3. attendance.csv
    with open(DATA_DIR / "attendance.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "course_code", "classes_held", "classes_attended"])
        w.writeheader()
        w.writerows(attendance)

    # 4. results.csv
    with open(DATA_DIR / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks", "total_marks", "max_marks", "result"])
        w.writeheader()
        w.writerows(results)

    print(f"[SUCCESS] Generated {len(students)} students, {len(COURSES)} courses, {len(attendance)} attendance records, {len(results)} results in {DATA_DIR}")

if __name__ == "__main__":
    generate_dataset()
