"""Task-level regressions for pipeline failure semantics."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.workers import tasks as tasks_module
from api.workers.tasks import (
    execute_export_job,
    execute_faithfulness_scores,
    execute_fto_pipeline,
    run_export,
    run_fto_pipeline,
)


def test_run_fto_pipeline_reraises_processing_failures():
    runtime = SimpleNamespace(engine=object(), redis_client=MagicMock())
    runtime.redis_client.close = MagicMock()
    analysis = SimpleNamespace(config={}, compound_input="aspirin", org_id="org-1", current_step=0)
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.get.return_value = analysis

    failure = RuntimeError("boom")
    with (
        patch("api.workers.tasks.task_runtime.build_pipeline_runtime", return_value=runtime),
        patch("api.workers.tasks.Session", return_value=session),
        patch(
            "api.workers.tasks.task_pipeline.run_pipeline_execution",
            side_effect=failure,
        ),
        patch("api.workers.tasks.task_state.publish_pipeline_event") as publish_mock,
        patch("api.workers.tasks.task_state.persist_pipeline_failure") as persist_mock,
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_fto_pipeline.run("analysis-1", org_id="org-1")

    publish_mock.assert_called_once()
    payload = publish_mock.call_args.args[5]
    assert payload["error"] == "Pipeline execution failed"
    assert payload["error_type"] == "RuntimeError"
    assert "boom" not in str(payload)
    persist_mock.assert_called_once()
    assert persist_mock.call_args.kwargs["exc"] is failure
    runtime.redis_client.close.assert_called_once()


def test_run_export_retries_retry_later_results():
    with (
        patch(
            "api.workers.tasks.execute_export_job",
            return_value={
                "status": "retry_later",
                "reason": "processing_lease_active",
                "retry_after_seconds": 7,
            },
        ) as execute,
        patch.object(run_export, "retry", side_effect=RuntimeError("retry scheduled")) as retry,
        pytest.raises(RuntimeError, match="retry scheduled"),
    ):
        run_export.run("export-1", org_id="org-1")

    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 7


def test_run_export_retries_failed_results():
    """A retryable durable failure schedules its next lease-bound delivery."""
    with (
        patch(
            "api.workers.tasks.execute_export_job",
            return_value={
                "status": "failed",
                "error": "export_failed",
                "retry_after_seconds": 120,
            },
        ) as execute,
        patch.object(run_export, "retry", side_effect=RuntimeError("retry scheduled")) as retry,
        pytest.raises(RuntimeError, match="retry scheduled"),
    ):
        run_export.run("export-1", org_id="org-1")

    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 120
    assert str(retry.call_args.kwargs["exc"]) == "export_failed"


def test_direct_pipeline_execution_requires_org_id():
    with pytest.raises(TypeError):
        execute_fto_pipeline(analysis_id="analysis-1")  # type: ignore[call-arg]


def test_direct_export_execution_requires_org_id():
    with pytest.raises(TypeError):
        execute_export_job(export_job_id="export-1")  # type: ignore[call-arg]


def test_direct_faithfulness_execution_requires_org_id():
    with pytest.raises(TypeError):
        execute_faithfulness_scores(analysis_id="analysis-1")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_delivery_reconciliation_discovery_includes_unknown_and_fans_out_tasks() -> None:
    org_ids = (uuid.uuid4(), uuid.uuid4())

    class Result:
        def scalars(self):
            return SimpleNamespace(all=lambda: org_ids)

    class DiscoverySession:
        def __init__(self) -> None:
            self.execute = AsyncMock(return_value=Result())
            self.commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = DiscoverySession()
    dispatcher = SimpleNamespace(
        dispatch_external_report_delivery_reconciliation=AsyncMock(
            side_effect=lambda **kwargs: f"task-{kwargs['org_id']}"
        )
    )
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch(
            "api.workers.monitor_tasks._assert_worker_has_bypassrls",
            AsyncMock(),
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        result = await tasks_module._dispatch_external_report_delivery_reconciliation_async()

    assert result["organizations"] == 2
    assert result["tasks_dispatched"] == 2
    assert result["dispatch_concurrency"] == 16
    session.commit.assert_awaited_once()
    assert dispatcher.dispatch_external_report_delivery_reconciliation.await_count == 2
    statement = session.execute.await_args.args[0]
    rendered = str(statement)
    compiled_values = tuple(statement.compile().params.values())
    assert any(
        value == "outcome_unknown"
        or (isinstance(value, tuple | list) and "outcome_unknown" in value)
        for value in compiled_values
    )
    assert "delivery_token_ciphertext IS NOT NULL" in rendered
    assert statement._limit_clause.value == 101


class _AsyncSessionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_reconciliation_active_lease_fails_transport_instead_of_acknowledging() -> None:
    org_id = uuid.uuid4()
    session = _AsyncSessionContext()
    reconcile = AsyncMock()
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch("api.db.session.bind_current_org_to_session", AsyncMock()),
        patch(
            "api.services.external_report_grants.reconcile_external_report_deliveries",
            reconcile,
        ),
        patch.object(
            tasks_module,
            "_acquire_external_report_delivery_reconciliation_lease",
            AsyncMock(return_value=False),
        ),
        pytest.raises(
            tasks_module.ExternalReportDeliveryReconciliationLeaseUnavailableError,
            match="lease is active",
        ),
    ):
        await tasks_module._reconcile_external_report_deliveries_for_org(
            str(org_id),
            dedupe_key=f"{org_id}-sweep-1",
        )

    reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_continuation_survives_crash_after_dispatch_before_lease_release() -> None:
    org_id = uuid.uuid4()
    session = _AsyncSessionContext()
    dispatcher = SimpleNamespace(
        dispatch_external_report_delivery_reconciliation=AsyncMock(return_value="continuation-task")
    )
    acquire = AsyncMock(side_effect=[True, False])
    release = AsyncMock(side_effect=RuntimeError("crash before release"))
    reconcile = AsyncMock(return_value={"processed": 20, "has_more": True})
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch("api.db.session.bind_current_org_to_session", AsyncMock()),
        patch(
            "api.services.external_report_grants.reconcile_external_report_deliveries",
            reconcile,
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch.object(
            tasks_module,
            "_acquire_external_report_delivery_reconciliation_lease",
            acquire,
        ),
        patch.object(
            tasks_module,
            "_external_report_delivery_reconciliation_lease_is_current",
            AsyncMock(return_value=True),
        ),
        patch.object(
            tasks_module,
            "_release_external_report_delivery_reconciliation_lease",
            release,
        ),
    ):
        with pytest.raises(RuntimeError, match="crash before release"):
            await tasks_module._reconcile_external_report_deliveries_for_org(
                str(org_id),
                dedupe_key=f"{org_id}-sweep-1",
            )

        continuation_call = (
            dispatcher.dispatch_external_report_delivery_reconciliation.await_args.kwargs
        )
        assert continuation_call["continuation"] == 1
        assert len(continuation_call["dedupe_key"]) == 32

        with pytest.raises(
            tasks_module.ExternalReportDeliveryReconciliationLeaseUnavailableError,
            match="lease is active",
        ):
            await tasks_module._reconcile_external_report_deliveries_for_org(
                str(org_id),
                dedupe_key=continuation_call["dedupe_key"],
                continuation=1,
            )

    assert reconcile.await_count == 1
    assert dispatcher.dispatch_external_report_delivery_reconciliation.await_count == 1


@pytest.mark.asyncio
async def test_expired_stale_worker_cannot_dispatch_competing_continuation() -> None:
    org_id = uuid.uuid4()
    session = _AsyncSessionContext()
    dispatcher = SimpleNamespace(dispatch_external_report_delivery_reconciliation=AsyncMock())
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch("api.db.session.bind_current_org_to_session", AsyncMock()),
        patch(
            "api.services.external_report_grants.reconcile_external_report_deliveries",
            AsyncMock(return_value={"processed": 20, "has_more": True}),
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch.object(
            tasks_module,
            "_acquire_external_report_delivery_reconciliation_lease",
            AsyncMock(return_value=True),
        ),
        patch.object(
            tasks_module,
            "_external_report_delivery_reconciliation_lease_is_current",
            AsyncMock(return_value=False),
        ),
        patch.object(
            tasks_module,
            "_release_external_report_delivery_reconciliation_lease",
            AsyncMock(),
        ) as release,
        pytest.raises(
            tasks_module.ExternalReportDeliveryReconciliationLeaseUnavailableError,
            match="lease expired",
        ),
    ):
        await tasks_module._reconcile_external_report_deliveries_for_org(
            str(org_id),
            dedupe_key=f"{org_id}-sweep-1",
        )

    dispatcher.dispatch_external_report_delivery_reconciliation.assert_not_awaited()
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_reconciliation_sweep_is_bounded_and_dispatches_one_continuation() -> None:
    org_ids = tuple(uuid.UUID(int=index) for index in range(1, 102))

    class Result:
        def scalars(self):
            return SimpleNamespace(all=lambda: org_ids)

    class DiscoverySession:
        def __init__(self) -> None:
            self.execute = AsyncMock(return_value=Result())
            self.commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = DiscoverySession()
    dispatcher = SimpleNamespace(
        dispatch_external_report_delivery_reconciliation=AsyncMock(
            side_effect=lambda **kwargs: f"task-{kwargs['org_id']}"
        ),
        dispatch_external_report_delivery_reconciliation_sweep=AsyncMock(
            return_value="continuation-task"
        ),
    )
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch(
            "api.workers.monitor_tasks._assert_worker_has_bypassrls",
            AsyncMock(),
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        result = await tasks_module._dispatch_external_report_delivery_reconciliation_async(
            sweep_id="2026071404-01"
        )

    expected_cursor = str(org_ids[99])
    assert result == {
        "organizations": 100,
        "tasks_dispatched": 100,
        "continuation_dispatched": True,
        "next_cursor": expected_cursor,
        "sweep_id": "2026071404-01",
        "dispatch_concurrency": 16,
    }
    assert dispatcher.dispatch_external_report_delivery_reconciliation.await_count == 100
    dispatcher.dispatch_external_report_delivery_reconciliation_sweep.assert_awaited_once_with(
        cursor=expected_cursor,
        sweep_id="2026071404-01",
        dedupe_key=f"2026071404-01-{expected_cursor}",
    )
    dispatched_keys = {
        call.kwargs["dedupe_key"]
        for call in dispatcher.dispatch_external_report_delivery_reconciliation.await_args_list
    }
    assert dispatched_keys == {f"{org_id}-2026071404-01" for org_id in org_ids[:100]}


@pytest.mark.asyncio
async def test_delivery_reconciliation_continuation_applies_exclusive_cursor() -> None:
    cursor = uuid.UUID(int=100)

    class Result:
        def scalars(self):
            return SimpleNamespace(all=tuple)

    class DiscoverySession:
        def __init__(self) -> None:
            self.execute = AsyncMock(return_value=Result())
            self.commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = DiscoverySession()
    dispatcher = SimpleNamespace(
        dispatch_external_report_delivery_reconciliation=AsyncMock(),
    )
    with (
        patch("api.db.session.async_session_factory", return_value=session),
        patch(
            "api.workers.monitor_tasks._assert_worker_has_bypassrls",
            AsyncMock(),
        ),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        result = await tasks_module._dispatch_external_report_delivery_reconciliation_async(
            cursor=str(cursor),
            sweep_id="2026071404-01",
        )

    statement = session.execute.await_args.args[0]
    assert "external_report_grants.org_id >" in str(statement)
    assert cursor in statement.compile().params.values()
    assert result["continuation_dispatched"] is False
    dispatcher.dispatch_external_report_delivery_reconciliation.assert_not_awaited()
