"""Contracts for the governed claimed-use counsel receipt workflow."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from praviar_pipeline.models.accused_acts import (
    ClaimedUseMatchReceipt,
    LabelCarveOutState,
    RegulatorySubmissionPath,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClaimedUseReceiptIssueRequest(BaseModel):
    """Attorney affirmation for one exact report claim and proposed use."""

    model_config = ConfigDict(extra="forbid")

    expected_report_id: str = Field(min_length=1, max_length=64)
    expected_report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_id: str = Field(min_length=4, max_length=64)
    claim_number: int = Field(ge=1)
    accused_act_index: int = Field(ge=0)
    claimed_use_match: Literal[True]
    product_identity_match: Literal[True]

    @field_validator("patent_id")
    @classmethod
    def _normalize_patent_id(cls, value: str) -> str:
        normalized = "".join(value.strip().upper().split())
        if normalized != value:
            raise ValueError("patent_id must use its normalized uppercase form")
        return normalized


class ClaimedUseReceiptRevokeRequest(BaseModel):
    """Reasoned, append-only revocation of one counsel receipt."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 10:
            raise ValueError("revocation reason must contain at least 10 characters")
        return normalized


class ClaimedUseEligibleUse(BaseModel):
    """One server-resolved regulatory submission that can be attested."""

    model_config = ConfigDict(extra="forbid")

    accused_act_index: int
    jurisdiction: str
    actor: str
    start_date: date
    regulatory_path: RegulatorySubmissionPath
    target_product_identity: str
    proposed_indication: str
    proposed_label_use: str
    label_carve_out_state: LabelCarveOutState


class ClaimedUseReceiptOut(BaseModel):
    """Durable receipt plus workflow and issuer metadata."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    analysis_id: uuid.UUID
    report_id: str
    report_fingerprint: str
    patent_id: str
    claim_number: int
    accused_act_index: int
    accused_act_sha256: str
    receipt: ClaimedUseMatchReceipt
    issuer_user_id: uuid.UUID
    reviewer_role: Literal["attorney"]
    attestation_statement_version: Literal["claimed-use-counsel-affirmation-v1"]
    issued_at: datetime
    revoked_at: datetime | None
    revoked_by_user_id: uuid.UUID | None
    revocation_reason: str
    governs_current_report: bool
    can_revoke: bool


class ClaimedUseReceiptListResponse(BaseModel):
    """Current report coordinates, eligible uses, and immutable receipt history."""

    model_config = ConfigDict(extra="forbid")

    current_report_id: str
    current_report_fingerprint: str
    eligible_uses: list[ClaimedUseEligibleUse]
    items: list[ClaimedUseReceiptOut]
