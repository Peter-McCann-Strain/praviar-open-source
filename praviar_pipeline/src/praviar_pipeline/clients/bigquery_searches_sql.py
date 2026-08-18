"""Public SQL builders for BigQuery patent search queries."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_searches_sql_builders import (
    build_assignee_search_query_sql,
    build_compound_annotations_query_sql,
    build_compound_search_query_sql,
    build_cpc_and_keywords_search_query_sql,
    build_translated_patents_search_query_sql,
)


def build_compound_search_query(
    *,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_compound_search_query_sql(
        synonyms=synonyms,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_compound_annotations_query(
    *,
    name: str,
    inchikey: str,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str, list[Any]]:
    return build_compound_annotations_query_sql(
        name=name,
        inchikey=inchikey,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_cpc_and_keywords_search_query(
    *,
    cpc_codes: list[str],
    keywords: list[str],
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_cpc_and_keywords_search_query_sql(
        cpc_codes=cpc_codes,
        keywords=keywords,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_assignee_search_query(
    *,
    assignees: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_assignee_search_query_sql(
        assignees=assignees,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_translated_patents_search_query(
    *,
    synonyms: list[str],
    jurisdictions: list[str],
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_translated_patents_search_query_sql(
        synonyms=synonyms,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
