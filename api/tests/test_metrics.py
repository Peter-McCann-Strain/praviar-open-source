"""Tests for domain-level Prometheus metrics in api.metrics."""

from __future__ import annotations

import prometheus_client

from api.metrics import (
    active_analyses_gauge,
    adaptive_escalations_total,
    celery_tasks_total,
    checkpoint_decisions_total,
    db_pool_saturation_gauge,
    drawing_influence_total,
    evaluator_outcomes_total,
    export_duration_seconds,
    llm_tokens_used_total,
    pipeline_duration_seconds,
    pipeline_runs_total,
    provider_errors_total,
    provider_latency_seconds,
    queue_depth_gauge,
    queue_oldest_task_age_seconds,
    record_adaptive_escalation,
    record_checkpoint_decision,
    record_evaluator_outcome,
    record_pipeline_run,
    record_provider_call,
    source_health_total,
    stale_analysis_oldest_expired_running_age_seconds,
    stale_analysis_reclaimed_total,
    stale_analysis_redrive_failures_total,
    stale_analysis_sweep_last_success_unixtime,
    webhook_duration_seconds,
)

# ---------------------------------------------------------------------------
# Existence checks
# ---------------------------------------------------------------------------


def test_pipeline_runs_total_exists() -> None:
    assert isinstance(pipeline_runs_total, prometheus_client.Counter)


def test_pipeline_duration_seconds_exists() -> None:
    assert isinstance(pipeline_duration_seconds, prometheus_client.Histogram)


def test_llm_tokens_used_total_exists() -> None:
    assert isinstance(llm_tokens_used_total, prometheus_client.Counter)


def test_celery_tasks_total_exists() -> None:
    assert isinstance(celery_tasks_total, prometheus_client.Counter)


def test_active_analyses_gauge_exists() -> None:
    assert isinstance(active_analyses_gauge, prometheus_client.Gauge)


def test_new_operational_metrics_exist() -> None:
    assert isinstance(adaptive_escalations_total, prometheus_client.Counter)
    assert isinstance(evaluator_outcomes_total, prometheus_client.Counter)
    assert isinstance(provider_latency_seconds, prometheus_client.Histogram)
    assert isinstance(provider_errors_total, prometheus_client.Counter)
    assert isinstance(source_health_total, prometheus_client.Counter)
    assert isinstance(drawing_influence_total, prometheus_client.Counter)
    assert isinstance(queue_depth_gauge, prometheus_client.Gauge)
    assert isinstance(queue_oldest_task_age_seconds, prometheus_client.Gauge)
    assert isinstance(db_pool_saturation_gauge, prometheus_client.Gauge)
    assert isinstance(export_duration_seconds, prometheus_client.Histogram)
    assert isinstance(webhook_duration_seconds, prometheus_client.Histogram)
    assert isinstance(checkpoint_decisions_total, prometheus_client.Counter)
    assert isinstance(stale_analysis_sweep_last_success_unixtime, prometheus_client.Gauge)
    assert isinstance(
        stale_analysis_oldest_expired_running_age_seconds,
        prometheus_client.Gauge,
    )
    assert isinstance(stale_analysis_reclaimed_total, prometheus_client.Counter)
    assert isinstance(stale_analysis_redrive_failures_total, prometheus_client.Counter)


# ---------------------------------------------------------------------------
# Metric names registered in the default registry
# ---------------------------------------------------------------------------

# prometheus_client strips the "_total" suffix from Counter metric *family*
# names when collecting (the suffix is re-added to the individual sample
# names).  The registered family names are therefore without the suffix.
_EXPECTED_METRIC_NAMES = {
    "praviar_pipeline_runs",
    "praviar_pipeline_duration_seconds",
    "praviar_llm_tokens",
    "praviar_celery_tasks",
    "praviar_active_analyses",
    "praviar_adaptive_escalations",
    "praviar_evaluator_outcomes",
    "praviar_provider_latency_seconds",
    "praviar_provider_errors",
    "praviar_source_health",
    "praviar_drawing_influence",
    "praviar_queue_depth",
    "praviar_queue_oldest_task_age_seconds",
    "praviar_db_pool_saturation",
    "praviar_export_duration_seconds",
    "praviar_webhook_duration_seconds",
    "praviar_checkpoint_decisions",
    "praviar_stale_analysis_sweep_last_success_unixtime",
    "praviar_stale_analysis_oldest_expired_running_age_seconds",
    "praviar_stale_analysis_reclaimed",
    "praviar_stale_analysis_redrive_failures",
}


