"""Benchmark report generator for Praviar Pipeline research evaluation.

Takes benchmark results and generates a publishable markdown report with:
  - Per-compound breakdown with pass/fail indicators
  - Aggregate statistics with confidence intervals
  - Confusion matrices for risk classification
  - Discovery recall analysis
  - Measured runtime and model-usage observations
  - Charts-ready JSON data for the web frontend
  - A research-candidate summary with explicit evidence limitations

Usage:
    python benchmark_report.py --results-dir praviar_pipeline/benchmark_results/20260325_143000/
    python benchmark_report.py --aggregate-json path/to/aggregate_scores.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def generate_markdown_report(
    aggregate: dict[str, Any],
    output_path: Path,
    previous_run: dict[str, Any] | None = None,
) -> str:
    """Generate a comprehensive markdown benchmark report.

    Args:
        aggregate: Aggregate scores dict (from AggregateScore.to_dict()).
        output_path: Where to write the report.
        previous_run: Optional previous run aggregate for regression comparison.

    Returns:
        The markdown string (also written to output_path).
    """
    lines: list[str] = []

    _render_header(lines, aggregate)
    if int(aggregate.get("total_cases", 0) or 0) == 0:
        _render_incomplete_execution(lines, aggregate)
        _render_release_gate_summary(lines, aggregate)
        _render_methodology(lines)
        _render_footer(lines, aggregate)
        report = "\n".join(lines)
        output_path.write_text(report, encoding="utf-8")
        return report

    _render_executive_summary(lines, aggregate)
    _render_release_gate_summary(lines, aggregate)
    _render_aggregate_metrics(lines, aggregate)
    _render_confusion_matrix(lines, aggregate)
    _render_per_compound_table(lines, aggregate)
    _render_discovery_analysis(lines, aggregate)
    _render_false_negative_analysis(lines, aggregate)
    _render_cost_comparison(lines, aggregate)
    if previous_run:
        _render_regression_comparison(lines, aggregate, previous_run)
    _render_confidence_intervals(lines, aggregate)
    _render_methodology(lines)
    _render_footer(lines, aggregate)

    report = "\n".join(lines)
    output_path.write_text(report, encoding="utf-8")
    return report


def generate_charts_json(
    aggregate: dict[str, Any], output_path: Path
) -> dict[str, Any]:
    """Generate charts-ready JSON data for the web frontend.

    Args:
        aggregate: Aggregate scores dict.
        output_path: Where to write the JSON.

    Returns:
        The charts data dict (also written to output_path).
    """
    charts: dict[str, Any] = {}

    # 1. Score radar chart data
    charts["score_radar"] = {
        "labels": [
            "Discovery Recall",
            "Triage Recall",
            "Risk Accuracy",
            "Element Accuracy",
            "Invalidity Recall",
            "1 - FP Rate",
            "1 - FN Rate",
        ],
        "values": [
            aggregate.get("mean_discovery_recall", 0),
            aggregate.get("mean_triage_recall", 0),
            aggregate.get("mean_risk_accuracy", 0),
            aggregate.get("mean_element_accuracy", 0),
            aggregate.get("mean_invalidity_recall", 0),
            1.0 - aggregate.get("mean_false_positive_rate", 0),
            1.0 - aggregate.get("mean_false_negative_rate", 0),
        ],
    }

    # 2. Per-case composite scores (bar chart)
    per_case = aggregate.get("per_case_scores", [])
    charts["composite_scores_bar"] = {
        "labels": [c.get("case_name", c.get("case_id", "")) for c in per_case],
        "values": [c.get("composite_score", 0) for c in per_case],
        "tiers": [c.get("tier", "") for c in per_case],
    }

    # 3. Risk confusion matrix (heatmap)
    cm = aggregate.get("overall_risk_confusion_matrix", {})
    charts["risk_confusion_heatmap"] = {
        "labels": cm.get("labels", []),
        "matrix": cm.get("matrix", []),
        "x_axis": "Predicted",
        "y_axis": "Actual",
    }

    # 4. Discovery recall by tier (grouped bar)
    tier_discovery: dict[str, list[float]] = {}
    for case in per_case:
        tier = case.get("tier", "unknown")
        recall = case.get("discovery", {}).get("recall", 0)
        tier_discovery.setdefault(tier, []).append(recall)

    charts["discovery_by_tier"] = {
        "tiers": list(tier_discovery.keys()),
        "mean_recall": [sum(v) / len(v) if v else 0 for v in tier_discovery.values()],
        "min_recall": [min(v) if v else 0 for v in tier_discovery.values()],
        "max_recall": [max(v) if v else 0 for v in tier_discovery.values()],
    }

    # 5. Cost vs accuracy scatter
    charts["cost_vs_accuracy"] = {
        "points": [
            {
                "case_id": c.get("case_id", ""),
                "cost_usd": c.get("estimated_cost_usd", 0),
                "composite_score": c.get("composite_score", 0),
                "tier": c.get("tier", ""),
            }
            for c in per_case
        ],
    }

    # 6. Confidence intervals (error bar chart)
    ci = aggregate.get("confidence_intervals", {})
    charts["confidence_intervals"] = {
        "metrics": list(ci.keys()),
        "means": [
            aggregate.get(f"mean_{k}", (lo + hi) / 2)
            if k != "composite_score"
            else aggregate.get("mean_composite_score", (lo + hi) / 2)
            for k, (lo, hi) in ci.items()
        ],
        "lower": [lo for _, (lo, _) in ci.items()],
        "upper": [hi for _, (_, hi) in ci.items()],
    }

    release_gate_summary = aggregate.get("release_gate_summary") or {}
    if release_gate_summary:
        charts["release_gate_status"] = {
            "overall_passed": bool(release_gate_summary.get("overall_passed")),
            "cohorts": [
                {
                    "cohort": cohort.get("cohort", ""),
                    "passed": bool(cohort.get("passed")),
                    "false_clear_attempt_count": cohort.get(
                        "false_clear_attempt_count", 0
                    ),
                    "citation_fidelity_rate": cohort.get("citation_fidelity_rate", 0),
                    "attorney_review_coverage": cohort.get(
                        "attorney_review_coverage", 0
                    ),
                    "attorney_review_mean_score": cohort.get(
                        "attorney_review_mean_score"
                    ),
                }
                for cohort in release_gate_summary.get("cohorts", [])
            ],
        }

    output_path.write_text(json.dumps(charts, indent=2, default=str), encoding="utf-8")
    return charts


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_header(lines: list[str], agg: dict[str, Any]) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    total_cases = int(agg.get("total_cases", 0) or 0)
    lines.append("# Praviar Pipeline Benchmark Validation Report")
    lines.append("")
    lines.append(f"**Generated**: {now}")
    if total_cases == 0:
        lines.append("**Completed cases**: 0")
        lines.append(f"**Recorded provider cost**: ${agg.get('total_cost_usd', 0):.2f}")
    else:
        lines.append(f"**Total cases**: {total_cases}")
        lines.append(f"**Total cost**: ${agg.get('total_cost_usd', 0):.2f}")
        lines.append(
            f"**Total duration**: {_format_duration(agg.get('total_duration_seconds', 0))}"
        )
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_incomplete_execution(lines: list[str], agg: dict[str, Any]) -> None:
    ledger = (agg.get("release_gate_summary") or {}).get("execution_ledger") or {}
    lines.append("## Execution Incomplete")
    lines.append("")
    lines.append(
        "**No valid accuracy report was produced.** No benchmark attempt completed "
        "scoring, so false-negative rate, false-positive rate, discovery recall, "
        "composite score, and per-compound cost/time are not estimable."
    )
    lines.append("")
    lines.append(f"- Planned attempts: {ledger.get('planned_attempts', 0)}")
    lines.append(f"- Attempted: {ledger.get('attempted_attempts', 0)}")
    lines.append(f"- Scored: {ledger.get('scored_attempts', 0)}")
    lines.append(f"- Gated: {ledger.get('gated_attempts', 0)}")
    failures = ledger.get("failures") or []
    if failures:
        lines.append(f"- Execution failures: {', '.join(map(str, failures))}")
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_executive_summary(lines: list[str], agg: dict[str, Any]) -> None:
    lines.append("## Executive Summary")
    lines.append("")

    composite = agg.get("mean_composite_score", 0)
    fn_rate = agg.get("mean_false_negative_rate", 0)
    fp_rate = agg.get("mean_false_positive_rate", 0)
    discovery = agg.get("mean_discovery_recall", 0)

    # Score interpretation
    if composite >= 0.95:
        verdict = "MEETS CONFIGURED RESEARCH THRESHOLD"
        interpretation = (
            "This candidate score meets the configured evaluation threshold; it does "
            "not establish legal accuracy, deployment readiness, or fitness for use."
        )
    elif composite >= 0.85:
        verdict = "RESEARCH CANDIDATE"
        interpretation = (
            "This candidate remains below the highest configured evaluation band and "
            "requires independent evidence review."
        )
    elif composite >= 0.70:
        verdict = "BELOW CONFIGURED TARGET"
        interpretation = (
            "The candidate is below the configured target and cannot support a release "
            "or legal-performance claim."
        )
    else:
        verdict = "BELOW CONFIGURED TARGET"
        interpretation = (
            "The candidate is below the configured target; investigate the measured "
            "failure modes before another evaluation."
        )

    lines.append(f"**Overall Verdict**: {verdict} (composite score: {composite:.1%})")
    lines.append("")
    lines.append(f"> {interpretation}")
    lines.append("")
    lines.append(
        f"- **False Negative Rate**: {fn_rate:.1%} "
        f"({'PASS' if fn_rate <= 0.05 else 'FAIL'} vs 5% threshold)"
    )
    lines.append(
        f"- **False Positive Rate**: {fp_rate:.1%} "
        f"({'PASS' if fp_rate <= 0.20 else 'NEEDS IMPROVEMENT'} vs 20% threshold)"
    )
    lines.append(f"- **Discovery Recall**: {discovery:.1%}")
    lines.append(
        f"- **Total blocking patents tracked**: {agg.get('total_blocking_patents', 0)}"
    )
    lines.append(
        f"- **Discovered**: {agg.get('total_discovered_blocking', 0)} "
        f"/ Missed: {agg.get('total_missed_blocking', 0)}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_aggregate_metrics(lines: list[str], agg: dict[str, Any]) -> None:
    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append("| Metric | Score | Target |")
    lines.append("|--------|-------|--------|")

    metrics = [
        ("Discovery Recall", agg.get("mean_discovery_recall", 0), ">= 0.90"),
        ("Triage Recall", agg.get("mean_triage_recall", 0), ">= 0.85"),
        ("Risk Classification Accuracy", agg.get("mean_risk_accuracy", 0), ">= 0.80"),
        ("Element-Level Accuracy", agg.get("mean_element_accuracy", 0), ">= 0.75"),
        ("Invalidity Recall", agg.get("mean_invalidity_recall", 0), ">= 0.70"),
        ("False Positive Rate", agg.get("mean_false_positive_rate", 0), "< 0.20"),
        ("False Negative Rate", agg.get("mean_false_negative_rate", 0), "< 0.05"),
        ("**Composite Score**", agg.get("mean_composite_score", 0), ">= 0.85"),
    ]

    for name, value, target in metrics:
        icon = _pass_fail_icon(name, value, target)
        lines.append(f"| {name} | {value:.1%} {icon} | {target} |")

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_release_gate_summary(lines: list[str], agg: dict[str, Any]) -> None:
    summary = agg.get("release_gate_summary") or {}
    cohorts = summary.get("cohorts", [])
    if not summary:
        return

    overall_status = "PASS" if summary.get("overall_passed") else "FAIL"

    lines.append("## Release Evidence Gate")
    lines.append("")
    lines.append(
        f"**Overall schema-v2 release-evidence gate**: {overall_status}. "
        "Stochastic attempts are retained for audit, while only eligible independent "
        "matters contribute to the conditional false-clear safety bound."
    )
    lines.append("")
    ledger = summary.get("execution_ledger") or {}
    lines.append(
        "**Execution ledger**: "
        f"{'PASS' if ledger.get('passed') else 'FAIL'} — "
        f"planned {ledger.get('planned_attempts', 0)}, "
        f"attempted {ledger.get('attempted_attempts', 0)}, "
        f"scored {ledger.get('scored_attempts', 0)}, "
        f"gated {ledger.get('gated_attempts', 0)}."
    )
    lines.append("")
    lines.append(
        "| Operational cohort | Status | False-clear attempts | Citation Fidelity | "
        "Attorney Review Coverage | Attorney Review Mean |"
    )
    lines.append(
        "|--------|--------|--------------|-------------------|--------------------------|----------------------|"
    )

    for cohort in cohorts:
        lines.append(
            f"| {cohort.get('cohort', 'unknown')} | "
            f"{'PASS' if cohort.get('passed') else 'FAIL'} | "
            f"{cohort.get('false_clear_attempt_count', 0)} | "
            f"{cohort.get('citation_fidelity_rate', 0):.1%} | "
            f"{cohort.get('attorney_review_coverage', 0):.1%} | "
            f"{_format_optional_score(cohort.get('attorney_review_mean_score'))} |"
        )

    failing = [cohort for cohort in cohorts if not cohort.get("passed")]
    if failing:
        lines.append("")
        lines.append("### Blocking Cohort Failures")
        lines.append("")
        for cohort in failing:
            failures = cohort.get("failures", []) or [
                "unspecified_release_gate_failure"
            ]
            lines.append(
                f"- **{cohort.get('cohort', 'unknown')}**: {', '.join(failures)}"
            )

    safety = summary.get("independent_case_safety") or {}
    safety_cohorts = safety.get("cohorts") or []
    lines.append("")
    lines.append("### Independent-case conditional safety evidence")
    lines.append("")
    lines.append(
        "The estimand is P(expected outcome is non-clear | Praviar outputs clear). "
        "A repeated run never increases the independent denominator."
    )
    lines.append("")
    lines.append(
        "| Cohort | Status | Eligible independent matters | Predicted-clear N | "
        "False clears (k) | Observed k/n | Exact upper bound |"
    )
    lines.append(
        "|--------|--------|------------------------------|-------------------|"
        "------------------|--------------|-------------------|"
    )
    if not safety_cohorts:
        lines.append(
            "| No eligible release-evidence cohort | FAIL | 0 | 0 | 0 | Not estimable | Not estimable |"
        )
    for cohort in safety_cohorts:
        predicted_clear_n = cohort.get("independent_predicted_clear_case_count", 0)
        observed_rate = cohort.get("observed_false_clear_rate")
        upper_bound = cohort.get("false_clear_rate_upper_bound")
        lines.append(
            f"| {cohort.get('cohort', 'unknown')} | "
            f"{'PASS' if cohort.get('passed') else 'FAIL'} | "
            f"{cohort.get('independent_case_count', 0)} | "
            f"{predicted_clear_n} | "
            f"{cohort.get('independent_false_clear_case_count', 0)} | "
            f"{f'{observed_rate:.2%}' if observed_rate is not None else 'Not estimable'} | "
            f"{f'{upper_bound:.2%}' if upper_bound is not None else 'Not estimable'} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_confusion_matrix(lines: list[str], agg: dict[str, Any]) -> None:
    cm = agg.get("overall_risk_confusion_matrix", {})
    labels = cm.get("labels", [])
    matrix = cm.get("matrix", [])

    if not labels or not matrix:
        return

    lines.append("## Risk Classification Confusion Matrix")
    lines.append("")
    lines.append(
        "Rows = actual risk (ground truth), Columns = predicted risk (pipeline)"
    )
    lines.append("")

    # Header
    header = (
        "| Actual \\ Predicted | "
        + " | ".join(label.upper() for label in labels)
        + " |"
    )
    lines.append(header)
    lines.append("|" + "---|" * (len(labels) + 1))

    for i, label in enumerate(labels):
        row = [str(matrix[i][j]) for j in range(len(labels))]
        # Bold diagonal (correct predictions)
        row[i] = f"**{row[i]}**"
        lines.append(f"| **{label.upper()}** | " + " | ".join(row) + " |")

    lines.append("")
    lines.append(f"Overall accuracy: {cm.get('accuracy', 0):.1%}")
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_per_compound_table(lines: list[str], agg: dict[str, Any]) -> None:
    per_case = agg.get("per_case_scores", [])
    if not per_case:
        return

    lines.append("## Per-Compound Results")
    lines.append("")
    lines.append("| Case | Tier | Composite | Discovery | Risk | FN Rate | Cost |")
    lines.append("|------|------|-----------|-----------|------|---------|------|")

    for case in per_case:
        name = case.get("case_name", case.get("case_id", "?"))
        if len(name) > 40:
            name = name[:37] + "..."
        tier = case.get("tier", "?")
        composite = case.get("composite_score", 0)
        discovery = case.get("discovery", {}).get("recall", 0)
        risk_correct = (
            "PASS" if case.get("risk", {}).get("overall_risk_correct") else "FAIL"
        )
        fn_rate = case.get("false_negative_rate", 0)
        cost = case.get("estimated_cost_usd", 0)

        composite_icon = (
            "PASS" if composite >= 0.85 else ("WARN" if composite >= 0.70 else "FAIL")
        )

        lines.append(
            f"| {name} | {tier} | {composite:.1%} {composite_icon} | "
            f"{discovery:.1%} | {risk_correct} | {fn_rate:.1%} | ${cost:.2f} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_discovery_analysis(lines: list[str], agg: dict[str, Any]) -> None:
    per_case = agg.get("per_case_scores", [])
    if not per_case:
        return

    lines.append("## Discovery Analysis")
    lines.append("")

    # Missed patents (most critical)
    any_missed = False
    for case in per_case:
        missed = case.get("discovery", {}).get("missed_blocking", [])
        if missed:
            if not any_missed:
                lines.append("### Missed Blocking Patents")
                lines.append("")
                any_missed = True
            name = case.get("case_name", case.get("case_id", ""))
            lines.append(f"**{name}**:")
            for pid in missed:
                lines.append(f"  - {pid}")
            lines.append("")

    if not any_missed:
        lines.append("No blocking patents were missed across all benchmark cases.")
        lines.append("")

    # Precision@K analysis
    lines.append("### Discovery Precision@K")
    lines.append("")
    lines.append("| Case | @20 | @50 | @100 |")
    lines.append("|------|-----|-----|------|")
    for case in per_case:
        name = case.get("case_name", case.get("case_id", "?"))
        if len(name) > 40:
            name = name[:37] + "..."
        p_at_k = case.get("discovery", {}).get("precision_at_k", {})
        p20 = p_at_k.get("20", p_at_k.get(20, 0))
        p50 = p_at_k.get("50", p_at_k.get(50, 0))
        p100 = p_at_k.get("100", p_at_k.get(100, 0))
        lines.append(f"| {name} | {p20:.1%} | {p50:.1%} | {p100:.1%} |")

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_false_negative_analysis(lines: list[str], agg: dict[str, Any]) -> None:
    lines.append("## False Negative Analysis")
    lines.append("")
    lines.append(
        "False negatives are the single most critical failure mode for an FTO tool. "
        "A false negative means a blocking patent was either not discovered, dismissed "
        "at triage, or incorrectly rated as LOW/CLEAR risk."
    )
    lines.append("")

    per_case = agg.get("per_case_scores", [])
    fn_cases = [c for c in per_case if c.get("false_negative_rate", 0) > 0]

    if fn_cases:
        lines.append(f"**{len(fn_cases)} case(s) had false negatives:**")
        lines.append("")
        for case in fn_cases:
            name = case.get("case_name", case.get("case_id", ""))
            fn_rate = case.get("false_negative_rate", 0)
            triage_dismissals = case.get("triage", {}).get("false_dismissals", [])
            lines.append(f"- **{name}**: FN rate {fn_rate:.1%}")
            if triage_dismissals:
                lines.append(f"  - Triage dismissals: {', '.join(triage_dismissals)}")
    else:
        lines.append("No false negatives detected across all benchmark cases.")

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_cost_comparison(lines: list[str], agg: dict[str, Any]) -> None:
    """Render measured execution observations without an unbound manual baseline."""
    lines.append("## Measured Execution Observations")
    lines.append("")
    lines.append("| Dimension | Measured candidate run |")
    lines.append("|-----------|------------------------|")

    total_cases = agg.get("total_cases", 1)
    total_cost = agg.get("total_cost_usd", 0)
    cost_per = total_cost / total_cases if total_cases else 0
    total_duration = agg.get("total_duration_seconds", 0)
    duration_per = total_duration / total_cases if total_cases else 0

    lines.append(f"| Recorded cost per case | ${cost_per:.2f} |")
    lines.append(f"| Recorded time per case | {_format_duration(duration_per)} |")
    lines.append(f"| Total recorded cost ({total_cases} cases) | ${total_cost:.2f} |")
    lines.append(
        f"| Candidate false-negative rate | {agg.get('mean_false_negative_rate', 0):.1%} |"
    )
    lines.append(
        f"| Candidate discovery recall | {agg.get('mean_discovery_recall', 0):.1%} |"
    )
    lines.append("")
    lines.append(
        "These observations describe only this recorded candidate execution. They are not "
        "a comparison with professional legal work and do not establish cost savings, "
        "legal accuracy, or operational readiness."
    )
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_regression_comparison(
    lines: list[str], current: dict[str, Any], previous: dict[str, Any]
) -> None:
    lines.append("## Regression Analysis")
    lines.append("")
    lines.append("Comparison against previous benchmark run.")
    lines.append("")
    lines.append("| Metric | Previous | Current | Delta |")
    lines.append("|--------|----------|---------|-------|")

    metrics = [
        ("Composite Score", "mean_composite_score"),
        ("Discovery Recall", "mean_discovery_recall"),
        ("Triage Recall", "mean_triage_recall"),
        ("False Negative Rate", "mean_false_negative_rate"),
        ("False Positive Rate", "mean_false_positive_rate"),
        ("Element Accuracy", "mean_element_accuracy"),
    ]

    regressions = []
    for name, key in metrics:
        prev = previous.get(key, 0)
        curr = current.get(key, 0)
        delta = curr - prev
        delta_str = f"+{delta:.1%}" if delta >= 0 else f"{delta:.1%}"
        icon = ""

        # Check for regressions
        if key == "mean_false_negative_rate" and delta > 0:
            icon = " REGRESSION"
            regressions.append(name)
        elif key in ("mean_false_positive_rate",) and delta > 0.02:
            icon = " REGRESSION"
            regressions.append(name)
        elif (
            key not in ("mean_false_negative_rate", "mean_false_positive_rate")
            and delta < -0.02
        ):
            icon = " REGRESSION"
            regressions.append(name)

        lines.append(f"| {name} | {prev:.1%} | {curr:.1%} | {delta_str}{icon} |")

    lines.append("")

    if regressions:
        lines.append(f"**REGRESSIONS DETECTED** in: {', '.join(regressions)}")
    else:
        lines.append("No regressions detected.")

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_confidence_intervals(lines: list[str], agg: dict[str, Any]) -> None:
    ci = agg.get("confidence_intervals", {})
    if not ci:
        return

    lines.append("## Statistical Confidence Intervals (95%)")
    lines.append("")
    lines.append("Bootstrap confidence intervals (n=1000 resamples).")
    lines.append("")
    lines.append("| Metric | Mean | 95% CI |")
    lines.append("|--------|------|--------|")

    for metric_name, (lo, hi) in ci.items():
        display_name = metric_name.replace("_", " ").title()
        mean_key = f"mean_{metric_name}"
        mean_val = agg.get(mean_key, (lo + hi) / 2)
        lines.append(f"| {display_name} | {mean_val:.1%} | [{lo:.1%}, {hi:.1%}] |")

    lines.append("")
    lines.append("---")
    lines.append("")


def _render_methodology(lines: list[str]) -> None:
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "This report was generated by the Praviar Pipeline research evaluation framework. "
        "Each case uses the labels and source references supplied by the selected evaluation "
        "dataset. This report does not independently establish that those labels are "
        "counsel-adjudicated ground truth or that the candidate is legally accurate."
    )
    lines.append("")
    lines.append("**Scoring dimensions:**")
    lines.append("")
    lines.append(
        "1. **Discovery Score**: Did we find the known blocking patents? (recall, precision@K)"
    )
    lines.append(
        "2. **Triage Score**: Were blocking patents correctly kept after triage?"
    )
    lines.append("3. **Risk Score**: Does risk classification match expected levels?")
    lines.append("4. **Claim Score**: Element-level analysis accuracy")
    lines.append("5. **Invalidity Score**: Prior art and PTAB detection")
    lines.append(
        "6. **False Positive Rate**: Non-blocking patents incorrectly flagged HIGH"
    )
    lines.append(
        "7. **False Negative Rate**: Blocking patents missed or underrated (5x penalty)"
    )
    lines.append("")
    lines.append("**Composite score formula:**")
    lines.append("")
    lines.append("```")
    lines.append("composite = 0.05 * discovery + 0.05 * triage + 0.10 * risk_f1")
    lines.append("          + 0.15 * element_accuracy + 0.05 * invalidity")
    lines.append("          + 0.10 * (1 - FP_rate) + 0.50 * (1 - FN_rate)")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")


def _render_footer(lines: list[str], agg: dict[str, Any]) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(
        f"*Report generated by Praviar Pipeline Benchmark Framework on {now}. "
        f"Total tokens consumed: {agg.get('total_tokens', 0):,}.*"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def _pass_fail_icon(name: str, value: float, target: str) -> str:
    """Return a pass/fail indicator based on the target."""
    # Parse the target to extract the threshold
    lower_name = name.lower()
    if "false" in lower_name and "negative" in lower_name:
        return "PASS" if value < 0.05 else "FAIL"
    elif "false" in lower_name and "positive" in lower_name:
        return "PASS" if value < 0.20 else "WARN"
    else:
        # Higher is better
        if ">=" in target:
            threshold = float(target.split(">=")[-1].strip())
            return "PASS" if value >= threshold else "FAIL"
        return ""


def _format_optional_score(value: Any) -> str:
    """Format an optional review score in report tables."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for report generation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Praviar Pipeline benchmark validation report.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Path to benchmark results directory containing aggregate_scores.json.",
    )
    parser.add_argument(
        "--aggregate-json",
        type=Path,
        help="Direct path to aggregate_scores.json.",
    )
    parser.add_argument(
        "--previous-run",
        type=Path,
        help="Path to previous run's aggregate_scores.json for regression comparison.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for the markdown report. Defaults to <results-dir>/benchmark_report.md.",
    )

    args = parser.parse_args()

    # Load aggregate scores
    if args.aggregate_json:
        aggregate_path = args.aggregate_json
    elif args.results_dir:
        aggregate_path = args.results_dir / "aggregate_scores.json"
    else:
        parser.error("Either --results-dir or --aggregate-json is required.")

    if not aggregate_path.exists():
        parser.error(f"Aggregate scores file not found: {aggregate_path}")

    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))

    # Load previous run if provided
    previous = None
    if args.previous_run and args.previous_run.exists():
        previous = json.loads(args.previous_run.read_text(encoding="utf-8"))

    # Determine output paths
    results_dir = args.results_dir or aggregate_path.parent
    report_path = args.output or results_dir / "benchmark_report.md"
    charts_path = results_dir / "charts_data.json"

    # Generate report
    generate_markdown_report(aggregate, report_path, previous_run=previous)
    print(f"Markdown report written to: {report_path}")

    # Generate charts JSON
    generate_charts_json(aggregate, charts_path)
    print(f"Charts JSON written to: {charts_path}")

    # Print summary
    print()
    print(f"Composite score: {aggregate.get('mean_composite_score', 0):.1%}")
    print(f"False negative rate: {aggregate.get('mean_false_negative_rate', 0):.1%}")
    print(f"Total cost: ${aggregate.get('total_cost_usd', 0):.2f}")


if __name__ == "__main__":
    main()
