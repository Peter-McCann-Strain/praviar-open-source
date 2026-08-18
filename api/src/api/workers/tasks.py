"""Celery tasks for pipeline execution and exports."""

from __future__ import annotations

import asyncio
import atexit
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import redis
import structlog
from sqlalchemy.orm import Session

from api.workers import task_exports, task_pipeline, task_runtime, task_state
from api.workers.celery_app import celery_app, run_async

logger = structlog.get_logger()

_sync_engine = None


def _get_sync_engine():
    """Return a module-level sync engine (cached to avoid per-task pool leak)."""
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine

        from api.config import get_settings

        settings = get_settings()
        sync_url = settings.database_url.replace("+asyncpg", "")
        _sync_engine = create_engine(
            sync_url,
            pool_size=settings.worker_db_pool_size,
            max_overflow=settings.worker_db_max_overflow,
            pool_timeout=settings.worker_db_pool_timeout,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            },
        )
    return _sync_engine


def _dispose_sync_engine() -> None:
    """Dispose sync engine on process exit."""
    global _sync_engine
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None


atexit.register(_dispose_sync_engine)


_lost_event_counts: dict[str, int] = {}

analysis_step_name_map: dict[int, str] = {
    1: "input",
    2: "search",
    3: "triage",
    4: "critic",
    5: "doe",
    6: "invalidity",
    7: "verify",
    8: "report",
}

EXTERNAL_REPORT_DELIVERY_RECONCILIATION_BATCH_SIZE = 20
EXTERNAL_REPORT_DELIVERY_RECONCILIATION_BUDGET_SECONDS = 210.0
EXTERNAL_REPORT_DELIVERY_RECONCILIATION_LEASE_TTL = timedelta(minutes=5)


class ExternalReportDeliveryReconciliationLeaseUnavailableError(RuntimeError):
    """Make Cloud Tasks retry instead of acknowledging a continuation too early."""


async def _acquire_external_report_delivery_reconciliation_lease(
    db,
    *,
    org_id: uuid.UUID,
    lease_id: uuid.UUID,
    now: datetime,
) -> bool:
    """Acquire or renew one durable tenant lease under the organization lock."""
    from sqlalchemy import select

    from api.db.models import Organization

    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        raise RuntimeError(f"Organization {org_id} does not exist")
    current_lease_id = organization.external_report_delivery_reconciliation_lease_id
    current_expiry = organization.external_report_delivery_reconciliation_lease_expires_at
    if (
        current_lease_id is not None
        and current_lease_id != lease_id
        and current_expiry is not None
        and current_expiry > now
    ):
        await db.commit()
        return False
    organization.external_report_delivery_reconciliation_lease_id = lease_id
    organization.external_report_delivery_reconciliation_lease_expires_at = (
        now + EXTERNAL_REPORT_DELIVERY_RECONCILIATION_LEASE_TTL
    )
    await db.commit()
    return True


async def _release_external_report_delivery_reconciliation_lease(
    db,
    *,
    org_id: uuid.UUID,
    lease_id: uuid.UUID,
) -> None:
    """Release only the lease owned by this task; never erase a successor lease."""
    from sqlalchemy import select

    from api.db.models import Organization

    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    organization = result.scalar_one_or_none()
    if (
        organization is not None
        and organization.external_report_delivery_reconciliation_lease_id == lease_id
    ):
        organization.external_report_delivery_reconciliation_lease_id = None
        organization.external_report_delivery_reconciliation_lease_expires_at = None
    await db.commit()


