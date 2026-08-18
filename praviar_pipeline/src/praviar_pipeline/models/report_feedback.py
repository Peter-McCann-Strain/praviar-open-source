"""Attorney feedback models for completed reports."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ClaimCorrection(BaseModel):
    """An attorney's correction to a specific claim analysis."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_number: int
    element_number: int | None = None
    original_status: str
    corrected_status: str
    attorney_reasoning: str


class AttorneyFeedback(BaseModel):
    """Attorney feedback on a generated report."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    attorney_id: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_accuracy: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Attorney's assessment of overall report accuracy",
    )
    corrections: list[ClaimCorrection] = Field(default_factory=list)
    comments: str = ""
    risk_level_correct: bool = True
