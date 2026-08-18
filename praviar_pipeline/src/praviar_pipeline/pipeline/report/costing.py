"""Costing helpers for report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.audit import StepTokenUsage

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis

# Model role -> Settings field name prefix mapping
_ROLE_TO_PRICING_KEY = {
    "triage": "haiku",
    "analysis": "sonnet",
    "deep": "sonnet",
}


def _model_name_to_pricing_key(model_name: str) -> str:
    """Derive pricing tier from actual model name."""
    lower = model_name.lower()
    if "haiku" in lower:
        return "haiku"
    if "sonnet" in lower:
        return "sonnet"
    if "opus" in lower:
        return "opus"
    return ""


def _compute_cost(step_token_usage: list[StepTokenUsage]) -> float:
    """Compute estimated USD cost from per-step token usage and model pricing."""
    settings = get_settings()
    total_cost = 0.0

    for step in step_token_usage:
        pricing_key = ""
        if step.model_name:
            pricing_key = _model_name_to_pricing_key(step.model_name)
        if not pricing_key:
            pricing_key = _ROLE_TO_PRICING_KEY.get(step.model_role, "sonnet")

        input_rate = getattr(settings, f"cost_per_million_input_{pricing_key}")
        output_rate = getattr(settings, f"cost_per_million_output_{pricing_key}")
        total_cost += (step.input_tokens / 1_000_000) * input_rate
        total_cost += (step.output_tokens / 1_000_000) * output_rate

    return round(total_cost, 4)


def _aggregate_step_tokens(
    prior_step_tokens: list[StepTokenUsage],
    analyses: list[PatentAnalysis],
    summary_in: int,
    summary_out: int,
    narr_in: int,
    narr_out: int,
) -> list[StepTokenUsage]:
    """Build per-step token usage list for cost computation."""
    usage: list[StepTokenUsage] = list(prior_step_tokens)

    analysis_in = sum(a.input_tokens for a in analyses)
    analysis_out = sum(a.output_tokens for a in analyses)
    if analysis_in or analysis_out:
        usage.append(
            StepTokenUsage(
                step_name="step4_analyze",
                model_role="deep",
                input_tokens=analysis_in,
                output_tokens=analysis_out,
            )
        )

    report_in = summary_in + narr_in
    report_out = summary_out + narr_out
    if report_in or report_out:
        usage.append(
            StepTokenUsage(
                step_name="step8_report",
                model_role="analysis",
                input_tokens=report_in,
                output_tokens=report_out,
            )
        )

    return usage
