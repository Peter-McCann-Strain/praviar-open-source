"""Service-layer tests for batch lifecycle management."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, make_mock_db

from api.db.models import Analysis, AnalysisStatus, BatchAnalysis
from api.errors import APIError
from api.schemas.analyses import AnalysisConfigSchema
from api.schemas.batch import CreateBatchRequest
from api.services.batch import (
    BatchPage,
    _launch_idempotency_key_digest,
    _launch_payload_digest,
    cancel_batch,
    create_batch,
    get_batch_with_live_status,
    list_batches_page,
    recompute_batch_status,
    serialize_batch,
    serialize_batch_page,
)
from api.services.billing_queries import AnalysisCreditReservation

BATCH_IDEMPOTENCY_KEY = "batch-launch-test-key-123456"


def make_service_batch_mock(**kw) -> MagicMock:
    batch = MagicMock()
    batch.id = kw.get("id", uuid.uuid4())
    batch.org_id = kw.get("org_id", uuid.uuid4())
    batch.user_id = kw.get("user_id", uuid.uuid4())
    batch.name = kw.get("name", "Batch Test")
    batch.total_compounds = kw.get("total_compounds", 3)
    batch.completed_count = kw.get("completed_count", 0)
    batch.failed_count = kw.get("failed_count", 0)
    batch.status = kw.get("status", AnalysisStatus.PENDING)
    batch.analysis_ids = kw.get("analysis_ids", [])
    batch.created_at = kw.get("created_at", datetime.now(UTC))
    batch.updated_at = kw.get("updated_at", datetime.now(UTC))
    return batch


def test_recompute_batch_status_matrix():
    cases = [
        (2, 2, 0, 0, AnalysisStatus.COMPLETED),
        (2, 1, 0, 1, AnalysisStatus.RUNNING),
        (2, 0, 2, 0, AnalysisStatus.FAILED),
        (2, 0, 1, 0, AnalysisStatus.RUNNING),
        (2, 0, 0, 0, AnalysisStatus.PENDING),
    ]

    for total, completed, failed, running, expected in cases:
        assert (
            recompute_batch_status(
                total_compounds=total,
                completed_count=completed,
                failed_count=failed,
                running_count=running,
            )
            == expected
        )


@pytest.mark.asyncio
async def test_create_batch_replays_same_org_key_without_capacity_and_redrives_pending() -> None:
    db = make_mock_db()
    org_id = uuid.uuid4()
    body = CreateBatchRequest(name="Replay-safe batch", compounds=["aspirin", "ibuprofen"])
    key = "batch-launch-replay-test-123456"
    existing = make_service_batch_mock(org_id=org_id, status=AnalysisStatus.PENDING)
    existing.launch_idempotency_key_digest = _launch_idempotency_key_digest(
        org_id=org_id,
        idempotency_key=key,
    )
    existing.launch_payload_digest = _launch_payload_digest(body)
    pending_child = make_analysis_mock(org_id=org_id, status=AnalysisStatus.PENDING)
    completed_child = make_analysis_mock(org_id=org_id, status=AnalysisStatus.COMPLETED)
    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(return_value="task-1")

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()) as lock_org,
        patch(
            "api.services.batch.load_batch_by_launch_key",
            new=AsyncMock(return_value=existing),
        ),
        patch(
            "api.services.batch.load_batch_analyses_for_update",
            new=AsyncMock(return_value=[pending_child, completed_child]),
        ),
        patch("api.services.batch.reserve_analysis_capacity", new=AsyncMock()) as capacity,
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        creation = await create_batch(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=body,
            request=MagicMock(),
            idempotency_key=key,
        )

    assert creation.batch is existing
    assert creation.replayed is True
    lock_org.assert_awaited_once()
    capacity.assert_not_awaited()
    dispatcher.dispatch_pipeline_run.assert_awaited_once_with(
        analysis_id=str(pending_child.id),
        org_id=str(org_id),
        reconciliation_key="repair-1",
    )
    assert pending_child.pipeline_reconciliation_generation == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_batch_rejects_same_key_with_different_payload() -> None:
    db = make_mock_db()
    org_id = uuid.uuid4()
    key = "batch-launch-conflict-test-123456"
    original = CreateBatchRequest(name="Original", compounds=["aspirin"])
    conflicting = CreateBatchRequest(name="Changed", compounds=["aspirin"])
    existing = make_service_batch_mock(org_id=org_id)
    existing.launch_payload_digest = _launch_payload_digest(original)

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
        patch(
            "api.services.batch.load_batch_by_launch_key",
            new=AsyncMock(return_value=existing),
        ),
        patch("api.services.batch.reserve_analysis_capacity", new=AsyncMock()) as capacity,
        pytest.raises(APIError) as exc_info,
    ):
        await create_batch(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=conflicting,
            request=MagicMock(),
            idempotency_key=key,
        )

    assert exc_info.value.status == 409
    capacity.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_batch_serializes_receipt_lookup_before_capacity_reservation() -> None:
    db = make_mock_db()
    db.refresh = AsyncMock()
    events: list[str] = []

    async def lock_org(*_args, **_kwargs):
        events.append("org_lock")

    async def load_receipt(*_args, **_kwargs):
        events.append("receipt_lookup")
        return None

    async def reserve_capacity(*_args, **_kwargs):
        events.append("capacity_reservation")
        return True, 0, 10

    with (
        patch("api.services.batch._lock_batch_launch_org", new=lock_org),
        patch("api.services.batch.load_batch_by_launch_key", new=load_receipt),
        patch("api.services.batch.reserve_analysis_capacity", new=reserve_capacity),
        patch("api.services.batch.write_audit_log", new=AsyncMock()),
        patch("api.workers.tasks.run_fto_pipeline") as run_fto_pipeline,
    ):
        run_fto_pipeline.delay = MagicMock()
        creation = await create_batch(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=CreateBatchRequest(name="Concurrent launch", compounds=["aspirin"]),
            request=MagicMock(),
            idempotency_key="batch-launch-concurrency-test-123456",
        )

    assert creation.replayed is False
    assert events == ["org_lock", "receipt_lookup", "capacity_reservation"]


@pytest.mark.asyncio
async def test_concurrent_same_key_batch_launches_share_one_receipt_and_capacity_charge() -> None:
    org_id = uuid.uuid4()
    body = CreateBatchRequest(name="Concurrent batch", compounds=["aspirin"])
    key = "batch-launch-concurrent-replay-123456"
    transaction_lock = asyncio.Lock()
    shared: dict[str, object] = {}
    databases = [make_mock_db(), make_mock_db()]
    for db in databases:
        db.refresh = AsyncMock()

        async def commit(*, session=db):
            if "batch" not in shared:
                added = [call.args[0] for call in session.add.call_args_list]
                shared["batch"] = next(item for item in added if isinstance(item, BatchAnalysis))
                shared["analyses"] = [item for item in added if isinstance(item, Analysis)]
            if transaction_lock.locked():
                transaction_lock.release()

        db.commit = AsyncMock(side_effect=commit)

    async def lock_org(db, **_kwargs):
        await transaction_lock.acquire()

    async def load_receipt(*_args, **_kwargs):
        return shared.get("batch")

    async def load_children(*_args, **_kwargs):
        return list(shared.get("analyses", []))

    dispatcher = MagicMock()
    dispatcher.dispatch_pipeline_run = AsyncMock(return_value="task-1")
    reserve_capacity = AsyncMock(return_value=(True, 0, 10))
    with (
        patch("api.services.batch._lock_batch_launch_org", new=lock_org),
        patch("api.services.batch.load_batch_by_launch_key", new=load_receipt),
        patch("api.services.batch.load_batch_analyses_for_update", new=load_children),
        patch("api.services.batch.reserve_analysis_capacity", new=reserve_capacity),
        patch("api.services.batch.load_org_default_config", new=AsyncMock(return_value=None)),
        patch("api.services.batch.write_audit_log", new=AsyncMock()),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        results = await asyncio.gather(
            *(
                create_batch(
                    db,
                    org_id=org_id,
                    user_id=uuid.uuid4(),
                    body=body,
                    request=MagicMock(),
                    idempotency_key=key,
                )
                for db in databases
            )
        )

    assert results[0].batch is results[1].batch
    assert {result.replayed for result in results} == {False, True}
    reserve_capacity.assert_awaited_once()
    assert len(shared["analyses"]) == 1
    assert dispatcher.dispatch_pipeline_run.await_count == 2


@pytest.mark.asyncio
async def test_create_batch_commits_and_dispatches():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    body = CreateBatchRequest(
        name="Aspirin Batch",
        compounds=["aspirin", "ibuprofen"],
        config=AnalysisConfigSchema(search_jurisdictions=["EP"]),
    )
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
        patch("api.services.batch.write_audit_log", new=AsyncMock()) as audit_log,
        patch("api.workers.tasks.run_fto_pipeline") as run_fto_pipeline,
        patch(
            "api.services.batch.reserve_analysis_capacity",
            new=AsyncMock(return_value=(True, 0, 100)),
        ),
    ):
        run_fto_pipeline.delay = MagicMock()
        creation = await create_batch(
            db,
            org_id=org_id,
            user_id=user_id,
            body=body,
            request=request,
            idempotency_key=BATCH_IDEMPOTENCY_KEY,
        )
        batch = creation.batch

    assert batch.name == "Aspirin Batch"
    assert batch.total_compounds == 2
    assert len(batch.analysis_ids) == 2
    assert batch.status == AnalysisStatus.PENDING
    assert creation.replayed is False
    assert db.commit.await_count == 1
    assert db.refresh.await_count == 1
    assert run_fto_pipeline.delay.call_count == 2
    analyses = [call.args[0] for call in db.add.call_args_list if hasattr(call.args[0], "config")]
    assert len(analyses) == 2
    assert analyses[0].config["trust_mode"] == "explorer"
    assert analyses[0].config["matter_type"] == "small_molecule"
    assert analyses[0].config["search_jurisdictions"] == ["EP", "WO"]
    assert "report_pipeline_v2" not in analyses[0].config
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True


@pytest.mark.asyncio
async def test_create_batch_applies_org_defaults_through_analysis_runtime_config():
    db = make_mock_db()
    db.refresh = AsyncMock()
    org_default_result = MagicMock()
    org_default_result.scalar_one_or_none.return_value = {
        "default_config": {
            "max_analysis_patents": 12,
            "search_jurisdictions": ["US"],
        }
    }
    db.execute.return_value = org_default_result
    request = MagicMock()
    body = CreateBatchRequest(
        name="Defaulted Batch",
        compounds=["aspirin"],
        config=AnalysisConfigSchema(search_jurisdictions=["EP"]),
    )

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
        patch("api.services.batch.write_audit_log", new=AsyncMock()),
        patch("api.workers.tasks.run_fto_pipeline") as run_fto_pipeline,
        patch(
            "api.services.batch.reserve_analysis_capacity",
            new=AsyncMock(return_value=(True, 0, 100)),
        ),
    ):
        run_fto_pipeline.delay = MagicMock()
        await create_batch(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=body,
            request=request,
            idempotency_key=BATCH_IDEMPOTENCY_KEY,
        )

    analysis = next(
        call.args[0] for call in db.add.call_args_list if hasattr(call.args[0], "config")
    )
    assert "claim_analysis_depth" not in analysis.config
    assert analysis.config["max_analysis_patents"] == 12
    assert analysis.config["search_jurisdictions"] == ["EP", "WO"]
    assert analysis.config["target_jurisdictions"] == ["EP"]


def test_create_batch_strips_legacy_org_default_config():
    """Retired config keys in persisted org defaults are stripped silently (not 500)."""
    from api.services.configs import org_default_config_from_settings

    config = org_default_config_from_settings(
        {
            "default_config": {
                "claim_analysis_depth": "deep",
                "report_pipeline_v2": False,
            }
        }
    )
    assert "claim_analysis_depth" not in config
    assert "report_pipeline_v2" not in config


@pytest.mark.asyncio
async def test_create_batch_rolls_back_and_skips_dispatch_when_audit_fails():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    body = CreateBatchRequest(
        name="Aspirin Batch",
        compounds=["aspirin", "ibuprofen"],
    )

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
        patch(
            "api.services.batch.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        patch("api.workers.tasks.run_fto_pipeline") as run_fto_pipeline,
        patch(
            "api.services.batch.reserve_analysis_capacity",
            new=AsyncMock(return_value=(True, 0, 100)),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        run_fto_pipeline.delay = MagicMock()
        await create_batch(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=body,
            request=request,
            idempotency_key=BATCH_IDEMPOTENCY_KEY,
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    run_fto_pipeline.delay.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_batch_preserves_receipts_and_child_credit_bindings_on_ambiguous_dispatch():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    body = CreateBatchRequest(
        name="Aspirin Batch",
        compounds=["aspirin", "ibuprofen"],
    )
    org_id = uuid.uuid4()
    reservation = AnalysisCreditReservation(
        org_id=org_id,
        reservation_id="batch-credit-reservation-1",
        credits=2,
    )

    async def reserve_credits(*_args, credit_reservations=None, **kwargs):
        assert kwargs["requested_analyses"] == 2
        assert kwargs["reservation_details"] == {"source": "batch.create"}
        assert kwargs["reservation_id"]
        assert kwargs["defer_credit_consumption"] is True
        assert credit_reservations is not None
        credit_reservations.append(reservation)
        return True, 8, 10

    with (
        patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
        patch("api.services.batch.write_audit_log", new=AsyncMock()),
        patch(
            "api.services.batch.reserve_analysis_capacity",
            new=AsyncMock(side_effect=reserve_credits),
        ),
        patch("api.services.batch.consume_analysis_credits", new=AsyncMock()) as consume_credit,
        patch("api.workers.tasks.run_fto_pipeline") as run_fto_pipeline,
        pytest.raises(APIError) as exc_info,
    ):
        first_task = MagicMock()
        first_task.id = "task-1"
        run_fto_pipeline.delay.side_effect = [
            first_task,
            RuntimeError("celery unavailable"),
        ]
        await create_batch(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=body,
            request=request,
            idempotency_key=BATCH_IDEMPOTENCY_KEY,
        )

    assert exc_info.value.status == 503
    batch = db.add.call_args_list[0].args[0]
    assert consume_credit.await_count == 2
    consumed_analysis_ids = [call.kwargs["analysis_id"] for call in consume_credit.await_args_list]
    assert [str(analysis_id) for analysis_id in consumed_analysis_ids] == batch.analysis_ids
    assert [call.kwargs["credits"] for call in consume_credit.await_args_list] == [1, 1]
    assert [call.kwargs["reservation_id"] for call in consume_credit.await_args_list] == [
        "batch-credit-reservation-1:0",
        "batch-credit-reservation-1:1",
    ]
    assert run_fto_pipeline.delay.call_count == 2
    assert batch.status == AnalysisStatus.PENDING
    child_analyses = [
        call.args[0] for call in db.add.call_args_list if hasattr(call.args[0], "batch_id")
    ]
    assert all(analysis.status == AnalysisStatus.PENDING for analysis in child_analyses)
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_get_batch_with_live_status_recomputes_and_commits():
    db = make_mock_db()
    batch_id = uuid.uuid4()
    analysis_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    batch = make_service_batch_mock(
        id=batch_id,
        analysis_ids=analysis_ids,
        total_compounds=2,
        status=AnalysisStatus.PENDING,
    )

    batch_result = MagicMock()
    batch_result.scalar_one_or_none.return_value = batch
    counts_result = [
        SimpleNamespace(status=AnalysisStatus.COMPLETED, cnt=1),
        SimpleNamespace(status=AnalysisStatus.FAILED, cnt=1),
    ]
    db.execute = AsyncMock(side_effect=[batch_result, counts_result])
    db.refresh = AsyncMock()

    live_batch = await get_batch_with_live_status(
        db,
        batch_id=batch_id,
        org_id=batch.org_id,
    )

    assert live_batch.completed_count == 1
    assert live_batch.failed_count == 1
    assert live_batch.status == AnalysisStatus.FAILED
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(batch)


@pytest.mark.asyncio
async def test_cancel_batch_cancels_running_child_analyses():
    db = make_mock_db()
    batch_id = uuid.uuid4()
    user_id = uuid.uuid4()
    analysis_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    batch = make_service_batch_mock(id=batch_id, analysis_ids=analysis_ids)

    batch_result = MagicMock()
    batch_result.scalar_one_or_none.return_value = batch
    pending_analysis = make_analysis_mock(status=AnalysisStatus.PENDING)
    running_analysis = make_analysis_mock(status=AnalysisStatus.RUNNING)
    cancel_result = MagicMock()
    cancel_result.scalars.return_value.all.return_value = [pending_analysis, running_analysis]
    db.execute = AsyncMock(side_effect=[batch_result, cancel_result])

    with (
        patch("api.services.batch.write_audit_log", new=AsyncMock()) as audit_log,
        patch(
            "api.services.batch.refund_cancelled_analysis_credits",
            new=AsyncMock(return_value=0),
        ),
    ):
        cancelled_batch = await cancel_batch(
            db,
            batch_id=batch_id,
            org_id=batch.org_id,
            user_id=user_id,
            request=MagicMock(),
        )

    assert cancelled_batch.status == AnalysisStatus.CANCELLED
    assert pending_analysis.status == AnalysisStatus.CANCELLED
    assert running_analysis.status == AnalysisStatus.CANCELLED
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["user_id"] == user_id
    cancel_query = str(db.execute.await_args_list[1].args[0])
    assert "analyses.org_id" in cancel_query
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_batch_refunds_each_cancelled_child_credit_in_same_transaction():
    db = make_mock_db()
    batch = make_service_batch_mock(analysis_ids=[str(uuid.uuid4()), str(uuid.uuid4())])
    batch_result = MagicMock()
    batch_result.scalar_one_or_none.return_value = batch
    children = [
        make_analysis_mock(status=AnalysisStatus.PENDING),
        make_analysis_mock(status=AnalysisStatus.RUNNING),
    ]
    cancel_result = MagicMock()
    cancel_result.scalars.return_value.all.return_value = children
    db.execute = AsyncMock(side_effect=[batch_result, cancel_result])

    with (
        patch("api.services.batch.write_audit_log", new=AsyncMock()) as audit_log,
        patch(
            "api.services.batch.refund_cancelled_analysis_credits",
            new=AsyncMock(side_effect=[1, 0]),
        ) as refund_credits,
    ):
        await cancel_batch(
            db,
            batch_id=batch.id,
            org_id=batch.org_id,
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    assert [call.kwargs["analysis_id"] for call in refund_credits.await_args_list] == [
        children[0].id,
        children[1].id,
    ]
    assert all(
        call.kwargs["details"] == {"source": "batch.cancel", "batch_id": str(batch.id)}
        for call in refund_credits.await_args_list
    )
    assert all(child.status == AnalysisStatus.CANCELLED for child in children)
    assert audit_log.await_args.kwargs["details"]["refunded_purchased_credits"] == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_batch_rolls_back_when_audit_fails():
    db = make_mock_db()
    batch_id = uuid.uuid4()
    batch = make_service_batch_mock(id=batch_id, analysis_ids=[])

    batch_result = MagicMock()
    batch_result.scalar_one_or_none.return_value = batch
    db.execute = AsyncMock(return_value=batch_result)

    with (
        patch(
            "api.services.batch.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await cancel_batch(
            db,
            batch_id=batch_id,
            org_id=batch.org_id,
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_batches_page_returns_page():
    db = make_mock_db()
    batch_one = make_service_batch_mock(name="Batch 1")
    batch_two = make_service_batch_mock(name="Batch 2")
    count_result = MagicMock()
    count_result.scalar_one.return_value = 2
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [batch_one, batch_two]
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    page = await list_batches_page(db, org_id=batch_one.org_id, page=1, per_page=20)

    assert isinstance(page, BatchPage)
    assert page.total == 2
    assert page.items == [batch_one, batch_two]
    assert serialize_batch_page(page)["total"] == 2
    assert serialize_batch(batch_one)["name"] == "Batch 1"
