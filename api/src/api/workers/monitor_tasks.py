"""Worker tasks for low-cost monitor execution.

Continuous FTO monitoring (Horizon 3, Task 3.2) turns a one-shot analysis into
ongoing surveillance. Two dispatch paths exist and share ``execute_monitor_run``:

* Reactive: the manual run endpoint (``routes/monitors.py``) calls
  ``execute_monitor_run`` directly, and a single monitor can be re-scanned via
  ``run_monitor_scan``. Behaviour-preserving for existing reactive runs.
* Scheduled: an internal worker route calls ``execute_due_monitor_dispatch``
  periodically. That function queries monitors whose ``schedule`` is due (based
  on ``last_run_at``) and fans out one ``run_monitor_scan`` per due monitor.
  Each scan runs in its own task so a slow or failing monitor cannot block the
  rest of the cohort.

Multi-tenancy: ``dispatch_due_monitors`` reads ``monitors`` across all orgs to
find due rows, which relies on the worker connecting with the BYPASSRLS role
(see the RLS contract in ``api/src/api/db/session.py``). Each ``run_monitor_scan``
writes org-scoped rows (the ``monitors`` row and ``monitor_alerts``), so it binds
``app.current_org_id`` to the session first. The transaction-local setting keeps
the write path correct under a non-privileged role too: defence in depth,
matching the pattern in ``task_faithfulness.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import and_, text, update
from sqlalchemy.engine import CursorResult

from api.db.session import async_session_factory, bind_current_org_to_session, pinned_advisory_lock
from api.errors import APIError
from api.workers.celery_app import celery_app, run_async

logger = structlog.get_logger()


def _monitor_scan_lock_key(monitor_id: uuid.UUID) -> int:
    """Return a stable signed bigint key for PostgreSQL advisory locks."""
    return monitor_id.int & ((1 << 63) - 1)


async def _run_monitor_scan_async(
    monitor_id: str,
    *,
    org_id: str,
    force_full_refresh: bool,
) -> dict:
    from api.services.monitor_runtime import execute_monitor_run, get_monitor_for_run

    monitor_uuid = uuid.UUID(str(monitor_id))
    org_uuid = uuid.UUID(str(org_id))
    lock_key = _monitor_scan_lock_key(monitor_uuid)

    async with pinned_advisory_lock(lock_key) as acquired:
        if not acquired:
            logger.info("monitor_scan_skipped_already_running", monitor_id=str(monitor_id))
            return {"status": "already_running", "monitor_id": monitor_id}

        async with async_session_factory() as db:
            await bind_current_org_to_session(db, org_uuid)
            try:
                monitor = await get_monitor_for_run(
                    db,
                    monitor_id=monitor_uuid,
                    org_id=org_uuid,
                )
            except APIError as exc:
                if exc.status != 404:
                    raise
                logger.warning("monitor_scan_not_found", monitor_id=str(monitor_id))
                return {"status": "not_found", "monitor_id": monitor_id}

            # Claim the execution lease before calling providers.
            # This creates a durable "running" marker so a crashed worker leaves
            # a reclaimable row instead of silently discarding the run.
            # The success path in execute_monitor_run clears scan_execution_id;
            # the exception handler below only writes "failed" while the lease
            # is still held — preventing a post-success db.refresh failure from
            # retroactively overwriting a successful "ok" status.
            scan_execution_id = uuid.uuid4()
            monitor.scan_execution_id = scan_execution_id
            monitor.scan_lease_expires_at = datetime.now(UTC) + timedelta(minutes=10)
            monitor.last_run_status = "running"
            await db.commit()

            try:
                result = await execute_monitor_run(
                    db,
                    monitor=monitor,
                    force_full_refresh=force_full_refresh,
                )
                return result.model_dump(mode="json")
            except Exception:
                # Only mark failed if the success commit hasn't already cleared
                # the lease (scan_execution_id set to None by execute_monitor_run).
                if monitor.scan_execution_id is not None:
                    monitor.last_run_status = "failed"
                    # Advance last_run_at on failure too. load_due_monitor_refs
                    # computes due-ness from last_run_at against the schedule
                    # interval; a permanently failing monitor (broken source
                    # analysis, persistently erroring providers) whose
                    # last_run_at was never advanced would be re-dispatched on
                    # EVERY hourly sweep — ignoring its daily/weekly/monthly
                    # cadence and re-billing external evidence providers each
                    # hour. Stamping last_run_at makes a failed run consume the
                    # schedule window like a successful one, so retries respect
                    # the configured interval instead of busy-looping.
                    monitor.last_run_at = datetime.now(UTC)
                    monitor.scan_execution_id = None
                    monitor.scan_lease_expires_at = None
                    try:
                        await db.commit()
                    except Exception:
                        await db.rollback()
                raise


async def _assert_worker_has_bypassrls(db) -> None:
    result = await db.execute(
        text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    row = result.one_or_none()
    if row is None or not row[0]:
        role_name = (await db.execute(text("SELECT current_user"))).scalar()
        raise RuntimeError(
            f"Worker DB role '{role_name}' does not have BYPASSRLS. "
            "The scheduled monitor dispatch cannot read across all tenants without it. "
            "Run `praviar-api db-bootstrap-roles` to grant BYPASSRLS to the worker role."
        )


async def _dispatch_due_monitors_async() -> dict:
    """Find monitors whose schedule is due and enqueue a scan for each.

    Due-ness is computed by ``load_due_monitor_ids``: a monitor is due when it
    is active and either has never run (``last_run_at`` is NULL) or the elapsed
    time since ``last_run_at`` is at least its schedule interval (daily = 1 day,
    weekly = 7 days, monthly = 30 days). This cross-org read requires the worker
    DB role to hold BYPASSRLS so the org_isolation RLS policy on monitors does
    not filter all rows. Use ``praviar-api db-bootstrap-roles`` to provision it.
    """
    from api.services.monitor_runtime import load_due_monitor_refs
    from api.services.task_dispatcher import build_dispatcher

    async with async_session_factory() as db:
        await _assert_worker_has_bypassrls(db)

        # Reclaim monitors whose scan lease expired while still showing
        # last_run_status="running" — this happens when a worker crashes
        # hard (SIGKILL/OOM) before the success or failure commit.
        # Without reclaim the UI shows "running" indefinitely.
        from api.db.models import Monitor

        now = datetime.now(UTC)
        reclaimed = await db.execute(
            update(Monitor)
            .where(
                and_(
                    Monitor.last_run_status == "running",
                    Monitor.scan_lease_expires_at.is_not(None),
                    Monitor.scan_lease_expires_at <= now,
                )
            )
            .values(
                last_run_status="failed",
                scan_execution_id=None,
                scan_lease_expires_at=None,
            )
        )
        reclaimed_count = cast(CursorResult[Any], reclaimed).rowcount
        if reclaimed_count:
            await db.commit()
            logger.warning(
                "monitor_scan_lease_expired_reclaimed",
                count=reclaimed_count,
            )

        due_refs = await load_due_monitor_refs(db)

    enqueued = 0
    failed = 0
    dispatcher = build_dispatcher()
    dispatch_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
    for monitor_id, org_id in due_refs:
        # Isolate per-monitor dispatch failures: a transient Cloud Tasks error
        # (DeadlineExceeded, ResourceExhausted, etc.) for one monitor must not
        # abort the sweep and starve every remaining due monitor in the cohort.
        # The docstring contract ("a slow or failing monitor cannot block the
        # rest of the cohort") only holds if each dispatch is isolated here.
        try:
            await dispatcher.dispatch_monitor_scan(
                monitor_id=str(monitor_id),
                org_id=str(org_id),
                force_full_refresh=False,
                dedupe_key=f"scheduled-{dispatch_bucket}-{monitor_id}",
            )
            enqueued += 1
        except Exception:
            failed += 1
            logger.error(
                "due_monitor_dispatch_enqueue_failed",
                monitor_id=str(monitor_id),
                org_id=str(org_id),
                exc_info=True,
            )

    logger.info(
        "due_monitor_dispatch_completed",
        due_monitors=len(due_refs),
        enqueued=enqueued,
        failed=failed,
    )
    return {"due_monitors": len(due_refs), "enqueued": enqueued, "failed": failed}


@celery_app.task
def run_monitor_scan(
    monitor_id: str,
    org_id: str,
    force_full_refresh: bool = False,
) -> dict:
    """Execute one bounded monitor scan, persisting history and any alerts."""
    return execute_monitor_scan(
        monitor_id=monitor_id,
        org_id=org_id,
        force_full_refresh=force_full_refresh,
    )


def execute_monitor_scan(
    *,
    monitor_id: str,
    org_id: str,
    force_full_refresh: bool = False,
) -> dict:
    """Execute one monitor scan outside Celery."""
    logger.info(
        "monitor_scan_starting",
        monitor_id=monitor_id,
        org_id=org_id,
        force_full_refresh=force_full_refresh,
    )
    return cast(
        dict,
        run_async(
            _run_monitor_scan_async(
                monitor_id,
                org_id=org_id,
                force_full_refresh=force_full_refresh,
            )
        ),
    )


@celery_app.task
def dispatch_due_monitors() -> dict:
    """Compatibility wrapper: enqueue a scan for every monitor that is due."""
    return execute_due_monitor_dispatch()


def execute_due_monitor_dispatch() -> dict:
    """Execute the due-monitor sweep outside Celery."""
    logger.info("due_monitor_dispatch_starting")
    return cast(dict, run_async(_dispatch_due_monitors_async()))
