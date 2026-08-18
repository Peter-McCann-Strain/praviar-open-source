"""Operation helpers for the BigQuery client facade."""

from __future__ import annotations

from typing import Any, cast


async def search_patents_by_compound_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            synonyms=synonyms,
            cpc_codes=cpc_codes,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def search_patents_hybrid_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    query_terms: list[str],
    jurisdictions: list[str] | None,
    project: str,
    dataset: str,
    table: str,
    max_results: int,
    rrf_k: int,
) -> list[dict[str, Any]]:
    if not query_terms:
        return []

    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            query_terms=query_terms,
            jurisdictions=jurisdictions,
            project=project,
            dataset=dataset,
            table=table,
            max_results=max_results,
            rrf_k=rrf_k,
        ),
    )


async def get_patent_claims_batch_impl(
    *,
    ensure_client_fn,
    settings_fn,
    query_fn,
    patent_ids: list[str],
) -> dict[str, str]:
    if not patent_ids:
        return {}

    settings = settings_fn()
    return cast(
        "dict[str, str]",
        await query_fn(
            client=ensure_client_fn(),
            settings=settings,
            patent_ids=patent_ids,
        ),
    )


async def get_examiner_citations_batch_impl(
    *,
    ensure_client_fn,
    settings_fn,
    query_fn,
    patent_ids: list[str],
) -> dict[str, dict[str, list[str]]]:
    if not patent_ids:
        return {}

    settings = settings_fn()
    return cast(
        "dict[str, dict[str, list[str]]]",
        await query_fn(
            client=ensure_client_fn(),
            settings=settings,
            patent_ids=patent_ids,
        ),
    )


async def search_compound_annotations_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    name: str,
    inchikey: str,
    max_results: int,
) -> list[dict[str, Any]]:
    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            name=name,
            inchikey=inchikey,
            max_results=max_results,
        ),
    )


async def search_by_cpc_and_keywords_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    cpc_codes: list[str],
    keywords: list[str],
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    if not cpc_codes:
        return []

    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            cpc_codes=cpc_codes,
            keywords=keywords,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def search_by_assignee_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    assignees: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    if not assignees:
        return []

    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            assignees=assignees,
            cpc_codes=cpc_codes,
            max_results=max_results,
            jurisdictions=jurisdictions,
        ),
    )


async def get_patent_metadata_batch_impl(
    *,
    ensure_client_fn,
    settings_fn,
    query_fn,
    patent_ids: list[str],
) -> list[dict[str, Any]]:
    if not patent_ids:
        return []

    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await query_fn(
            client=ensure_client_fn(),
            settings=settings,
            patent_ids=patent_ids,
        ),
    )


async def search_translated_patents_impl(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    search_fn,
    synonyms: list[str],
    jurisdictions: list[str] | None,
    max_results: int,
) -> list[dict[str, Any]]:
    if jurisdictions is None:
        jurisdictions = ["JP", "KR", "CN", "IN", "DE", "FR"]

    settings = settings_fn()
    return cast(
        "list[dict[str, Any]]",
        await search_fn(
            client=ensure_client_fn(),
            settings=settings,
            cache_facade=cache_facade,
            synonyms=synonyms,
            jurisdictions=jurisdictions,
            max_results=max_results,
        ),
    )


async def get_patent_full_text_impl(
    *,
    ensure_client_fn,
    settings_fn,
    query_fn,
    patent_id: str,
) -> str:
    if not patent_id:
        return ""

    settings = settings_fn()
    return cast(
        "str",
        await query_fn(
            client=ensure_client_fn(),
            settings=settings,
            patent_id=patent_id,
        ),
    )


async def close_bigquery_client_impl(client, *, to_thread_fn) -> None:
    if client is None:
        return
    await to_thread_fn(client.close)
