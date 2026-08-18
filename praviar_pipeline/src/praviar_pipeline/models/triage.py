"""Triage models — output of Step 3 (LLM triage)."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Relevance(enum.StrEnum):
    """Patent relevance classification."""

    RELEVANT = "relevant"
    POSSIBLY_RELEVANT = "possibly_relevant"
    NOT_RELEVANT = "not_relevant"
    UNKNOWN = "unknown"


class TriageResult(BaseModel):
    """LLM triage classification for a single patent."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    relevance: Relevance
    reason: str = Field(description="Why this patent is/isn't relevant to the compound")
    blocking_potential: str = Field(
        default="",
        description="Brief assessment of blocking risk if relevant",
    )
    key_claims: list[int] = Field(
        default_factory=list,
        description="Claim numbers identified as potentially blocking",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Drawing-based auto-triage fields (populated when triage bypasses LLM)
    drawing_auto_filtered: bool = Field(
        default=False,
        description="True if triage was decided by drawing evidence, not LLM",
    )
    drawing_tanimoto: float | None = Field(
        default=None,
        description="Highest Tanimoto from drawing analysis (for audit trail)",
    )

    @field_validator("relevance", mode="before")
    @classmethod
    def _coerce_relevance(cls, v: str) -> str:
        """Case-insensitive coercion of relevance values."""
        if isinstance(v, str):
            v = v.strip().lower().replace(" ", "_").replace("-", "_")
            mapping = {e.value: e.value for e in Relevance}
            mapping.update(
                {
                    "possibly relevant": "possibly_relevant",
                    "not relevant": "not_relevant",
                    "irrelevant": "not_relevant",
                    "maybe": "possibly_relevant",
                }
            )
            return mapping.get(v, v)
        return v

    @field_validator("key_claims", mode="before")
    @classmethod
    def _validate_key_claims(cls, v: list) -> list:
        """Ensure all claim numbers are positive."""
        if isinstance(v, list):
            return [c for c in v if isinstance(c, int) and c >= 1]
        return v

    @model_validator(mode="after")
    def _check_blocking_potential(self) -> TriageResult:
        """Warn if relevant patent has no blocking potential assessment."""
        if (
            self.relevance in (Relevance.RELEVANT, Relevance.POSSIBLY_RELEVANT)
            and not self.blocking_potential
        ):
            import structlog

            structlog.get_logger().warning(
                "triage_missing_blocking_potential",
                relevance=self.relevance.value,
            )
        return self


class TriageBatch(BaseModel):
    """A batch of triage results from a single LLM call."""

    model_config = ConfigDict(extra="forbid")

    results: list[TriageResult]
    model_used: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
