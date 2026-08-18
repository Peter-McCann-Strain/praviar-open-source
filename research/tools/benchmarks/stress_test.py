"""Stress test: run 5 wildly different compounds through the full FTO pipeline.

Captures ALL intermediate outputs, timings, errors, and token usage per step.
Produces a detailed diagnostic report showing exactly what worked and what didn't.

Usage:
    python research/tools/benchmarks/stress_test.py
    python research/tools/benchmarks/stress_test.py --compound "aspirin"      # single compound
    python research/tools/benchmarks/stress_test.py --skip-llm                 # skip LLM-heavy steps (3-6, 8)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure the praviar_pipeline package is importable
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "praviar_pipeline" / "src"))

import structlog  # noqa: E402

# ── Logging setup ────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(
            exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False),
        ),
    ]
)
logger = structlog.get_logger()


# ── Compound definitions ────────────────────────────────────────────────────
# 5 wildly different compounds to stress test every part of the pipeline:
#
# 1. Succinic acid      — small organic acid (MW 118), bio-based chemicals, many fermentation patents
# 2. Semaglutide        — huge peptide drug (MW 4113), blockbuster GLP-1 agonist, complex patent landscape
# 3. Buckminsterfullerene (C60) — exotic carbon allotrope (MW 720), niche patents, unusual structure
# 4. Sodium chloride    — simple inorganic salt (MW 58), near-zero patent risk, tests "clear" path
# 5. Remdesivir         — antiviral nucleotide analog (MW 602), COVID drug, multi-jurisdictional patents

STRESS_TEST_COMPOUNDS = [
    {
        "input": "succinic acid",
        "description": "Small dicarboxylic acid — bio-based chemical with fermentation patents",
        "expected_complexity": "medium",
    },
    {
        "input": "semaglutide",
        "description": "Large peptide GLP-1 agonist — blockbuster drug, complex patent landscape",
        "expected_complexity": "high",
    },
    {
        "input": "C1=CC=CC=C1",  # benzene SMILES
        "description": "Benzene via SMILES — simple aromatic, tests SMILES input path",
        "expected_complexity": "low",
    },
    {
        "input": "7440-23-5",  # sodium CAS number
        "description": "Sodium via CAS number — elemental, tests CAS input + minimal patent risk",
        "expected_complexity": "low",
    },
    {
        "input": "remdesivir",
        "description": "Antiviral nucleotide analog — COVID drug with multi-jurisdictional patents",
        "expected_complexity": "high",
    },
]


# ── Per-step result capture ──────────────────────────────────────────────────


@dataclass
class StepResult:
    """Captures everything about one pipeline step's execution."""

    step_name: str
    status: str = "not_run"  # "success", "error", "skipped"
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    error_type: str = ""
    error_message: str = ""
    error_traceback: str = ""
    output_summary: dict = field(default_factory=dict)
    raw_output: dict | list | None = None  # serializable snapshot
    warnings: list[str] = field(default_factory=list)
    token_usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "error_traceback": self.error_traceback,
            "output_summary": self.output_summary,
            "warnings": self.warnings,
            "token_usage": self.token_usage,
        }


@dataclass
class CompoundResult:
    """Full diagnostic result for one compound."""

    compound_input: str
    description: str
    expected_complexity: str
    overall_status: str = "not_run"
    total_duration_seconds: float = 0.0
    steps: list[StepResult] = field(default_factory=list)
    compound_resolved: dict | None = None
    final_risk: str = ""
    total_patents_found: int = 0
    patents_after_triage: int = 0
    patents_analyzed: int = 0
    analysis_failures_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "compound_input": self.compound_input,
            "description": self.description,
            "expected_complexity": self.expected_complexity,
            "overall_status": self.overall_status,
            "total_duration_seconds": self.total_duration_seconds,
            "compound_resolved": self.compound_resolved,
            "final_risk": self.final_risk,
            "total_patents_found": self.total_patents_found,
            "patents_after_triage": self.patents_after_triage,
            "patents_analyzed": self.patents_analyzed,
            "analysis_failures_count": self.analysis_failures_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "steps": [s.to_dict() for s in self.steps],
        }


# ── Serialization helpers ────────────────────────────────────────────────────


