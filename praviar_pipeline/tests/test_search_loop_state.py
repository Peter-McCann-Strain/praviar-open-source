"""Tests for search-loop state and delegation helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.models.report import EvidenceCollectionDirective, EvidenceDirectivePriority
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.search_loop import CoverageAssessment, SearchIterationLog
from praviar_pipeline.pipeline.search_loop import (
    SearchLoopState,
    apply_coverage_assessment,
    record_search_results,
    record_triage_results,
)


def test_record_search_results_only_keeps_new_hits() -> None:
    state = SearchLoopState()
    source_health = SimpleNamespace(entries=[])
    funnel = [SimpleNamespace(source="pubchem")]
    first_hit = SimpleNamespace(patent_id="US123")
    duplicate_hit = SimpleNamespace(patent_id="US123")
    second_hit = SimpleNamespace(patent_id="US456")

    truly_new = record_search_results(
        state,
        new_hits=[first_hit, duplicate_hit, second_hit],
        source_health=source_health,
        search_funnel=funnel,
    )

    assert [hit.patent_id for hit in truly_new] == ["US123", "US456"]
    assert [hit.patent_id for hit in state.all_patent_hits] == ["US123", "US456"]
    assert state.last_source_health is source_health
    assert state.all_search_funnel == funnel


def test_record_triage_results_accumulates_counts() -> None:
    state = SearchLoopState()
    triage_relevant = [SimpleNamespace(patent_id="US123")]
    triage_all = [*triage_relevant, SimpleNamespace(patent_id="US456")]

    record_triage_results(
        state,
        triage_relevant=triage_relevant,
        triage_all=triage_all,
        input_tokens=10,
        output_tokens=6,
        failed_count=1,
    )

    assert state.all_triage_relevant == triage_relevant
    assert state.all_triage_complete == triage_all
    assert state.total_triage_in == 10
    assert state.total_triage_out == 6
    assert state.total_triage_failed == 1


def test_apply_coverage_assessment_stops_when_adequate() -> None:
    queries = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    state = SearchLoopState(current_queries=queries, accumulated_queries=queries)
    iter_log = SearchIterationLog(iteration_number=1)
    assessment = CoverageAssessment(coverage_adequate=True, confidence=0.9)

    should_stop = apply_coverage_assessment(
        state,
        iter_log=iter_log,
        assessment=assessment,
        input_tokens=7,
        output_tokens=3,
        coverage_threshold=0.7,
        merge_queries_fn=lambda base, new: new,
    )

    assert should_stop is True
    assert state.iteration_logs == [iter_log]
    assert iter_log.assessment is assessment
    assert iter_log.input_tokens == 7
    assert iter_log.output_tokens == 3
    assert state.termination_reason == "coverage_adequate"


def test_apply_coverage_assessment_updates_queries_when_more_search_needed() -> None:
    current = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    accumulated = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    suggested = ExpandedSearchQueries(patent_synonyms=["asa"], cpc_codes=["A61K"])
    state = SearchLoopState(current_queries=current, accumulated_queries=accumulated)
    iter_log = SearchIterationLog(iteration_number=1)
    assessment = CoverageAssessment(
        coverage_adequate=False,
        confidence=0.2,
        suggested_queries=suggested,
    )

    should_stop = apply_coverage_assessment(
        state,
        iter_log=iter_log,
        assessment=assessment,
        input_tokens=5,
        output_tokens=2,
        coverage_threshold=0.7,
        merge_queries_fn=lambda base, new: ExpandedSearchQueries(
            patent_synonyms=base.patent_synonyms + new.patent_synonyms,
            cpc_codes=base.cpc_codes + new.cpc_codes,
        ),
    )

    assert should_stop is False
    assert state.current_queries is suggested
    assert state.accumulated_queries.patent_synonyms == ["aspirin", "asa"]
    assert state.accumulated_queries.cpc_codes == ["A61K"]
    assert state.iteration_logs == []


def test_apply_coverage_assessment_does_not_stop_on_confident_but_inadequate_result() -> None:
    current = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    suggested = ExpandedSearchQueries(patent_synonyms=["asa"])
    state = SearchLoopState(current_queries=current, accumulated_queries=current)
    iter_log = SearchIterationLog(iteration_number=1)
    assessment = CoverageAssessment(
        coverage_adequate=False,
        confidence=0.95,
        suggested_queries=suggested,
    )

    should_stop = apply_coverage_assessment(
        state,
        iter_log=iter_log,
        assessment=assessment,
        input_tokens=4,
        output_tokens=2,
        coverage_threshold=0.7,
        merge_queries_fn=lambda base, new: ExpandedSearchQueries(
            patent_synonyms=base.patent_synonyms + new.patent_synonyms,
        ),
    )

    assert should_stop is False
    assert state.current_queries is suggested
    assert state.accumulated_queries.patent_synonyms == ["aspirin", "asa"]


def test_apply_coverage_assessment_uses_directive_fallback_queries() -> None:
    current = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    state = SearchLoopState(current_queries=current, accumulated_queries=current)
    iter_log = SearchIterationLog(iteration_number=1)
    directive = EvidenceCollectionDirective(
        directive_id="collect_authoritative_records:US123",
        directive_type="collect_authoritative_records",
        priority=EvidenceDirectivePriority.CRITICAL,
        target_patent_ids=["US123"],
        recommended_adapters=["patentsview"],
        summary="Collect authoritative records.",
        rationale="Needed before clear.",
    )
    assessment = CoverageAssessment(
        coverage_adequate=False,
        confidence=0.5,
        evidence_collection_directives=[directive],
    )

    should_stop = apply_coverage_assessment(
        state,
        iter_log=iter_log,
        assessment=assessment,
        input_tokens=3,
        output_tokens=1,
        coverage_threshold=0.7,
        merge_queries_fn=lambda base, new: ExpandedSearchQueries(
            patent_synonyms=base.patent_synonyms + new.patent_synonyms,
            cpc_codes=base.cpc_codes + new.cpc_codes,
            key_assignees=base.key_assignees + new.key_assignees,
        ),
        patent_hits=[
            SimpleNamespace(
                patent_id="US123",
                assignees=["Fallback Pharma"],
                cpc_codes=["C07D401/12"],
            )
        ],
    )

    assert should_stop is False
    assert state.current_queries.key_assignees == ["Fallback Pharma"]
    assert state.current_queries.cpc_codes == ["C07D401/12"]
    assert state.pending_collection_directives == [directive]
    assert state.termination_reason == ""


def test_apply_coverage_assessment_stops_with_record_collection_required_when_no_queries() -> None:
    current = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    state = SearchLoopState(current_queries=current, accumulated_queries=current)
    iter_log = SearchIterationLog(iteration_number=1)
    directive = EvidenceCollectionDirective(
        directive_id="collect_us_file_wrapper_dossier:US123",
        directive_type="collect_us_file_wrapper_dossier",
        priority=EvidenceDirectivePriority.CRITICAL,
        target_patent_ids=["US123"],
        recommended_adapters=["uspto_odp"],
        summary="Collect dossier history.",
        rationale="Needed before clear.",
    )
    assessment = CoverageAssessment(
        coverage_adequate=False,
        confidence=0.4,
        evidence_collection_directives=[directive],
    )

    should_stop = apply_coverage_assessment(
        state,
        iter_log=iter_log,
        assessment=assessment,
        input_tokens=3,
        output_tokens=1,
        coverage_threshold=0.7,
        merge_queries_fn=lambda base, new: new,
        patent_hits=[SimpleNamespace(patent_id="US123", assignees=[], cpc_codes=[])],
    )

    assert should_stop is True
    assert state.iteration_logs == [iter_log]
    assert state.pending_collection_directives == [directive]
    assert state.termination_reason == "record_collection_required"


@pytest.mark.asyncio
async def test_assess_coverage_wrapper_uses_configured_model() -> None:
    from praviar_pipeline.pipeline.search_loop import _assess_coverage

    compound = SimpleNamespace(name="aspirin")
    patent_hits = [SimpleNamespace(patent_id="US123")]
    triage_results = [SimpleNamespace(patent_id="US123")]
    queries = ExpandedSearchQueries(patent_synonyms=["aspirin"])
    source_health = SimpleNamespace(entries=[])
    assessment = CoverageAssessment(coverage_adequate=True, confidence=0.8)
    collector_runs = []

    with (
        patch("praviar_pipeline.pipeline.search_loop.get_settings") as mock_settings,
        patch(
            "praviar_pipeline.pipeline.search_loop.execute_live_evidence_collectors",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    source_health=source_health,
                    prosecution_cache={"US123": {"office_actions": "summary"}},
                    collector_runs=[{"definition": {"collector_name": "uspto_odp"}}],
                )
            ),
        ) as mock_collectors,
        patch(
            "praviar_pipeline.pipeline.search_loop.assess_search_coverage",
            new=AsyncMock(return_value=(assessment, 11, 7)),
        ) as mock_assess,
    ):
        mock_settings.return_value = SimpleNamespace(claude_triage_model="claude-test")

        result = await _assess_coverage(
            compound,
            patent_hits,
            triage_results,
            triage_results,
            queries,
            source_health,
            2,
            {},
            collector_runs,
        )

    assert result == (assessment, 11, 7)
    assert collector_runs == [{"definition": {"collector_name": "uspto_odp"}}]
    mock_collectors.assert_awaited_once()
    assert mock_assess.await_args.kwargs["prosecution_cache"] == {
        "US123": {"office_actions": "summary"}
    }
    assert mock_assess.await_args.kwargs["existing_collector_runs"] == [
        {"definition": {"collector_name": "uspto_odp"}}
    ]
    mock_assess.assert_awaited_once_with(
        compound,
        patent_hits,
        triage_results,
        triage_results,
        queries,
        source_health,
        2,
        prosecution_cache={"US123": {"office_actions": "summary"}},
        existing_collector_runs=[{"definition": {"collector_name": "uspto_odp"}}],
        model_name="claude-test",
    )
