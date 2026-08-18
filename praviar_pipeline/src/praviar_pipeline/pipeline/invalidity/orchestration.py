"""Deterministic orchestration helpers for invalidity assessment."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from praviar_pipeline.errors import InvalidityAssessmentError, SourceUnavailableError
from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.invalidity import InvalidityAssessment

if TYPE_CHECKING:
    import asyncio
    from datetime import date

    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.invalidity import PriorArtReference, PTABResult
    from praviar_pipeline.models.patent import PatentHit


InvalidityUsageTuple = tuple[InvalidityAssessment, int, int]
InvalidityLlmCallable = Callable[..., Awaitable[tuple]]


@dataclass(slots=True)
class InvalidityContext:
    to_assess: list[PatentAnalysis]
    priority_dates: dict[str, date | None]


def build_invalidity_context(
    blocking_patents: list[PatentAnalysis],
    patent_hits: list[PatentHit] | None,
    *,
    compound_name: str,
    logger,
) -> InvalidityContext:
    """Filter invalidity targets and normalize lookup state."""
    to_assess = [p for p in blocking_patents if p.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)]
    logger.debug(
        "step6_entry",
        total_patents=len(blocking_patents),
        blocking_count=len(to_assess),
        has_patent_hits=patent_hits is not None,
        patent_hits_count=len(patent_hits) if patent_hits else 0,
    )

    if blocking_patents and not to_assess:
        # Non-empty input but nothing to assess means every analysis landed at
        # LOW or CLEAR. Surface at WARNING with the risk distribution so an
        # operator can tell a genuine all-clear landscape apart from analyses
        # that were quietly downgraded upstream.
        logger.warning(
            "step6_no_blocking_after_filter",
            total_patents=len(blocking_patents),
        )

    priority_dates = {}
    if patent_hits:
        for hit in patent_hits:
            priority_dates[hit.patent_id] = hit.priority_date

    return InvalidityContext(to_assess=to_assess, priority_dates=priority_dates)


async def fetch_examiner_citations(
    to_assess: list[PatentAnalysis],
    *,
    client_factory,
    logger,
) -> dict[str, dict[str, list[str]]]:
    """Batch-fetch examiner citations for the blocking patents."""
    failure_type: str | None = None
    try:
        async with client_factory() as client:
            citations_map = await client.get_examiner_citations_batch(
                [analysis.patent_id for analysis in to_assess]
            )
            logger.info(
                "examiner_citations_fetched",
                patents_with_citations=sum(
                    1
                    for value in citations_map.values()
                    if value.get("examiner") or value.get("applicant")
                ),
                total=len(to_assess),
            )
            return cast("dict[str, dict[str, list[str]]]", citations_map)
    except Exception as exc:
        failure_type = type(exc).__name__
        logger.error(
            "examiner_citations_fetch_failed",
            error_type=failure_type,
        )

    if failure_type is not None:
        # Raise outside the except block so the original provider exception
        # cannot survive as a secret-bearing implicit exception context.
        raise SourceUnavailableError(
            "examiner_citations",
            "examiner citation fetch failed",
        ) from None

    raise AssertionError("examiner citation fetch reached an unreachable state")


async def process_single_patent(
    analysis,
    *,
    semaphore: asyncio.Semaphore,
    claude,
    system_prompt: str,
    compound: ResolvedCompound,
    priority_dates: dict[str, date | None],
    citations_map: dict[str, dict[str, list[str]]],
    drawing_evidence: DrawingEvidenceStore | None,
    ptab_checker: Callable[[str], Awaitable[PTABResult]],
    prior_art_searcher: Callable[
        [PatentAnalysis, ResolvedCompound, date | None],
        Awaitable[list[PriorArtReference]],
    ],
    llm_assessor: InvalidityLlmCallable,
    strength_chooser: Callable[[str, list[PriorArtReference], PTABResult], str],
) -> InvalidityUsageTuple:
    """Run the full invalidity pipeline for a single patent."""
    async with semaphore:
        ptab = await ptab_checker(analysis.patent_id)
        priority_date = priority_dates.get(analysis.patent_id)
        prior_art = await prior_art_searcher(analysis, compound, priority_date)
        patent_citations = citations_map.get(analysis.patent_id)

        (
            arguments,
            wd_issues,
            reasoning,
            confidence,
            llm_strength,
            confidence_band,
            claim_charts,
            graham_factors,
            enablement_screening,
            usage,
        ) = await llm_assessor(
            claude,
            analysis,
            compound,
            ptab,
            system_prompt,
            prior_art=prior_art,
            examiner_citations=patent_citations,
            drawing_evidence=drawing_evidence,
        )

        strength = strength_chooser(llm_strength, prior_art, ptab)
        assessment = InvalidityAssessment(
            patent_id=analysis.patent_id,
            claim_numbers=[claim.claim_number for claim in analysis.claims_analyzed],
            ptab=ptab,
            prior_art=prior_art,
            arguments=arguments,
            claim_charts=claim_charts,
            graham_factors=graham_factors,
            enablement_screening=enablement_screening,
            written_description_issues=wd_issues,
            overall_invalidity_strength=strength,
            reasoning=reasoning,
            confidence=confidence,
            confidence_band=confidence_band,
        )
        return (
            assessment,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )


def aggregate_invalidity_results(
    results: list[InvalidityUsageTuple | BaseException],
    *,
    compound_name: str,
    logger,
) -> tuple[list[InvalidityAssessment], int, int]:
    """Normalize gathered invalidity results into the public return tuple."""
    assessments: list[InvalidityAssessment] = []
    total_input = 0
    total_output = 0
    failures: list[BaseException] = []

    for result in results:
        if isinstance(result, BaseException):
            logger.warning(
                "invalidity_patent_failed",
                error_type=type(result).__name__,
            )
            failures.append(result)
            continue

        assessment, input_tokens, output_tokens = result
        assessments.append(assessment)
        total_input += input_tokens
        total_output += output_tokens

    if failures:
        for exc in failures:
            logger.warning(
                "invalidity_assessment_failed",
                error_type=type(exc).__name__,
            )
        raise InvalidityAssessmentError(
            failure_types=tuple(type(exc).__name__ for exc in failures),
        ) from None

    logger.info(
        "invalidity_assessment_complete",
        assessed=len(assessments),
        with_ptab=sum(1 for assessment in assessments if assessment.ptab.has_been_challenged),
        with_prior_art=sum(1 for assessment in assessments if assessment.prior_art),
    )
    logger.debug(
        "step6_output_summary",
        assessed=len(assessments),
        with_ptab=sum(1 for assessment in assessments if assessment.ptab.has_been_challenged),
        with_prior_art=sum(1 for assessment in assessments if assessment.prior_art),
        strength_distribution={
            strength: sum(
                1
                for assessment in assessments
                if assessment.overall_invalidity_strength == strength
            )
            for strength in ("strong", "moderate", "weak")
        },
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )

    return assessments, total_input, total_output
