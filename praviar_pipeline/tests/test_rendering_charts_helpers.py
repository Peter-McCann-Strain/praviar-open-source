"""Tests for chart data and export helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.audit import PipelineAuditTrail, StepTiming
from praviar_pipeline.rendering.charts_data import (
    build_assignee_series,
    build_funnel_chart_data,
    build_patent_timeline_entries,
    build_risk_distribution_series,
    build_timing_series,
    fmt_duration,
    normalize_source_entries,
)


def _make_analysis(
    patent_id: str = "US1234567B2",
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    assignee: str = "Acme",
    expiry: date | None = None,
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title="Test patent",
        assignee=assignee,
        expiry_date=expiry,
        claims_analyzed=[],
        risk_level=risk_level,
        risk_summary="test",
    )


def _make_trail() -> PipelineAuditTrail:
    started = datetime(2026, 1, 1, 12, 0, 0)
    return PipelineAuditTrail(
        total_patents_discovered=10,
        patents_after_hard_filter=8,
        patents_after_ranking=6,
        patents_after_triage=4,
        patents_analyzed=2,
        timing_data=[
            StepTiming(
                step_name="step1_resolve",
                started_at=started,
                completed_at=started + timedelta(seconds=2.5),
                duration_seconds=2.5,
            ),
        ],
    )


def test_fmt_duration():
    assert fmt_duration(0.05) == "50ms"
    assert fmt_duration(0.1) == "0.1s"
    assert fmt_duration(65.0) == "1m 5s"


def test_build_funnel_chart_data():
    labels, counts = build_funnel_chart_data(_make_trail())
    assert labels[0] == "Discovered"
    assert counts[-1] == 2


def test_build_risk_distribution_series():
    analyses = [
        _make_analysis(risk_level=RiskLevel.HIGH),
        _make_analysis(risk_level=RiskLevel.MEDIUM),
        _make_analysis(risk_level=RiskLevel.MEDIUM),
    ]
    series = build_risk_distribution_series(analyses)
    assert [entry[0] for entry in series] == [RiskLevel.HIGH, RiskLevel.MEDIUM]
    assert [entry[2] for entry in series] == [1, 2]


def test_build_patent_timeline_entries_defaults_filing_date():
    analyses = [_make_analysis(expiry=date(2030, 1, 1))]
    entries = build_patent_timeline_entries(analyses)
    assert entries[0][0] == "US1234567B2"
    assert entries[0][2] == date(2030, 1, 1)


def test_build_assignee_series():
    analyses = [
        _make_analysis(assignee="Beta"),
        _make_analysis(assignee="Alpha"),
        _make_analysis(assignee="Beta"),
    ]
    series = build_assignee_series(analyses)
    assert series[-1] == ("Beta", 2)


def test_build_timing_series():
    trail = _make_trail()
    assert build_timing_series(trail) == [("step1_resolve", 2.5)]


def test_normalize_source_entries():
    entries = [
        {"source": "PubChem", "status": "ok", "patent_count": 5},
        {"source": "BigQuery", "status": "failed", "patent_count": 0},
    ]
    normalized = normalize_source_entries(entries)
    assert normalized[0] == ("BigQuery", "FAILED", 0)
    assert normalized[1] == ("PubChem", "OK", 5)
