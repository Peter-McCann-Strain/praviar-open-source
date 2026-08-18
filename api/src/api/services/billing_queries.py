"""Billing query helpers — reads, usage limits, and read-model orchestration.

Absorbs: billing_queries_read, billing_queries_usage, and billing_read_models.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.models import Analysis, AnalysisCreditLedger, AnalysisStatus, Organization
from api.errors import APIError
from api.schemas.billing import CreditPackId
from api.services import billing_policy
from api.services.billing_policy import BillingServiceContext, load_billing_service_context

logger = structlog.get_logger()

# ── Type aliases ───────────────────────────────────────────────────────────

GetOrgFn = Callable[[AsyncSession, uuid.UUID], Awaitable[Any]]
GetMonthlyUsageFn = Callable[..., Awaitable[int]]


@dataclass(frozen=True)
class AnalysisCreditReservation:
    """Purchased-credit reservation created during capacity enforcement."""

    org_id: uuid.UUID
    reservation_id: str
    credits: int


@dataclass(frozen=True)
class AnalysisCapacitySnapshot:
    """Read-only capacity snapshot using the same ledger rules as enforcement."""

    available: int
    used: int
    entitlement_limit: int


# ── Read-side query helpers (absorbed from billing_queries_read) ───────────

# Non-terminal statuses that count against the monthly limit.  Counting
# PENDING and RUNNING as well as COMPLETED prevents concurrent submissions
# from all passing the check before any one of them finishes.
_BILLABLE_STATUSES = (
    AnalysisStatus.PENDING,
    AnalysisStatus.RUNNING,
    AnalysisStatus.COMPLETED,
)


def _effective_analysis_period_start(
    org: Organization,
    *,
    now: datetime | None = None,
) -> datetime:
    """Return the single period boundary used by usage and credit ledgers."""
    configured_start = org.billing_cycle_start
    if configured_start is not None:
        return configured_start
    current = now or datetime.now(UTC)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def get_monthly_usage(
    db: AsyncSession,
    org_id: uuid.UUID,
    period_start: datetime | None = None,
) -> int:
    """Count non-terminal analyses for the org in the current billing period.

    Includes PENDING and RUNNING (not just COMPLETED) so that concurrent
    submissions cannot all pass the limit check before any one finishes.
    """
    if period_start is None:
        now = datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.org_id == org_id,
            Analysis.status.in_(_BILLABLE_STATUSES),
            Analysis.created_at >= period_start,
        )
    )
    return int(result.scalar_one())


async def get_org_by_id(db: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    """Fetch an organisation by ID."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    return result.scalar_one_or_none()


async def get_org_for_billing_or_404(db, org_id: uuid.UUID) -> Organization:
    """Fetch an organisation by ID or raise the billing 404 contract."""
    org = await get_org_by_id(db, org_id)
    if org is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "Not Found", "Organization not found")
    return org


def map_invoice_list(invoices) -> dict:
    """Map Stripe invoice objects into the API response shape."""
    items = []
    for invoice in invoices.data:
        items.append(
            {
                "id": invoice.id,
                "number": invoice.number,
                "status": invoice.status or "unknown",
                "amount_due_cents": invoice.amount_due or 0,
                "amount_paid_cents": invoice.amount_paid or 0,
                "currency": invoice.currency or "usd",
                "created_at": datetime.fromtimestamp(invoice.created, tz=UTC),
                "hosted_invoice_url": invoice.hosted_invoice_url,
                "pdf_url": invoice.invoice_pdf,
            }
        )

    return {"invoices": items, "has_more": invoices.has_more}


async def build_billing_status_data(
    db,
    *,
    org: Organization,
    get_monthly_usage_fn,
    plan_to_display_tier_fn,
    plan_limit_for_fn,
    get_credit_balance_fn=None,
    get_consumed_credit_count_fn=None,
) -> dict:
    """Build the current billing snapshot for an organisation."""
    plan_key = plan_to_display_tier_fn(org.plan)
    period_start = _effective_analysis_period_start(org)
    entitlement = await _load_analysis_capacity_entitlement(
        db,
        org=org,
        plan_key=plan_key,
        period_start=period_start,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=plan_limit_for_fn,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
    )

    return {
        "org_id": org.id,
        "plan": plan_key,
        "stripe_customer_id": org.stripe_customer_id,
        "stripe_subscription_id": org.stripe_subscription_id,
        "subscription_status": org.subscription_status,
        "current_period_start": org.billing_cycle_start,
        "current_period_end": org.current_period_end,
        "analyses_used": entitlement.analyses_used,
        "analyses_limit": entitlement.effective_limit,
        "included_analyses_limit": entitlement.included_limit,
        "purchased_credits_balance": entitlement.purchased_credits_balance,
        "purchased_credits_used": entitlement.consumed_purchased_credits,
        "cancel_at_period_end": org.cancel_at_period_end,
    }


