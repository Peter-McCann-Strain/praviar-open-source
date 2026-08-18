"""Stripe checkout, portal, and invoice orchestration for billing.

Consolidates: billing_stripe_checkout, billing_stripe_errors,
billing_stripe_guards, billing_stripe_invoices,
billing_stripe_session_payloads, and billing_stripe_values.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import stripe
import structlog
from fastapi import Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import APIError
from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_metadata import (
    build_checkout_session_metadata,
    build_credit_pack_checkout_metadata,
)
from api.services.billing_policy import credit_pack_size
from api.services.blocking_sdk import retryable_exception_types, run_blocking_sdk_call

STRIPE_SDK_TIMEOUT_SECONDS = 10.0
STRIPE_SDK_MAX_ATTEMPTS = 2
_DEFAULT_URL_PORTS = {"http": 80, "https": 443}
CHECKOUT_SESSION_ID_PARAM = "checkout_session_id"
STRIPE_CHECKOUT_SESSION_ID_PLACEHOLDER = "{CHECKOUT_SESSION_ID}"


async def _commit_or_rollback(db: AsyncSession) -> None:
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def _rollback_billing_session(db: AsyncSession) -> None:
    await db.rollback()


def stripe_retry_exceptions() -> tuple[type[BaseException], ...]:
    return retryable_exception_types(
        getattr(stripe, "APIConnectionError", None),
        getattr(stripe, "RateLimitError", None),
    )


# ── Value builders ─────────────────────────────────────────────────────────


def build_checkout_return_url(
    billing_origin_url_fn: Callable[[], str],
    *,
    state: str,
) -> str:
    return f"{billing_origin_url_fn().rstrip('/')}/billing?checkout={state}"


def build_credit_pack_checkout_return_url(
    billing_origin_url_fn: Callable[[], str],
    *,
    credit_pack_id: CreditPackId,
    state: str,
) -> str:
    query = urlencode(
        {
            "checkout": state,
            "credit_pack": credit_pack_id.value,
            "intent": "credits",
        }
    )
    return f"{billing_origin_url_fn().rstrip('/')}/billing?{query}"


def build_portal_return_url(billing_origin_url_fn: Callable[[], str]) -> str:
    return f"{billing_origin_url_fn().rstrip('/')}/billing"


def _url_origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Billing redirect URLs must be absolute URLs.",
        )
    scheme = parsed.scheme.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Billing redirect URLs must include a valid port.",
        ) from exc
    if port == _DEFAULT_URL_PORTS.get(scheme):
        port = None
    return (scheme, parsed.hostname.lower(), port)


def _require_same_billing_origin(*, url: str, billing_origin_url: str, label: str) -> None:
    if _url_origin(url) != _url_origin(billing_origin_url):
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            f"{label} must use the configured application origin.",
        )


def resolve_checkout_return_urls(
    billing_origin_url_fn: Callable[[], str],
    *,
    success_url: str,
    cancel_url: str,
) -> tuple[str, str]:
    billing_origin_url = billing_origin_url_fn()
    resolved_success_url = success_url or build_checkout_return_url(
        lambda: billing_origin_url,
        state="success",
    )
    resolved_cancel_url = cancel_url or build_checkout_return_url(
        lambda: billing_origin_url,
        state="cancelled",
    )
    _require_same_billing_origin(
        url=resolved_success_url,
        billing_origin_url=billing_origin_url,
        label="success_url",
    )
    _require_same_billing_origin(
        url=resolved_cancel_url,
        billing_origin_url=billing_origin_url,
        label="cancel_url",
    )
    return (
        resolved_success_url,
        resolved_cancel_url,
    )


def add_checkout_session_id_placeholder(success_url: str) -> str:
    """Append Stripe's server-substituted Checkout session id parameter."""
    parts = urlsplit(success_url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != CHECKOUT_SESSION_ID_PARAM
    ]
    encoded_query = urlencode(query_items)
    placeholder_query = f"{CHECKOUT_SESSION_ID_PARAM}={STRIPE_CHECKOUT_SESSION_ID_PLACEHOLDER}"
    query = f"{encoded_query}&{placeholder_query}" if encoded_query else placeholder_query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def build_checkout_session_line_items(price_id: str) -> list[dict[str, object]]:
    return [{"price": price_id, "quantity": 1}]


