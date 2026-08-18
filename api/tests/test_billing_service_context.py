"""Tests for shared billing service runtime context."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.db.models import OrgPlan
from api.schemas.billing import PlanTier
from api.services.billing_policy import load_billing_service_context


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.plan_free_analyses_per_month = 3
    settings.plan_starter_analyses_per_month = 8
    settings.plan_pro_analyses_per_month = 20
    settings.stripe_price_starter = "price_starter"
    settings.stripe_price_pro = "price_pro"
    settings.stripe_secret_key = "sk_test"
    settings.cors_origins = ["https://app.example.com"]
    return settings


def test_load_billing_service_context_exposes_policy_helpers() -> None:
    context = load_billing_service_context(get_settings_fn=_settings)

    assert context.get_monthly_limits()["starter"] == 8
    assert context.plan_limit_for("pro") == 20
    assert context.price_id_to_plan("price_starter") == OrgPlan.STARTER
    assert context.plan_to_display_tier(OrgPlan.PRO) == "pro"
    assert context.checkout_price_id(PlanTier.PRO) == "price_pro"
    assert context.billing_origin_url() == "https://app.example.com"


def test_load_billing_service_context_can_configure_stripe() -> None:
    with patch("api.services.billing_policy.stripe") as stripe_module:
        context = load_billing_service_context(
            get_settings_fn=_settings,
            configure_stripe=True,
        )

    assert context.stripe_secret_key == "sk_test"
    assert stripe_module.api_key == "sk_test"
