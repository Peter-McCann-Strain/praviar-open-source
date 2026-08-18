"""Narrative generation helpers for report generation."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import anthropic
import httpx
import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment

logger = structlog.get_logger()
_PATENT_SPLIT_RE = re.compile(
    r"(?=^###?\s*(?:US|EP|WO|JP|KR|CN|IN|CA|AU|GB|DE|FR)[-\s]?\d)", re.MULTILINE
)
_PATENT_ID_RE = re.compile(
    r"(?:US|EP|WO|JP|KR|CN|IN|CA|AU|GB|DE|FR)[-\s]?[\d,\s]{4,}(?:\s?[A-Z]\d?)?"
)


def _build_patent_details(
    analyses: list[PatentAnalysis],
    patent_hits: list | None,
) -> dict[str, dict]:
    patent_details: dict[str, dict] = {}
    if not patent_hits:
        return patent_details

    analyzed_patent_ids = {analysis.patent_id for analysis in analyses}
    for patent_hit in patent_hits:
        if patent_hit.patent_id in analyzed_patent_ids and hasattr(patent_hit, "model_dump"):
            patent_details[patent_hit.patent_id] = patent_hit.model_dump(mode="json")
    return patent_details


def _extract_per_patent_narratives(key_patents_content: str) -> dict[str, str]:
    """Extract per-patent narrative blocks from the key-patents section."""
    narratives: dict[str, str] = {}
    for part in _PATENT_SPLIT_RE.split(key_patents_content):
        ids = _PATENT_ID_RE.findall(part)
        if not ids:
            continue
        patent_id = ids[0].replace("-", "").replace(" ", "").replace(",", "").strip()
        narratives[patent_id] = part.strip()[:1500]
    return narratives


async def _generate_patent_narratives(
    claude: ClaudeClient,
    analyses: list[PatentAnalysis],
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
    compound: ResolvedCompound,
    patent_details: dict[str, dict] | None = None,
) -> tuple[dict[str, str], int, int]:
    """Generate per-patent natural language narratives."""
    system_prompt = claude.load_prompt("patent_narrative_system.txt")
    narratives: dict[str, str] = {}
    total_input_tokens = 0
    total_output_tokens = 0

    doe_by_patent: dict[str, list[DoEAssessment]] = {}
    for assessment in doe_assessments:
        doe_by_patent.setdefault(assessment.patent_id, []).append(assessment)

    invalidity_by_patent = {
        assessment.patent_id: assessment for assessment in invalidity_assessments
    }

    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.narrative_concurrency)

    async def _call_with_retry(system: str, user: str) -> tuple[str, dict]:
        failure_type: str | None = None
        for attempt in range(settings.narrative_max_retries):
            try:
                return await claude.complete_text(
                    system=system,
                    user=user,
                    model=claude._models.analysis,
                    max_tokens=settings.report_narrative_max_tokens,
                    effort=settings.thinking_effort_report,
                    cache_system=True,
                )
            except (
                httpx.HTTPError,
                ConnectionError,
                TimeoutError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APITimeoutError,
            ) as exc:
                failure_type = safe_exception_type(exc)
                if attempt < settings.narrative_max_retries - 1:
                    wait = min(2**attempt, settings.narrative_retry_max_wait)
                    logger.warning(
                        "narrative_retry",
                        attempt=attempt + 1,
                        max_retries=settings.narrative_max_retries,
                        wait=wait,
                        error_type=failure_type,
                    )
                    await asyncio.sleep(wait)
        if failure_type is not None:
            raise SourceUnavailableError(
                "report_narrative",
                "narrative generation failed",
            ) from None
        raise AssertionError("narrative retry loop reached an unreachable state")

    async def _generate_one(analysis: PatentAnalysis) -> tuple[str, str, int, int]:
        doe_context = ""
        if analysis.patent_id in doe_by_patent:
            doe_results = doe_by_patent[analysis.patent_id]
            equivalent_count = sum(1 for assessment in doe_results if assessment.overall_equivalent)
            doe_context = f"\nDoE: {equivalent_count}/{len(doe_results)} elements found equivalent."

        invalidity_context = ""
        if analysis.patent_id in invalidity_by_patent:
            invalidity = invalidity_by_patent[analysis.patent_id]
            invalidity_context = (
                f"\nInvalidity: {invalidity.overall_invalidity_strength} "
                f"({invalidity.confidence_band} confidence)."
            )

        claims_summary = []
        for claim in analysis.claims_analyzed:
            met_count = sum(1 for element in claim.elements if element.status.value == "met")
            claims_summary.append(
                f"Claim {claim.claim_number}: {met_count}/{len(claim.elements)} elements met"
            )

        enrichment_context = ""
        if patent_details and analysis.patent_id in patent_details:
            detail = patent_details[analysis.patent_id]

            ptab_proceedings = detail.get("ptab_proceedings", [])
            if ptab_proceedings:
                ptab_lines = [
                    f"  - {proceeding.get('proceeding_type', 'Unknown')} "
                    f"{proceeding.get('proceeding_number', '')}: "
                    f"{proceeding.get('status', 'Unknown')} "
                    f"(petitioner: {proceeding.get('petitioner', 'Unknown')})"
                    for proceeding in ptab_proceedings
                ]
                enrichment_context += "\nPTAB Proceedings:\n" + chr(10).join(ptab_lines)

            orange_book = detail.get("orange_book_info")
            if orange_book and orange_book.get("is_listed"):
                products = ", ".join(orange_book.get("product_names", [])[:3])
                enrichment_context += (
                    "\nOrange Book: Listed"
                    f" (NDA: {', '.join(orange_book.get('nda_numbers', []))},"
                    f" products: {products})"
                )

            patent_term_info = detail.get("patent_term_info")
            if patent_term_info and patent_term_info.get("adjusted_expiry"):
                terminal_disclaimer_note = ""
                if patent_term_info.get("terminal_disclaimer"):
                    terminal_disclaimer_note = (
                        ", terminal disclaimer "
                        f"(linked to {patent_term_info.get('td_linked_patent', 'unknown')})"
                    )
                enrichment_context += (
                    f"\nPatent Term: expires {patent_term_info['adjusted_expiry']}"
                    f", PTA {patent_term_info.get('pta_days', 0)} days"
                    f", maintenance {patent_term_info.get('maintenance_fee_status', 'unknown')}"
                    f"{terminal_disclaimer_note}"
                )

            assignments = detail.get("assignments", [])
            if assignments:
                latest_assignment = assignments[0]
                enrichment_context += (
                    f"\nOwnership: {latest_assignment.get('conveyance', 'Transfer')}"
                    f" ({latest_assignment.get('recorded_date', 'unknown')})"
                )

        evidence = f"""Patent: {analysis.patent_id}
Title: {analysis.title}
Assignee: {analysis.assignee}
Risk Level: {analysis.risk_level.value}
Expiry: {analysis.expiry_date or "unknown"}
Compound: {compound.name}

Claims Analysis:
{chr(10).join(claims_summary)}

Risk Summary: {analysis.risk_summary}{doe_context}{invalidity_context}{enrichment_context}"""
        user_prompt = (
            "Draft a concise patent narrative using only the supplied evidence.\n\n"
            + sanitize_untrusted_text(evidence, data_type="report_patent_evidence")
        )

        async with semaphore:
            narrative, usage = await _call_with_retry(system_prompt, user_prompt)

        return (
            analysis.patent_id,
            narrative,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

    results = await asyncio.gather(
        *[_generate_one(analysis) for analysis in analyses],
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, BaseException):
            logger.error(
                "narrative_generation_failed",
                error_type=safe_exception_type(result),
            )
            continue

        patent_id, narrative, input_tokens, output_tokens = result
        narratives[patent_id] = narrative
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        logger.debug(
            "narrative_generated",
            narrative_length=len(narrative),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    return narratives, total_input_tokens, total_output_tokens