async def build_usage_summary_data(
    db,
    *,
    org: Organization,
    get_monthly_usage_fn,
    plan_to_display_tier_fn,
    plan_limit_for_fn,
    get_credit_balance_fn=None,
    get_consumed_credit_count_fn=None,
) -> dict:
    """Build the current billing-cycle usage summary."""
    plan_key = plan_to_display_tier_fn(org.plan)

    period_start = _effective_analysis_period_start(org)
    period_end = org.current_period_end

    entitlement = await _load_analysis_capacity_entitlement(
        db,
        org=org,
        plan_key=plan_key,
        period_start=period_start,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=plan_limit_for_fn,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
    )
    limit = entitlement.effective_limit
    usage_pct = min((entitlement.analyses_used / limit) * 100, 100.0) if limit > 0 else 0.0
    overage = max(entitlement.analyses_used - limit, 0)

    cost_per_analysis_cents = {
        "free": 0,
        "starter": 5000,
        "pro": 3500,
        "enterprise": 2500,
    }

    return {
        "org_id": org.id,
        "plan": plan_key,
        "analyses_used": entitlement.analyses_used,
        "analyses_limit": limit,
        "included_analyses_limit": entitlement.included_limit,
        "purchased_credits_balance": entitlement.purchased_credits_balance,
        "purchased_credits_used": entitlement.consumed_purchased_credits,
        "usage_pct": round(usage_pct, 1),
        "cost_this_month_cents": entitlement.analyses_used
        * cost_per_analysis_cents.get(plan_key, 0),
        "overage_analyses": overage,
        "period_start": period_start,
        "period_end": period_end,
    }


# ── Usage-limit helpers (absorbed from billing_queries_usage) ──────────────


async def get_analysis_credit_balance(db, org_id: uuid.UUID) -> int:
    """Return remaining purchased analysis credits for an org."""
    result = await db.execute(
        select(func.coalesce(func.sum(AnalysisCreditLedger.credits_delta), 0)).where(
            AnalysisCreditLedger.org_id == org_id
        )
    )
    return max(int(result.scalar_one() or 0), 0)


async def get_credit_pack_checkout_reconciliation(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: str,
) -> dict[str, object]:
    """Return only an exact current-user purchase or an indistinguishable pending state."""
    result = await db.execute(
        select(AnalysisCreditLedger).where(
            AnalysisCreditLedger.org_id == org_id,
            AnalysisCreditLedger.user_id == user_id,
            AnalysisCreditLedger.kind == "purchase",
            AnalysisCreditLedger.stripe_checkout_session_id == session_id,
        )
    )
    ledger = result.scalar_one_or_none()
    if ledger is None:
        return {"status": "pending", "session_id": session_id}

    try:
        ledger_credit_pack_id = ledger.credit_pack_id
        if not isinstance(ledger_credit_pack_id, str):
            raise TypeError("credit pack identifier is not a string")
        credit_pack_id = CreditPackId(ledger_credit_pack_id)
    except (TypeError, ValueError):
        logger.error(
            "credit_pack_reconciliation_invalid_ledger_pack",
            ledger_entry_id=str(ledger.id),
            org_id=str(org_id),
            session_id=session_id,
        )
        return {"status": "pending", "session_id": session_id}

    expected_credits = billing_policy.credit_pack_size(credit_pack_id)
    payment_intent_id = str(ledger.stripe_payment_intent_id or "").strip()
    if ledger.credits_delta != expected_credits or not payment_intent_id.startswith("pi_"):
        logger.error(
            "credit_pack_reconciliation_invalid_purchase_identity",
            ledger_entry_id=str(ledger.id),
            org_id=str(org_id),
            session_id=session_id,
            credit_pack_id=credit_pack_id.value,
            credits_delta=ledger.credits_delta,
            expected_credits=expected_credits,
            has_payment_intent=bool(payment_intent_id),
        )
        return {"status": "pending", "session_id": session_id}

    current_balance = await get_analysis_credit_balance(db, org_id)
    return {
        "status": "applied",
        "session_id": session_id,
        "ledger_entry_id": ledger.id,
        "credit_pack_id": credit_pack_id,
        "credits_applied": ledger.credits_delta,
        "current_purchased_credits_balance": current_balance,
        "applied_at": ledger.created_at,
    }


