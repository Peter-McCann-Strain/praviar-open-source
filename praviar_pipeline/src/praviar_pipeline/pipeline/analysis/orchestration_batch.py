"""Batch-analysis implementation for Step 4 agentic claim escalation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import structlog

from praviar_pipeline.pipeline.analysis.adaptive_decision import (
    AGENTIC_ESCALATION_STAGE,
    SINGLE_PASS_STAGE,
    build_adaptive_execution_plan,
    stamp_analysis_execution,
)
from praviar_pipeline.pipeline.analysis.orchestration_evaluation import (
    evaluate_patent_analysis,
    maybe_run_perspectives,
)
from praviar_pipeline.pipeline.analysis.orchestration_results import (
    build_analysis_failure,
    log_analysis_failure,
    log_batch_summary,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable, Sequence

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.logging_config import ProgressTracker
    from praviar_pipeline.models.analysis import AnalysisEvaluation, PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.reasoning import ReasoningTrace
    from praviar_pipeline.models.report import AnalysisFailure
    from praviar_pipeline.models.triage import TriageResult
    from praviar_pipeline.tools import FTOToolkit

logger = structlog.get_logger()


@dataclass(slots=True)
class AnalysisBatchContext:
    """Immutable batch dependencies shared across patent tasks."""

    claude: ClaudeClient
    compound: ResolvedCompound
    settings: Settings
    system_prompt: str
    evaluator_prompt: str
    global_escalation_reasons: list[str]
    triage_map: dict[str, TriageResult]
    spec_text_cache: dict[str, str]
    prosecution_cache: dict[str, dict[str, object]]
    toolkit: FTOToolkit | None
    drawing_evidence: DrawingEvidenceStore | None
    analyze_single_pass: Callable[..., Awaitable[PatentAnalysis]]
    analyze_agentic: Callable[..., Awaitable[tuple[PatentAnalysis, ReasoningTrace]]]
    evaluate_analysis: Callable[[ClaudeClient, PatentAnalysis, str], Awaitable[AnalysisEvaluation]]
    apply_evaluation_fixes: Callable[[PatentAnalysis, AnalysisEvaluation], PatentAnalysis]
    run_perspectives: Callable[..., Awaitable[list]]
    synthesize_perspectives: Callable[..., Awaitable[object]]
    format_compound_for_analysis: Callable[[ResolvedCompound], str]
    format_patent_for_analysis: Callable[[PatentHit, TriageResult | None], str]
    tracker: ProgressTracker


def build_analysis_timeout(settings: Settings) -> float:
    """Return the per-patent timeout used for batch analysis."""
    return settings.http_timeout_long * 5


async def run_patent_analysis_task(
    *,
    patent: PatentHit,
    context: AnalysisBatchContext,
    semaphore: asyncio.Semaphore,
) -> tuple[PatentAnalysis, ReasoningTrace | None]:
    """Run one patent through analysis, evaluation, and optional perspectives."""
    async with semaphore:
        patent_started_at = time.monotonic()
        triage = context.triage_map.get(patent.patent_id)

        logger.info(
            "patent_analysis_begin",
            execution_profile="world_class_adaptive",
            has_claims=bool(patent.claims_text),
            has_abstract=bool(patent.abstract),
            triage_relevance=triage.relevance.value if triage else "unknown",
        )

        analysis, trace = await _analyze_patent(
            patent=patent,
            triage=triage,
            context=context,
        )

        analysis_duration = time.monotonic() - patent_started_at
        logger.info(
            "patent_analysis_done",
            claims_analyzed=len(analysis.claims_analyzed),
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            duration_s=round(analysis_duration, 2),
        )

        analysis = await _evaluate_patent(
            patent=patent,
            analysis=analysis,
            triage=triage,
            context=context,
        )
        analysis = await _maybe_run_perspectives(
            patent=patent,
            analysis=analysis,
            triage=triage,
            context=context,
        )

        total_duration = time.monotonic() - patent_started_at
        context.tracker.mark_complete(
            success=True,
            patent_id=patent.patent_id,
            risk_level=analysis.risk_level.value,
            total_duration_s=round(total_duration, 2),
        )
        return analysis, trace


async def _analyze_patent(
    *,
    patent: PatentHit,
    triage: TriageResult | None,
    context: AnalysisBatchContext,
) -> tuple[PatentAnalysis, ReasoningTrace | None]:
    execution_plan = build_adaptive_execution_plan(
        patent=patent,
        triage=triage,
        drawing_evidence=context.drawing_evidence,
        global_reasons=context.global_escalation_reasons,
    )
    logger.info(
        "adaptive_execution_plan",
        execution_profile=execution_plan.execution_profile,
        stages=list(execution_plan.stages),
        escalation_required=execution_plan.escalation_required,
    )
    if execution_plan.escalation_required:
        analysis, trace = await context.analyze_agentic(
            context.claude,
            patent,
            context.compound,
            triage,
            product_context=context.settings.product_context,
            intended_actions=context.settings.intended_actions,
            target_jurisdictions=context.settings.target_jurisdictions,
            development_stage=getattr(context.settings, "development_stage", ""),
        )
        return (
            stamp_analysis_execution(
                analysis,
                stage=AGENTIC_ESCALATION_STAGE,
                escalation_reasons=list(execution_plan.escalation_reasons),
                execution_plan=execution_plan,
            ),
            trace,
        )

    analysis = await context.analyze_single_pass(
        context.claude,
        patent,
        context.compound,
        triage,
        context.system_prompt,
        toolkit=context.toolkit,
        drawing_evidence=context.drawing_evidence,
        spec_text=context.spec_text_cache.get(patent.patent_id, ""),
        prosecution_context=context.prosecution_cache.get(patent.patent_id),
        product_context=context.settings.product_context,
        intended_actions=context.settings.intended_actions,
        target_jurisdictions=context.settings.target_jurisdictions,
        development_stage=getattr(context.settings, "development_stage", ""),
    )
    return (
        stamp_analysis_execution(
            analysis,
            stage=SINGLE_PASS_STAGE,
            execution_plan=execution_plan,
        ),
        None,
    )


async def _evaluate_patent(
    *,
    patent: PatentHit,
    analysis: PatentAnalysis,
    triage: TriageResult | None,
    context: AnalysisBatchContext,
) -> PatentAnalysis:
    return cast(
        "PatentAnalysis",
        await evaluate_patent_analysis(
            patent=patent,
            analysis=analysis,
            triage=triage,
            context=context,
            logger=logger,
        ),
    )


async def _maybe_run_perspectives(
    *,
    patent: PatentHit,
    analysis: PatentAnalysis,
    triage: TriageResult | None,
    context: AnalysisBatchContext,
) -> PatentAnalysis:
    return cast(
        "PatentAnalysis",
        await maybe_run_perspectives(
            patent=patent,
            analysis=analysis,
            triage=triage,
            context=context,
            logger=logger,
        ),
    )


def collect_batch_results(
    *,
    results: Sequence[tuple[PatentAnalysis, ReasoningTrace | None] | BaseException],
    patents_to_analyze: list[PatentHit],
    tracker: ProgressTracker,
    settings: Settings,
    compound_name: str,
) -> tuple[list[PatentAnalysis], list[AnalysisFailure], list[ReasoningTrace]]:
    """Split batch results into analyses, failures, and traces."""
    analyses: list[PatentAnalysis] = []
    failures: list[AnalysisFailure] = []
    traces: list[ReasoningTrace] = []

    for index, result in enumerate(results):
        if isinstance(result, BaseException):
            patent = patents_to_analyze[index]
            log_analysis_failure(patent=patent, error=result, logger=logger)
            failures.append(
                build_analysis_failure(
                    patent_id=patent.patent_id,
                    error=result,
                    settings=settings,
                )
            )
            tracker.mark_complete(
                success=False,
                patent_id=patent.patent_id,
                error_type=safe_exception_type(result),
            )
            continue

        analysis, trace = result
        analyses.append(analysis)
        if trace is not None:
            traces.append(trace)
        logger.debug(
            "analysis_result_collected",
            claims_count=len(analysis.claims_analyzed),
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
        )

    log_batch_summary(
        analyses=analyses,
        failures=failures,
        compound_name=compound_name,
        logger=logger,
    )

    return analyses, failures, traces
