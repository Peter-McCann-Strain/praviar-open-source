from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.db.models import OrgPlan
from api.services import billing_sync


@pytest.mark.asyncio
async def test_get_or_create_customer_returns_existing_identifier():
    db = SimpleNamespace(flush=AsyncMock())
    org = SimpleNamespace(id=uuid.uuid4(), stripe_customer_id="cus_existing")

    result = await billing_sync.get_or_create_stripe_customer_impl(
        db,
        org,
        create_customer_fn=MagicMock(),
    )

    assert result == "cus_existing"
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_customer_persists_new_identifier(monkeypatch):
    customer = SimpleNamespace(id="cus_created")
    sdk_call = AsyncMock(return_value=customer)
    monkeypatch.setattr(billing_sync, "run_blocking_sdk_call", sdk_call)
    db = SimpleNamespace(flush=AsyncMock())
    org = SimpleNamespace(
        id=uuid.uuid4(),
        name="Example Org",
        clerk_org_id="org_clerk",
        stripe_customer_id=None,
    )

    result = await billing_sync.get_or_create_stripe_customer_impl(
        db,
        org,
        create_customer_fn=MagicMock(),
    )

    assert result == "cus_created"
    assert org.stripe_customer_id == "cus_created"
    db.flush.assert_awaited_once()
    assert sdk_call.await_args.kwargs["idempotency_key"] == f"customer:{org.id}"
    assert sdk_call.await_args.kwargs["metadata"]["org_id"] == str(org.id)


@pytest.mark.asyncio
async def test_subscription_sync_returns_when_subscription_is_absent():
    org = SimpleNamespace(
        id=uuid.uuid4(),
        plan=OrgPlan.STARTER,
        stripe_customer_id="cus_1",
        stripe_subscription_id=None,
    )

    result = await billing_sync.sync_subscription_status_impl(
        SimpleNamespace(),
        org=org,
        retrieve_subscription_fn=MagicMock(),
        price_id_to_plan_fn=MagicMock(),
        plan_limit_for_fn=MagicMock(),
    )

    assert result == {
        "plan": OrgPlan.STARTER.value,
        "subscription_status": None,
        "message": "No active subscription",
    }


@pytest.mark.asyncio
async def test_subscription_sync_rolls_back_when_commit_fails(monkeypatch):
    subscription = SimpleNamespace(
        status="active",
        current_period_start=1_700_000_000,
        current_period_end=1_700_086_400,
        cancel_at_period_end=False,
        items=SimpleNamespace(data=[]),
    )
    monkeypatch.setattr(
        billing_sync,
        "run_blocking_sdk_call",
        AsyncMock(return_value=subscription),
    )
    db = SimpleNamespace(
        flush=AsyncMock(),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        rollback=AsyncMock(),
    )
    org = SimpleNamespace(
        id=uuid.uuid4(),
        plan=OrgPlan.STARTER,
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await billing_sync.sync_subscription_status_impl(
            db,
            org=org,
            retrieve_subscription_fn=MagicMock(),
            price_id_to_plan_fn=MagicMock(),
            plan_limit_for_fn=MagicMock(),
        )

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrated_sync_normalizes_stripe_timeout(monkeypatch):
    org_id = uuid.uuid4()
    org = SimpleNamespace(stripe_subscription_id="sub_1")
    monkeypatch.setattr(
        billing_sync,
        "get_org_for_sync",
        AsyncMock(return_value=org),
    )
    log_error = MagicMock()
    monkeypatch.setattr(billing_sync, "log_stripe_operation_error", log_error)
    monkeypatch.setattr(
        billing_sync,
        "build_stripe_sync_error_response",
        lambda exc: {"error": type(exc).__name__},
    )
    mutation = AsyncMock(side_effect=TimeoutError("stripe timed out"))

    result = await billing_sync.sync_subscription_status_orchestrated(
        SimpleNamespace(),
        org_id=org_id,
        get_org_by_id_fn=AsyncMock(),
        retrieve_subscription_fn=MagicMock(),
        price_id_to_plan_fn=MagicMock(),
        plan_limit_for_fn=MagicMock(),
        sync_subscription_mutation_fn=mutation,
        logger=MagicMock(),
    )

    assert result == {"error": "TimeoutError"}
    log_error.assert_called_once()
    assert log_error.call_args.kwargs["extra_fields"] == {"subscription_id": "sub_1"}
