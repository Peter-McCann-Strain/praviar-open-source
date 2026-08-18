"""Schemas for human decisions on blocking pipeline checkpoints."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CheckpointType = Literal[
    "identity_review",
    "search_review",
    "triage_review",
    "analysis_review",
    "report_review",
]
CheckpointDecisionKind = Literal["approve", "reject", "modify"]
REPORT_REVIEW_CHECKPOINT_ID = re.compile(
    r"^[A-Za-z0-9._-]{1,64}:report_review:(?P<digest_prefix>[0-9a-f]{16})$"
)
REPORT_REVIEW_ATTESTATION_PREFIX = (
    "Reviewer attested to the bounded report draft and claim-source ledger bound to "
    "review payload SHA-256 "
)


def report_review_attestation_note(review_payload_sha256: str) -> str:
    """Return the only persisted approval note accepted for report review."""

    return f"{REPORT_REVIEW_ATTESTATION_PREFIX}{review_payload_sha256}."


class CheckpointDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_type: CheckpointType
    decision: CheckpointDecisionKind
    note: str = Field(default="", max_length=4000)
    review_payload_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _require_note_when_rejecting(self) -> CheckpointDecisionIn:
        if self.decision == "reject" and not self.note.strip():
            raise ValueError("note is required when decision is 'reject'")
        if (
            self.checkpoint_type == "identity_review"
            and self.decision == "approve"
            and not self.note.strip()
        ):
            raise ValueError("note is required when approving the resolved identity checkpoint")
        if self.checkpoint_type == "report_review" and self.decision == "approve":
            if self.review_payload_sha256 is None:
                raise ValueError(
                    "review_payload_sha256 is required when approving the report checkpoint"
                )
            if self.note != report_review_attestation_note(self.review_payload_sha256):
                raise ValueError(
                    "report approval note must attest to the exact review payload SHA-256"
                )
        elif self.review_payload_sha256 is not None:
            raise ValueError(
                "review_payload_sha256 is only accepted when approving the report checkpoint"
            )
        return self


class CheckpointDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    org_id: uuid.UUID
    checkpoint_id: str
    checkpoint_type: str
    decision: str
    note: str
    reviewer_id: uuid.UUID
    reviewed_at: datetime
    created_at: datetime
    updated_at: datetime
