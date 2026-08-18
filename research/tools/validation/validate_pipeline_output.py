"""Validate actual pipeline output against reconciled ground truth.

Compares a pipeline JSON report against expected results for a compound,
scoring search recall, triage recall, risk accuracy, and composite metrics.
Reports per-step metrics and overall PASS/FAIL against configured research
thresholds. Passing those thresholds does not establish legal accuracy.

Usage:
    python validate_pipeline_output.py output.json sofosbuvir
    python validate_pipeline_output.py output.json sofosbuvir --gt-dir ../ground-truth-extraction
    python validate_pipeline_output.py output.json sofosbuvir --verbose
    python validate_pipeline_output.py output.json sofosbuvir --json-output results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Patent ID normalization (mirrored from metrics.py)
# ---------------------------------------------------------------------------


def normalize_patent_id(pid: str) -> str:
    """Normalize patent ID: strip spaces, uppercase, remove kind code."""
    pid = pid.strip().upper().replace(" ", "").replace("-", "").replace(",", "")
    pid = re.sub(r"(?<=\d)[A-Z]\d*$", "", pid)
    return pid


def _ids_match(a: str, b: str) -> bool:
    return normalize_patent_id(a) == normalize_patent_id(b)


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

RESEARCH_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = RESEARCH_ROOT / "validation"
DEFAULT_GT_DIR = VALIDATION_DIR / "ground-truth-extraction"
EXPECTED_RESULTS_PATH = (
    Path(__file__).resolve().parent / "expected_pipeline_results.json"
)

RISK_ORDER = {"high": 3, "critical": 3, "medium": 2, "low": 1, "clear": 0, "none": 0}


def load_pipeline_output(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_ground_truth(compound_name: str, gt_dir: Path) -> dict:
    gt_path = gt_dir / compound_name.lower() / "reconciled" / "ground_truth.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")
    with open(gt_path) as f:
        return json.load(f)


def load_expected_results(compound_name: str) -> dict:
    with open(EXPECTED_RESULTS_PATH) as f:
        data = json.load(f)
    for compound in data["compounds"]:
        if compound["name"].lower() == compound_name.lower():
            return compound
    raise ValueError(
        f"Compound '{compound_name}' not found in expected_pipeline_results.json. "
        f"Available: {[c['name'] for c in data['compounds']]}"
    )


# ---------------------------------------------------------------------------
# Metric 1: Search Recall
# ---------------------------------------------------------------------------


def compute_search_recall(
    report: dict,
    expected: dict,
    verbose: bool = False,
) -> dict:
    """What fraction of expected blocking patents did the pipeline discover?

    A patent counts as 'found' if the pipeline report contains it (in
    patent_analyses, triage audit, or patent_details) by patent_id or any
    of its US family members.
    """
    # Collect all patent IDs the pipeline discovered (any step)
    discovered: set[str] = set()

    # From patent_analyses
    for a in report.get("patent_analyses", []):
        pid = a.get("patent_id", "")
        if pid:
            discovered.add(normalize_patent_id(pid))

    # From triage audit (includes rejected patents)
    for entry in report.get("audit_trail", {}).get("triage_audit", []):
        pid = entry.get("patent_id", "")
        if pid:
            discovered.add(normalize_patent_id(pid))

    # From patent_details if present
    for pid in report.get("patent_details", {}).keys():
        discovered.add(normalize_patent_id(pid))

    # From search funnel
    for entry in report.get("audit_trail", {}).get("search_funnel", []):
        pid = entry.get("patent_id", "")
        if pid:
            discovered.add(normalize_patent_id(pid))

    blocking = expected.get("expected_blocking_patents", [])
    found = 0
    missed: list[str] = []
    found_list: list[str] = []

    for bp in blocking:
        patent_id = bp["patent_id"]
        family = bp.get("us_family_members", [])
        all_ids = [patent_id] + family

        match = False
        for candidate in all_ids:
            if normalize_patent_id(candidate) in discovered:
                match = True
                break

        if match:
            found += 1
            found_list.append(patent_id)
        else:
            missed.append(patent_id)

    total = len(blocking)
    recall = found / total if total > 0 else 1.0

    result = {
        "metric": "search_recall",
        "score": round(recall, 4),
        "found": found,
        "total": total,
        "threshold": expected.get("minimum_search_recall", 0.95),
        "passed": recall >= expected.get("minimum_search_recall", 0.95),
    }
    if verbose:
        result["found_patents"] = found_list
        result["missed_patents"] = missed
        result["pipeline_discovered_count"] = len(discovered)

    return result


# ---------------------------------------------------------------------------
# Metric 2: Triage Recall
# ---------------------------------------------------------------------------


def compute_triage_recall(
    report: dict,
    expected: dict,
    verbose: bool = False,
) -> dict:
    """What fraction of expected blocking patents survived triage?

    A patent that was triaged out (rejected as not relevant) is a false
    negative. Only patents that actually made it to analysis count.
    """
    analyzed_ids: set[str] = set()
    for a in report.get("patent_analyses", []):
        pid = a.get("patent_id", "")
        if pid:
            analyzed_ids.add(normalize_patent_id(pid))

    blocking = expected.get("expected_blocking_patents", [])
    # Filter to patents that are currently blocking or have non-clear risk
    active_blocking = [
        bp
        for bp in blocking
        if bp.get("blocking_status") not in ("formerly_blocking", "expired")
        or bp.get("expected_risk_level", "").lower() not in ("clear",)
    ]

    # If all patents are expired/clear, triage recall = skip or perfect
    if not active_blocking:
        return {
            "metric": "triage_recall",
            "score": 1.0,
            "found": 0,
            "total": 0,
            "threshold": expected.get("minimum_triage_recall", 1.0),
            "passed": True,
            "note": "No currently-blocking patents to triage",
        }

    survived = 0
    triaged_out: list[str] = []
    survived_list: list[str] = []

    for bp in active_blocking:
        patent_id = bp["patent_id"]
        family = bp.get("us_family_members", [])
        all_ids = [patent_id] + family

        match = False
        for candidate in all_ids:
            if normalize_patent_id(candidate) in analyzed_ids:
                match = True
                break

        if match:
            survived += 1
            survived_list.append(patent_id)
        else:
            triaged_out.append(patent_id)

    total = len(active_blocking)
    recall = survived / total if total > 0 else 1.0

    result = {
        "metric": "triage_recall",
        "score": round(recall, 4),
        "found": survived,
        "total": total,
        "threshold": expected.get("minimum_triage_recall", 1.0),
        "passed": recall >= expected.get("minimum_triage_recall", 1.0),
    }
    if verbose:
        result["survived_patents"] = survived_list
        result["triaged_out_patents"] = triaged_out

    return result


# ---------------------------------------------------------------------------
# Metric 3: Risk Accuracy
# ---------------------------------------------------------------------------


def compute_risk_accuracy(
    report: dict,
    expected: dict,
    gt: dict,
    verbose: bool = False,
) -> dict:
    """Per-patent risk level accuracy for patents that were analyzed.

    Compares expected_risk_level from GT against the pipeline's risk_level
    for each blocking patent found and analyzed.
    """
    analyses = report.get("patent_analyses", [])

    def _find_analysis(patent_id: str, family: list[str]) -> dict | None:
        all_ids = [patent_id] + family
        for candidate in all_ids:
            norm = normalize_patent_id(candidate)
            for a in analyses:
                if normalize_patent_id(a.get("patent_id", "")) == norm:
                    return a
        return None

    blocking = expected.get("expected_blocking_patents", [])
    correct = 0
    total = 0
    details: list[dict] = []

    for bp in blocking:
        patent_id = bp["patent_id"]
        family = bp.get("us_family_members", [])
        expected_risk = bp.get("expected_risk_level", "").lower()
        if not expected_risk:
            continue

        analysis = _find_analysis(patent_id, family)
        if not analysis:
            continue

        predicted_risk = analysis.get("risk_level", "").lower()
        is_correct = predicted_risk == expected_risk

        # Allow adjacent risk levels as partial credit
        expected_ord = RISK_ORDER.get(expected_risk, -1)
        predicted_ord = RISK_ORDER.get(predicted_risk, -1)
        is_adjacent = abs(expected_ord - predicted_ord) <= 1

        if is_correct:
            correct += 1
        total += 1

        if verbose:
            details.append(
                {
                    "patent_id": patent_id,
                    "expected": expected_risk,
                    "predicted": predicted_risk,
                    "correct": is_correct,
                    "adjacent": is_adjacent,
                }
            )

    accuracy = correct / total if total > 0 else -1.0

    result = {
        "metric": "risk_accuracy",
        "score": round(accuracy, 4) if accuracy >= 0 else -1.0,
        "correct": correct,
        "total": total,
        "threshold": expected.get("minimum_risk_accuracy", 0.85),
        "passed": accuracy >= expected.get("minimum_risk_accuracy", 0.85)
        if accuracy >= 0
        else False,
    }
    if verbose:
        result["details"] = details

    return result


# ---------------------------------------------------------------------------
# Metric 4: Overall Risk Match
# ---------------------------------------------------------------------------


def compute_overall_risk_match(
    report: dict,
    expected: dict,
) -> dict:
    """Does the pipeline's overall risk match the expected risk?"""
    pipeline_risk = report.get("risk_summary", {}).get("overall_risk", "").lower()
    expected_risk = expected.get("expected_overall_risk", "").lower()
    acceptable = [
        r.lower() for r in expected.get("acceptable_overall_risks", [expected_risk])
    ]

    return {
        "metric": "overall_risk_match",
        "pipeline_risk": pipeline_risk,
        "expected_risk": expected_risk,
        "acceptable_risks": acceptable,
        "passed": pipeline_risk in acceptable,
    }


