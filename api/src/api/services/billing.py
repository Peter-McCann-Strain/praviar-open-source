"""Billing service layer — Stripe customer management, usage tracking, and plan sync."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import stripe
import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import (
    CreditCapacityRequest,
    Notification,
    NotificationType,
    Organization,
    User,
    UserRole,
)
from api.errors import APIError, problem_type_uri
from api.schemas.billing import CreditPackId, PlanTier
from api.services import (
    billing_facade,
    billing_queries,
    billing_sync,
)
from api.services.billing_policy import (
    plan_limit_for as plan_limit_for,
)
from api.services.billing_policy import (
    plan_to_display_tier as plan_to_display_tier,
)
from api.services.billing_policy import (
    price_id_to_plan as price_id_to_plan,
)

logger = structlog.get_logger()


# ── Context helpers ────────────────────────────────────────────────────────


def _load_context(*, configure_stripe: bool = False):
    """Load billing context with the application settings function bound."""
    return billing_facade.load_context(
        get_settings_fn=get_settings,
        configure_stripe=configure_stripe,
    )


def _configured_context():
    return _load_context(configure_stripe=True)


# ── Stripe customer management ─────────────────────────────────────────────


async def get_or_create_stripe_customer(
    db: AsyncSession,
    org: Organization,
) -> str:
    """Return the Stripe customer ID for an org, creating one if needed.

    Stores the customer ID on the typed organization column.
    """
    _configured_context()
    return await billing_facade.get_or_create_stripe_customer(
        db,
        org,
        create_customer_fn=stripe.Customer.create,
    )


# ── Usage tracking ─────────────────────────────────────────────────────────


get_monthly_usage = billing_facade.get_monthly_usage
record_usage_event = billing_facade.record_usage_event
check_usage_limit = billing_facade.check_usage_limit


async def get_billing_status_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict:
    """Return the current billing snapshot for an organization."""
    return await billing_facade.get_billing_status_data(
        db,
        org_id=org_id,
        load_context_fn=_load_context,
        get_org_fn=billing_queries.get_org_for_billing_or_404,
        get_monthly_usage_fn=get_monthly_usage,
    )


async def create_credit_capacity_request_data(
    db: AsyncSession,
    *,
    user: User,
    requested_reports: int,
    source: str,
    request: Request,
) -> dict[str, object]:
    """Notify active organization administrators that launch capacity is needed."""
    result = await db.execute(
        select(User).where(
            User.org_id == user.org_id,
            User.id != user.id,
            User.role == UserRole.ADMIN,
            User.membership_active.is_(True),
            User.membership_deleted_at.is_(None),
            User.membership_permission_denied_at.is_(None),
        )
    )
    administrators = list(result.scalars().all())
    if not administrators:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No active workspace administrator is available to receive "
                "this Report Credit request."
            ),
        )

    requester_name = (user.full_name or "").strip() or "Workspace member"
    report_label = "Report Credit" if requested_reports == 1 else "Report Credits"
    request_id = uuid.uuid4()
    requested_at = datetime.now(UTC)
    db.add(
        CreditCapacityRequest(
            id=request_id,
            org_id=user.org_id,
            requester_user_id=user.id,
            requester_name=requester_name,
            requested_reports=requested_reports,
            source=source,
            status="pending",
            notified_admins=len(administrators),
            requested_at=requested_at,
        )
    )
    for administrator in administrators:
        db.add(
            Notification(
                user_id=administrator.id,
                org_id=user.org_id,
                type=NotificationType.SYSTEM,
                title="Report Credit capacity requested",
                body=(
                    f"{requester_name} requested {requested_reports} "
                    f"{report_label} for an FTO analysis launch. "
                    f"Reference {str(request_id)[:8]}."
                ),
                data={
                    "href": "/billing?intent=credits&source=capacity_request",
                    "kind": "credit_capacity_request",
                    "request_id": str(request_id),
                    "requested_reports": requested_reports,
                    "requested_at": requested_at.isoformat(),
                    "requester_id": str(user.id),
                    "source": source,
                },
            )
        )
    db.add(
        Notification(
            user_id=user.id,
            org_id=user.org_id,
            type=NotificationType.SYSTEM,
            title="Report Credit request sent",
            body=(
                f"Your request for {requested_reports} {report_label} was sent "
                f"to {len(administrators)} workspace administrator"
                f"{'' if len(administrators) == 1 else 's'}. "
                f"Reference {str(request_id)[:8]}."
            ),
            read=True,
            data={
                "href": "/billing",
                "kind": "credit_capacity_request_confirmation",
                "notified_admins": len(administrators),
                "request_id": str(request_id),
                "requested_reports": requested_reports,
                "requested_at": requested_at.isoformat(),
                "source": source,
            },
        )
    )

    try:
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            action="billing.credit_capacity_requested",
            details={
                "notified_admins": len(administrators),
                "request_id": str(request_id),
                "requested_reports": requested_reports,
                "requested_at": requested_at.isoformat(),
                "source": source,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "billing_credit_capacity_requested",
        notified_admins=len(administrators),
        org_id=str(user.org_id),
        requested_reports=requested_reports,
        source=source,
        user_id=str(user.id),
    )
    return {
        "notified_admins": len(administrators),
        "request_id": request_id,
        "requested_at": requested_at,
        "status": "sent",
    }


def serialize_credit_capacity_request(item: CreditCapacityRequest) -> dict[str, object]:
    """Serialize one durable request without loading ORM relationships."""
    return {
        "id": item.id,
        "requester_user_id": item.requester_user_id,
        "requester_name": item.requester_name,
        "requested_reports": item.requested_reports,
        "source": item.source,
        "status": item.status,
        "notified_admins": item.notified_admins,
        "requested_at": item.requested_at,
        "resolved_at": item.resolved_at,
        "resolved_by_user_id": item.resolved_by_user_id,
        "resolution_note": item.resolution_note,
        "fulfillment_credit_ledger_id": item.fulfillment_credit_ledger_id,
    }


async def list_credit_capacity_requests_data(
    db: AsyncSession,
    *,
    user: User,
    page: int,
    per_page: int,
    request_status: str | None,
) -> dict[str, object]:
    """List workspace requests for admins or current-user requests for creators."""
    query = select(CreditCapacityRequest).where(CreditCapacityRequest.org_id == user.org_id)
    if user.role != UserRole.ADMIN:
        query = query.where(CreditCapacityRequest.requester_user_id == user.id)
    if request_status is not None:
        query = query.where(CreditCapacityRequest.status == request_status)

    total = int(
        (
            await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
        ).scalar_one()
    )
    rows = (
        (
            await db.execute(
                query.order_by(
                    CreditCapacityRequest.requested_at.desc(),
                    CreditCapacityRequest.id.desc(),
                )
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [serialize_credit_capacity_request(item) for item in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


async def resolve_credit_capacity_request_data(
    db: AsyncSession,
    *,
    user: User,
    request_id: uuid.UUID,
    resolution_status: str,
    note: str | None,
    request: Request,
) -> dict[str, object]:
    """Resolve one pending workspace request transactionally and notify its owner."""
    if resolution_status not in {"fulfilled", "declined"}:
        raise APIError(422, "Validation Error", "Unsupported capacity request resolution")

    org_result = await db.execute(
        select(Organization).where(Organization.id == user.org_id).with_for_update()
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Billing organization not found")

    request_result = await db.execute(
        select(CreditCapacityRequest)
        .where(
            CreditCapacityRequest.id == request_id,
            CreditCapacityRequest.org_id == user.org_id,
        )
        .with_for_update()
    )
    capacity_request = request_result.scalar_one_or_none()
    if capacity_request is None:
        raise APIError(404, "Not Found", "Report Credit capacity request not found")
    if capacity_request.status != "pending":
        if capacity_request.status == resolution_status:
            return {
                **serialize_credit_capacity_request(capacity_request),
                "resolution_outcome": "already_resolved",
            }
        raise APIError(
            409,
            "Conflict",
            "Report Credit capacity request has already been resolved",
            type_uri=problem_type_uri("capacity-request-already-resolved"),
        )

    resolved_at = datetime.now(UTC)
    normalized_note = (note or "").strip() or None
    if resolution_status == "declined" and (normalized_note is None or len(normalized_note) < 4):
        raise APIError(
            422,
            "Validation Error",
            "A decline reason of at least 4 characters is required",
        )

    available_capacity_at_resolution: int | None = None
    if resolution_status == "fulfilled":
        capacity = await billing_queries.get_available_analysis_capacity(db, org=org)
        available_capacity_at_resolution = capacity.available
        if capacity.available < capacity_request.requested_reports:
            raise APIError(
                409,
                "Conflict",
                (
                    f"Only {capacity.available} of "
                    f"{capacity_request.requested_reports} requested report slots "
                    "are currently available. Add capacity or reduce the request "
                    "before verifying."
                ),
                type_uri=problem_type_uri("insufficient-capacity"),
            )

    capacity_request.status = resolution_status
    capacity_request.resolved_at = resolved_at
    capacity_request.resolved_by_user_id = user.id
    capacity_request.resolution_note = normalized_note
    capacity_request.fulfillment_credit_ledger_id = None

    if capacity_request.requester_user_id is not None:
        capacity_verified = resolution_status == "fulfilled"
        resolution_label = "verified" if capacity_verified else "declined"
        resolution_detail = (
            (
                f" An administrator verified that "
                f"{available_capacity_at_resolution} shared report slot"
                f"{'' if available_capacity_at_resolution == 1 else 's'} "
                f"were available at {resolved_at.strftime('%H:%M')} UTC. "
                "Capacity is shared, not reserved, and rechecked when an analysis starts."
            )
            if capacity_verified
            else ""
        )
        db.add(
            Notification(
                user_id=capacity_request.requester_user_id,
                org_id=user.org_id,
                type=NotificationType.SYSTEM,
                title=(
                    "Report Credit capacity verified"
                    if capacity_verified
                    else "Report Credit request declined"
                ),
                body=(
                    f"Your request for {capacity_request.requested_reports} "
                    f"Report Credit"
                    f"{'' if capacity_request.requested_reports == 1 else 's'} "
                    f"was {resolution_label}. Reference {str(capacity_request.id)[:8]}."
                    f"{resolution_detail}"
                ),
                data={
                    "href": "/billing",
                    "kind": "credit_capacity_request_resolved",
                    "request_id": str(capacity_request.id),
                    "resolved_at": resolved_at.isoformat(),
                    "resolution_status": resolution_status,
                    "available_capacity_at_resolution": available_capacity_at_resolution,
                    "capacity_reserved": False,
                },
            )
        )

    try:
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            action="billing.credit_capacity_request.resolved",
            details={
                "request_id": str(capacity_request.id),
                "requested_reports": capacity_request.requested_reports,
                "resolved_by_user_id": str(user.id),
                "resolution_status": resolution_status,
                "resolved_at": resolved_at.isoformat(),
                "resolution_kind": (
                    "capacity_verified" if resolution_status == "fulfilled" else "declined"
                ),
                "available_capacity_at_resolution": available_capacity_at_resolution,
                "capacity_reserved": False,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "billing_credit_capacity_request_resolved",
        org_id=str(user.org_id),
        request_id=str(capacity_request.id),
        resolution_status=resolution_status,
        user_id=str(user.id),
    )
    return {
        **serialize_credit_capacity_request(capacity_request),
        "resolution_outcome": "resolved",
    }


async def fulfill_pending_credit_capacity_requests(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    purchaser_user_id: uuid.UUID,
    credit_ledger_id: uuid.UUID,
    purchased_credits: int,
) -> list[uuid.UUID]:
    """Fulfill whole pending requests in FIFO order inside the purchase transaction."""
    result = await db.execute(
        select(CreditCapacityRequest)
        .where(
            CreditCapacityRequest.org_id == org_id,
            CreditCapacityRequest.status == "pending",
        )
        .order_by(
            CreditCapacityRequest.requested_at.asc(),
            CreditCapacityRequest.id.asc(),
        )
        .with_for_update()
    )
    pending_requests = list(result.scalars().all())
    remaining_credits = purchased_credits
    resolved_at = datetime.now(UTC)
    fulfilled: list[CreditCapacityRequest] = []
    for capacity_request in pending_requests:
        if capacity_request.requested_reports > remaining_credits:
            break
        capacity_request.status = "fulfilled"
        capacity_request.resolved_at = resolved_at
        capacity_request.resolved_by_user_id = purchaser_user_id
        capacity_request.resolution_note = "Automatically fulfilled by Report Credit purchase."
        capacity_request.fulfillment_credit_ledger_id = credit_ledger_id
        fulfilled.append(capacity_request)
        remaining_credits -= capacity_request.requested_reports

        if capacity_request.requester_user_id is not None:
            db.add(
                Notification(
                    user_id=capacity_request.requester_user_id,
                    org_id=org_id,
                    type=NotificationType.BILLING_EVENT,
                    title="Report Credit request fulfilled",
                    body=(
                        f"Your request for {capacity_request.requested_reports} "
                        f"Report Credit"
                        f"{'' if capacity_request.requested_reports == 1 else 's'} "
                        f"was fulfilled by a workspace purchase. "
                        f"Reference {str(capacity_request.id)[:8]}."
                    ),
                    data={
                        "href": "/billing",
                        "kind": "credit_capacity_request_auto_fulfilled",
                        "request_id": str(capacity_request.id),
                        "fulfilled_at": resolved_at.isoformat(),
                        "fulfillment_credit_ledger_id": str(credit_ledger_id),
                    },
                )
            )

    if not fulfilled:
        return []

    db.add(
        Notification(
            user_id=purchaser_user_id,
            org_id=org_id,
            type=NotificationType.BILLING_EVENT,
            title="Report Credit requests fulfilled",
            body=(
                f"{len(fulfilled)} pending capacity request"
                f"{'' if len(fulfilled) == 1 else 's'} fulfilled in FIFO order."
            ),
            read=True,
            data={
                "href": "/billing?intent=credits&source=capacity_fulfillment",
                "kind": "credit_capacity_requests_auto_fulfilled_admin",
                "request_ids": [str(item.id) for item in fulfilled],
                "fulfillment_credit_ledger_id": str(credit_ledger_id),
            },
        )
    )
    await write_audit_log(
        db,
        org_id=org_id,
        user_id=purchaser_user_id,
        action="billing.credit_capacity_requests.auto_fulfilled",
        details={
            "credit_ledger_id": str(credit_ledger_id),
            "fulfilled_request_ids": [str(item.id) for item in fulfilled],
            "purchaser_user_id": str(purchaser_user_id),
            "purchased_credits": purchased_credits,
            "remaining_unallocated_credits": remaining_credits,
        },
        fail_closed=True,
    )
    return [item.id for item in fulfilled]


async def create_checkout_session_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: PlanTier,
    success_url: str,
    cancel_url: str,
    request: Request,
) -> dict:
    """Create a Stripe Checkout session and persist the audit trail."""
    context = _configured_context()
    return await billing_facade.create_checkout_session_data(
        db,
        org_id=org_id,
        user_id=user_id,
        plan_id=plan_id,
        success_url=success_url,
        cancel_url=cancel_url,
        request=request,
        load_context_fn=_load_context,
        get_org_for_billing_or_404_fn=billing_queries.get_org_for_billing_or_404,
        get_or_create_customer_fn=get_or_create_stripe_customer,
        write_audit_log_fn=write_audit_log,
        create_checkout_session_fn=stripe.checkout.Session.create,
        billing_origin_url_fn=context.billing_origin_url,
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
) -> dict:
    """Create a Stripe Checkout session for one-time analysis credits."""
    context = _configured_context()
    return await billing_facade.create_credit_pack_checkout_session_data(
        db,
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=credit_pack_id,
        success_url=success_url,
        cancel_url=cancel_url,
        request=request,
        load_context_fn=_load_context,
        get_org_for_billing_or_404_fn=billing_queries.get_org_for_billing_or_404,
        get_or_create_customer_fn=get_or_create_stripe_customer,
        write_audit_log_fn=write_audit_log,
        create_checkout_session_fn=stripe.checkout.Session.create,
        billing_origin_url_fn=context.billing_origin_url,
        logger=logger,
    )


async def get_credit_pack_checkout_reconciliation_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: str,
) -> dict[str, object]:
    """Return the current user's authoritative credit-purchase ledger state."""
    return await billing_queries.get_credit_pack_checkout_reconciliation(
        db,
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
    )


