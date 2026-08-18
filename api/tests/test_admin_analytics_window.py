"""Tests for shared admin analytics window helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from api.db.models import Analysis
from api.services.admin_analytics import (
    build_analytics_window_filter,
    model_name_from_config,
    parse_date_range,
    parse_period,
)


def test_parse_period_defaults_to_month_for_unknown_value():
    assert parse_period("weird") == timedelta(days=30)


def test_parse_date_range_uses_explicit_iso_values():
    start, end = parse_date_range("month", "2026-04-01", "2026-04-11")

    assert start == datetime(2026, 4, 1, tzinfo=UTC)
    assert end == datetime(2026, 4, 11, tzinfo=UTC)


def test_build_analytics_window_filter_uses_created_at_between():
    result = build_analytics_window_filter(
        datetime(2026, 4, 1, tzinfo=UTC),
        datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert "created_at BETWEEN" in str(result)
    assert "BETWEEN" in str(result).upper()
    assert Analysis.created_at.key == "created_at"


def test_model_name_from_config_defaults_to_unified_adaptive_profile():
    assert model_name_from_config({}) == "world_class_adaptive"


def test_model_name_from_config_uses_adaptive_execution_profile():
    assert (
        model_name_from_config({"analysis_execution_profile": "agentic_escalation"})
        == "agentic_escalation"
    )
