"""Schemas for persisted report review workflow state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatusValue = Literal["pending", "under_review", "approved", "changes_requested"]


class AnalysisReviewDecisionCounts(BaseModel):
    """Counts of reviewer decisions recorded for an analysis."""

    model_config = ConfigDict(extra="forbid")

    accept: int = 0
    reject: int = 0
    edit: int = 0


class AnalysisReviewStatusResponse(BaseModel):
    """Report-level review workflow snapshot for an analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    status: ReviewStatusValue = "pending"
    note: str | None = None
    reviewer_name: str | None = None
    reviewer_email: str | None = None
    reviewed_at: datetime | None = None
    updated_at: datetime
    decision_counts: AnalysisReviewDecisionCounts = Field(
        default_factory=AnalysisReviewDecisionCounts
    )
    findings_total: int = 0
    findings_reviewed: int = 0
    completion_pct: float = 0.0


class UpdateAnalysisReviewStatusRequest(BaseModel):
    """Inbound payload for changing report review workflow state."""

    model_config = ConfigDict(extra="forbid")

    status: ReviewStatusValue
    note: str = Field(default="", max_length=4000)
