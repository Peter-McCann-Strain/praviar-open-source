"""Shared SQL builders for BigQuery patent search queries."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    PUBLICATION_SELECT_COLUMNS as _PUBLICATION_SELECT_COLUMNS,
)
from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    PUBLICATION_SELECT_COLUMNS_WITH_CPC as _PUBLICATION_SELECT_COLUMNS_WITH_CPC,
)
from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    TRANSLATED_PUBLICATION_SELECT_COLUMNS as _TRANSLATED_PUBLICATION_SELECT_COLUMNS,
)
from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    build_publication_search_sql as _build_publication_search_sql,
)
from praviar_pipeline.clients.bigquery_searches_sql_query_parts import (
    build_assignee_search_query_sql_parts,
    build_compound_annotations_query_sql_parts,
    build_compound_search_query_sql_parts,
    build_cpc_and_keywords_search_query_sql_parts,
    build_translated_patents_search_query_sql_parts,
)

PUBLICATION_SELECT_COLUMNS = _PUBLICATION_SELECT_COLUMNS
PUBLICATION_SELECT_COLUMNS_WITH_CPC = _PUBLICATION_SELECT_COLUMNS_WITH_CPC
TRANSLATED_PUBLICATION_SELECT_COLUMNS = _TRANSLATED_PUBLICATION_SELECT_COLUMNS
build_publication_search_sql = _build_publication_search_sql


def build_compound_search_query_sql(
    *,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_compound_search_query_sql_parts(
        synonyms=synonyms,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_compound_annotations_query_sql(
    *,
    name: str,
    inchikey: str,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str, list[Any]]:
    return build_compound_annotations_query_sql_parts(
        name=name,
        inchikey=inchikey,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_cpc_and_keywords_search_query_sql(
    *,
    cpc_codes: list[str],
    keywords: list[str],
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_cpc_and_keywords_search_query_sql_parts(
        cpc_codes=cpc_codes,
        keywords=keywords,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_assignee_search_query_sql(
    *,
    assignees: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_assignee_search_query_sql_parts(
        assignees=assignees,
        cpc_codes=cpc_codes,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_translated_patents_search_query_sql(
    *,
    synonyms: list[str],
    jurisdictions: list[str],
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    return build_translated_patents_search_query_sql_parts(
        synonyms=synonyms,
        jurisdictions=jurisdictions,
        max_results=max_results,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
