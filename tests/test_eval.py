"""
Unit Tests for Evaluation Framework (Section 7 Contract)
"""

import json
from pathlib import Path
from eval.judge import run_benchmark

def test_evaluation_benchmark_execution():
    summary = run_benchmark()
    assert summary["total_questions"] >= 20
    metrics = summary["metrics"]
    assert metrics["answer_correctness_pct"] >= 90.0
    assert metrics["citation_accuracy_pct"] >= 90.0
    assert metrics["abstention_accuracy_pct"] == 100.0
    assert metrics["tool_result_correctness_pct"] == 100.0
    assert metrics["retrieval_hit_rate_pct"] >= 90.0

def test_results_and_report_files_exist():
    results_path = Path("eval/results.json")
    report_path = Path("eval/EVALUATION_REPORT.md")
    assert results_path.exists()
    assert report_path.exists()

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["results"]) >= 20
