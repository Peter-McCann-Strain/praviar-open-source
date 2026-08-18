"""Subscription sync and mutation helpers for billing.

Consolidates: billing_mutations and billing_stripe_sync.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import stripe
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import OrgPlan
from api.services.billing_checkout import (
    STRIPE_SDK_MAX_ATTEMPTS,
    STRIPE_SDK_TIMEOUT_SECONDS,
    build_stripe_sync_error_response,
    get_org_for_sync,
    log_stripe_operation_error,
    stripe_retry_exceptions,
)
from api.services.blocking_sdk import run_blocking_sdk_call

logger = structlog.get_logger()


# ── Stripe customer mutation ───────────────────────────────────────────────


async def get_or_create_stripe_customer_impl(
    db,
    org,
    *,
    create_customer_fn,
) -> str:
    """Return the Stripe customer ID for an org, creating one if needed."""
    existing_id = org.stripe_customer_id
    if existing_id:
        logger.debug("stripe_customer_exists", org_id=str(org.id), customer_id=existing_id)
        return str(existing_id)

    logger.info("stripe_customer_creating", org_id=str(org.id), org_name=org.name)
    customer = await run_blocking_sdk_call(
        "stripe.customer.create",
        create_customer_fn,
        name=org.name,
        metadata={
            "org_id": str(org.id),
            "clerk_org_id": org.clerk_org_id,
        },
        idempotency_key=f"customer:{org.id}",
        timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
        max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
        retry_exceptions=stripe_retry_exceptions(),
        logger_override=logger,
    )

    customer_id = str(customer.id)
    org.stripe_customer_id = customer_id
    await db.flush()

    logger.info(
        "stripe_customer_created",
        org_id=str(org.id),
        stripe_customer_id=customer_id,
    )
    return customer_id


# ── Subscription sync mutation ─────────────────────────────────────────────


async def sync_subscription_status_impl(
    db,
    *,
    org,
    retrieve_subscription_fn,
    price_id_to_plan_fn,
    plan_limit_for_fn,
) -> dict:
    """Sync the organisation's subscription state from Stripe."""
    customer_id = org.stripe_customer_id
    if not customer_id:
        logger.info("sync_no_stripe_customer", org_id=str(org.id))
        return {
            "plan": org.plan.value,
            "subscription_status": None,
            "message": "No Stripe customer linked",
        }

    subscription_id = org.stripe_subscription_id
    if not subscription_id:
        logger.info("sync_no_subscription", org_id=str(org.id))
        return {
            "plan": org.plan.value,
            "subscription_status": None,
            "message": "No active subscription",
        }

    subscription = await run_blocking_sdk_call(
        "stripe.subscription.retrieve",
        retrieve_subscription_fn,
        subscription_id,
        timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
        max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
        retry_exceptions=stripe_retry_exceptions(),
        logger_override=logger,
    )
    org.subscription_status = subscription.status
    org.billing_cycle_start = datetime.fromtimestamp(subscription.current_period_start, tz=UTC)
    org.current_period_end = datetime.fromtimestamp(subscription.current_period_end, tz=UTC)
    org.cancel_at_period_end = bool(subscription.cancel_at_period_end)

    if subscription.items and subscription.items.data:
        price_id = subscription.items.data[0].price.id
        new_plan = price_id_to_plan_fn(price_id)
        org.plan = new_plan
        org.max_analyses_per_month = plan_limit_for_fn(new_plan.value)

    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "subscription_synced",
        org_id=str(org.id),
        plan=org.plan.value,
        status=subscription.status,
    )
    return {
        "plan": org.plan.value,
        "subscription_status": subscription.status,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
    }


# ── Subscription sync orchestration ───────────────────────────────────────


async def sync_subscription_status_orchestrated(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    get_org_by_id_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[Any | None]],
    retrieve_subscription_fn: Callable[..., Any],
    price_id_to_plan_fn: Callable[[str], OrgPlan],
    plan_limit_for_fn: Callable[[str], int],
    sync_subscription_mutation_fn: Callable[..., Awaitable[dict]],
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Sync an org's subscription state from Stripe."""
    org = await get_org_for_sync(
        db,
        org_id=org_id,
        get_org_by_id_fn=get_org_by_id_fn,
        logger=logger,
    )
    if org is None:
        return {"error": "Organization not found"}

    try:
        return await sync_subscription_mutation_fn(
            db,
            org=org,
            retrieve_subscription_fn=retrieve_subscription_fn,
            price_id_to_plan_fn=price_id_to_plan_fn,
            plan_limit_for_fn=plan_limit_for_fn,
        )
    except (stripe.StripeError, TimeoutError) as exc:
        log_stripe_operation_error(
            logger,
            event_name="sync_stripe_error",
            org_id=str(org_id),
            exc=exc,
            extra_fields={"subscription_id": org.stripe_subscription_id},
        )
        return build_stripe_sync_error_response(exc)