CREDIT_PACK_CHECKOUT_CUSTOM_TEXT = {
    "submit": {
        "message": (
            "Report Credit Packs are prepaid capacity. Included Report Credits "
            "are used first; purchased credits are generally non-refundable "
            "except as required by law or expressly stated in an order form."
        )
    }
}

CREDIT_PACK_INVOICE_FOOTER = (
    "1 Report Credit = 1 first-pass FTO report request for 1 compound. "
    "Reports are informational tools and not legal advice."
)


def build_credit_pack_invoice_creation(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_pack_id: CreditPackId,
    credits: int,
) -> dict[str, object]:
    return {
        "enabled": True,
        "invoice_data": {
            "description": f"{credits} Praviar Report Credits",
            "footer": CREDIT_PACK_INVOICE_FOOTER,
            "metadata": {
                "org_id": str(org_id),
                "user_id": str(user_id),
                "credit_pack_id": credit_pack_id.value,
                "credits": str(credits),
            },
        },
    }


def build_checkout_session_audit_details(
    *,
    plan_id: PlanTier,
    session_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    return {
        "plan_id": plan_id.value,
        "session_id": session_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }


def build_credit_pack_checkout_session_audit_details(
    *,
    credit_pack_id: CreditPackId,
    credits: int,
    session_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    return {
        "credit_pack_id": credit_pack_id.value,
        "credits": str(credits),
        "session_id": session_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }


def build_portal_session_audit_details(*, portal_session_id: str) -> dict[str, str]:
    return {"portal_session_id": portal_session_id}


def build_empty_invoice_payload() -> dict[str, object]:
    return {"invoices": [], "has_more": False}


# ── Session payload builders ───────────────────────────────────────────────


def build_checkout_session_payload(
    *,
    customer_id: str,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: PlanTier,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, object]:
    return {
        "mode": "subscription",
        "customer": customer_id,
        "line_items": build_checkout_session_line_items(price_id),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": build_checkout_session_metadata(
            org_id=org_id,
            user_id=user_id,
            plan_id=plan_id,
        ),
        "allow_promotion_codes": True,
    }


def build_credit_pack_checkout_session_payload(
    *,
    customer_id: str,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_pack_id: CreditPackId,
    credits: int,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, object]:
    return {
        "mode": "payment",
        "customer": customer_id,
        "line_items": build_checkout_session_line_items(price_id),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": build_credit_pack_checkout_metadata(
            org_id=org_id,
            user_id=user_id,
            credit_pack_id=credit_pack_id,
            credits=credits,
        ),
        "custom_text": CREDIT_PACK_CHECKOUT_CUSTOM_TEXT,
        "invoice_creation": build_credit_pack_invoice_creation(
            org_id=org_id,
            user_id=user_id,
            credit_pack_id=credit_pack_id,
            credits=credits,
        ),
        "allow_promotion_codes": True,
    }


def build_portal_session_payload(
    *,
    customer_id: str,
    return_url: str,
) -> dict[str, str]:
    return {
        "customer": customer_id,
        "return_url": return_url,
    }


# ── Error and logging helpers ──────────────────────────────────────────────


PUBLIC_STRIPE_ERROR_DETAIL = (
    "Stripe could not confirm this billing operation. No billing changes are "
    "being claimed. Retry shortly or contact support if the problem persists."
)
PUBLIC_STRIPE_SYNC_ERROR = "Stripe synchronization failed. No billing changes are being claimed."


def _safe_stripe_error_fields(exc: Exception) -> dict[str, Any]:
    fields: dict[str, Any] = {"error_type": type(exc).__name__}
    stripe_code = getattr(exc, "code", None)
    if isinstance(stripe_code, str) and stripe_code:
        fields["stripe_code"] = stripe_code
    http_status = getattr(exc, "http_status", None)
    if isinstance(http_status, int):
        fields["stripe_http_status"] = http_status
    request_id = getattr(exc, "request_id", None)
    if isinstance(request_id, str) and request_id:
        fields["stripe_request_id"] = request_id
    return fields