# ---------------------------------------------------------------------------
# Metric 5: Critical Patent Detection
# ---------------------------------------------------------------------------


def compute_critical_patent_detection(
    report: dict,
    expected: dict,
    verbose: bool = False,
) -> dict:
    """Did the pipeline find ALL critical must-find patents?"""
    critical = expected.get("critical_patents_must_find", [])
    if not critical:
        return {
            "metric": "critical_patent_detection",
            "score": 1.0,
            "found": 0,
            "total": 0,
            "passed": True,
            "note": "No critical patents defined for this compound",
        }

    # Collect all patent IDs the pipeline analyzed
    analyzed_ids: set[str] = set()
    for a in report.get("patent_analyses", []):
        pid = a.get("patent_id", "")
        if pid:
            analyzed_ids.add(normalize_patent_id(pid))

    found = 0
    missed: list[str] = []
    for pid in critical:
        if normalize_patent_id(pid) in analyzed_ids:
            found += 1
        else:
            missed.append(pid)

    total = len(critical)
    score = found / total if total > 0 else 1.0

    result = {
        "metric": "critical_patent_detection",
        "score": round(score, 4),
        "found": found,
        "total": total,
        "passed": found == total,
    }
    if verbose:
        result["missed_critical"] = missed

    return result


# ---------------------------------------------------------------------------
# Metric 6: False Negative Rate
# ---------------------------------------------------------------------------


