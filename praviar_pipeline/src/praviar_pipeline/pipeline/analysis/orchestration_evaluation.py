"""Evaluation and multi-perspective helpers for batch patent analysis."""

from __future__ import annotations

import time

from praviar_pipeline.pipeline.analysis.adaptive_decision import (
    AGENTIC_ESCALATION_STAGE,
    analysis_needs_perspective_review,
    mark_analysis_quality_gate_failure,
    stamp_analysis_execution,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type


def _count_critical_issues(evaluation) -> int:
    return sum(1 for issue in evaluation.issues if issue.severity == "critical")


async def evaluate_patent_analysis(
    *,
    patent,
    analysis,
    triage,
    context,
    logger,
):
    eval_started_at = time.monotonic()
    try:
        evaluation = await context.evaluate_analysis(
            context.claude,
            analysis,
            context.evaluator_prompt,
        )
        eval_duration = time.monotonic() - eval_started_at
        logger.info(
            "evaluator_result",
            quality=evaluation.overall_quality,
            critical=_count_critical_issues(evaluation),
            duration_s=round(eval_duration, 2),
        )

        has_critical = _count_critical_issues(evaluation) > 0
        if has_critical and evaluation.overall_quality == "needs_revision":
            analysis = context.apply_evaluation_fixes(analysis, evaluation)

        if evaluation.overall_quality == "poor" and not getattr(
            analysis, "analysis_escalated", False
        ):
            analysis = await reanalyze_after_poor_evaluation(
                patent=patent,
                analysis=analysis,
                triage=triage,
                context=context,
                logger=logger,
            )
    except Exception as exc:
        analysis = mark_analysis_quality_gate_failure(
            analysis,
            "evaluator_initial_evaluation_failed",
        )
        logger.warning(
            "evaluator_quality_gate_failed",
            phase="initial_evaluation",
            error_type=safe_exception_type(exc),
        )

    return analysis


async def reanalyze_after_poor_evaluation(
    *,
    patent,
    analysis,
    triage,
    context,
    logger,
):
    reasons = list(getattr(analysis, "analysis_escalation_reasons", []) or [])
    reasons.append("poor_evaluator_quality")
    logger.warning(
        "evaluator_triggered_agentic_escalation",
    )
    analysis, _ = await context.analyze_agentic(
        context.claude,
        patent,
        context.compound,
        triage,
    )
    analysis = stamp_analysis_execution(
        analysis,
        stage=AGENTIC_ESCALATION_STAGE,
        escalation_reasons=reasons,
    )
    try:
        reevaluation = await context.evaluate_analysis(
            context.claude,
            analysis,
            context.evaluator_prompt,
        )
        if reevaluation.revised_risk_level is not None:
            analysis = context.apply_evaluation_fixes(analysis, reevaluation)
    except Exception as exc:
        analysis = mark_analysis_quality_gate_failure(
            analysis,
            "evaluator_reanalysis_failed",
        )
        logger.warning(
            "evaluator_quality_gate_failed",
            phase="re_evaluation",
            error_type=safe_exception_type(exc),
        )
    return analysis


async def maybe_run_perspectives(
    *,
    patent,
    analysis,
    triage,
    context,
    logger,
):
    if not context.settings.multi_perspective_enabled:
        return analysis
    if not analysis_needs_perspective_review(analysis):
        return analysis

    try:
        compound_context = context.format_compound_for_analysis(context.compound)
        patent_context = context.format_patent_for_analysis(patent, triage)
        perspective_results = await context.run_perspectives(
            context.claude,
            patent,
            context.compound,
            analysis,
            compound_context,
            patent_context,
        )
        synthesis = await context.synthesize_perspectives(
            context.claude,
            perspective_results,
            analysis,
        )
        analysis.perspective_analyses = perspective_results
        analysis.multi_perspective_synthesis = synthesis
        logger.info(
            "multi_perspective_complete",
            perspectives=len(perspective_results),
            disagreements=len(getattr(synthesis, "disagreements", [])),
        )
    except Exception as exc:
        analysis = mark_analysis_quality_gate_failure(
            analysis,
            "perspective_review_failed",
        )
        logger.warning(
            "multi_perspective_quality_gate_failed",
            error_type=safe_exception_type(exc),
        )

    return analysis
