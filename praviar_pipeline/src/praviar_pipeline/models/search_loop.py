"""Search loop models — output of agentic search iteration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from praviar_pipeline.models.report_evidence import EvidenceCollectionDirective
from praviar_pipeline.models.search import ExpandedSearchQueries


class CoverageGap(BaseModel):
    """A specific gap identified in search coverage."""

    model_config = ConfigDict(extra="ignore")

    gap_type: str = (
        ""  # "missing_assignee", "missing_cpc", "search_bias", "source_failure", "low_confidence"
    )
    description: str = ""
    suggested_action: str = ""

    @field_validator("gap_type", mode="before")
    @classmethod
    def _coerce_gap_type(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower().replace(" ", "_").replace("-", "_")
        return v


class CoverageAssessment(BaseModel):
    """Assessment of search coverage adequacy."""

    model_config = ConfigDict(extra="ignore")

    coverage_adequate: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    gaps_identified: list[CoverageGap] = Field(default_factory=list)
    evidence_collection_directives: list[EvidenceCollectionDirective] = Field(default_factory=list)
    suggested_queries: ExpandedSearchQueries | None = None
    iteration_summary: str = ""
    assignee_distribution: dict[str, int] = Field(default_factory=dict)
    cpc_distribution: dict[str, int] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.0


class SearchIterationLog(BaseModel):
    """Log entry for a single search iteration."""

    model_config = ConfigDict(extra="forbid")

    iteration_number: int = 1
    patents_found_new: int = 0
    patents_found_total: int = 0
    triage_relevant_new: int = 0
    queries_used: ExpandedSearchQueries | None = None
    assessment: CoverageAssessment | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class SearchLoopResult(BaseModel):
    """Complete result of the agentic search loop."""

    model_config = ConfigDict(extra="forbid")

    iterations_completed: int = 1
    iteration_logs: list[SearchIterationLog] = Field(default_factory=list)
    final_assessment: CoverageAssessment | None = None
    pending_collection_directives: list[EvidenceCollectionDirective] = Field(default_factory=list)
    termination_reason: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
