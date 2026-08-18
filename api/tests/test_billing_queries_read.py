from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_mock_db

from api.db.models import OrgPlan
from api.services.billing_queries import (
    build_billing_status_data,
    build_usage_summary_data,
    get_monthly_usage,
    get_org_for_billing_or_404,
    map_invoice_list,
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
async def test_get_org_for_billing_or_404_raises_for_missing_org() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(Exception, match="Organization not found"):
        await get_org_for_billing_or_404(db, uuid.uuid4())


@pytest.mark.asyncio
async def test_get_monthly_usage_counts_completed_analyses() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one.return_value = 5
    db.execute = AsyncMock(return_value=result)

    assert await get_monthly_usage(db, uuid.uuid4()) == 5


@pytest.mark.asyncio
async def test_build_billing_status_data_uses_loaded_org() -> None:
    db = make_mock_db()
    org = _make_org()
    get_monthly_usage_fn = AsyncMock(return_value=4)
    context = MagicMock()
    context.plan_to_display_tier.return_value = "starter"
    context.plan_limit_for.return_value = 8

    result = await build_billing_status_data(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_to_display_tier_fn=context.plan_to_display_tier,
        plan_limit_for_fn=context.plan_limit_for,
        get_credit_balance_fn=AsyncMock(return_value=0),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
    )

    assert result["org_id"] == org.id
    assert result["plan"] == "starter"
    assert result["analyses_used"] == 4
    assert result["analyses_limit"] == 8
    assert result["included_analyses_limit"] == 8
    assert result["purchased_credits_balance"] == 0
    assert result["purchased_credits_used"] == 0
    get_monthly_usage_fn.assert_awaited_once_with(db, org.id, org.billing_cycle_start)


@pytest.mark.asyncio
async def test_build_usage_summary_data_uses_period_start_and_limits() -> None:
    db = make_mock_db()
    org = _make_org(
        billing_cycle_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
    )
    get_monthly_usage_fn = AsyncMock(return_value=9)
    context = MagicMock()
    context.plan_to_display_tier.return_value = "starter"
    context.plan_limit_for.return_value = 8

    result = await build_usage_summary_data(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_to_display_tier_fn=context.plan_to_display_tier,
        plan_limit_for_fn=context.plan_limit_for,
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
    get_monthly_usage_fn.assert_awaited_once_with(db, org.id, org.billing_cycle_start)


@pytest.mark.asyncio
async def test_build_billing_status_data_matches_lapsed_launch_capacity() -> None:
    db = make_mock_db()
    org = _make_org(
        plan=OrgPlan.PRO,
        max_analyses_per_month=20,
        subscription_status="past_due",
    )

    result = await build_billing_status_data(
        db,
        org=org,
        get_monthly_usage_fn=AsyncMock(return_value=5),
        plan_to_display_tier_fn=lambda plan: plan.value,
        plan_limit_for_fn=lambda plan: {"free": 3, "pro": 20}[plan],
        get_credit_balance_fn=AsyncMock(return_value=2),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
    )

    assert result["subscription_status"] == "past_due"
    assert result["analyses_used"] == 5
    assert result["included_analyses_limit"] == 3
    assert result["purchased_credits_balance"] == 2
    assert result["purchased_credits_used"] == 0
    assert result["analyses_limit"] == 7


@pytest.mark.asyncio
async def test_build_usage_summary_data_matches_lapsed_launch_capacity() -> None:
    db = make_mock_db()
    org = _make_org(
        plan=OrgPlan.PRO,
        max_analyses_per_month=20,
        subscription_status="unpaid",
    )

    result = await build_usage_summary_data(
        db,
        org=org,
        get_monthly_usage_fn=AsyncMock(return_value=5),
        plan_to_display_tier_fn=lambda plan: plan.value,
        plan_limit_for_fn=lambda plan: {"free": 3, "pro": 20}[plan],
        get_credit_balance_fn=AsyncMock(return_value=2),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
    )

    assert result["analyses_used"] == 5
    assert result["included_analyses_limit"] == 3
    assert result["purchased_credits_balance"] == 2
    assert result["purchased_credits_used"] == 0
    assert result["analyses_limit"] == 7
    assert result["usage_pct"] == 71.4
    assert result["overage_analyses"] == 0


def test_map_invoice_list_normalizes_missing_fields() -> None:
    invoice = MagicMock()
    invoice.id = "in_123"
    invoice.number = None
    invoice.status = None
    invoice.amount_due = None
    invoice.amount_paid = 1200
    invoice.currency = None
    invoice.created = 1
    invoice.hosted_invoice_url = None
    invoice.invoice_pdf = None
    invoices = MagicMock()
    invoices.data = [invoice]
    invoices.has_more = True

    result = map_invoice_list(invoices)

    assert result["has_more"] is True
    assert result["invoices"][0]["status"] == "unknown"
    assert result["invoices"][0]["amount_due_cents"] == 0
    assert result["invoices"][0]["currency"] == "usd"
