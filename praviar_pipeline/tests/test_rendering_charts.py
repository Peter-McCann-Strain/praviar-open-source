"""Tests for praviar_pipeline.rendering.charts — matplotlib chart generation."""

import base64
from datetime import date, datetime, timedelta

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.audit import PipelineAuditTrail, StepTiming
from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.rendering.charts import (
    _fmt_duration,
    render_assignee_chart,
    render_funnel_chart,
    render_patent_timeline,
    render_risk_distribution_chart,
    render_risk_gauge,
    render_source_health_chart,
    render_timing_waterfall,
)


def _make_audit_trail(**overrides) -> PipelineAuditTrail:
    defaults = {
        "total_patents_discovered": 5000,
        "patents_after_hard_filter": 2000,
        "patents_after_ranking": 200,
        "patents_after_triage": 30,
        "patents_analyzed": 15,
    }
    defaults.update(overrides)
    return PipelineAuditTrail(**defaults)


def _make_analysis(risk_level: RiskLevel) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=f"US{id(risk_level)}B2",
        title="Test patent",
        assignee="Acme",
        claims_analyzed=[],
        risk_level=risk_level,
        risk_summary="test",
    )


class TestRenderFunnelChart:
    def test_returns_base64_string(self):
        trail = _make_audit_trail()
        result = render_funnel_chart(trail)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_output_is_valid_base64(self):
        trail = _make_audit_trail()
        result = render_funnel_chart(trail)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"  # PNG magic bytes

    def test_handles_zero_counts(self):
        trail = _make_audit_trail(
            total_patents_discovered=0,
            patents_after_hard_filter=0,
            patents_after_ranking=0,
            patents_after_triage=0,
            patents_analyzed=0,
        )
        result = render_funnel_chart(trail)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"


class TestRenderRiskDistributionChart:
    def test_returns_base64_png(self):
        analyses = [
            _make_analysis(RiskLevel.HIGH),
            _make_analysis(RiskLevel.MEDIUM),
            _make_analysis(RiskLevel.LOW),
        ]
        result = render_risk_distribution_chart(analyses)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"

    def test_empty_analyses(self):
        result = render_risk_distribution_chart([])
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"

    def test_single_risk_level(self):
        analyses = [_make_analysis(RiskLevel.HIGH)] * 5
        result = render_risk_distribution_chart(analyses)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_all_clear_counted_as_low(self):
        analyses = [_make_analysis(RiskLevel.CLEAR)]
        result = render_risk_distribution_chart(analyses)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"


def _make_full_analysis(
    patent_id: str,
    risk: RiskLevel,
    assignee: str = "Test Corp",
    expiry: date | None = None,
) -> PatentAnalysis:
    """Helper to create a PatentAnalysis with all commonly-needed fields."""
    return PatentAnalysis(
        patent_id=patent_id,
        title=f"Patent {patent_id}",
        assignee=assignee,
        expiry_date=expiry,
        risk_level=risk,
        risk_summary="Test risk summary",
        claims_analyzed=[],
        input_tokens=0,
        output_tokens=0,
    )


def _make_step_timing(
    step_name: str,
    duration_seconds: float,
) -> StepTiming:
    """Helper to create a StepTiming entry."""
    started = datetime(2026, 1, 1, 12, 0, 0)
    completed = started + timedelta(seconds=duration_seconds)
    return StepTiming(
        step_name=step_name,
        started_at=started,
        completed_at=completed,
        duration_seconds=duration_seconds,
    )


