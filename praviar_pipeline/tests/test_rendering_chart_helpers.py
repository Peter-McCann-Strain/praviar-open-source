"""Focused tests for chart helper modules."""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.audit import PipelineAuditTrail, StepTiming
from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.rendering.charts_distribution import (
    render_funnel_chart,
    render_risk_distribution_chart,
)
from praviar_pipeline.rendering.charts_gauge import render_risk_gauge
from praviar_pipeline.rendering.charts_timeline import (
    render_assignee_chart,
    render_patent_timeline,
    render_source_health_chart,
    render_timing_waterfall,
)


def _assert_png(result: str) -> None:
    assert isinstance(result, str)
    assert len(result) > 50
    decoded = base64.b64decode(result)
    assert decoded[:4] == b"\x89PNG"


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


def _make_analysis(
    patent_id: str,
    risk: RiskLevel,
    assignee: str = "Test Corp",
    expiry: date | None = None,
) -> PatentAnalysis:
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


def _make_step_timing(step_name: str, duration_seconds: float) -> StepTiming:
    started = datetime(2026, 1, 1, 12, 0, 0)
    completed = started + timedelta(seconds=duration_seconds)
    return StepTiming(
        step_name=step_name,
        started_at=started,
        completed_at=completed,
        duration_seconds=duration_seconds,
    )


def test_distribution_helpers_render_png() -> None:
    _assert_png(render_funnel_chart(_make_audit_trail()))
    _assert_png(
        render_risk_distribution_chart(
            [
                _make_analysis("US1", RiskLevel.HIGH),
                _make_analysis("US2", RiskLevel.MEDIUM),
            ],
        ),
    )


def test_timeline_and_series_helpers_render_png() -> None:
    analyses = [
        _make_analysis("US1234567B2", RiskLevel.HIGH, expiry=date(2030, 6, 15)),
        _make_analysis("US9999999B2", RiskLevel.MEDIUM, assignee="Acme Incorporated"),
    ]
    _assert_png(render_patent_timeline(analyses))
    _assert_png(render_assignee_chart(analyses))
    _assert_png(
        render_timing_waterfall(
            PipelineAuditTrail(
                timing_data=[
                    _make_step_timing("step1_resolve", 2.5),
                    _make_step_timing("step2_search", 15.0),
                ],
            ),
        ),
    )
    _assert_png(
        render_source_health_chart(
            [
                SourceHealthEntry(source="PubChem", status=SourceStatus.OK, patent_count=25),
                SourceHealthEntry(source="SureChEMBL", status=SourceStatus.FAILED, patent_count=0),
            ],
        ),
    )


def test_risk_gauge_helper_render_png() -> None:
    _assert_png(render_risk_gauge(RiskLevel.HIGH, blocking_count=5, total_analyzed=10))
