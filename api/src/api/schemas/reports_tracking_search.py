"""Search-loop and coverage report models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from api.schemas.reports_tracking_evidence import EvidenceCollectionDirectiveResponse


class ExpandedSearchQueriesResponse(BaseModel):
    """Search expansion payload used by the iterative search loop."""

    patent_synonyms: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    key_assignees: list[str] = Field(default_factory=list)
    process_keywords: list[str] = Field(default_factory=list)
    compound_class_terms: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class CoverageGapResponse(BaseModel):
    """A single gap identified during iterative search."""

    gap_type: str = ""
    description: str = ""
    suggested_action: str = ""


class CoverageAssessmentResponse(BaseModel):
    """Coverage-assessment payload emitted by the search loop."""

    coverage_adequate: bool = False
    confidence: float = 0.0
    gaps_identified: list[CoverageGapResponse] = Field(default_factory=list)
    evidence_collection_directives: list[EvidenceCollectionDirectiveResponse] = Field(
        default_factory=list
    )
    suggested_queries: ExpandedSearchQueriesResponse | dict[str, Any] | None = None
    iteration_summary: str = ""
    assignee_distribution: dict[str, int] = Field(default_factory=dict)
    cpc_distribution: dict[str, int] = Field(default_factory=dict)

    @field_validator("suggested_queries", mode="before")
    @classmethod
    def _validate_suggested_queries(
        cls,
        value: ExpandedSearchQueriesResponse | dict[str, Any] | None,
    ) -> ExpandedSearchQueriesResponse | dict[str, Any] | None:
        if value in (None, {}):
            return value
        return ExpandedSearchQueriesResponse.model_validate(value)


class SearchIterationLogResponse(BaseModel):
    """A single iteration record from the search loop."""

    iteration_number: int = 1
    patents_found_new: int = 0
    patents_found_total: int = 0
    triage_relevant_new: int = 0
    queries_used: ExpandedSearchQueriesResponse | dict[str, Any] | None = None
    assessment: CoverageAssessmentResponse | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @field_validator("queries_used", mode="before")
    @classmethod
    def _validate_queries_used(
        cls,
        value: ExpandedSearchQueriesResponse | dict[str, Any] | None,
    ) -> ExpandedSearchQueriesResponse | dict[str, Any] | None:
        if value in (None, {}):
            return value
        return ExpandedSearchQueriesResponse.model_validate(value)


class SearchLoopResultResponse(BaseModel):
    """Complete iterative search-loop output."""

    iterations_completed: int = 1
    iteration_logs: list[SearchIterationLogResponse] = Field(default_factory=list)
    final_assessment: CoverageAssessmentResponse | None = None
    pending_collection_directives: list[EvidenceCollectionDirectiveResponse] = Field(
        default_factory=list
    )
    termination_reason: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
