"""Schemas for governed evidence search over report provenance."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

EvidenceRetrievalMode = Literal["report_evidence", "external_evidence"]


class EvidenceSearchRequest(BaseModel):
    """Inbound query for governed evidence search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=200)
    retrieval_mode: EvidenceRetrievalMode = "report_evidence"

    @field_validator("query")
    @classmethod
    def require_substantive_query(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError(
                "Evidence search query must contain at least 2 non-whitespace characters"
            )
        return value


class EvidenceSearchProvenanceItemResponse(BaseModel):
    """One provenance field rendered alongside a governed evidence result."""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: str


class EvidenceSearchFollowUpTargetResponse(BaseModel):
    """Comment-routing target suggested for a governed evidence result."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["analysis", "patent", "claim"] = "analysis"
    target_id: str = ""
    suggested_note: str = ""


class EvidenceSearchProviderCapabilityResponse(BaseModel):
    """One governed provider layer represented in the current evidence scope."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    provider_name: str
    provider_class: str = "report_derived"
    provider_status: Literal["active", "caution_only", "declared_only"] = "active"
    live_retrieval_supported: bool = False
    configured: bool = False
    configured_for_org: bool = False
    materialized_in_report: bool = False
    execution_mode: Literal[
        "placeholder_contract",
        "report_materialized",
        "bundled_dataset",
        "live_api",
    ] = "placeholder_contract"
    modality_coverage: list[str] = Field(default_factory=list)
    jurisdiction_coverage: list[str] = Field(default_factory=list)
    governance_note: str = ""
    retrieved_at: str = ""
    source_as_of: str = ""
    dataset_version: str = ""


class EvidenceSearchProviderExecutionResponse(BaseModel):
    """Execution/completeness receipt kept separate from evidence rows."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    provider_name: str
    status: Literal["succeeded", "failed"]
    result_count: int = Field(ge=0)
    explicit_zero_results: bool
    completed_at: AwareDatetime
    error_type: str = ""


class EvidenceSearchProviderNoticeResponse(BaseModel):
    """Non-evidentiary execution or routing notice."""

    model_config = ConfigDict(extra="forbid")

    provider_name: str
    notice_type: Literal["execution_failure", "missing_handler", "routing_policy"]
    message: str


class EvidenceSearchResultResponse(BaseModel):
    """One governed evidence-search result with provenance context."""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    title: str
    summary: str
    source_name: str = ""
    authority_tier: str = "supporting"
    freshness: str = ""
    artifact_type: str = ""
    section: str = ""
    patent_id: str = ""
    relevance: float = 0.0
    provenance: list[EvidenceSearchProvenanceItemResponse] = Field(default_factory=list)
    follow_up_target: EvidenceSearchFollowUpTargetResponse | None = None


class EvidenceSearchScopeResponse(BaseModel):
    """Search-scope metadata for governed evidence expansion."""

    model_config = ConfigDict(extra="forbid")

    mode: EvidenceRetrievalMode = "report_evidence"
    external_live_retrieval: bool = False
    comment_routing_available: bool = True
    sources_considered: list[str] = Field(default_factory=list)
    governed_note: str = (
        "Searches report-derived evidence and provenance only. "
        "No external live retrieval runs here."
    )
    provider_capabilities: list[EvidenceSearchProviderCapabilityResponse] = Field(
        default_factory=list
    )
    providers: list[EvidenceSearchProviderCapabilityResponse] = Field(default_factory=list)
    hybrid_evidence_ready: bool = False


class EvidenceSearchResponse(BaseModel):
    """Governed evidence-search response."""

    model_config = ConfigDict(extra="forbid")

    query: str
    interpreted_query: str
    scope: EvidenceSearchScopeResponse
    results: list[EvidenceSearchResultResponse] = Field(default_factory=list)
    provider_executions: list[EvidenceSearchProviderExecutionResponse] = Field(default_factory=list)
    provider_notices: list[EvidenceSearchProviderNoticeResponse] = Field(default_factory=list)
    total: int = 0
