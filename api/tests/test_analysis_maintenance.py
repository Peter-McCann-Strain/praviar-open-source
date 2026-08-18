from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.db.models import AnalysisStatus
from api.services.analysis_dispatch import (
    MAX_PIPELINE_RECONCILIATION_GENERATIONS,
    PIPELINE_RECONCILIATION_COOLDOWN,
)
from api.services.analysis_maintenance import (
    STALE_ANALYSIS_SWEEP_BATCH_SIZE,
    _rotated_org_ids,
    mark_stale_analyses_failed_async,
)


def _result(*, scalar=None, scalars=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = list(scalars or [])
    return result


def _session_context(session):
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    return context


def _pending_analysis(*, generation: int = 0, dispatched_at: datetime | None = None):
    analysis = MagicMock()
    analysis.status = AnalysisStatus.PENDING
    analysis.pipeline_execution_id = None
    analysis.pipeline_reconciliation_generation = generation
    analysis.pipeline_reconciliation_dispatched_at = dispatched_at
    return analysis


def _expired_running_analysis() -> MagicMock:
    analysis = MagicMock()
    analysis.status = AnalysisStatus.RUNNING
    analysis.pipeline_execution_id = uuid.uuid4()
    analysis.pipeline_lease_expires_at = datetime.now(UTC) - timedelta(minutes=30)
    analysis.updated_at = datetime.now(UTC) - timedelta(hours=3)
    analysis.pipeline_reconciliation_generation = 0
    analysis.pipeline_reconciliation_dispatched_at = None
    return analysis


def _discovery_sessions(*, org_id, analysis_id):
    org_session = AsyncMock()
    org_session.execute.return_value = _result(scalars=[org_id])
    stale_session = AsyncMock()
    stale_session.execute.side_effect = [
        _result(),
        _result(scalars=[analysis_id]),
    ]
    return org_session, stale_session


def _reservation_session(*, org_id, analysis):
    session = AsyncMock()
    session.execute.side_effect = [
        _result(),
        _result(scalar=org_id),
        _result(scalar=analysis),
    ]
    return session


def test_stale_sweep_rotates_tenants_by_scheduler_window() -> None:
    org_ids = [uuid.uuid4() for _ in range(3)]
    first_window = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    second_window = first_window + timedelta(minutes=15)

    first = _rotated_org_ids(org_ids, now=first_window)
    second = _rotated_org_ids(org_ids, now=second_window)

    assert sorted(first) == sorted(org_ids)
    assert second == [*first[1:], first[0]]


@pytest.mark.asyncio
async def test_stale_analysis_sweep_redrives_with_persisted_generation() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    analysis = _pending_analysis()
    org_session, stale_session = _discovery_sessions(
        org_id=org_id,
        analysis_id=analysis_id,
    )
    reservation_session = _reservation_session(org_id=org_id, analysis=analysis)
    session_factory = MagicMock(
        side_effect=[
            _session_context(org_session),
            _session_context(stale_session),
            _session_context(reservation_session),
        ]
    )
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(return_value="task-1")

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.analysis_maintenance.stale_analysis_sweep_last_success_unixtime"
        ) as last_success,
        patch(
            "api.services.analysis_maintenance.refund_cancelled_analysis_credits",
            new=AsyncMock(),
        ) as refund,
    ):
        result = await mark_stale_analyses_failed_async()

    assert result == {
        "marked_count": 0,
        "redriven_count": 1,
        "refunded_credits": 0,
        "orgs_checked": 1,
        "error_count": 0,
    }
    dispatcher.dispatch_pipeline_run.assert_awaited_once_with(
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        reconciliation_key="repair-1",
    )
    assert analysis.pipeline_reconciliation_generation == 1
    assert isinstance(analysis.pipeline_reconciliation_dispatched_at, datetime)
    org_query = org_session.execute.await_args.args[0]
    assert "ORDER BY organizations.id" in str(org_query)
    stale_query = stale_session.execute.await_args_list[1].args[0]
    assert "ORDER BY" in str(stale_query)
    assert "LIMIT" in str(stale_query)
    assert "analyses.status = :status_1" in str(stale_query)
    assert "analyses.status = :status_2" in str(stale_query)
    assert "analyses.updated_at" in str(stale_query)
    assert STALE_ANALYSIS_SWEEP_BATCH_SIZE in stale_query.compile().params.values()
    reservation_session.commit.assert_awaited_once()
    refund.assert_not_awaited()
    last_success.set.assert_called_once()


