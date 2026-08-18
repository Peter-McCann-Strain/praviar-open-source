"""Critic/Reviewer models — output of Step 4.5 portfolio-level review."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from praviar_pipeline.models.analysis_validation import validate_governed_enum_value


class CriticIssueSeverity(enum.StrEnum):
    """Severity of a critic finding."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class CriticIssueType(enum.StrEnum):
    """Type of quality issue found by the critic."""

    RISK_CLAIM_MISMATCH = "risk_claim_mismatch"
    INTERNAL_INCONSISTENCY = "internal_inconsistency"
    CROSS_PATENT_INCONSISTENCY = "cross_patent_inconsistency"
    MISSING_LIMITATION = "missing_limitation"
    INFEASIBLE_DESIGN_AROUND = "infeasible_design_around"
    CONFIDENCE_CALIBRATION = "confidence_calibration"
    ASSIGNEE_LOGIC_INCONSISTENCY = "assignee_logic_inconsistency"
    MISSING_DEPENDENT_CLAIM = "missing_dependent_claim"
    TRANSITIONAL_PHRASE_ISSUE = "transitional_phrase_issue"


class CriticFinding(BaseModel):
    """A single issue identified by the critic agent."""

    model_config = ConfigDict(extra="forbid")

    issue_type: CriticIssueType
    patent_id: str
    severity: CriticIssueSeverity
    description: str
    suggested_correction: str = ""
    claim_numbers: list[int] = Field(default_factory=list)
    related_patent_ids: list[str] = Field(default_factory=list)

    @field_validator("issue_type", mode="before")
    @classmethod
    def _coerce_issue_type(cls, v: str) -> str:
        return validate_governed_enum_value(
            v,
            valid_values={e.value for e in CriticIssueType},
            replace_spaces=True,
        )

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: str) -> str:
        return validate_governed_enum_value(
            v,
            valid_values={e.value for e in CriticIssueSeverity},
        )


class CriticReport(BaseModel):
    """Portfolio-level review of all patent analyses."""

    model_config = ConfigDict(extra="forbid")

    findings: list[CriticFinding] = Field(default_factory=list)
    patents_reviewed: int = 0
    patents_flagged_for_revision: list[str] = Field(default_factory=list)
    overall_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    portfolio_level_observations: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