async def _external_report_delivery_reconciliation_lease_is_current(
    db,
    *,
    org_id: uuid.UUID,
    lease_id: uuid.UUID,
    now: datetime,
) -> bool:
    """Fence continuation dispatch as well as database writes."""
    from sqlalchemy import select

    from api.db.models import Organization

    result = await db.execute(
        select(Organization)
        .where(
            Organization.id == org_id,
            Organization.external_report_delivery_reconciliation_lease_id == lease_id,
            Organization.external_report_delivery_reconciliation_lease_expires_at > now,
        )
        .with_for_update()
    )
    organization = result.scalar_one_or_none()
    current = organization is not None
    if organization is not None:
        organization.external_report_delivery_reconciliation_lease_expires_at = (
            now + EXTERNAL_REPORT_DELIVERY_RECONCILIATION_LEASE_TTL
        )
    await db.commit()
    return current


async def _reconcile_external_report_deliveries_for_org(
    org_id: str,
    *,
    dedupe_key: str | None = None,
    continuation: int = 0,
) -> dict[str, Any]:
    from api.db.session import async_session_factory, bind_current_org_to_session
    from api.services.external_report_grants import reconcile_external_report_deliveries
    from api.services.task_dispatcher import build_dispatcher

    parsed_org_id = uuid.UUID(org_id)
    resolved_dedupe_key = dedupe_key or f"celery-{parsed_org_id}-{uuid.uuid4().hex}"
    lease_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"praviar:external-report-delivery-reconciliation:{resolved_dedupe_key}",
    )
    async with async_session_factory() as db:
        await bind_current_org_to_session(db, parsed_org_id)
        acquired = await _acquire_external_report_delivery_reconciliation_lease(
            db,
            org_id=parsed_org_id,
            lease_id=lease_id,
            now=datetime.now(UTC),
        )
        if not acquired:
            raise ExternalReportDeliveryReconciliationLeaseUnavailableError(
                f"Delivery reconciliation lease is active for organization {parsed_org_id}"
            )
        counts = await reconcile_external_report_deliveries(
            db,
            org_id=parsed_org_id,
            reconciliation_lease_id=lease_id,
            batch_size=EXTERNAL_REPORT_DELIVERY_RECONCILIATION_BATCH_SIZE,
            time_budget_seconds=EXTERNAL_REPORT_DELIVERY_RECONCILIATION_BUDGET_SECONDS,
        )
        continuation_dispatched = False
        lease_is_current = await _external_report_delivery_reconciliation_lease_is_current(
            db,
            org_id=parsed_org_id,
            lease_id=lease_id,
            now=datetime.now(UTC),
        )
        if not lease_is_current:
            raise ExternalReportDeliveryReconciliationLeaseUnavailableError(
                f"Delivery reconciliation lease expired for organization {parsed_org_id}"
            )
        if counts["has_more"]:
            next_continuation = continuation + 1
            next_dedupe_key = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"praviar:external-report-delivery-reconciliation:"
                f"{resolved_dedupe_key}:{next_continuation}",
            ).hex
            await build_dispatcher().dispatch_external_report_delivery_reconciliation(
                org_id=str(parsed_org_id),
                dedupe_key=next_dedupe_key,
                continuation=next_continuation,
            )
            continuation_dispatched = True
        await _release_external_report_delivery_reconciliation_lease(
            db,
            org_id=parsed_org_id,
            lease_id=lease_id,
        )
        return {
            **counts,
            "lease_acquired": True,
            "continuation_dispatched": continuation_dispatched,
        }


