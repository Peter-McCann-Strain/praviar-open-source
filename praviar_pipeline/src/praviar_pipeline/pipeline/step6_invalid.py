"""Step 6: Patent Invalidity Analysis — PTAB check + scholarly prior art + LLM assessment."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.clients.ptab import PTABClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.invalidity import llm as invalidity_llm
from praviar_pipeline.pipeline.invalidity import orchestration as invalidity_orchestration
from praviar_pipeline.pipeline.invalidity import ptab as invalidity_ptab
from praviar_pipeline.pipeline.invalidity import scholarly as invalidity_scholarly
from praviar_pipeline.pipeline.invalidity.scoring import (
    choose_invalidity_strength,
)
from praviar_pipeline.utils.dates import parse_date as _parse_date

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.invalidity import (
        InvalidityAssessment,
        PriorArtReference,
        PTABResult,
    )
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


# Direct aliases for trivial passthroughs — preserve the names that downstream
# tests import from this step facade, but skip the wrapper-call indirection.
_is_relevant_paper = invalidity_scholarly._is_relevant_paper
_build_scholarly_queries = invalidity_scholarly._build_scholarly_queries
_search_s2_multi_query = invalidity_scholarly._search_s2_multi_query
_search_oa_multi_query = invalidity_scholarly._search_oa_multi_query
_search_scholarly_prior_art = invalidity_scholarly._search_scholarly_prior_art


async def _check_ptab(patent_id: str) -> PTABResult:
    """Query PTAB API for proceedings against this patent.

    PTAB is part of the invalidity evidence record. Auth/network failures
    propagate so the run does not mistake an unavailable PTAB source for a
    patent with no challenges.
    """
    return await invalidity_ptab.check_ptab_impl(
        patent_id,
        client_factory=PTABClient,
        parse_date_fn=_parse_date,
        logger=logger,
    )


async def _assess_invalidity_llm(
    claude: ClaudeClient,
    analysis: PatentAnalysis,
    compound: ResolvedCompound,
    ptab: PTABResult,
    system_prompt: str,
    prior_art: list[PriorArtReference] | None = None,
    examiner_citations: dict[str, list[str]] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
) -> tuple:
    """LLM assessment of invalidity arguments.

    Returns tuple of (prior_art, written_description_issues, reasoning, confidence,
    overall_strength, confidence_band, claim_charts, graham_factors,
    enablement_screening, usage).
    """
    return await invalidity_llm.assess_invalidity_llm_impl(
        claude,
        analysis,
        compound,
        ptab,
        system_prompt,
        prior_art=prior_art,
        examiner_citations=examiner_citations,
        drawing_evidence=drawing_evidence,
        settings_factory=get_settings,
    )


async def assess_invalidity(
    blocking_patents: list[PatentAnalysis],
    compound: ResolvedCompound,
    patent_hits: list[PatentHit] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
) -> tuple[list[InvalidityAssessment], int, int]:
    """Assess invalidity for blocking patents (HIGH/MEDIUM risk).

    Args:
        blocking_patents: Patent analyses from Step 4.
        compound: The resolved compound being analyzed.
        patent_hits: Original search hits (for priority date lookup).
        drawing_evidence: Drawing analysis results for structural evidence.
    """
    if not blocking_patents:
        # Zero input means step4 produced no blocking analyses.  Surface at
        # WARNING so an operator can diagnose an upstream search failure
        # rather than silently producing an empty invalidity report.
        logger.warning(
            "step6_received_zero_input",
            blocking_patents_count=0,
        )
    context = invalidity_orchestration.build_invalidity_context(
        blocking_patents,
        patent_hits,
        compound_name=compound.name,
        logger=logger,
    )

    if not context.to_assess:
        logger.info("invalidity_no_blocking_patents")
        return [], 0, 0

    logger.info(
        "invalidity_assessment_start",
        patent_count=len(context.to_assess),
    )

    citations_map = await invalidity_orchestration.fetch_examiner_citations(
        context.to_assess,
        client_factory=BigQueryClient,
        logger=logger,
    )

    async with ClaudeClient() as claude:
        system_prompt = claude.load_prompt("invalidity_screening_system.txt")
        semaphore = asyncio.Semaphore(get_settings().analysis_concurrency)
        results = await asyncio.gather(
            *[
                invalidity_orchestration.process_single_patent(
                    analysis,
                    semaphore=semaphore,
                    claude=claude,
                    system_prompt=system_prompt,
                    compound=compound,
                    priority_dates=context.priority_dates,
                    citations_map=citations_map,
                    drawing_evidence=drawing_evidence,
                    ptab_checker=_check_ptab,
                    prior_art_searcher=_search_scholarly_prior_art,
                    llm_assessor=_assess_invalidity_llm,
                    strength_chooser=choose_invalidity_strength,
                )
                for analysis in context.to_assess
            ],
            return_exceptions=True,
        )
        return invalidity_orchestration.aggregate_invalidity_results(
            results,
            compound_name=compound.name,
            logger=logger,
        )
