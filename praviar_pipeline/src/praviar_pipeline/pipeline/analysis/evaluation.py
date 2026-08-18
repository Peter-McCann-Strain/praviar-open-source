"""Evaluation helpers for Step 4 adaptive claim analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.analysis import AnalysisEvaluation, PatentAnalysis, RiskLevel
from praviar_pipeline.pipeline.analysis.risk import compute_risk_from_elements
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient

logger = structlog.get_logger()
RISK_CONSERVATISM = {
    RiskLevel.CLEAR: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}


async def evaluate_analysis(
    claude: ClaudeClient,
    analysis: PatentAnalysis,
    evaluator_prompt: str,
) -> AnalysisEvaluation:
    """Evaluate a patent analysis for consistency."""
    evidence = (
        f"Patent: {sanitize_prompt_value(analysis.patent_id)}\n"
        f"Title: {analysis.title}\n"
        f"Risk Level: {analysis.risk_level.value}\n"
        f"Risk Summary: {analysis.risk_summary}\n\n"
        "Claims Analyzed:\n"
    )
    settings = get_settings()
    for claim in analysis.claims_analyzed:
        evidence += (
            f"\n  Claim {claim.claim_number} ({claim.claim_type}): "
            f"overall_status={claim.overall_status.value}"
        )
        for element in claim.elements:
            reason = element.reasoning[: settings.analysis_element_reasoning_max_chars]
            evidence += f"\n    Element {element.element_number}: {element.status.value} — {reason}"
    user_prompt = (
        "Review the following untrusted FTO analysis evidence for quality and consistency.\n\n"
        + sanitize_untrusted_text(evidence, data_type="model_analysis")
    )

    evaluation, _usage = await claude.complete(
        system=evaluator_prompt,
        user=user_prompt,
        response_model=AnalysisEvaluation,
        model=claude._models.triage,
        max_tokens=settings.evaluator_max_tokens,
        effort=settings.thinking_effort_analysis,
        cache_system=True,
    )
    return evaluation


def apply_evaluation_fixes(
    analysis: PatentAnalysis,
    evaluation: AnalysisEvaluation,
) -> PatentAnalysis:
    """Apply evaluator-provided fixes to an analysis."""
    if evaluation.revised_risk_level is not None:
        deterministic_risk = compute_risk_from_elements(analysis)
        revised_risk = max(
            evaluation.revised_risk_level,
            deterministic_risk,
            key=lambda risk: RISK_CONSERVATISM[risk],
        )
        logger.info(
            "evaluator_risk_correction",
            evaluator_revised=evaluation.revised_risk_level.value,
            deterministic_floor=deterministic_risk.value,
            revised=revised_risk.value,
        )
        analysis.risk_level = revised_risk
    return analysis
