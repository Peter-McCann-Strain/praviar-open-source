"""Tests for scheduled monitor dispatch (continuous monitoring, Task 3.2).

Covers the due-calculation in ``load_due_monitor_ids`` and the fan-out
behaviour of the scheduled worker entrypoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db

from api.services.monitor_runtime import (
    MAX_DUE_MONITOR_DISPATCH_BATCH,
    load_due_monitor_ids,
    load_due_monitor_refs,
)
from api.workers.monitor_tasks import (
    _dispatch_due_monitors_async,
    _monitor_scan_lock_key,
    _run_monitor_scan_async,
    execute_due_monitor_dispatch,
    execute_monitor_scan,
)


def _make_monitor_mock(*, schedule: str, last_run_at: datetime | None, is_active: bool = True):
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.schedule = schedule
    monitor.last_run_at = last_run_at
    monitor.is_active = is_active
    return monitor


@pytest.mark.asyncio
async def test_load_due_monitor_ids_includes_never_run_monitor():
    """A monitor that has never run (last_run_at is NULL) is always due."""
    db = make_mock_db()
    never_run = _make_monitor_mock(schedule="weekly", last_run_at=None)
    db.execute.return_value.all.return_value = [(never_run.id, never_run.org_id)]

    due_ids = await load_due_monitor_ids(db)

    assert due_ids == [never_run.id]


@pytest.mark.asyncio
async def test_load_due_monitor_ids_weekly_due_after_seven_days():
    """A weekly monitor last run >= 7 days ago is due; one run 3 days ago is not."""
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    db = make_mock_db()
    due_monitor = _make_monitor_mock(
        schedule="weekly",
        last_run_at=now - timedelta(days=8),
    )
    db.execute.return_value.all.return_value = [(due_monitor.id, due_monitor.org_id)]

    due_ids = await load_due_monitor_ids(db, now=now)

    assert due_ids == [due_monitor.id]


@pytest.mark.asyncio
async def test_load_due_monitor_ids_weekly_exactly_seven_days_is_due():
    """The due threshold is inclusive: exactly 7 days elapsed counts as due."""
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    db = make_mock_db()
    boundary_monitor = _make_monitor_mock(
        schedule="weekly",
        last_run_at=now - timedelta(days=7),
    )
    db.execute.return_value.all.return_value = [(boundary_monitor.id, boundary_monitor.org_id)]

    due_ids = await load_due_monitor_ids(db, now=now)

    assert due_ids == [boundary_monitor.id]


@pytest.mark.asyncio
async def test_load_due_monitor_refs_caps_scheduler_batch_size():
    db = make_mock_db()
    db.execute.return_value.all.return_value = []

    await load_due_monitor_refs(db, limit=MAX_DUE_MONITOR_DISPATCH_BATCH + 100)

    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert f"LIMIT {MAX_DUE_MONITOR_DISPATCH_BATCH}" in compiled


@pytest.mark.asyncio
async def test_dispatch_due_monitors_enqueues_one_scan_per_due_monitor():
    """dispatch_due_monitors fans out a run_monitor_scan task per due monitor."""
    due_id_one = uuid.uuid4()
    due_id_two = uuid.uuid4()
    org_id_one = uuid.uuid4()
    org_id_two = uuid.uuid4()
    db = make_mock_db()

    with (
        patch("api.workers.monitor_tasks.async_session_factory") as factory,
        patch(
            "api.services.monitor_runtime.load_due_monitor_refs",
        ) as load_due,
        patch(
            "api.services.task_dispatcher.build_dispatcher",
            return_value=SimpleNamespace(dispatch_monitor_scan=AsyncMock()),
        ) as build_dispatcher,
    ):
        factory.return_value.__aenter__.return_value = db
        factory.return_value.__aexit__.return_value = False
        load_due.return_value = [(due_id_one, org_id_one), (due_id_two, org_id_two)]

        result = await _dispatch_due_monitors_async()

    assert result == {"due_monitors": 2, "enqueued": 2, "failed": 0}
    dispatcher = build_dispatcher.return_value
    assert dispatcher.dispatch_monitor_scan.await_count == 2
    calls = [call.kwargs for call in dispatcher.dispatch_monitor_scan.await_args_list]
    assert {call["monitor_id"] for call in calls} == {str(due_id_one), str(due_id_two)}
    assert {call["org_id"] for call in calls} == {str(org_id_one), str(org_id_two)}
    assert all(call["force_full_refresh"] is False for call in calls)
    assert all(call["dedupe_key"].startswith("scheduled-") for call in calls)
    assert any(call["dedupe_key"].endswith(str(due_id_one)) for call in calls)
    assert any(call["dedupe_key"].endswith(str(due_id_two)) for call in calls)


@pytest.mark.asyncio
async def test_dispatch_due_monitors_enqueues_nothing_when_no_monitor_is_due():
    """When no monitor is due, dispatch enqueues no scans and reports zero."""
    db = make_mock_db()

    with (
        patch("api.workers.monitor_tasks.async_session_factory") as factory,
        patch(
            "api.services.monitor_runtime.load_due_monitor_refs",
        ) as load_due,
        patch(
            "api.services.task_dispatcher.build_dispatcher",
            return_value=SimpleNamespace(dispatch_monitor_scan=AsyncMock()),
        ) as build_dispatcher,
    ):
        factory.return_value.__aenter__.return_value = db
        factory.return_value.__aexit__.return_value = False
        load_due.return_value = []

        result = await _dispatch_due_monitors_async()

    assert result == {"due_monitors": 0, "enqueued": 0, "failed": 0}
    build_dispatcher.return_value.dispatch_monitor_scan.assert_not_awaited()


def test_monitor_scan_lock_key_fits_postgres_bigint():
    monitor_id = uuid.uuid4()

    lock_key = _monitor_scan_lock_key(monitor_id)

    assert 0 <= lock_key < 2**63
    assert lock_key == _monitor_scan_lock_key(monitor_id)


def test_execute_monitor_scan_delegates_to_async_entrypoint():
    monitor_id = uuid.uuid4()

    def _run_async(coro):
        coro.close()
        return {"status": "ok", "monitor_id": str(monitor_id)}

    with patch(
        "api.workers.monitor_tasks.run_async",
        side_effect=_run_async,
    ) as run_async:
        result = execute_monitor_scan(
            monitor_id=str(monitor_id),
            org_id=str(uuid.uuid4()),
            force_full_refresh=True,
        )

    assert result == {"status": "ok", "monitor_id": str(monitor_id)}
    run_async.assert_called_once()


def test_execute_due_monitor_dispatch_delegates_to_async_entrypoint():
    def _run_async(coro):
        coro.close()
        return {"due_monitors": 2, "enqueued": 2}

    with patch(
        "api.workers.monitor_tasks.run_async",
        side_effect=_run_async,
    ) as run_async:
        result = execute_due_monitor_dispatch()

    assert result == {"due_monitors": 2, "enqueued": 2}
    run_async.assert_called_once()


@pytest.mark.asyncio
async def test_run_monitor_scan_skips_when_advisory_lock_is_busy():
    """Duplicate queue delivery should not run the same monitor scan twice.

    The advisory lock is now held on a dedicated pinned connection
    (pinned_advisory_lock), not on the main DB session. When the lock is busy
    the worker returns early without opening any session.
    """
    monitor_id = uuid.uuid4()
    monitor = MagicMock()
    monitor.id = monitor_id
    monitor.org_id = uuid.uuid4()

    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = False  # lock not acquired
    lock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.workers.monitor_tasks.async_session_factory") as factory,
        patch(
            "api.workers.monitor_tasks.bind_current_org_to_session",
            new_callable=AsyncMock,
        ) as bind_org,
        patch(
            "api.services.monitor_runtime.execute_monitor_run",
            new_callable=AsyncMock,
        ) as run_monitor,
        patch(
            "api.workers.monitor_tasks.pinned_advisory_lock",
            return_value=lock_cm,
        ),
    ):
        result = await _run_monitor_scan_async(
            str(monitor_id),
            org_id=str(monitor.org_id),
            force_full_refresh=False,
        )

    assert result == {"status": "already_running", "monitor_id": str(monitor_id)}
    factory.assert_not_called()
    bind_org.assert_not_awaited()
    run_monitor.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_monitor_scan_releases_advisory_lock_after_success():
    """A successful scan must complete with the lock held throughout.

    The lock is managed by pinned_advisory_lock (dedicated connection).
    The main DB session only handles the monitor fetch and execution.
    """
    monitor_id = uuid.uuid4()
    monitor = MagicMock()
    monitor.id = monitor_id
    monitor.org_id = uuid.uuid4()
    response = MagicMock()
    response.model_dump.return_value = {"status": "ok", "monitor_id": str(monitor_id)}
    db = make_mock_db()
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=monitor_result)

    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = True  # lock acquired
    lock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.workers.monitor_tasks.async_session_factory") as factory,
        patch(
            "api.workers.monitor_tasks.bind_current_org_to_session",
            new_callable=AsyncMock,
        ) as bind_org,
        patch(
            "api.services.monitor_runtime.execute_monitor_run",
            new_callable=AsyncMock,
            return_value=response,
        ) as run_monitor,
        patch(
            "api.workers.monitor_tasks.pinned_advisory_lock",
            return_value=lock_cm,
        ),
    ):
        factory.return_value.__aenter__.return_value = db
        factory.return_value.__aexit__.return_value = False

        result = await _run_monitor_scan_async(
            str(monitor_id),
            org_id=str(monitor.org_id),
            force_full_refresh=False,
        )

    assert result == {"status": "ok", "monitor_id": str(monitor_id)}
    bind_org.assert_awaited_once_with(db, monitor.org_id)
    run_monitor.assert_awaited_once_with(db, monitor=monitor, force_full_refresh=False)


@pytest.mark.asyncio
async def test_run_monitor_scan_advances_last_run_at_on_failure():
    """A failed scan must stamp last_run_at so the schedule window is consumed.

    Otherwise a permanently failing monitor (last_run_at left NULL/stale) is
    re-selected by load_due_monitor_refs on every hourly sweep, re-billing
    external evidence providers and ignoring its configured cadence.
    """
    monitor_id = uuid.uuid4()
    monitor = MagicMock()
    monitor.id = monitor_id
    monitor.org_id = uuid.uuid4()
    monitor.last_run_at = None  # never succeeded
    # The lease set on the running marker; the failure handler only writes
    # "failed" while scan_execution_id is still set (success would clear it).
    monitor.scan_execution_id = uuid.uuid4()

    db = make_mock_db()
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=monitor_result)
    db.commit = AsyncMock()

    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = True
    lock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.workers.monitor_tasks.async_session_factory") as factory,
        patch(
            "api.workers.monitor_tasks.bind_current_org_to_session",
            new_callable=AsyncMock,
        ),
        patch(
            "api.services.monitor_runtime.execute_monitor_run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider exploded"),
        ),
        patch(
            "api.workers.monitor_tasks.pinned_advisory_lock",
            return_value=lock_cm,
        ),
    ):
        factory.return_value.__aenter__.return_value = db
        factory.return_value.__aexit__.return_value = False

        with pytest.raises(RuntimeError, match="provider exploded"):
            await _run_monitor_scan_async(
                str(monitor_id),
                org_id=str(monitor.org_id),
                force_full_refresh=False,
            )

    assert monitor.last_run_status == "failed"
    assert isinstance(monitor.last_run_at, datetime)
    assert monitor.scan_execution_id is None
    assert monitor.scan_lease_expires_at is None
