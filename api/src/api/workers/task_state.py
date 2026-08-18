"""State and failure helpers for worker Celery tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis

from api.db.models import AnalysisStatus
from api.workers import task_persistence

MAX_PERSISTED_FAILURE_MESSAGE_CHARS = 2000


def _coerce_analysis_status(status) -> AnalysisStatus:  # noqa: ANN001
    try:
        return status if isinstance(status, AnalysisStatus) else AnalysisStatus(status)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported analysis status: {status!r}") from exc


def publish_pipeline_event(
    redis_client: redis.Redis,
    analysis_id: str,
    step: int,
    step_name: str,
    event_type: str,
    payload: dict | None = None,
    *,
    lost_event_counts: dict[str, int],
    logger,
) -> None:
    """Publish a pipeline event to Redis PubSub."""
    event = {
        "step": step,
        "step_name": step_name,
        "type": event_type,
        "payload": payload or {},
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        redis_client.publish(f"analysis:{analysis_id}", json.dumps(event))
    except redis.RedisError as exc:
        lost_event_counts[analysis_id] = lost_event_counts.get(analysis_id, 0) + 1
        logger.error(
            "redis_publish_failed",
            analysis_id=analysis_id,
            step=step,
            step_name=step_name,
            event_type=event_type,
            error=str(exc),
            lost_event_count=lost_event_counts[analysis_id],
            exc_info=True,
        )


def is_cancelled(status) -> bool:  # noqa: ANN001
    return status in {AnalysisStatus.CANCELLED, AnalysisStatus.DELETED}


def is_pipeline_terminal(status) -> bool:  # noqa: ANN001
    normalized_status = _coerce_analysis_status(status)
    return normalized_status in {
        AnalysisStatus.COMPLETED,
        AnalysisStatus.CANCELLED,
        AnalysisStatus.DELETED,
    }


def classify_pipeline_execution_status(
    status,  # noqa: ANN001
    lease_expires_at: datetime | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Return an idempotent skip status, or ``None`` when execution may start."""
    normalized_status = _coerce_analysis_status(status)
    if normalized_status == AnalysisStatus.COMPLETED:
        return "already_completed"
    if normalized_status == AnalysisStatus.FAILED:
        # Terminal: a prior run already wrote a failure (or the stale-analysis
        # sweep expired it).  Late Cloud Task retries must not reopen it.
        return "already_failed"
    if normalized_status == AnalysisStatus.CANCELLED:
        return "cancelled"
    if normalized_status == AnalysisStatus.DELETED:
        return "deleted"
    if normalized_status != AnalysisStatus.RUNNING:
        return None

    if lease_expires_at is None:
        return "already_running"
    if lease_expires_at.tzinfo is None:
        raise ValueError("pipeline_lease_expires_at must be timezone-aware")

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if lease_expires_at > current_time:
        return "already_running"
    return None


def store_pipeline_results(analysis, report_dict: dict, duration: float) -> None:
    task_persistence.store_pipeline_results_impl(analysis, report_dict, duration)


def write_analysis_completed_audit(db, analysis) -> None:  # noqa: ANN001
    task_persistence.write_analysis_completed_audit_impl(db, analysis)


def upsert_compound(  # noqa: ANN001
    db,
    compound: dict,
    *,
    org_id,
    completed_at,
) -> None:
    task_persistence.upsert_compound_impl(
        db,
        compound,
        org_id=org_id,
        completed_at=completed_at,
    )


def log_output_dir(*, analysis_id: str, logger) -> None:
    try:
        from praviar_pipeline.config import get_settings as get_sg_settings

        sg_output_dir = get_sg_settings().resolved_output_dir
        logger.info(
            "pipeline_output_dir",
            analysis_id=analysis_id,
            output_dir=str(sg_output_dir),
        )
    except Exception:
        logger.debug("could_not_resolve_praviar_pipeline_output_dir", exc_info=True)


def persist_pipeline_cancellation(db, analysis, duration: float) -> None:  # noqa: ANN001
    if analysis:
        # A non-None execution_id on a RUNNING analysis means a different worker
        # has reclaimed the slot since this outer handler opened its session.
        # The inner run_pipeline_execution handler always clears execution_id
        # before re-raising in every case except the execution-id mismatch
        # (zombie worker) path — so a non-None id here is the reclaim signal.
        # Do not overwrite the new worker's state.
        if analysis.status == AnalysisStatus.RUNNING and analysis.pipeline_execution_id is not None:
            return
        if analysis.status != AnalysisStatus.DELETED:
            analysis.status = AnalysisStatus.CANCELLED
            analysis.pipeline_duration_seconds = duration
        analysis.pipeline_execution_id = None
        analysis.pipeline_lease_expires_at = None
        db.commit()


def persist_pipeline_failure(
    db,
    analysis,
    duration: float,
    tb: str,
    exc: Exception | None = None,
) -> None:  # noqa: ANN001
    if analysis:
        # Do not resurrect a record that has already reached a user- or
        # compliance-driven terminal state. A pipeline crash that races a
        # concurrent soft-delete (status -> DELETED, e.g. GDPR Art. 17
        # erasure in offboarding) or an explicit cancellation (status ->
        # CANCELLED) must not overwrite that status with FAILED — doing so
        # would make an erased/cancelled analysis visible again in list
        # queries (which filter status != DELETED) and would re-expose a
        # record the operator intended to retire. Only the lease/execution
        # bookkeeping is cleared in that case so the row is no longer held.
        if analysis.status in (AnalysisStatus.DELETED, AnalysisStatus.CANCELLED):
            analysis.pipeline_execution_id = None
            analysis.pipeline_lease_expires_at = None
            db.commit()
            return
        # Same reclaim guard as persist_pipeline_cancellation: a non-None
        # execution_id on a RUNNING row signals a different worker holds the
        # lease. Do not clobber the new worker's state.
        if analysis.status == AnalysisStatus.RUNNING and analysis.pipeline_execution_id is not None:
            return
        analysis.status = AnalysisStatus.FAILED
        analysis.error_message = _build_persisted_failure_message(exc, tb)
        analysis.pipeline_duration_seconds = duration
        analysis.pipeline_execution_id = None
        analysis.pipeline_lease_expires_at = None
        db.commit()


def _build_persisted_failure_message(exc: Exception | None, tb: str) -> str:
    """Return a bounded tenant-safe failure summary for Analysis.error_message."""
    if exc is None:
        message = "Pipeline failed. See worker logs for traceback."
    else:
        error_type = type(exc).__name__
        message = f"Pipeline failed: {error_type}. See worker logs for scrubbed diagnostics."

    if "\n" in message or "\r" in message:
        message = " ".join(message.split())
    if not message:
        message = "Pipeline failed. See worker logs for traceback."
    return message[:MAX_PERSISTED_FAILURE_MESSAGE_CHARS]
