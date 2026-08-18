"""Query-construction helpers for BigQuery patent search SQL."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_searches_sql_compound_parts import (
    build_compound_annotations_query_sql_parts_impl,
    build_compound_search_query_sql_parts_impl,
)
from praviar_pipeline.clients.bigquery_searches_sql_publication_parts import (
    build_assignee_search_query_sql_parts_impl,
    build_cpc_and_keywords_search_query_sql_parts_impl,
    build_translated_patents_search_query_sql_parts_impl,
)


def build_compound_search_query_sql_parts(
    *,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_compound_search_query_sql_parts_impl(
        synonyms=synonyms,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_compound_annotations_query_sql_parts(
    *,
    name: str,
    inchikey: str,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str, list[Any]]:
    return build_compound_annotations_query_sql_parts_impl(
        name=name,
        inchikey=inchikey,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_cpc_and_keywords_search_query_sql_parts(
    *,
    cpc_codes: list[str],
    keywords: list[str],
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_cpc_and_keywords_search_query_sql_parts_impl(
        cpc_codes=cpc_codes,
        keywords=keywords,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_assignee_search_query_sql_parts(
    *,
    assignees: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_assignee_search_query_sql_parts_impl(
        assignees=assignees,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_translated_patents_search_query_sql_parts(
    *,
    synonyms: list[str],
    jurisdictions: list[str],
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_translated_patents_search_query_sql_parts_impl(
        synonyms=synonyms,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