def compute_false_negative_rate(
    report: dict,
    expected: dict,
    verbose: bool = False,
) -> dict:
    """Fraction of currently-blocking patents missed or under-rated.

    A patent is a false negative if:
    1. Not discovered at all
    2. Discovered but triaged out
    3. Analyzed but rated LOW/CLEAR when expected HIGH/MEDIUM
    """
    blocking = expected.get("expected_blocking_patents", [])

    # Filter to currently blocking patents with HIGH or MEDIUM expected risk
    active = [
        bp
        for bp in blocking
        if bp.get("blocking_status") in ("currently_blocking", "active")
        and bp.get("expected_risk_level", "").lower() in ("high", "medium", "critical")
    ]

    if not active:
        return {
            "metric": "false_negative_rate",
            "score": 0.0,
            "missed": 0,
            "total": 0,
            "passed": True,
            "note": "No currently-blocking HIGH/MEDIUM patents to evaluate",
        }

    # All discovered IDs
    discovered: set[str] = set()
    for a in report.get("patent_analyses", []):
        discovered.add(normalize_patent_id(a.get("patent_id", "")))
    for entry in report.get("audit_trail", {}).get("triage_audit", []):
        discovered.add(normalize_patent_id(entry.get("patent_id", "")))
    for pid in report.get("patent_details", {}).keys():
        discovered.add(normalize_patent_id(pid))

    analyzed_ids: set[str] = set()
    for a in report.get("patent_analyses", []):
        analyzed_ids.add(normalize_patent_id(a.get("patent_id", "")))

    analyses = report.get("patent_analyses", [])
    missed = 0
    fn_details: list[dict] = []

    for bp in active:
        patent_id = bp["patent_id"]
        family = bp.get("us_family_members", [])
        all_ids = [patent_id] + family
        expected_risk = bp.get("expected_risk_level", "").lower()

        # Check discovery
        found_in_discovery = any(normalize_patent_id(c) in discovered for c in all_ids)
        if not found_in_discovery:
            missed += 1
            if verbose:
                fn_details.append({"patent_id": patent_id, "reason": "not_discovered"})
            continue

        # Check analysis
        found_in_analysis = any(normalize_patent_id(c) in analyzed_ids for c in all_ids)
        if not found_in_analysis:
            missed += 1
            if verbose:
                fn_details.append({"patent_id": patent_id, "reason": "triaged_out"})
            continue

        # Check risk level
        for candidate in all_ids:
            norm = normalize_patent_id(candidate)
            for a in analyses:
                if normalize_patent_id(a.get("patent_id", "")) == norm:
                    predicted = a.get("risk_level", "").lower()
                    if predicted in ("low", "clear", "none") and expected_risk in (
                        "high",
                        "medium",
                        "critical",
                    ):
                        missed += 1
                        if verbose:
                            fn_details.append(
                                {
                                    "patent_id": patent_id,
                                    "reason": "under_rated",
                                    "predicted": predicted,
                                    "expected": expected_risk,
                                }
                            )
                    break

    total = len(active)
    rate = missed / total if total > 0 else 0.0

    result = {
        "metric": "false_negative_rate",
        "score": round(rate, 4),
        "missed": missed,
        "total": total,
        "passed": rate == 0.0,
    }
    if verbose:
        result["details"] = fn_details

    return result


