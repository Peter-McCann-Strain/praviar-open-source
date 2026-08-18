"""Service-layer tests for billing orchestration and Stripe integration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db

from api.db.models import OrgPlan
from api.errors import APIError
from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing import (
    create_checkout_session_data,
    create_credit_pack_checkout_session_data,
    create_portal_session_data,
    get_billing_status_data,
    get_usage_summary_data,
    list_invoice_data,
    sync_subscription_status,
)
from api.services.billing_policy import load_billing_service_context


def make_billing_org_mock(**kw: object) -> MagicMock:
    org = MagicMock()
    org.id = kw.get("id", uuid.uuid4())
    org.name = kw.get("name", "Test Org")
    org.clerk_org_id = kw.get("clerk_org_id", "clerk_org_test")
    org.plan = kw.get("plan", OrgPlan.STARTER)
    org.max_analyses_per_month = kw.get("max_analyses_per_month", 8)
    org.stripe_customer_id = kw.get("stripe_customer_id")
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


def make_settings_mock(**kw: object) -> MagicMock:
    settings = MagicMock()
    settings.stripe_secret_key = kw.get("stripe_secret_key", "sk_test")
    settings.stripe_price_starter = kw.get("stripe_price_starter", "price_starter")
    settings.stripe_price_pro = kw.get("stripe_price_pro", "price_pro")
    settings.stripe_price_credit_pack_single_analysis = kw.get(
        "stripe_price_credit_pack_single_analysis",
        "price_credit_single",
    )
    settings.stripe_price_credit_pack_portfolio_5 = kw.get(
        "stripe_price_credit_pack_portfolio_5",
        "price_credit_portfolio",
    )
    settings.stripe_price_credit_pack_diligence_15 = kw.get(
        "stripe_price_credit_pack_diligence_15",
        "price_credit_diligence",
    )
    settings.stripe_price_credit_pack_scale_30 = kw.get(
        "stripe_price_credit_pack_scale_30",
        "price_credit_scale",
    )
    settings.cors_origins = kw.get("cors_origins", ["https://app.example.com"])
    settings.plan_free_analyses_per_month = kw.get("plan_free_analyses_per_month", 3)
    settings.plan_starter_analyses_per_month = kw.get("plan_starter_analyses_per_month", 8)
    settings.plan_pro_analyses_per_month = kw.get("plan_pro_analyses_per_month", 20)
    return settings


def make_billing_context_mock(**kw: object):
    return load_billing_service_context(
        get_settings_fn=lambda: make_settings_mock(**kw),
        configure_stripe=bool(kw.get("configure_stripe", False)),
    )


@pytest.mark.asyncio
async def test_get_billing_status_data_returns_snapshot():
    db = make_mock_db()
    org = make_billing_org_mock()

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    usage_result = MagicMock()
    usage_result.scalar_one.return_value = 5
    credit_result = MagicMock()
    credit_result.scalar_one.return_value = 0
    consumed_result = MagicMock()
    consumed_result.scalar_one.return_value = 0
    db.execute = AsyncMock(side_effect=[org_result, usage_result, credit_result, consumed_result])

    with patch(
        "api.services.billing_facade.load_context",
        return_value=make_billing_context_mock(),
    ):
        result = await get_billing_status_data(db, org_id=org.id)

    assert result["org_id"] == org.id
    assert result["plan"] == "starter"
    assert result["analyses_used"] == 5
    assert result["analyses_limit"] == 8
    assert result["included_analyses_limit"] == 8
    assert result["purchased_credits_balance"] == 0
    assert result["purchased_credits_used"] == 0
    assert result["subscription_status"] == "active"
    assert result["current_period_start"] == org.billing_cycle_start
    assert result["cancel_at_period_end"] is False


@pytest.mark.asyncio
async def test_create_checkout_session_data_commits_and_audits():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id=None)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)
    request = MagicMock()
    session = MagicMock(id="cs_test", url="https://checkout.example.com/session")

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch(
            "api.services.billing.get_or_create_stripe_customer",
            new=AsyncMock(return_value="cus_test"),
        ) as create_customer,
        patch("api.services.billing.write_audit_log", new=AsyncMock()) as audit_log,
        patch(
            "api.services.billing.stripe.checkout.Session.create",
            return_value=session,
        ) as stripe_create,
    ):
        result = await create_checkout_session_data(
            db,
            org_id=org.id,
            user_id=uuid.uuid4(),
            plan_id=PlanTier.STARTER,
            success_url="",
            cancel_url="",
            request=request,
        )

    assert result == {
        "checkout_url": "https://checkout.example.com/session",
        "session_id": "cs_test",
    }
    create_customer.assert_awaited_once()
    audit_log.assert_awaited_once()
    stripe_create.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_checkout_session_data_rejects_free_plan_without_org_lookup():
    db = make_mock_db()
    db.execute = AsyncMock()

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await create_checkout_session_data(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=PlanTier.FREE,
            success_url="",
            cancel_url="",
            request=MagicMock(),
        )

    assert "free plan" in str(exc_info.value)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_credit_pack_checkout_session_data_commits_and_audits():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id=None)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)
    request = MagicMock()
    session = MagicMock(id="cs_credit", url="https://checkout.example.com/credits")

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch(
            "api.services.billing.get_or_create_stripe_customer",
            new=AsyncMock(return_value="cus_test"),
        ) as create_customer,
        patch("api.services.billing.write_audit_log", new=AsyncMock()) as audit_log,
        patch(
            "api.services.billing.stripe.checkout.Session.create",
            return_value=session,
        ) as stripe_create,
    ):
        result = await create_credit_pack_checkout_session_data(
            db,
            org_id=org.id,
            user_id=uuid.uuid4(),
            credit_pack_id=CreditPackId.PORTFOLIO_5,
            success_url="",
            cancel_url="",
            request=request,
        )

    assert result == {
        "checkout_url": "https://checkout.example.com/credits",
        "session_id": "cs_credit",
    }
    create_customer.assert_awaited_once()
    audit_log.assert_awaited_once()
    stripe_create.assert_called_once()
    assert stripe_create.call_args.kwargs["mode"] == "payment"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_portal_session_data_creates_customer_and_commits():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id=None)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)
    request = MagicMock()
    portal = MagicMock(id="bps_test", url="https://billing.example.com/portal")

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch(
            "api.services.billing.get_or_create_stripe_customer",
            new=AsyncMock(return_value="cus_test"),
        ) as create_customer,
        patch("api.services.billing.write_audit_log", new=AsyncMock()) as audit_log,
        patch(
            "api.services.billing.stripe.billing_portal.Session.create",
            return_value=portal,
        ) as stripe_create,
    ):
        result = await create_portal_session_data(
            db,
            org_id=org.id,
            user_id=uuid.uuid4(),
            request=request,
        )

    assert result == {"portal_url": "https://billing.example.com/portal"}
    create_customer.assert_awaited_once()
    audit_log.assert_awaited_once()
    stripe_create.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_portal_session_data_does_not_commit_customer_before_portal_success():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id=None)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch(
            "api.services.billing.get_or_create_stripe_customer",
            new=AsyncMock(return_value="cus_test"),
        ),
        patch(
            "api.services.billing.stripe.billing_portal.Session.create",
            side_effect=Exception("portal boom"),
        ),
        pytest.raises(Exception, match="portal boom"),
    ):
        await create_portal_session_data(
            db,
            org_id=org.id,
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_usage_summary_data_calculates_overage_and_cost():
    db = make_mock_db()
    org = make_billing_org_mock(
        plan=OrgPlan.STARTER,
        max_analyses_per_month=8,
        billing_cycle_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
    )

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    usage_result = MagicMock()
    usage_result.scalar_one.return_value = 9
    credit_result = MagicMock()
    credit_result.scalar_one.return_value = 0
    consumed_result = MagicMock()
    consumed_result.scalar_one.return_value = 0
    db.execute = AsyncMock(side_effect=[org_result, usage_result, credit_result, consumed_result])

    with patch(
        "api.services.billing_facade.load_context",
        return_value=make_billing_context_mock(),
    ):
        result = await get_usage_summary_data(db, org_id=org.id)

    assert result["plan"] == "starter"
    assert result["analyses_used"] == 9
    assert result["analyses_limit"] == 9
    assert result["included_analyses_limit"] == 8
    assert result["purchased_credits_balance"] == 0
    assert result["purchased_credits_used"] == 0
    assert result["usage_pct"] == 100.0
    assert result["cost_this_month_cents"] == 45_000
    assert result["overage_analyses"] == 0
    assert result["period_start"] == org.billing_cycle_start
    assert result["period_end"] == org.current_period_end


@pytest.mark.asyncio
async def test_list_invoice_data_maps_stripe_items():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id="cus_test")
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)
    invoice = MagicMock(
        id="in_test",
        number="INV-001",
        status="paid",
        amount_due=0,
        amount_paid=12_000,
        currency="usd",
        created=1_700_000_000,
        hosted_invoice_url="https://stripe.example.com/invoice",
        invoice_pdf="https://stripe.example.com/pdf",
    )
    invoices = MagicMock(data=[invoice], has_more=True)

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch("api.services.billing.stripe.Invoice.list", return_value=invoices),
    ):
        result = await list_invoice_data(db, org_id=org.id)

    assert result["has_more"] is True
    assert result["invoices"][0]["id"] == "in_test"
    assert result["invoices"][0]["status"] == "paid"
    assert result["invoices"][0]["amount_paid_cents"] == 12_000


@pytest.mark.asyncio
async def test_list_invoice_data_returns_empty_when_not_configured():
    db = make_mock_db()
    with patch(
        "api.services.billing_facade.load_context",
        return_value=make_billing_context_mock(stripe_secret_key=""),
    ):
        result = await list_invoice_data(db, org_id=uuid.uuid4())

    assert result == {"invoices": [], "has_more": False}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_subscription_status_updates_plan_from_subscription_price():
    db = make_mock_db()
    org = make_billing_org_mock(
        plan=OrgPlan.STARTER,
        max_analyses_per_month=8,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
    )
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)
    subscription = SimpleNamespace(
        status="active",
        current_period_start=1_700_000_000,
        current_period_end=1_702_000_000,
        cancel_at_period_end=False,
        items=SimpleNamespace(data=[SimpleNamespace(price=SimpleNamespace(id="price_pro"))]),
    )

    with (
        patch(
            "api.services.billing_facade.load_context",
            return_value=make_billing_context_mock(configure_stripe=True),
        ),
        patch(
            "api.services.billing.stripe.Subscription.retrieve",
            return_value=subscription,
        ),
    ):
        result = await sync_subscription_status(db, org.id)

    assert result["plan"] == "pro"
    assert result["subscription_status"] == "active"
    assert org.plan == OrgPlan.PRO
    assert org.max_analyses_per_month == 20
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_subscription_status_returns_message_when_customer_missing():
    db = make_mock_db()
    org = make_billing_org_mock(stripe_customer_id=None, stripe_subscription_id=None)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    db.execute = AsyncMock(return_value=org_result)

    result = await sync_subscription_status(db, org.id)

    assert result["message"] == "No Stripe customer linked"
