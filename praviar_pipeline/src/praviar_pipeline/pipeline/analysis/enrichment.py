"""Patent-enrichment helpers for Step 4 preparation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.analysis.prep_helpers import filter_us_patents
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    record_claims_text_retrieval,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type
from praviar_pipeline.utils.spec_text import chunk_spec_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


async def _enrich_claims_from_bigquery(
    patents_to_analyze: list[PatentHit],
    *,
    bigquery_client: Any,
) -> None:
    missing_claims = [patent for patent in patents_to_analyze if not patent.claims_text]
    if not missing_claims:
        return
    logger.info("enriching_claims_from_bigquery", count=len(missing_claims))
    try:
        claims_map = await bigquery_client.get_patent_claims_batch(
            [patent.patent_id for patent in missing_claims]
        )
    except Exception as exc:
        logger.warning(
            "bigquery_claims_enrichment_failed",
            count=len(missing_claims),
            error_type=safe_exception_type(exc),
        )
        return
    enriched = 0
    for patent in missing_claims:
        text = claims_map.get(patent.patent_id, "")
        if text:
            record_claims_text_retrieval(
                patent,
                text,
                source=PatentSource.BIGQUERY,
                collector_identity="analysis.bigquery_claims",
                upstream_locator=(
                    "https://console.cloud.google.com/bigquery?project="
                    f"patents-public-data&patent={patent.patent_id}"
                ),
            )
            enriched += 1
    logger.info("claims_enrichment_done", enriched=enriched, total=len(missing_claims))


async def _enrich_claims_from_epo_ops(
    patents_to_analyze: list[PatentHit],
) -> None:
    """Fetch English claims text from EPO OPS for patents still missing it.

    Runs after BigQuery and PatentsView attempts in the analysis enrichment
    chain. The configured EPO OPS DOCDB source is attempted when earlier
    collectors leave claims absent; source health records any remaining gap.
    """
    missing_claims = [patent for patent in patents_to_analyze if not patent.claims_text]
    if not missing_claims:
        return

    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    logger.info("analysis_epo_ops_claims_start", count=len(missing_claims))
    enriched = 0
    consecutive_empty = 0
    circuit_breaker_threshold = 10

    async with EPOOPSClient() as epo_client:
        for patent in missing_claims:
            try:
                text = await epo_client.get_claims_text(patent.patent_id)
                if text:
                    record_claims_text_retrieval(
                        patent,
                        text,
                        source=PatentSource.EPO_SEARCH,
                        collector_identity="analysis.epo_ops_claims",
                        upstream_locator=(
                            "https://ops.epo.org/3.2/rest-services/published-data/"
                            f"publication/epodoc/{patent.patent_id}/claims"
                        ),
                    )
                    enriched += 1
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= circuit_breaker_threshold:
                        logger.info(
                            "analysis_epo_ops_claims_circuit_open",
                            consecutive_empty=consecutive_empty,
                            remaining=len(missing_claims) - (missing_claims.index(patent) + 1),
                        )
                        break
            except Exception as exc:
                logger.debug(
                    "analysis_epo_ops_claims_fetch_failed",
                    error_type=safe_exception_type(exc),
                )

    if enriched:
        logger.info("analysis_epo_ops_claims_done", enriched=enriched, total=len(missing_claims))
    else:
        logger.warning(
            "analysis_epo_ops_claims_empty",
            count=len(missing_claims),
        )


async def _enrich_claims_from_patentsview(
    patents_to_analyze: list[PatentHit],
    *,
    settings: Settings,
) -> None:
    still_missing = [
        patent
        for patent in patents_to_analyze
        if not patent.claims_text and patent.patent_id.startswith("US")
    ]
    if not still_missing:
        return

    try:
        from praviar_pipeline.clients.patentsview import PatentsViewClient

        if settings.patentsview_api_key:
            async with PatentsViewClient() as patentsview_client:
                patentsview_enriched = 0
                for patent in still_missing[:10]:
                    try:
                        text = await patentsview_client.get_patent_claims_text(patent.patent_id)
                        if text:
                            record_claims_text_retrieval(
                                patent,
                                text,
                                source=PatentSource.PATENTSVIEW,
                                collector_identity="analysis.patentsview_claims",
                                upstream_locator=(
                                    "https://search.patentsview.org/api/v1/patent/"
                                    f"?patent_id={patent.patent_id}"
                                ),
                            )
                            patentsview_enriched += 1
                    except Exception as exc:
                        logger.warning(
                            "patentsview_claims_fetch_failed",
                            error_type=safe_exception_type(exc),
                        )
                if patentsview_enriched:
                    logger.info(
                        "patentsview_claims_fallback",
                        enriched=patentsview_enriched,
                    )
    except Exception as exc:
        logger.warning(
            "patentsview_claims_fallback_skipped",
            error_type=safe_exception_type(exc),
        )


async def _build_spec_text_cache(
    patents_to_analyze: list[PatentHit],
    *,
    bigquery_client: Any,
    settings: Settings,
) -> dict[str, str]:
    """Fetch and right-size specification text for Step 4 claim construction.

    Under Phillips v. AWH Corp. claim terms are construed against the patent
    specification, so the analysed patents need their specification text in
    hand. Coverage extends to ``settings.spec_text_max_patents`` (a principled
    cap on BigQuery cost) rather than the historical first ten, and oversized
    specifications are reduced by definition-aware chunking
    (:func:`~praviar_pipeline.utils.spec_text.chunk_spec_text`) instead of a
    blunt character truncation that silently discarded later definitions.
    """
    spec_text_cache: dict[str, str] = {}
    max_patents = settings.spec_text_max_patents
    max_chars = settings.spec_text_max_chars
    if len(patents_to_analyze) > max_patents:
        raise SourceUnavailableError(
            "bigquery",
            "specification coverage exceeds configured analysis cap",
        )
    for patent in patents_to_analyze:
        retrieval_failure: SourceUnavailableError | None = None
        try:
            full_text = await bigquery_client.get_patent_full_text(patent.patent_id)
            if not full_text:
                raise SourceUnavailableError(
                    "bigquery",
                    "required patent specification is unavailable",
                )
            spec_text_cache[patent.patent_id] = chunk_spec_text(
                full_text,
                max_chars=max_chars,
            )
        except SourceUnavailableError:
            raise
        except Exception as exc:
            logger.warning(
                "spec_text_fetch_failed",
                error_type=safe_exception_type(exc),
            )
            retrieval_failure = SourceUnavailableError(
                "bigquery",
                "required patent specification retrieval failed",
            )
        if retrieval_failure is not None:
            raise retrieval_failure
    if spec_text_cache:
        logger.info(
            "spec_text_enrichment_done",
            enriched=len(spec_text_cache),
            patents_considered=min(len(patents_to_analyze), max_patents),
        )

    return spec_text_cache


async def _build_prosecution_cache(
    patents_to_analyze: list[PatentHit],
    *,
    settings: Settings,
    fetch_prosecution_context: Callable[[str], Awaitable[dict[str, Any] | None]],
) -> dict[str, dict[str, Any]]:
    prosecution_cache: dict[str, dict[str, Any]] = {}
    us_patents = filter_us_patents(patents_to_analyze)
    if not us_patents or not settings.uspto_odp_api_key:
        return prosecution_cache

    logger.info("prosecution_history_fetch_start", count=len(us_patents))
    prosecution_results = await asyncio.gather(
        *(fetch_prosecution_context(patent.patent_id) for patent in us_patents[:50]),
        return_exceptions=True,
    )
    for patent, result in zip(us_patents[:50], prosecution_results, strict=False):
        if isinstance(result, dict) and result:
            prosecution_cache[patent.patent_id] = result
        elif result is None:
            logger.warning(
                "prosecution_context_fetch_failed",
            )
        elif isinstance(result, BaseException):
            logger.warning(
                "prosecution_context_gather_failed",
                error_type=safe_exception_type(result),
            )
    if prosecution_cache:
        logger.info(
            "prosecution_history_fetch_done",
            enriched=len(prosecution_cache),
            total_us=len(us_patents),
        )
    return prosecution_cache


async def enrich_patents_for_analysis_impl(
    patents_to_analyze: list[PatentHit],
    settings: Settings,
    *,
    bigquery_client_cls: Any,
    fetch_prosecution_context: Callable[[str], Awaitable[dict[str, Any] | None]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Enrich claims/spec text and fetch prosecution history for analysis."""
    async with bigquery_client_cls() as bigquery_client:
        await _enrich_claims_from_bigquery(
            patents_to_analyze,
            bigquery_client=bigquery_client,
        )
        await _enrich_claims_from_patentsview(
            patents_to_analyze,
            settings=settings,
        )
        # EPO OPS fallback: fetch English claims for patents still missing text
        # after BigQuery (quota) and PatentsView (US-only, no claims endpoint).
        await _enrich_claims_from_epo_ops(patents_to_analyze)
        spec_text_cache = await _build_spec_text_cache(
            patents_to_analyze,
            bigquery_client=bigquery_client,
            settings=settings,
        )

    prosecution_cache = await _build_prosecution_cache(
        patents_to_analyze,
        settings=settings,
        fetch_prosecution_context=fetch_prosecution_context,
    )
    return spec_text_cache, prosecution_cache
