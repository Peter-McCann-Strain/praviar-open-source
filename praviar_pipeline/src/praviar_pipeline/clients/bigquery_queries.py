"""Grouped query helpers for the BigQuery patent client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from praviar_pipeline.clients.bigquery_helpers import get_cached_result, put_cached_result
from praviar_pipeline.clients.bigquery_patents import (
    get_examiner_citations_batch_query,
    get_patent_claims_batch_query,
    get_patent_full_text_query,
    get_patent_metadata_batch_query,
)
from praviar_pipeline.clients.bigquery_searches import (
    search_by_assignee_query,
    search_by_cpc_and_keywords_query,
    search_compound_annotations_query,
    search_patents_by_compound_query,
    search_translated_patents_query,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class _CacheFacade(Protocol):
    def get_cache(self) -> Any: ...


T = TypeVar("T")


def _sorted_or_none(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return sorted(values)


def _sorted_or_empty(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted(values)


async def _search_bigquery_hybrid_query(
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Import the pipeline-owned hybrid query lazily to avoid a client cycle."""
    from praviar_pipeline.pipeline.search.hybrid_bigquery import search_bigquery_hybrid

    return await search_bigquery_hybrid(**kwargs)


async def _run_cached_query(
    *,
    cache_facade: _CacheFacade,
    cache_key: str,
    cache_kwargs: dict[str, Any],
    query_factory: Callable[[], Awaitable[T]],
) -> T:
    cache = cache_facade.get_cache()
    cached = get_cached_result(cache, cache_key, **cache_kwargs)
    if cached is not None:
        return cast("T", cached)
    result = await query_factory()
    put_cached_result(cache, cache_key, result, **cache_kwargs)
    return result


async def search_patents_by_compound_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    return await _run_cached_query(
        cache_facade=cache_facade,
        cache_key="search_patents_by_compound",
        cache_kwargs={
            "synonyms": sorted(synonyms),
            "cpc_codes": _sorted_or_none(cpc_codes),
            "max_results": max_results,
            "jurisdictions": _sorted_or_none(jurisdictions),
        },
        query_factory=lambda: search_patents_by_compound_query(
            client=client,
            settings=settings,
            synonyms=synonyms,
            cpc_codes=cpc_codes,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def search_patents_hybrid_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    query_terms: list[str],
    jurisdictions: list[str] | None,
    project: str,
    dataset: str,
    table: str,
    max_results: int,
    rrf_k: int,
) -> list[dict[str, Any]]:
    normalized_query_terms = list(
        dict.fromkeys(term.strip() for term in query_terms if term.strip())
    )
    if not normalized_query_terms:
        return []
    return cast(
        "list[dict[str, Any]]",
        await _run_cached_query(
            cache_facade=cache_facade,
            cache_key="search_patents_hybrid",
            cache_kwargs={
                # Embedding text preserves term order, so the cache key must too.
                "query_terms": normalized_query_terms,
                "jurisdictions": _sorted_or_none(jurisdictions),
                "project": project,
                "dataset": dataset,
                "table": table,
                "max_results": max_results,
                "rrf_k": rrf_k,
            },
            query_factory=lambda: _search_bigquery_hybrid_query(
                client=client,
                settings=settings,
                query_terms=normalized_query_terms,
                jurisdictions=jurisdictions,
                project=project,
                dataset=dataset,
                table=table,
                limit=max_results,
                rrf_k=rrf_k,
            ),
        ),
    )


async def search_compound_annotations_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    name: str,
    inchikey: str,
    max_results: int,
) -> list[dict[str, Any]]:
    return await _run_cached_query(
        cache_facade=cache_facade,
        cache_key="search_compound_annotations",
        cache_kwargs={
            "name": name.lower(),
            "inchikey": inchikey,
            "max_results": max_results,
        },
        query_factory=lambda: search_compound_annotations_query(
            client=client,
            settings=settings,
            name=name,
            inchikey=inchikey,
            max_results=max_results,
        ),
    )


async def search_by_cpc_and_keywords_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    cpc_codes: list[str],
    keywords: list[str],
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    return await _run_cached_query(
        cache_facade=cache_facade,
        cache_key="search_by_cpc_and_keywords",
        cache_kwargs={
            "cpc_codes": sorted(cpc_codes),
            "keywords": _sorted_or_empty(keywords),
            "max_results": max_results,
            "jurisdictions": _sorted_or_none(jurisdictions),
        },
        query_factory=lambda: search_by_cpc_and_keywords_query(
            client=client,
            settings=settings,
            cpc_codes=cpc_codes,
            keywords=keywords,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def search_by_assignee_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    assignees: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    return await _run_cached_query(
        cache_facade=cache_facade,
        cache_key="search_by_assignee",
        cache_kwargs={
            "assignees": sorted(a.lower() for a in assignees),
            "cpc_codes": _sorted_or_none(cpc_codes),
            "max_results": max_results,
            "jurisdictions": _sorted_or_none(jurisdictions),
        },
        query_factory=lambda: search_by_assignee_query(
            client=client,
            settings=settings,
            assignees=assignees,
            cpc_codes=cpc_codes,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def search_translated_patents_cached(
    *,
    client,
    settings,
    cache_facade: _CacheFacade,
    synonyms: list[str],
    jurisdictions: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    return await _run_cached_query(
        cache_facade=cache_facade,
        cache_key="search_translated_patents",
        cache_kwargs={
            "synonyms": sorted(synonyms),
            "jurisdictions": sorted(jurisdictions),
            "max_results": max_results,
        },
        query_factory=lambda: search_translated_patents_query(
            client=client,
            settings=settings,
            synonyms=synonyms,
            jurisdictions=jurisdictions,
            max_results=max_results,
        ),
    )


async def get_patent_claims_batch(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> dict[str, str]:
    return await get_patent_claims_batch_query(
        client=client,
        settings=settings,
        patent_ids=patent_ids,
    )


async def get_examiner_citations_batch(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> dict[str, dict[str, list[str]]]:
    return await get_examiner_citations_batch_query(
        client=client,
        settings=settings,
        patent_ids=patent_ids,
    )


async def get_patent_metadata_batch(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> list[dict[str, Any]]:
    return await get_patent_metadata_batch_query(
        client=client,
        settings=settings,
        patent_ids=patent_ids,
    )


async def get_patent_full_text(
    *,
    client,
    settings,
    patent_id: str,
) -> str:
    return await get_patent_full_text_query(
        client=client,
        settings=settings,
        patent_id=patent_id,
    )
