"""Stripe webhook helpers — payload parsing, org lookups, and lifecycle handlers.

Consolidates: stripe_webhooks_invoices, stripe_webhooks_payloads,
stripe_webhooks_queries, and stripe_webhooks_subscriptions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AnalysisCreditLedger, Organization, OrgPlan
from api.services.billing import fulfill_pending_credit_capacity_requests
from api.services.billing_metadata import (
    is_credit_pack_checkout_metadata,
    parse_checkout_session_metadata,
    parse_credit_pack_checkout_metadata,
)
from api.services.billing_policy import credit_pack_size

CREDIT_LEDGER_SESSION_UNIQUE_CONSTRAINT = "uq_analysis_credit_ledger_stripe_session"


def _integrity_error_constraint_name(exc: IntegrityError) -> str | None:
    """Extract a PostgreSQL constraint name without parsing error text."""
    pending: list[object] = [exc.orig]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))

        direct_name = getattr(current, "constraint_name", None)
        if isinstance(direct_name, str) and direct_name:
            return direct_name
        diag = getattr(current, "diag", None)
        diag_name = getattr(diag, "constraint_name", None)
        if isinstance(diag_name, str) and diag_name:
            return diag_name

        pending.extend(
            candidate
            for candidate in (
                getattr(current, "__cause__", None),
                getattr(current, "__context__", None),
            )
            if candidate is not None
        )
    return None


def _is_credit_session_unique_conflict(exc: IntegrityError) -> bool:
    return _integrity_error_constraint_name(exc) == CREDIT_LEDGER_SESSION_UNIQUE_CONSTRAINT


def _credit_purchase_matches_event(
    ledger: AnalysisCreditLedger,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credits: int,
    credit_pack_id: str,
    session_id: str,
    payment_intent_id: str,
) -> bool:
    """Verify a unique-conflict row is the same idempotent purchase."""
    return bool(
        ledger.org_id == org_id
        and ledger.user_id == user_id
        and ledger.kind == "purchase"
        and ledger.credits_delta == credits
        and ledger.credit_pack_id == credit_pack_id
        and ledger.stripe_checkout_session_id == session_id
        and ledger.stripe_payment_intent_id == payment_intent_id
    )


# ── Payload helpers ────────────────────────────────────────────────────────


async def _commit_or_rollback(db: AsyncSession) -> None:
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


def event_object(event_data: dict[str, Any]) -> dict[str, Any]:
    """Return the Stripe object payload for a webhook event."""
    obj = event_data.get("object", {})
    return obj if isinstance(obj, dict) else {}


def event_metadata(event_data: dict[str, Any]) -> dict[str, Any]:
    """Return the metadata payload for a webhook event object."""
    metadata = event_object(event_data).get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def extract_audit_org_id_from_event(event_data: dict[str, Any]) -> str | None:
    """Extract the org id used for webhook audit logging."""
    org_id = event_metadata(event_data).get("org_id")
    return str(org_id) if org_id else None


# ── Organisation lookup helpers ────────────────────────────────────────────


async def load_org_by_id(
    db: AsyncSession,
    org_id: str,
) -> Organization | None:
    """Load an organisation by UUID string."""
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    return result.scalar_one_or_none()


async def load_org_by_customer(
    db: AsyncSession,
    customer_id: str,
) -> Organization | None:
    """Load an organisation by Stripe customer id."""
    result = await db.execute(
        select(Organization).where(Organization.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


def _stripe_identity_matches(
    org: Organization,
    *,
    customer_id: object,
    subscription_id: object,
) -> bool:
    """Return True when a subscription event matches the resolved tenant."""
    event_customer_id = str(customer_id or "").strip()
    event_subscription_id = str(subscription_id or "").strip()
    raw_org_customer_id = getattr(org, "stripe_customer_id", None)
    raw_org_subscription_id = getattr(org, "stripe_subscription_id", None)
    org_customer_id = raw_org_customer_id.strip() if isinstance(raw_org_customer_id, str) else ""
    org_subscription_id = (
        raw_org_subscription_id.strip() if isinstance(raw_org_subscription_id, str) else ""
    )

    if not event_customer_id or not org_customer_id or org_customer_id != event_customer_id:
        return False
    return bool(event_subscription_id and org_subscription_id == event_subscription_id)


# ── Invoice event handlers ─────────────────────────────────────────────────


async def handle_invoice_payment_succeeded_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    extract_audit_org_id_fn,
    async_session_factory_fn,
    load_org_by_customer_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle invoice.payment_succeeded.

    Mirror image of ``handle_invoice_payment_failed_impl``: a failed payment
    flips an ``active`` org to ``past_due`` *immediately* so we stop granting
    paid analysis quota during Stripe's dunning retries (the Wave 43 quota cap
    treats ``past_due`` as effectively free-tier). When a later retry succeeds
    we must restore quota with the same immediacy — ``customer.subscription``
    ``.updated`` "may not arrive for days", so relying on it alone would leave a
    paying org throttled to free-tier limits in the interim. We therefore clear
    ``past_due`` back to ``active`` here, scoped to the invoice's own customer +
    subscription so a spoofed/mismatched event cannot escalate an unrelated org.
    """
    invoice = event_object_fn(event_data)
    customer_id = invoice.get("customer", "")
    subscription_id = invoice.get("subscription", "")
    amount_paid = invoice.get("amount_paid", 0)

    logger.info(
        "webhook_invoice_paid",
        customer_id=customer_id,
        subscription_id=subscription_id,
        amount_cents=amount_paid,
    )

    org_id: str | None = extract_audit_org_id_fn(event_data)

    if customer_id:
        async with async_session_factory_fn() as db:
            org = await load_org_by_customer_fn(db, customer_id)
            if org:
                org_id = str(org.id)
                # Only the dunning-recovery transition is performed here. We do
                # NOT promote incomplete/unpaid/canceled orgs to active — those
                # are owned by checkout/subscription lifecycle events — and we
                # require the invoice's subscription to match the org's so a
                # stray paid invoice on a different subscription cannot re-enable
                # quota for the wrong subscription state.
                if org.subscription_status == "past_due" and _stripe_identity_matches(
                    org,
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                ):
                    org.subscription_status = "active"
                    await _commit_or_rollback(db)
                    logger.info(
                        "webhook_org_restored_active_after_payment",
                        org_id=org_id,
                        customer_id=customer_id,
                    )

    return {"status": "ok", "org_id": org_id}


