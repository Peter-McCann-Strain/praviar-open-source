"""Implementation helpers for the public billing service facade."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Organization, OrgPlan
from api.schemas.billing import CreditPackId, PlanTier
from api.services import billing_checkout, billing_queries, billing_sync
from api.services.billing_policy import BillingServiceContext, load_billing_service_context

__all__ = [
    "load_context",
    "plan_limit_for",
    "price_id_to_plan",
    "plan_to_display_tier",
    "get_or_create_stripe_customer",
    "get_monthly_usage",
    "get_billing_status_data",
    "create_checkout_session_data",
    "create_credit_pack_checkout_session_data",
    "create_portal_session_data",
    "get_usage_summary_data",
    "list_invoice_data",
    "record_usage_event",
    "check_usage_limit",
    "sync_subscription_status",
]


def load_context(*, get_settings_fn, configure_stripe: bool = False) -> BillingServiceContext:
    return load_billing_service_context(
        get_settings_fn=get_settings_fn,
        configure_stripe=configure_stripe,
    )


def plan_limit_for(plan_key: str, *, load_context_fn: Callable[[], BillingServiceContext]) -> int:
    return load_context_fn().plan_limit_for(plan_key)


def price_id_to_plan(
    price_id: str,
    *,
    load_context_fn: Callable[[], BillingServiceContext],
) -> OrgPlan:
    """Map a Stripe price ID to an OrgPlan enum value."""
    return load_context_fn().price_id_to_plan(price_id)


def plan_to_display_tier(
    plan: OrgPlan,
    *,
    load_context_fn: Callable[[], BillingServiceContext],
) -> str:
    """Map DB OrgPlan to display tier name for the frontend."""
    return load_context_fn().plan_to_display_tier(plan)


async def get_or_create_stripe_customer(
    db: AsyncSession,
    org: Organization,
    *,
    create_customer_fn,
) -> str:
    """Return the Stripe customer ID for an org, creating one if needed."""
    return await billing_sync.get_or_create_stripe_customer_impl(
        db,
        org,
        create_customer_fn=create_customer_fn,
    )


async def get_monthly_usage(
    db: AsyncSession,
    org_id: uuid.UUID,
    period_start: datetime | None = None,
) -> int:
    """Count completed analyses for the org in the current billing period."""
    return await billing_queries.get_monthly_usage(db, org_id, period_start)


async def get_billing_status_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn,
    get_org_fn,
    get_monthly_usage_fn,
) -> dict:
    return await billing_queries.get_billing_status_data(
        db,
        org_id=org_id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
        get_monthly_usage_fn=get_monthly_usage_fn,
    )


async def create_checkout_session_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: PlanTier,
    success_url: str,
    cancel_url: str,
    request: Request,
    load_context_fn,
    get_org_for_billing_or_404_fn,
    get_or_create_customer_fn,
    write_audit_log_fn,
    create_checkout_session_fn,
    billing_origin_url_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Checkout session and persist the audit trail."""
    context = load_context_fn(configure_stripe=True)
    return await billing_checkout.create_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        plan_id=plan_id,
        success_url=success_url,
        cancel_url=cancel_url,
        request=request,
        stripe_secret_key=context.stripe_secret_key,
        get_org_for_billing_or_404_fn=get_org_for_billing_or_404_fn,
        checkout_price_id_fn=context.checkout_price_id,
        get_or_create_customer_fn=get_or_create_customer_fn,
        write_audit_log_fn=write_audit_log_fn,
        create_checkout_session_fn=create_checkout_session_fn,
        billing_origin_url_fn=billing_origin_url_fn,
        logger=logger,
    )


async def create_credit_pack_checkout_session_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_pack_id: CreditPackId,
    success_url: str,
    cancel_url: str,
    request: Request,
    load_context_fn,
    get_org_for_billing_or_404_fn,
    get_or_create_customer_fn,
    write_audit_log_fn,
    create_checkout_session_fn,
    billing_origin_url_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Checkout session for one-time analysis credits."""
    context = load_context_fn(configure_stripe=True)
    return await billing_checkout.create_credit_pack_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=credit_pack_id,
        success_url=success_url,
        cancel_url=cancel_url,
        request=request,
        stripe_secret_key=context.stripe_secret_key,
        get_org_for_billing_or_404_fn=get_org_for_billing_or_404_fn,
        credit_pack_price_id_fn=context.credit_pack_price_id,
        get_or_create_customer_fn=get_or_create_customer_fn,
        write_audit_log_fn=write_audit_log_fn,
        create_checkout_session_fn=create_checkout_session_fn,
        billing_origin_url_fn=billing_origin_url_fn,
        logger=logger,
    )


async def create_portal_session_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    load_context_fn,
    get_org_for_billing_or_404_fn,
    get_or_create_customer_fn,
    write_audit_log_fn,
    create_portal_session_fn,
    billing_origin_url_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Customer Portal session and persist the audit trail."""
    context = load_context_fn(configure_stripe=True)
    return await billing_checkout.create_portal_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        request=request,
        stripe_secret_key=context.stripe_secret_key,
        get_org_for_billing_or_404_fn=get_org_for_billing_or_404_fn,
        get_or_create_customer_fn=get_or_create_customer_fn,
        write_audit_log_fn=write_audit_log_fn,
        create_portal_session_fn=create_portal_session_fn,
        billing_origin_url_fn=billing_origin_url_fn,
        logger=logger,
    )


async def get_usage_summary_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn,
    get_org_fn,
    get_monthly_usage_fn,
) -> dict:
    """Return the current billing-cycle usage summary for an organization."""
    return await billing_queries.get_usage_summary_data(
        db,
        org_id=org_id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
        get_monthly_usage_fn=get_monthly_usage_fn,
    )


async def list_invoice_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn,
    get_org_for_billing_or_404_fn,
    list_invoices_fn,
    map_invoice_list_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Return recent Stripe invoices for an organization."""
    context = load_context_fn(configure_stripe=True)
    return await billing_checkout.list_invoice_data_impl(
        db,
        org_id=org_id,
        stripe_secret_key=context.stripe_secret_key,
        get_org_for_billing_or_404_fn=get_org_for_billing_or_404_fn,
        list_invoices_fn=list_invoices_fn,
        map_invoice_list_fn=map_invoice_list_fn,
        logger=logger,
    )


async def record_usage_event(
    db: AsyncSession,
    org_id: uuid.UUID,
    analysis_id: uuid.UUID,
) -> None:
    """Record a metered usage event for a completed analysis."""
    await billing_queries.record_usage_event(db, org_id, analysis_id)


async def check_usage_limit(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> tuple[bool, int, int]:
    """Check whether the org is within its monthly analysis limit."""
    return await billing_queries.check_usage_limit(db, org_id)


async def sync_subscription_status(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn,
    get_org_by_id_fn,
    retrieve_subscription_fn,
    sync_subscription_mutation_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Sync the org's subscription status from Stripe."""
    context = load_context_fn(configure_stripe=True)
    return await billing_sync.sync_subscription_status_orchestrated(
        db,
        org_id=org_id,
        get_org_by_id_fn=get_org_by_id_fn,
        retrieve_subscription_fn=retrieve_subscription_fn,
        price_id_to_plan_fn=context.price_id_to_plan,
        plan_limit_for_fn=context.plan_limit_for,
        sync_subscription_mutation_fn=sync_subscription_mutation_fn,
        logger=logger,
    )