def test_metric_names_in_registry() -> None:
    registered = {m.name for m in prometheus_client.REGISTRY.collect()}
    for name in _EXPECTED_METRIC_NAMES:
        assert name in registered, f"Metric '{name}' not found in REGISTRY"


# ---------------------------------------------------------------------------
# record_pipeline_run helper
# ---------------------------------------------------------------------------


def test_record_pipeline_run_increments_counter() -> None:
    # Capture the counter value before calling the helper.
    before = _counter_value(
        pipeline_runs_total,
        status="completed",
        execution_profile="world_class_adaptive",
    )

    record_pipeline_run("completed", "world_class_adaptive", 45.2)

    after = _counter_value(
        pipeline_runs_total,
        status="completed",
        execution_profile="world_class_adaptive",
    )
    assert after == before + 1.0


def test_record_pipeline_run_observes_histogram() -> None:
    # Ensure that observing a duration does not raise and that the _count
    # bucket increases.
    before_count = _histogram_count(
        pipeline_duration_seconds,
        execution_profile="world_class_adaptive",
    )

    record_pipeline_run("completed", "world_class_adaptive", 45.2)

    after_count = _histogram_count(
        pipeline_duration_seconds,
        execution_profile="world_class_adaptive",
    )
    assert after_count == before_count + 1


def test_record_pipeline_run_different_statuses() -> None:
    before_failed = _counter_value(
        pipeline_runs_total,
        status="failed",
        execution_profile="world_class_adaptive",
    )
    before_cancelled = _counter_value(
        pipeline_runs_total,
        status="cancelled",
        execution_profile="world_class_adaptive",
    )

    record_pipeline_run("failed", "world_class_adaptive", 12.0)
    record_pipeline_run("cancelled", "world_class_adaptive", 5.0)

    assert (
        _counter_value(
            pipeline_runs_total,
            status="failed",
            execution_profile="world_class_adaptive",
        )
        == before_failed + 1.0
    )
    assert (
        _counter_value(
            pipeline_runs_total,
            status="cancelled",
            execution_profile="world_class_adaptive",
        )
        == before_cancelled + 1.0
    )


def test_new_metric_helpers_increment_expected_series() -> None:
    before_escalation = _counter_value(
        adaptive_escalations_total,
        stage="agentic_escalation",
        reason="drawing_structure_evidence",
    )
    before_evaluator = _counter_value(evaluator_outcomes_total, outcome="poor")
    before_provider_error = _counter_value(
        provider_errors_total,
        provider="anthropic",
        operation="analysis",
    )
    before_checkpoint = _counter_value(
        checkpoint_decisions_total,
        checkpoint_type="analysis_review",
        decision="approve",
    )

    record_adaptive_escalation("agentic_escalation", ["drawing_structure_evidence"])
    record_evaluator_outcome("poor")
    record_provider_call(
        provider="anthropic",
        operation="analysis",
        duration_s=0.2,
        errored=True,
    )
    record_checkpoint_decision("analysis_review", "approve")

    assert (
        _counter_value(
            adaptive_escalations_total,
            stage="agentic_escalation",
            reason="drawing_structure_evidence",
        )
        == before_escalation + 1.0
    )
    assert _counter_value(evaluator_outcomes_total, outcome="poor") == before_evaluator + 1.0
    assert (
        _counter_value(
            provider_errors_total,
            provider="anthropic",
            operation="analysis",
        )
        == before_provider_error + 1.0
    )
    assert (
        _counter_value(
            checkpoint_decisions_total,
            checkpoint_type="analysis_review",
            decision="approve",
        )
        == before_checkpoint + 1.0
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _counter_value(counter: prometheus_client.Counter, **labels: str) -> float:
    """Return the current value of a labelled Counter sample."""
    child = counter.labels(**labels)
    # _value.get() returns the underlying float.
    return child._value.get()  # type: ignore[attr-defined]


def _histogram_count(histogram: prometheus_client.Histogram, **labels: str) -> float:
    """Return the observation count for a labelled Histogram.

    prometheus_client does not expose a ``_count`` attribute on child objects;
    the count is only available via the collected samples.  We locate the
    ``*_count`` sample that matches the requested label set.
    """
    count_suffix = "_count"
    for metric_family in histogram.collect():
        for sample in metric_family.samples:
            if sample.name.endswith(count_suffix) and sample.labels == labels:
                return sample.value
    return 0.0
