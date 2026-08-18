"""Compound-focused SQL query-part builders for BigQuery patent search."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_searches_helpers import (
    build_or_clause,
    build_regex_pattern,
)
from praviar_pipeline.clients.bigquery_searches_sql_conditions import (
    build_cpc_conditions,
    build_jurisdiction_conditions,
)
from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    PUBLICATION_SELECT_COLUMNS_WITH_CPC,
    build_publication_search_sql,
)


def build_compound_search_query_sql_parts_impl(
    *,
    synonyms: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    synonym_pattern = build_regex_pattern(synonyms)
    if not synonym_pattern:
        return None, []

    query_params = [
        scalar_query_parameter_cls("synonym_pattern", "STRING", synonym_pattern),
        scalar_query_parameter_cls("max_results", "INT64", max_results),
    ]
    cpc_clause = ""
    if cpc_codes:
        cpc_conditions, cpc_params = build_cpc_conditions(
            cpc_codes=cpc_codes,
            code_expression="c2.code",
            scalar_query_parameter_cls=scalar_query_parameter_cls,
        )
        query_params.extend(cpc_params)
        cpc_clause = build_or_clause(
            cpc_conditions,
            prefix=" AND EXISTS (SELECT 1 FROM UNNEST(p.cpc) AS c2 WHERE ",
            suffix=")",
        )

    jurisdiction_clause = ""
    if jurisdictions:
        jur_conditions, jur_params = build_jurisdiction_conditions(
            jurisdictions=jurisdictions,
            scalar_query_parameter_cls=scalar_query_parameter_cls,
        )
        query_params.extend(jur_params)
        jurisdiction_clause = build_or_clause(jur_conditions, prefix=" AND ")

    sql = build_publication_search_sql(
        select_columns=PUBLICATION_SELECT_COLUMNS_WITH_CPC,
        extra_where_clause=f"""
            AND (
                EXISTS (SELECT 1 FROM UNNEST(p.abstract_localized) AS a
                        WHERE a.language = 'en'
                        AND REGEXP_CONTAINS(LOWER(a.text), @synonym_pattern))
                OR EXISTS (SELECT 1 FROM UNNEST(p.claims_localized) AS cl
                           WHERE cl.language = 'en'
                           AND REGEXP_CONTAINS(LOWER(cl.text), @synonym_pattern))
            )
            {cpc_clause}
            {jurisdiction_clause}
        """.rstrip(),
    )
    return sql, query_params


def build_compound_annotations_query_sql_parts_impl(
    *,
    name: str,
    inchikey: str,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str, list[Any]]:
    sql = """
        SELECT DISTINCT
            publication_number,
            confidence
        FROM
            `patents-public-data.google_patents_research.annotations`
        WHERE
            (LOWER(preferred_name) = @compound_name
             OR inchi_key = @inchikey)
            AND confidence > 0.5
        ORDER BY confidence DESC
        LIMIT @max_results
    """
    query_params = [
        scalar_query_parameter_cls("compound_name", "STRING", name.lower()),
        scalar_query_parameter_cls("inchikey", "STRING", inchikey),
        scalar_query_parameter_cls("max_results", "INT64", max_results),
    ]
    return sql, query_params
