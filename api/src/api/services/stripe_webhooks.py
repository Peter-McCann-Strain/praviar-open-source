"""Stripe webhook service layer — payload interpretation and billing mutations."""

from __future__ import annotations

from typing import Any

import structlog

from api.db.session import async_session_factory
from api.services import billing_webhooks
from api.services.billing_policy import plan_limit_for, price_id_to_plan

logger = structlog.get_logger()

CUSTOMER_BOUND_WEBHOOK_TYPES = frozenset(
    {
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
)


def _event_object(event_data: dict[str, Any]) -> dict[str, Any]:
    """Return the Stripe object payload for a webhook event."""
    return billing_webhooks.event_object(event_data)


def _event_metadata(event_data: dict[str, Any]) -> dict[str, Any]:
    """Return the metadata payload for a webhook event object."""
    return billing_webhooks.event_metadata(event_data)


def extract_audit_org_id(event_data: dict[str, Any]) -> str | None:
    """Extract the org id used for webhook audit logging."""
    return billing_webhooks.extract_audit_org_id_from_event(event_data)


async def resolve_receipt_org_id(
    event_type: str,
    event_data: dict[str, Any],
) -> str | None:
    """Resolve the tenant used for Stripe receipt RLS binding before side effects."""
    metadata_org_id = extract_audit_org_id(event_data)

    if event_type not in CUSTOMER_BOUND_WEBHOOK_TYPES:
        return metadata_org_id

    obj = _event_object(event_data)
    customer_id = str(obj.get("customer") or "").strip()
    if not customer_id:
        return None

    async with async_session_factory() as db:
        org = await billing_webhooks.load_org_by_customer(db, customer_id)
    if org is None:
        return None

    resolved_org_id = str(org.id)
    if metadata_org_id and metadata_org_id != resolved_org_id:
        logger.error(
            "stripe_webhook_metadata_org_mismatch",
            event_type=event_type,
            metadata_org_id=metadata_org_id,
            resolved_org_id=resolved_org_id,
            customer_id=customer_id,
        )

    if event_type.startswith("customer.subscription."):
        subscription_id = str(obj.get("id") or "").strip()
        if not billing_webhooks._stripe_identity_matches(
            org,
            customer_id=customer_id,
            subscription_id=subscription_id,
        ):
            return None
    elif event_type.startswith("invoice."):
        subscription_id = str(obj.get("subscription") or "").strip()
        if subscription_id and not billing_webhooks._stripe_identity_matches(
            org,
            customer_id=customer_id,
            subscription_id=subscription_id,
        ):
            return None

    return resolved_org_id


async def handle_checkout_completed(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle checkout.session.completed and activate the org subscription."""
    return await billing_webhooks.handle_checkout_completed_impl(
        event_data,
        event_object_fn=_event_object,
        event_metadata_fn=_event_metadata,
        async_session_factory_fn=async_session_factory,
        load_org_by_id_fn=billing_webhooks.load_org_by_id,
        plan_limit_for_fn=plan_limit_for,
        logger=logger,
    )


async def handle_checkout_async_payment_succeeded(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle async success for payment-mode credit-pack Checkout sessions."""
    return await handle_checkout_completed(event_data)


async def handle_subscription_updated(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle customer.subscription.updated and sync billing state."""
    return await billing_webhooks.handle_subscription_updated_impl(
        event_data,
        event_object_fn=_event_object,
        event_metadata_fn=_event_metadata,
        async_session_factory_fn=async_session_factory,
        load_org_by_id_fn=billing_webhooks.load_org_by_id,
        load_org_by_customer_fn=billing_webhooks.load_org_by_customer,
        price_id_to_plan_fn=price_id_to_plan,
        plan_limit_for_fn=plan_limit_for,
        logger=logger,
    )


async def handle_subscription_deleted(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle customer.subscription.deleted and downgrade the org to free."""
    return await billing_webhooks.handle_subscription_deleted_impl(
        event_data,
        event_object_fn=_event_object,
        event_metadata_fn=_event_metadata,
        async_session_factory_fn=async_session_factory,
        load_org_by_id_fn=billing_webhooks.load_org_by_id,
        load_org_by_customer_fn=billing_webhooks.load_org_by_customer,
        plan_limit_for_fn=plan_limit_for,
        logger=logger,
    )


async def handle_invoice_payment_succeeded(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle invoice.payment_succeeded."""
    return await billing_webhooks.handle_invoice_payment_succeeded_impl(
        event_data,
        event_object_fn=_event_object,
        extract_audit_org_id_fn=lambda _event_data: None,
        async_session_factory_fn=async_session_factory,
        load_org_by_customer_fn=billing_webhooks.load_org_by_customer,
        logger=logger,
    )


async def handle_invoice_payment_failed(event_data: dict[str, Any]) -> dict[str, Any]:
    """Handle invoice.payment_failed."""
    return await billing_webhooks.handle_invoice_payment_failed_impl(
        event_data,
        event_object_fn=_event_object,
        extract_audit_org_id_fn=lambda _event_data: None,
        async_session_factory_fn=async_session_factory,
        load_org_by_customer_fn=billing_webhooks.load_org_by_customer,
        logger=logger,
    )


_EVENT_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "checkout.session.async_payment_succeeded": handle_checkout_async_payment_succeeded,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_succeeded": handle_invoice_payment_succeeded,
    "invoice.payment_failed": handle_invoice_payment_failed,
}

HANDLED_WEBHOOK_RESULT_STATUSES = {"ok", "error", "skipped"}


async def process_stripe_webhook_event(
    event_type: str,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a verified Stripe event to the lifecycle handler."""
    handler = _EVENT_HANDLERS.get(event_type)
    if handler is None:
        return {"status": "ignored", "event_type": event_type, "org_id": None}

    trusted_org_id = None
    if event_type in CUSTOMER_BOUND_WEBHOOK_TYPES:
        trusted_org_id = await resolve_receipt_org_id(event_type, event_data)
    result = await handler(event_data)
    if not isinstance(result, dict):
        raise TypeError("Stripe webhook handler result must be an object")
    if result.get("status") not in HANDLED_WEBHOOK_RESULT_STATUSES:
        raise ValueError(f"Invalid Stripe webhook handler status: {result.get('status')!r}")
    result.setdefault("event_type", event_type)
    if event_type in CUSTOMER_BOUND_WEBHOOK_TYPES:
        result["org_id"] = trusted_org_id
    elif "org_id" not in result:
        result["org_id"] = extract_audit_org_id(event_data)
    return result