def _safe_serialize(obj) -> dict | list | str | None:
    """Attempt to serialize a Pydantic model or list of models to dict."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_safe_serialize(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return str(obj)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Step runner ──────────────────────────────────────────────────────────────


async def _run_step(step_name: str, coro_fn, *args, **kwargs) -> tuple[StepResult, Any]:
    """Run a single pipeline step with full instrumentation.

    Returns (StepResult, raw_return_value).
    """
    result = StepResult(step_name=step_name)
    result.started_at = _now_iso()
    start = time.time()
    raw_return: Any = None

    try:
        logger.info(f"▶ {step_name}", status="starting")
        raw_return = await coro_fn(*args, **kwargs)
        result.status = "success"
        logger.info(f"✓ {step_name}", status="success", duration=f"{time.time() - start:.1f}s")
    except Exception as exc:
        result.status = "error"
        result.error_type = type(exc).__name__
        result.error_message = str(exc)[:2000]
        result.error_traceback = traceback.format_exc()
        logger.error(
            f"✗ {step_name}",
            status="error",
            error_type=type(exc).__name__,
            error=str(exc)[:500],
            exc_info=True,
        )
    finally:
        result.completed_at = _now_iso()
        result.duration_seconds = round(time.time() - start, 2)

    return result, raw_return


# ── Main pipeline runner per compound ────────────────────────────────────────


async def run_compound(compound_def: dict, output_dir: Path, skip_llm: bool = False) -> CompoundResult:
    """Run the full pipeline for one compound with comprehensive monitoring."""
    from praviar_pipeline.models.report import SourceHealth
    from praviar_pipeline.pipeline.step1_resolve import resolve_compound
    from praviar_pipeline.pipeline.step2_search import search_patents
    from praviar_pipeline.pipeline.step3_triage import triage_patents
    from praviar_pipeline.pipeline.step4_analyze import analyze_patents
    from praviar_pipeline.pipeline.step5_doe import assess_equivalents
    from praviar_pipeline.pipeline.step6_invalid import assess_invalidity
    from praviar_pipeline.pipeline.step7_verify import verify_analysis
    from praviar_pipeline.pipeline.step8_report import generate_report

    user_input = compound_def["input"]
    cr = CompoundResult(
        compound_input=user_input,
        description=compound_def["description"],
        expected_complexity=compound_def["expected_complexity"],
    )
    overall_start = time.time()

    logger.info("=" * 70)
    logger.info(f"COMPOUND: {user_input}", description=compound_def["description"])
    logger.info("=" * 70)

    # ── Step 1: Resolve ──────────────────────────────────────────────────
    step1, compound = await _run_step("step1_resolve", resolve_compound, user_input)

    if compound:
        step1.output_summary = {
            "name": compound.name,
            "pubchem_cid": compound.pubchem_cid,
            "canonical_smiles": compound.canonical_smiles,
            "molecular_weight": compound.molecular_weight,
            "molecular_formula": compound.molecular_formula,
            "synonyms_count": len(compound.synonyms),
            "cas_numbers": compound.cas_numbers,
            "functional_groups": compound.functional_groups,
            "related_compounds_count": len(compound.related_compounds),
            "inchi_key": compound.inchi_key,
        }
        cr.compound_resolved = step1.output_summary
        # Save full resolve output
        _save_step_output(output_dir, "step1_resolve", compound)
    else:
        step1.warnings.append("Compound resolution returned None — all subsequent steps will fail")
    cr.steps.append(step1)

    if not compound or step1.status == "error":
        cr.overall_status = "fatal_step1"
        cr.total_duration_seconds = round(time.time() - overall_start, 2)
        return cr

    # ── Step 2: Search ───────────────────────────────────────────────────
    step2, search_result = await _run_step("step2_search", search_patents, compound)

    patent_hits, source_health, search_funnel = [], SourceHealth(), []
    if search_result:
        patent_hits, source_health, search_funnel = search_result
        step2.output_summary = {
            "total_patents_found": len(patent_hits),
            "sources_queried": [e.source for e in source_health.entries],
            "sources_ok": [e.source for e in source_health.entries if e.status.value == "ok"],
            "sources_failed": [e.source for e in source_health.entries if e.status.value == "failed"],
            "sources_skipped": [e.source for e in source_health.entries if e.status.value == "skipped"],
            "funnel_entries": len(search_funnel),
            "match_types": _count_by(patent_hits, lambda p: p.match_type or "unknown"),
            "source_breakdown": _count_by_sources(patent_hits),
            "top_5_patents": [
                {"id": p.patent_id, "title": p.title[:80], "score": p.confidence_score}
                for p in sorted(patent_hits, key=lambda p: p.confidence_score, reverse=True)[:5]
            ],
        }
        if source_health.any_failed:
            step2.warnings.append(f"Failed sources: {source_health.failed_sources}")
        if source_health.all_failed:
            step2.warnings.append("ALL search sources failed!")
        cr.total_patents_found = len(patent_hits)
        _save_step_output(output_dir, "step2_search", {
            "patent_hits": [p.model_dump(mode="json") for p in patent_hits],
            "source_health": source_health.model_dump(mode="json"),
            "search_funnel_count": len(search_funnel),
        })
    cr.steps.append(step2)

    if not patent_hits:
        logger.warning("No patents found — skipping steps 3-6")
        cr.steps.append(StepResult(step_name="step3_triage", status="skipped"))
        cr.steps.append(StepResult(step_name="step4_analyze", status="skipped"))
        cr.steps.append(StepResult(step_name="step5_doe", status="skipped"))
        cr.steps.append(StepResult(step_name="step6_invalidity", status="skipped"))

        # Still run verification and report with empty data
        step7, verification = await _run_step(
            "step7_verify", _sync_wrapper, verify_analysis,
            [], [], [], patent_hits,
        )
        step7.output_summary = {"checks": 0, "all_passed": True}
        cr.steps.append(step7)
        cr.overall_status = "no_patents_found"
        cr.total_duration_seconds = round(time.time() - overall_start, 2)
        _save_compound_summary(output_dir, cr)
        return cr

    if skip_llm:
        logger.info("--skip-llm: skipping LLM-heavy steps 3-8")
        for name in ["step3_triage", "step4_analyze", "step5_doe", "step6_invalidity",
                      "step7_verify", "step8_report"]:
            cr.steps.append(StepResult(step_name=name, status="skipped"))
        cr.overall_status = "skipped_llm"
        cr.total_duration_seconds = round(time.time() - overall_start, 2)
        _save_compound_summary(output_dir, cr)
        return cr

    # ── Step 3: Triage ───────────────────────────────────────────────────
    step3, triage_result = await _run_step("step3_triage", triage_patents, patent_hits, compound)

    triage_results = []
    triage_in = triage_out = 0
    if triage_result:
        triage_results, triage_in, triage_out, _triage_failed = triage_result
        step3.output_summary = {
            "patents_triaged": len(patent_hits),
            "relevant_found": len(triage_results),
            "relevance_breakdown": _count_by(
                triage_results, lambda t: t.relevance.value if hasattr(t.relevance, "value") else str(t.relevance)
            ),
            "top_relevant": [
                {"id": t.patent_id, "relevance": str(t.relevance), "confidence": t.confidence}
                for t in triage_results[:5]
            ],
        }
        step3.token_usage = {"input_tokens": triage_in, "output_tokens": triage_out}
        cr.patents_after_triage = len(triage_results)
        cr.total_input_tokens += triage_in
        cr.total_output_tokens += triage_out
        _save_step_output(output_dir, "step3_triage", {
            "triage_results": [t.model_dump(mode="json") for t in triage_results],
            "token_usage": {"input": triage_in, "output": triage_out},
        })
    cr.steps.append(step3)

    # Map back to patent hits
    relevant_ids = {t.patent_id for t in triage_results}
    relevant_patents = [p for p in patent_hits if p.patent_id in relevant_ids]

    if not relevant_patents:
        logger.warning("No relevant patents after triage — skipping steps 4-6")
        for name in ["step4_analyze", "step5_doe", "step6_invalidity"]:
            cr.steps.append(StepResult(step_name=name, status="skipped"))

        step7, verification = await _run_step(
            "step7_verify", _sync_wrapper, verify_analysis,
            [], [], [], patent_hits,
        )
        cr.steps.append(step7)
        cr.overall_status = "no_relevant_patents"
        cr.total_duration_seconds = round(time.time() - overall_start, 2)
        _save_compound_summary(output_dir, cr)
        return cr

    # ── Step 4: Analyze ──────────────────────────────────────────────────
    step4, analyze_result = await _run_step(
        "step4_analyze", analyze_patents, relevant_patents, compound, triage_results,
    )

    analyses, analysis_failures = [], []
    if analyze_result:
        analyses, analysis_failures = analyze_result
        step4.output_summary = {
            "patents_analyzed": len(analyses),
            "failures": len(analysis_failures),
            "risk_breakdown": _count_by(analyses, lambda a: a.risk_level.value),
            "failure_details": [
                {"patent_id": f.patent_id, "error_type": f.error_type, "recoverable": f.recoverable}
                for f in analysis_failures
            ],
            "analyses_summary": [
                {
                    "patent_id": a.patent_id,
                    "risk_level": a.risk_level.value,
                    "claims_analyzed": len(a.claims_analyzed),
                    "tokens": a.input_tokens + a.output_tokens,
                }
                for a in analyses
            ],
        }
        if analysis_failures:
            step4.warnings.append(
                f"{len(analysis_failures)} patent(s) failed analysis: "
                + ", ".join(f.patent_id for f in analysis_failures)
            )
        cr.patents_analyzed = len(analyses)
        cr.analysis_failures_count = len(analysis_failures)
        _save_step_output(output_dir, "step4_analyze", {
            "analyses": [a.model_dump(mode="json") for a in analyses],
            "failures": [f.model_dump(mode="json") for f in analysis_failures],
        })
    cr.steps.append(step4)

    # ── Step 5: DoE ──────────────────────────────────────────────────────
    step5, doe_result = await _run_step("step5_doe", assess_equivalents, analyses, compound)

    doe_assessments = []
    doe_in = doe_out = 0
    if doe_result:
        doe_assessments, doe_in, doe_out = doe_result
        step5.output_summary = {
            "assessments": len(doe_assessments),
            "equivalents_found": sum(1 for d in doe_assessments if d.overall_equivalent),
            "estoppel_blocks": sum(1 for d in doe_assessments if d.estoppel and d.estoppel.estoppel_applies),
        }
        step5.token_usage = {"input_tokens": doe_in, "output_tokens": doe_out}
        cr.total_input_tokens += doe_in
        cr.total_output_tokens += doe_out
        _save_step_output(output_dir, "step5_doe", {
            "doe_assessments": [d.model_dump(mode="json") for d in doe_assessments],
            "token_usage": {"input": doe_in, "output": doe_out},
        })
    cr.steps.append(step5)

    # ── Step 6: Invalidity ───────────────────────────────────────────────
    step6, inv_result = await _run_step(
        "step6_invalidity", assess_invalidity, analyses, compound, patent_hits=patent_hits,
    )

    invalidity_assessments = []
    inv_in = inv_out = 0
    if inv_result:
        invalidity_assessments, inv_in, inv_out = inv_result
        step6.output_summary = {
            "assessments": len(invalidity_assessments),
            "strength_breakdown": _count_by(invalidity_assessments, lambda i: i.overall_invalidity_strength),
            "ptab_challenged": sum(1 for i in invalidity_assessments if i.ptab and i.ptab.has_been_challenged),
        }
        step6.token_usage = {"input_tokens": inv_in, "output_tokens": inv_out}
        cr.total_input_tokens += inv_in
        cr.total_output_tokens += inv_out
        _save_step_output(output_dir, "step6_invalidity", {
            "invalidity_assessments": [i.model_dump(mode="json") for i in invalidity_assessments],
            "token_usage": {"input": inv_in, "output": inv_out},
        })
    cr.steps.append(step6)

    # ── Step 7: Verify (deterministic, no API calls) ─────────────────────
    step7, verification = await _run_step(
        "step7_verify", _sync_wrapper, verify_analysis,
        analyses, doe_assessments, invalidity_assessments, patent_hits,
    )

    if verification:
        step7.output_summary = {
            "total_checks": len(verification.checks),
            "passed_checks": sum(1 for c in verification.checks if c.passed),
            "failed_checks": sum(1 for c in verification.checks if not c.passed),
            "warning_checks": sum(1 for c in verification.checks if c.severity == "warning"),
            "all_passed": verification.all_passed,
            "check_details": [
                {
                    "name": c.check_name,
                    "passed": c.passed,
                    "severity": c.severity,
                    "details": c.details[:200],
                }
                for c in verification.checks
            ],
        }
        _save_step_output(output_dir, "step7_verify", {
            "verification": verification.model_dump(mode="json"),
        })
    cr.steps.append(step7)

    # ── Step 8: Report ───────────────────────────────────────────────────
    from praviar_pipeline.models.audit import StepTokenUsage

    prior_step_tokens = [
        StepTokenUsage(step_name="step3_triage", model_role="triage",
                       input_tokens=triage_in, output_tokens=triage_out),
        StepTokenUsage(step_name="step5_doe", model_role="analysis",
                       input_tokens=doe_in, output_tokens=doe_out),
        StepTokenUsage(step_name="step6_invalidity", model_role="analysis",
                       input_tokens=inv_in, output_tokens=inv_out),
    ]
    search_sources = list({s.value for p in patent_hits for s in p.sources})

    step8, report = await _run_step(
        "step8_report", generate_report,
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        verification=verification or _empty_verification(),
        total_patents_found=len(patent_hits),
        search_sources=search_sources,
        source_health=source_health,
        prior_llm_tokens=(triage_in + doe_in + inv_in, triage_out + doe_out + inv_out),
        prior_step_tokens=prior_step_tokens,
        analysis_failures=analysis_failures,
    )

    if report:
        step8.output_summary = {
            "report_id": report.report_id[:8],
            "overall_risk": report.risk_summary.overall_risk.value,
            "blocking_patents": report.risk_summary.blocking_patents_count,
            "executive_summary_length": len(report.risk_summary.executive_summary),
            "data_limitations": len(report.data_limitations),
            "analysis_failures_in_report": len(report.analysis_failures),
            "total_input_tokens": report.total_input_tokens,
            "total_output_tokens": report.total_output_tokens,
            "estimated_cost_usd": report.estimated_cost_usd,
        }
        step8.token_usage = {
            "total_input_tokens": report.total_input_tokens,
            "total_output_tokens": report.total_output_tokens,
            "estimated_cost_usd": report.estimated_cost_usd,
        }
        cr.final_risk = report.risk_summary.overall_risk.value
        cr.total_input_tokens = report.total_input_tokens
        cr.total_output_tokens = report.total_output_tokens

        # Save full report
        _save_step_output(output_dir, "step8_report_full", report)
    cr.steps.append(step8)

    # ── Final status ─────────────────────────────────────────────────────
    failed_steps = [s for s in cr.steps if s.status == "error"]
    if failed_steps:
        cr.overall_status = f"partial_failure ({len(failed_steps)} steps failed)"
    else:
        cr.overall_status = "success"

    cr.total_duration_seconds = round(time.time() - overall_start, 2)
    _save_compound_summary(output_dir, cr)
    return cr


# ── Helper functions ─────────────────────────────────────────────────────────


async def _sync_wrapper(fn, *args, **kwargs):
    """Wrap a synchronous function to run via _run_step."""
    return fn(*args, **kwargs)


def _empty_verification():
    from praviar_pipeline.models.verification import VerificationResult
    return VerificationResult()


def _count_by(items: list, key_fn) -> dict[str, int]:
    """Count items by a key function."""
    counts: dict[str, int] = {}
    for item in items:
        k = str(key_fn(item))
        counts[k] = counts.get(k, 0) + 1
    return counts


def _count_by_sources(patent_hits) -> dict[str, int]:
    """Count patents per source."""
    counts: dict[str, int] = {}
    for p in patent_hits:
        for s in p.sources:
            k = s.value if hasattr(s, "value") else str(s)
            counts[k] = counts.get(k, 0) + 1
    return counts


def _save_step_output(output_dir: Path, step_name: str, data) -> None:
    """Save step output as JSON."""
    path = output_dir / f"{step_name}.json"
    try:
        serializable = _safe_serialize(data) if not isinstance(data, (dict, list)) else data
        path.write_text(json.dumps(serializable, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not save {step_name} output", error=str(exc))


def _save_compound_summary(output_dir: Path, cr: CompoundResult) -> None:
    """Save compound summary."""
    path = output_dir / "compound_summary.json"
    path.write_text(json.dumps(cr.to_dict(), indent=2, default=str), encoding="utf-8")


# ── Summary report ───────────────────────────────────────────────────────────


def print_summary(results: list[CompoundResult], output_root: Path) -> None:
    """Print a comprehensive summary of all compound results."""
    print("\n")
    print("=" * 90)
    print("  STRESS TEST RESULTS SUMMARY")
    print("=" * 90)

    # Overall stats
    total = len(results)
    successes = sum(1 for r in results if r.overall_status == "success")
    failures = sum(1 for r in results if "failure" in r.overall_status or "fatal" in r.overall_status)
    print(f"\n  Compounds tested: {total}")
    print(f"  Fully successful: {successes}")
    print(f"  Partial/full failures: {failures}")
    print(f"  Results saved to: {output_root}")

    # Per-compound table
    print("\n" + "-" * 90)
    print(f"  {'Compound':<25} {'Status':<30} {'Risk':<10} {'Patents':<10} {'Time':<8} {'Tokens':<10}")
    print("-" * 90)

    for r in results:
        status_display = r.overall_status[:28]
        risk_display = r.final_risk or "n/a"
        patent_display = f"{r.total_patents_found}→{r.patents_after_triage}→{r.patents_analyzed}"
        time_display = f"{r.total_duration_seconds:.0f}s"
        token_display = f"{r.total_input_tokens + r.total_output_tokens:,}"
        print(f"  {r.compound_input:<25} {status_display:<30} {risk_display:<10} {patent_display:<10} {time_display:<8} {token_display:<10}")

    # Per-step breakdown
    print("\n" + "-" * 90)
    print("  STEP-BY-STEP BREAKDOWN")
    print("-" * 90)

    step_names = [
        "step1_resolve", "step2_search", "step3_triage", "step4_analyze",
        "step5_doe", "step6_invalidity", "step7_verify", "step8_report",
    ]

    for step_name in step_names:
        print(f"\n  {step_name}:")
        for r in results:
            step = next((s for s in r.steps if s.step_name == step_name), None)
            if not step:
                print(f"    {r.compound_input:<22} — not run")
                continue

            status_icon = {"success": "✓", "error": "✗", "skipped": "○"}.get(step.status, "?")
            line = f"    {status_icon} {r.compound_input:<22} {step.status:<10} {step.duration_seconds:.1f}s"

            if step.token_usage:
                tokens = step.token_usage.get("input_tokens", 0) + step.token_usage.get("output_tokens", 0)
                if tokens:
                    line += f"  [{tokens:,} tokens]"

            if step.warnings:
                line += f"  ⚠ {step.warnings[0][:50]}"

            if step.error_type:
                line += f"  [{step.error_type}: {step.error_message[:60]}]"

            print(line)

            # Print output summary highlights
            if step.output_summary:
                highlights = _format_highlights(step_name, step.output_summary)
                if highlights:
                    print(f"      └─ {highlights}")

    # Errors detail section
    all_errors = []
    for r in results:
        for s in r.steps:
            if s.status == "error":
                all_errors.append((r.compound_input, s.step_name, s.error_type, s.error_message))

    if all_errors:
        print("\n" + "-" * 90)
        print("  ERRORS (detailed)")
        print("-" * 90)
        for compound, step, err_type, err_msg in all_errors:
            print(f"\n  [{compound}] {step}:")
            print(f"    {err_type}: {err_msg[:200]}")

    # Warnings section
    all_warnings = []
    for r in results:
        for s in r.steps:
            for w in s.warnings:
                all_warnings.append((r.compound_input, s.step_name, w))

    if all_warnings:
        print("\n" + "-" * 90)
        print("  WARNINGS")
        print("-" * 90)
        for compound, step, warning in all_warnings:
            print(f"  [{compound}] {step}: {warning}")

    # Analysis failures
    total_analysis_failures = sum(r.analysis_failures_count for r in results)
    if total_analysis_failures:
        print(f"\n  ⚠ Total analysis failures across all compounds: {total_analysis_failures}")

    print("\n" + "=" * 90)
    print(f"  Full results: {output_root}")
    print("=" * 90 + "\n")

    # Save summary JSON
    summary_path = output_root / "summary.json"
    summary = {
        "timestamp": _now_iso(),
        "total_compounds": total,
        "successes": successes,
        "failures": failures,
        "total_errors": len(all_errors),
        "total_warnings": len(all_warnings),
        "total_analysis_failures": total_analysis_failures,
        "compounds": [r.to_dict() for r in results],
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"  Summary JSON: {summary_path}")


def _format_highlights(step_name: str, summary: dict) -> str:
    """Format key highlights from a step's output summary."""
    if step_name == "step1_resolve":
        return f"CID={summary.get('pubchem_cid')}, MW={summary.get('molecular_weight')}, groups={summary.get('functional_groups')}"
    if step_name == "step2_search":
        ok = summary.get("sources_ok", [])
        failed = summary.get("sources_failed", [])
        return f"patents={summary.get('total_patents_found')}, sources_ok={ok}, failed={failed}"
    if step_name == "step3_triage":
        return f"relevant={summary.get('relevant_found')}/{summary.get('patents_triaged')}, breakdown={summary.get('relevance_breakdown')}"
    if step_name == "step4_analyze":
        return f"analyzed={summary.get('patents_analyzed')}, failures={summary.get('failures')}, risks={summary.get('risk_breakdown')}"
    if step_name == "step5_doe":
        return f"assessments={summary.get('assessments')}, equivalents={summary.get('equivalents_found')}"
    if step_name == "step6_invalidity":
        return f"assessments={summary.get('assessments')}, strength={summary.get('strength_breakdown')}"
    if step_name == "step7_verify":
        return f"checks={summary.get('total_checks')}, passed={summary.get('passed_checks')}, warnings={summary.get('warning_checks')}"
    if step_name == "step8_report":
        return f"risk={summary.get('overall_risk')}, cost=${summary.get('estimated_cost_usd', 0):.4f}"
    return ""


