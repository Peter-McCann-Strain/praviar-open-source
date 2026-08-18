"""Request/response schemas for reviewer accept/reject/edit decisions."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FindingType = Literal["patent", "claim_element", "doe", "invalidity"]
DecisionKind = Literal["accept", "reject", "edit"]


class ReviewerDecisionIn(BaseModel):
    """Inbound payload for creating or upserting a reviewer decision."""

    model_config = ConfigDict(extra="forbid")

    finding_type: FindingType
    finding_ref: str = Field(min_length=1, max_length=512)
    decision: DecisionKind
    note: str = Field(default="", max_length=4000)
    edited_text: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def _require_decision_evidence(self) -> "ReviewerDecisionIn":
        if self.decision == "edit" and not self.edited_text.strip():
            raise ValueError("edited_text is required when decision is 'edit'")
        if self.decision in {"reject", "edit"} and not self.note.strip():
            raise ValueError(
                "note is required when decision is 'reject' or 'edit'",
            )
        return self


class ReviewerDecisionOut(BaseModel):
    """Outbound representation of a persisted reviewer decision."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    finding_type: FindingType
    finding_ref: str
    decision: DecisionKind
    note: str
    edited_text: str
    reviewer_user_id: str
    reviewer_name: str
    reviewer_email: str
    created_at: datetime
    updated_at: datetime


class ReviewerDecisionListResponse(BaseModel):
    """List of reviewer decisions for an analysis, with counters."""

    items: list[ReviewerDecisionOut]
    counts: dict[str, int]