@pytest.mark.asyncio
async def test_stale_analysis_sweep_preserves_ambiguous_dispatch_failure() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    analysis = _pending_analysis()
    org_session, stale_session = _discovery_sessions(
        org_id=org_id,
        analysis_id=analysis_id,
    )
    reservation_session = _reservation_session(org_id=org_id, analysis=analysis)
    session_factory = MagicMock(
        side_effect=[
            _session_context(org_session),
            _session_context(stale_session),
            _session_context(reservation_session),
        ]
    )
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(side_effect=RuntimeError("queue unavailable"))

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.analysis_maintenance.stale_analysis_redrive_failures_total"
        ) as redrive_failures,
        patch(
            "api.services.analysis_maintenance.stale_analysis_sweep_last_success_unixtime"
        ) as last_success,
        patch(
            "api.services.analysis_maintenance.refund_cancelled_analysis_credits",
            new=AsyncMock(),
        ) as refund,
    ):
        result = await mark_stale_analyses_failed_async()

    assert result == {
        "marked_count": 0,
        "redriven_count": 0,
        "refunded_credits": 0,
        "orgs_checked": 1,
        "error_count": 1,
    }
    assert analysis.status == AnalysisStatus.PENDING
    assert analysis.pipeline_reconciliation_generation == 1
    reservation_session.commit.assert_awaited_once()
    refund.assert_not_awaited()
    redrive_failures.inc.assert_called_once_with()
    last_success.set.assert_not_called()


@pytest.mark.asyncio
async def test_stale_analysis_sweep_refunds_after_generation_exhaustion() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    analysis = _pending_analysis(
        generation=MAX_PIPELINE_RECONCILIATION_GENERATIONS,
        dispatched_at=(datetime.now(UTC) - PIPELINE_RECONCILIATION_COOLDOWN - timedelta(minutes=1)),
    )
    org_session, stale_session = _discovery_sessions(
        org_id=org_id,
        analysis_id=analysis_id,
    )
    reservation_session = _reservation_session(org_id=org_id, analysis=analysis)
    terminal_session = _reservation_session(org_id=org_id, analysis=analysis)
    session_factory = MagicMock(
        side_effect=[
            _session_context(org_session),
            _session_context(stale_session),
            _session_context(reservation_session),
            _session_context(terminal_session),
        ]
    )
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock()

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.analysis_maintenance.refund_cancelled_analysis_credits",
            new=AsyncMock(return_value=1),
        ) as refund,
    ):
        result = await mark_stale_analyses_failed_async()

    assert result == {
        "marked_count": 1,
        "redriven_count": 0,
        "refunded_credits": 1,
        "orgs_checked": 1,
        "error_count": 0,
    }
    refund.assert_awaited_once_with(
        terminal_session,
        org_id=org_id,
        analysis_id=analysis_id,
    )
    assert analysis.status == AnalysisStatus.FAILED
    assert "bounded reconciliation generations" in analysis.error_message
    dispatcher.dispatch_pipeline_run.assert_not_awaited()
    reservation_session.commit.assert_awaited_once()
    terminal_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_analysis_sweep_has_global_multi_org_dispatch_bound() -> None:
    org_ids = [uuid.uuid4(), uuid.uuid4()]
    analysis_ids = [uuid.uuid4() for _ in range(120)]
    org_session = AsyncMock()
    org_session.execute.return_value = _result(scalars=org_ids)

    stale_sessions: list[AsyncMock] = []
    reservation_sessions: list[AsyncMock] = []
    session_contexts = [_session_context(org_session)]
    for index, org_id in enumerate(org_ids):
        start = index * 60
        org_analysis_ids = analysis_ids[start : start + 60]
        stale_session = AsyncMock()
        stale_session.execute.side_effect = [
            _result(),
            _result(scalars=org_analysis_ids),
        ]
        stale_sessions.append(stale_session)
        session_contexts.append(_session_context(stale_session))
        reservation_count = min(
            60,
            STALE_ANALYSIS_SWEEP_BATCH_SIZE - start,
        )
        for _ in range(reservation_count):
            analysis = _pending_analysis()
            reservation_session = _reservation_session(
                org_id=org_id,
                analysis=analysis,
            )
            reservation_sessions.append(reservation_session)
            session_contexts.append(_session_context(reservation_session))

    session_factory = MagicMock(side_effect=session_contexts)
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(return_value="task")

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch(
            "api.services.analysis_maintenance._rotated_org_ids",
            side_effect=lambda values: values,
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.analysis_maintenance.refund_cancelled_analysis_credits",
            new=AsyncMock(),
        ),
    ):
        result = await mark_stale_analyses_failed_async()

    assert result["orgs_checked"] == 2
    assert result["redriven_count"] == STALE_ANALYSIS_SWEEP_BATCH_SIZE
    assert dispatcher.dispatch_pipeline_run.await_count == (STALE_ANALYSIS_SWEEP_BATCH_SIZE)
    assert len(reservation_sessions) == STALE_ANALYSIS_SWEEP_BATCH_SIZE
    assert all(session.commit.await_count == 1 for session in reservation_sessions)
    second_query = stale_sessions[1].execute.await_args_list[1].args[0]
    assert STALE_ANALYSIS_SWEEP_BATCH_SIZE - 60 in second_query.compile().params.values()