async def get_consumed_analysis_credit_count(
    db,
    org_id: uuid.UUID,
    period_start: datetime | None,
) -> int:
    """Return net credit-covered analyses consumed in the current billing period."""
    query = select(func.coalesce(func.sum(AnalysisCreditLedger.credits_delta), 0)).where(
        AnalysisCreditLedger.org_id == org_id,
        AnalysisCreditLedger.kind.in_(("consume", "refund")),
    )
    if period_start is not None:
        query = query.where(AnalysisCreditLedger.created_at >= period_start)

    result = await db.execute(query)
    return max(-(int(result.scalar_one() or 0)), 0)


async def _load_analysis_capacity_entitlement(
    db,
    *,
    org,
    plan_key: str,
    period_start: datetime | None,
    get_monthly_usage_fn,
    plan_limit_for_fn,
    get_credit_balance_fn=None,
    get_consumed_credit_count_fn=None,
) -> billing_policy.AnalysisCapacityEntitlement:
    """Load the ledger inputs and resolve the shared capacity policy once."""
    credit_balance_fn = get_credit_balance_fn or get_analysis_credit_balance
    consumed_credit_count_fn = get_consumed_credit_count_fn or get_consumed_analysis_credit_count
    used = await get_monthly_usage_fn(db, org.id, period_start)
    purchased_credits_balance = await credit_balance_fn(db, org.id)
    credit_analyses_used = await consumed_credit_count_fn(db, org.id, period_start)
    return billing_policy.resolve_analysis_capacity_entitlement(
        analyses_used=used,
        configured_included_limit=org.max_analyses_per_month,
        consumed_purchased_credits=credit_analyses_used,
        plan_key=plan_key,
        purchased_credits_balance=purchased_credits_balance,
        subscription_status=getattr(org, "subscription_status", None),
        plan_limit_for_fn=plan_limit_for_fn,
    )


async def get_available_analysis_capacity(
    db: AsyncSession,
    *,
    org: Organization,
) -> AnalysisCapacitySnapshot:
    """Return available analysis capacity without reserving or mutating credits."""
    plan_key = org.plan.value if org.plan else "free"
    period_start = _effective_analysis_period_start(org)
    entitlement = await _load_analysis_capacity_entitlement(
        db,
        org=org,
        plan_key=plan_key,
        period_start=period_start,
        get_monthly_usage_fn=get_monthly_usage,
        plan_limit_for_fn=billing_policy.plan_limit_for,
    )
    return AnalysisCapacitySnapshot(
        available=entitlement.available,
        used=entitlement.analyses_used,
        entitlement_limit=entitlement.effective_limit,
    )


