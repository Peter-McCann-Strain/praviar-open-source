"""Database-specific scholarly prior-art source search helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

import structlog

from praviar_pipeline.clients.lens import LensClient
from praviar_pipeline.clients.openalex import OpenAlexClient
from praviar_pipeline.clients.pubmed import PubMedClient
from praviar_pipeline.clients.semantic_scholar import SemanticScholarClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.pipeline.invalidity import scholarly_helpers

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.invalidity import PriorArtReference

SearchResultBuckets = tuple[dict[str, "PriorArtReference"], list["PriorArtReference"]]
SearchExecutor = Callable[[Any, str, int, int, int], Awaitable[list[dict]]]
ReferenceBuilder = Callable[[dict], "PriorArtReference"]
AbstractGetter = Callable[[dict], str]

logger = structlog.get_logger()


async def _search_multi_query_source(
    queries: list[str],
    year_before: int,
    compound: ResolvedCompound,
    patent_id: str,
    *,
    client_factory: Callable[[], Any],
    search_executor: SearchExecutor,
    reference_builder: ReferenceBuilder,
    abstract_getter: AbstractGetter,
    failure_event: str,
    source_name: str,
) -> SearchResultBuckets:
    """Run a multi-query scholarly search with shared relevance and dedupe rules."""
    refs_by_doi: dict[str, PriorArtReference] = {}
    refs_no_doi: list[PriorArtReference] = []

    failure_type: str | None = None
    try:
        settings = get_settings()
        async with client_factory() as client:
            for index, query in enumerate(queries):
                max_results = (
                    settings.scholarly_primary_max_results
                    if index == 0
                    else settings.scholarly_secondary_max_results
                )
                works = await search_executor(
                    client,
                    query,
                    year_before,
                    index,
                    max_results,
                )

                for work in works:
                    title = work.get("title", "")
                    abstract = abstract_getter(work)
                    if not scholarly_helpers.is_relevant_paper(title, abstract, compound):
                        continue
                    scholarly_helpers.collect_reference(
                        reference_builder(work),
                        refs_by_doi,
                        refs_no_doi,
                    )

                if index == 0 and len(works) >= settings.scholarly_early_exit_threshold:
                    break
    except Exception as exc:
        # Client/retry exceptions can retain the full request URL, including
        # query-string API keys. Keep only the class name and raise the stable
        # public error *after* leaving this except block so Python does not
        # attach the sensitive exception as __context__.
        failure_type = type(exc).__name__
        logger.error(
            failure_event,
            error_type=failure_type,
        )

    if failure_type is not None:
        raise SourceUnavailableError(source_name, "scholarly search failed") from None

    return refs_by_doi, refs_no_doi


async def search_semantic_scholar_multi_query(
    queries: list[str],
    year_before: int,
    compound: ResolvedCompound,
    patent_id: str,
    *,
    client_factory: Callable[[], Any] = SemanticScholarClient,
) -> SearchResultBuckets:
    async def run_query(
        client,
        query: str,
        before_year: int,
        index: int,
        max_results: int,
    ) -> list[dict]:
        fields = ["Chemistry"] if index == 0 else ["Chemistry", "Biology"]
        return cast(
            "list[dict]",
            await client.search_papers(
                query,
                year_before=before_year,
                fields_of_study=fields,
                max_results=max_results,
            ),
        )

    return await _search_multi_query_source(
        queries,
        year_before,
        compound,
        patent_id,
        client_factory=client_factory,
        search_executor=run_query,
        reference_builder=scholarly_helpers.build_semantic_scholar_reference,
        abstract_getter=lambda paper: paper.get("abstract", "") or "",
        failure_event="s2_scholarly_search_failed",
        source_name="semantic_scholar",
    )


async def search_openalex_multi_query(
    queries: list[str],
    year_before: int,
    compound: ResolvedCompound,
    patent_id: str,
    *,
    client_factory: Callable[[], Any] = OpenAlexClient,
) -> SearchResultBuckets:
    async def run_query(
        client,
        query: str,
        before_year: int,
        index: int,
        max_results: int,
    ) -> list[dict]:
        del index
        return cast(
            "list[dict]",
            await client.search_works(
                query,
                year_before=before_year,
                max_results=max_results,
            ),
        )

    return await _search_multi_query_source(
        queries,
        year_before,
        compound,
        patent_id,
        client_factory=client_factory,
        search_executor=run_query,
        reference_builder=scholarly_helpers.build_openalex_reference,
        abstract_getter=lambda _: "",
        failure_event="openalex_scholarly_search_failed",
        source_name="openalex",
    )


async def search_lens_scholarly_by_patent(
    patent_id: str,
    compound: ResolvedCompound,
    *,
    client_factory: Callable[[], Any] = LensClient,
) -> SearchResultBuckets:
    """Search Lens scholarly literature linked to the patent."""
    refs_by_doi: dict[str, PriorArtReference] = {}
    refs_no_doi: list[PriorArtReference] = []
    settings = get_settings()

    if not settings.lens_api_key:
        raise ConfigurationError(
            "LENS_API_KEY is required for Lens scholarly prior-art search",
            source="lens_scholarly",
            step="invalidity",
        )

    failure_type: str | None = None
    try:
        async with client_factory() as lens_client:
            scholarly_works = await lens_client.search_scholarly_by_patent(
                patent_id,
                max_results=10,
            )
            for work in scholarly_works:
                title = work.get("title", "")
                if not scholarly_helpers.is_relevant_paper(title, "", compound):
                    continue
                scholarly_helpers.collect_reference(
                    scholarly_helpers.build_lens_reference(work),
                    refs_by_doi,
                    refs_no_doi,
                )
    except Exception as exc:
        failure_type = type(exc).__name__
        logger.error(
            "lens_scholarly_search_failed",
            error_type=failure_type,
        )

    if failure_type is not None:
        raise SourceUnavailableError("lens_scholarly", "scholarly search failed") from None

    return refs_by_doi, refs_no_doi


async def search_pubmed_prior_art(
    compound: ResolvedCompound,
    patent_id: str,
    *,
    client_factory: Callable[[], Any] = PubMedClient,
) -> SearchResultBuckets:
    """Search PubMed/MEDLINE for biomedical prior art."""
    refs_by_doi: dict[str, PriorArtReference] = {}
    refs_no_doi: list[PriorArtReference] = []

    failure_type: str | None = None
    try:
        async with client_factory() as pubmed_client:
            papers = await pubmed_client.search_compound_literature(
                compound.name,
                synonyms=compound.synonyms[:5],
                cas_numbers=compound.cas_numbers[:3],
                max_results=20,
            )
            for paper in papers:
                title = paper.get("title", "")
                if not scholarly_helpers.is_relevant_paper(title, "", compound):
                    continue
                scholarly_helpers.collect_reference(
                    scholarly_helpers.build_pubmed_reference(paper),
                    refs_by_doi,
                    refs_no_doi,
                )
    except Exception as exc:
        failure_type = type(exc).__name__
        logger.error(
            "pubmed_scholarly_search_failed",
            error_type=failure_type,
        )

    if failure_type is not None:
        raise SourceUnavailableError("pubmed", "scholarly search failed") from None

    return refs_by_doi, refs_no_doi