async def _dispatch_external_report_delivery_reconciliation_async(
    *,
    cursor: str | None = None,
    sweep_id: str | None = None,
) -> dict[str, int | str | bool | None]:
    """Dispatch one bounded page and persist progress as a Cloud Task continuation."""
    from sqlalchemy import and_, or_, select

    from api.db.models import ExternalReportGrant
    from api.db.session import async_session_factory
    from api.services.external_report_grants import DELIVERY_DISPATCH_TIMEOUT
    from api.services.task_dispatcher import build_dispatcher
    from api.workers.monitor_tasks import _assert_worker_has_bypassrls

    page_size = 100
    dispatch_concurrency = 16
    now = datetime.now(UTC)
    resolved_sweep_id = sweep_id or f"{now:%Y%m%d%H}-{now.minute // 15:02d}"
    dispatcher = build_dispatcher()
    semaphore = asyncio.Semaphore(dispatch_concurrency)
    parsed_cursor = uuid.UUID(cursor) if cursor else None

    async def dispatch_one(org_id: uuid.UUID) -> str:
        async with semaphore:
            return await dispatcher.dispatch_external_report_delivery_reconciliation(
                org_id=str(org_id),
                dedupe_key=f"{org_id}-{resolved_sweep_id}",
            )

    async with async_session_factory() as discovery_db:
        await _assert_worker_has_bypassrls(discovery_db)
        statement = (
            select(ExternalReportGrant.org_id)
            .where(
                or_(
                    ExternalReportGrant.delivery_state == "provider_accepted",
                    and_(
                        ExternalReportGrant.delivery_state == "prepared",
                        ExternalReportGrant.expires_at <= now,
                    ),
                    and_(
                        ExternalReportGrant.delivery_state == "dispatching",
                        or_(
                            ExternalReportGrant.expires_at <= now,
                            ExternalReportGrant.delivery_dispatch_started_at.is_(None),
                            ExternalReportGrant.delivery_dispatch_started_at
                            <= now - DELIVERY_DISPATCH_TIMEOUT,
                        ),
                    ),
                    and_(
                        ExternalReportGrant.delivery_state == "outcome_unknown",
                        or_(
                            ExternalReportGrant.expires_at <= now,
                            ExternalReportGrant.delivery_reconciliation_next_attempt_at.is_(None),
                            ExternalReportGrant.delivery_reconciliation_next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        ExternalReportGrant.delivery_state.in_(("active", "rejected", "cancelled")),
                        ExternalReportGrant.delivery_token_ciphertext.is_not(None),
                    ),
                ),
            )
            .distinct()
            .order_by(ExternalReportGrant.org_id.asc())
            .limit(page_size + 1)
        )
        if parsed_cursor is not None:
            statement = statement.where(ExternalReportGrant.org_id > parsed_cursor)
        result = await discovery_db.execute(statement)
        discovered = tuple(result.scalars().all())
        await discovery_db.commit()

    org_ids = discovered[:page_size]
    await asyncio.gather(*(dispatch_one(org_id) for org_id in org_ids))
    has_more = len(discovered) > page_size
    next_cursor = str(org_ids[-1]) if has_more and org_ids else None
    if next_cursor is not None:
        await dispatcher.dispatch_external_report_delivery_reconciliation_sweep(
            cursor=next_cursor,
            sweep_id=resolved_sweep_id,
            dedupe_key=f"{resolved_sweep_id}-{next_cursor}",
        )

    return {
        "organizations": len(org_ids),
        "tasks_dispatched": len(org_ids),
        "continuation_dispatched": next_cursor is not None,
        "next_cursor": next_cursor,
        "sweep_id": resolved_sweep_id,
        "dispatch_concurrency": dispatch_concurrency,
    }


def execute_external_report_delivery_reconciliation() -> dict[str, int | str | bool | None]:
    """Synchronous entrypoint for Cloud Scheduler's internal worker route."""
    return cast(
        dict[str, int | str | bool | None],
        run_async(_dispatch_external_report_delivery_reconciliation_async()),
    )


@celery_app.task(max_retries=0)
def dispatch_external_report_delivery_reconciliation_sweep(
    cursor: str,
    sweep_id: str,
) -> dict[str, int | str | bool | None]:
    """Run one bounded continuation page in the local Celery backend."""
    return cast(
        dict[str, int | str | bool | None],
        run_async(
            _dispatch_external_report_delivery_reconciliation_async(
                cursor=cursor,
                sweep_id=sweep_id,
            )
        ),
    )


@celery_app.task(max_retries=0)
def reconcile_external_report_deliveries_for_org(
    org_id: str,
    dedupe_key: str | None = None,
    continuation: int = 0,
) -> dict[str, Any]:
    """Recover accepted invitations; never retry ambiguous provider submits."""
    return cast(
        dict[str, Any],
        run_async(
            _reconcile_external_report_deliveries_for_org(
                org_id,
                dedupe_key=dedupe_key,
                continuation=continuation,
            )
        ),
    )


def _build_checkpoint_decision_provider(*, runtime, analysis_id: str, org_id: str):
    """Return a storage-backed provider for pipeline HITL checkpoints."""

    def _provider(checkpoint_type, context):  # noqa: ANN001
        checkpoint_id = str(context.get("checkpoint_id", "")).strip()
        if not checkpoint_id:
            return None

        from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType

        from api.db.models import AnalysisCheckpointDecision
        from api.db.session import bind_org_to_sync_session

        with Session(runtime.engine) as decision_db:
            bind_org_to_sync_session(decision_db, org_id)
            decision = (
                decision_db.query(AnalysisCheckpointDecision)
                .filter(
                    AnalysisCheckpointDecision.analysis_id == uuid.UUID(str(analysis_id)),
                    AnalysisCheckpointDecision.org_id == uuid.UUID(str(org_id)),
                    AnalysisCheckpointDecision.checkpoint_id == checkpoint_id,
                )
                .one_or_none()
            )
            if decision is None:
                return None
            expected_type = getattr(checkpoint_type, "value", str(checkpoint_type))
            if str(decision.checkpoint_type) != expected_type:
                return None
            if expected_type == "report_review" and str(decision.decision) == "approve":
                from api.schemas.checkpoint_decisions import (
                    REPORT_REVIEW_CHECKPOINT_ID,
                    report_review_attestation_note,
                )

                review_payload_sha256 = str(context.get("review_payload_sha256", "")).strip()
                checkpoint_match = REPORT_REVIEW_CHECKPOINT_ID.fullmatch(checkpoint_id)
                if (
                    len(review_payload_sha256) != 64
                    or any(
                        character not in "0123456789abcdef" for character in review_payload_sha256
                    )
                    or checkpoint_match is None
                    or checkpoint_match.group("digest_prefix") != review_payload_sha256[:16]
                    or str(decision.note) != report_review_attestation_note(review_payload_sha256)
                ):
                    return None
            return CheckpointDecision(
                checkpoint_type=CheckpointType(str(decision.checkpoint_type)),
                action=str(decision.decision),
                reviewer_id=str(decision.reviewer_id),
                reviewed_at=decision.reviewed_at,
                notes=decision.note,
            )

    return _provider


@celery_app.task(
    bind=True,
    max_retries=1,
    autoretry_for=(ConnectionError,),
    retry_kwargs={"countdown": 30},
)
def run_fto_pipeline(self, analysis_id: str, org_id: str) -> dict:
    """Execute the Praviar Pipeline FTO pipeline with progress callbacks."""
    return execute_fto_pipeline(
        analysis_id=analysis_id,
        org_id=org_id,
        attempt=self.request.retries + 1,
    )


def execute_fto_pipeline(
    *,
    analysis_id: str,
    org_id: str,
    attempt: int = 1,
    execution_id: str | None = None,
    provider_retry_attempt: int = 0,
) -> dict:
    """Execute a pipeline run outside Celery.

    Celery remains a local/dev dispatcher. Production Cloud Run Jobs pass the
    persisted execution ID so stale or duplicate Job executions cannot claim
    a newer reservation.
    """
    from praviar_pipeline.errors import PipelineCancelledError

    from api.config import get_settings

    settings = get_settings()
    runtime = task_runtime.build_pipeline_runtime(
        get_settings_fn=lambda: settings,
        redis_from_url=redis.from_url,
        get_sync_engine_fn=_get_sync_engine,
    )
    lease_ttl_seconds = max(settings.celery_hard_time_limit, settings.sse_max_stream_seconds) + 300
    pipeline_start = time.time()

    logger.info(
        "pipeline_starting",
        analysis_id=analysis_id,
        attempt=attempt,
        org_id=org_id,
    )

    try:
        with Session(runtime.engine) as db:
            from api.db.models import Analysis
            from api.db.session import bind_org_to_sync_session

            bind_org_to_sync_session(db, org_id)
            analysis = db.get(Analysis, analysis_id)
            if analysis is None:
                logger.error("analysis_not_found", id=analysis_id)
                return {"status": "not_found"}
            if org_id is not None and str(analysis.org_id) != str(org_id):
                logger.error(
                    "pipeline_task_org_mismatch",
                    analysis_id=analysis_id,
                    expected_org_id=org_id,
                    actual_org_id=str(analysis.org_id),
                )
                return {"status": "org_mismatch"}

            config = analysis.config or {}
            compound_input = analysis.compound_input

            def _run_pipeline(on_progress, should_cancel):
                from praviar_pipeline.run import run_pipeline

                return run_pipeline(
                    compound_input,
                    on_progress=on_progress,
                    should_cancel=should_cancel,
                    config_overrides=config,
                    checkpoint_decision_provider=_build_checkpoint_decision_provider(
                        runtime=runtime,
                        analysis_id=analysis_id,
                        org_id=org_id,
                    ),
                )

            return task_pipeline.run_pipeline_execution(
                db=db,
                analysis=analysis,
                analysis_id=analysis_id,
                pipeline_start=pipeline_start,
                execution_profile="world_class_adaptive",
                redis_client=runtime.redis_client,
                lost_event_counts=_lost_event_counts,
                logger=logger,
                publish_event_fn=task_state.publish_pipeline_event,
                is_cancelled_fn=task_state.is_cancelled,
                store_pipeline_results_fn=task_state.store_pipeline_results,
                upsert_compound_fn=task_state.upsert_compound,
                run_async_fn=run_async,
                pipeline_runner_factory=_run_pipeline,
                log_output_dir_fn=task_state.log_output_dir,
                write_audit_fn=task_state.write_analysis_completed_audit,
                lease_ttl_seconds=int(lease_ttl_seconds),
                expected_execution_id=(
                    uuid.UUID(execution_id) if execution_id is not None else None
                ),
                provider_retry_attempt=provider_retry_attempt,
            )

    except PipelineCancelledError as exc:
        duration = time.time() - pipeline_start
        task_state.publish_pipeline_event(
            runtime.redis_client,
            analysis_id,
            0,
            "cancelled",
            "cancelled",
            {"message": str(exc), "cancelled": True},
            lost_event_counts=_lost_event_counts,
            logger=logger,
        )
        try:
            with Session(runtime.engine) as db:
                from sqlalchemy import select as _sa_select

                from api.db.models import Analysis
                from api.db.session import bind_org_to_sync_session

                bind_org_to_sync_session(db, org_id)
                analysis = db.execute(
                    _sa_select(Analysis).where(Analysis.id == analysis_id).with_for_update()
                ).scalar_one_or_none()
                task_state.persist_pipeline_cancellation(db, analysis, duration)
        except Exception:
            logger.exception("failed_to_persist_cancellation", analysis_id=analysis_id)
        logger.info(
            "pipeline_cancelled",
            analysis_id=analysis_id,
            duration_seconds=round(duration, 2),
        )
        return {"status": "cancelled", "analysis_id": analysis_id}
    except Exception as exc:
        duration = time.time() - pipeline_start
        lost_events = _lost_event_counts.pop(analysis_id, 0)
        logger.error(
            "pipeline_failed",
            analysis_id=analysis_id,
            error_type=type(exc).__name__,
            duration_seconds=round(duration, 2),
            lost_events=lost_events,
        )
        _failing_step = 0
        _failing_step_name = "error"
        try:
            with Session(runtime.engine) as db:
                from sqlalchemy import select as _sa_select

                from api.db.models import Analysis
                from api.db.session import bind_org_to_sync_session

                bind_org_to_sync_session(db, org_id)
                analysis = db.execute(
                    _sa_select(Analysis).where(Analysis.id == analysis_id).with_for_update()
                ).scalar_one_or_none()
                if analysis is not None:
                    _failing_step = analysis.current_step or 0
                    _failing_step_name = analysis_step_name_map.get(_failing_step, "unknown")
                task_state.persist_pipeline_failure(db, analysis, duration, "", exc=exc)
        except Exception:
            logger.exception(
                "failed_to_update_status",
                analysis_id=analysis_id,
            )
        task_state.publish_pipeline_event(
            runtime.redis_client,
            analysis_id,
            _failing_step,
            _failing_step_name,
            "failed",
            {
                "error": "Pipeline execution failed",
                "error_type": type(exc).__name__,
                "lost_events": lost_events,
            },
            lost_event_counts=_lost_event_counts,
            logger=logger,
        )
        raise
    finally:
        runtime.redis_client.close()
        logger.debug("redis_client_closed", analysis_id=analysis_id)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_export(self, export_job_id: str, org_id: str) -> dict:
    """Export a report to PDF/DOCX/XLSX/CSV/JSON."""
    result = execute_export_job(export_job_id=export_job_id, org_id=org_id)
    # The worker owns the durable retry budget and lease. Celery only supplies
    # the next delivery, timed to that lease, for both active duplicate
    # deliveries and newly recorded retryable failures.
    if isinstance(result, dict) and result.get("status") in {"retry_later", "failed"}:
        try:
            retry_after_seconds = int(result.get("retry_after_seconds") or 60)
        except (TypeError, ValueError):
            retry_after_seconds = 60
        raise self.retry(
            countdown=max(1, retry_after_seconds),
            exc=RuntimeError(result.get("reason") or result.get("error") or "export_retry_later"),
        )
    return result


def execute_export_job(*, export_job_id: str, org_id: str) -> dict:
    """Execute a report export outside Celery.

    Production Cloud Tasks invokes this through the internal worker route.
    Celery remains the local/test dispatcher and delegates here.
    """
    logger.info("export_starting", job_id=export_job_id, org_id=org_id)
    return task_exports.run_export_job(
        engine=_get_sync_engine(),
        export_job_id=export_job_id,
        org_id=org_id,
        logger=logger,
        render_export_fn=task_exports.render_export_artifact,
    )


# ---------------------------------------------------------------------------
# Faithfulness-Aware UQ task (T3-02)
#
# Paper: arXiv:2505.21072 (Vashurin, Fadeeva et al., May 2025).
# Feature flag: ``PRAVIAR_FAITHFULNESS_UQ_ENABLED``. Without it set, the task
# is never dispatched; existing analyses are unaffected.
#
# This task runs after the FTO pipeline completes successfully. It scores each
# (claim sentence, cited evidence) pair extracted from ``report_data`` via a
# Claude Haiku NLI prompt and persists the verdicts to ``faithfulness_scores``.
# Shadow mode: no consumer reads these rows for queue ordering or report
# assembly until correlation with reviewer-override events has been measured.
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, max_retries=0)
def compute_faithfulness_scores(self, analysis_id: str, org_id: str) -> dict:
    """Score per-evidence faithfulness for the analysis (shadow signal)."""
    return execute_faithfulness_scores(analysis_id=analysis_id, org_id=org_id)


def execute_faithfulness_scores(*, analysis_id: str, org_id: str) -> dict:
    """Execute shadow faithfulness scoring outside Celery."""
    from api.workers import task_faithfulness

    logger.info("faithfulness_uq_starting", analysis_id=analysis_id)
    return task_faithfulness.compute_faithfulness_scores_impl(
        engine=_get_sync_engine(),
        analysis_id=analysis_id,
        org_id=org_id,
    )


from api.workers import monitor_tasks as _monitor_tasks  # noqa: E402,F401