async def handle_invoice_payment_failed_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    extract_audit_org_id_fn,
    async_session_factory_fn,
    load_org_by_customer_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle invoice.payment_failed."""
    invoice = event_object_fn(event_data)
    customer_id = invoice.get("customer", "")
    subscription_id = invoice.get("subscription", "")
    amount_due = invoice.get("amount_due", 0)
    attempt_count = invoice.get("attempt_count", 0)

    logger.warning(
        "webhook_invoice_payment_failed",
        customer_id=customer_id,
        subscription_id=subscription_id,
        amount_due_cents=amount_due,
        attempt_count=attempt_count,
    )

    org_id: str | None = extract_audit_org_id_fn(event_data)

    # Mark the org as past_due immediately so we don't grant analysis quota
    # while Stripe is in a dunning retry cycle. customer.subscription.updated
    # may not arrive for days after the first failed payment.
    if customer_id:
        async with async_session_factory_fn() as db:
            org = await load_org_by_customer_fn(db, customer_id)
            if org:
                org_id = str(org.id)
                if org.subscription_status == "active":
                    org.subscription_status = "past_due"
                    await _commit_or_rollback(db)
                    logger.warning(
                        "webhook_org_marked_past_due",
                        org_id=org_id,
                        customer_id=customer_id,
                        attempt_count=attempt_count,
                    )

    return {
        "status": "ok",
        "warning": "payment_failed",
        "org_id": org_id,
    }


# ── Subscription lifecycle handlers ───────────────────────────────────────


async def handle_checkout_completed_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    event_metadata_fn,
    async_session_factory_fn,
    load_org_by_id_fn,
    plan_limit_for_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle checkout.session.completed and activate the org subscription."""
    session_obj = event_object_fn(event_data)
    customer_id = session_obj.get("customer", "")
    subscription_id = session_obj.get("subscription", "")
    session_mode = session_obj.get("mode", "")
    payment_status = session_obj.get("payment_status", "")

    if session_mode == "payment":
        metadata = event_metadata_fn(event_data)
        if not is_credit_pack_checkout_metadata(metadata):
            logger.info(
                "webhook_checkout_payment_session_skipped",
                customer_id=customer_id,
                session_id=session_obj.get("id", ""),
                metadata_purpose=metadata.get("purpose"),
            )
            return {
                "status": "skipped",
                "reason": "payment checkout session is not a Praviar credit-pack checkout",
            }
        return await handle_credit_pack_checkout_completed_impl(
            event_data,
            event_object_fn=event_object_fn,
            event_metadata_fn=event_metadata_fn,
            async_session_factory_fn=async_session_factory_fn,
            load_org_by_id_fn=load_org_by_id_fn,
            logger=logger,
        )

    if session_mode != "subscription":
        logger.warning(
            "webhook_checkout_unexpected_mode",
            mode=session_mode,
            customer_id=customer_id,
        )
        return {"status": "skipped", "reason": f"unexpected checkout mode: {session_mode}"}

    if not subscription_id:
        logger.warning(
            "webhook_checkout_missing_subscription_id",
            customer_id=customer_id,
        )
        return {
            "status": "error",
            "reason": "subscription id missing on checkout.session.completed",
        }

    try:
        metadata = parse_checkout_session_metadata(event_metadata_fn(event_data))
    except (ValueError, ValidationError) as exc:
        logger.error(
            "webhook_checkout_invalid_metadata",
            customer_id=customer_id,
            subscription_id=subscription_id,
            error=str(exc),
        )
        raise
    org_id = str(metadata.org_id)
    new_plan = OrgPlan(metadata.plan_id.value)

    logger.info(
        "webhook_checkout_completed",
        customer_id=customer_id,
        subscription_id=subscription_id,
        org_id=org_id,
        plan=new_plan.value,
    )

    async with async_session_factory_fn() as db:
        org = await load_org_by_id_fn(db, org_id)
        if not org:
            logger.error("webhook_checkout_org_not_found", org_id=org_id)
            return {"status": "error", "reason": "org not found", "org_id": org_id}

        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription_id
        # Bank-transfer sessions arrive with payment_status='unpaid'; mark as
        # incomplete until invoice.payment_succeeded confirms the payment.
        org.subscription_status = "incomplete" if payment_status == "unpaid" else "active"
        org.plan = new_plan
        org.max_analyses_per_month = plan_limit_for_fn(new_plan.value)
        await _commit_or_rollback(db)

    logger.info(
        "webhook_plan_activated",
        org_id=org_id,
        plan=new_plan.value,
        customer_id=customer_id,
    )
    return {"status": "ok", "org_id": org_id, "plan": new_plan.value}


