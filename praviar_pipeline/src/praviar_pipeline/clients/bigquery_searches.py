"""Search-query implementations for the BigQuery patent client."""

from __future__ import annotations

import asyncio
from typing import Any

from praviar_pipeline.clients.bigquery_helpers import (
    build_job_config,
    rows_to_dicts,
)
from praviar_pipeline.clients.bigquery_searches_sql import (
    build_assignee_search_query,
    build_compound_annotations_query,
    build_compound_search_query,
    build_cpc_and_keywords_search_query,
    build_translated_patents_search_query,
)


async def search_patents_by_compound_query(
    *,
    client,
    settings,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql, query_params = build_compound_search_query(
        synonyms=synonyms,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=ScalarQueryParameter,
    )
    if sql is None:
        return []

    job_config = build_job_config(
        query_parameters=query_params,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)


async def search_compound_annotations_query(
    *,
    client,
    settings,
    name: str,
    inchikey: str,
    max_results: int,
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql, query_params = build_compound_annotations_query(
        name=name,
        inchikey=inchikey,
        max_results=max_results,
        scalar_query_parameter_cls=ScalarQueryParameter,
    )

    job_config = build_job_config(
        query_parameters=query_params,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)


async def search_by_cpc_and_keywords_query(
    *,
    client,
    settings,
    cpc_codes: list[str],
    keywords: list[str],
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql, query_params = build_cpc_and_keywords_search_query(
        cpc_codes=cpc_codes,
        keywords=keywords,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=ScalarQueryParameter,
    )
    if sql is None:
        return []

    job_config = build_job_config(
        query_parameters=query_params,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)


async def search_by_assignee_query(
    *,
    client,
    settings,
    assignees: list[str],
    cpc_codes: list[str] | None,
    max_results: int,
    jurisdictions: list[str] | None,
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql, query_params = build_assignee_search_query(
        assignees=assignees,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=ScalarQueryParameter,
    )
    if sql is None:
        return []

    job_config = build_job_config(
        query_parameters=query_params,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)


async def search_translated_patents_query(
    *,
    client,
    settings,
    synonyms: list[str],
    jurisdictions: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql, query_params = build_translated_patents_search_query(
        synonyms=synonyms,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=ScalarQueryParameter,
    )
    if sql is None:
        return []

    job_config = build_job_config(
        query_parameters=query_params,
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)
