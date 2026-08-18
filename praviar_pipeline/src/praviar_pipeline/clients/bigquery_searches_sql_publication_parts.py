"""Publication-search SQL query-part builders for BigQuery patent search."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_helpers import build_scalar_conditions
from praviar_pipeline.clients.bigquery_searches_helpers import (
    build_or_clause,
    build_regex_pattern,
)
from praviar_pipeline.clients.bigquery_searches_sql_conditions import (
    build_cpc_conditions,
    build_jurisdiction_conditions,
    build_keyword_clause,
)
from praviar_pipeline.clients.bigquery_searches_sql_fragments import (
    PUBLICATION_SELECT_COLUMNS,
    PUBLICATION_SELECT_COLUMNS_WITH_CPC,
    TRANSLATED_PUBLICATION_SELECT_COLUMNS,
    build_publication_search_sql,
)


def build_cpc_and_keywords_search_query_sql_parts_impl(
    *,
    cpc_codes: list[str],
    keywords: list[str],
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    if not cpc_codes:
        return None, []

    query_params = [scalar_query_parameter_cls("max_results", "INT64", max_results)]
    cpc_conditions, cpc_params = build_cpc_conditions(
        cpc_codes=cpc_codes,
        code_expression="c.code",
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
    query_params.extend(cpc_params)

    keyword_clause, keyword_params = build_keyword_clause(
        keywords=keywords,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
    if keyword_params:
        query_params.extend(keyword_params)

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
            {
            build_or_clause(
                cpc_conditions,
                prefix=" AND EXISTS (SELECT 1 FROM UNNEST(p.cpc) AS c WHERE ",
                suffix=")",
            )
        }
            {keyword_clause}
            {jurisdiction_clause}
        """.rstrip(),
    )
    return sql, query_params


def build_assignee_search_query_sql_parts_impl(
    *,
    assignees: list[str],
    cpc_codes: list[str] | None,
    jurisdictions: list[str] | None,
    max_results: int,
    scalar_query_parameter_cls,
) -> tuple[str | None, list[Any]]:
    if not assignees:
        return None, []

    query_params = [scalar_query_parameter_cls("max_results", "INT64", max_results)]
    assignee_conditions, assignee_params = build_scalar_conditions(
        assignees,
        limit=10,
        param_prefix="assignee",
        condition_builder=lambda param_name: f"LOWER(a.name) LIKE @{param_name}",
        value_builder=lambda assignee: f"%{assignee.lower()}%",
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
    query_params.extend(assignee_params)

    cpc_clause = ""
    if cpc_codes:
        cpc_conditions, cpc_params = build_cpc_conditions(
            cpc_codes=cpc_codes,
            code_expression="c.code",
            scalar_query_parameter_cls=scalar_query_parameter_cls,
        )
        query_params.extend(cpc_params)
        cpc_clause = build_or_clause(
            cpc_conditions,
            prefix=" AND EXISTS (SELECT 1 FROM UNNEST(p.cpc) AS c WHERE ",
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
        select_columns=PUBLICATION_SELECT_COLUMNS,
        extra_where_clause=f"""
            {
            build_or_clause(
                assignee_conditions,
                prefix=(" AND EXISTS (SELECT 1 FROM UNNEST(p.assignee_harmonized) AS a WHERE "),
                suffix=")",
            )
        }
            {cpc_clause}
            {jurisdiction_clause}
        """.rstrip(),
    )
    return sql, query_params


def build_translated_patents_search_query_sql_parts_impl(
    *,
    synonyms: list[str],
    jurisdictions: list[str],
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
    jurisdiction_conditions, jurisdiction_params = build_jurisdiction_conditions(
        jurisdictions=jurisdictions,
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )
    query_params.extend(jurisdiction_params)

    if not jurisdiction_conditions:
        return None, []

    sql = f"""
        SELECT
            {TRANSLATED_PUBLICATION_SELECT_COLUMNS}
        FROM
            `patents-public-data.patents.publications` p
        WHERE
            {build_or_clause(jurisdiction_conditions)}
            AND (
                EXISTS (SELECT 1 FROM UNNEST(p.abstract_localized) AS a
                        WHERE REGEXP_CONTAINS(LOWER(a.text), @synonym_pattern))
                OR EXISTS (SELECT 1 FROM UNNEST(p.title_localized) AS t
                           WHERE REGEXP_CONTAINS(LOWER(t.text), @synonym_pattern))
            )
        ORDER BY p.grant_date DESC
        LIMIT @max_results
    """
    return sql, query_params
