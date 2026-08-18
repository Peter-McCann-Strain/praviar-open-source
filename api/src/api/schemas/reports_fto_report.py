"""Top-level validated FTO report response model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from praviar_pipeline.models.regulatory_exclusivity import RegulatoryExclusivity
from praviar_pipeline.models.report_source_spans import ClaimSourceSpanMap
from pydantic import BaseModel, Field, field_validator

from api.schemas.reports_core import (
    AnalysisFailureResponse,
    DataLimitationResponse,
    DoEAssessmentResponse,
    InvalidityAssessmentResponse,
    PatentAnalysisResponse,
    RiskSummaryResponse,
    SourceHealthResponse,
    StepTokenUsageResponse,
    VerificationResultResponse,
)
from api.schemas.reports_drawings import PatentDrawingAnalysisResponse
from api.schemas.reports_tracking import (
    AuthorityCoverageResponse,
    BibliographyEntryResponse,
    CertificationScopeResponse,
    ClaimConstructionRecordResponse,
    ClaimProgramDecisionResponse,
    ClearanceDecisionResponse,
    CommercialExposureResponse,
    CoverageGapResponse,
    CriticFindingResponse,
    CriticReportResponse,
    DecisionScopeResponse,
    EvidenceAdapterResultResponse,
    EvidenceArtifactResponse,
    EvidenceCollectionDirectiveResponse,
    EvidenceCollectorRunResponse,
    FutureRiskFindingResponse,
    JurisdictionDecisionResponse,
    MatterEvidenceIndexResponse,
    MatterGraphResponse,
    MatterGraphSummaryResponse,
    MatterStoreResponse,
    PipelineAuditTrailResponse,
    ProsecutionDossierResponse,
    ProsecutionFindingResponse,
    RecordCompletenessResponse,
    RunObservabilityResponse,
    SearchLoopResultResponse,
    VerificationSummaryResponse,
)
from api.schemas.reports_types import CohortStatus


class FTOReportResponse(BaseModel):
    """Validated response schema for the full FTO report.

    Validates all top-level keys so callers get type guarantees, while
    keeping fast-evolving pipeline sections permissive and the review-facing
    decision surfaces explicitly typed.
    """

    report_id: str
    generated_at: datetime
    praviar_pipeline_version: str = ""
    compound: dict[str, Any]
    risk_summary: RiskSummaryResponse
    clearance_decision: ClearanceDecisionResponse | dict[str, Any] = Field(default_factory=dict)
    decision_scope: DecisionScopeResponse | dict[str, Any] = Field(default_factory=dict)
    supporting_scope: DecisionScopeResponse | dict[str, Any] = Field(default_factory=dict)
    certification_scope: CertificationScopeResponse | dict[str, Any] = Field(default_factory=dict)
    cohort_status: CohortStatus | None = None
    jurisdiction_decisions: list[JurisdictionDecisionResponse] = Field(default_factory=list)
    patent_analyses: list[PatentAnalysisResponse] = Field(default_factory=list)
    doe_assessments: list[DoEAssessmentResponse] = Field(default_factory=list)
    invalidity_assessments: list[InvalidityAssessmentResponse] = Field(default_factory=list)
    drawing_analyses: list[PatentDrawingAnalysisResponse] = Field(
        default_factory=list,
        description=(
            "Per-patent drawing analyses produced by step 2.75. Surfaces extracted "
            "chemical structures and Markush metadata (is_markush, markush_cxsmiles, "
            "markush_r_groups) so the web UI can distinguish R-group templates from "
            "fully-specified molecules."
        ),
    )
    drawing_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregate statistics across all drawing analyses.",
    )
    verification: VerificationResultResponse = Field(default_factory=VerificationResultResponse)
    prosecution_findings: list[ProsecutionFindingResponse] = Field(default_factory=list)
    prosecution_dossiers: list[ProsecutionDossierResponse] = Field(default_factory=list)
    claim_construction_record: ClaimConstructionRecordResponse | dict[str, Any] = Field(
        default_factory=dict
    )
    future_risk: list[FutureRiskFindingResponse] = Field(default_factory=list)
    commercial_exposure: CommercialExposureResponse | dict[str, Any] = Field(default_factory=dict)
    claim_program_decisions: list[ClaimProgramDecisionResponse] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifactResponse] = Field(default_factory=list)
    evidence_adapter_results: list[EvidenceAdapterResultResponse] = Field(default_factory=list)
    collector_runs: list[EvidenceCollectorRunResponse] = Field(default_factory=list)
    evidence_collection_plan: list[EvidenceCollectionDirectiveResponse] = Field(
        default_factory=list
    )
    coverage_gaps: list[CoverageGapResponse] = Field(default_factory=list)
    matter_graph: MatterGraphResponse | dict[str, Any] = Field(default_factory=dict)
    matter_graph_summary: MatterGraphSummaryResponse | dict[str, Any] = Field(default_factory=dict)
    matter_store: MatterStoreResponse | dict[str, Any] = Field(default_factory=dict)
    claim_source_span_map: ClaimSourceSpanMap = Field(default_factory=ClaimSourceSpanMap)
    authority_coverage: AuthorityCoverageResponse | dict[str, Any] = Field(default_factory=dict)
    record_completeness: RecordCompletenessResponse | dict[str, Any] = Field(default_factory=dict)
    run_observability: RunObservabilityResponse | dict[str, Any] = Field(default_factory=dict)
    matter_evidence_index: MatterEvidenceIndexResponse | dict[str, Any] = Field(
        default_factory=dict
    )
    total_patents_found: int = 0
    patents_after_triage: int = 0
    search_sources_used: list[str] = Field(default_factory=list)
    source_health: SourceHealthResponse = Field(default_factory=SourceHealthResponse)
    scholarly_prior_art_count: int = 0
    analysis_failures: list[AnalysisFailureResponse] = Field(default_factory=list)
    data_limitations: list[DataLimitationResponse] = Field(default_factory=list)
    audit_trail: PipelineAuditTrailResponse = Field(default_factory=PipelineAuditTrailResponse)
    patent_narratives: dict[str, str] = Field(default_factory=dict)
    critic_report: CriticReportResponse | None = None
    review_issues: list[CriticFindingResponse] = Field(default_factory=list)
    regulatory_exclusivity: RegulatoryExclusivity | None = None
    disclaimer: str = ""
    llm_models_used: dict[str, str] = Field(default_factory=dict)
    search_loop_result: SearchLoopResultResponse | None = None
    execution_profile: Literal["world_class_adaptive"] = "world_class_adaptive"
    report_pipeline: Literal["world_class_adaptive"] = "world_class_adaptive"
    trust_mode: str = "explorer"
    intended_actions: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    jurisdiction_bundle: str = "custom"
    development_stage: str = "discovery"
    asset_type_hint: str = "unknown"
    routing_profile: dict[str, Any] = Field(default_factory=dict)
    opinion_readiness: dict[str, Any] = Field(default_factory=dict)
    data_coverage: dict[str, Any] = Field(default_factory=dict)
    search_strategy_log: list[dict[str, Any]] = Field(default_factory=list)
    negative_search_log: list[dict[str, Any]] = Field(default_factory=list)
    source_convergence: dict[str, Any] = Field(default_factory=dict)
    jurisdiction_matrix: list[dict[str, Any]] = Field(default_factory=list)
    jurisdiction_certification: list[dict[str, Any]] = Field(default_factory=list)
    jurisdiction_source_coverage: list[dict[str, Any]] = Field(default_factory=list)
    jurisdiction_local_review_required: list[str] = Field(default_factory=list)
    uncertainty_register: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_traces: list[dict[str, Any]] = Field(default_factory=list)
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    bibliography: list[BibliographyEntryResponse] = Field(default_factory=list)
    verification_summary: VerificationSummaryResponse | dict[str, Any] = Field(default_factory=dict)
    factual_accuracy_rate: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    step_token_usage: list[StepTokenUsageResponse] = Field(default_factory=list)
    patent_details: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None

    @field_validator("clearance_decision", mode="before")
    @classmethod
    def _validate_clearance_decision(
        cls, value: ClearanceDecisionResponse | dict[str, Any] | None
    ) -> ClearanceDecisionResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return ClearanceDecisionResponse.model_validate(value)

    @field_validator("decision_scope", mode="before")
    @classmethod
    def _validate_decision_scope(
        cls, value: DecisionScopeResponse | dict[str, Any] | None
    ) -> DecisionScopeResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return DecisionScopeResponse.model_validate(value)

    @field_validator("supporting_scope", mode="before")
    @classmethod
    def _validate_supporting_scope(
        cls, value: DecisionScopeResponse | dict[str, Any] | None
    ) -> DecisionScopeResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return DecisionScopeResponse.model_validate(value)

    @field_validator("certification_scope", mode="before")
    @classmethod
    def _validate_certification_scope(
        cls, value: CertificationScopeResponse | dict[str, Any] | None
    ) -> CertificationScopeResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return CertificationScopeResponse.model_validate(value)

    @field_validator("claim_construction_record", mode="before")
    @classmethod
    def _validate_claim_construction_record(
        cls, value: ClaimConstructionRecordResponse | dict[str, Any] | None
    ) -> ClaimConstructionRecordResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return ClaimConstructionRecordResponse.model_validate(value)

    @field_validator("commercial_exposure", mode="before")
    @classmethod
    def _validate_commercial_exposure(
        cls, value: CommercialExposureResponse | dict[str, Any] | None
    ) -> CommercialExposureResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return CommercialExposureResponse.model_validate(value)

    @field_validator("matter_evidence_index", mode="before")
    @classmethod
    def _validate_matter_evidence_index(
        cls, value: MatterEvidenceIndexResponse | dict[str, Any] | None
    ) -> MatterEvidenceIndexResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return MatterEvidenceIndexResponse.model_validate(value)

    @field_validator("matter_graph_summary", mode="before")
    @classmethod
    def _validate_matter_graph_summary(
        cls, value: MatterGraphSummaryResponse | dict[str, Any] | None
    ) -> MatterGraphSummaryResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return MatterGraphSummaryResponse.model_validate(value)

    @field_validator("matter_store", mode="before")
    @classmethod
    def _validate_matter_store(
        cls, value: MatterStoreResponse | dict[str, Any] | None
    ) -> MatterStoreResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return MatterStoreResponse.model_validate(value)

    @field_validator("matter_graph", mode="before")
    @classmethod
    def _validate_matter_graph(
        cls, value: MatterGraphResponse | dict[str, Any] | None
    ) -> MatterGraphResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return MatterGraphResponse.model_validate(value)

    @field_validator("authority_coverage", mode="before")
    @classmethod
    def _validate_authority_coverage(
        cls, value: AuthorityCoverageResponse | dict[str, Any] | None
    ) -> AuthorityCoverageResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return AuthorityCoverageResponse.model_validate(value)

    @field_validator("record_completeness", mode="before")
    @classmethod
    def _validate_record_completeness(
        cls, value: RecordCompletenessResponse | dict[str, Any] | None
    ) -> RecordCompletenessResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return RecordCompletenessResponse.model_validate(value)

    @field_validator("run_observability", mode="before")
    @classmethod
    def _validate_run_observability(
        cls, value: RunObservabilityResponse | dict[str, Any] | None
    ) -> RunObservabilityResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return RunObservabilityResponse.model_validate(value)

    @field_validator("critic_report", mode="before")
    @classmethod
    def _validate_critic_report(
        cls, value: CriticReportResponse | dict[str, Any] | None
    ) -> CriticReportResponse | None:
        if value is None:
            return None
        return CriticReportResponse.model_validate(value)

    @field_validator("search_loop_result", mode="before")
    @classmethod
    def _validate_search_loop_result(
        cls, value: SearchLoopResultResponse | dict[str, Any] | None
    ) -> SearchLoopResultResponse | None:
        if value is None:
            return None
        return SearchLoopResultResponse.model_validate(value)

    @field_validator("verification_summary", mode="before")
    @classmethod
    def _validate_verification_summary(
        cls, value: VerificationSummaryResponse | dict[str, Any] | None
    ) -> VerificationSummaryResponse | dict[str, Any]:
        if value in (None, {}):
            return {}
        return VerificationSummaryResponse.model_validate(value)


__all__ = ["FTOReportResponse"]