def build_stripe_api_error(operation_label: str, exc: Exception) -> APIError:
    """Build a standard 502 APIError for a Stripe failure."""
    return APIError(
        status.HTTP_502_BAD_GATEWAY,
        "Stripe Error",
        f"Failed to {operation_label}. {PUBLIC_STRIPE_ERROR_DETAIL}",
    )


def build_stripe_sync_error_response(exc: Exception) -> dict[str, str]:
    """Build the public response for a Stripe sync failure."""
    return {"error": PUBLIC_STRIPE_SYNC_ERROR}


def log_stripe_operation_error(
    logger: structlog.stdlib.BoundLogger,
    *,
    event_name: str,
    org_id: str,
    exc: Exception,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Log a standard Stripe failure payload."""
    event_fields: dict[str, Any] = {
        "org_id": org_id,
        **_safe_stripe_error_fields(exc),
    }
    if extra_fields:
        event_fields.update(extra_fields)
    logger.error(event_name, **event_fields)


# ── Guard and validation helpers ───────────────────────────────────────────


def require_billing_configured(
    stripe_secret_key: str | None,
    *,
    unavailable_message: str,
    logger=None,
) -> None:
    """Raise the standard billing configuration error when Stripe is disabled."""
    if stripe_secret_key:
        return

    if logger is not None:
        logger.error("billing_stripe_not_configured")

    raise APIError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Service Unavailable",
        unavailable_message,
    )


def resolve_checkout_price_id(
    plan_id: PlanTier,
    *,
    checkout_price_id_fn: Callable[[PlanTier], str | None],
) -> str:
    """Validate a requested checkout tier and return its configured price id."""
    if plan_id == PlanTier.FREE:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Cannot checkout for the free plan. Use the customer portal to downgrade.",
        )

    if plan_id == PlanTier.ENTERPRISE:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Enterprise plans require contacting sales.",
        )

    price_id = checkout_price_id_fn(plan_id)
    if not price_id:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            f"No Stripe price configured for plan: {plan_id.value}",
        )

    return price_id


def resolve_credit_pack_price_id(
    credit_pack_id: CreditPackId,
    *,
    credit_pack_price_id_fn: Callable[[CreditPackId], str | None],
) -> str:
    """Validate a requested credit pack and return its configured price id."""
    price_id = credit_pack_price_id_fn(credit_pack_id)
    if not price_id:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            f"No Stripe price configured for credit pack: {credit_pack_id.value}",
        )

    return price_id


async def get_org_for_sync(
    db,
    *,
    org_id: uuid.UUID,
    get_org_by_id_fn: Callable[[Any, uuid.UUID], Awaitable[Any | None]],
    logger,
):
    """Fetch the org for subscription sync and log the standard missing-org case."""
    org = await get_org_by_id_fn(db, org_id)
    if org is None:
        logger.error("sync_org_not_found", org_id=str(org_id))
    return org


# ── Invoice listing ────────────────────────────────────────────────────────


async def list_invoice_data_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    stripe_secret_key: str | None,
    get_org_for_billing_or_404_fn: Callable[[AsyncSession, uuid.UUID], Any],
    list_invoices_fn: Callable[..., Any],
    map_invoice_list_fn: Callable[[Any], dict],
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Return recent Stripe invoices for an organization."""
    if not stripe_secret_key:
        return build_empty_invoice_payload()

    org = await get_org_for_billing_or_404_fn(db, org_id)
    customer_id = org.stripe_customer_id
    if not customer_id:
        return build_empty_invoice_payload()

    try:
        invoices = await run_blocking_sdk_call(
            "stripe.invoices.list",
            list_invoices_fn,
            customer=customer_id,
            limit=20,
            timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
            max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
            retry_exceptions=stripe_retry_exceptions(),
            logger_override=logger,
        )
    except (stripe.StripeError, TimeoutError) as exc:
        log_stripe_operation_error(
            logger,
            event_name="invoices_list_failed",
            org_id=str(org.id),
            exc=exc,
        )
        raise build_stripe_api_error("fetch invoices", exc) from exc

    return map_invoice_list_fn(invoices)


# ── Checkout and portal session orchestration ──────────────────────────────


async def create_checkout_session_data_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: PlanTier,
    success_url: str,
    cancel_url: str,
    request: Request,
    stripe_secret_key: str | None,
    get_org_for_billing_or_404_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[Any]],
    checkout_price_id_fn: Callable[[PlanTier], str | None],
    get_or_create_customer_fn: Callable[[AsyncSession, Any], Awaitable[str]],
    write_audit_log_fn: Callable[..., Awaitable[None]],
    create_checkout_session_fn: Callable[..., Any],
    billing_origin_url_fn: Callable[[], str],
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Checkout session and persist the audit trail."""
    require_billing_configured(
        stripe_secret_key,
        unavailable_message="Billing is not configured. Contact support.",
        logger=logger,
    )
    price_id = resolve_checkout_price_id(
        plan_id,
        checkout_price_id_fn=checkout_price_id_fn,
    )

    org = await get_org_for_billing_or_404_fn(db, org_id)
    success_return_url, cancel_return_url = resolve_checkout_return_urls(
        billing_origin_url_fn,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    try:
        customer_id = await get_or_create_customer_fn(db, org)
        checkout_payload = build_checkout_session_payload(
            customer_id=customer_id,
            org_id=org.id,
            user_id=user_id,
            plan_id=plan_id,
            price_id=price_id,
            success_url=success_return_url,
            cancel_url=cancel_return_url,
        )
        checkout_idempotency_key = f"checkout:{org.id}:{user_id}:{uuid.uuid4()}"
        session = await run_blocking_sdk_call(
            "stripe.checkout.session.create",
            lambda: create_checkout_session_fn(
                **checkout_payload,
                idempotency_key=checkout_idempotency_key,
            ),
            timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
            max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
            retry_exceptions=stripe_retry_exceptions(),
            logger_override=logger,
        )

        await write_audit_log_fn(
            db,
            org_id=org.id,
            user_id=user_id,
            action="billing.checkout.started",
            details=build_checkout_session_audit_details(
                plan_id=plan_id,
                session_id=session.id,
                success_url=success_return_url,
                cancel_url=cancel_return_url,
            ),
            request=request,
        )
        await _commit_or_rollback(db)
        return {"checkout_url": session.url, "session_id": session.id}
    except (stripe.StripeError, TimeoutError) as exc:
        await _rollback_billing_session(db)
        log_stripe_operation_error(
            logger,
            event_name="checkout_session_failed",
            org_id=str(org.id),
            exc=exc,
        )
        raise build_stripe_api_error("create checkout session", exc) from exc
    except Exception:
        await _rollback_billing_session(db)
        raise


async def create_credit_pack_checkout_session_data_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_pack_id: CreditPackId,
    success_url: str,
    cancel_url: str,
    request: Request,
    stripe_secret_key: str | None,
    get_org_for_billing_or_404_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[Any]],
    credit_pack_price_id_fn: Callable[[CreditPackId], str | None],
    get_or_create_customer_fn: Callable[[AsyncSession, Any], Awaitable[str]],
    write_audit_log_fn: Callable[..., Awaitable[None]],
    create_checkout_session_fn: Callable[..., Any],
    billing_origin_url_fn: Callable[[], str],
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Checkout session for one-time analysis credits."""
    require_billing_configured(
        stripe_secret_key,
        unavailable_message="Billing is not configured. Contact support.",
        logger=logger,
    )
    price_id = resolve_credit_pack_price_id(
        credit_pack_id,
        credit_pack_price_id_fn=credit_pack_price_id_fn,
    )

    org = await get_org_for_billing_or_404_fn(db, org_id)
    success_return_url, cancel_return_url = resolve_checkout_return_urls(
        billing_origin_url_fn,
        success_url=success_url
        or build_credit_pack_checkout_return_url(
            billing_origin_url_fn,
            credit_pack_id=credit_pack_id,
            state="success",
        ),
        cancel_url=cancel_url
        or build_credit_pack_checkout_return_url(
            billing_origin_url_fn,
            credit_pack_id=credit_pack_id,
            state="cancelled",
        ),
    )
    success_return_url = add_checkout_session_id_placeholder(success_return_url)
    credits = credit_pack_size(credit_pack_id)

    try:
        customer_id = await get_or_create_customer_fn(db, org)
        checkout_payload = build_credit_pack_checkout_session_payload(
            customer_id=customer_id,
            org_id=org.id,
            user_id=user_id,
            credit_pack_id=credit_pack_id,
            credits=credits,
            price_id=price_id,
            success_url=success_return_url,
            cancel_url=cancel_return_url,
        )
        request_key = uuid.uuid4()
        checkout_idempotency_key = (
            f"credit-pack:{org.id}:{user_id}:{credit_pack_id.value}:{request_key}"
        )
        session = await run_blocking_sdk_call(
            "stripe.checkout.session.create",
            lambda: create_checkout_session_fn(
                **checkout_payload,
                idempotency_key=checkout_idempotency_key,
            ),
            timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
            max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
            retry_exceptions=stripe_retry_exceptions(),
            logger_override=logger,
        )

        await write_audit_log_fn(
            db,
            org_id=org.id,
            user_id=user_id,
            action="billing.credit_pack.checkout.started",
            details=build_credit_pack_checkout_session_audit_details(
                credit_pack_id=credit_pack_id,
                credits=credits,
                session_id=session.id,
                success_url=success_return_url,
                cancel_url=cancel_return_url,
            ),
            request=request,
        )
        await _commit_or_rollback(db)
        return {"checkout_url": session.url, "session_id": session.id}
    except (stripe.StripeError, TimeoutError) as exc:
        await _rollback_billing_session(db)
        log_stripe_operation_error(
            logger,
            event_name="credit_pack_checkout_session_failed",
            org_id=str(org.id),
            exc=exc,
            extra_fields={"credit_pack_id": credit_pack_id.value},
        )
        raise build_stripe_api_error("create credit pack checkout session", exc) from exc
    except Exception:
        await _rollback_billing_session(db)
        raise


