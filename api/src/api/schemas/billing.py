"""Request/response schemas for billing and Stripe integration."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanTier(StrEnum):
    """Available billing plans. Mirrors OrgPlan but includes STARTER."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class CreditPackId(StrEnum):
    """One-time analysis credit packs available through Stripe Checkout."""

    SINGLE_ANALYSIS = "single_analysis"
    PORTFOLIO_5 = "portfolio_5"
    DILIGENCE_15 = "diligence_15"
    SCALE_30 = "scale_30"


class CreditCapacityRequestStatus(StrEnum):
    """Lifecycle state for a durable Report Credit capacity request."""

    PENDING = "pending"
    FULFILLED = "fulfilled"
    DECLINED = "declined"


# ── Response schemas ────────────────────────────────────────────────────────


class BillingStatusResponse(BaseModel):
    """Current org billing status: plan, subscription, and usage overview."""

    org_id: uuid.UUID
    can_manage_billing: bool
    plan: PlanTier
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    subscription_status: str | None = None  # "active", "past_due", "canceled", etc.
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    analyses_used: int = 0
    analyses_limit: int = Field(
        default=0,
        ge=0,
        description=(
            "Effective current-period ceiling; subtract analyses_used to obtain "
            "the same remaining capacity enforced at launch."
        ),
    )
    included_analyses_limit: int = Field(default=0, ge=0)
    purchased_credits_balance: int = Field(default=0, ge=0)
    purchased_credits_used: int = Field(
        default=0,
        ge=0,
        description="Net purchased Report Credits consumed in the current billing period.",
    )
    cancel_at_period_end: bool = False

    model_config = ConfigDict(from_attributes=True)


class UsageSummaryResponse(BaseModel):
    """Current month usage summary with cost estimates."""

    org_id: uuid.UUID
    plan: PlanTier
    analyses_used: int = 0
    analyses_limit: int = Field(
        default=0,
        ge=0,
        description=(
            "Effective current-period ceiling; subtract analyses_used to obtain "
            "the same remaining capacity enforced at launch."
        ),
    )
    included_analyses_limit: int = Field(default=0, ge=0)
    purchased_credits_balance: int = Field(default=0, ge=0)
    purchased_credits_used: int = Field(
        default=0,
        ge=0,
        description="Net purchased Report Credits consumed in the current billing period.",
    )
    usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    cost_this_month_cents: int = 0
    currency: str = "usd"
    overage_analyses: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None


class InvoiceItem(BaseModel):
    """Single invoice from Stripe."""

    id: str
    number: str | None = None
    status: str  # "paid", "open", "void", "uncollectible"
    amount_due_cents: int = 0
    amount_paid_cents: int = 0
    currency: str = "usd"
    created_at: datetime
    hosted_invoice_url: str | None = None
    pdf_url: str | None = None


class InvoiceListResponse(BaseModel):
    """List of past invoices."""

    invoices: list[InvoiceItem]
    has_more: bool = False


# ── Request schemas ─────────────────────────────────────────────────────────


class CreateCheckoutRequest(BaseModel):
    """Request to create a Stripe Checkout session for plan upgrade."""

    plan_id: PlanTier = Field(
        ...,
        description="Target plan tier (starter or pro)",
    )
    success_url: str = Field(
        default="",
        max_length=2048,
        description="URL to redirect to after successful checkout",
    )
    cancel_url: str = Field(
        default="",
        max_length=2048,
        description="URL to redirect to if checkout is cancelled",
    )


class CreateCreditPackCheckoutRequest(BaseModel):
    """Request to create a Stripe Checkout session for one-time credit packs."""

    credit_pack_id: CreditPackId = Field(
        ...,
        description="Analysis credit pack to purchase",
    )
    success_url: str = Field(
        default="",
        max_length=2048,
        description="URL to redirect to after successful checkout",
    )
    cancel_url: str = Field(
        default="",
        max_length=2048,
        description="URL to redirect to if checkout is cancelled",
    )


class CreateCreditCapacityRequest(BaseModel):
    """Ask active workspace administrators to add Report Credit capacity."""

    requested_reports: int = Field(default=1, ge=1, le=30)
    source: Literal["analysis_launch", "capacity_watch", "launch_retry"]


class ResolveCreditCapacityRequest(BaseModel):
    """Administrator resolution for one pending capacity request."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["fulfilled", "declined"]
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_decline_reason(self) -> ResolveCreditCapacityRequest:
        normalized_note = (self.note or "").strip()
        if self.status == "declined" and len(normalized_note) < 4:
            raise ValueError("A decline reason of at least 4 characters is required")
        self.note = normalized_note or None
        return self


class CreateCheckoutResponse(BaseModel):
    """Response containing the Stripe Checkout session URL."""

    checkout_url: str
    session_id: str


class CreditCapacityRequestResponse(BaseModel):
    """Delivery result for an in-app Report Credit capacity request."""

    notified_admins: int = Field(ge=1)
    request_id: uuid.UUID
    requested_at: datetime
    status: Literal["sent"]


class CreditCapacityRequestItem(BaseModel):
    """One durable capacity request visible within the caller's role scope."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_user_id: uuid.UUID | None = None
    requester_name: str
    requested_reports: int = Field(ge=1, le=30)
    source: Literal["analysis_launch", "capacity_watch", "launch_retry"]
    status: CreditCapacityRequestStatus
    notified_admins: int = Field(ge=1)
    requested_at: datetime
    resolved_at: datetime | None = None
    resolved_by_user_id: uuid.UUID | None = None
    resolution_note: str | None = None
    fulfillment_credit_ledger_id: uuid.UUID | None = None
    resolution_outcome: Literal["resolved", "already_resolved"] | None = None


class CreditCapacityRequestListResponse(BaseModel):
    """Paginated role-scoped capacity requests."""

    items: list[CreditCapacityRequestItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)


class CreditPackCheckoutReconciliationPending(BaseModel):
    """A Stripe return that has not produced an authoritative ledger entry."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending"] = "pending"
    session_id: str


class CreditPackCheckoutReconciliationApplied(BaseModel):
    """An authoritative Report Credit purchase recorded in the org ledger."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["applied"] = "applied"
    session_id: str
    ledger_entry_id: uuid.UUID
    credit_pack_id: CreditPackId
    credits_applied: int = Field(gt=0)
    current_purchased_credits_balance: int = Field(ge=0)
    applied_at: datetime


CreditPackCheckoutReconciliationResponse = Annotated[
    CreditPackCheckoutReconciliationPending | CreditPackCheckoutReconciliationApplied,
    Field(discriminator="status"),
]


class CreatePortalResponse(BaseModel):
    """Response containing the Stripe Customer Portal URL."""

    portal_url: str


# ── Webhook audit schema ───────────────────────────────────────────────────


class WebhookEventLog(BaseModel):
    """Audit trail entry for a processed Stripe webhook event."""

    event_id: str
    event_type: str
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    org_id: uuid.UUID | None = None
    processed_at: datetime
    success: bool = True
    error_message: str | None = None