async def create_portal_session_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
) -> dict:
    """Create a Stripe Customer Portal session and persist the audit trail."""
    context = _configured_context()
    return await billing_facade.create_portal_session_data(
        db,
        org_id=org_id,
        user_id=user_id,
        request=request,
        load_context_fn=_load_context,
        get_org_for_billing_or_404_fn=billing_queries.get_org_for_billing_or_404,
        get_or_create_customer_fn=get_or_create_stripe_customer,
        write_audit_log_fn=write_audit_log,
        create_portal_session_fn=stripe.billing_portal.Session.create,
        billing_origin_url_fn=context.billing_origin_url,
        logger=logger,
    )


async def get_usage_summary_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict:
    """Return the current billing-cycle usage summary for an organization."""
    return await billing_facade.get_usage_summary_data(
        db,
        org_id=org_id,
        load_context_fn=_load_context,
        get_org_fn=billing_queries.get_org_for_billing_or_404,
        get_monthly_usage_fn=get_monthly_usage,
    )


async def list_invoice_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict:
    """Return recent Stripe invoices for an organization."""
    return await billing_facade.list_invoice_data(
        db,
        org_id=org_id,
        load_context_fn=_load_context,
        get_org_for_billing_or_404_fn=billing_queries.get_org_for_billing_or_404,
        list_invoices_fn=stripe.Invoice.list,
        map_invoice_list_fn=billing_queries.map_invoice_list,
        logger=logger,
    )


# ── Subscription sync ──────────────────────────────────────────────────────


async def sync_subscription_status(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> dict:
    """Sync the org's subscription status from Stripe.

    Fetches the latest subscription data from Stripe and updates the
    org's plan and settings accordingly.

    Returns a dict with the synced subscription info.
    """
    return await billing_facade.sync_subscription_status(
        db,
        org_id=org_id,
        load_context_fn=_load_context,
        get_org_by_id_fn=billing_queries.get_org_by_id,
        retrieve_subscription_fn=stripe.Subscription.retrieve,
        sync_subscription_mutation_fn=billing_sync.sync_subscription_status_impl,
        logger=logger,
    )