@pytest.mark.asyncio
async def test_stale_analysis_sweep_reclaims_expired_running_execution() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    analysis = _expired_running_analysis()
    previous_execution_id = analysis.pipeline_execution_id
    org_session, stale_session = _discovery_sessions(
        org_id=org_id,
        analysis_id=analysis_id,
    )
    reservation_session = _reservation_session(org_id=org_id, analysis=analysis)
    session_factory = MagicMock(
        side_effect=[
            _session_context(org_session),
            _session_context(stale_session),
            _session_context(reservation_session),
        ]
    )
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(return_value="repair-task")

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.analysis_maintenance.stale_analysis_oldest_expired_running_age_seconds"
        ) as oldest_expired_running,
        patch("api.services.analysis_maintenance.stale_analysis_reclaimed_total") as reclaimed,
        patch(
            "api.services.analysis_maintenance.refund_cancelled_analysis_credits",
            new=AsyncMock(),
        ),
    ):
        result = await mark_stale_analyses_failed_async()

    assert result["redriven_count"] == 1
    assert analysis.status == AnalysisStatus.PENDING
    assert analysis.pipeline_execution_id is None
    assert analysis.pipeline_lease_expires_at is None
    assert analysis.pipeline_reconciliation_generation == 1
    reservation_session.commit.assert_awaited_once()
    dispatcher.dispatch_pipeline_run.assert_awaited_once_with(
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        reconciliation_key="repair-1",
    )
    assert previous_execution_id is not None
    reclaimed.inc.assert_called_once_with()
    assert oldest_expired_running.set.call_count == 2
    assert oldest_expired_running.set.call_args.args[0] >= 3 * 60 * 60


@pytest.mark.asyncio
async def test_stale_analysis_sweep_does_not_reclaim_renewed_running_lease() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    analysis = _expired_running_analysis()
    analysis.pipeline_lease_expires_at = datetime.now(UTC) + timedelta(minutes=20)
    org_session, stale_session = _discovery_sessions(
        org_id=org_id,
        analysis_id=analysis_id,
    )
    reservation_session = _reservation_session(org_id=org_id, analysis=analysis)
    session_factory = MagicMock(
        side_effect=[
            _session_context(org_session),
            _session_context(stale_session),
            _session_context(reservation_session),
        ]
    )
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock()

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        result = await mark_stale_analyses_failed_async()

    assert result["redriven_count"] == 0
    assert analysis.status == AnalysisStatus.RUNNING
    reservation_session.rollback.assert_awaited_once()
    reservation_session.commit.assert_not_awaited()
    dispatcher.dispatch_pipeline_run.assert_not_awaited()