# ---------------------------------------------------------------------------
# Composite Score (mirrors metrics.py weighting)
# ---------------------------------------------------------------------------


def compute_composite_score(
    search_recall: float,
    triage_recall: float,
    risk_accuracy: float,
    false_negative_rate: float,
) -> float:
    """Weighted composite score matching metrics.py formula.

    Weights:
        0.10 * search_recall (discovery + triage approximation)
        0.10 * risk_accuracy
        0.50 * (1 - false_negative_rate)
        0.05 * triage_recall
    Remaining weight (element accuracy, invalidity) not computable without
    full GT claim data, so we renormalize over available metrics.
    """
    components: list[tuple[float, float]] = []

    if search_recall >= 0:
        components.append((0.10, search_recall))
    if triage_recall >= 0:
        components.append((0.05, triage_recall))
    if risk_accuracy >= 0:
        components.append((0.10, risk_accuracy))
    if false_negative_rate >= 0:
        components.append((0.50, 1.0 - false_negative_rate))

    total_weight = sum(w for w, _ in components)
    if total_weight == 0:
        return -1.0

    weighted_sum = sum(w * s for w, s in components)
    return round(weighted_sum / total_weight, 4)


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def validate(
    report: dict,
    compound_name: str,
    gt_dir: Path,
    verbose: bool = False,
) -> dict:
    """Run all validation metrics and return structured results."""
    gt = load_ground_truth(compound_name, gt_dir)
    expected = load_expected_results(compound_name)

    search = compute_search_recall(report, expected, verbose=verbose)
    triage = compute_triage_recall(report, expected, verbose=verbose)
    risk = compute_risk_accuracy(report, expected, gt, verbose=verbose)
    overall = compute_overall_risk_match(report, expected)
    critical = compute_critical_patent_detection(report, expected, verbose=verbose)
    fnr = compute_false_negative_rate(report, expected, verbose=verbose)

    composite = compute_composite_score(
        search_recall=search["score"],
        triage_recall=triage["score"],
        risk_accuracy=risk["score"] if risk["score"] >= 0 else -1.0,
        false_negative_rate=fnr["score"],
    )

    min_composite = expected.get("minimum_composite_score", 0.85)
    composite_passed = composite >= min_composite if composite >= 0 else False

    all_passed = all(
        [
            search["passed"],
            triage["passed"],
            risk["passed"] if risk["score"] >= 0 else True,
            overall["passed"],
            critical["passed"],
            fnr["passed"],
            composite_passed,
        ]
    )

    return {
        "compound": compound_name,
        "compound_type": expected.get("compound_type", "unknown"),
        "pipeline_report_id": report.get("report_id", "unknown"),
        "overall_verdict": "PASS" if all_passed else "FAIL",
        "composite_score": composite,
        "composite_threshold": min_composite,
        "composite_passed": composite_passed,
        "metrics": {
            "search_recall": search,
            "triage_recall": triage,
            "risk_accuracy": risk,
            "overall_risk_match": overall,
            "critical_patent_detection": critical,
            "false_negative_rate": fnr,
        },
        "summary": _build_summary(
            compound_name,
            all_passed,
            composite,
            search,
            triage,
            risk,
            overall,
            critical,
            fnr,
        ),
    }