async def handle_credit_pack_checkout_completed_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    event_metadata_fn,
    async_session_factory_fn,
    load_org_by_id_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle paid one-time Checkout sessions for analysis credit packs."""
    session_obj = event_object_fn(event_data)
    session_id = str(session_obj.get("id") or "").strip()
    customer_id = str(session_obj.get("customer") or "").strip()
    payment_intent_id = str(session_obj.get("payment_intent") or "").strip()
    session_mode = str(session_obj.get("mode") or "").strip()
    payment_status = str(session_obj.get("payment_status") or "").strip()

    missing_identity_fields = [
        field_name
        for field_name, value in (
            ("id", session_id),
            ("customer", customer_id),
            ("payment_intent", payment_intent_id),
        )
        if not value
    ]
    if missing_identity_fields:
        logger.error(
            "webhook_credit_pack_missing_stripe_identity",
            missing_fields=missing_identity_fields,
            session_id=session_id,
            customer_id=customer_id,
        )
        raise ValueError("credit-pack checkout session is missing required Stripe identity")

    if session_mode != "payment":
        logger.warning(
            "webhook_credit_pack_unexpected_mode",
            mode=session_mode,
            customer_id=customer_id,
            session_id=session_id,
        )
        return {"status": "skipped", "reason": f"unexpected checkout mode: {session_mode}"}

    if payment_status != "paid":
        logger.info(
            "webhook_credit_pack_payment_not_paid",
            payment_status=payment_status,
            customer_id=customer_id,
            session_id=session_id,
        )
        return {
            "status": "skipped",
            "reason": f"payment status not paid: {payment_status}",
        }

    try:
        metadata = parse_credit_pack_checkout_metadata(event_metadata_fn(event_data))
    except (ValueError, ValidationError) as exc:
        logger.error(
            "webhook_credit_pack_invalid_metadata",
            customer_id=customer_id,
            session_id=session_id,
            error=str(exc),
        )
        raise

    expected_credits = credit_pack_size(metadata.credit_pack_id)
    if metadata.credits != expected_credits:
        logger.error(
            "webhook_credit_pack_credit_mismatch",
            customer_id=customer_id,
            session_id=session_id,
            credit_pack_id=metadata.credit_pack_id.value,
            metadata_credits=metadata.credits,
            expected_credits=expected_credits,
        )
        raise ValueError("credit pack metadata credits do not match configured pack size")

    org_id = str(metadata.org_id)
    logger.info(
        "webhook_credit_pack_checkout_completed",
        customer_id=customer_id,
        session_id=session_id,
        org_id=org_id,
        credit_pack_id=metadata.credit_pack_id.value,
        credits=metadata.credits,
    )

    async with async_session_factory_fn() as db:
        await db.execute(select(func.set_config("app.current_org_id", org_id, True)))
        org = await load_org_by_id_fn(db, org_id)
        if not org:
            logger.error("webhook_credit_pack_org_not_found", org_id=org_id)
            return {"status": "error", "reason": "org not found", "org_id": org_id}

        if org.stripe_customer_id and org.stripe_customer_id != customer_id:
            logger.error(
                "webhook_credit_pack_customer_mismatch",
                org_id=org_id,
                expected_customer_id=org.stripe_customer_id,
                event_customer_id=customer_id,
                session_id=session_id,
            )
            return {"status": "error", "reason": "stripe customer mismatch", "org_id": org_id}

        if not org.stripe_customer_id:
            org.stripe_customer_id = customer_id

        existing_result = await db.execute(
            select(AnalysisCreditLedger).where(
                AnalysisCreditLedger.stripe_checkout_session_id == session_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if not _credit_purchase_matches_event(
                existing,
                org_id=metadata.org_id,
                user_id=metadata.user_id,
                credits=metadata.credits,
                credit_pack_id=metadata.credit_pack_id.value,
                session_id=session_id,
                payment_intent_id=payment_intent_id,
            ):
                raise ValueError(
                    "existing credit ledger purchase does not match Stripe checkout event"
                )
            return {
                "status": "ok",
                "org_id": org_id,
                "credit_pack_id": metadata.credit_pack_id.value,
                "credits": metadata.credits,
                "duplicate": True,
            }

        ledger_id = uuid.uuid4()
        db.add(
            AnalysisCreditLedger(
                id=ledger_id,
                org_id=metadata.org_id,
                user_id=metadata.user_id,
                kind="purchase",
                credits_delta=metadata.credits,
                credit_pack_id=metadata.credit_pack_id.value,
                stripe_checkout_session_id=session_id,
                stripe_payment_intent_id=payment_intent_id or None,
                details={"source": "stripe.checkout.session.completed"},
            )
        )
        try:
            fulfilled_request_ids = await fulfill_pending_credit_capacity_requests(
                db,
                org_id=metadata.org_id,
                purchaser_user_id=metadata.user_id,
                credit_ledger_id=ledger_id,
                purchased_credits=metadata.credits,
            )
            await _commit_or_rollback(db)
        except IntegrityError as exc:
            await db.rollback()
            if not _is_credit_session_unique_conflict(exc):
                raise

            # The failed transaction cleared SET LOCAL/RLS state. Rebind the
            # tenant and prove the conflicting row is this exact purchase
            # before acknowledging an idempotent delivery.
            await db.execute(select(func.set_config("app.current_org_id", org_id, True)))
            duplicate_result = await db.execute(
                select(AnalysisCreditLedger).where(
                    AnalysisCreditLedger.stripe_checkout_session_id == session_id
                )
            )
            duplicate = duplicate_result.scalar_one_or_none()
            if duplicate is None or not _credit_purchase_matches_event(
                duplicate,
                org_id=metadata.org_id,
                user_id=metadata.user_id,
                credits=metadata.credits,
                credit_pack_id=metadata.credit_pack_id.value,
                session_id=session_id,
                payment_intent_id=payment_intent_id,
            ):
                raise
            return {
                "status": "ok",
                "org_id": org_id,
                "credit_pack_id": metadata.credit_pack_id.value,
                "credits": metadata.credits,
                "duplicate": True,
            }
        except Exception:
            await db.rollback()
            raise

    logger.info(
        "webhook_credit_pack_granted",
        org_id=org_id,
        credit_pack_id=metadata.credit_pack_id.value,
        credits=metadata.credits,
        fulfilled_capacity_requests=len(fulfilled_request_ids),
        session_id=session_id,
    )
    return {
        "status": "ok",
        "org_id": org_id,
        "credit_pack_id": metadata.credit_pack_id.value,
        "credits": metadata.credits,
    }


async def handle_subscription_updated_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    event_metadata_fn,
    async_session_factory_fn,
    load_org_by_id_fn,
    load_org_by_customer_fn,
    price_id_to_plan_fn,
    plan_limit_for_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle customer.subscription.updated and sync billing state."""
    subscription = event_object_fn(event_data)
    subscription_id = subscription.get("id", "")
    customer_id = subscription.get("customer", "")
    sub_status = subscription.get("status", "")
    cancel_at_period_end = subscription.get("cancel_at_period_end", False)
    metadata = event_metadata_fn(event_data)
    org_id = str(metadata.get("org_id") or "")

    logger.info(
        "webhook_subscription_updated",
        subscription_id=subscription_id,
        status=sub_status,
        org_id=org_id,
    )

    async with async_session_factory_fn() as db:
        if not org_id:
            org = await load_org_by_customer_fn(db, customer_id)
            if org:
                org_id = str(org.id)

        if not org_id:
            logger.warning(
                "webhook_subscription_updated_no_org",
                customer_id=customer_id,
                subscription_id=subscription_id,
            )
            return {"status": "skipped", "reason": "cannot resolve org", "org_id": None}

        org = await load_org_by_id_fn(db, org_id)
        if not org:
            return {"status": "error", "reason": "org not found", "org_id": org_id}
        if not _stripe_identity_matches(
            org,
            customer_id=customer_id,
            subscription_id=subscription_id,
        ):
            logger.error(
                "webhook_subscription_updated_identity_mismatch",
                org_id=org_id,
                customer_id=customer_id,
                subscription_id=subscription_id,
            )
            return {
                "status": "error",
                "reason": "stripe identity mismatch",
                "org_id": org_id,
            }

        current_period_start = subscription.get("current_period_start")
        current_period_end = subscription.get("current_period_end")
        stripe_event_created = int(event_data.get("created", 0))

        new_period_end: datetime | None = None
        if current_period_end:
            new_period_end = datetime.fromtimestamp(int(current_period_end), tz=UTC)

        # Primary guard: reject events from a prior billing period.
        event_is_current = (
            new_period_end is None
            or org.current_period_end is None
            or new_period_end >= org.current_period_end
        )

        # Secondary guard: within the same billing period two distinct
        # subscription.updated events share the same current_period_end, so the
        # primary guard alone cannot prevent out-of-order delivery (e.g.
        # active → past_due, then a stale active overwrites back).  Compare
        # Stripe's event-level ``created`` timestamp stored from the last
        # accepted event.
        if event_is_current and stripe_event_created and new_period_end == org.current_period_end:
            # Coerce defensively: settings is a free-form JSONB blob, and a
            # corrupted/legacy value of the wrong type would make int() raise and
            # crash the webhook handler (Stripe then retries the same event
            # forever). An unparseable marker means "no reliable prior event", so
            # treat it as 0 — the safe direction that lets the current event
            # through rather than silently dropping it.
            raw_last_event_at = (org.settings or {}).get("stripe_last_subscription_event_at", 0)
            try:
                last_event_at = int(raw_last_event_at)
            except (TypeError, ValueError):
                logger.warning(
                    "stripe_last_event_marker_invalid",
                    org_id=str(org.id),
                    raw_value=repr(raw_last_event_at),
                )
                last_event_at = 0
            if stripe_event_created < last_event_at:
                event_is_current = False

        if event_is_current:
            if current_period_start:
                org.billing_cycle_start = datetime.fromtimestamp(int(current_period_start), tz=UTC)
            if new_period_end is not None:
                org.current_period_end = new_period_end
            org.subscription_status = sub_status
            org.cancel_at_period_end = bool(cancel_at_period_end)

            if stripe_event_created:
                org.settings = {
                    **(org.settings or {}),
                    "stripe_last_subscription_event_at": stripe_event_created,
                }

            items = subscription.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id", "")
                if price_id:
                    new_plan = price_id_to_plan_fn(price_id)
                    org.plan = new_plan
                    org.max_analyses_per_month = plan_limit_for_fn(new_plan.value)
        else:
            logger.warning(
                "webhook_subscription_stale_event_skipped",
                org_id=org_id,
                event_period_end=int(current_period_end) if current_period_end else None,
                stored_period_end=org.current_period_end.isoformat()
                if org.current_period_end
                else None,
            )

        await _commit_or_rollback(db)

    logger.info(
        "webhook_subscription_synced",
        org_id=org_id,
        status=sub_status,
    )
    return {"status": "ok", "org_id": org_id, "subscription_status": sub_status}


