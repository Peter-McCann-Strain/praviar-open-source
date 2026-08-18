from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.search.orchestration import (
    SearchExecutionSummary,
    build_search_contribution_summary,
    emit_search_completion_logs,
    execute_search_coordinator,
    execute_search_plan,
    finalize_search_run,
    maybe_expand_via_citations,
    partition_source_outcomes,
    prepare_search_results,
    run_source,
)


@pytest.mark.asyncio
async def test_execute_search_plan_partitions_success_and_failure() -> None:
    async def _value(result):
        return result

    plan = [
        ("pubchem_sdq", _value([{"publicationnumber": "US100"}])),
        ("bigquery", _value([{"publication_number": "US200"}])),
    ]

    async def fake_run_source(name, coro):
        result = await coro
        if name == "bigquery":
            return name, result, RuntimeError("bigquery down"), 12
        return name, result, None, 7

    summary = await execute_search_plan(plan, fake_run_source)

    assert summary.sdq_results == [{"publicationnumber": "US100"}]
    assert summary.bigquery_rows == []
    assert summary.failures == {"bigquery": "source search failed (RuntimeError)"}
    assert summary.source_timings == {"pubchem_sdq": 7, "bigquery": 12}
    assert summary.health.entries[0].source == "pubchem_sdq"
    assert summary.health.entries[1].source == "bigquery"
    assert summary.health.failed_sources == ["bigquery"]


@pytest.mark.asyncio
async def test_run_source_converts_timeout_to_structured_failure() -> None:
    async def _slow_source():
        await asyncio.sleep(1)
        return [{"publicationnumber": "US100"}]

    name, result, error, elapsed_ms = await run_source(
        "pubchem_sdq",
        _slow_source(),
        timeout_s=0.01,
    )

    assert name == "pubchem_sdq"
    assert result is None
    assert isinstance(error, TimeoutError)
    assert str(error) == "source exceeded timeout_s=0.01"
    assert elapsed_ms >= 0


@pytest.mark.asyncio
async def test_finalize_search_run_preserves_real_ranking_signal_provenance() -> None:
    hit = PatentHit(
        patent_id="US100A1",
        sources=[PatentSource.PUBCHEM],
        ranking_composite_score=0.71,
        ranking_bm25_score=4.2,
        ranking_bm25_normalized_score=0.84,
        ranking_embedding_score=-0.1,
        ranking_embedding_normalized_score=0.25,
        ranking_final_blend_score=0.63,
    )

    async def _enrich(_hits):
        return MagicMock()

    _counts, funnel = await finalize_search_run(
        [hit],
        collect_audit=True,
        enrich_hits_fn=_enrich,
    )

    assert funnel[0].composite_score == 0.71
    assert funnel[0].bm25_score == 4.2
    assert funnel[0].bm25_normalized_score == 0.84
    assert funnel[0].embedding_score == -0.1
    assert funnel[0].embedding_normalized_score == 0.25
    assert funnel[0].final_blend_score == 0.63


@pytest.mark.asyncio
async def test_search_failure_outputs_and_logs_never_expose_request_credentials() -> None:
    sentinel = "search-orchestration-api-key-sentinel"
    request = httpx.Request("GET", f"https://provider.test/search?api_key={sentinel}")
    response = httpx.Response(503, request=request, text=f"echoed={sentinel}")
    provider_error = httpx.HTTPStatusError(
        "provider unavailable",
        request=request,
        response=response,
    )

    async def _failing_source():
        raise provider_error

    recording_logger = MagicMock()
    with patch(
        "praviar_pipeline.pipeline.search.orchestration.logger",
        recording_logger,
    ):
        outcome = await run_source("openalex", _failing_source())
        summary = partition_source_outcomes([outcome])

    serialized = summary.health.model_dump_json() + repr(summary.failures)
    assert sentinel not in serialized
    assert "HTTPStatusError" in serialized
    for call in recording_logger.method_calls:
        assert sentinel not in repr((call.args, call.kwargs))


