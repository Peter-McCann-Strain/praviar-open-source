"""Domain-level Prometheus metrics for the Praviar API.

These metrics are registered with the default prometheus_client registry on
import and are therefore exposed alongside the standard HTTP metrics at the
/metrics endpoint (which is gated to loopback callers only).

Import this module once during app initialisation (e.g. in app_setup.py after
configure_extensions) so that all metric names are registered before the first
scrape request arrives.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Pipeline outcomes
# ---------------------------------------------------------------------------

pipeline_runs_total = Counter(
    "praviar_pipeline_runs_total",
    "Total pipeline runs by status",
    ["status", "execution_profile"],  # status: completed / failed / cancelled
)

pipeline_duration_seconds = Histogram(
    "praviar_pipeline_duration_seconds",
    "Pipeline end-to-end wall-clock time",
    ["execution_profile"],
    buckets=[30, 60, 120, 300, 600, 1200, 3600],
)

# ---------------------------------------------------------------------------
# LLM cost tracking
# ---------------------------------------------------------------------------

llm_tokens_used_total = Counter(
    "praviar_llm_tokens_total",
    "LLM tokens consumed by type",
    ["token_type", "model"],  # token_type: input / output / cache_read / cache_write
)

# ---------------------------------------------------------------------------
# Celery task completions
# ---------------------------------------------------------------------------

celery_tasks_total = Counter(
    "praviar_celery_tasks_total",
    "Celery task completions",
    ["task_name", "status"],
)

# ---------------------------------------------------------------------------
# Concurrency gauge
# ---------------------------------------------------------------------------

active_analyses_gauge = Gauge(
    "praviar_active_analyses",
    "Number of analyses currently in progress",
)

adaptive_escalations_total = Counter(
    "praviar_adaptive_escalations_total",
    "Adaptive analysis escalations by stage and reason",
    ["stage", "reason"],
)

evaluator_outcomes_total = Counter(
    "praviar_evaluator_outcomes_total",
    "Evaluator outcomes for adaptive claim analysis",
    ["outcome"],
)

provider_latency_seconds = Histogram(
    "praviar_provider_latency_seconds",
    "Provider call latency by provider and operation",
    ["provider", "operation"],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
)

provider_errors_total = Counter(
    "praviar_provider_errors_total",
    "Provider call errors by provider and operation",
    ["provider", "operation"],
)

source_health_total = Counter(
    "praviar_source_health_total",
    "Source health observations by source and status",
    ["source", "status"],
)

drawing_influence_total = Counter(
    "praviar_drawing_influence_total",
    "Drawing influence state observations",
    ["state"],
)

queue_depth_gauge = Gauge(
    "praviar_queue_depth",
    "Queue depth by queue name",
    ["queue"],
)

queue_oldest_task_age_seconds = Gauge(
    "praviar_queue_oldest_task_age_seconds",
    "Oldest task age by queue name",
    ["queue"],
)

db_pool_saturation_gauge = Gauge(
    "praviar_db_pool_saturation",
    "Database pool saturation ratio by pool name",
    ["pool"],
)

export_duration_seconds = Histogram(
    "praviar_export_duration_seconds",
    "Export duration by format and status",
    ["format", "status"],
    buckets=[0.1, 0.5, 1, 2.5, 5, 10, 30, 60],
)

webhook_duration_seconds = Histogram(
    "praviar_webhook_duration_seconds",
    "Webhook handling duration by source and status",
    ["source", "status"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

checkpoint_decisions_total = Counter(
    "praviar_checkpoint_decisions_total",
    "Human checkpoint decisions by type and decision",
    ["checkpoint_type", "decision"],
)

chat_history_persist_failures_total = Counter(
    "praviar_chat_history_persist_failures_total",
    "Chat history persistence failures after successful provider call",
    [],
)

chat_citation_validation_failures_total = Counter(
    "praviar_chat_citation_validation_failures_total",
    "Governed chat responses blocked by the citation fail-closed gate",
    ["reason"],
)

# ---------------------------------------------------------------------------
# Stale-analysis reconciliation
# ---------------------------------------------------------------------------

stale_analysis_sweep_last_success_unixtime = Gauge(
    "praviar_stale_analysis_sweep_last_success_unixtime",
    "Unix timestamp of the last stale-analysis sweep that completed without errors",
)

stale_analysis_oldest_expired_running_age_seconds = Gauge(
    "praviar_stale_analysis_oldest_expired_running_age_seconds",
    "Oldest expired RUNNING analysis age observed by the latest reconciliation sweep",
)

stale_analysis_reclaimed_total = Counter(
    "praviar_stale_analysis_reclaimed_total",
    "Expired RUNNING analyses reclaimed by stale-analysis reconciliation",
)

stale_analysis_redrive_failures_total = Counter(
    "praviar_stale_analysis_redrive_failures_total",
    "Stale-analysis redrive dispatch failures",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


build_info = Gauge(
    "praviar_build_info",
    "Build information",
    ["version", "environment"],
)


def record_pipeline_run(status: str, execution_profile: str, duration_s: float) -> None:
    """Record a single pipeline completion.

    Args:
        status:     Outcome of the run -- one of ``completed``, ``failed``,
                    or ``cancelled``.
        execution_profile: Unified pipeline execution profile.
        duration_s: Wall-clock duration of the run in seconds.
    """
    pipeline_runs_total.labels(status=status, execution_profile=execution_profile).inc()
    pipeline_duration_seconds.labels(execution_profile=execution_profile).observe(duration_s)


def record_adaptive_escalation(stage: str, reasons: list[str]) -> None:
    for reason in reasons or ["unspecified"]:
        adaptive_escalations_total.labels(stage=stage, reason=reason).inc()


def record_evaluator_outcome(outcome: str) -> None:
    evaluator_outcomes_total.labels(outcome=outcome).inc()


def record_provider_call(
    *,
    provider: str,
    operation: str,
    duration_s: float,
    errored: bool = False,
) -> None:
    provider_latency_seconds.labels(provider=provider, operation=operation).observe(duration_s)
    if errored:
        provider_errors_total.labels(provider=provider, operation=operation).inc()


def record_checkpoint_decision(checkpoint_type: str, decision: str) -> None:
    checkpoint_decisions_total.labels(
        checkpoint_type=checkpoint_type,
        decision=decision,
    ).inc()


# ---------------------------------------------------------------------------
# Circuit breaker observability
# ---------------------------------------------------------------------------

circuit_breaker_state_gauge = Gauge(
    "praviar_circuit_breaker_state",
    "Circuit breaker state (1=active) per circuit and state label",
    ["circuit", "state"],
)

circuit_breaker_fast_fails_total = Counter(
    "praviar_circuit_breaker_fast_fails_total",
    "Requests fast-failed by an open circuit breaker",
    ["circuit"],
)

circuit_breaker_inflight_gauge = Gauge(
    "praviar_circuit_breaker_inflight",
    "Number of in-flight calls currently inside the bulkhead per circuit",
    ["circuit"],
)

circuit_breaker_probe_deadline_exceeded_total = Counter(
    "praviar_circuit_breaker_probe_deadline_exceeded_total",
    "Times a HALF_OPEN probe was assumed disconnected and replaced with a fresh probe",
    ["circuit"],
)

circuit_breaker_cancelled_total = Counter(
    "praviar_circuit_breaker_cancelled_total",
    "Calls cancelled by the client (GeneratorExit/CancelledError) while a "
    "HALF_OPEN probe was in-flight",
    ["circuit"],
)

http_retries_total = Counter(
    "praviar_http_retries_total",
    "Outbound HTTP retry attempts by caller and reason",
    # reason:
    #   status_code   — per-attempt retryable HTTP status (429/502/503/504)
    #   network_error — per-attempt network-layer transient (timeout/connect)
    #   exhausted     — terminal: all attempts consumed; call ultimately failed
    #   recovered     — terminal: a later attempt succeeded after ≥1 earlier failure
    ["caller", "reason"],
)

sso_sync_failures_total = Counter(
    "praviar_sso_sync_failures_total",
    "SSO status DB sync commit failures",
    [],
)

# ---------------------------------------------------------------------------
# SSE stream observability
# ---------------------------------------------------------------------------

sse_events_dropped_total = Counter(
    "praviar_sse_events_dropped_total",
    "SSE progress events dropped because the client queue was full",
)
