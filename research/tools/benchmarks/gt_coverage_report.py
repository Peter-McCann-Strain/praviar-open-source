#!/usr/bin/env python3
"""Ground truth coverage report for Praviar Pipeline benchmark validation.

Analyzes enriched ground truth files and produces a coverage matrix showing:
- Which scoring dimensions can be evaluated deterministically per case
- Which cases need LLM judge or expert review
- Coverage gaps by benchmark source, difficulty, and scoring dimension
- Actionable recommendations for improving ground truth quality

Usage:
    # Generate coverage report (text)
    python research/tools/benchmarks/gt_coverage_report.py

    # Generate JSON report
    python research/tools/benchmarks/gt_coverage_report.py --json

    # Output to file
    python research/tools/benchmarks/gt_coverage_report.py --output coverage_report.json --json

    # Analyze a single enriched file
    python research/tools/benchmarks/gt_coverage_report.py --file enriched/paragraph_iv_enriched.json

    # Also analyze unenriched benchmark files to show what enrichment adds
    python research/tools/benchmarks/gt_coverage_report.py --include-raw
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gt_coverage")

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = REPO_ROOT / "research" / "benchmarks"
ENRICHED_DIR = BENCHMARKS_DIR / "enriched"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

SCORING_DIMENSIONS = [
    "discovery",
    "triage",
    "risk_classification",
    "claim_elements",
    "invalidity",
    "doe",
    "patent_term",
    "false_positive",
    "false_negative",
]


@dataclass
class CaseCoverage:
    """Coverage analysis for a single enriched case."""

    case_id: str
    compound_name: str
    source: str
    difficulty: str
    confidence: str
    needs_expert_review: bool
    scoring_capabilities: dict[str, bool] = field(default_factory=dict)
    requires_llm_judge: list[str] = field(default_factory=list)
    blocking_patent_count: int = 0
    non_blocking_patent_count: int = 0
    total_expected_claims: int = 0
    total_expected_elements: int = 0
    has_invalidity_gt: bool = False
    has_doe_gt: bool = False
    has_expiry_dates: bool = False
    has_ptab_gt: bool = False


@dataclass
class SourceCoverage:
    """Aggregated coverage for one benchmark source."""

    source: str
    total_cases: int = 0
    by_difficulty: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_confidence: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dimension_coverage: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    needs_expert_review: int = 0
    needs_llm_judge: int = 0
    total_blocking_patents: int = 0
    total_expected_claims: int = 0
    total_expected_elements: int = 0
    cases_with_invalidity: int = 0
    cases_with_doe: int = 0
    cases_with_ptab: int = 0
    cases_with_expiry: int = 0


@dataclass
class CoverageReport:
    """Complete coverage report across all enriched ground truth."""

    total_cases: int = 0
    total_enriched_files: int = 0
    by_source: dict[str, SourceCoverage] = field(default_factory=dict)
    by_difficulty: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_confidence: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dimension_totals: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dimension_pct: dict[str, float] = field(default_factory=dict)
    cases_needing_expert_review: int = 0
    cases_needing_llm_judge: int = 0
    llm_judge_dimension_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    case_details: list[CaseCoverage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _analyze_case(case: dict[str, Any]) -> CaseCoverage:
    """Analyze coverage of a single enriched case."""
    metadata = case.get("metadata", {})
    scoring = case.get("scoring_capabilities", {})
    expected = case.get("expected_outcome", {})
    blocking = expected.get("blocking_patents", [])
    non_blocking = expected.get("non_blocking_patents", [])

    # Count claims and elements
    total_claims = 0
    total_elements = 0
    has_invalidity = False
    has_doe = False
    has_ptab = False
    has_expiry = False

    for bp in blocking:
        for claim in bp.get("expected_claims", []):
            total_claims += 1
            total_elements += len(claim.get("expected_elements", []))

        if bp.get("expected_invalidity"):
            has_invalidity = True
            inv = bp["expected_invalidity"]
            if inv.get("ptab_proceeding") or inv.get("ptab_outcome"):
                has_ptab = True

        if bp.get("expected_doe"):
            has_doe = True

        if bp.get("expected_expiry"):
            has_expiry = True

    # Map scoring_capabilities to dimension names
    dim_map = {
        "can_score_discovery": "discovery",
        "can_score_triage": "triage",
        "can_score_risk_classification": "risk_classification",
        "can_score_claim_elements": "claim_elements",
        "can_score_invalidity": "invalidity",
        "can_score_doe": "doe",
        "can_score_patent_term": "patent_term",
        "can_score_false_positive": "false_positive",
        "can_score_false_negative": "false_negative",
    }

    capabilities: dict[str, bool] = {}
    for key, dim in dim_map.items():
        capabilities[dim] = scoring.get(key, False)

    return CaseCoverage(
        case_id=case.get("id", ""),
        compound_name=case.get("compound_name", ""),
        source=metadata.get("source", "unknown"),
        difficulty=metadata.get("difficulty", "unknown"),
        confidence=metadata.get("confidence_in_ground_truth", "unknown"),
        needs_expert_review=metadata.get("needs_expert_review", False),
        scoring_capabilities=capabilities,
        requires_llm_judge=scoring.get("requires_llm_judge", []),
        blocking_patent_count=len(blocking),
        non_blocking_patent_count=len(non_blocking),
        total_expected_claims=total_claims,
        total_expected_elements=total_elements,
        has_invalidity_gt=has_invalidity,
        has_doe_gt=has_doe,
        has_expiry_dates=has_expiry,
        has_ptab_gt=has_ptab,
    )


def _analyze_enriched_file(filepath: Path) -> list[CaseCoverage]:
    """Analyze all cases in an enriched file."""
    with open(filepath) as f:
        data = json.load(f)

    cases = data.get("cases", [])
    return [_analyze_case(c) for c in cases]


def build_coverage_report(
    enriched_dir: Path | None = None,
    single_file: Path | None = None,
) -> CoverageReport:
    """Build a complete coverage report from enriched ground truth files."""
    report = CoverageReport()

    if single_file:
        files = [single_file]
    elif enriched_dir and enriched_dir.exists():
        files = sorted(enriched_dir.glob("*.json"))
    else:
        log.error("No enriched files found at %s", enriched_dir)
        return report

    all_cases: list[CaseCoverage] = []

    for filepath in files:
        log.info("Analyzing %s", filepath.name)
        cases = _analyze_enriched_file(filepath)
        all_cases.extend(cases)
        report.total_enriched_files += 1

    report.total_cases = len(all_cases)
    report.case_details = all_cases

    # Aggregate by source
    for case in all_cases:
        source = case.source

        if source not in report.by_source:
            report.by_source[source] = SourceCoverage(source=source)
        sc = report.by_source[source]

        sc.total_cases += 1
        sc.by_difficulty[case.difficulty] += 1
        sc.by_confidence[case.confidence] += 1
        sc.total_blocking_patents += case.blocking_patent_count
        sc.total_expected_claims += case.total_expected_claims
        sc.total_expected_elements += case.total_expected_elements

        if case.needs_expert_review:
            sc.needs_expert_review += 1
            report.cases_needing_expert_review += 1

        if case.requires_llm_judge:
            sc.needs_llm_judge += 1
            report.cases_needing_llm_judge += 1
            for dim in case.requires_llm_judge:
                report.llm_judge_dimension_counts[dim] += 1

        if case.has_invalidity_gt:
            sc.cases_with_invalidity += 1
        if case.has_doe_gt:
            sc.cases_with_doe += 1
        if case.has_ptab_gt:
            sc.cases_with_ptab += 1
        if case.has_expiry_dates:
            sc.cases_with_expiry += 1

        for dim, can_score in case.scoring_capabilities.items():
            if can_score:
                sc.dimension_coverage[dim] += 1
                report.dimension_totals[dim] += 1

        report.by_difficulty[case.difficulty] += 1
        report.by_confidence[case.confidence] += 1

    # Compute dimension percentages
    if report.total_cases > 0:
        for dim in SCORING_DIMENSIONS:
            count = report.dimension_totals.get(dim, 0)
            report.dimension_pct[dim] = round(count / report.total_cases * 100, 1)

    # Identify gaps and generate recommendations
    report.gaps, report.recommendations = _identify_gaps(report)

    return report


def _identify_gaps(report: CoverageReport) -> tuple[list[str], list[str]]:
    """Identify coverage gaps and generate recommendations."""
    gaps: list[str] = []
    recommendations: list[str] = []

    total = report.total_cases
    if total == 0:
        gaps.append("No enriched cases found. Run enrich_ground_truth.py first.")
        recommendations.append("Run: python research/tools/benchmarks/enrich_ground_truth.py")
        return gaps, recommendations

    # Check each scoring dimension
    for dim in SCORING_DIMENSIONS:
        count = report.dimension_totals.get(dim, 0)
        pct = report.dimension_pct.get(dim, 0)

        if pct < 10:
            gaps.append(f"CRITICAL: {dim} coverage is {pct}% ({count}/{total} cases)")
        elif pct < 30:
            gaps.append(f"LOW: {dim} coverage is {pct}% ({count}/{total} cases)")
        elif pct < 60:
            gaps.append(f"MODERATE: {dim} coverage is {pct}% ({count}/{total} cases)")

    # DoE is always low — only DoE benchmark file has it
    doe_count = report.dimension_totals.get("doe", 0)
    if doe_count < 10:
        recommendations.append(
            f"DoE ground truth is very sparse ({doe_count} cases). "
            "Consider expert review of doe_estoppel_claim_construction cases to add "
            "Function-Way-Result test expectations."
        )

    # Claim elements
    claim_count = report.dimension_totals.get("claim_elements", 0)
    if claim_count < total * 0.4:
        recommendations.append(
            f"Only {claim_count}/{total} cases have structured claim element GT. "
            "Run with --llm flag to use Claude Haiku for parsing, or prioritize "
            "expert review of paragraph_iv and ptab cases."
        )

    # False positive coverage
    fp_count = report.dimension_totals.get("false_positive", 0)
    if fp_count < 5:
        recommendations.append(
            f"Only {fp_count} cases have non-blocking patent GT for false positive scoring. "
            "Add known non-blocking patents to enriched cases."
        )

    # Expert review needed
    if report.cases_needing_expert_review > total * 0.3:
        recommendations.append(
            f"{report.cases_needing_expert_review}/{total} cases need expert review. "
            "Prioritize high-value cases (patent_cliff, bpcia) first."
        )

    # Confidence distribution
    low_conf = report.by_confidence.get("low", 0)
    if low_conf > total * 0.2:
        recommendations.append(
            f"{low_conf} cases have low confidence GT. These should not be used "
            "for regression testing without expert verification."
        )

    # Source diversity
    if len(report.by_source) < 5:
        recommendations.append(
            f"Only {len(report.by_source)} benchmark sources enriched. "
            "Enrich all benchmark files for comprehensive coverage."
        )

    # LLM judge needs
    if report.cases_needing_llm_judge > total * 0.5:
        recommendations.append(
            f"{report.cases_needing_llm_judge}/{total} cases need LLM judge for "
            "some dimensions. Consider enriching claim elements to reduce this."
        )

    return gaps, recommendations


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _format_text_report(report: CoverageReport) -> str:
    """Format the coverage report as human-readable text."""
    lines: list[str] = []
    w = lines.append

    w("=" * 80)
    w("PRAVIAR_PIPELINE GROUND TRUTH COVERAGE REPORT")
    w("=" * 80)
    w("")
    w(f"Total enriched files:    {report.total_enriched_files}")
    w(f"Total benchmark cases:   {report.total_cases}")
    w(f"Need expert review:      {report.cases_needing_expert_review}")
    w(f"Need LLM judge:          {report.cases_needing_llm_judge}")
    w("")

    # Scoring dimension coverage matrix
    w("-" * 80)
    w("SCORING DIMENSION COVERAGE")
    w("-" * 80)
    w(f"{'Dimension':<25} {'Cases':>8} {'Coverage':>10} {'Status':<15}")
    w("-" * 80)

    for dim in SCORING_DIMENSIONS:
        count = report.dimension_totals.get(dim, 0)
        pct = report.dimension_pct.get(dim, 0)

        if pct >= 60:
            status = "GOOD"
        elif pct >= 30:
            status = "MODERATE"
        elif pct >= 10:
            status = "LOW"
        else:
            status = "CRITICAL"

        bar = "#" * int(pct / 2) + "." * (50 - int(pct / 2))
        w(f"  {dim:<23} {count:>6}   {pct:>6.1f}%   {status:<10}  [{bar}]")

    w("")

    # Confidence distribution
    w("-" * 80)
    w("CONFIDENCE DISTRIBUTION")
    w("-" * 80)
    for level in ("high", "medium", "low"):
        count = report.by_confidence.get(level, 0)
        pct = count / report.total_cases * 100 if report.total_cases else 0
        w(f"  {level:<10}  {count:>5} cases  ({pct:.1f}%)")
    w("")

    # Difficulty distribution
    w("-" * 80)
    w("DIFFICULTY DISTRIBUTION")
    w("-" * 80)
    for level in ("easy", "medium", "hard", "expert"):
        count = report.by_difficulty.get(level, 0)
        pct = count / report.total_cases * 100 if report.total_cases else 0
        w(f"  {level:<10}  {count:>5} cases  ({pct:.1f}%)")
    w("")

    # Per-source breakdown
    w("-" * 80)
    w("PER-SOURCE BREAKDOWN")
    w("-" * 80)

    for source_name in sorted(report.by_source.keys()):
        sc = report.by_source[source_name]
        w(f"\n  {source_name.upper()} ({sc.total_cases} cases)")
        w(f"    Blocking patents:    {sc.total_blocking_patents}")
        w(f"    Expected claims:     {sc.total_expected_claims}")
        w(f"    Expected elements:   {sc.total_expected_elements}")
        w(f"    With invalidity GT:  {sc.cases_with_invalidity}")
        w(f"    With DoE GT:         {sc.cases_with_doe}")
        w(f"    With PTAB GT:        {sc.cases_with_ptab}")
        w(f"    With expiry dates:   {sc.cases_with_expiry}")
        w(f"    Need expert review:  {sc.needs_expert_review}")
        w(f"    Need LLM judge:      {sc.needs_llm_judge}")

        # Dimension coverage for this source
        dim_parts = []
        for dim in SCORING_DIMENSIONS:
            cnt = sc.dimension_coverage.get(dim, 0)
            if cnt > 0:
                dim_parts.append(f"{dim}={cnt}")
        if dim_parts:
            w(f"    Scorable dims:       {', '.join(dim_parts)}")

    w("")

    # LLM judge requirements
    if report.llm_judge_dimension_counts:
        w("-" * 80)
        w("LLM JUDGE REQUIREMENTS (dimensions needing non-deterministic scoring)")
        w("-" * 80)
        for dim, count in sorted(report.llm_judge_dimension_counts.items(), key=lambda x: -x[1]):
            w(f"  {dim:<30} {count:>5} cases")
        w("")

    # Coverage gaps
    if report.gaps:
        w("-" * 80)
        w("COVERAGE GAPS")
        w("-" * 80)
        for gap in report.gaps:
            w(f"  * {gap}")
        w("")

    # Recommendations
    if report.recommendations:
        w("-" * 80)
        w("RECOMMENDATIONS")
        w("-" * 80)
        for i, rec in enumerate(report.recommendations, 1):
            w(f"  {i}. {rec}")
        w("")

    # Cases needing expert review (list top 20)
    expert_cases = [c for c in report.case_details if c.needs_expert_review]
    if expert_cases:
        w("-" * 80)
        w(f"CASES NEEDING EXPERT REVIEW (showing {min(20, len(expert_cases))}/{len(expert_cases)})")
        w("-" * 80)
        for case in expert_cases[:20]:
            dims_ok = sum(1 for v in case.scoring_capabilities.values() if v)
            dims_total = len(SCORING_DIMENSIONS)
            w(f"  {case.case_id:<20} {case.compound_name:<30} "
              f"[{case.source}] conf={case.confidence} dims={dims_ok}/{dims_total}")
        w("")

    w("=" * 80)
    return "\n".join(lines)


def _format_json_report(report: CoverageReport) -> dict[str, Any]:
    """Format the coverage report as JSON."""
    return {
        "summary": {
            "total_enriched_files": report.total_enriched_files,
            "total_cases": report.total_cases,
            "cases_needing_expert_review": report.cases_needing_expert_review,
            "cases_needing_llm_judge": report.cases_needing_llm_judge,
        },
        "dimension_coverage": {
            dim: {
                "count": report.dimension_totals.get(dim, 0),
                "percentage": report.dimension_pct.get(dim, 0),
                "status": (
                    "good" if report.dimension_pct.get(dim, 0) >= 60
                    else "moderate" if report.dimension_pct.get(dim, 0) >= 30
                    else "low" if report.dimension_pct.get(dim, 0) >= 10
                    else "critical"
                ),
            }
            for dim in SCORING_DIMENSIONS
        },
        "confidence_distribution": dict(report.by_confidence),
        "difficulty_distribution": dict(report.by_difficulty),
        "by_source": {
            name: {
                "total_cases": sc.total_cases,
                "blocking_patents": sc.total_blocking_patents,
                "expected_claims": sc.total_expected_claims,
                "expected_elements": sc.total_expected_elements,
                "with_invalidity": sc.cases_with_invalidity,
                "with_doe": sc.cases_with_doe,
                "with_ptab": sc.cases_with_ptab,
                "with_expiry": sc.cases_with_expiry,
                "needs_expert_review": sc.needs_expert_review,
                "needs_llm_judge": sc.needs_llm_judge,
                "dimension_coverage": dict(sc.dimension_coverage),
                "by_difficulty": dict(sc.by_difficulty),
                "by_confidence": dict(sc.by_confidence),
            }
            for name, sc in sorted(report.by_source.items())
        },
        "llm_judge_requirements": dict(report.llm_judge_dimension_counts),
        "gaps": report.gaps,
        "recommendations": report.recommendations,
        "coverage_matrix": [
            {
                "case_id": c.case_id,
                "compound_name": c.compound_name,
                "source": c.source,
                "difficulty": c.difficulty,
                "confidence": c.confidence,
                "needs_expert_review": c.needs_expert_review,
                "blocking_patents": c.blocking_patent_count,
                "expected_claims": c.total_expected_claims,
                "expected_elements": c.total_expected_elements,
                "has_invalidity_gt": c.has_invalidity_gt,
                "has_doe_gt": c.has_doe_gt,
                "has_ptab_gt": c.has_ptab_gt,
                "has_expiry_dates": c.has_expiry_dates,
                "deterministic_dims": {
                    dim: can for dim, can in c.scoring_capabilities.items()
                },
                "requires_llm_judge": c.requires_llm_judge,
            }
            for c in report.case_details
        ],
    }


# ---------------------------------------------------------------------------
# Raw benchmark analysis (optional)
# ---------------------------------------------------------------------------


def _analyze_raw_benchmarks(benchmarks_dir: Path) -> str:
    """Analyze unenriched benchmark files to show baseline coverage."""
    lines: list[str] = []
    w = lines.append

    w("")
    w("=" * 80)
    w("RAW BENCHMARK FILES (before enrichment)")
    w("=" * 80)

    total_cases = 0
    cases_with_smiles = 0
    cases_with_patents = 0
    cases_with_expiry = 0
    cases_with_claims = 0
    cases_with_invalidity_text = 0

    for filepath in sorted(benchmarks_dir.glob("*.json")):
        if filepath.name in ("benchmark_schema.json", "enriched_ground_truth_schema.json"):
            continue

        try:
            with open(filepath) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue

        # Extract cases
        cases: list[dict[str, Any]] = []
        if isinstance(data, list):
            cases = data
        elif isinstance(data, dict):
            for key in ("cases", "published_analyses", "entries"):
                if key in data and isinstance(data[key], list):
                    cases = data[key]
                    break

        if not cases:
            continue

        file_cases = len(cases)
        total_cases += file_cases

        has_smiles = 0
        has_patents = 0
        has_expiry = 0
        has_claims_data = 0
        has_invalidity = 0

        for case in cases:
            compound = case.get("compound", {})
            smiles = compound.get("smiles", "")
            if smiles and smiles.lower() not in ("", "n/a", "none"):
                has_smiles += 1
                cases_with_smiles += 1

            # Count patents
            patents = case.get("patents", case.get("patent", case.get("patent_thicket", {})))
            if patents:
                has_patents += 1
                cases_with_patents += 1

                # Check expiry
                patent_list = []
                if isinstance(patents, list):
                    patent_list = patents
                elif isinstance(patents, dict):
                    patent_list = patents.get("key_patents", [])
                    if not patent_list and patents.get("patent_number"):
                        patent_list = [patents]

                for p in patent_list:
                    if p.get("expiry_date") or p.get("expiry"):
                        has_expiry += 1
                        cases_with_expiry += 1
                        break

            # Check claims
            benchmark = case.get("benchmark", case.get("benchmark_value", {}))
            kce = benchmark.get("key_claim_elements", {})
            if kce.get("met") or kce.get("not_met"):
                has_claims_data += 1
                cases_with_claims += 1

            # Check invalidity text
            litigation = case.get("litigation", {})
            if litigation.get("invalidity_basis") or case.get("ptab_proceeding"):
                has_invalidity += 1
                cases_with_invalidity_text += 1

        w(f"\n  {filepath.name}")
        w(f"    Cases: {file_cases}  SMILES: {has_smiles}  Patents: {has_patents}  "
          f"Expiry: {has_expiry}  Claims: {has_claims_data}  Invalidity: {has_invalidity}")

    w(f"\n  TOTALS:")
    w(f"    Cases: {total_cases}")
    w(f"    With SMILES:          {cases_with_smiles} ({cases_with_smiles/total_cases*100:.0f}%)" if total_cases else "")
    w(f"    With patents:         {cases_with_patents} ({cases_with_patents/total_cases*100:.0f}%)" if total_cases else "")
    w(f"    With expiry dates:    {cases_with_expiry} ({cases_with_expiry/total_cases*100:.0f}%)" if total_cases else "")
    w(f"    With claim elements:  {cases_with_claims} ({cases_with_claims/total_cases*100:.0f}%)" if total_cases else "")
    w(f"    With invalidity text: {cases_with_invalidity_text} ({cases_with_invalidity_text/total_cases*100:.0f}%)" if total_cases else "")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze ground truth coverage and identify gaps in benchmark data.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of text.",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Write report to file instead of stdout.",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Analyze a single enriched file.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Also analyze unenriched benchmark files for comparison.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build report
    single_file = Path(args.file) if args.file else None
    if single_file and not single_file.is_absolute():
        single_file = BENCHMARKS_DIR / single_file

    report = build_coverage_report(
        enriched_dir=ENRICHED_DIR,
        single_file=single_file,
    )

    if report.total_cases == 0 and not single_file:
        log.warning(
            "No enriched files found in %s. Run enrich_ground_truth.py first.",
            ENRICHED_DIR,
        )
        # Still produce output showing what we know
        if args.include_raw:
            raw_analysis = _analyze_raw_benchmarks(BENCHMARKS_DIR)
            print(raw_analysis)
        else:
            print("No enriched ground truth files found.")
            print(f"Expected location: {ENRICHED_DIR}")
            print("Run: python research/tools/benchmarks/enrich_ground_truth.py")
        return 1

    # Format output
    if args.json:
        output = json.dumps(_format_json_report(report), indent=2)
    else:
        output = _format_text_report(report)
        if args.include_raw:
            output += _analyze_raw_benchmarks(BENCHMARKS_DIR)

    # Write or print
    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w") as f:
            f.write(output)
        log.info("Report written to %s", out_path)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