def _build_summary(
    compound: str,
    all_passed: bool,
    composite: float,
    search: dict,
    triage: dict,
    risk: dict,
    overall: dict,
    critical: dict,
    fnr: dict,
) -> str:
    verdict = "PASS" if all_passed else "FAIL"
    lines = [
        f"=== Validation Report: {compound} ===",
        f"Overall Verdict: {verdict}",
        f"Composite Score: {composite:.4f} (threshold: {search.get('threshold', 'N/A')})",
        "",
        "Per-Step Metrics:",
        f"  Search Recall:     {search['score']:.4f}  ({search['found']}/{search['total']})  "
        f"{'PASS' if search['passed'] else 'FAIL'}  (min: {search['threshold']})",
        f"  Triage Recall:     {triage['score']:.4f}  ({triage['found']}/{triage['total']})  "
        f"{'PASS' if triage['passed'] else 'FAIL'}  (min: {triage['threshold']})",
    ]

    if risk["score"] >= 0:
        lines.append(
            f"  Risk Accuracy:     {risk['score']:.4f}  ({risk['correct']}/{risk['total']})  "
            f"{'PASS' if risk['passed'] else 'FAIL'}  (min: {risk['threshold']})"
        )
    else:
        lines.append("  Risk Accuracy:     N/A  (no patents available for comparison)")

    lines.extend(
        [
            f"  Overall Risk:      {overall['pipeline_risk'].upper() or 'N/A'}  "
            f"(expected: {overall['expected_risk'].upper()})  "
            f"{'PASS' if overall['passed'] else 'FAIL'}",
            f"  Critical Patents:  {critical['found']}/{critical['total']}  "
            f"{'PASS' if critical['passed'] else 'FAIL'}",
            f"  False Neg Rate:    {fnr['score']:.4f}  ({fnr['missed']}/{fnr['total']})  "
            f"{'PASS' if fnr['passed'] else 'FAIL'}  (target: 0.0)",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate pipeline output against ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "report_path",
        type=Path,
        help="Path to pipeline output JSON file",
    )
    parser.add_argument(
        "compound",
        type=str,
        help="Compound name (sofosbuvir, ritonavir, adalimumab, fingolimod, nirmatrelvir)",
    )
    parser.add_argument(
        "--gt-dir",
        type=Path,
        default=DEFAULT_GT_DIR,
        help="Path to ground-truth-extraction directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include per-patent detail in output",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write structured JSON results to file",
    )

    args = parser.parse_args()

    if not args.report_path.exists():
        print(f"ERROR: Report file not found: {args.report_path}", file=sys.stderr)
        sys.exit(1)

    report = load_pipeline_output(args.report_path)
    results = validate(report, args.compound, args.gt_dir, verbose=args.verbose)

    # Print human-readable summary
    print(results["summary"])
    print()

    if args.json_output:
        with open(args.json_output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"JSON results written to: {args.json_output}")

    # Exit code: 0 = PASS, 1 = FAIL
    sys.exit(0 if results["overall_verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
