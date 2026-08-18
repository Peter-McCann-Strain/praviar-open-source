"""Step 4: Deep Claim Analysis — element-by-element FTO analysis via Claude Opus."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.models.reasoning import ReasoningTrace  # noqa: TC001 — used at runtime
from praviar_pipeline.pipeline.analysis import (
    analyze_single_patent_agentic as _analyze_single_patent_agentic_impl,
)
from praviar_pipeline.pipeline.analysis import (
    analyze_single_patent_single_pass as _analyze_single_patent_single_pass_impl,
)
from praviar_pipeline.pipeline.analysis import (
    apply_evaluation_fixes as _apply_evaluation_fixes,
)
from praviar_pipeline.pipeline.analysis import (
    build_analysis_toolkit,
    build_triage_map,
    enrich_patents_for_analysis,
    run_analysis_batch,
)
from praviar_pipeline.pipeline.analysis import (
    evaluate_analysis as _evaluate_analysis,
)
from praviar_pipeline.pipeline.analysis import (
    fetch_prosecution_context as _fetch_prosecution_context,
)
from praviar_pipeline.pipeline.analysis import (
    run_perspectives as _run_perspectives,
)
from praviar_pipeline.pipeline.analysis import (
    synthesize_perspectives as _synthesize_perspectives,
)
from praviar_pipeline.pipeline.analysis.context_formatting import (
    format_compound_for_analysis as _format_compound_for_analysis_impl,
)
from praviar_pipeline.pipeline.analysis.context_formatting import (
    format_patent_for_analysis as _format_patent_for_analysis_impl,
)
from praviar_pipeline.pipeline.analysis.risk import (
    compute_risk_from_elements as _compute_risk_from_elements,
)
from praviar_pipeline.sanitize import sanitize_patent_text

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import AnalysisFailure
    from praviar_pipeline.models.triage import TriageResult
    from praviar_pipeline.tools import FTOToolkit

# Re-exported for downstream tests / modules that import the underscore-prefixed
# names directly from this step module.
__all__ = [
    "_analyze_single_patent_agentic",
    "_analyze_single_patent_single_pass",
    "_apply_evaluation_fixes",
    "_compute_risk_from_elements",
    "_evaluate_analysis",
    "_fetch_prosecution_context",
    "_format_compound_for_analysis",
    "_format_patent_for_analysis",
    "analyze_patents",
    "analyze_patents_with_context",
]

logger = structlog.get_logger()


def _format_compound_for_analysis(compound: ResolvedCompound) -> str:
    """Bind step-local get_settings into the shared formatter."""
    return _format_compound_for_analysis_impl(compound, get_settings_fn=get_settings)


def _format_patent_for_analysis(patent: PatentHit, triage: TriageResult | None) -> str:
    """Format and sanitize a patent for the adaptive-analysis prompt.

    Sanitization happens at this LLM-call boundary so that downstream
    helpers in :mod:`praviar_pipeline.pipeline.analysis` do not need to know
    about prompt-injection defences.
    """
    formatted = _format_patent_for_analysis_impl(patent, triage)
    return sanitize_patent_text(formatted)


async def _run_single_pass_stage(
    claude: ClaudeClient,
    patent: PatentHit,
    compound: ResolvedCompound,
    triage: TriageResult | None,
    system_prompt: str,
    toolkit: FTOToolkit | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    spec_text: str = "",
    prosecution_context: dict[str, object] | None = None,
    product_context: object = None,
    intended_actions: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
) -> PatentAnalysis:
    """Run the single-pass internal stage for one patent."""
    return await _analyze_single_patent_single_pass_impl(
        claude,
        patent,
        compound,
        triage,
        system_prompt,
        toolkit=toolkit,
        drawing_evidence=drawing_evidence,
        spec_text=spec_text,
        prosecution_context=prosecution_context,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
        format_compound_for_analysis=_format_compound_for_analysis,
        format_patent_for_analysis=_format_patent_for_analysis,
        compute_risk_from_elements=_compute_risk_from_elements,
    )


async def _run_agentic_escalation_stage(
    claude: ClaudeClient,
    patent: PatentHit,
    compound: ResolvedCompound,
    triage: TriageResult | None,
    product_context: object = None,
    intended_actions: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
) -> tuple[PatentAnalysis, ReasoningTrace]:
    """Run the agentic escalation internal stage for one patent."""
    return await _analyze_single_patent_agentic_impl(
        claude,
        patent,
        compound,
        triage,
        format_compound_for_analysis=_format_compound_for_analysis,
        format_patent_for_analysis=_format_patent_for_analysis,
        compute_risk_from_elements=_compute_risk_from_elements,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )


_analyze_single_patent_single_pass = _run_single_pass_stage
_analyze_single_patent_agentic = _run_agentic_escalation_stage


async def analyze_patents(
    patents: list[PatentHit],
    compound: ResolvedCompound,
    triage_results: list[TriageResult] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    global_escalation_reasons: list[str] | None = None,
) -> tuple[list[PatentAnalysis], list[AnalysisFailure], list[ReasoningTrace]]:
    """Deep claim analysis wrapper returning the historical 3-tuple contract."""
    analyses, failures, traces, _prosecution_cache = await analyze_patents_with_context(
        patents,
        compound,
        triage_results=triage_results,
        drawing_evidence=drawing_evidence,
        global_escalation_reasons=global_escalation_reasons,
    )
    return analyses, failures, traces


async def analyze_patents_with_context(
    patents: list[PatentHit],
    compound: ResolvedCompound,
    triage_results: list[TriageResult] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    global_escalation_reasons: list[str] | None = None,
) -> tuple[
    list[PatentAnalysis],
    list[AnalysisFailure],
    list[ReasoningTrace],
    dict[str, dict[str, object]],
]:
    """Deep claim analysis on triaged patents.

    Sends each patent to Claude Opus for element-by-element analysis,
    followed by an evaluator pass to check for consistency issues.
    Limited to 20 patents max to control cost.

    The governed adaptive path starts with a bounded single-pass stage
    and escalates high-stakes or uncertain patents to the ClaimAnalysisAgent.

    Returns (analyses, failures, reasoning_traces, prosecution_cache) —
    failures are never silently dropped.
    """
    if not patents:
        # Zero input means triage filtered everything out (or upstream search
        # produced nothing). Surface at WARNING so an operator can diagnose.
        logger.warning(
            "step4_received_zero_input",
            patent_count=0,
        )
        logger.debug("step4_entry", patent_count=0)
        return [], [], [], {}

    # Cap at configured limit for cost control
    settings = get_settings()
    patents_to_analyze = patents[: settings.max_analysis_patents]
    logger.info(
        "world_class_analysis_start",
        patent_count=len(patents_to_analyze),
    )
    logger.debug(
        "step4_entry",
        patent_count=len(patents_to_analyze),
        total_input_patents=len(patents),
        max_analysis_patents=settings.max_analysis_patents,
        has_triage_results=triage_results is not None,
        triage_count=len(triage_results) if triage_results else 0,
    )

    spec_text_cache, prosecution_cache = await enrich_patents_for_analysis(
        patents_to_analyze,
        settings,
        bigquery_client_cls=BigQueryClient,
        fetch_prosecution_context=_fetch_prosecution_context,
    )
    triage_map = build_triage_map(triage_results)
    toolkit = build_analysis_toolkit(patents_to_analyze, settings)

    async with ClaudeClient() as claude:
        system_prompt = claude.load_prompt("claim_analysis_system.txt")
        evaluator_prompt = claude.load_prompt("evaluator_system.txt")

        # Single-pass prompts can include multi-perspective instructions; the
        # dedicated perspective agents are triggered later for escalated or
        # medium/high-risk analyses.
        if settings.multi_perspective_enabled:
            try:
                perspective_section = claude.load_prompt("multi_perspective_section.txt")
                system_prompt = system_prompt + "\n\n" + perspective_section
                logger.info("multi_perspective_prompt_injected")
            except FileNotFoundError:
                logger.warning("multi_perspective_prompt_not_found")
        analyses, failures, traces = await run_analysis_batch(
            claude=claude,
            patents_to_analyze=patents_to_analyze,
            compound=compound,
            settings=settings,
            system_prompt=system_prompt,
            evaluator_prompt=evaluator_prompt,
            global_escalation_reasons=global_escalation_reasons,
            triage_map=triage_map,
            spec_text_cache=spec_text_cache,
            prosecution_cache=prosecution_cache,
            toolkit=toolkit,
            drawing_evidence=drawing_evidence,
            analyze_single_pass=_analyze_single_patent_single_pass,
            analyze_agentic=_analyze_single_patent_agentic,
            evaluate_analysis=_evaluate_analysis,
            apply_evaluation_fixes=_apply_evaluation_fixes,
            run_perspectives=_run_perspectives,
            synthesize_perspectives=_synthesize_perspectives,
            format_compound_for_analysis=_format_compound_for_analysis,
            format_patent_for_analysis=_format_patent_for_analysis,
        )
        return analyses, failures, traces, prosecution_cache
