from __future__ import annotations

from research.tools.benchmarks.benchmark_report import generate_markdown_report


def test_empty_execution_does_not_render_zero_as_passing_accuracy(tmp_path) -> None:
    aggregate = {
        "total_cases": 0,
        "total_cost_usd": 0.0,
        "total_duration_seconds": 0.0,
        "mean_false_negative_rate": 0.0,
        "mean_false_positive_rate": 0.0,
        "release_gate_summary": {
            "overall_passed": False,
            "execution_ledger": {
                "passed": False,
                "planned_attempts": 1,
                "attempted_attempts": 1,
                "scored_attempts": 0,
                "gated_attempts": 0,
                "failures": ["execution_errored_attempts:1"],
            },
            "cohorts": [],
            "independent_case_safety": {"cohorts": []},
        },
    }

    report = generate_markdown_report(aggregate, tmp_path / "report.md")

    assert "No valid accuracy report was produced" in report
    assert "**Completed cases**: 0" in report
    assert "**Total duration**" not in report
    assert "False Negative Rate**: 0.0% (PASS" not in report
    assert "Praviar Pipeline vs Manual FTO Comparison" not in report
    assert (
        "Execution ledger**: FAIL — planned 1, attempted 1, scored 0, gated 0" in report
    )


def test_scored_report_does_not_claim_legal_or_deployment_readiness(tmp_path) -> None:
    aggregate = {
        "total_cases": 1,
        "total_cost_usd": 1.25,
        "total_duration_seconds": 2.0,
        "mean_composite_score": 0.99,
        "mean_false_negative_rate": 0.0,
        "mean_false_positive_rate": 0.0,
        "mean_discovery_recall": 1.0,
        "release_gate_summary": {"overall_passed": False, "cohorts": []},
    }

    report = generate_markdown_report(aggregate, tmp_path / "report.md")

    assert "MEETS CONFIGURED RESEARCH THRESHOLD" in report
    assert "does not establish legal accuracy" in report
    assert "## Measured Execution Observations" in report
    assert "not a comparison with professional legal work" in report
    assert "Production-ready" not in report
    assert "Manual FTO" not in report
    assert "Cost reduction" not in report
    assert "expert-validated ground truth" not in report
