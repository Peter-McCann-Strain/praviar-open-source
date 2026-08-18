"""Batch orchestration helpers for Step 4 adaptive claim analysis."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from praviar_pipeline.logging_config import ProgressTracker
from praviar_pipeline.pipeline.analysis.orchestration_helpers import (
    AnalysisBatchContext,
    build_analysis_timeout,
    collect_batch_results,
    run_patent_analysis_task,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.analysis import AnalysisEvaluation, PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.reasoning import ReasoningTrace
    from praviar_pipeline.models.report import AnalysisFailure
    from praviar_pipeline.models.triage import TriageResult
    from praviar_pipeline.tools import FTOToolkit


async def run_analysis_batch(
    *,
    claude: ClaudeClient,
    patents_to_analyze: list[PatentHit],
    compound: ResolvedCompound,
    settings: Settings,
    system_prompt: str,
    evaluator_prompt: str,
    global_escalation_reasons: list[str] | None,
    triage_map: dict[str, TriageResult],
    spec_text_cache: dict[str, str],
    prosecution_cache: dict[str, dict[str, object]],
    toolkit: FTOToolkit | None,
    drawing_evidence: DrawingEvidenceStore | None,
    analyze_single_pass: Callable[..., Awaitable[PatentAnalysis]],
    analyze_agentic: Callable[..., Awaitable[tuple[PatentAnalysis, ReasoningTrace]]],
    evaluate_analysis: Callable[[ClaudeClient, PatentAnalysis, str], Awaitable[AnalysisEvaluation]],
    apply_evaluation_fixes: Callable[[PatentAnalysis, AnalysisEvaluation], PatentAnalysis],
    run_perspectives: Callable[..., Awaitable[list]],
    synthesize_perspectives: Callable[..., Awaitable[object]],
    format_compound_for_analysis: Callable[[ResolvedCompound], str],
    format_patent_for_analysis: Callable[[PatentHit, TriageResult | None], str],
) -> tuple[list[PatentAnalysis], list[AnalysisFailure], list[ReasoningTrace]]:
    semaphore = asyncio.Semaphore(settings.analysis_concurrency)
    context = AnalysisBatchContext(
        claude=claude,
        compound=compound,
        settings=settings,
        system_prompt=system_prompt,
        evaluator_prompt=evaluator_prompt,
        global_escalation_reasons=list(global_escalation_reasons or []),
        triage_map=triage_map,
        spec_text_cache=spec_text_cache,
        prosecution_cache=prosecution_cache,
        toolkit=toolkit,
        drawing_evidence=drawing_evidence,
        analyze_single_pass=analyze_single_pass,
        analyze_agentic=analyze_agentic,
        evaluate_analysis=evaluate_analysis,
        apply_evaluation_fixes=apply_evaluation_fixes,
        run_perspectives=run_perspectives,
        synthesize_perspectives=synthesize_perspectives,
        format_compound_for_analysis=format_compound_for_analysis,
        format_patent_for_analysis=format_patent_for_analysis,
        tracker=ProgressTracker(total=len(patents_to_analyze), operation="patent_analysis"),
    )
    analysis_timeout = build_analysis_timeout(settings)

    results = await asyncio.gather(
        *[
            asyncio.wait_for(
                run_patent_analysis_task(
                    patent=patent,
                    context=context,
                    semaphore=semaphore,
                ),
                timeout=analysis_timeout,
            )
            for patent in patents_to_analyze
        ],
        return_exceptions=True,
    )

    return collect_batch_results(
        results=results,
        patents_to_analyze=patents_to_analyze,
        tracker=context.tracker,
        settings=settings,
        compound_name=compound.name,
    )