async def handle_subscription_deleted_impl(
    event_data: dict[str, Any],
    *,
    event_object_fn,
    event_metadata_fn,
    async_session_factory_fn,
    load_org_by_id_fn,
    load_org_by_customer_fn,
    plan_limit_for_fn,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    """Handle customer.subscription.deleted and downgrade the org to free."""
    subscription = event_object_fn(event_data)
    subscription_id = subscription.get("id", "")
    customer_id = subscription.get("customer", "")
    metadata = event_metadata_fn(event_data)
    org_id = str(metadata.get("org_id") or "")

    logger.info(
        "webhook_subscription_deleted",
        subscription_id=subscription_id,
        org_id=org_id,
    )

    async with async_session_factory_fn() as db:
        if not org_id:
            org = await load_org_by_customer_fn(db, customer_id)
            if org:
                org_id = str(org.id)

        if not org_id:
            logger.warning(
                "webhook_subscription_deleted_no_org",
                customer_id=customer_id,
            )
            return {"status": "skipped", "reason": "cannot resolve org", "org_id": None}

        org = await load_org_by_id_fn(db, org_id)
        if not org:
            return {"status": "error", "reason": "org not found", "org_id": org_id}
        if not _stripe_identity_matches(
            org,
            customer_id=customer_id,
            subscription_id=subscription_id,
        ):
            logger.error(
                "webhook_subscription_deleted_identity_mismatch",
                org_id=org_id,
                customer_id=customer_id,
                subscription_id=subscription_id,
            )
            return {
                "status": "error",
                "reason": "stripe identity mismatch",
                "org_id": org_id,
            }

        org.plan = OrgPlan.FREE
        org.max_analyses_per_month = plan_limit_for_fn(OrgPlan.FREE.value)
        org.subscription_status = "canceled"
        org.stripe_subscription_id = None
        org.billing_cycle_start = None
        org.current_period_end = None
        org.cancel_at_period_end = False

        await _commit_or_rollback(db)

    logger.info(
        "webhook_plan_downgraded_to_free",
        org_id=org_id,
        subscription_id=subscription_id,
    )
    return {"status": "ok", "org_id": org_id}