async def create_portal_session_data_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    stripe_secret_key: str | None,
    get_org_for_billing_or_404_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[Any]],
    get_or_create_customer_fn: Callable[[AsyncSession, Any], Awaitable[str]],
    write_audit_log_fn: Callable[..., Awaitable[None]],
    create_portal_session_fn: Callable[..., Any],
    billing_origin_url_fn: Callable[[], str],
    logger: structlog.stdlib.BoundLogger,
) -> dict:
    """Create a Stripe Customer Portal session and persist the audit trail."""
    require_billing_configured(
        stripe_secret_key,
        unavailable_message="Billing is not configured.",
        logger=logger,
    )

    org = await get_org_for_billing_or_404_fn(db, org_id)
    try:
        customer_id = await get_or_create_customer_fn(db, org)
        portal_payload = build_portal_session_payload(
            customer_id=customer_id,
            return_url=build_portal_return_url(billing_origin_url_fn),
        )
        portal_idempotency_key = f"portal:{org.id}:{user_id}"
        portal = await run_blocking_sdk_call(
            "stripe.billing_portal.session.create",
            lambda: create_portal_session_fn(
                **portal_payload,
                idempotency_key=portal_idempotency_key,
            ),
            timeout_seconds=STRIPE_SDK_TIMEOUT_SECONDS,
            max_attempts=STRIPE_SDK_MAX_ATTEMPTS,
            retry_exceptions=stripe_retry_exceptions(),
            logger_override=logger,
        )

        await write_audit_log_fn(
            db,
            org_id=org.id,
            user_id=user_id,
            action="billing.portal.started",
            details=build_portal_session_audit_details(portal_session_id=portal.id),
            request=request,
        )
        await _commit_or_rollback(db)
        return {"portal_url": portal.url}
    except (stripe.StripeError, TimeoutError) as exc:
        await _rollback_billing_session(db)
        log_stripe_operation_error(
            logger,
            event_name="portal_session_failed",
            org_id=str(org.id),
            exc=exc,
        )
        raise build_stripe_api_error("create portal session", exc) from exc
    except Exception:
        await _rollback_billing_session(db)
        raise
