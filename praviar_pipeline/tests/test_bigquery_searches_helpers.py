from __future__ import annotations

from praviar_pipeline.clients.bigquery_searches_helpers import (
    build_or_clause,
    build_regex_pattern,
)


def test_build_regex_pattern_escapes_and_normalizes() -> None:
    assert build_regex_pattern(["Beta+", "alpha"]) == "(beta\\+|alpha)"


def test_build_regex_pattern_returns_none_for_empty_values() -> None:
    assert build_regex_pattern(["", None, ""]) is None


def test_build_regex_pattern_ignores_whitespace_only_values() -> None:
    assert build_regex_pattern(["  ", "\tAlpha  ", "\n"]) == "(alpha)"


def test_build_or_clause_prefixes_and_wraps_conditions() -> None:
    assert build_or_clause(["a = 1", "b = 2"], prefix=" AND ") == " AND (a = 1 OR b = 2)"


def test_build_or_clause_returns_empty_string_for_no_conditions() -> None:
    assert build_or_clause([]) == ""
