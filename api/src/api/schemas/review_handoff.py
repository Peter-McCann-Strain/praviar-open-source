"""Schemas for analysis-scoped legal review handoff actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.review_status import AnalysisReviewStatusResponse


class CreateAnalysisReviewHandoffRequest(BaseModel):
    """Create a targeted comment and optionally escalate the analysis into review."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)
    review_note: str = Field(default="", max_length=4000)
    target_type: Literal["analysis", "patent", "claim"] = "analysis"
    target_id: str = Field(default="", max_length=255)
    mentions: list[str] = Field(default_factory=list, max_length=50)
    promote_to_under_review: bool = True


class AnalysisReviewHandoffResponse(BaseModel):
    """Result of a targeted review handoff from the report workspace."""

    model_config = ConfigDict(extra="forbid")

    comment_id: uuid.UUID
    created_at: datetime | None = None
    target_type: Literal["analysis", "patent", "claim"]
    target_id: str = ""
    escalated_to_review: bool = False
    review_status: AnalysisReviewStatusResponse
