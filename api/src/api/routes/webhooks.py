"""Clerk webhook handlers for user/org sync."""

import hashlib

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import ClerkWebhookReceipt
from api.db.session import async_session_factory, set_current_org_id
from api.errors import APIError
from api.schemas.common import StatusResponse
from api.services.clerk_webhooks import (
    MEMBERSHIP_EVENT_TYPES,
)
from api.services.clerk_webhooks import (
    handle_membership_event as _handle_membership_event,
)
from api.services.clerk_webhooks import (
    handle_org_created as _handle_org_created,
)
from api.services.clerk_webhooks import (
    handle_user_created as _handle_user_created,
)

logger = structlog.get_logger()

router = APIRouter()

SUBSCRIBED_EVENT_TYPES = frozenset(
    {"user.created", "organization.created", *MEMBERSHIP_EVENT_TYPES}
)


def _require_clerk_event_payload(payload) -> tuple[str, dict]:
    """Validate the verified Clerk payload shape before any DB work."""
    if not isinstance(payload, dict):
        logger.error("webhook_payload_not_object", payload_type=type(payload).__name__)
        raise APIError(400, "Bad Request", "Webhook payload must be an object")

    event_type = str(payload.get("type") or "").strip()
    if not event_type:
        logger.error("webhook_missing_event_type")
        raise APIError(400, "Bad Request", "Missing webhook event type")

    data = payload.get("data", {})
    if event_type in SUBSCRIBED_EVENT_TYPES and not isinstance(data, dict):
        logger.error(
            "webhook_data_not_object",
            event_type=event_type,
            data_type=type(data).__name__,
        )
        raise APIError(400, "Bad Request", "Webhook data must be an object")

    return event_type, data if isinstance(data, dict) else {}


async def _claim_clerk_webhook_receipt(
    db,
    *,
    svix_id: str,
    event_type: str,
    payload_sha256: str,
) -> bool:
    """Atomically claim a verified Svix delivery inside the work transaction."""
    db.add(
        ClerkWebhookReceipt(
            svix_id=svix_id,
            event_type=event_type,
            payload_sha256=payload_sha256,
        )
    )
    try:
        await db.flush()
        return True
    except IntegrityError as exc:
        # The unique Svix ID serializes concurrent retries. Roll back the failed
        # insert before reading the winning committed receipt.
        await db.rollback()
        result = await db.execute(
            select(ClerkWebhookReceipt).where(ClerkWebhookReceipt.svix_id == svix_id)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise
        if existing.event_type != event_type or existing.payload_sha256 != payload_sha256:
            logger.error(
                "clerk_webhook_receipt_collision",
                svix_id=svix_id,
                event_type=event_type,
                existing_event_type=existing.event_type,
            )
            raise APIError(
                409,
                "Conflict",
                "Webhook delivery ID was reused with a different payload",
            ) from exc
        return False


@router.post("/webhooks/clerk", response_model=StatusResponse)
async def clerk_webhook(request: Request) -> dict:
    """Handle Clerk webhook events for user and org synchronization."""
    body = await request.body()

    settings = get_settings()
    if not settings.clerk_webhook_secret:
        logger.error("webhook_secret_not_configured")
        raise APIError(500, "Internal Server Error", "CLERK_WEBHOOK_SECRET not configured")

    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")

    if not all([svix_id, svix_timestamp, svix_signature]):
        logger.warning(
            "webhook_missing_headers",
            has_svix_id=bool(svix_id),
            has_svix_timestamp=bool(svix_timestamp),
            has_svix_signature=bool(svix_signature),
        )
        raise APIError(401, "Unauthorized", "Missing webhook signature headers")

    try:
        from svix.webhooks import Webhook

        wh = Webhook(settings.clerk_webhook_secret)
        payload = wh.verify(
            body,
            {
                "svix-id": svix_id,
                "svix-timestamp": svix_timestamp,
                "svix-signature": svix_signature,
            },
        )
    except Exception as exc:
        logger.error("webhook_verification_failed", error=str(exc), exc_info=True)
        raise APIError(
            401,
            "Unauthorized",
            "Webhook verification failed",
        ) from exc

    event_type, event_data = _require_clerk_event_payload(payload)
    logger.info("webhook_received", event_type=event_type, svix_id=svix_id)

    if event_type not in SUBSCRIBED_EVENT_TYPES:
        logger.warning("webhook_unhandled_event", event_type=event_type)
        return {"status": "ok"}

    async with async_session_factory() as db:
        try:
            claimed = await _claim_clerk_webhook_receipt(
                db,
                svix_id=svix_id,
                event_type=event_type,
                payload_sha256=hashlib.sha256(body).hexdigest(),
            )
            if not claimed:
                return {"status": "already_processed"}
            if event_type == "user.created":
                result = await _handle_user_created(db, event_data)
                await db.commit()
                return result
            if event_type == "organization.created":
                result = await _handle_org_created(db, event_data)
                await db.commit()
                return result
            result = await _handle_membership_event(
                db,
                event_data,
                event_type=event_type,
                event_id=svix_id,
                source="clerk_webhook",
                write_audit_log_fn=write_audit_log,
            )
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
        finally:
            # Membership handling binds tenant RLS on this manually-created
            # session. Unlike get_db(), this route must clear the ContextVar.
            set_current_org_id(None)
