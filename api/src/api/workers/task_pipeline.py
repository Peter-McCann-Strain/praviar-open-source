"""Execution helpers for pipeline Celery tasks."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis
    import structlog
    from sqlalchemy.orm import Session

    from api.db.models import Analysis

from api.metrics import active_analyses_gauge, record_pipeline_run

DEFAULT_PIPELINE_LEASE_TTL_SECONDS = 40 * 60

# Total number of pipeline steps. Used in progress percentage calculations
# and in the final completion event so that all three sites stay in sync.
# Update this constant if the pipeline step count changes.
PIPELINE_TOTAL_STEPS = 8

PipelineExecutionResult = dict[str, str]


@dataclass(frozen=True)
class _PipelineExecutionClaim:
    execution_id: uuid.UUID


@dataclass
class _PipelineProgressController:
    db: Session
    analysis: Analysis
    analysis_id: str
    execution_id: uuid.UUID
    lease_ttl_seconds: int
    redis_client: redis.Redis
    lost_event_counts: dict[str, int]
    logger: structlog.stdlib.BoundLogger
    publish_event_fn: Callable[..., Any]
    is_cancelled_fn: Callable[..., bool]
    pipeline_event_model: Any
    cancelled_error: Callable[..., Exception]
    pending_events: list[Any] = field(default_factory=list)

    def cancellation_reason(self) -> str | None:
        self.db.refresh(self.analysis)
        if self.analysis.pipeline_execution_id != self.execution_id:
            return "execution_fence_lost"
        if self.is_cancelled_fn(self.analysis.status):
            return "analysis_cancelled"
        return None

    def should_cancel(self) -> bool:
        return self.cancellation_reason() is not None

    def renew_execution_lease(self) -> None:
        self.analysis.pipeline_lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=self.lease_ttl_seconds
        )

    def flush_events(self) -> None:
        if not self.pending_events:
            return
        for event in self.pending_events:
            self.db.add(event)
        self.pending_events.clear()
        self.db.commit()

    def discard_events(self) -> None:
        self.pending_events.clear()

    def on_progress(
        self,
        step_num: int,
        step_name: str,
        event_type: str,
        payload: dict,
    ) -> None:
        cancel_reason = self.cancellation_reason()
        if cancel_reason is not None:
            self._raise_progress_cancellation(
                cancel_reason=cancel_reason,
                step_num=step_num,
                step_name=step_name,
                event_type=event_type,
            )
        self._publish_progress(
            step_num=step_num,
            step_name=step_name,
            event_type=event_type,
            payload=payload,
        )
        self.pending_events.append(
            self.pipeline_event_model(
                analysis_id=self.analysis_id,
                step_number=step_num,
                step_name=step_name,
                event_type=event_type,
                payload=payload,
            )
        )
        self._update_progress_state(step_num=step_num, event_type=event_type)
        if event_type in {"started", "completed", "checkpoint", "review_required"}:
            self._flush_progress_boundary(
                step_num=step_num,
                step_name=step_name,
                event_type=event_type,
            )

    def _raise_progress_cancellation(
        self,
        *,
        cancel_reason: str,
        step_num: int,
        step_name: str,
        event_type: str,
    ) -> None:
        if cancel_reason == "execution_fence_lost":
            self.db.rollback()
            self.pending_events.clear()
        else:
            try:
                self.flush_events()
            except Exception as flush_exc:
                self.logger.error(
                    "pipeline_event_flush_failed_on_cancel",
                    step_num=step_num,
                    step_name=step_name,
                    event_type=event_type,
                    error_type=type(flush_exc).__name__,
                    exc_info=True,
                )
                self.db.rollback()
        raise self.cancelled_error(
            f"Analysis {self.analysis_id} stopped during {step_name}: {cancel_reason}",
            step=step_name,
        )

    def _publish_progress(
        self,
        *,
        step_num: int,
        step_name: str,
        event_type: str,
        payload: dict,
    ) -> None:
        try:
            self.publish_event_fn(
                self.redis_client,
                self.analysis_id,
                step_num,
                step_name,
                event_type,
                payload,
                lost_event_counts=self.lost_event_counts,
                logger=self.logger,
            )
        except Exception as publish_exc:
            self.logger.error(
                "progress_publish_failed",
                step_num=step_num,
                step_name=step_name,
                event_type=event_type,
                error_type=type(publish_exc).__name__,
                exc_info=True,
            )

    def _update_progress_state(self, *, step_num: int, event_type: str) -> None:
        if event_type == "started":
            self.analysis.current_step = step_num
            self.analysis.progress_pct = ((step_num - 1) / PIPELINE_TOTAL_STEPS) * 100
            self.renew_execution_lease()
        elif event_type == "completed":
            self.analysis.progress_pct = (step_num / PIPELINE_TOTAL_STEPS) * 100
            self.renew_execution_lease()
        elif event_type in {"checkpoint", "review_required"}:
            self.renew_execution_lease()

    def _flush_progress_boundary(
        self,
        *,
        step_num: int,
        step_name: str,
        event_type: str,
    ) -> None:
        try:
            self.flush_events()
        except Exception as commit_exc:
            self.logger.error(
                "progress_commit_failed",
                step_num=step_num,
                step_name=step_name,
                event_type=event_type,
                error_type=type(commit_exc).__name__,
                exc_info=True,
            )
            self.db.rollback()
            self.pending_events.clear()
            raise


def _claim_pipeline_execution(
    *,
    db: Session,
    analysis: Analysis,
    analysis_id: str,
    lease_ttl_seconds: int,
    expected_execution_id: uuid.UUID | None,
    provider_retry_attempt: int,
    logger: structlog.stdlib.BoundLogger,
    analysis_status: Any,
    classify_status_fn: Callable[..., str | None],
) -> _PipelineExecutionClaim | PipelineExecutionResult:
    db.refresh(analysis, with_for_update=True)
    lease_now = datetime.now(UTC)
    persisted_execution_id = getattr(analysis, "pipeline_execution_id", None)
    skip_status = classify_status_fn(
        analysis.status,
        getattr(analysis, "pipeline_lease_expires_at", None),
        now=lease_now,
    )
    retry_owns_active_fence = (
        skip_status == "already_running"
        and provider_retry_attempt > 0
        and expected_execution_id is not None
        and persisted_execution_id == expected_execution_id
    )
    if retry_owns_active_fence:
        logger.warning(
            "pipeline_provider_retry_adopting_active_fence",
            analysis_id=analysis_id,
            execution_id=str(expected_execution_id),
            provider_retry_attempt=provider_retry_attempt,
        )
        skip_status = None
    if skip_status is not None:
        db.rollback()
        logger.info(
            "pipeline_skipped_idempotent_analysis",
            analysis_id=analysis_id,
            status=str(analysis.status),
            skip_status=skip_status,
        )
        return {"status": skip_status, "analysis_id": analysis_id}
    if expected_execution_id is not None and persisted_execution_id != expected_execution_id:
        db.rollback()
        logger.info(
            "pipeline_skipped_stale_execution",
            analysis_id=analysis_id,
            expected_execution_id=str(expected_execution_id),
            persisted_execution_id=(
                str(persisted_execution_id) if persisted_execution_id is not None else None
            ),
        )
        return {"status": "stale_execution", "analysis_id": analysis_id}
    if expected_execution_id is None and persisted_execution_id is not None:
        db.rollback()
        logger.info(
            "pipeline_skipped_reserved_execution",
            analysis_id=analysis_id,
            persisted_execution_id=str(persisted_execution_id),
        )
        return {"status": "launch_reserved", "analysis_id": analysis_id}

    analysis.status = analysis_status.RUNNING
    analysis.current_step = 0
    analysis.progress_pct = 0.0
    execution_id = expected_execution_id or uuid.uuid4()
    analysis.pipeline_execution_id = execution_id
    analysis.pipeline_lease_expires_at = lease_now + timedelta(seconds=lease_ttl_seconds)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _PipelineExecutionClaim(execution_id=execution_id)


def _finish_pipeline_run(
    *,
    status: str,
    execution_profile: str,
    pipeline_start: float,
    measure_before_decrement: bool = False,
) -> float:
    elapsed = time.time() - pipeline_start if measure_before_decrement else 0.0
    active_analyses_gauge.dec()
    if not measure_before_decrement:
        elapsed = time.time() - pipeline_start
    record_pipeline_run(
        status=status,
        execution_profile=execution_profile,
        duration_s=elapsed,
    )
    return elapsed


def _handle_pipeline_runner_failure(
    *,
    controller: _PipelineProgressController,
    analysis_status: Any,
    execution_profile: str,
    pipeline_start: float,
) -> None:
    controller.discard_events()
    controller.db.rollback()
    try:
        controller.db.refresh(controller.analysis, with_for_update=True)
        if controller.analysis.pipeline_execution_id != controller.execution_id:
            controller.db.rollback()
        elif controller.analysis.status in (
            analysis_status.DELETED,
            analysis_status.CANCELLED,
        ):
            controller.analysis.pipeline_execution_id = None
            controller.analysis.pipeline_lease_expires_at = None
            controller.db.commit()
        else:
            controller.analysis.status = analysis_status.FAILED
            controller.analysis.pipeline_execution_id = None
            controller.analysis.pipeline_lease_expires_at = None
            controller.db.commit()
    except Exception as mark_exc:
        controller.db.rollback()
        controller.logger.error(
            "pipeline_mark_failed_write_error",
            analysis_id=str(controller.analysis.id),
            error=str(mark_exc),
            error_type=type(mark_exc).__name__,
            exc_info=True,
        )
    _finish_pipeline_run(
        status="failed",
        execution_profile=execution_profile,
        pipeline_start=pipeline_start,
    )


def _guard_pipeline_completion(
    *,
    controller: _PipelineProgressController,
    analysis_status: Any,
    execution_profile: str,
    pipeline_start: float,
) -> None:
    if controller.should_cancel():
        controller.discard_events()
        controller.db.rollback()
        _finish_pipeline_run(
            status="cancelled",
            execution_profile=execution_profile,
            pipeline_start=pipeline_start,
        )
        raise controller.cancelled_error(
            f"Analysis {controller.analysis_id} cancelled before completion write",
            step="report",
        )
    controller.db.refresh(controller.analysis, with_for_update=True)
    if controller.analysis.pipeline_execution_id != controller.execution_id:
        controller.discard_events()
        controller.db.rollback()
        _finish_pipeline_run(
            status="cancelled",
            execution_profile=execution_profile,
            pipeline_start=pipeline_start,
        )
        raise controller.cancelled_error(
            f"Analysis {controller.analysis_id} zombie worker: execution-id mismatch, aborting",
            step="report",
        )
    if controller.analysis.status in (
        analysis_status.DELETED,
        analysis_status.CANCELLED,
    ):
        controller.discard_events()
        controller.analysis.pipeline_execution_id = None
        controller.analysis.pipeline_lease_expires_at = None
        controller.db.commit()
        _finish_pipeline_run(
            status="cancelled",
            execution_profile=execution_profile,
            pipeline_start=pipeline_start,
        )
        raise controller.cancelled_error(
            f"Analysis {controller.analysis_id} reached terminal status "
            f"{controller.analysis.status.value!r} before completion write",
            step="report",
        )


def _downgrade_replaced_report_approval(db: Session, analysis: Analysis) -> None:
    if not getattr(analysis, "flagged_for_review", False):
        return
    from sqlalchemy import select as sa_select

    from api.db.models import AnalysisReviewStatus, ReviewStatus

    review_status = db.execute(
        sa_select(AnalysisReviewStatus)
        .where(
            AnalysisReviewStatus.analysis_id == analysis.id,
            AnalysisReviewStatus.org_id == analysis.org_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if review_status is not None and review_status.status == ReviewStatus.APPROVED:
        review_status.status = ReviewStatus.CHANGES_REQUESTED
        review_status.note = (
            "Approval reverted: analysis report replaced by a re-run and has not been re-reviewed."
        )


def _persist_pipeline_completion(
    *,
    controller: _PipelineProgressController,
    report_dict: dict[str, Any],
    pipeline_start: float,
    execution_profile: str,
    store_pipeline_results_fn: Callable[..., None],
    upsert_compound_fn: Callable[..., None],
    write_audit_fn: Callable[..., None] | None,
    analysis_status: Any,
) -> None:
    try:
        controller.flush_events()
        controller.analysis.status = analysis_status.COMPLETED
        controller.analysis.completed_at = datetime.now(UTC)
        controller.analysis.pipeline_execution_id = None
        controller.analysis.pipeline_lease_expires_at = None
        _bind_report_certification(controller.analysis, report_dict)
        store_pipeline_results_fn(
            controller.analysis,
            report_dict,
            time.time() - pipeline_start,
        )
        _downgrade_replaced_report_approval(controller.db, controller.analysis)
        upsert_compound_fn(
            controller.db,
            report_dict.get("compound", {}),
            org_id=controller.analysis.org_id,
            completed_at=controller.analysis.completed_at,
        )
        if write_audit_fn is not None:
            write_audit_fn(controller.db, controller.analysis)
        controller.db.commit()
    except Exception:
        controller.discard_events()
        controller.db.rollback()
        _finish_pipeline_run(
            status="failed",
            execution_profile=execution_profile,
            pipeline_start=pipeline_start,
        )
        raise


def _bind_report_certification(analysis: Analysis, report_dict: dict[str, Any]) -> None:
    from praviar_pipeline.report_certification_binding import (
        REPORT_BINDING_FIELD,
        ReportCertificationSigner,
        sign_report_certification_binding,
    )

    from api.config import get_settings

    report_dict[REPORT_BINDING_FIELD] = sign_report_certification_binding(
        report_dict,
        signer=ReportCertificationSigner.from_secret(
            get_settings().report_certification_signing_keyring_secret.get_secret_value()
        ),
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
    )


def _dispatch_faithfulness_uq(
    *,
    analysis: Analysis,
    analysis_id: str,
    run_async_fn: Callable[..., Any],
    logger: structlog.stdlib.BoundLogger,
) -> None:
    try:
        from api.services.faithfulness_uq import is_feature_enabled

        if is_feature_enabled():
            from api.services.task_dispatcher import build_dispatcher

            run_async_fn(
                build_dispatcher().dispatch_faithfulness_scores(
                    analysis_id=str(analysis.id),
                    org_id=str(analysis.org_id),
                )
            )
            logger.info(
                "faithfulness_uq_dispatched",
                analysis_id=analysis_id,
            )
    except Exception:
        logger.warning(
            "faithfulness_uq_dispatch_failed",
            analysis_id=analysis_id,
            exc_info=True,
        )


def _record_lost_pipeline_events(
    *,
    analysis_id: str,
    lost_events: int,
    logger: structlog.stdlib.BoundLogger,
) -> None:
    if lost_events <= 0:
        return
    logger.warning(
        "pipeline_degraded_observability",
        analysis_id=analysis_id,
        lost_event_count=lost_events,
    )
    try:
        from api.metrics import sse_events_dropped_total

        sse_events_dropped_total.inc(lost_events)
    except Exception:
        logger.warning(
            "pipeline_sse_metric_record_failed",
            analysis_id=analysis_id,
            lost_event_count=lost_events,
            exc_info=True,
        )


def _publish_pipeline_completion(
    *,
    analysis: Analysis,
    analysis_id: str,
    redis_client: redis.Redis,
    lost_event_counts: dict[str, int],
    logger: structlog.stdlib.BoundLogger,
    publish_event_fn: Callable[..., Any],
) -> None:
    lost_events = lost_event_counts.pop(analysis_id, 0)
    publish_event_fn(
        redis_client,
        analysis_id,
        PIPELINE_TOTAL_STEPS,
        "report",
        "completed",
        {
            "overall_risk": analysis.overall_risk,
            "duration": analysis.pipeline_duration_seconds,
            "lost_events": lost_events,
        },
        lost_event_counts=lost_event_counts,
        logger=logger,
    )
    _record_lost_pipeline_events(
        analysis_id=analysis_id,
        lost_events=lost_events,
        logger=logger,
    )
    logger.info(
        "pipeline_completed",
        analysis_id=analysis_id,
        risk=analysis.overall_risk,
        duration=analysis.pipeline_duration_seconds,
        lost_events=lost_events,
    )


def run_pipeline_execution(
    *,
    db: Session,
    analysis: Analysis,
    analysis_id: str,
    pipeline_start: float,
    execution_profile: str = "world_class_adaptive",
    redis_client: redis.Redis,
    lost_event_counts: dict[str, int],
    logger: structlog.stdlib.BoundLogger,
    publish_event_fn: Callable[..., Any],
    is_cancelled_fn: Callable[..., bool],
    store_pipeline_results_fn: Callable[..., None],
    upsert_compound_fn: Callable[..., None],
    run_async_fn: Callable[..., Any],
    pipeline_runner_factory: Callable[..., Any],
    log_output_dir_fn: Callable[..., None],
    write_audit_fn: Callable[..., None] | None = None,
    lease_ttl_seconds: int = DEFAULT_PIPELINE_LEASE_TTL_SECONDS,
    expected_execution_id: uuid.UUID | None = None,
    provider_retry_attempt: int = 0,
) -> PipelineExecutionResult:
    from praviar_pipeline.errors import PipelineCancelledError

    from api.db.models import AnalysisStatus, PipelineEvent
    from api.workers.task_state import classify_pipeline_execution_status

    claim = _claim_pipeline_execution(
        db=db,
        analysis=analysis,
        analysis_id=analysis_id,
        lease_ttl_seconds=lease_ttl_seconds,
        expected_execution_id=expected_execution_id,
        provider_retry_attempt=provider_retry_attempt,
        logger=logger,
        analysis_status=AnalysisStatus,
        classify_status_fn=classify_pipeline_execution_status,
    )
    if isinstance(claim, dict):
        return claim

    active_analyses_gauge.inc()
    controller = _PipelineProgressController(
        db=db,
        analysis=analysis,
        analysis_id=analysis_id,
        execution_id=claim.execution_id,
        lease_ttl_seconds=lease_ttl_seconds,
        redis_client=redis_client,
        lost_event_counts=lost_event_counts,
        logger=logger,
        publish_event_fn=publish_event_fn,
        is_cancelled_fn=is_cancelled_fn,
        pipeline_event_model=PipelineEvent,
        cancelled_error=PipelineCancelledError,
    )
    try:
        report_dict = run_async_fn(
            pipeline_runner_factory(controller.on_progress, controller.should_cancel)
        )
    except Exception:
        _handle_pipeline_runner_failure(
            controller=controller,
            analysis_status=AnalysisStatus,
            execution_profile=execution_profile,
            pipeline_start=pipeline_start,
        )
        raise

    _guard_pipeline_completion(
        controller=controller,
        analysis_status=AnalysisStatus,
        execution_profile=execution_profile,
        pipeline_start=pipeline_start,
    )
    _persist_pipeline_completion(
        controller=controller,
        report_dict=report_dict,
        pipeline_start=pipeline_start,
        execution_profile=execution_profile,
        store_pipeline_results_fn=store_pipeline_results_fn,
        upsert_compound_fn=upsert_compound_fn,
        write_audit_fn=write_audit_fn,
        analysis_status=AnalysisStatus,
    )
    _finish_pipeline_run(
        status="completed",
        execution_profile=execution_profile,
        pipeline_start=pipeline_start,
        measure_before_decrement=True,
    )
    _dispatch_faithfulness_uq(
        analysis=analysis,
        analysis_id=analysis_id,
        run_async_fn=run_async_fn,
        logger=logger,
    )
    log_output_dir_fn(analysis_id=analysis_id, logger=logger)
    _publish_pipeline_completion(
        analysis=analysis,
        analysis_id=analysis_id,
        redis_client=redis_client,
        lost_event_counts=lost_event_counts,
        logger=logger,
        publish_event_fn=publish_event_fn,
    )
    return {"status": "completed", "analysis_id": analysis_id}