def test_build_search_contribution_summary_combines_source_and_final_counts(
    sample_patent_hits,
) -> None:
    summary = build_search_contribution_summary(
        sdq_results=[{"publicationnumber": "US7851188B2"}],
        source_map={
            "US7851188B2": {PatentSource.PUBCHEM, PatentSource.BIGQUERY},
            "US6265190B1": {PatentSource.BIGQUERY},
        },
        source_timings={"pubchem_sdq": 7, "bigquery": 12},
        hits=sample_patent_hits,
        normalize_patent_id=lambda patent_id: patent_id,
    )

    assert summary.total_unique_patents == 2
    assert summary.sdq_total == 1
    assert summary.source_metrics["pubchem_sdq"]["total"] == 1
    assert summary.source_metrics["bigquery"]["total"] == 2
    assert summary.final_source_counts["bigquery"] == 2
    assert summary.final_source_counts["pubchem"] == 1
    assert summary.final_sole_source["bigquery"] == 1
    assert summary.final_sole_source["surechembl"] == 1


def test_prepare_search_results_passes_multi_source_ids_and_builds_hits() -> None:
    summary = SearchExecutionSummary(
        sdq_results=[{"publicationnumber": "US100"}],
        surechembl_results=[("US100", PatentSource.SURECHEMBL)],
        source_timings={"pubchem_sdq": 5},
    )
    captured: dict[str, object] = {}
    fake_hit = type("Hit", (), {"patent_id": "US100", "sources": [PatentSource.PUBCHEM]})()
    settings = type(
        "Settings",
        (),
        {"search_max_ranked_results": 25, "collect_audit_trail": True},
    )()

    def fake_rank_patents(sdq_results, compound, **kwargs):
        captured["multi_source_ids"] = kwargs["multi_source_ids"]
        return [{"publicationnumber": "US100"}]

    prepared = prepare_search_results(
        summary=summary,
        compound=object(),
        settings=settings,
        build_source_map_fn=lambda **kwargs: {
            "US100": {PatentSource.PUBCHEM, PatentSource.SURECHEMBL}
        },
        rank_patents_fn=fake_rank_patents,
        assemble_hits_fn=lambda **kwargs: ([fake_hit], {"US100"}),
        build_search_contribution_summary_fn=lambda **kwargs: build_search_contribution_summary(
            sdq_results=kwargs["sdq_results"],
            source_map=kwargs["source_map"],
            source_timings=kwargs["source_timings"],
            hits=kwargs["hits"],
            normalize_patent_id=lambda patent_id: patent_id,
        ),
        normalize_patent_id=lambda patent_id: patent_id,
    )

    assert captured["multi_source_ids"] == {"US100"}
    assert prepared.hits == [fake_hit]
    assert prepared.seen_norm_ids == {"US100"}
    assert prepared.ranked_sdq == [{"publicationnumber": "US100"}]


@pytest.mark.asyncio
async def test_maybe_expand_via_citations_skips_when_disabled() -> None:
    summary = SearchExecutionSummary(cpc_search_rows=[{"publication_number": "US100"}])
    called = False

    async def fake_expand(*args, **kwargs):
        nonlocal called
        called = True

    await maybe_expand_via_citations(
        enabled=False,
        summary=summary,
        hits=[],
        seen_norm_ids=set(),
        source_map={},
        settings=object(),
        expand_via_citations_fn=fake_expand,
    )

    assert called is False


@pytest.mark.asyncio
async def test_maybe_expand_via_citations_passes_expected_rows() -> None:
    summary = SearchExecutionSummary(
        cpc_search_rows=[{"publication_number": "US100"}],
        assignee_search_rows=[{"publication_number": "US200"}],
    )
    captured = {}

    async def fake_expand(
        hits,
        seen_norm_ids,
        source_map,
        *,
        supplementary_rows,
        settings,
    ):
        captured["supplementary_rows"] = supplementary_rows

    await maybe_expand_via_citations(
        enabled=True,
        summary=summary,
        hits=[],
        seen_norm_ids=set(),
        source_map={},
        settings=object(),
        expand_via_citations_fn=fake_expand,
    )

    assert captured["supplementary_rows"] == [
        [{"publication_number": "US100"}],
        [{"publication_number": "US200"}],
    ]


@pytest.mark.asyncio
async def test_finalize_search_run_enriches_hits_and_builds_funnel(sample_patent_hits) -> None:
    async def fake_enrich_hits(hits):
        return type(
            "Counts",
            (),
            {
                "legal": 1,
                "families": 2,
                "patent_term": 3,
                "application_data": 4,
                "epo_register": 5,
                "ptab": 6,
                "orange_book": 7,
            },
        )()

    enrichment_counts, search_funnel = await finalize_search_run(
        sample_patent_hits,
        collect_audit=True,
        enrich_hits_fn=fake_enrich_hits,
    )

    assert enrichment_counts.legal == 1
    assert len(search_funnel) == len({hit.patent_id for hit in sample_patent_hits})


