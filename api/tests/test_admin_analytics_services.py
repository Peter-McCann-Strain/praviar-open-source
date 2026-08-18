"""Tests for admin analytics service helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.db.models import AnalysisStatus
from api.schemas.admin_analytics import AuditLogEntryExtended
from api.services.admin_analytics import (
    estimate_model_cost,
    get_audit_log_page,
    get_cost_breakdown_summary,
    get_model_pricing,
    get_model_usage_summary,
    get_usage_analytics_summary,
    parse_date_range,
    parse_period,
    render_audit_log_csv,
)


def _row(**values):
    row = SimpleNamespace(**values)
    row._mapping = values
    return row


def test_parse_period_defaults_to_month_for_unknown_value():
    assert parse_period("weird") == timedelta(days=30)


def test_parse_date_range_uses_explicit_iso_values():
    start, end = parse_date_range("month", "2026-04-01", "2026-04-11")

    assert start == datetime(2026, 4, 1, tzinfo=UTC)
    assert end == datetime(2026, 4, 11, tzinfo=UTC)


def test_parse_date_range_rejects_partial_explicit_range():
    with pytest.raises(ValueError, match="start_date and end_date"):
        parse_date_range("month", "2026-04-01", None)


def test_parse_date_range_rejects_invalid_explicit_value():
    with pytest.raises(ValueError, match="start_date must be an ISO-8601"):
        parse_date_range("month", "not-a-date", "2026-04-11")


def test_parse_date_range_rejects_inverted_explicit_range():
    with pytest.raises(ValueError, match="start_date must be before"):
        parse_date_range("month", "2026-04-12", "2026-04-11")


def test_estimate_model_cost_uses_default_pricing_when_model_unknown():
    with patch(
        "api.services.admin_analytics.get_model_pricing",
        return_value={"default": (3.0, 15.0)},
    ):
        cost = estimate_model_cost("unknown-model", 1_000_000, 2_000_000)

    assert cost == 33.0


def test_get_model_pricing_surfaces_pipeline_config_errors():
    with (
        patch("praviar_pipeline.config.get_settings", side_effect=RuntimeError("broken")),
        pytest.raises(RuntimeError, match="broken"),
    ):
        get_model_pricing()


async def test_get_usage_analytics_summary_builds_usage_breakdown(mock_db):
    org_id = uuid.uuid4()
    org_result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(
                org_id=org_id,
                org_name="Praviar Labs",
                analysis_count=4,
                total_cost=20.0,
            )
        ]
    )
    status_result = SimpleNamespace(
        all=lambda: [
            _row(status=AnalysisStatus.COMPLETED, count=3),
            _row(status=AnalysisStatus.FAILED, count=1),
        ]
    )
    compound_result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(
                compound_name="aspirin",
                compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
                analysis_count=2,
            )
        ]
    )
    agg_result = SimpleNamespace(
        one=lambda: SimpleNamespace(total=4, total_cost=20.0, avg_duration=55.5)
    )
    mock_db.execute.side_effect = [org_result, status_result, compound_result, agg_result]

    summary = await get_usage_analytics_summary(
        mock_db,
        period="month",
        range_start=datetime(2026, 4, 1, tzinfo=UTC),
        range_end=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert summary.period == "month"
    assert summary.total_analyses == 4
    assert summary.avg_cost_per_analysis == 5.0
    assert summary.avg_duration_seconds == 55.5
    assert summary.org_usage[0].org_name == "Praviar Labs"
    assert summary.status_breakdown[0].status == "completed"
    assert summary.top_compounds[0].compound_name == "aspirin"


@pytest.mark.asyncio
async def test_get_cost_breakdown_summary_builds_sections(mock_db):
    daily_result = SimpleNamespace(
        all=lambda: [
            _row(
                date="2026-04-11",
                total_cost=12.3,
                count=2,
                input_tokens=1000,
                output_tokens=500,
            )
        ]
    )
    step_result = SimpleNamespace(
        all=lambda: [SimpleNamespace(step_name="step4_analyze", analysis_count=2)]
    )
    totals_result = SimpleNamespace(one=lambda: SimpleNamespace(total_cost=12.3, total_count=2))
    model_result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(
                config={"analysis_execution_profile": "agentic_escalation"},
                input_tokens=1000,
                output_tokens=500,
                total_cost=12.3,
                count=2,
            )
        ]
    )
    mock_db.execute.side_effect = [daily_result, step_result, totals_result, model_result]

    summary = await get_cost_breakdown_summary(
        mock_db,
        period="month",
        start_date="2026-04-01",
        end_date="2026-04-11",
        org_id=None,
    )

    assert summary.total_cost_usd == 12.3
    assert summary.total_input_tokens == 1000
    assert summary.step_costs[0].step_name == "step4_analyze"
    assert summary.model_costs[0].model_name == "agentic_escalation"
    assert summary.start_date == "2026-04-01"
    assert summary.end_date == "2026-04-11"


async def test_get_model_usage_summary_aggregates_by_model(mock_db):
    aggregate_result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(
                config={"analysis_execution_profile": "agentic_escalation"},
                input_tokens=1200,
                output_tokens=300,
                total_cost=12.3456,
                count=4,
            ),
            SimpleNamespace(
                config={"analysis_execution_profile": "single_pass"},
                input_tokens=500,
                output_tokens=100,
                total_cost=3.5,
                count=2,
            ),
        ]
    )
    cache_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: [
                {
                    "cost": {
                        "cache_creation_input_tokens": 100,
                        "cache_read_input_tokens": 50,
                    }
                },
                {
                    "cost": {
                        "cache_creation_input_tokens": 200,
                        "cache_read_input_tokens": 0,
                    }
                },
            ]
        )
    )
    mock_db.execute.side_effect = [aggregate_result, cache_result]

    summary = await get_model_usage_summary(
        mock_db,
        period="month",
        range_start=datetime(2026, 4, 1, tzinfo=UTC),
        range_end=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert summary.period == "month"
    assert summary.total_tokens == 2100
    assert summary.total_cost_usd == 15.8456
    assert summary.overall_cache_hit_rate == 50.0
    assert [model.model_name for model in summary.models] == [
        "agentic_escalation",
        "single_pass",
    ]
    assert summary.models[0].request_count == 4
    assert summary.models[1].total_tokens == 600


@pytest.mark.asyncio
async def test_get_audit_log_page_builds_user_emails(mock_db):
    audit_entry = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action="analysis.created",
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        details={"compound": "aspirin"},
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 1)
    logs_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [audit_entry]))
    users_result = SimpleNamespace(all=lambda: [(audit_entry.user_id, "user@praviar.io")])
    mock_db.execute.side_effect = [count_result, logs_result, users_result]

    page = await get_audit_log_page(
        mock_db,
        action=None,
        user_id=None,
        start_date=None,
        end_date=None,
        page=1,
        per_page=50,
        sort="desc",
    )

    assert page.total == 1
    assert page.items[0].user_email == "user@praviar.io"
    assert page.has_next is False


def test_render_audit_log_csv_writes_rows():
    item = AuditLogEntryExtended(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action="analysis.created",
        user_id=uuid.uuid4(),
        user_email="user@praviar.io",
        analysis_id=uuid.uuid4(),
        details={"compound": "aspirin"},
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )

    csv_text = render_audit_log_csv([item])

    assert "analysis.created" in csv_text
    assert "user@praviar.io" in csv_text
