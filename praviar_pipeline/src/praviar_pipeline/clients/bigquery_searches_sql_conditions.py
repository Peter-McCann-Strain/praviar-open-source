"""Shared condition builders for BigQuery patent search SQL."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.clients.bigquery_helpers import build_scalar_conditions
from praviar_pipeline.clients.bigquery_searches_helpers import build_regex_pattern


def build_cpc_conditions(
    *,
    cpc_codes: list[str],
    code_expression: str,
    scalar_query_parameter_cls,
) -> tuple[list[str], list[Any]]:
    return build_scalar_conditions(
        cpc_codes,
        limit=20,
        param_prefix="cpc_prefix",
        condition_builder=lambda param_name: f"{code_expression} LIKE @{param_name}",
        value_builder=lambda code: f"{code}%",
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_jurisdiction_conditions(
    *,
    jurisdictions: list[str],
    scalar_query_parameter_cls,
) -> tuple[list[str], list[Any]]:
    return build_scalar_conditions(
        jurisdictions,
        limit=15,
        param_prefix="jur",
        condition_builder=lambda param_name: f"p.publication_number LIKE @{param_name}",
        value_builder=lambda jurisdiction: f"{jurisdiction}%",
        scalar_query_parameter_cls=scalar_query_parameter_cls,
    )


def build_keyword_clause(
    *,
    keywords: list[str],
    scalar_query_parameter_cls,
) -> tuple[str, list[Any]]:
    if not keywords:
        return "", []

    keyword_pattern = build_regex_pattern(keywords)
    if not keyword_pattern:
        return "", []

    return (
        """
                AND (
                    EXISTS (SELECT 1 FROM UNNEST(p.abstract_localized) AS a
                            WHERE a.language = 'en'
                            AND REGEXP_CONTAINS(LOWER(a.text), @keyword_pattern))
                    OR EXISTS (SELECT 1 FROM UNNEST(p.claims_localized) AS cl
                               WHERE cl.language = 'en'
                               AND REGEXP_CONTAINS(LOWER(cl.text), @keyword_pattern))
                )
            """,
        [scalar_query_parameter_cls("keyword_pattern", "STRING", keyword_pattern)],
    )
