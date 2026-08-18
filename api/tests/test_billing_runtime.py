"""Tests for billing plumbing helpers that delegate through billing_facade.

The old billing_runtime module has been consolidated into billing_facade;
these tests verify the same delegation contracts now exercised via billing.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from api.db.models import OrgPlan
from api.services import billing_facade


def test_load_context_delegates_to_billing_service_context() -> None:
    with patch(
        "api.services.billing_facade.load_billing_service_context",
        return_value=MagicMock(marker="context"),
    ) as load_context:
        result = billing_facade.load_context(
            get_settings_fn=MagicMock(return_value=MagicMock()),
        )

    assert result.marker == "context"  # type: ignore[attr-defined]
    load_context.assert_called_once_with(get_settings_fn=ANY, configure_stripe=False)


def test_plan_helpers_use_loaded_context() -> None:
    context = MagicMock()
    context.plan_limit_for.return_value = 8
    context.price_id_to_plan.return_value = OrgPlan.STARTER
    context.plan_to_display_tier.return_value = "pro"
    load_context_fn = MagicMock(return_value=context)

    assert billing_facade.plan_limit_for("starter", load_context_fn=load_context_fn) == 8
    assert (
        billing_facade.price_id_to_plan("price_starter", load_context_fn=load_context_fn)
        == OrgPlan.STARTER
    )
    assert (
        billing_facade.plan_to_display_tier(OrgPlan.PRO, load_context_fn=load_context_fn) == "pro"
    )
    assert load_context_fn.call_count == 3


@pytest.mark.asyncio
async def test_customer_and_usage_helpers_delegate_to_facade() -> None:
    db = MagicMock()
    org = MagicMock()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    with (
        patch(
            "api.services.billing_facade.billing_sync.get_or_create_stripe_customer_impl",
            new=AsyncMock(return_value="cus_test"),
        ) as get_or_create_stripe_customer,
        patch(
            "api.services.billing_facade.billing_queries.get_monthly_usage",
            new=AsyncMock(return_value=7),
        ) as get_monthly_usage,
        patch(
            "api.services.billing_facade.billing_queries.record_usage_event",
            new=AsyncMock(),
        ) as record_usage_event,
        patch(
            "api.services.billing_facade.billing_queries.check_usage_limit",
            new=AsyncMock(return_value=(True, 5, 8)),
        ) as check_usage_limit,
    ):
        customer_id = await billing_facade.get_or_create_stripe_customer(
            db,
            org,
            create_customer_fn=MagicMock(),
        )
        usage = await billing_facade.get_monthly_usage(db, org_id, None)
        await billing_facade.record_usage_event(db, org_id, analysis_id)
        limit = await billing_facade.check_usage_limit(db, org_id)

    assert customer_id == "cus_test"
    assert usage == 7
    assert limit == (True, 5, 8)
    get_or_create_stripe_customer.assert_awaited_once()
    get_monthly_usage.assert_awaited_once()
    record_usage_event.assert_awaited_once()
    check_usage_limit.assert_awaited_once()