async def consume_analysis_credits(
    db,
    *,
    org_id: uuid.UUID,
    credits: int,
    analysis_id: uuid.UUID | None = None,
    details: dict | None = None,
    reservation_id: str | None = None,
) -> None:
    """Append a credit-consumption ledger entry inside the caller transaction."""
    if credits <= 0:
        return
    ledger_details = dict(details or {})
    if reservation_id:
        ledger_details["reservation_id"] = reservation_id
        existing = await db.execute(
            select(AnalysisCreditLedger.id).where(
                AnalysisCreditLedger.org_id == org_id,
                AnalysisCreditLedger.kind == "consume",
                AnalysisCreditLedger.details["reservation_id"].astext == reservation_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
    db.add(
        AnalysisCreditLedger(
            org_id=org_id,
            analysis_id=analysis_id,
            kind="consume",
            credits_delta=-credits,
            details=ledger_details,
        )
    )
    await db.flush()


async def refund_analysis_credit_reservation(
    db,
    *,
    org_id: uuid.UUID,
    reservation: AnalysisCreditReservation,
    analysis_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    """Append a compensating refund entry for a reserved purchased credit."""
    if reservation.credits <= 0:
        return
    if reservation.org_id != org_id:
        raise ValueError("reservation org_id does not match refund org_id")

    existing = await db.execute(
        select(AnalysisCreditLedger.id).where(
            AnalysisCreditLedger.org_id == org_id,
            AnalysisCreditLedger.kind == "refund",
            AnalysisCreditLedger.details["reservation_id"].astext == reservation.reservation_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    refund_details = {
        "reservation_id": reservation.reservation_id,
        **(details or {}),
    }
    db.add(
        AnalysisCreditLedger(
            org_id=org_id,
            analysis_id=analysis_id,
            kind="refund",
            credits_delta=reservation.credits,
            details=refund_details,
        )
    )
    await db.flush()


async def refund_cancelled_analysis_credits(
    db,
    *,
    org_id: uuid.UUID,
    analysis_id: uuid.UUID,
    details: dict | None = None,
) -> int:
    """Refund purchased credits reserved by a cancelled analysis.

    Analysis creation records every purchased-credit reservation in the
    append-only ledger. Cancellation must compensate those entries in the same
    transaction as the lifecycle transition so a user cannot lose a purchased
    credit for work they explicitly stopped. The reservation helper keeps this
    operation idempotent across retries.
    """
    result = await db.execute(
        select(AnalysisCreditLedger).where(
            AnalysisCreditLedger.org_id == org_id,
            AnalysisCreditLedger.analysis_id == analysis_id,
            AnalysisCreditLedger.kind == "consume",
        )
    )
    refunded = 0
    for consumption in result.scalars().all():
        consumption_details = consumption.details if isinstance(consumption.details, dict) else {}
        reservation_id = consumption_details.get("reservation_id")
        if not isinstance(reservation_id, str) or not reservation_id:
            raise RuntimeError("Purchased-credit consumption is missing its reservation identifier")
        credits = -int(consumption.credits_delta)
        if credits <= 0:
            raise RuntimeError("Purchased-credit consumption has an invalid delta")
        await refund_analysis_credit_reservation(
            db,
            org_id=org_id,
            reservation=AnalysisCreditReservation(
                org_id=org_id,
                reservation_id=reservation_id,
                credits=credits,
            ),
            analysis_id=analysis_id,
            details={
                "reason": "analysis_cancelled",
                "source": "analysis.delete",
                **(details or {}),
            },
        )
        refunded += credits
    return refunded


async def check_usage_limit_for_org(
    db,
    *,
    org,
    get_monthly_usage_fn,
    plan_limit_for_fn,
    requested_analyses: int = 1,
    get_credit_balance_fn=get_analysis_credit_balance,
    get_consumed_credit_count_fn=get_consumed_analysis_credit_count,
    consume_credits_fn=consume_analysis_credits,
    reservation_id: str | None = None,
    reservation_details: dict | None = None,
    credit_reservations: list[AnalysisCreditReservation] | None = None,
    analysis_id: uuid.UUID | None = None,
    defer_credit_consumption: bool = False,
) -> tuple[bool, int, int]:
    """Reserve capacity for upcoming analyses if the org has allowance or credits."""
    plan_key = org.plan.value if org.plan else "free"

    # Free and not-yet-billed organisations have no Stripe cycle start. Use the
    # same current-calendar-month boundary for analysis usage and credit-ledger
    # consumption so historical credits cannot restore current allowance.
    period_start = _effective_analysis_period_start(org)
    entitlement = await _load_analysis_capacity_entitlement(
        db,
        org=org,
        plan_key=plan_key,
        period_start=period_start,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=plan_limit_for_fn,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
    )
    credits_needed = entitlement.purchased_credits_required(requested_analyses)

    if credits_needed <= 0:
        return True, entitlement.analyses_used, entitlement.effective_limit

    if entitlement.purchased_credits_balance >= credits_needed:
        effective_reservation_id = reservation_id or (
            str(uuid.uuid4()) if credit_reservations is not None else None
        )
        ledger_details = {
            "requested_analyses": requested_analyses,
            "included_remaining": entitlement.included_remaining,
            **(reservation_details or {}),
        }
        if not defer_credit_consumption:
            await consume_credits_fn(
                db,
                org_id=org.id,
                credits=credits_needed,
                analysis_id=analysis_id,
                details=ledger_details,
                reservation_id=effective_reservation_id,
            )
        if credit_reservations is not None and effective_reservation_id:
            credit_reservations.append(
                AnalysisCreditReservation(
                    org_id=org.id,
                    reservation_id=effective_reservation_id,
                    credits=credits_needed,
                )
            )
        return True, entitlement.analyses_used, entitlement.effective_limit

    return False, entitlement.analyses_used, entitlement.effective_limit


async def record_usage_event(db, org_id, analysis_id) -> None:
    """Increment the org's analyses_used_this_month counter for a completed analysis.

    WARNING: This function is dead code. analyses_used_this_month is never
    incremented at runtime and never read by enforcement code. Quota enforcement
    uses get_monthly_usage (live COUNT(*) of Analysis rows), not this counter.
    Do NOT read analyses_used_this_month for enforcement — it is always 0 in
    production. Either wire this function into the analysis-complete path (under
    the same FOR UPDATE lock as check_usage_limit) or delete it.
    """
    await db.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(
            analyses_used_this_month=Organization.analyses_used_this_month + 1,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "usage_event_recorded",
        org_id=str(org_id),
        analysis_id=str(analysis_id),
    )


async def check_usage_limit(
    db,
    org_id,
    *,
    reservation_id: str | None = None,
    reservation_details: dict | None = None,
    credit_reservations: list[AnalysisCreditReservation] | None = None,
    analysis_id: uuid.UUID | None = None,
    defer_credit_consumption: bool = False,
) -> tuple[bool, int, int]:
    """Check whether an organisation is within its monthly analysis limit.

    Uses SELECT ... FOR UPDATE on the org row to serialize concurrent quota
    checks.  Without this lock, two requests at used == limit-1 can both read
    within_limit=True before either INSERT commits, silently exceeding the cap.
    """
    return await reserve_analysis_capacity(
        db,
        org_id,
        requested_analyses=1,
        reservation_id=reservation_id,
        reservation_details=reservation_details,
        credit_reservations=credit_reservations,
        analysis_id=analysis_id,
        defer_credit_consumption=defer_credit_consumption,
    )


async def reserve_analysis_capacity(
    db,
    org_id,
    *,
    requested_analyses: int,
    reservation_id: str | None = None,
    reservation_details: dict | None = None,
    credit_reservations: list[AnalysisCreditReservation] | None = None,
    analysis_id: uuid.UUID | None = None,
    defer_credit_consumption: bool = False,
) -> tuple[bool, int, int]:
    """Reserve plan allowance or purchased credits for upcoming analyses."""
    if requested_analyses <= 0:
        raise ValueError("requested_analyses must be positive")

    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if org is None:
        logger.error("usage_check_org_not_found", org_id=str(org_id))
        return False, 0, 0

    within_limit, used, limit = await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage,
        requested_analyses=requested_analyses,
        plan_limit_for_fn=lambda plan_key: billing_policy.plan_limit_for(
            plan_key,
            get_settings(),
        ),
        reservation_id=reservation_id,
        reservation_details=reservation_details,
        credit_reservations=credit_reservations,
        analysis_id=analysis_id,
        defer_credit_consumption=defer_credit_consumption,
    )
    logger.debug(
        "usage_limit_check",
        org_id=str(org.id),
        plan=org.plan.value if org.plan else "free",
        used=used,
        limit=limit,
        requested_analyses=requested_analyses,
        within_limit=within_limit,
    )
    return within_limit, used, limit


# ── Read-model orchestration (absorbed from billing_read_models) ───────────


async def _load_org_and_context(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn: Callable[[], BillingServiceContext],
    get_org_fn: GetOrgFn,
) -> tuple[BillingServiceContext, Any]:
    context = load_context_fn()
    org = await get_org_fn(db, org_id)
    return context, org


async def get_billing_status_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn: Callable[[], BillingServiceContext] = load_billing_service_context,
    get_org_fn: GetOrgFn = get_org_for_billing_or_404,
    get_monthly_usage_fn: GetMonthlyUsageFn = get_monthly_usage,
    get_credit_balance_fn=None,
    get_consumed_credit_count_fn=None,
) -> dict:
    """Load the billing status read model for an organisation."""
    context, org = await _load_org_and_context(
        db,
        org_id=org_id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
    )
    return await build_billing_status_data(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_to_display_tier_fn=context.plan_to_display_tier,
        plan_limit_for_fn=context.plan_limit_for,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
    )


async def get_usage_summary_data(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    load_context_fn: Callable[[], BillingServiceContext] = load_billing_service_context,
    get_org_fn: GetOrgFn = get_org_for_billing_or_404,
    get_monthly_usage_fn: GetMonthlyUsageFn = get_monthly_usage,
    get_credit_balance_fn=None,
    get_consumed_credit_count_fn=None,
) -> dict:
    """Load the usage summary read model for an organisation."""
    context, org = await _load_org_and_context(
        db,
        org_id=org_id,
        load_context_fn=load_context_fn,
        get_org_fn=get_org_fn,
    )
    return await build_usage_summary_data(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_to_display_tier_fn=context.plan_to_display_tier,
        plan_limit_for_fn=context.plan_limit_for,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
    )


__all__ = [
    "AnalysisCapacitySnapshot",
    "AnalysisCreditReservation",
    "build_billing_status_data",
    "build_usage_summary_data",
    "check_usage_limit",
    "check_usage_limit_for_org",
    "consume_analysis_credits",
    "get_analysis_credit_balance",
    "get_available_analysis_capacity",
    "get_billing_status_data",
    "get_consumed_analysis_credit_count",
    "get_monthly_usage",
    "get_org_by_id",
    "get_org_for_billing_or_404",
    "get_usage_summary_data",
    "map_invoice_list",
    "record_usage_event",
    "refund_analysis_credit_reservation",
    "refund_cancelled_analysis_credits",
    "reserve_analysis_capacity",
]
