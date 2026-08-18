"""Tests for benchmark report release-gate rendering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "tools" / "benchmarks"))

from benchmark_report import generate_charts_json, generate_markdown_report


def _make_aggregate() -> dict:
    return {
        "total_cases": 1,
        "total_cost_usd": 11.0,
        "total_duration_seconds": 120.0,
        "total_tokens": 12345,
        "mean_composite_score": 0.94,
        "mean_false_negative_rate": 0.0,
        "mean_false_positive_rate": 0.1,
        "mean_discovery_recall": 1.0,
        "mean_triage_recall": 1.0,
        "mean_risk_accuracy": 1.0,
        "mean_element_accuracy": 0.9,
        "mean_invalidity_recall": 0.8,
        "total_blocking_patents": 1,
        "total_discovered_blocking": 1,
        "total_missed_blocking": 0,
        "overall_risk_confusion_matrix": {
            "labels": ["clear"],
            "matrix": [[1]],
            "accuracy": 1.0,
        },
        "per_case_scores": [
            {
                "case_id": "case-1",
                "case_name": "Case 1",
                "tier": "1",
                "composite_score": 0.94,
                "estimated_cost_usd": 11.0,
                "false_negative_rate": 0.0,
                "discovery": {"recall": 1.0, "precision_at_k": {}, "missed_blocking": []},
                "triage": {"false_dismissals": []},
                "risk": {"overall_risk_correct": True},
            }
        ],
        "confidence_intervals": {},
        "release_gate_summary": {
            "schema_version": 2,
            "overall_passed": False,
            "operational_gates_passed": False,
            "cohorts": [
                {
                    "cohort": "us_ep_small_molecule",
                    "passed": False,
                    "attempt_count": 1,
                    "false_clear_attempt_count": 1,
                    "citation_fidelity_rate": 0.5,
                    "attorney_review_coverage": 0.5,
                    "attorney_review_mean_score": 0.82,
                    "failures": [
                        "false_clear_count_exceeded:1>0",
                        "citation_fidelity_rate_below_threshold:0.500<1.000",
                    ],
                }
            ],
        },
    }


def test_generate_markdown_report_renders_release_gate_section(tmp_path: Path):
    output_path = tmp_path / "benchmark_report.md"

    markdown = generate_markdown_report(_make_aggregate(), output_path)

    assert output_path.exists()
    assert "## Release Evidence Gate" in markdown
    assert "**Overall schema-v2 release-evidence gate**: FAIL." in markdown
    assert "| us_ep_small_molecule | FAIL | 1 | 50.0% | 50.0% | 0.82 |" in markdown
    assert (
        "- **us_ep_small_molecule**: false_clear_count_exceeded:1>0, citation_fidelity_rate_below_threshold:0.500<1.000"
        in markdown
    )


def test_generate_charts_json_includes_release_gate_status(tmp_path: Path):
    output_path = tmp_path / "charts_data.json"

    charts = generate_charts_json(_make_aggregate(), output_path)

    assert output_path.exists()
    assert charts["release_gate_status"]["overall_passed"] is False
    assert charts["release_gate_status"]["cohorts"][0]["cohort"] == "us_ep_small_molecule"

    serialized = json.loads(output_path.read_text(encoding="utf-8"))
    assert serialized["release_gate_status"]["cohorts"][0]["false_clear_attempt_count"] == 1
