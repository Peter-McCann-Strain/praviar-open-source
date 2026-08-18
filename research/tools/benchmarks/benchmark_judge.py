"""LLM-as-Judge evaluation module for Praviar Pipeline benchmark suite.

Evaluates the QUALITY of pipeline outputs that cannot be scored
deterministically — specifically claim analysis reasoning, invalidity
arguments, design-around suggestions, and overall legal soundness.

Uses Claude Haiku by default (cheap, fast, adequate for scoring). Each
evaluation produces structured JudgeScore objects with numeric scores,
per-dimension breakdowns, reasoning, and red-flag detection.

Usage:
    # Single case evaluation
    judge = BenchmarkJudge(model="claude-haiku-4-5-20251001")
    score = await judge.evaluate_claim_analysis(report_data, ground_truth)

    # Batch evaluation
    scores = await judge.evaluate_batch(cases)

    # Calibration (3 runs, measure variance)
    calibration = await judge.calibrate(report_data, ground_truth)

CLI:
    python benchmark_judge.py --benchmarks paragraph_iv_benchmarks.json \\
        --reports output/ --model claude-haiku-4-5-20251001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import structlog
from benchmark_judge_prompts import (
    JUDGE_DIMENSIONS,
    JUDGE_PROMPTS,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Cost tracking & model defaults — reads from centralized config when available,
# falls back to env vars / hardcoded defaults for standalone script use.
# ---------------------------------------------------------------------------

import os


def _no_paid_api_enabled() -> bool:
    return os.environ.get("NO_PAID_API", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_model_costs() -> dict[str, tuple[float, float]]:
    """Load model pricing from praviar_pipeline config if available, else use defaults."""
    try:
        from praviar_pipeline.config import get_settings

        s = get_settings()
        return {
            s.claude_triage_model: (
                s.cost_per_million_input_haiku,
                s.cost_per_million_output_haiku,
            ),
            s.claude_analysis_model: (
                s.cost_per_million_input_sonnet,
                s.cost_per_million_output_sonnet,
            ),
            s.claude_deep_model: (s.cost_per_million_input_opus, s.cost_per_million_output_opus),
        }
    except Exception:
        return {
            "claude-haiku-4-5-20251001": (1.00, 5.00),
            "claude-sonnet-4-6": (3.00, 15.00),
            "claude-opus-4-6": (5.00, 25.00),
        }


_MODEL_COSTS: dict[str, tuple[float, float]] = _load_model_costs()

DEFAULT_JUDGE_MODEL = os.environ.get("CLAUDE_TRIAGE_MODEL", "claude-haiku-4-5-20251001")
CALIBRATION_RUNS = 3
MAX_JUDGE_TOKENS = 4096
JUDGE_TEMPERATURE = 0.0


# ---------------------------------------------------------------------------
# Data classes for judge results
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension (1-5 scale)."""

    name: str
    score: int = 0
    reasoning: str = ""

    @property
    def normalized(self) -> float:
        """Convert 1-5 scale to 0-1 scale."""
        return max(0.0, (self.score - 1) / 4.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "normalized": round(self.normalized, 4),
            "reasoning": self.reasoning,
        }


@dataclass
class JudgeScore:
    """Complete judge evaluation for one dimension of one case."""

    judge_type: str  # claim_analysis, invalidity, design_around, legal_soundness
    case_id: str = ""
    patent_id: str = ""
    dimensions: list[DimensionScore] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    critical_errors: list[str] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    raw_response: str = ""

    # Cost tracking
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0

    @property
    def mean_dimension_score(self) -> float:
        """Mean normalized score across all dimensions."""
        if not self.dimensions:
            return 0.0
        return statistics.mean(d.normalized for d in self.dimensions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_type": self.judge_type,
            "case_id": self.case_id,
            "patent_id": self.patent_id,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "red_flags": self.red_flags,
            "critical_errors": self.critical_errors,
            "overall_score": round(self.overall_score, 4),
            "mean_dimension_score": round(self.mean_dimension_score, 4),
            "summary": self.summary,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "duration_seconds": round(self.duration_seconds, 2),
        }


