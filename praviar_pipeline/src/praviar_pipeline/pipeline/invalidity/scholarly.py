"""Scholarly prior-art search helpers for Step 6 invalidity analysis."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.openalex import OpenAlexClient
from praviar_pipeline.clients.pubmed import PubMedClient
from praviar_pipeline.clients.semantic_scholar import SemanticScholarClient
from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.pipeline.invalidity import scholarly_helpers, scholarly_sources

if TYPE_CHECKING:
    from datetime import date

    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.invalidity import PriorArtReference

logger = structlog.get_logger()


def _is_relevant_paper(
    paper_title: str,
    paper_abstract: str,
    compound: ResolvedCompound,
) -> bool:
    return bool(scholarly_helpers.is_relevant_paper(paper_title, paper_abstract, compound))


def _build_scholarly_queries(compound: ResolvedCompound) -> list[str]:
    return scholarly_helpers.build_scholarly_queries(compound)


async def _search_s2_multi_query(
    queries: list[str],
    year_before: int,
    compound: ResolvedCompound,
    patent_id: str,
) -> tuple[dict[str, PriorArtReference], list[PriorArtReference]]:
    return await scholarly_sources.search_semantic_scholar_multi_query(
        queries,
        year_before,
        compound,
        patent_id,
        client_factory=SemanticScholarClient,
    )


async def _search_oa_multi_query(
    queries: list[str],
    year_before: int,
    compound: ResolvedCompound,
    patent_id: str,
) -> tuple[dict[str, PriorArtReference], list[PriorArtReference]]:
    return await scholarly_sources.search_openalex_multi_query(
        queries,
        year_before,
        compound,
        patent_id,
        client_factory=OpenAlexClient,
    )


async def _search_pubmed_prior_art(
    compound: ResolvedCompound,
    patent_id: str,
) -> tuple[dict[str, PriorArtReference], list[PriorArtReference]]:
    return await scholarly_sources.search_pubmed_prior_art(
        compound,
        patent_id,
        client_factory=PubMedClient,
    )


async def _search_scholarly_prior_art(
    patent: PatentAnalysis,
    compound: ResolvedCompound,
    priority_date: date | None,
) -> list[PriorArtReference]:
    """Search multiple scholarly databases for prior art predating the patent."""
    if not priority_date:
        logger.info(
            "scholarly_search_skipped",
        )
        return []

    queries = _build_scholarly_queries(compound)
    results = await asyncio.gather(
        _search_s2_multi_query(queries, priority_date.year, compound, patent.patent_id),
        _search_oa_multi_query(queries, priority_date.year, compound, patent.patent_id),
        _search_pubmed_prior_art(compound, patent.patent_id),
        return_exceptions=True,
    )

    source_names = ["semantic_scholar", "openalex", "pubmed"]
    successful_results: list[tuple[dict[str, PriorArtReference], list[PriorArtReference]]] = []
    failures: dict[str, str] = {}

    for index, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.warning(
                "scholarly_search_failed",
                source=source_names[index],
                error_type=type(result).__name__,
            )
            failures[f"scholarly_{source_names[index]}"] = type(result).__name__
            continue

        successful_results.append(result)

    if failures:
        raise SearchSourceFailedError(failures)

    (
        filtered_references,
        skipped_post_priority,
        total_raw,
        unique_by_doi,
        without_doi,
    ) = scholarly_helpers.combine_scholarly_references(
        successful_results,
        priority_date,
    )

    logger.info(
        "scholarly_prior_art_found",
        query_count=len(queries),
        total_raw=total_raw,
        skipped_post_priority=skipped_post_priority,
        after_date_filter=len(filtered_references),
        unique_by_doi=unique_by_doi,
        without_doi=without_doi,
    )
    return filtered_references
