"""Evaluator-pass analysis models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from praviar_pipeline.models.analysis_claims import RiskLevel
from praviar_pipeline.models.analysis_validation import (
    coerce_enum_value,
    validate_governed_enum_value,
)


class EvaluationIssue(BaseModel):
    """A quality issue found by the evaluator pass."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str = Field(description="Type of quality issue found")
    description: str
    suggested_fix: str
    severity: str = Field(description="critical or advisory")

    @field_validator("issue_type", mode="before")
    @classmethod
    def _coerce_issue_type(cls, v: str) -> str:
        return validate_governed_enum_value(
            v,
            valid_values={
                "risk_claim_mismatch",
                "missing_element",
                "unsupported_conclusion",
                "inconsistent_confidence",
                "element_consistency",
                "missing_analysis",
                "confidence_calibration",
            },
            replace_spaces=True,
        )

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: str) -> str:
        return validate_governed_enum_value(
            v,
            valid_values={"critical", "advisory"},
        )


class AnalysisEvaluation(BaseModel):
    """Result of the evaluator pass on a patent analysis."""

    model_config = ConfigDict(extra="forbid")

    issues: list[EvaluationIssue] = Field(default_factory=list)
    overall_quality: str = Field(description="good, needs_revision, or poor")
    revised_risk_level: RiskLevel | None = Field(
        default=None,
        description="Corrected risk level if original was wrong",
    )

    @field_validator("overall_quality", mode="before")
    @classmethod
    def _coerce_quality(cls, v: str) -> str:
        return validate_governed_enum_value(
            v,
            valid_values={"good", "needs_revision", "poor"},
            replace_spaces=True,
        )

    @field_validator("revised_risk_level", mode="before")
    @classmethod
    def _coerce_revised_risk_level(cls, v: str | None) -> str | None:
        """Normalise the revised risk level, failing loud on bad input.

        The revised risk level is written straight back onto the patent
        analysis, so an unrecognised value raises rather than silently
        defaulting (the silent-zero defect).
        """
        return coerce_enum_value(
            v,
            valid_values={e.value for e in RiskLevel},
            default=RiskLevel.MEDIUM.value,
            log_event="revised_risk_level_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )
