"""Request/response schemas for attorney feedback."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SearchRelevanceLabel = Literal["relevant", "not_relevant", "uncertain"]
SearchRelevanceReason = Literal[
    "direct_claim_match",
    "structure_match",
    "family_duplicate",
    "wrong_jurisdiction",
    "irrelevant_compound",
    "non_blocking_subject_matter",
    "prior_art_only",
    "insufficient_evidence",
    "other",
]


class CorrectionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patent_id: str = Field(default="", max_length=64)
    field: str = Field(default="", max_length=100)
    original_value: str = Field(default="", max_length=500)
    corrected_value: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)


class SubmitFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    overall_accuracy: float = Field(ge=0.0, le=1.0)
    risk_level_correct: bool = True
    corrected_risk: str | None = Field(default=None, max_length=20)
    corrections: list[CorrectionEntry] = Field(default_factory=list, max_length=50)


class SearchRelevanceFeedbackIn(BaseModel):
    """Case-scoped attorney relevance judgment bound to an exact search plan."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str = Field(min_length=1, max_length=64)
    relevance: SearchRelevanceLabel
    reason_codes: list[SearchRelevanceReason] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=4000)
    suggested_queries: list[str] = Field(default_factory=list, max_length=20)
    expected_query_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("patent_id")
    @classmethod
    def _normalize_patent_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != value:
            raise ValueError("patent_id must not contain surrounding whitespace")
        return normalized

    @field_validator("reason_codes")
    @classmethod
    def _dedupe_reason_codes(
        cls,
        values: list[SearchRelevanceReason],
    ) -> list[SearchRelevanceReason]:
        return list(dict.fromkeys(values))

    @field_validator("suggested_queries")
    @classmethod
    def _validate_suggested_queries(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 500 for value in cleaned):
            raise ValueError("suggested query exceeds 500 characters")
        return cleaned


class SearchRelevanceFeedbackOut(BaseModel):
    """Persisted relevance judgment with reviewer identity snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    patent_id: str
    relevance: SearchRelevanceLabel
    reason_codes: list[SearchRelevanceReason]
    note: str
    suggested_queries: list[str]
    query_plan_sha256: str
    report_fingerprint: str
    reviewer_name: str
    reviewer_email: str
    created_at: datetime
    updated_at: datetime


class SearchRelevanceFeedbackListResponse(BaseModel):
    items: list[SearchRelevanceFeedbackOut]
    counts: dict[str, int]