@dataclass
class CaseJudgeResult:
    """All judge evaluations for a single benchmark case."""

    case_id: str
    compound_name: str = ""
    claim_scores: list[JudgeScore] = field(default_factory=list)
    invalidity_scores: list[JudgeScore] = field(default_factory=list)
    design_around_scores: list[JudgeScore] = field(default_factory=list)
    legal_soundness: JudgeScore | None = None

    @property
    def total_cost_usd(self) -> float:
        cost = sum(s.cost_usd for s in self.claim_scores)
        cost += sum(s.cost_usd for s in self.invalidity_scores)
        cost += sum(s.cost_usd for s in self.design_around_scores)
        if self.legal_soundness:
            cost += self.legal_soundness.cost_usd
        return cost

    @property
    def total_tokens(self) -> int:
        tokens = sum(s.input_tokens + s.output_tokens for s in self.claim_scores)
        tokens += sum(s.input_tokens + s.output_tokens for s in self.invalidity_scores)
        tokens += sum(s.input_tokens + s.output_tokens for s in self.design_around_scores)
        if self.legal_soundness:
            tokens += self.legal_soundness.input_tokens + self.legal_soundness.output_tokens
        return tokens

    @property
    def overall_quality_score(self) -> float:
        """Weighted average across all judge dimensions."""
        scores: list[tuple[str, float, float]] = []
        # Claim analysis: weight 0.35
        if self.claim_scores:
            claim_avg = statistics.mean(s.overall_score for s in self.claim_scores)
            scores.append(("claim", 0.35, claim_avg))
        # Invalidity: weight 0.25
        if self.invalidity_scores:
            inv_avg = statistics.mean(s.overall_score for s in self.invalidity_scores)
            scores.append(("invalidity", 0.25, inv_avg))
        # Design-around: weight 0.15
        if self.design_around_scores:
            da_avg = statistics.mean(s.overall_score for s in self.design_around_scores)
            scores.append(("design_around", 0.15, da_avg))
        # Legal soundness: weight 0.25
        if self.legal_soundness:
            scores.append(("legal", 0.25, self.legal_soundness.overall_score))

        if not scores:
            return 0.0

        total_weight = sum(w for _, w, _ in scores)
        if total_weight == 0:
            return 0.0
        return sum(w * val for _, w, val in scores) / total_weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "compound_name": self.compound_name,
            "claim_scores": [s.to_dict() for s in self.claim_scores],
            "invalidity_scores": [s.to_dict() for s in self.invalidity_scores],
            "design_around_scores": [s.to_dict() for s in self.design_around_scores],
            "legal_soundness": self.legal_soundness.to_dict() if self.legal_soundness else None,
            "overall_quality_score": round(self.overall_quality_score, 4),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
        }


@dataclass
class CalibrationResult:
    """Result of running the same case through the judge multiple times."""

    case_id: str
    judge_type: str
    num_runs: int = 0
    scores: list[float] = field(default_factory=list)
    mean_score: float = 0.0
    std_dev: float = 0.0
    variance: float = 0.0
    is_stable: bool = False  # variance < 0.15

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "judge_type": self.judge_type,
            "num_runs": self.num_runs,
            "scores": [round(s, 4) for s in self.scores],
            "mean_score": round(self.mean_score, 4),
            "std_dev": round(self.std_dev, 4),
            "variance": round(self.variance, 4),
            "is_stable": self.is_stable,
        }


# ---------------------------------------------------------------------------
# JSON extraction and parsing
# ---------------------------------------------------------------------------


def _extract_json_from_response(text: str) -> str:
    """Extract JSON object from LLM response text.

    Handles markdown code blocks, preamble text, and bare JSON.
    """
    import re

    stripped = text.strip()

    # If it starts with {, find the matching closing brace
    if stripped.startswith("{"):
        last_brace = stripped.rfind("}")
        if last_brace > 0:
            return stripped[: last_brace + 1]
        return stripped

    # Extract from ```json ... ``` code blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Unclosed code block
    match = re.search(r"```(?:json)?\s*\n?(.*)", stripped, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # Find first { to last }
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1]

    return stripped


