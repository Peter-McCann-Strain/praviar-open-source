"""Top-level patent analysis model."""

from __future__ import annotations

from datetime import date

from pydantic import ConfigDict, Field, field_validator

from praviar_pipeline.models._base import PatentBase
from praviar_pipeline.models.analysis_claims import (
    ClaimAnalysis,
    DesignAroundSuggestion,
    RiskLevel,
)
from praviar_pipeline.models.analysis_perspectives import (
    MultiPerspectiveSynthesis,
    PerspectiveAnalysis,
)
from praviar_pipeline.models.analysis_validation import coerce_enum_value
from praviar_pipeline.models.patent import OrangeBookInfo


class PatentAnalysis(PatentBase):
    """Complete FTO analysis for a single patent.

    Internal pipeline-state model populated from LLM output (Step 4).
    LLM output is a governed boundary: surplus fields and malformed nested
    structures are rejected so schema drift cannot silently change a legal
    conclusion. ``patent_id`` is inherited from
    :class:`~praviar_pipeline.models._base.PatentBase`.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    assignee: str = ""
    expiry_date: date | None = None
    claims_analyzed: list[ClaimAnalysis] = Field(default_factory=list)
    risk_level: RiskLevel
    risk_summary: str = Field(description="Executive summary of the risk from this patent")
    design_around_suggestions: list[DesignAroundSuggestion] = Field(default_factory=list)

    @field_validator("risk_level", mode="before")
    @classmethod
    def _coerce_risk_level(cls, v: str) -> str:
        """Normalise the risk level from LLM output, failing loud on bad input.

        Casing and surrounding whitespace are tolerated, but an unrecognised
        value raises rather than silently defaulting: a malformed risk level
        quietly becoming a lower band would drop the patent from invalidity
        assessment and action-item generation (the silent-zero defect).
        """
        return coerce_enum_value(
            v,
            valid_values={e.value for e in RiskLevel},
            default=RiskLevel.MEDIUM.value,
            log_event="risk_level_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )

    orange_book_info: OrangeBookInfo | None = None
    model_used: str = ""
    thinking_text: str = Field(
        default="",
        description="Extended thinking reasoning chain for debugging",
    )
    input_tokens: int = 0
    output_tokens: int = 0
    analysis_execution_profile: str = Field(
        default="world_class_adaptive",
        description="Unified runtime profile used for this patent analysis.",
    )
    analysis_stage: str = Field(
        default="single_pass",
        description="Internal adaptive stage that produced the final analysis.",
    )
    analysis_escalated: bool = Field(
        default=False,
        description="Whether this analysis escalated to agentic research.",
    )
    analysis_escalation_reasons: list[str] = Field(
        default_factory=list,
        description="Internal audit reasons for agentic escalation.",
    )
    analysis_execution_plan: dict[str, object] = Field(
        default_factory=dict,
        description="Internal adaptive execution-plan metadata.",
    )
    analysis_quality_gate_failures: list[str] = Field(
        default_factory=list,
        description="Quality gates that failed after claim analysis completed.",
    )
    analysis_review_required: bool = Field(
        default=False,
        description="Whether quality gates require human review before clearance.",
    )
    analysis_context_sha256: str = Field(
        default="",
        pattern=r"^(?:|[0-9a-f]{64})$",
        description=(
            "Deterministic receipt binding this analysis to the exact customer "
            "product, act, territory, jurisdiction, and development-stage context."
        ),
    )
    perspective_analyses: list[PerspectiveAnalysis] = Field(default_factory=list)
    multi_perspective_synthesis: MultiPerspectiveSynthesis | None = None