# ── Entry point ──────────────────────────────────────────────────────────────


async def main(compounds: list[dict] | None = None, skip_llm: bool = False) -> None:
    """Run stress test on all compounds."""
    if compounds is None:
        compounds = STRESS_TEST_COMPOUNDS

    # Create timestamped output directory under praviar_pipeline/output/stress_tests/
    from praviar_pipeline.config import get_settings

    base_output = get_settings().resolved_output_dir / "stress_tests"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = base_output / timestamp
    output_root.mkdir(parents=True, exist_ok=True)

    logger.info("stress_test_start", compounds=len(compounds), output_dir=str(output_root))

    results: list[CompoundResult] = []
    for i, compound_def in enumerate(compounds, 1):
        logger.info(f"\n{'━' * 70}")
        logger.info(f"  COMPOUND {i}/{len(compounds)}: {compound_def['input']}")
        logger.info(f"{'━' * 70}\n")

        # Each compound gets its own output directory
        safe_name = compound_def["input"].replace(" ", "_").replace("/", "_")[:30]
        compound_dir = output_root / f"{i:02d}_{safe_name}"
        compound_dir.mkdir(parents=True, exist_ok=True)

        result = await run_compound(compound_def, compound_dir, skip_llm=skip_llm)
        results.append(result)

        # Brief pause between compounds to let connections settle
        if i < len(compounds):
            logger.info("Pausing 3s between compounds...")
            await asyncio.sleep(3)

    print_summary(results, output_root)


if __name__ == "__main__":
    args = sys.argv[1:]
    skip_llm = "--skip-llm" in args
    if skip_llm:
        args.remove("--skip-llm")

    compounds = None
    if "--compound" in args:
        idx = args.index("--compound")
        if idx + 1 < len(args):
            compound_name = args[idx + 1]
            compounds = [{
                "input": compound_name,
                "description": f"Single compound test: {compound_name}",
                "expected_complexity": "unknown",
            }]

    asyncio.run(main(compounds=compounds, skip_llm=skip_llm))
