"""Tests for pure admin metrics helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from api.schemas.admin import DailyMetric
from api.services.admin_health import (
    build_admin_metrics_summary,
    build_metrics_window_start,
    serialize_daily_metric_row,
)


def test_build_metrics_window_start_uses_reference_time():
    now = datetime(2026, 4, 11, 12, 0, tzinfo=UTC)

    window_start = build_metrics_window_start(now=now, window_days=30)

    assert window_start == datetime(2026, 3, 12, 12, 0, tzinfo=UTC)


def test_serialize_daily_metric_row_normalizes_fields():
    row = SimpleNamespace(date=date(2026, 4, 1), count=3, cost=12.5, errors=None)

    metric = serialize_daily_metric_row(row)

    assert metric == DailyMetric(date="2026-04-01", count=3, cost=12.5, errors=0)


def test_build_admin_metrics_summary_computes_error_rate_and_cost():
    summary = build_admin_metrics_summary(
        daily=[DailyMetric(date="2026-04-01", count=3, cost=12.5, errors=1)],
        total_analyses=4,
        total_cost=None,
        avg_duration_seconds=87.5,
        error_count=1,
    )

    assert summary.daily[0].date == "2026-04-01"
    assert summary.total_analyses == 4
    assert summary.total_cost == 0.0
    assert summary.avg_duration_seconds == 87.5
    assert summary.error_rate == 0.25


def test_build_admin_metrics_summary_handles_zero_analyses():
    summary = build_admin_metrics_summary(
        daily=[],
        total_analyses=0,
        total_cost=16.5,
        avg_duration_seconds=None,
        error_count=0,
    )

    assert summary.total_analyses == 0
    assert summary.total_cost == 16.5
    assert summary.avg_duration_seconds is None
    assert summary.error_rate == 0.0
