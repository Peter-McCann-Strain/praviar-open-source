"""Multi-perspective analysis models."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from praviar_pipeline.models.analysis_claims import RiskLevel
from praviar_pipeline.models.analysis_validation import coerce_enum_value


class PerspectiveType(enum.StrEnum):
    """Expert perspective for multi-perspective analysis."""

    PATENT_ATTORNEY = "patent_attorney"
    MEDICINAL_CHEMIST = "medicinal_chemist"
    BUSINESS_ANALYST = "business_analyst"


class PerspectiveAnalysis(BaseModel):
    """Analysis from a single expert perspective."""

    model_config = ConfigDict(extra="ignore")

    perspective: PerspectiveType
    key_findings: list[str] = Field(default_factory=list)
    risk_assessment: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_risk_level: RiskLevel | None = None
    evidence_cited: list[str] = Field(default_factory=list)

    @field_validator("perspective", mode="before")
    @classmethod
    def _coerce_perspective(cls, v: str) -> str:
        return coerce_enum_value(
            v,
            valid_values={e.value for e in PerspectiveType},
            default=PerspectiveType.PATENT_ATTORNEY.value,
            log_event="perspective_coerced",
            replace_spaces=True,
        )

    @field_validator("recommended_risk_level", mode="before")
    @classmethod
    def _coerce_risk(cls, v: str | None) -> str | None:
        """Normalise the recommended risk level, failing loud on bad input."""
        return coerce_enum_value(
            v,
            valid_values={e.value for e in RiskLevel},
            default=RiskLevel.MEDIUM.value,
            log_event="recommended_risk_level_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )


class MultiPerspectiveSynthesis(BaseModel):
    """Synthesized output from all expert perspectives."""

    model_config = ConfigDict(extra="ignore")

    perspectives: list[PerspectiveAnalysis] = Field(default_factory=list)
    synthesized_risk: RiskLevel | None = None
    disagreements: list[str] = Field(default_factory=list)
    synthesis_reasoning: str = ""

    @field_validator("synthesized_risk", mode="before")
    @classmethod
    def _coerce_synth_risk(cls, v: str | None) -> str | None:
        """Normalise the synthesised risk level, failing loud on bad input."""
        return coerce_enum_value(
            v,
            valid_values={e.value for e in RiskLevel},
            default=RiskLevel.MEDIUM.value,
            log_event="synthesized_risk_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )
