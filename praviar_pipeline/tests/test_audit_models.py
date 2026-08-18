"""Tests for audit trail Pydantic models — SearchFunnelEntry, TriageAuditEntry,
AnalysisAuditEntry, StepTiming, PipelineAuditTrail.
"""

from __future__ import annotations

from datetime import UTC, datetime

from praviar_pipeline.models import (
    AnalysisAuditEntry,
    PipelineAuditTrail,
    SearchFunnelEntry,
    StepTiming,
    TriageAuditEntry,
)

# ---------------------------------------------------------------------------
# SearchFunnelEntry
# ---------------------------------------------------------------------------


class TestSearchFunnelEntry:
    def test_minimal_construction(self):
        entry = SearchFunnelEntry(patent_id="US7851188B2")
        assert entry.patent_id == "US7851188B2"

    def test_defaults(self):
        entry = SearchFunnelEntry(patent_id="US123")
        assert entry.sources_found_in == []
        assert entry.passed_hard_filter is True
        assert entry.filter_reason == ""
        assert entry.composite_score is None
        assert entry.bm25_score is None
        assert entry.final_blend_score is None
        assert entry.final_rank is None
        assert entry.included_in_triage is False

    def test_full_construction(self):
        entry = SearchFunnelEntry(
            patent_id="US7851188B2",
            sources_found_in=["pubchem", "bigquery"],
            passed_hard_filter=True,
            composite_score=0.85,
            bm25_score=0.72,
            final_blend_score=0.80,
            final_rank=1,
            included_in_triage=True,
        )
        assert entry.composite_score == 0.85
        assert entry.final_rank == 1
        assert entry.included_in_triage is True

    def test_filtered_out_entry(self):
        entry = SearchFunnelEntry(
            patent_id="JP2020123456A",
            sources_found_in=["surechembl"],
            passed_hard_filter=False,
            filter_reason="non-US",
        )
        assert entry.passed_hard_filter is False
        assert entry.filter_reason == "non-US"

    def test_serialization_roundtrip(self):
        entry = SearchFunnelEntry(
            patent_id="US100",
            sources_found_in=["pubchem"],
            composite_score=0.5,
        )
        data = entry.model_dump(mode="json")
        restored = SearchFunnelEntry.model_validate(data)
        assert restored.patent_id == entry.patent_id
        assert restored.composite_score == entry.composite_score


# ---------------------------------------------------------------------------
# TriageAuditEntry
# ---------------------------------------------------------------------------


class TestTriageAuditEntry:
    def test_construction(self):
        entry = TriageAuditEntry(
            patent_id="US7851188B2",
            relevance="relevant",
            reason="Directly covers succinic acid",
            confidence=0.95,
            passed_triage=True,
        )
        assert entry.patent_id == "US7851188B2"
        assert entry.relevance == "relevant"
        assert entry.passed_triage is True

    def test_defaults(self):
        entry = TriageAuditEntry(
            patent_id="US123",
            relevance="not_relevant",
            reason="Unrelated",
        )
        assert entry.confidence == 0.0
        assert entry.passed_triage is False

    def test_serialization_roundtrip(self):
        entry = TriageAuditEntry(
            patent_id="US456",
            relevance="possibly_relevant",
            reason="May be relevant",
            confidence=0.6,
        )
        data = entry.model_dump(mode="json")
        restored = TriageAuditEntry.model_validate(data)
        assert restored.patent_id == entry.patent_id
        assert restored.confidence == entry.confidence


# ---------------------------------------------------------------------------
# AnalysisAuditEntry
# ---------------------------------------------------------------------------


class TestAnalysisAuditEntry:
    def test_construction(self):
        entry = AnalysisAuditEntry(
            patent_id="US7851188B2",
            selected_for_analysis=True,
            selection_reason="Top-ranked relevant patent",
            risk_level="high",
            selected_for_doe=True,
            selected_for_invalidity=True,
        )
        assert entry.selected_for_analysis is True
        assert entry.risk_level == "high"
        assert entry.selected_for_doe is True
        assert entry.selected_for_invalidity is True

    def test_defaults(self):
        entry = AnalysisAuditEntry(
            patent_id="US123",
            selected_for_analysis=False,
        )
        assert entry.selection_reason == ""
        assert entry.risk_level is None
        assert entry.selected_for_doe is False
        assert entry.selected_for_invalidity is False

    def test_serialization_roundtrip(self):
        entry = AnalysisAuditEntry(
            patent_id="US789",
            selected_for_analysis=True,
            risk_level="medium",
        )
        data = entry.model_dump(mode="json")
        restored = AnalysisAuditEntry.model_validate(data)
        assert restored.risk_level == "medium"


