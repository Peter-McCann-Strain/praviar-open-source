from __future__ import annotations

from praviar_pipeline.clients.bigquery_searches_sql import (
    build_assignee_search_query,
    build_compound_annotations_query,
    build_compound_search_query,
    build_cpc_and_keywords_search_query,
    build_translated_patents_search_query,
)
from praviar_pipeline.clients.bigquery_searches_sql_builders import (
    PUBLICATION_SELECT_COLUMNS,
    build_compound_search_query_sql,
    build_publication_search_sql,
)


class _Param:
    def __init__(self, name: str, kind: str, value) -> None:
        self.name = name
        self.kind = kind
        self.value = value


def _assert_balanced_parentheses(sql: str) -> None:
    assert sql.count("(") == sql.count(")")


def test_build_publication_search_sql_wraps_columns_and_filters() -> None:
    sql = build_publication_search_sql(
        select_columns=PUBLICATION_SELECT_COLUMNS,
        extra_where_clause="AND p.publication_number LIKE @jur_0",
    )

    assert "`patents-public-data.patents.publications` p" in sql
    assert "p.title_localized" in sql
    assert "AND p.publication_number LIKE @jur_0" in sql
    assert "LIMIT @max_results" in sql


def test_build_compound_search_query_sql_uses_shared_select_columns() -> None:
    sql, params = build_compound_search_query_sql(
        synonyms=["Alpha"],
        cpc_codes=["C07"],
        jurisdictions=["US"],
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is not None
    assert PUBLICATION_SELECT_COLUMNS.splitlines()[0].strip() in sql
    assert "c2.code LIKE @cpc_prefix_0" in sql
    assert "REGEXP_CONTAINS(LOWER(a.text), @synonym_pattern)" in sql
    assert [param.name for param in params] == [
        "synonym_pattern",
        "max_results",
        "cpc_prefix_0",
        "jur_0",
    ]
    _assert_balanced_parentheses(sql)


def test_build_compound_search_query_includes_optional_clauses() -> None:
    sql, params = build_compound_search_query(
        synonyms=["Alpha", "Beta+"],
        cpc_codes=["C07", "A01"],
        jurisdictions=["US", "EP"],
        max_results=25,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is not None
    assert "REGEXP_CONTAINS(LOWER(a.text), @synonym_pattern)" in sql
    assert "c2.code LIKE @cpc_prefix_0" in sql
    assert "p.publication_number LIKE @jur_0" in sql
    assert [param.name for param in params] == [
        "synonym_pattern",
        "max_results",
        "cpc_prefix_0",
        "cpc_prefix_1",
        "jur_0",
        "jur_1",
    ]
    assert params[0].value == "(alpha|beta\\+)"
    _assert_balanced_parentheses(sql)


def test_build_compound_annotations_query_normalizes_name() -> None:
    sql, params = build_compound_annotations_query(
        name="Amber Acid",
        inchikey="ABC",
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert "google_patents_research.annotations" in sql
    assert [param.name for param in params] == [
        "compound_name",
        "inchikey",
        "max_results",
    ]
    assert params[0].value == "amber acid"


def test_build_cpc_and_keywords_search_query_requires_cpc_codes() -> None:
    sql, params = build_cpc_and_keywords_search_query(
        cpc_codes=[],
        keywords=["kinase"],
        jurisdictions=None,
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is None
    assert params == []


def test_build_cpc_and_keywords_search_query_includes_keyword_clause() -> None:
    sql, params = build_cpc_and_keywords_search_query(
        cpc_codes=["C07"],
        keywords=["kinase"],
        jurisdictions=["US"],
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is not None
    assert "keyword_pattern" in sql
    assert "c.code LIKE @cpc_prefix_0" in sql
    assert "p.publication_number LIKE @jur_0" in sql
    assert [param.name for param in params] == [
        "max_results",
        "cpc_prefix_0",
        "keyword_pattern",
        "jur_0",
    ]
    _assert_balanced_parentheses(sql)


def test_build_assignee_search_query_requires_assignees() -> None:
    sql, params = build_assignee_search_query(
        assignees=[],
        cpc_codes=["C07"],
        jurisdictions=["US"],
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is None
    assert params == []


def test_build_assignee_search_query_balances_exists_clauses() -> None:
    sql, params = build_assignee_search_query(
        assignees=["Acme"],
        cpc_codes=["C07"],
        jurisdictions=["US"],
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is not None
    assert "a.name" in sql
    assert "c.code LIKE @cpc_prefix_0" in sql
    assert "p.publication_number LIKE @jur_0" in sql
    assert [param.name for param in params] == [
        "max_results",
        "assignee_0",
        "cpc_prefix_0",
        "jur_0",
    ]
    _assert_balanced_parentheses(sql)


def test_build_translated_patents_search_query_requires_jurisdictions() -> None:
    sql, params = build_translated_patents_search_query(
        synonyms=["alpha"],
        jurisdictions=[],
        max_results=10,
        scalar_query_parameter_cls=_Param,
    )

    assert sql is None
    assert params == []
