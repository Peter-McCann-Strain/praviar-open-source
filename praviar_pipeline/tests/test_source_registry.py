"""Tests for source capability planning and coverage-aware policy."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.models.report import SourceStatus
from praviar_pipeline.pipeline.search.orchestration import (
    _required_failures_for_policy,
    execute_search_plan,
)
from praviar_pipeline.pipeline.search.plan import build_search_plan
from praviar_pipeline.pipeline.search.source_registry import SOURCE_CAPABILITIES


async def _empty(*args: Any, **kwargs: Any) -> list[Any]:
    return []


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "search_enable_pubchem": True,
        "search_enable_surechembl": True,
        "search_enable_bigquery": True,
        "search_enable_patcid": True,
        "search_allowed_jurisdictions": ["US", "EP", "WO"],
        "kipris_api_key": "",
        "patentscope_username": "",
        "patentscope_password": "",
        "patentsview_api_key": "pv",
        "ops_consumer_key": "",
        "ops_consumer_secret": "",
        "source_failure_policy": "coverage_aware",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _compound() -> SimpleNamespace:
    return SimpleNamespace(name="sofosbuvir", synonyms=[], pubchem_cid=45375808)


def _close_plan_coroutines(plan) -> None:
    for _name, coro in plan:
        coro.close()


def test_lens_is_absent_from_runtime_search_plan() -> None:
    plan = build_search_plan(
        compound=_compound(),
        expanded_queries=SimpleNamespace(),
        has_expansion=False,
        settings=_settings(lens_api_key="configured-but-dormant"),
        search_pubchem_sdq=_empty,
        search_surechembl=_empty,
        search_bigquery=_empty,
        search_bigquery_annotations=_empty,
        search_patcid=_empty,
        search_pubchem_similar=_empty,
        search_bigquery_cpc=_empty,
        search_bigquery_assignee=_empty,
        search_epo_claims=_empty,
        search_kipris=_empty,
        search_patentscope=_empty,
        search_bigquery_translated=_empty,
        search_patentsview=_empty,
    )
    try:
        assert "lens" not in SOURCE_CAPABILITIES
        assert "lens" not in [name for name, _coro in plan]
        assert not [entry for entry in plan.planned_entries if entry.source == "lens"]
    finally:
        _close_plan_coroutines(plan)


def test_missing_patentscope_is_recorded_when_wo_is_in_scope() -> None:
    plan = build_search_plan(
        compound=_compound(),
        expanded_queries=SimpleNamespace(),
        has_expansion=False,
        settings=_settings(search_allowed_jurisdictions=["US", "EP", "WO"]),
        search_pubchem_sdq=_empty,
        search_surechembl=_empty,
        search_bigquery=_empty,
        search_bigquery_annotations=_empty,
        search_patcid=_empty,
        search_pubchem_similar=_empty,
        search_bigquery_cpc=_empty,
        search_bigquery_assignee=_empty,
        search_epo_claims=_empty,
        search_kipris=_empty,
        search_patentscope=_empty,
        search_bigquery_translated=_empty,
        search_patentsview=_empty,
    )
    try:
        assert "patentscope" not in [name for name, _coro in plan]
        patentscope_entries = [
            entry for entry in plan.planned_entries if entry.source == "patentscope"
        ]
        assert len(patentscope_entries) == 1
        assert patentscope_entries[0].status == SourceStatus.NOT_CONFIGURED
    finally:
        _close_plan_coroutines(plan)


def test_patentscope_is_not_requested_without_wo_scope() -> None:
    plan = build_search_plan(
        compound=_compound(),
        expanded_queries=SimpleNamespace(),
        has_expansion=False,
        settings=_settings(search_allowed_jurisdictions=["US", "EP"]),
        search_pubchem_sdq=_empty,
        search_surechembl=_empty,
        search_bigquery=_empty,
        search_bigquery_annotations=_empty,
        search_patcid=_empty,
        search_pubchem_similar=_empty,
        search_bigquery_cpc=_empty,
        search_bigquery_assignee=_empty,
        search_epo_claims=_empty,
        search_kipris=_empty,
        search_patentscope=_empty,
        search_bigquery_translated=_empty,
        search_patentsview=_empty,
    )
    try:
        assert "patentscope" not in [name for name, _coro in plan]
        assert not [entry for entry in plan.planned_entries if entry.source == "patentscope"]
    finally:
        _close_plan_coroutines(plan)


def test_biologic_plan_includes_required_ncbi_sequence_lane() -> None:
    plan = build_search_plan(
        compound=SimpleNamespace(
            name="adalimumab",
            synonyms=[],
            pubchem_cid=None,
            compound_type="biologic",
            protein_subunit_sequences=["ACDEFGHIKLMNPQRSTVWY"],
        ),
        expanded_queries=SimpleNamespace(),
        has_expansion=False,
        settings=_settings(search_enable_ncbi_patent_sequence=True),
        search_pubchem_sdq=_empty,
        search_surechembl=_empty,
        search_bigquery=_empty,
        search_bigquery_annotations=_empty,
        search_patcid=_empty,
        search_pubchem_similar=_empty,
        search_bigquery_cpc=_empty,
        search_bigquery_assignee=_empty,
        search_epo_claims=_empty,
        search_kipris=_empty,
        search_patentscope=_empty,
        search_bigquery_translated=_empty,
        search_patentsview=_empty,
        search_ncbi_patent_sequence=_empty,
    )
    try:
        assert "ncbi_patent_sequence" in [name for name, _coro in plan]
    finally:
        _close_plan_coroutines(plan)


@pytest.mark.asyncio
async def test_coverage_aware_allows_single_source_failure_when_coverage_exists() -> None:
    async def _ok() -> list[dict]:
        return []

    async def _fail() -> list[dict]:
        raise RuntimeError("source down")

    plan = [
        ("pubchem_sdq", _ok()),
        ("patentsview", _ok()),
        ("kipris", _fail()),
    ]
    summary = await execute_search_plan(plan, _run_source_for_test)

    required = _required_failures_for_policy(summary=summary, settings=_settings())

    assert "kipris" in summary.failures
    assert required == {}


@pytest.mark.asyncio
async def test_coverage_aware_fails_when_no_bibliographic_source_succeeds() -> None:
    async def _ok() -> list[dict]:
        return []

    async def _fail() -> list[dict]:
        raise RuntimeError("source down")

    plan = [
        ("pubchem_sdq", _ok()),
        ("bigquery", _fail()),
        ("patentsview", _fail()),
    ]
    summary = await execute_search_plan(plan, _run_source_for_test)

    required = _required_failures_for_policy(summary=summary, settings=_settings())

    assert "coverage:bibliographic_legal" in required
    with pytest.raises(SearchSourceFailedError):
        raise SearchSourceFailedError(required)


@pytest.mark.asyncio
async def test_sequence_coverage_fails_closed_even_under_best_effort_policy() -> None:
    async def _ok() -> list[dict]:
        return []

    async def _fail() -> list[dict]:
        raise RuntimeError("NCBI unavailable")

    summary = await execute_search_plan(
        [
            ("pubchem_sdq", _ok()),
            ("patentsview", _ok()),
            ("ncbi_patent_sequence", _fail()),
        ],
        _run_source_for_test,
    )

    required = _required_failures_for_policy(
        summary=summary,
        settings=_settings(source_failure_policy="best_effort"),
        compound_type="biologic",
    )

    assert "coverage:sequence_identity" in required


async def _run_source_for_test(name: str, coro):
    from praviar_pipeline.pipeline.search.orchestration import run_source

    return await run_source(name, coro)