# ---------------------------------------------------------------------------
# StepTiming
# ---------------------------------------------------------------------------


class TestStepTiming:
    def test_construction(self):
        started = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        completed = datetime(2025, 6, 1, 12, 0, 5, tzinfo=UTC)
        timing = StepTiming(
            step_name="step2_search",
            started_at=started,
            completed_at=completed,
            duration_seconds=5.0,
            items_processed=100,
            items_output=25,
        )
        assert timing.step_name == "step2_search"
        assert timing.duration_seconds == 5.0
        assert timing.items_processed == 100
        assert timing.items_output == 25

    def test_defaults(self):
        now = datetime.now(UTC)
        timing = StepTiming(
            step_name="step1",
            started_at=now,
            completed_at=now,
            duration_seconds=0.1,
        )
        assert timing.items_processed == 0
        assert timing.items_output == 0

    def test_serialization_roundtrip(self):
        now = datetime.now(UTC)
        timing = StepTiming(
            step_name="step3_triage",
            started_at=now,
            completed_at=now,
            duration_seconds=2.3,
            items_processed=50,
            items_output=10,
        )
        data = timing.model_dump(mode="json")
        restored = StepTiming.model_validate(data)
        assert restored.step_name == timing.step_name
        assert restored.duration_seconds == timing.duration_seconds


# ---------------------------------------------------------------------------
# PipelineAuditTrail
# ---------------------------------------------------------------------------


class TestPipelineAuditTrail:
    def test_empty_construction(self):
        trail = PipelineAuditTrail()
        assert trail.search_funnel == []
        assert trail.triage_audit == []
        assert trail.analysis_audit == []
        assert trail.timing_data == []
        assert trail.total_patents_discovered == 0
        assert trail.patents_after_hard_filter == 0
        assert trail.patents_after_ranking == 0
        assert trail.patents_after_triage == 0
        assert trail.patents_analyzed == 0

    def test_populated_construction(self):
        now = datetime.now(UTC)
        trail = PipelineAuditTrail(
            search_funnel=[
                SearchFunnelEntry(patent_id="US1"),
                SearchFunnelEntry(patent_id="US2"),
            ],
            triage_audit=[
                TriageAuditEntry(
                    patent_id="US1",
                    relevance="relevant",
                    reason="Direct match",
                    passed_triage=True,
                ),
            ],
            analysis_audit=[
                AnalysisAuditEntry(
                    patent_id="US1",
                    selected_for_analysis=True,
                ),
            ],
            timing_data=[
                StepTiming(
                    step_name="step1",
                    started_at=now,
                    completed_at=now,
                    duration_seconds=1.0,
                ),
            ],
            total_patents_discovered=100,
            patents_after_hard_filter=80,
            patents_after_ranking=25,
            patents_after_triage=10,
            patents_analyzed=5,
        )
        assert len(trail.search_funnel) == 2
        assert len(trail.triage_audit) == 1
        assert trail.total_patents_discovered == 100
        assert trail.patents_analyzed == 5

    def test_serialization_roundtrip(self):
        now = datetime.now(UTC)
        trail = PipelineAuditTrail(
            search_funnel=[SearchFunnelEntry(patent_id="US1")],
            timing_data=[
                StepTiming(
                    step_name="step2",
                    started_at=now,
                    completed_at=now,
                    duration_seconds=3.0,
                ),
            ],
            total_patents_discovered=50,
        )
        data = trail.model_dump(mode="json")
        restored = PipelineAuditTrail.model_validate(data)
        assert restored.total_patents_discovered == 50
        assert len(restored.search_funnel) == 1
        assert restored.search_funnel[0].patent_id == "US1"

    def test_defaults_are_list_factory(self):
        """Ensure default_factory=list produces independent instances."""
        trail_a = PipelineAuditTrail()
        trail_b = PipelineAuditTrail()
        trail_a.search_funnel.append(SearchFunnelEntry(patent_id="US99"))
        assert len(trail_b.search_funnel) == 0
