from __future__ import annotations

from praviar_pipeline.clients.bigquery_searches_sql_conditions import (
    build_jurisdiction_conditions,
    build_keyword_clause,
)


class _Param:
    def __init__(self, name: str, kind: str, value) -> None:
        self.name = name
        self.kind = kind
        self.value = value


def test_build_jurisdiction_conditions_prefixes_publication_number() -> None:
    conditions, params = build_jurisdiction_conditions(
        jurisdictions=["US", "EP"],
        scalar_query_parameter_cls=_Param,
    )

    assert conditions == [
        "p.publication_number LIKE @jur_0",
        "p.publication_number LIKE @jur_1",
    ]
    assert [param.value for param in params] == ["US%", "EP%"]


def test_build_keyword_clause_returns_empty_when_pattern_is_empty() -> None:
    clause, params = build_keyword_clause(
        keywords=["", "   "],
        scalar_query_parameter_cls=_Param,
    )

    assert clause == ""
    assert params == []
