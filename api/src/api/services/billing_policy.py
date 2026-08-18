"""Pure billing policy helpers and runtime context shared across billing services and webhooks.

Absorbs the billing_service_context module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import stripe
import structlog

from api.config import get_settings
from api.db.models import OrgPlan
from api.schemas.billing import CreditPackId, PlanTier

logger = structlog.get_logger()

LAPSED_SUBSCRIPTION_STATUSES = frozenset(
    {"past_due", "incomplete", "incomplete_expired", "unpaid", "canceled"}
)


@dataclass(frozen=True, slots=True)
class AnalysisCapacityEntitlement:
    """Authoritative plan-and-credit capacity used by reads and reservations."""

    analyses_used: int
    consumed_purchased_credits: int
    included_limit: int
    purchased_credits_balance: int

    @property
    def plan_analyses_used(self) -> int:
        return max(self.analyses_used - self.consumed_purchased_credits, 0)

    @property
    def included_remaining(self) -> int:
        return max(self.included_limit - self.plan_analyses_used, 0)

    @property
    def available(self) -> int:
        return self.included_remaining + self.purchased_credits_balance

    @property
    def effective_limit(self) -> int:
        """Return a read-model ceiling whose remaining value equals launch capacity."""
        return self.analyses_used + self.available

    def purchased_credits_required(self, requested_analyses: int) -> int:
        return max(requested_analyses - self.included_remaining, 0)


def resolve_analysis_capacity_entitlement(
    *,
    analyses_used: int,
    configured_included_limit: int | None,
    consumed_purchased_credits: int,
    plan_key: str,
    purchased_credits_balance: int,
    subscription_status: str | None,
    plan_limit_for_fn,
) -> AnalysisCapacityEntitlement:
    """Resolve effective capacity, downgrading explicitly lapsed paid subscriptions."""
    included_limit = configured_included_limit or plan_limit_for_fn(plan_key)
    normalized_status = (subscription_status or "").strip().lower()
    if plan_key != "enterprise" and normalized_status in LAPSED_SUBSCRIPTION_STATUSES:
        included_limit = min(included_limit, plan_limit_for_fn("free"))

    normalized_used = max(int(analyses_used), 0)
    return AnalysisCapacityEntitlement(
        analyses_used=normalized_used,
        consumed_purchased_credits=min(
            max(int(consumed_purchased_credits), 0),
            normalized_used,
        ),
        included_limit=max(int(included_limit), 0),
        purchased_credits_balance=max(int(purchased_credits_balance), 0),
    )


def get_monthly_limits(settings=None) -> dict[str, int]:
    """Load monthly analysis limits from config."""
    resolved_settings = settings or get_settings()
    return {
        "free": resolved_settings.plan_free_analyses_per_month,
        "starter": resolved_settings.plan_starter_analyses_per_month,
        "pro": resolved_settings.plan_pro_analyses_per_month,
        "enterprise": 999_999,
    }


def plan_limit_for(plan_key: str, settings=None) -> int:
    """Resolve the monthly limit for a plan key."""
    limits = get_monthly_limits(settings)
    return limits.get(plan_key, limits["free"])


def price_id_to_plan(price_id: str, settings=None) -> OrgPlan:
    """Map a Stripe price ID to a stored organization plan."""
    resolved_settings = settings or get_settings()
    mapping = {
        resolved_settings.stripe_price_starter: OrgPlan.STARTER,
        resolved_settings.stripe_price_pro: OrgPlan.PRO,
    }
    plan = mapping.get(price_id, OrgPlan.FREE)
    logger.debug("price_id_to_plan", price_id=price_id, resolved_plan=plan.value)
    return plan


def plan_to_display_tier(plan: OrgPlan) -> str:
    """Map a stored plan enum to the frontend tier label."""
    return plan.value


def checkout_price_id(plan_id: PlanTier, settings=None) -> str | None:
    """Resolve the Stripe price ID for a requested checkout tier."""
    resolved_settings = settings or get_settings()
    price_map = {
        PlanTier.STARTER: resolved_settings.stripe_price_starter,
        PlanTier.PRO: resolved_settings.stripe_price_pro,
    }
    return price_map.get(plan_id)


def credit_pack_size(credit_pack_id: CreditPackId) -> int:
    """Resolve the number of analysis credits in a one-time pack."""
    return {
        CreditPackId.SINGLE_ANALYSIS: 1,
        CreditPackId.PORTFOLIO_5: 5,
        CreditPackId.DILIGENCE_15: 15,
        CreditPackId.SCALE_30: 30,
    }[credit_pack_id]


def credit_pack_price_id(credit_pack_id: CreditPackId, settings=None) -> str | None:
    """Resolve the Stripe price ID for a requested analysis credit pack."""
    resolved_settings = settings or get_settings()
    price_map = {
        CreditPackId.SINGLE_ANALYSIS: resolved_settings.stripe_price_credit_pack_single_analysis,
        CreditPackId.PORTFOLIO_5: resolved_settings.stripe_price_credit_pack_portfolio_5,
        CreditPackId.DILIGENCE_15: resolved_settings.stripe_price_credit_pack_diligence_15,
        CreditPackId.SCALE_30: resolved_settings.stripe_price_credit_pack_scale_30,
    }
    return price_map.get(credit_pack_id)


def billing_origin_url(settings=None) -> str:
    """Resolve the canonical app origin used in billing redirects."""
    resolved_settings = settings or get_settings()
    return str(resolved_settings.cors_origins[0])


# ── Billing service context (absorbed from billing_service_context) ────────


@dataclass(frozen=True, slots=True)
class BillingServiceContext:
    settings: Any

    @property
    def stripe_secret_key(self) -> str | None:
        return cast(str | None, self.settings.stripe_secret_key)

    def get_monthly_limits(self) -> dict[str, int]:
        return get_monthly_limits(self.settings)

    def plan_limit_for(self, plan_key: str) -> int:
        return plan_limit_for(plan_key, self.settings)

    def price_id_to_plan(self, price_id: str) -> OrgPlan:
        return price_id_to_plan(price_id, self.settings)

    def plan_to_display_tier(self, plan: OrgPlan) -> str:
        return plan_to_display_tier(plan)

    def checkout_price_id(self, plan_id: PlanTier) -> str | None:
        return checkout_price_id(plan_id, self.settings)

    def credit_pack_price_id(self, credit_pack_id: CreditPackId) -> str | None:
        return credit_pack_price_id(credit_pack_id, self.settings)

    def billing_origin_url(self) -> str:
        return billing_origin_url(self.settings)


def load_billing_service_context(
    *,
    get_settings_fn=get_settings,
    configure_stripe: bool = False,
) -> BillingServiceContext:
    """Load billing settings and optionally configure the Stripe SDK."""
    settings = get_settings_fn()
    if configure_stripe:
        stripe.api_key = settings.stripe_secret_key
    return BillingServiceContext(settings=settings)
