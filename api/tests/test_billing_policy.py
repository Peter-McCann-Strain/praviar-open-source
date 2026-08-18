"""Tests for billing policy helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.db.models import OrgPlan
from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_policy import (
    billing_origin_url,
    checkout_price_id,
    credit_pack_price_id,
    credit_pack_size,
    plan_limit_for,
    plan_to_display_tier,
    price_id_to_plan,
    resolve_analysis_capacity_entitlement,
)


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.plan_free_analyses_per_month = 3
    settings.plan_starter_analyses_per_month = 8
    settings.plan_pro_analyses_per_month = 20
    settings.stripe_price_starter = "price_starter"
    settings.stripe_price_pro = "price_pro"
    settings.stripe_price_credit_pack_single_analysis = "price_credit_single"
    settings.stripe_price_credit_pack_portfolio_5 = "price_credit_portfolio"
    settings.stripe_price_credit_pack_diligence_15 = "price_credit_diligence"
    settings.stripe_price_credit_pack_scale_30 = "price_credit_scale"
    settings.cors_origins = ["https://app.example.com"]
    return settings


def test_plan_limit_for_uses_configured_limits() -> None:
    settings = _settings()

    assert plan_limit_for("free", settings) == 3
    assert plan_limit_for("starter", settings) == 8
    assert plan_limit_for("pro", settings) == 20
    assert plan_limit_for("enterprise", settings) == 999_999


def test_price_id_to_plan_uses_price_mapping() -> None:
    settings = _settings()

    assert price_id_to_plan("price_starter", settings) == OrgPlan.STARTER
    assert price_id_to_plan("price_pro", settings) == OrgPlan.PRO
    assert price_id_to_plan("unknown", settings) == OrgPlan.FREE


def test_checkout_price_id_and_origin_url() -> None:
    settings = _settings()

    assert checkout_price_id(PlanTier.STARTER, settings) == "price_starter"
    assert checkout_price_id(PlanTier.PRO, settings) == "price_pro"
    assert billing_origin_url(settings) == "https://app.example.com"


def test_credit_pack_price_id_and_size() -> None:
    settings = _settings()

    assert credit_pack_size(CreditPackId.SINGLE_ANALYSIS) == 1
    assert credit_pack_size(CreditPackId.PORTFOLIO_5) == 5
    assert credit_pack_size(CreditPackId.DILIGENCE_15) == 15
    assert credit_pack_size(CreditPackId.SCALE_30) == 30
    assert credit_pack_price_id(CreditPackId.SINGLE_ANALYSIS, settings) == "price_credit_single"
    assert credit_pack_price_id(CreditPackId.PORTFOLIO_5, settings) == "price_credit_portfolio"
    assert credit_pack_price_id(CreditPackId.DILIGENCE_15, settings) == "price_credit_diligence"
    assert credit_pack_price_id(CreditPackId.SCALE_30, settings) == "price_credit_scale"


def test_plan_to_display_tier_matches_plan_value() -> None:
    assert plan_to_display_tier(OrgPlan.PRO) == "pro"


@pytest.mark.parametrize(
    "subscription_status",
    ["past_due", "incomplete", "incomplete_expired", "unpaid", "canceled"],
)
def test_lapsed_subscription_capacity_uses_free_allowance_and_keeps_credits(
    subscription_status: str,
) -> None:
    entitlement = resolve_analysis_capacity_entitlement(
        analyses_used=5,
        configured_included_limit=20,
        consumed_purchased_credits=0,
        plan_key="pro",
        purchased_credits_balance=2,
        subscription_status=subscription_status,
        plan_limit_for_fn=lambda plan: {"free": 3, "pro": 20}[plan],
    )

    assert entitlement.included_limit == 3
    assert entitlement.included_remaining == 0
    assert entitlement.purchased_credits_balance == 2
    assert entitlement.available == 2
    assert entitlement.effective_limit == 7
    assert entitlement.purchased_credits_required(1) == 1


@pytest.mark.parametrize("subscription_status", ["active", "trialing"])
def test_paying_subscription_capacity_keeps_stored_allowance(
    subscription_status: str,
) -> None:
    entitlement = resolve_analysis_capacity_entitlement(
        analyses_used=5,
        configured_included_limit=20,
        consumed_purchased_credits=0,
        plan_key="pro",
        purchased_credits_balance=2,
        subscription_status=subscription_status,
        plan_limit_for_fn=lambda plan: {"free": 3, "pro": 20}[plan],
    )

    assert entitlement.included_limit == 20
    assert entitlement.available == 17
    assert entitlement.effective_limit == 22


@pytest.mark.parametrize("subscription_status", [None, "canceled", "past_due"])
def test_enterprise_contract_capacity_is_independent_of_stripe_status(
    subscription_status: str | None,
) -> None:
    entitlement = resolve_analysis_capacity_entitlement(
        analyses_used=120,
        configured_included_limit=400,
        consumed_purchased_credits=0,
        plan_key="enterprise",
        purchased_credits_balance=0,
        subscription_status=subscription_status,
        plan_limit_for_fn=lambda plan: {"free": 3, "enterprise": 999_999}[plan],
    )

    assert entitlement.included_limit == 400
    assert entitlement.available == 280
    assert entitlement.effective_limit == 400
