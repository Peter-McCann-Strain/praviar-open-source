"""Maintenance tasks for the analysis lifecycle.

These functions are invoked by Cloud Scheduler via internal endpoints and are
not part of the hot request path.  Each function opens its own DB session(s)
and is fully self-contained.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy import func as sqlfunc

from api.db.models import AnalysisStatus
from api.db.models_analysis import Analysis
from api.db.models_identity import Organization
from api.metrics import (
    stale_analysis_oldest_expired_running_age_seconds,
    stale_analysis_reclaimed_total,
    stale_analysis_redrive_failures_total,
    stale_analysis_sweep_last_success_unixtime,
)
from api.services.analysis_dispatch import reserve_pipeline_reconciliation
from api.services.billing_queries import refund_cancelled_analysis_credits

logger = structlog.get_logger()

# PENDING launch receipts and RUNNING execution leases older than this threshold
# are considered orphaned. Set well above Cloud Tasks max dispatch + queue
# latency (~10 min) to avoid false positives on slow-dispatch under load.
_DEFAULT_GRACE_HOURS: int = 2
STALE_ANALYSIS_SWEEP_BATCH_SIZE: int = 100
_STALE_ANALYSIS_SWEEP_ROTATION_INTERVAL = timedelta(minutes=15)


def _rotated_org_ids(
    org_ids: list[uuid.UUID],
    *,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Rotate the deterministic tenant order once per scheduler interval."""
    if not org_ids:
        return []
    current_time = now or datetime.now(UTC)
    interval_seconds = int(_STALE_ANALYSIS_SWEEP_ROTATION_INTERVAL.total_seconds())
    offset = int(current_time.timestamp() // interval_seconds) % len(org_ids)
    return [*org_ids[offset:], *org_ids[:offset]]


async def mark_stale_analyses_failed_async(
    grace_hours: int = _DEFAULT_GRACE_HOURS,
) -> dict:
    """Redrive orphaned PENDING receipts and expired RUNNING leases.

    A RUNNING analysis is eligible only after both its heartbeat is stale and
    its execution lease is absent or expired. Reclaiming it clears the old
    execution fence before dispatch so the abandoned worker cannot later
    overwrite the successor.

    Works in two phases to respect FORCE RLS:
    1. Fetch all non-erased org IDs from ``organizations`` (accessible without
       per-org context since the table has no tenant isolation policy).
    2. For each org, bind ``app.current_org_id`` and bulk-UPDATE stale rows.
    """
    from api.db.session import async_session_factory

    sweep_now = datetime.now(UTC)
    cutoff = sweep_now - timedelta(hours=grace_hours)

    # Phase 1: collect org IDs from the non-RLS-gated organizations table.
    async with async_session_factory() as db:
        org_result = await db.execute(
            select(Organization.id)
            .where(
                Organization.deletion_status.is_(None) | (Organization.deletion_status != "erased")
            )
            .order_by(Organization.id)
        )
        org_ids = list(org_result.scalars().all())

    marked_count = 0
    redriven_count = 0
    refunded_credits = 0
    error_count = 0
    orgs_checked = 0
    remaining_receipts = STALE_ANALYSIS_SWEEP_BATCH_SIZE
    oldest_expired_running_age_seconds = 0.0
    stale_analysis_oldest_expired_running_age_seconds.set(0.0)

    from api.services.task_dispatcher import build_dispatcher

    dispatcher = build_dispatcher()

    # Phase 2: discover stale tenant-scoped launch receipts, then redrive them.
    for org_id in _rotated_org_ids(org_ids):
        if remaining_receipts <= 0:
            break
        orgs_checked += 1
        try:
            async with async_session_factory() as db:
                await db.execute(
                    select(sqlfunc.set_config("app.current_org_id", str(org_id), True))
                )
                result = await db.execute(
                    select(Analysis.id)
                    .where(
                        Analysis.org_id == org_id,
                        or_(
                            and_(
                                Analysis.status == AnalysisStatus.PENDING,
                                Analysis.created_at < cutoff,
                                or_(
                                    Analysis.pipeline_execution_id.is_(None),
                                    Analysis.pipeline_lease_expires_at < sweep_now,
                                ),
                            ),
                            and_(
                                Analysis.status == AnalysisStatus.RUNNING,
                                Analysis.updated_at < cutoff,
                                or_(
                                    Analysis.pipeline_lease_expires_at.is_(None),
                                    Analysis.pipeline_lease_expires_at < sweep_now,
                                ),
                            ),
                        ),
                    )
                    .order_by(Analysis.created_at, Analysis.id)
                    .limit(remaining_receipts)
                )
                stale_ids = list(result.scalars().all())[:remaining_receipts]
                remaining_receipts -= len(stale_ids)

            for analysis_id in stale_ids:
                terminal_reason: str | None = None
                reclaimed_running_age_seconds: float | None = None
                previous_execution_id: uuid.UUID | None = None
                async with async_session_factory() as db:
                    await db.execute(
                        select(sqlfunc.set_config("app.current_org_id", str(org_id), True))
                    )
                    await db.execute(
                        select(Organization.id).where(Organization.id == org_id).with_for_update()
                    )
                    analysis_result = await db.execute(
                        select(Analysis)
                        .where(
                            Analysis.id == analysis_id,
                            Analysis.org_id == org_id,
                        )
                        .with_for_update()
                    )
                    analysis = analysis_result.scalar_one_or_none()
                    if analysis is None:
                        await db.rollback()
                        continue

                    reclaimed_running = analysis.status == AnalysisStatus.RUNNING
                    if reclaimed_running:
                        lease_expiry = analysis.pipeline_lease_expires_at
                        updated_at = analysis.updated_at
                        if (
                            updated_at is None
                            or updated_at >= cutoff
                            or (lease_expiry is not None and lease_expiry >= sweep_now)
                        ):
                            await db.rollback()
                            continue
                        previous_execution_id = analysis.pipeline_execution_id
                        reclaimed_running_age_seconds = max(
                            0.0,
                            (sweep_now - updated_at).total_seconds(),
                        )
                        analysis.status = AnalysisStatus.PENDING
                        analysis.pipeline_execution_id = None
                        analysis.pipeline_lease_expires_at = None
                    elif analysis.status == AnalysisStatus.PENDING:
                        reservation_expiry = analysis.pipeline_lease_expires_at
                        if analysis.pipeline_execution_id is not None and (
                            reservation_expiry is None or reservation_expiry >= sweep_now
                        ):
                            await db.rollback()
                            continue
                        analysis.pipeline_execution_id = None
                        analysis.pipeline_lease_expires_at = None
                    else:
                        await db.rollback()
                        continue

                    reservation = reserve_pipeline_reconciliation(analysis)
                    if reservation is None:
                        await db.rollback()
                        continue
                    if reservation.exhausted:
                        terminal_reason = (
                            "Analysis expired: no worker claimed this task after "
                            f"{reservation.generation} bounded reconciliation generations."
                        )
                    await db.commit()

                if reclaimed_running_age_seconds is not None:
                    oldest_expired_running_age_seconds = max(
                        oldest_expired_running_age_seconds,
                        reclaimed_running_age_seconds,
                    )
                    stale_analysis_oldest_expired_running_age_seconds.set(
                        oldest_expired_running_age_seconds
                    )
                    stale_analysis_reclaimed_total.inc()
                    logger.warning(
                        "stale_analysis_sweep.expired_running_reclaimed",
                        org_id=str(org_id),
                        analysis_id=str(analysis_id),
                        previous_execution_id=(
                            str(previous_execution_id)
                            if previous_execution_id is not None
                            else None
                        ),
                        expired_running_age_seconds=reclaimed_running_age_seconds,
                        grace_hours=grace_hours,
                    )

                if terminal_reason is None:
                    try:
                        await dispatcher.dispatch_pipeline_run(
                            analysis_id=str(analysis_id),
                            org_id=str(org_id),
                            reconciliation_key=reservation.task_key,
                        )
                        redriven_count += 1
                        logger.warning(
                            "stale_analysis_sweep.redriven",
                            org_id=str(org_id),
                            analysis_id=str(analysis_id),
                            generation=reservation.generation,
                            generation_advanced=reservation.advanced,
                            grace_hours=grace_hours,
                        )
                        continue
                    except Exception:
                        # Queue-call failure is ambiguous: the task can have
                        # been durably accepted before the response was lost.
                        # Retain the bounded generation and retry its stable
                        # name until the cooldown advances it. Only exhaustion
                        # terminalizes and refunds.
                        error_count += 1
                        stale_analysis_redrive_failures_total.inc()
                        logger.exception(
                            "stale_analysis_sweep.redrive_failed",
                            org_id=str(org_id),
                            analysis_id=str(analysis_id),
                            generation=reservation.generation,
                        )
                        continue

                async with async_session_factory() as db:
                    await db.execute(
                        select(sqlfunc.set_config("app.current_org_id", str(org_id), True))
                    )
                    await db.execute(
                        select(Organization.id).where(Organization.id == org_id).with_for_update()
                    )
                    analysis_result = await db.execute(
                        select(Analysis)
                        .where(
                            Analysis.id == analysis_id,
                            Analysis.org_id == org_id,
                        )
                        .with_for_update()
                    )
                    analysis = analysis_result.scalar_one_or_none()
                    if (
                        analysis is None
                        or analysis.status != AnalysisStatus.PENDING
                        or analysis.pipeline_execution_id is not None
                    ):
                        await db.rollback()
                        continue

                    refunded_credits += await refund_cancelled_analysis_credits(
                        db,
                        org_id=org_id,
                        analysis_id=analysis_id,
                    )
                    analysis.status = AnalysisStatus.FAILED
                    analysis.error_message = terminal_reason
                    analysis.updated_at = datetime.now(UTC)
                    await db.commit()
                    marked_count += 1
                    logger.warning(
                        "stale_analysis_sweep.marked_failed",
                        org_id=str(org_id),
                        analysis_id=str(analysis_id),
                        grace_hours=grace_hours,
                    )
        except Exception:
            error_count += 1
            logger.exception("stale_analysis_sweep.org_error", org_id=str(org_id))

    logger.info(
        "stale_analysis_sweep.complete",
        orgs_available=len(org_ids),
        orgs_checked=orgs_checked,
        marked_count=marked_count,
        redriven_count=redriven_count,
        refunded_credits=refunded_credits,
        error_count=error_count,
        grace_hours=grace_hours,
    )
    if error_count == 0:
        stale_analysis_sweep_last_success_unixtime.set(datetime.now(UTC).timestamp())
    return {
        "marked_count": marked_count,
        "redriven_count": redriven_count,
        "refunded_credits": refunded_credits,
        "orgs_checked": orgs_checked,
        "error_count": error_count,
    }
