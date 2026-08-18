"""Top-level FTO I/O response and request models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from api.schemas.reports_types import RiskLevel

ExportSectionId = Literal[
    "executive_summary",
    "patent_analysis",
    "claim_charts",
    "invalidity_assessment",
    "audit_trail",
    "pipeline_metadata",
]
ExportAudienceId = Literal["full", "executive", "attorney", "scientist", "investor"]


class ReportSummaryResponse(BaseModel):
    """Denormalized summary from an analysis."""

    overall_risk: RiskLevel | None
    blocking_patents_count: int | None
    total_patents_found: int
    executive_summary: str
    risk_ratings_restricted: bool = False

    model_config = ConfigDict(from_attributes=True)


class ExportRequest(BaseModel):
    """Request body for triggering an export."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["pdf", "docx", "pptx", "xlsx", "csv", "json"]
    sections: list[ExportSectionId] = Field(default_factory=list, max_length=50)
    audience: ExportAudienceId = "full"


class ExportJobResponse(BaseModel):
    """Response after requesting an export."""

    job_id: uuid.UUID
    status: str
    download_url: str | None = None
    format: str | None = None
    file_size_bytes: int = 0
    manifest_schema_version: str | None = None
    manifest_hash: str | None = None
    manifest_snapshot: dict[str, Any] | None = None
    artifact_sha256: str | None = None
    report_payload_sha256: str | None = None
    artifact_currency: Literal["current", "superseded"] = "current"
    superseded_at: datetime | None = None
    superseded_reason: str | None = None
    superseded_conclusion_ids: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    error_message: str | None = None
    retryable: bool = False
    retry_after_seconds: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ExternalReportGrantCreateRequest(BaseModel):
    """Create a mailbox-verified external report grant."""

    model_config = ConfigDict(extra="forbid")

    recipient_email: EmailStr
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_views: int = Field(default=25, ge=1, le=100)


class ReportSearchRequest(BaseModel):
    """Request to search within a report."""

    query: str = Field(..., min_length=2, max_length=500)


class ExternalReportGrantResponse(BaseModel):
    """Sender-visible grant metadata; the raw link token is create-only."""

    id: uuid.UUID
    recipient_email: EmailStr
    recipient_domain: str
    invitation_sent_at: datetime | None = None
    expires_at: datetime
    revoked_at: datetime | None = None
    max_views: int
    view_count: int
    download_allowed: bool = False
    max_downloads: int = 0
    download_count: int = 0
    last_accessed_at: datetime | None = None
    status: Literal[
        "active",
        "delivery_pending",
        "delivery_rejected",
        "delivery_outcome_unknown",
        "delivery_cancelled_by_policy",
        "delivery_cancelled_expired",
        "delivery_cancelled_retention_expired",
        "delivery_reconciliation_alert",
        "expired",
        "revoked",
        "view_limit_reached",
    ]


class ExternalReportGrantCreatedResponse(ExternalReportGrantResponse):
    """Create/replay response; the raw token is available only before cleanup."""

    share_token: str | None = Field(
        default=None,
        min_length=40,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    invitation_status: Literal["provider_accepted"] = "provider_accepted"
    replayed: bool = False


class ExternalReportGrantListResponse(BaseModel):
    """Active and historical grants for one analysis."""

    items: list[ExternalReportGrantResponse] = Field(default_factory=list)


ExternalReportGrantActivityEvent = Literal[
    "delivery_dispatch_started",
    "delivery_provider_accepted",
    "delivery_rejected",
    "delivery_outcome_unknown",
    "delivery_cancelled_by_policy",
    "delivery_cancelled_expired",
    "delivery_cancelled_retention_expired",
    "delivery_reconciliation_alert",
    "invitation_sent",
    "recipient_verified",
    "report_viewed",
    "revoked",
    "revoked_by_policy",
    "revoked_by_reissue",
]


class ExternalReportGrantActivityItem(BaseModel):
    """One non-secret immutable event in a sender-visible grant timeline."""

    id: uuid.UUID
    event: ExternalReportGrantActivityEvent
    occurred_at: datetime
    view_number: int | None = Field(default=None, ge=1)


class ExternalReportGrantActivityResponse(BaseModel):
    """Activity for one org-, analysis-, and grant-scoped recipient grant."""

    items: list[ExternalReportGrantActivityItem] = Field(default_factory=list)


class ExternalGrantVerificationRequest(BaseModel):
    """One-time mailbox verification code submission."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[0-9]{8}$")


class ExternalGrantVerificationResponse(BaseModel):
    """Short-lived access proof returned after consuming a valid code."""

    access_secret: str = Field(
        min_length=40,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    access_expires_at: datetime


class ExternalGrantChallengeResponse(BaseModel):
    """Generic challenge response that does not disclose recipient identity."""

    status: Literal["verification_sent"] = "verification_sent"


__all__ = [
    "ExportJobResponse",
    "ExportRequest",
    "ReportSearchRequest",
    "ReportSummaryResponse",
    "ExternalGrantChallengeResponse",
    "ExternalGrantVerificationRequest",
    "ExternalGrantVerificationResponse",
    "ExternalReportGrantCreateRequest",
    "ExternalReportGrantCreatedResponse",
    "ExternalReportGrantListResponse",
    "ExternalReportGrantActivityEvent",
    "ExternalReportGrantActivityItem",
    "ExternalReportGrantActivityResponse",
    "ExternalReportGrantResponse",
]