def _assert_valid_base64_png(result: str) -> None:
    """Shared assertion: result is a non-trivial base64-encoded PNG."""
    assert isinstance(result, str)
    assert len(result) > 50
    decoded = base64.b64decode(result)
    assert decoded[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# 3. TestRenderPatentTimeline
# ---------------------------------------------------------------------------


class TestRenderPatentTimeline:
    def test_returns_base64_png(self):
        analyses = [
            _make_full_analysis("US1234567B2", RiskLevel.HIGH, expiry=date(2030, 6, 15)),
        ]
        result = render_patent_timeline(analyses)
        _assert_valid_base64_png(result)

    def test_empty_analyses(self):
        result = render_patent_timeline([])
        _assert_valid_base64_png(result)

    def test_missing_patent_details(self):
        analyses = [
            _make_full_analysis("US1111111B2", RiskLevel.MEDIUM, expiry=date(2032, 1, 1)),
        ]
        result = render_patent_timeline(analyses, patent_details=None)
        _assert_valid_base64_png(result)

    def test_multiple_risk_levels(self):
        analyses = [
            _make_full_analysis("US0001A", RiskLevel.HIGH, expiry=date(2035, 3, 1)),
            _make_full_analysis("US0002A", RiskLevel.MEDIUM, expiry=date(2030, 7, 15)),
            _make_full_analysis("US0003A", RiskLevel.LOW, expiry=date(2028, 12, 31)),
        ]
        result = render_patent_timeline(analyses)
        _assert_valid_base64_png(result)

    def test_none_expiry_dates(self):
        """All analyses have expiry_date=None -- should produce placeholder chart."""
        analyses = [
            _make_full_analysis("US9999A", RiskLevel.HIGH, expiry=None),
            _make_full_analysis("US9998A", RiskLevel.LOW, expiry=None),
        ]
        result = render_patent_timeline(analyses)
        _assert_valid_base64_png(result)

    def test_with_patent_details(self):
        analyses = [
            _make_full_analysis("US5555B2", RiskLevel.MEDIUM, expiry=date(2033, 5, 20)),
        ]
        patent_details = {
            "US5555B2": {"filing_date": date(2013, 5, 20)},
        }
        result = render_patent_timeline(analyses, patent_details=patent_details)
        _assert_valid_base64_png(result)


# ---------------------------------------------------------------------------
# 4. TestRenderRiskGauge
# ---------------------------------------------------------------------------


class TestRenderRiskGauge:
    def test_high_risk(self):
        result = render_risk_gauge(RiskLevel.HIGH, blocking_count=5, total_analyzed=10)
        _assert_valid_base64_png(result)

    def test_clear_risk(self):
        result = render_risk_gauge(RiskLevel.CLEAR, blocking_count=0, total_analyzed=10)
        _assert_valid_base64_png(result)

    def test_zero_counts(self):
        result = render_risk_gauge(RiskLevel.LOW, blocking_count=0, total_analyzed=0)
        _assert_valid_base64_png(result)

    def test_large_counts(self):
        result = render_risk_gauge(RiskLevel.HIGH, blocking_count=50, total_analyzed=100)
        _assert_valid_base64_png(result)

    def test_all_risk_levels(self):
        for level in [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.CLEAR]:
            result = render_risk_gauge(level, blocking_count=1, total_analyzed=5)
            _assert_valid_base64_png(result)


# ---------------------------------------------------------------------------
# 5. TestRenderAssigneeChart
# ---------------------------------------------------------------------------


class TestRenderAssigneeChart:
    def test_returns_base64_png(self):
        analyses = [
            _make_full_analysis("US0001A", RiskLevel.HIGH, assignee="Acme Corp"),
            _make_full_analysis("US0002A", RiskLevel.MEDIUM, assignee="BioGen Inc"),
        ]
        result = render_assignee_chart(analyses)
        _assert_valid_base64_png(result)

    def test_empty_analyses(self):
        result = render_assignee_chart([])
        _assert_valid_base64_png(result)

    def test_multiple_assignees(self):
        analyses = [
            _make_full_analysis(f"US{i:04d}A", RiskLevel.LOW, assignee=f"Company {chr(65 + i)}")
            for i in range(8)
        ]
        result = render_assignee_chart(analyses)
        _assert_valid_base64_png(result)

    def test_long_assignee_name(self):
        long_name = "A" * 100
        analyses = [
            _make_full_analysis("US0001A", RiskLevel.HIGH, assignee=long_name),
        ]
        result = render_assignee_chart(analyses)
        _assert_valid_base64_png(result)

    def test_single_assignee(self):
        analyses = [
            _make_full_analysis(f"US{i:04d}A", RiskLevel.MEDIUM, assignee="Universal Corp")
            for i in range(5)
        ]
        result = render_assignee_chart(analyses)
        _assert_valid_base64_png(result)


# ---------------------------------------------------------------------------
# 6. TestRenderTimingWaterfall
# ---------------------------------------------------------------------------


class TestRenderTimingWaterfall:
    def test_returns_base64_png(self):
        trail = PipelineAuditTrail(
            timing_data=[
                _make_step_timing("step1_resolve", 2.5),
                _make_step_timing("step2_search", 15.0),
                _make_step_timing("step3_triage", 8.3),
            ],
        )
        result = render_timing_waterfall(trail)
        _assert_valid_base64_png(result)

    def test_empty_timing(self):
        trail = PipelineAuditTrail(timing_data=[])
        result = render_timing_waterfall(trail)
        _assert_valid_base64_png(result)

    def test_various_durations(self):
        trail = PipelineAuditTrail(
            timing_data=[
                _make_step_timing("fast_step", 0.05),  # sub-second -> ms
                _make_step_timing("medium_step", 12.345),  # seconds
                _make_step_timing("slow_step", 125.0),  # minutes
            ],
        )
        result = render_timing_waterfall(trail)
        _assert_valid_base64_png(result)

    def test_fmt_duration_helper(self):
        """Test the _fmt_duration function directly with edge cases."""
        # Sub-100ms -> milliseconds
        assert _fmt_duration(0.05) == "50ms"
        assert _fmt_duration(0.001) == "1ms"
        # Seconds range
        assert _fmt_duration(0.1) == "0.1s"
        assert _fmt_duration(5.0) == "5.0s"
        assert _fmt_duration(59.9) == "59.9s"
        # Minutes range
        assert _fmt_duration(60.0) == "1m 0s"
        assert _fmt_duration(90.0) == "1m 30s"
        assert _fmt_duration(125.0) == "2m 5s"


# ---------------------------------------------------------------------------
# 7. TestRenderSourceHealthChart
# ---------------------------------------------------------------------------


class TestRenderSourceHealthChart:
    def test_returns_base64_png(self):
        entries = [
            {"source": "PubChem", "status": "OK", "patent_count": 42},
            {"source": "BigQuery", "status": "OK", "patent_count": 18},
        ]
        result = render_source_health_chart(entries)
        _assert_valid_base64_png(result)

    def test_empty_sources(self):
        result = render_source_health_chart([])
        _assert_valid_base64_png(result)

    def test_dict_input(self):
        entries = [
            {"source": "PubChem", "status": "OK", "patent_count": 10},
        ]
        result = render_source_health_chart(entries)
        _assert_valid_base64_png(result)

    def test_object_input(self):
        entries = [
            SourceHealthEntry(source="PubChem", status=SourceStatus.OK, patent_count=25),
            SourceHealthEntry(source="SureChEMBL", status=SourceStatus.FAILED, patent_count=0),
        ]
        result = render_source_health_chart(entries)
        _assert_valid_base64_png(result)

    def test_mixed_statuses(self):
        entries = [
            {"source": "PubChem", "status": "OK", "patent_count": 50},
            {"source": "BigQuery", "status": "FAILED", "patent_count": 0},
            {"source": "PatCID", "status": "SKIPPED", "patent_count": 0},
            {"source": "SureChEMBL", "status": "OK", "patent_count": 12},
        ]
        result = render_source_health_chart(entries)
        _assert_valid_base64_png(result)