def parse_judge_response(
    raw_text: str,
    judge_type: str,
) -> tuple[list[DimensionScore], list[str], list[str], float, str]:
    """Parse a judge LLM response into structured scores.

    Returns:
        (dimensions, red_flags, critical_errors, overall_score, summary)
    """
    json_text = _extract_json_from_response(raw_text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.error("judge_response_parse_failed", raw_length=len(raw_text))
        return [], [], [], 0.0, "Failed to parse judge response"

    dimension_keys = JUDGE_DIMENSIONS.get(judge_type, [])
    dimensions: list[DimensionScore] = []
    for key in dimension_keys:
        dim_data = data.get(key, {})
        if isinstance(dim_data, dict):
            score_val = dim_data.get("score", 0)
            reasoning_val = dim_data.get("reasoning", "")
        else:
            score_val = 0
            reasoning_val = ""

        # Clamp score to 1-5
        if isinstance(score_val, (int, float)):
            score_val = max(1, min(5, int(round(score_val))))
        else:
            score_val = 1

        dimensions.append(
            DimensionScore(
                name=key,
                score=score_val,
                reasoning=str(reasoning_val),
            )
        )

    red_flags = data.get("red_flags", [])
    if not isinstance(red_flags, list):
        red_flags = [str(red_flags)] if red_flags else []
    red_flags = [str(f) for f in red_flags if f]

    critical_errors = data.get("critical_errors", [])
    if not isinstance(critical_errors, list):
        critical_errors = [str(critical_errors)] if critical_errors else []
    critical_errors = [str(e) for e in critical_errors if e]

    overall_score = data.get("overall_score", 0.0)
    if isinstance(overall_score, (int, float)):
        overall_score = max(0.0, min(1.0, float(overall_score)))
    else:
        overall_score = 0.0

    summary = str(data.get("summary", ""))

    return dimensions, red_flags, critical_errors, overall_score, summary


# ---------------------------------------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------------------------------------


def _format_claim_analysis(patent_analysis: dict) -> str:
    """Format a PatentAnalysis dict as readable text for the judge."""
    lines = []
    lines.append(f"Patent: {patent_analysis.get('patent_id', 'unknown')}")
    lines.append(f"Risk Level: {patent_analysis.get('risk_level', 'unknown')}")
    lines.append(f"Risk Summary: {patent_analysis.get('risk_summary', '')}")
    lines.append("")

    for claim in patent_analysis.get("claims_analyzed", []):
        lines.append(
            f"--- Claim {claim.get('claim_number', '?')} ({claim.get('claim_type', '')}) ---"
        )
        lines.append(f"Overall Status: {claim.get('overall_status', '?')}")
        lines.append(f"Overall Confidence: {claim.get('overall_confidence', 0.0)}")
        lines.append(f"Reasoning: {claim.get('reasoning', '')}")
        lines.append("")

        for elem in claim.get("elements", []):
            lines.append(
                f"  Element {elem.get('element_number', '?')}: "
                f"{elem.get('status', '?')} (confidence: {elem.get('confidence', 0.0)})"
            )
            lines.append(f"    Text: {elem.get('element_text', '')}")
            lines.append(f"    Reasoning: {elem.get('reasoning', '')}")
            lines.append(f"    Evidence: {elem.get('evidence', '')}")
        lines.append("")

    return "\n".join(lines)


def _format_invalidity_assessment(assessment: dict) -> str:
    """Format an InvalidityAssessment dict as readable text for the judge."""
    lines = []
    lines.append(f"Patent: {assessment.get('patent_id', 'unknown')}")
    lines.append(
        f"Overall Invalidity Strength: {assessment.get('overall_invalidity_strength', '?')}"
    )
    lines.append(f"Confidence: {assessment.get('confidence', 0.0)}")
    lines.append(f"Confidence Band: {assessment.get('confidence_band', '?')}")
    lines.append(f"Reasoning: {assessment.get('reasoning', '')}")
    lines.append("")

    # Prior art
    prior_art = assessment.get("prior_art", [])
    if prior_art:
        lines.append(f"Prior Art References ({len(prior_art)}):")
        for ref in prior_art:
            lines.append(f"  - {ref.get('reference_id', '?')}: {ref.get('title', '')}")
            lines.append(
                f"    Anticipation: {ref.get('anticipation_score', 0.0)}, "
                f"Obviousness: {ref.get('obviousness_score', 0.0)}"
            )
            lines.append(f"    Relevance: {ref.get('relevance', '')}")
        lines.append("")

    # Written description issues
    wd_issues = assessment.get("written_description_issues", [])
    if wd_issues:
        lines.append("Written Description Issues:")
        for issue in wd_issues:
            lines.append(f"  - {issue}")
        lines.append("")

    # PTAB
    ptab = assessment.get("ptab", {})
    if ptab.get("has_been_challenged"):
        lines.append("PTAB History:")
        for proc in ptab.get("proceedings", []):
            lines.append(f"  - {proc.get('proceeding_number', '?')}: {proc.get('status', '?')}")
            lines.append(f"    Claims cancelled: {proc.get('claims_cancelled', [])}")
        lines.append("")

    # Claim charts
    charts = assessment.get("claim_charts", [])
    if charts:
        lines.append(f"Claim Charts ({len(charts)}):")
        for chart in charts:
            lines.append(
                f"  Claim {chart.get('claim_number', '?')} vs {chart.get('prior_art_reference_id', '?')}:"
            )
            lines.append(
                f"    All elements disclosed: {chart.get('all_elements_disclosed', False)}"
            )
            for entry in chart.get("entries", []):
                lines.append(
                    f"      Element {entry.get('element_number', '?')}: "
                    f"disclosed={entry.get('disclosed', '?')}"
                )
        lines.append("")

    # Graham factors
    graham = assessment.get("graham_factors")
    if graham:
        lines.append("Graham Factors (Obviousness):")
        lines.append(f"  Scope & Content: {graham.get('scope_and_content', '')}")
        lines.append(f"  Differences: {graham.get('differences_from_prior_art', '')}")
        lines.append(f"  POSITA: {graham.get('level_of_ordinary_skill', '')}")
        lines.append(f"  Overall: {graham.get('overall_obviousness_assessment', '')}")
        lines.append("")

    return "\n".join(lines)


def _format_design_around(suggestions: list[dict]) -> str:
    """Format DesignAroundSuggestion list as readable text."""
    if not suggestions:
        return "(No design-around suggestions provided)"
    lines = []
    for i, sug in enumerate(suggestions, 1):
        lines.append(f"Suggestion {i}:")
        lines.append(f"  Element Avoided: {sug.get('element_avoided', '?')}")
        lines.append(f"  Suggestion: {sug.get('suggestion', '')}")
        lines.append(f"  Feasibility: {sug.get('feasibility', '')}")
        lines.append("")
    return "\n".join(lines)


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD for a judge call."""
    normalized_model = model.lower()
    if "haiku" in normalized_model:
        costs = (1.00, 5.00)
    elif "sonnet" in normalized_model:
        costs = (3.00, 15.00)
    elif "opus" in normalized_model:
        costs = (5.00, 25.00)
    else:
        costs = _MODEL_COSTS.get(model, (1.00, 5.00))
    return (input_tokens * costs[0] + output_tokens * costs[1]) / 1_000_000


# ---------------------------------------------------------------------------
# BenchmarkJudge — main class
# ---------------------------------------------------------------------------


class BenchmarkJudge:
    """LLM-as-Judge evaluator for benchmark pipeline outputs.

    Args:
        model: Claude model to use for judging. Defaults to Haiku.
        api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        temperature: Temperature for judge calls. Default 0.0 for determinism.
        max_tokens: Max output tokens for judge responses.
    """

    def __init__(
        self,
        model: str = DEFAULT_JUDGE_MODEL,
        api_key: str | None = None,
        temperature: float = JUDGE_TEMPERATURE,
        max_tokens: int = MAX_JUDGE_TOKENS,
    ) -> None:
        if _no_paid_api_enabled():
            raise RuntimeError(
                "NO_PAID_API=true blocks live Anthropic benchmark judge calls. "
                "Run offline fixture gates or explicitly disable no-credit mode for the paid lane."
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = (
            anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    # -- Core LLM call -------------------------------------------------------

    async def _call_judge(self, system: str, user: str) -> tuple[str, int, int, float]:
        """Make a single judge LLM call.

        Returns: (response_text, input_tokens, output_tokens, duration_seconds)
        """
        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        duration = time.monotonic() - t0

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break

        return text, response.usage.input_tokens, response.usage.output_tokens, duration

    # -- Claim Analysis Evaluation -------------------------------------------

    async def evaluate_claim_analysis(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
        patent_analysis: dict[str, Any] | None = None,
    ) -> list[JudgeScore]:
        """Evaluate claim analysis quality for all patents in a report.

        If patent_analysis is provided, evaluates just that one patent.
        Otherwise evaluates all patent_analyses in the report.
        """
        gt_benchmark = ground_truth.get("benchmark", {})
        gt_litigation = ground_truth.get("litigation", {})
        gt_compound = ground_truth.get("compound", {})
        gt_elements = gt_benchmark.get("key_claim_elements", {})

        analyses = [patent_analysis] if patent_analysis else report_data.get("patent_analyses", [])
        scores: list[JudgeScore] = []

        for analysis in analyses:
            prompt_text = JUDGE_PROMPTS["claim_analysis"].format(
                compound_name=gt_compound.get(
                    "generic_name", gt_compound.get("brand_name", "unknown")
                ),
                compound_smiles=gt_compound.get("smiles", ""),
                patent_id=analysis.get("patent_id", "unknown"),
                patent_title=analysis.get("title", ""),
                patent_assignee=analysis.get("assignee", ""),
                litigation_ruling=gt_litigation.get("ruling", "unknown"),
                claims_at_issue=str(
                    gt_litigation.get("claims_upheld", [])
                    + gt_litigation.get("claims_invalidated", [])
                ),
                gt_elements_met="\n".join(f"- {e}" for e in gt_elements.get("met", [])),
                gt_elements_not_met="\n".join(f"- {e}" for e in gt_elements.get("not_met", [])),
                pipeline_claim_analysis=_format_claim_analysis(analysis),
            )

            system = (
                "You are a patent law expert. Evaluate the AI pipeline output "
                "according to the rubric. Return ONLY a JSON object."
            )

            raw_text, in_tok, out_tok, dur = await self._call_judge(system, prompt_text)

            dimensions, red_flags, critical_errors, overall, summary = parse_judge_response(
                raw_text, "claim_analysis"
            )

            score = JudgeScore(
                judge_type="claim_analysis",
                case_id=ground_truth.get("id", ""),
                patent_id=analysis.get("patent_id", ""),
                dimensions=dimensions,
                red_flags=red_flags,
                critical_errors=critical_errors,
                overall_score=overall,
                summary=summary,
                raw_response=raw_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=_compute_cost(self.model, in_tok, out_tok),
                duration_seconds=dur,
            )
            scores.append(score)

            logger.info(
                "judge_claim_analysis",
                case_id=ground_truth.get("id"),
                patent_id=analysis.get("patent_id"),
                overall_score=round(overall, 3),
                red_flags_count=len(red_flags),
                cost_usd=round(score.cost_usd, 5),
            )

        return scores

    # -- Invalidity Evaluation -----------------------------------------------

    async def evaluate_invalidity(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
    ) -> list[JudgeScore]:
        """Evaluate invalidity assessment quality for all assessments in a report."""
        gt_litigation = ground_truth.get("litigation", {})
        assessments = report_data.get("invalidity_assessments", [])
        scores: list[JudgeScore] = []

        for assessment in assessments:
            # Find matching GT patent info
            patent_id = assessment.get("patent_id", "")
            gt_patent = _find_gt_patent(ground_truth, patent_id)

            prompt_text = JUDGE_PROMPTS["invalidity"].format(
                patent_id=patent_id,
                patent_title=gt_patent.get("title", ""),
                litigation_ruling=gt_litigation.get("ruling", "unknown"),
                invalidity_basis=gt_litigation.get("invalidity_basis", "Not specified"),
                claims_challenged=str(assessment.get("claim_numbers", [])),
                claims_invalidated=str(gt_litigation.get("claims_invalidated", [])),
                claims_upheld=str(gt_litigation.get("claims_upheld", [])),
                pipeline_invalidity_output=_format_invalidity_assessment(assessment),
            )

            system = (
                "You are a patent law expert. Evaluate the AI pipeline's invalidity "
                "assessment according to the rubric. Return ONLY a JSON object."
            )

            raw_text, in_tok, out_tok, dur = await self._call_judge(system, prompt_text)

            dimensions, red_flags, critical_errors, overall, summary = parse_judge_response(
                raw_text, "invalidity"
            )

            score = JudgeScore(
                judge_type="invalidity",
                case_id=ground_truth.get("id", ""),
                patent_id=patent_id,
                dimensions=dimensions,
                red_flags=red_flags,
                critical_errors=critical_errors,
                overall_score=overall,
                summary=summary,
                raw_response=raw_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=_compute_cost(self.model, in_tok, out_tok),
                duration_seconds=dur,
            )
            scores.append(score)

            logger.info(
                "judge_invalidity",
                case_id=ground_truth.get("id"),
                patent_id=patent_id,
                overall_score=round(overall, 3),
                red_flags_count=len(red_flags),
            )

        return scores

    # -- Design-Around Evaluation --------------------------------------------

    async def evaluate_design_around(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
    ) -> list[JudgeScore]:
        """Evaluate design-around suggestion quality for all patents."""
        gt_compound = ground_truth.get("compound", {})
        analyses = report_data.get("patent_analyses", [])
        scores: list[JudgeScore] = []

        for analysis in analyses:
            suggestions = analysis.get("design_around_suggestions", [])
            if not suggestions:
                continue

            # Build claim limitations from claim elements
            claim_limitations = []
            for claim in analysis.get("claims_analyzed", []):
                for elem in claim.get("elements", []):
                    if elem.get("status") == "met":
                        claim_limitations.append(
                            f"Claim {claim.get('claim_number', '?')}, "
                            f"Element {elem.get('element_number', '?')}: "
                            f"{elem.get('element_text', '')}"
                        )

            prompt_text = JUDGE_PROMPTS["design_around"].format(
                compound_name=gt_compound.get(
                    "generic_name", gt_compound.get("brand_name", "unknown")
                ),
                compound_smiles=gt_compound.get("smiles", ""),
                therapeutic_area=gt_compound.get("therapeutic_area", "unknown"),
                drug_class=gt_compound.get("drug_class", "unknown"),
                patent_id=analysis.get("patent_id", "unknown"),
                claim_limitations="\n".join(f"- {lim}" for lim in claim_limitations)
                or "(none identified)",
                pipeline_design_around=_format_design_around(suggestions),
            )

            system = (
                "You are a medicinal chemistry and patent law expert. Evaluate "
                "the design-around suggestions according to the rubric. Return ONLY a JSON object."
            )

            raw_text, in_tok, out_tok, dur = await self._call_judge(system, prompt_text)

            dimensions, red_flags, critical_errors, overall, summary = parse_judge_response(
                raw_text, "design_around"
            )

            score = JudgeScore(
                judge_type="design_around",
                case_id=ground_truth.get("id", ""),
                patent_id=analysis.get("patent_id", ""),
                dimensions=dimensions,
                red_flags=red_flags,
                critical_errors=critical_errors,
                overall_score=overall,
                summary=summary,
                raw_response=raw_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=_compute_cost(self.model, in_tok, out_tok),
                duration_seconds=dur,
            )
            scores.append(score)

            logger.info(
                "judge_design_around",
                case_id=ground_truth.get("id"),
                patent_id=analysis.get("patent_id"),
                overall_score=round(overall, 3),
            )

        return scores

    # -- Legal Soundness Evaluation ------------------------------------------

    async def evaluate_legal_soundness(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
    ) -> JudgeScore:
        """Evaluate overall legal soundness of the report."""
        gt_compound = ground_truth.get("compound", {})
        gt_litigation = ground_truth.get("litigation", {})
        gt_benchmark = ground_truth.get("benchmark", {})
        risk_summary = report_data.get("risk_summary", {})

        # Extract blocking patents from pipeline
        blocking = [
            a.get("patent_id", "")
            for a in report_data.get("patent_analyses", [])
            if a.get("risk_level") in ("high", "medium")
        ]

        prompt_text = JUDGE_PROMPTS["legal_soundness"].format(
            compound_name=gt_compound.get("generic_name", gt_compound.get("brand_name", "unknown")),
            compound_smiles=gt_compound.get("smiles", ""),
            therapeutic_area=gt_compound.get("therapeutic_area", "unknown"),
            litigation_ruling=gt_litigation.get("ruling", "unknown"),
            invalidity_basis=gt_litigation.get("invalidity_basis", "Not specified"),
            expected_risk_today=gt_benchmark.get("expected_risk_today", "unknown"),
            pipeline_risk_level=risk_summary.get("overall_risk", "unknown"),
            patents_analyzed_count=risk_summary.get("total_patents_analyzed", 0),
            blocking_patents_count=risk_summary.get("blocking_patents_count", 0),
            pipeline_report_summary=risk_summary.get("executive_summary", "(No summary available)"),
            pipeline_risk_summary=risk_summary.get("executive_summary", "")[:500],
            pipeline_blocking_patents=", ".join(blocking) or "(none identified)",
            pipeline_key_risks="\n".join(f"- {r}" for r in risk_summary.get("key_risks", []))
            or "(none)",
        )

        system = (
            "You are a senior patent attorney. Evaluate the overall legal soundness "
            "of this FTO report according to the rubric. Return ONLY a JSON object."
        )

        raw_text, in_tok, out_tok, dur = await self._call_judge(system, prompt_text)

        dimensions, red_flags, critical_errors, overall, summary = parse_judge_response(
            raw_text, "legal_soundness"
        )

        score = JudgeScore(
            judge_type="legal_soundness",
            case_id=ground_truth.get("id", ""),
            dimensions=dimensions,
            red_flags=red_flags,
            critical_errors=critical_errors,
            overall_score=overall,
            summary=summary,
            raw_response=raw_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=_compute_cost(self.model, in_tok, out_tok),
            duration_seconds=dur,
        )

        logger.info(
            "judge_legal_soundness",
            case_id=ground_truth.get("id"),
            overall_score=round(overall, 3),
            critical_errors_count=len(critical_errors),
        )

        return score

    # -- Full Case Evaluation ------------------------------------------------

    async def evaluate_case(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
    ) -> CaseJudgeResult:
        """Run all judge evaluations for a single benchmark case."""
        case_id = ground_truth.get("id", "")
        compound_name = ground_truth.get("compound", {}).get(
            "generic_name",
            ground_truth.get("compound", {}).get("brand_name", ""),
        )

        logger.info("judge_case_start", case_id=case_id, compound=compound_name)
        t0 = time.monotonic()

        result = CaseJudgeResult(case_id=case_id, compound_name=compound_name)

        # Run all four evaluation types
        result.claim_scores = await self.evaluate_claim_analysis(report_data, ground_truth)
        result.invalidity_scores = await self.evaluate_invalidity(report_data, ground_truth)
        result.design_around_scores = await self.evaluate_design_around(report_data, ground_truth)
        result.legal_soundness = await self.evaluate_legal_soundness(report_data, ground_truth)

        duration = time.monotonic() - t0
        logger.info(
            "judge_case_complete",
            case_id=case_id,
            overall_quality=round(result.overall_quality_score, 3),
            total_cost=round(result.total_cost_usd, 4),
            duration_s=round(duration, 1),
            claim_evals=len(result.claim_scores),
            invalidity_evals=len(result.invalidity_scores),
            design_around_evals=len(result.design_around_scores),
        )

        return result

    # -- Batch Evaluation ----------------------------------------------------

    async def evaluate_batch(
        self,
        cases: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> list[CaseJudgeResult]:
        """Evaluate multiple (report, ground_truth) pairs sequentially.

        Sequential to respect API rate limits and keep costs predictable.
        """
        results: list[CaseJudgeResult] = []
        total_cost = 0.0

        for i, (report, gt) in enumerate(cases, 1):
            logger.info("judge_batch_progress", case=i, total=len(cases))
            result = await self.evaluate_case(report, gt)
            results.append(result)
            total_cost += result.total_cost_usd

        logger.info(
            "judge_batch_complete",
            cases=len(results),
            total_cost_usd=round(total_cost, 4),
        )
        return results

    # -- Calibration ---------------------------------------------------------

    async def calibrate(
        self,
        report_data: dict[str, Any],
        ground_truth: dict[str, Any],
        judge_type: str = "legal_soundness",
        num_runs: int = CALIBRATION_RUNS,
    ) -> CalibrationResult:
        """Run the same evaluation multiple times to measure variance.

        A variance < 0.15 across runs indicates acceptable stability.
        """
        scores: list[float] = []

        for run in range(num_runs):
            logger.info("calibration_run", run=run + 1, total=num_runs, judge_type=judge_type)

            if judge_type == "claim_analysis":
                judge_scores = await self.evaluate_claim_analysis(report_data, ground_truth)
                if judge_scores:
                    scores.append(statistics.mean(s.overall_score for s in judge_scores))
            elif judge_type == "invalidity":
                judge_scores = await self.evaluate_invalidity(report_data, ground_truth)
                if judge_scores:
                    scores.append(statistics.mean(s.overall_score for s in judge_scores))
            elif judge_type == "design_around":
                judge_scores = await self.evaluate_design_around(report_data, ground_truth)
                if judge_scores:
                    scores.append(statistics.mean(s.overall_score for s in judge_scores))
            elif judge_type == "legal_soundness":
                score = await self.evaluate_legal_soundness(report_data, ground_truth)
                scores.append(score.overall_score)
            else:
                raise ValueError(f"Unknown judge_type: {judge_type}")

        if len(scores) < 2:
            std_dev = 0.0
            variance = 0.0
        else:
            std_dev = statistics.stdev(scores)
            variance = statistics.variance(scores)

        mean_score = statistics.mean(scores) if scores else 0.0

        result = CalibrationResult(
            case_id=ground_truth.get("id", ""),
            judge_type=judge_type,
            num_runs=num_runs,
            scores=scores,
            mean_score=mean_score,
            std_dev=std_dev,
            variance=variance,
            is_stable=variance < 0.15,
        )

        logger.info(
            "calibration_complete",
            judge_type=judge_type,
            mean=round(mean_score, 3),
            std_dev=round(std_dev, 3),
            variance=round(variance, 4),
            is_stable=result.is_stable,
        )

        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_gt_patent(ground_truth: dict, patent_id: str) -> dict:
    """Find a patent in the ground truth by normalized ID."""
    import re

    _kind = re.compile(r"(?<=\d)[A-Z]\d*$")

    def _norm(pid: str) -> str:
        pid = pid.strip().upper().replace(" ", "").replace("-", "")
        return _kind.sub("", pid)

    target = _norm(patent_id)
    for pat in ground_truth.get("patents", []):
        if _norm(pat.get("patent_number", pat.get("number", ""))) == target:
            return pat
    return {}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _run_cli(args: argparse.Namespace) -> None:
    """CLI execution logic."""
    benchmarks_path = Path(args.benchmarks)
    reports_dir = Path(args.reports)

    if not benchmarks_path.exists():
        print(f"Benchmarks file not found: {benchmarks_path}")
        return

    with open(benchmarks_path) as f:
        benchmarks = json.load(f)

    judge = BenchmarkJudge(
        model=args.model,
        temperature=0.0,
    )

    results: list[dict] = []

    try:
        for gt in benchmarks:
            case_id = gt.get("id", "")
            report_path = reports_dir / f"{case_id}_report.json"

            if not report_path.exists():
                logger.warning("report_not_found", case_id=case_id, path=str(report_path))
                continue

            with open(report_path) as f:
                report_data = json.load(f)

            if args.calibrate:
                cal = await judge.calibrate(report_data, gt, judge_type=args.judge_type)
                results.append(cal.to_dict())
            else:
                case_result = await judge.evaluate_case(report_data, gt)
                results.append(case_result.to_dict())

        # Write output
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        total_cost = sum(r.get("total_cost_usd", 0.0) for r in results)
        print("\nJudge evaluation complete:")
        print(f"  Cases evaluated: {len(results)}")
        print(f"  Total cost: ${total_cost:.4f}")
        print(f"  Results saved to: {output_path}")

    finally:
        await judge.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-as-Judge evaluation for Praviar Pipeline benchmarks",
    )
    parser.add_argument(
        "--benchmarks",
        type=str,
        default="research/benchmarks/paragraph_iv_benchmarks.json",
        help="Path to benchmark JSON file",
    )
    parser.add_argument(
        "--reports",
        type=str,
        default="output/",
        help="Directory containing pipeline report JSON files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/judge_results.json",
        help="Output path for judge results",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_JUDGE_MODEL,
        help=f"Claude model for judging (default: {DEFAULT_JUDGE_MODEL})",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Run calibration mode (3 runs per case, measure variance)",
    )
    parser.add_argument(
        "--judge-type",
        type=str,
        default="legal_soundness",
        choices=["claim_analysis", "invalidity", "design_around", "legal_soundness"],
        help="Judge type for calibration mode",
    )

    args = parser.parse_args()
    asyncio.run(_run_cli(args))


if __name__ == "__main__":
    main()
