from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_mock_db

from api.db.models import OrgPlan
from api.services.billing_queries import (
    get_billing_status_data,
    get_usage_summary_data,
)


def _make_org(**kw: object) -> MagicMock:
    org = MagicMock()
    org.id = kw.get("id", uuid.uuid4())
    org.plan = kw.get("plan", OrgPlan.STARTER)
    org.max_analyses_per_month = kw.get("max_analyses_per_month", 8)
    org.stripe_customer_id = kw.get("stripe_customer_id", "cus_test")
    org.stripe_subscription_id = kw.get("stripe_subscription_id", "sub_test")
    org.subscription_status = kw.get("subscription_status", "active")
    org.billing_cycle_start = kw.get(
        "billing_cycle_start",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    org.current_period_end = kw.get(
        "current_period_end",
        datetime(2026, 2, 1, tzinfo=UTC),
    )
    org.cancel_at_period_end = kw.get("cancel_at_period_end", False)
    return org


@pytest.mark.asyncio
async def test_get_billing_status_data_uses_shared_context_loader() -> None:
    db = make_mock_db()
    org = _make_org()
    get_org_fn = AsyncMock(return_value=org)
    context = MagicMock()
    context.plan_to_display_tier.return_value = "starter"
    context.plan_limit_for.return_value = 8
    load_context_fn = MagicMock(return_value=context)
    get_monthly_usage_fn = AsyncMock(return_value=5)

    result = await get_billing_status_data(
        db,
        org_id=org.id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
        get_monthly_usage_fn=get_monthly_usage_fn,
        get_credit_balance_fn=AsyncMock(return_value=0),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
    )

    assert result["org_id"] == org.id
    assert result["plan"] == "starter"
    assert result["analyses_used"] == 5
    assert result["analyses_limit"] == 8
    assert result["included_analyses_limit"] == 8
    assert result["purchased_credits_balance"] == 0
    assert result["purchased_credits_used"] == 0
    load_context_fn.assert_called_once_with()
    get_org_fn.assert_awaited_once_with(db, org.id)
    get_monthly_usage_fn.assert_awaited_once_with(db, org.id, org.billing_cycle_start)


@pytest.mark.asyncio
async def test_get_usage_summary_data_uses_shared_context_loader() -> None:
    db = make_mock_db()
    org = _make_org(
        billing_cycle_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
    )
    get_org_fn = AsyncMock(return_value=org)
    context = MagicMock()
    context.plan_to_display_tier.return_value = "starter"
    context.plan_limit_for.return_value = 8
    load_context_fn = MagicMock(return_value=context)
    get_monthly_usage_fn = AsyncMock(return_value=9)

    result = await get_usage_summary_data(
        db,
        org_id=org.id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
        get_monthly_usage_fn=get_monthly_usage_fn,
        get_credit_balance_fn=AsyncMock(return_value=0),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
    )

    assert result["plan"] == "starter"
    assert result["analyses_used"] == 9
    assert result["analyses_limit"] == 9
    assert result["included_analyses_limit"] == 8
    assert result["purchased_credits_balance"] == 0
    assert result["purchased_credits_used"] == 0
    assert result["overage_analyses"] == 0
    load_context_fn.assert_called_once_with()
    get_org_fn.assert_awaited_once_with(db, org.id)
    get_monthly_usage_fn.assert_awaited_once_with(db, org.id, org.billing_cycle_start)
