"""Billing routes — plan status, Stripe Checkout, Customer Portal, usage, and invoices."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from api.db.models import User
from api.deps import PERMISSION_MATRIX, DBSession, require_permission
from api.ratelimit import authenticated_org_user_rate_limit_key, limiter
from api.schemas.billing import (
    BillingStatusResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    CreateCreditCapacityRequest,
    CreateCreditPackCheckoutRequest,
    CreatePortalResponse,
    CreditCapacityRequestItem,
    CreditCapacityRequestListResponse,
    CreditCapacityRequestResponse,
    CreditCapacityRequestStatus,
    CreditPackCheckoutReconciliationResponse,
    InvoiceListResponse,
    ResolveCreditCapacityRequest,
    UsageSummaryResponse,
)
from api.services.billing import (
    create_checkout_session_data,
    create_credit_capacity_request_data,
    create_credit_pack_checkout_session_data,
    create_portal_session_data,
    get_billing_status_data,
    get_credit_pack_checkout_reconciliation_data,
    get_usage_summary_data,
    list_credit_capacity_requests_data,
    list_invoice_data,
    resolve_credit_capacity_request_data,
)

router = APIRouter()

BillingViewer = Annotated[User, Depends(require_permission("billing.view"))]
BillingManager = Annotated[User, Depends(require_permission("billing.manage"))]


async def _credit_capacity_requester(
    request: Request,
    user: Annotated[User, Depends(require_permission("analysis.create"))],
) -> User:
    """Bind authenticated identity for the per-org/per-user request throttle."""
    request.state.rate_limit_org_id = str(user.org_id)
    request.state.rate_limit_user_id = str(user.id)
    return user


CreditCapacityRequester = Annotated[User, Depends(_credit_capacity_requester)]


# ── GET /billing/status ────────────────────────────────────────────────────


@router.get("/billing/status", response_model=BillingStatusResponse)
async def get_billing_status(
    user: BillingViewer,
    db: DBSession,
) -> dict:
    """Current org billing status: plan, usage, subscription details."""
    snapshot = await get_billing_status_data(db, org_id=user.org_id)
    return {
        **snapshot,
        "can_manage_billing": user.role in PERMISSION_MATRIX["billing.manage"],
    }


# ── POST /billing/credit-capacity-requests ────────────────────────────────


@router.post(
    "/billing/credit-capacity-requests",
    response_model=CreditCapacityRequestResponse,
    status_code=201,
)
@limiter.limit("3/hour", key_func=authenticated_org_user_rate_limit_key)
async def create_credit_capacity_request(
    body: CreateCreditCapacityRequest,
    user: CreditCapacityRequester,
    db: DBSession,
    request: Request,
) -> dict[str, object]:
    """Notify active workspace administrators that Report Credits are needed."""
    return await create_credit_capacity_request_data(
        db,
        user=user,
        requested_reports=body.requested_reports,
        source=body.source,
        request=request,
    )


# ── GET /billing/credit-capacity-requests ─────────────────────────────────


@router.get(
    "/billing/credit-capacity-requests",
    response_model=CreditCapacityRequestListResponse,
)
async def list_credit_capacity_requests(
    user: CreditCapacityRequester,
    db: DBSession,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    request_status: Annotated[
        CreditCapacityRequestStatus | None,
        Query(alias="status"),
    ] = None,
) -> dict[str, object]:
    """List all workspace requests for admins or only the caller's requests."""
    return await list_credit_capacity_requests_data(
        db,
        user=user,
        page=page,
        per_page=per_page,
        request_status=request_status.value if request_status else None,
    )


# ── POST /billing/credit-capacity-requests/{id}/resolve ───────────────────


@router.post(
    "/billing/credit-capacity-requests/{request_id}/resolve",
    response_model=CreditCapacityRequestItem,
)
async def resolve_credit_capacity_request(
    request_id: uuid.UUID,
    body: ResolveCreditCapacityRequest,
    user: BillingManager,
    db: DBSession,
    request: Request,
) -> dict[str, object]:
    """Resolve one pending workspace request as fulfilled or declined."""
    return await resolve_credit_capacity_request_data(
        db,
        user=user,
        request_id=request_id,
        resolution_status=body.status,
        note=body.note,
        request=request,
    )


# ── POST /billing/checkout ─────────────────────────────────────────────────


@router.post("/billing/checkout", response_model=CreateCheckoutResponse)
@limiter.limit("5/minute")
async def create_checkout_session(
    body: CreateCheckoutRequest,
    user: BillingManager,
    db: DBSession,
    request: Request,
) -> dict:
    """Create a Stripe Checkout session for plan upgrade."""
    return await create_checkout_session_data(
        db,
        org_id=user.org_id,
        user_id=user.id,
        plan_id=body.plan_id,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        request=request,
    )


# ── POST /billing/credit-packs/checkout ───────────────────────────────────


@router.post("/billing/credit-packs/checkout", response_model=CreateCheckoutResponse)
@limiter.limit("5/minute")
async def create_credit_pack_checkout_session(
    body: CreateCreditPackCheckoutRequest,
    user: BillingManager,
    db: DBSession,
    request: Request,
) -> dict:
    """Create a Stripe Checkout session for one-time analysis credits."""
    return await create_credit_pack_checkout_session_data(
        db,
        org_id=user.org_id,
        user_id=user.id,
        credit_pack_id=body.credit_pack_id,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        request=request,
    )


# ── GET /billing/credit-packs/reconciliation ──────────────────────────────


@router.get(
    "/billing/credit-packs/reconciliation",
    response_model=CreditPackCheckoutReconciliationResponse,
)
async def get_credit_pack_checkout_reconciliation(
    user: BillingViewer,
    db: DBSession,
    response: Response,
    session_id: Annotated[
        str,
        Query(
            min_length=12,
            max_length=255,
            pattern=r"^cs_(?:test|live)_[A-Za-z0-9]+$",
        ),
    ],
) -> dict[str, object]:
    """Return an exact user-scoped ledger match or a non-enumerating pending state."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return await get_credit_pack_checkout_reconciliation_data(
        db,
        org_id=user.org_id,
        user_id=user.id,
        session_id=session_id,
    )


# ── POST /billing/portal ──────────────────────────────────────────────────


@router.post("/billing/portal", response_model=CreatePortalResponse)
@limiter.limit("10/minute")
async def create_portal_session(
    user: BillingManager,
    db: DBSession,
    request: Request,
) -> dict:
    """Create a Stripe Customer Portal session for subscription management."""
    return await create_portal_session_data(
        db,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )


# ── GET /billing/usage ─────────────────────────────────────────────────────


@router.get("/billing/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user: BillingViewer,
    db: DBSession,
) -> dict:
    """Current month usage summary."""
    return await get_usage_summary_data(db, org_id=user.org_id)


# ── GET /billing/invoices ──────────────────────────────────────────────────


@router.get("/billing/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    user: BillingViewer,
    db: DBSession,
) -> dict:
    """List past invoices from Stripe for the org."""
    return await list_invoice_data(db, org_id=user.org_id)
