"""Stripe webhook handler — processes subscription lifecycle events.

This route is exempt from authentication (Stripe calls it directly).
All events are verified using the Stripe webhook signing secret.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import stripe
import structlog
from fastapi import APIRouter, Request, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api.config import get_settings
from api.db.models import AuditLog, StripeEvent
from api.db.session import async_session_factory
from api.errors import APIError
from api.services.blocking_sdk import run_blocking_sdk_call
from api.services.stripe_webhooks import (
    extract_audit_org_id,  # noqa: F401  # type: ignore[reportUnusedImport]
    process_stripe_webhook_event,
    resolve_receipt_org_id,
)

logger = structlog.get_logger()

router = APIRouter()

STRIPE_WEBHOOK_VERIFY_TIMEOUT_SECONDS = 5.0
STRIPE_WEBHOOK_PROCESSING_LEASE_SECONDS = 5 * 60


class StripeWebhookReceiptStatus(StrEnum):
    """Receipt state for a verified Stripe event idempotency record."""

    NEW = "new"
    DUPLICATE_PROCESSED = "duplicate_processed"
    IN_PROGRESS = "in_progress"
    STALE_RETRY = "stale_retry"


@dataclass(frozen=True)
class StripeWebhookReceipt:
    status: StripeWebhookReceiptStatus
    execution_id: uuid.UUID | None = None


def _require_stripe_event_identity(event: dict[str, Any]) -> tuple[str, str]:
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    if not event_id or not event_type:
        logger.error(
            "stripe_webhook_missing_event_identity",
            has_event_id=bool(event_id),
            has_event_type=bool(event_type),
        )
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Stripe webhook event is missing id or type",
        )
    return event_id, event_type


def _parse_org_uuid(org_id: str | None):
    if not org_id:
        return None
    try:
        return uuid.UUID(org_id)
    except (ValueError, TypeError, AttributeError):
        return None


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _stripe_webhook_lease_expires_at(now: datetime | None = None) -> datetime:
    current_time = now or datetime.now(UTC)
    return current_time + timedelta(seconds=STRIPE_WEBHOOK_PROCESSING_LEASE_SECONDS)


def _stripe_event_by_id_query(event_id: str):
    return select(StripeEvent).where(StripeEvent.stripe_event_id == event_id).with_for_update()


async def _bind_org_to_webhook_session(session, org_uuid: uuid.UUID | None) -> None:
    if org_uuid is None:
        # org_uuid is unresolved at receipt time (e.g. checkout.session.completed before
        # the customer metadata is written).  Set a sentinel so RLS allows the INSERT to
        # stripe_events without silently skipping the SET LOCAL entirely, and log a
        # warning so unresolved events are auditable in the log pipeline.
        logger.warning(
            "stripe_webhook_unresolved_org",
            detail="org_uuid is None — using nil sentinel for RLS SET LOCAL",
        )
        await session.execute(
            select(func.set_config("app.current_org_id", str(uuid.UUID(int=0)), True))
        )
        return
    await session.execute(select(func.set_config("app.current_org_id", str(org_uuid), True)))


def _stripe_webhook_receipt_status(
    receipt: StripeWebhookReceipt | StripeWebhookReceiptStatus,
) -> StripeWebhookReceiptStatus:
    if isinstance(receipt, StripeWebhookReceipt):
        return receipt.status
    return StripeWebhookReceiptStatus(receipt)


def _stripe_webhook_receipt_execution_id(
    receipt: StripeWebhookReceipt | StripeWebhookReceiptStatus,
) -> uuid.UUID | None:
    if isinstance(receipt, StripeWebhookReceipt):
        return receipt.execution_id
    return None


def _stripe_event_processing_lease_active(
    lease_expires_at: datetime | None,
    *,
    now: datetime,
) -> bool:
    if lease_expires_at is None:
        return False
    return _coerce_aware_utc(lease_expires_at) > now


def _claim_existing_stripe_event_receipt(
    existing: StripeEvent,
    *,
    org_uuid,
    now: datetime,
) -> tuple[StripeWebhookReceipt, bool]:
    mutated = False
    if existing.org_id is None and org_uuid is not None:
        existing.org_id = org_uuid
        mutated = True

    if existing.processed:
        return StripeWebhookReceipt(StripeWebhookReceiptStatus.DUPLICATE_PROCESSED), mutated

    if _stripe_event_processing_lease_active(
        getattr(existing, "processing_lease_expires_at", None),
        now=now,
    ):
        return StripeWebhookReceipt(StripeWebhookReceiptStatus.IN_PROGRESS), mutated

    execution_id = uuid.uuid4()
    existing.processing_execution_id = execution_id
    existing.processing_lease_expires_at = _stripe_webhook_lease_expires_at(now)
    return StripeWebhookReceipt(
        StripeWebhookReceiptStatus.STALE_RETRY,
        execution_id=execution_id,
    ), True


async def _record_stripe_event_receipt(
    *,
    event_id: str,
    event_type: str,
    org_id: str | None,
) -> StripeWebhookReceipt:
    """Claim a Stripe event receipt for processing."""
    org_uuid = _parse_org_uuid(org_id)
    now = datetime.now(UTC)
    execution_id = uuid.uuid4()

    async with async_session_factory() as session:
        await _bind_org_to_webhook_session(session, org_uuid)
        existing = (await session.execute(_stripe_event_by_id_query(event_id))).scalar_one_or_none()
        if existing is not None:
            receipt_status, mutated = _claim_existing_stripe_event_receipt(
                existing,
                org_uuid=org_uuid,
                now=now,
            )
            if mutated:
                await session.commit()
            return receipt_status

        # Use nil UUID sentinel for unresolved orgs so the RLS WITH CHECK
        # (org_id = app.current_org_id) passes — the session was already
        # bound to uuid.UUID(int=0) by _bind_org_to_webhook_session when
        # org_uuid is None.  Inserting NULL would fail the check.
        session.add(
            StripeEvent(
                stripe_event_id=event_id,
                event_type=event_type,
                org_id=org_uuid if org_uuid is not None else uuid.UUID(int=0),
                processed=False,
                processing_execution_id=execution_id,
                processing_lease_expires_at=_stripe_webhook_lease_expires_at(now),
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # PostgreSQL SET LOCAL values are transaction-scoped.  The rollback
            # above clears the RLS organisation binding, so restore it before
            # querying the receipt inserted by the concurrent request.
            await _bind_org_to_webhook_session(session, org_uuid)
            existing = (
                await session.execute(_stripe_event_by_id_query(event_id))
            ).scalar_one_or_none()
            if existing is None:
                raise
            receipt_status, mutated = _claim_existing_stripe_event_receipt(
                existing,
                org_uuid=org_uuid,
                now=datetime.now(UTC),
            )
            if mutated:
                await session.commit()
            return receipt_status

    return StripeWebhookReceipt(
        StripeWebhookReceiptStatus.NEW,
        execution_id=execution_id,
    )


async def _mark_stripe_event_processed(
    *,
    event_id: str,
    org_id: str | None,
    execution_id: uuid.UUID | None = None,
) -> bool:
    """Mark a Stripe event as successfully processed."""
    org_uuid = _parse_org_uuid(org_id)

    async with async_session_factory() as session:
        await _bind_org_to_webhook_session(session, org_uuid)
        existing = (await session.execute(_stripe_event_by_id_query(event_id))).scalar_one_or_none()
        if existing is None:
            session.add(
                StripeEvent(
                    stripe_event_id=event_id,
                    event_type="unknown",
                    org_id=org_uuid if org_uuid is not None else uuid.UUID(int=0),
                    processed=True,
                    processing_execution_id=None,
                    processing_lease_expires_at=None,
                )
            )
        else:
            if (
                execution_id is not None
                and not existing.processed
                and existing.processing_execution_id != execution_id
            ):
                logger.warning(
                    "stripe_webhook_receipt_mark_superseded",
                    event_id=event_id,
                    execution_id=str(execution_id),
                    current_execution_id=str(existing.processing_execution_id),
                )
                return False
            existing.processed = True
            existing.processing_execution_id = None
            existing.processing_lease_expires_at = None
            if existing.org_id is None and org_uuid is not None:
                existing.org_id = org_uuid
        await session.commit()
    return True


async def _release_stripe_event_receipt(
    *,
    event_id: str,
    org_id: str | None,
    execution_id: uuid.UUID | None = None,
) -> None:
    """Release an unprocessed Stripe event receipt so Stripe retries can reclaim it."""
    org_uuid = _parse_org_uuid(org_id)

    try:
        async with async_session_factory() as session:
            await _bind_org_to_webhook_session(session, org_uuid)
            existing = (
                await session.execute(_stripe_event_by_id_query(event_id))
            ).scalar_one_or_none()
            if existing is None or existing.processed:
                return
            if execution_id is not None and existing.processing_execution_id != execution_id:
                logger.warning(
                    "stripe_webhook_receipt_release_superseded",
                    event_id=event_id,
                    execution_id=str(execution_id),
                    current_execution_id=str(existing.processing_execution_id),
                )
                return
            existing.processing_execution_id = None
            existing.processing_lease_expires_at = None
            if existing.org_id is None and org_uuid is not None:
                existing.org_id = org_uuid
            await session.commit()
    except SQLAlchemyError as exc:
        logger.error(
            "stripe_webhook_receipt_release_failed",
            event_id=event_id,
            error=str(exc),
            error_type=type(exc).__name__,
            severity="error",
            exc_info=True,
        )


async def _mark_stripe_event_processed_or_raise(
    *,
    event_id: str,
    event_type: str,
    org_id: str | None,
    execution_id: uuid.UUID | None,
) -> None:
    marked = await _mark_stripe_event_processed(
        event_id=event_id,
        org_id=org_id,
        execution_id=execution_id,
    )
    if marked:
        return
    logger.warning(
        "stripe_webhook_receipt_mark_superseded_before_ack",
        event_type=event_type,
        event_id=event_id,
        execution_id=str(execution_id) if execution_id is not None else None,
    )
    raise APIError(
        status.HTTP_409_CONFLICT,
        "Conflict",
        "Stripe webhook event receipt was superseded by a newer retry",
    )


async def _write_webhook_audit(
    org_id: str | None,
    event_id: str,
    event_type: str,
    details: dict,
    *,
    success: bool = True,
) -> None:
    """Write an audit log entry for a webhook event.

    Audit failures must not silently disappear. We catch the narrowest set of
    expected failure modes (DB errors, payload validation, malformed UUID) and
    surface them at error severity so the metric counter / log pipeline can
    react. Anything outside that surface propagates.
    """
    try:
        import uuid

        org_uuid = uuid.UUID(org_id) if org_id else uuid.UUID(int=0)
        async with async_session_factory() as session:
            await _bind_org_to_webhook_session(
                session,
                org_uuid if org_id else None,
            )
            log = AuditLog(
                org_id=org_uuid,
                user_id=None,
                action=f"webhook.stripe.{event_type}",
                details={
                    "event_id": event_id,
                    "success": success,
                    **details,
                },
                ip_address="stripe-webhook",
            )
            session.add(log)
            await session.commit()
    except (SQLAlchemyError, ValidationError, ValueError, TypeError) as exc:
        # Log at error severity so the audit-failure metric is incremented; do
        # not re-raise — webhook delivery must still ack to Stripe.
        logger.error(
            "webhook_audit_failed",
            event_id=event_id,
            event_type=event_type,
            error=str(exc),
            error_type=type(exc).__name__,
            severity="error",
            exc_info=True,
        )


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    """Handle incoming Stripe webhook events."""
    settings = get_settings()

    if not settings.stripe_webhook_secret:
        logger.error("stripe_webhook_secret_not_configured")
        raise APIError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "STRIPE_WEBHOOK_SECRET not configured",
        )

    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        logger.warning("stripe_webhook_missing_signature")
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "Unauthorized",
            "Missing Stripe signature header",
        )

    try:
        event = await run_blocking_sdk_call(
            "stripe.webhook.construct_event",
            stripe.Webhook.construct_event,
            payload=body,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
            timeout_seconds=STRIPE_WEBHOOK_VERIFY_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
    except stripe.SignatureVerificationError as exc:
        logger.error(
            "stripe_webhook_signature_invalid",
            error=str(exc),
            exc_info=True,
        )
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "Unauthorized",
            "Invalid Stripe webhook signature",
        ) from exc
    except ValueError as exc:
        logger.error(
            "stripe_webhook_payload_invalid",
            error=str(exc),
            exc_info=True,
        )
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Invalid webhook payload",
        ) from exc
    except TimeoutError as exc:
        logger.error(
            "stripe_webhook_signature_timeout",
            error=str(exc),
            exc_info=True,
        )
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service Unavailable",
            "Stripe webhook verification timed out",
        ) from exc

    # Stripe 15 returns StripeObject models rather than dict subclasses.
    # Normalize once so downstream webhook handlers can keep using dict access.
    event_dict: dict[str, Any] = dict(event)
    event_id, event_type = _require_stripe_event_identity(event_dict)
    event_data = event_dict.get("data", {})

    logger.info(
        "stripe_webhook_received",
        event_type=event_type,
        event_id=event_id,
    )
    receipt_org_id = await resolve_receipt_org_id(event_type, event_data)
    receipt = await _record_stripe_event_receipt(
        event_id=event_id,
        event_type=event_type,
        org_id=receipt_org_id,
    )
    receipt_status = _stripe_webhook_receipt_status(receipt)
    receipt_execution_id = _stripe_webhook_receipt_execution_id(receipt)
    if receipt_status == StripeWebhookReceiptStatus.DUPLICATE_PROCESSED:
        logger.info(
            "stripe_webhook_duplicate_ignored",
            event_type=event_type,
            event_id=event_id,
        )
        return {"status": "ok", "event_type": event_type, "duplicate": True}
    if receipt_status == StripeWebhookReceiptStatus.IN_PROGRESS:
        logger.warning(
            "stripe_webhook_duplicate_in_progress",
            event_type=event_type,
            event_id=event_id,
        )
        raise APIError(
            status.HTTP_409_CONFLICT,
            "Conflict",
            "Stripe webhook event is already being processed",
        )

    receipt_released = False
    try:
        result = await process_stripe_webhook_event(event_type, event_data)
        if not isinstance(result, dict):
            raise TypeError("Stripe webhook handler result must be an object")
        if result.get("status") == "ignored":
            logger.info(
                "stripe_webhook_unhandled",
                event_type=event_type,
                event_id=event_id,
            )
            await _mark_stripe_event_processed_or_raise(
                event_id=event_id,
                event_type=event_type,
                org_id=result.get("org_id") or receipt_org_id,
                execution_id=receipt_execution_id,
            )
            return {"status": "ignored", "event_type": event_type}

        if result.get("status") == "skipped":
            logger.info(
                "stripe_webhook_skipped",
                event_type=event_type,
                event_id=event_id,
                reason=result.get("reason"),
            )
            await _mark_stripe_event_processed_or_raise(
                event_id=event_id,
                event_type=event_type,
                org_id=result.get("org_id") or receipt_org_id,
                execution_id=receipt_execution_id,
            )
            return {"status": "skipped", "event_type": event_type}

        if result.get("status") != "ok":
            logger.error(
                "stripe_webhook_handler_unsuccessful",
                event_type=event_type,
                event_id=event_id,
                result=result,
                severity="error",
            )
            await _write_webhook_audit(
                org_id=result.get("org_id") or receipt_org_id,
                event_id=event_id,
                event_type=event_type,
                details=result,
                success=False,
            )
            await _release_stripe_event_receipt(
                event_id=event_id,
                org_id=result.get("org_id") or receipt_org_id,
                execution_id=receipt_execution_id,
            )
            receipt_released = True
            raise APIError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Stripe webhook processing failed",
            )

        await _write_webhook_audit(
            org_id=result.get("org_id") or receipt_org_id,
            event_id=event_id,
            event_type=event_type,
            details=result,
            success=True,
        )
        await _mark_stripe_event_processed_or_raise(
            event_id=event_id,
            event_type=event_type,
            org_id=result.get("org_id") or receipt_org_id,
            execution_id=receipt_execution_id,
        )
        logger.info(
            "stripe_webhook_processed",
            event_type=event_type,
            event_id=event_id,
            result=result,
        )
        return {"status": "ok", "event_type": event_type}
    except (
        SQLAlchemyError,
        ValidationError,
        stripe.StripeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        # Narrow set of expected handler failure modes: DB errors, payload
        # validation, Stripe SDK errors, and malformed event payloads. The
        # audit log MUST record this failure with severity=error.
        logger.error(
            "stripe_webhook_handler_error",
            event_type=event_type,
            event_id=event_id,
            error=str(exc),
            error_type=type(exc).__name__,
            severity="error",
            exc_info=True,
        )
        await _write_webhook_audit(
            org_id=receipt_org_id,
            event_id=event_id,
            event_type=event_type,
            details={"error": str(exc), "error_type": type(exc).__name__},
            success=False,
        )
        await _release_stripe_event_receipt(
            event_id=event_id,
            org_id=receipt_org_id,
            execution_id=receipt_execution_id,
        )
        receipt_released = True
        raise APIError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Stripe webhook processing failed",
        ) from exc
    except APIError:
        if not receipt_released:
            await _release_stripe_event_receipt(
                event_id=event_id,
                org_id=receipt_org_id,
                execution_id=receipt_execution_id,
            )
        raise
    except Exception:
        if not receipt_released:
            await _release_stripe_event_receipt(
                event_id=event_id,
                org_id=receipt_org_id,
                execution_id=receipt_execution_id,
            )
        raise