def test_emit_search_completion_logs_uses_summary_and_contribution(sample_patent_hits) -> None:
    summary = SearchExecutionSummary(
        sdq_results=[{"publicationnumber": "US7851188B2"}],
        surechembl_results=[("US6265190B1", PatentSource.SURECHEMBL)],
        source_timings={"pubchem_sdq": 7},
        health=type("Health", (), {"model_dump": lambda self: {"entries": []}})(),
    )
    contribution_summary = build_search_contribution_summary(
        sdq_results=summary.sdq_results,
        source_map={
            "US7851188B2": {PatentSource.PUBCHEM, PatentSource.BIGQUERY},
            "US6265190B1": {PatentSource.SURECHEMBL},
        },
        source_timings=summary.source_timings,
        hits=sample_patent_hits,
        normalize_patent_id=lambda patent_id: patent_id,
    )
    enrichment_counts = type(
        "Counts",
        (),
        {
            "legal": 1,
            "families": 2,
            "patent_term": 3,
            "application_data": 4,
            "epo_register": 5,
            "ptab": 6,
            "orange_book": 7,
        },
    )()

    emit_search_completion_logs(
        compound_name="aspirin",
        hits=sample_patent_hits,
        summary=summary,
        contribution_summary=contribution_summary,
        enrichment_counts=enrichment_counts,
        ranked_sdq_count=1,
    )


@pytest.mark.asyncio
async def test_execute_search_coordinator_runs_preparation_enrichment_and_logging() -> None:
    summary = SearchExecutionSummary(
        sdq_results=[{"publicationnumber": "US100"}],
        bigquery_rows=[{"publication_number": "US200"}],
        health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_sdq",
                    status=SourceStatus.OK,
                    patent_count=1,
                ),
                SourceHealthEntry(
                    source="bigquery",
                    status=SourceStatus.OK,
                    patent_count=1,
                ),
            ]
        ),
        source_timings={"pubchem_sdq": 5},
    )
    compound = type("Compound", (), {"name": "aspirin"})()
    settings = type(
        "Settings",
        (),
        {
            "collect_audit_trail": True,
            "search_citation_traversal_enabled": False,
        },
    )()
    hit = type("Hit", (), {"patent_id": "US100"})()
    contribution_summary = type(
        "ContributionSummary",
        (),
        {
            "total_unique_patents": 1,
            "sdq_total": 1,
            "source_metrics": {"pubchem_sdq": {"total": 1}},
        },
    )()
    prepared = type(
        "Prepared",
        (),
        {
            "hits": [hit],
            "seen_norm_ids": {"US100"},
            "source_map": {"US100": {PatentSource.PUBCHEM}},
            "contribution_summary": contribution_summary,
            "ranked_sdq": [{"publicationnumber": "US100"}],
        },
    )()
    enrichment_counts = type(
        "Counts",
        (),
        {
            "legal": 1,
            "families": 2,
            "patent_term": 3,
            "application_data": 4,
            "epo_register": 5,
            "ptab": 6,
            "orange_book": 7,
        },
    )()
    emit_logs_calls = []

    async def fake_execute_search_plan(plan, run_source):
        return summary

    async def fake_maybe_expand(**kwargs):
        return None

    async def fake_finalize(hits, *, collect_audit, enrich_hits_fn):
        return enrichment_counts, ["audit-entry"]

    hits, health, search_funnel = await execute_search_coordinator(
        compound=compound,
        expanded_queries=object(),
        has_expansion=False,
        settings=settings,
        build_search_plan_fn=lambda **kwargs: [("pubchem_sdq", object())],
        execute_search_plan_fn=fake_execute_search_plan,
        run_source_fn=object(),
        prepare_search_results_fn=lambda **kwargs: prepared,
        build_source_map_fn=object(),
        rank_patents_fn=object(),
        assemble_hits_fn=object(),
        build_search_contribution_summary_fn=object(),
        normalize_patent_id=lambda patent_id: patent_id,
        maybe_expand_via_citations_fn=fake_maybe_expand,
        expand_via_citations_fn=object(),
        finalize_search_run_fn=fake_finalize,
        enrich_hits_fn=object(),
        emit_search_completion_logs_fn=lambda **kwargs: emit_logs_calls.append(kwargs),
    )

    assert hits == [hit]
    assert health is summary.health
    assert search_funnel == ["audit-entry"]
    assert len(emit_logs_calls) == 1
    assert emit_logs_calls[0]["ranked_sdq_count"] == 1
