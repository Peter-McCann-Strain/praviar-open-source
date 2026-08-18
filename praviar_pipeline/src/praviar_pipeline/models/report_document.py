"""Top-level FTO report document model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from praviar_pipeline.manifest import ReportManifest
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.audit import PipelineAuditTrail, StepTokenUsage
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.critic import CriticFinding, CriticReport
from praviar_pipeline.models.drawing import PatentDrawingAnalysis
from praviar_pipeline.models.equivalents import DoEAssessment
from praviar_pipeline.models.invalidity import InvalidityAssessment
from praviar_pipeline.models.regulatory_exclusivity import RegulatoryExclusivity
from praviar_pipeline.models.report_common import (
    REPORT_DISCLAIMER,
    ActionItem,
    AnalysisFailure,
    DataLimitation,
    RiskSummary,
    SourceHealth,
    _get_version,
)
from praviar_pipeline.models.report_decisioning import (
    CertificationScope,
    ClaimConstructionRecord,
    ClearanceDecision,
    CohortStatus,
    CommercialExposure,
    DecisionScope,
    FutureRiskFinding,
    JurisdictionDecision,
    OpinionReadiness,
    ProsecutionDossier,
    ProsecutionFinding,
)
from praviar_pipeline.models.report_evidence import (
    AuthorityCoverage,
    ClaimProgramDecision,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceCollectionDirective,
    EvidenceCollectorRun,
    MatterEvidenceIndex,
    MatterGraph,
    MatterGraphSummary,
    MatterStore,
    RecordCompleteness,
    RunObservability,
)
from praviar_pipeline.models.report_source_spans import ClaimSourceSpanMap
from praviar_pipeline.models.search_loop import CoverageGap, SearchLoopResult
from praviar_pipeline.models.verification import VerificationResult


class FTOReport(BaseModel):
    """Complete Freedom-to-Operate report."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    praviar_pipeline_version: str = Field(default_factory=_get_version)

    compound: ResolvedCompound

    risk_summary: RiskSummary
    clearance_decision: ClearanceDecision = Field(default_factory=ClearanceDecision)
    decision_scope: DecisionScope = Field(default_factory=DecisionScope)
    supporting_scope: DecisionScope = Field(default_factory=DecisionScope)
    certification_scope: CertificationScope = Field(default_factory=CertificationScope)
    trust_mode: Literal["explorer", "counsel", "monitor"] = "explorer"
    intended_actions: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    jurisdiction_bundle: str = "custom"
    development_stage: str = "discovery"
    asset_type_hint: str = "unknown"
    routing_profile: dict[str, Any] = Field(default_factory=dict)
    opinion_readiness: OpinionReadiness = Field(default_factory=OpinionReadiness)
    cohort_status: CohortStatus | None = None
    jurisdiction_decisions: list[JurisdictionDecision] = Field(default_factory=list)
    patent_analyses: list[PatentAnalysis] = Field(default_factory=list)
    doe_assessments: list[DoEAssessment] = Field(default_factory=list)
    invalidity_assessments: list[InvalidityAssessment] = Field(default_factory=list)
    verification: VerificationResult = Field(default_factory=VerificationResult)
    prosecution_findings: list[ProsecutionFinding] = Field(default_factory=list)
    prosecution_dossiers: list[ProsecutionDossier] = Field(default_factory=list)
    claim_construction_record: ClaimConstructionRecord = Field(
        default_factory=ClaimConstructionRecord
    )
    future_risk: list[FutureRiskFinding] = Field(default_factory=list)
    commercial_exposure: CommercialExposure = Field(default_factory=CommercialExposure)
    claim_program_decisions: list[ClaimProgramDecision] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    evidence_adapter_results: list[EvidenceAdapterResult] = Field(default_factory=list)
    collector_runs: list[EvidenceCollectorRun] = Field(default_factory=list)
    evidence_collection_plan: list[EvidenceCollectionDirective] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
    matter_graph: MatterGraph = Field(default_factory=MatterGraph)
    matter_graph_summary: MatterGraphSummary = Field(default_factory=MatterGraphSummary)
    matter_store: MatterStore = Field(default_factory=MatterStore)
    authority_coverage: AuthorityCoverage = Field(default_factory=AuthorityCoverage)
    record_completeness: RecordCompleteness = Field(default_factory=RecordCompleteness)
    run_observability: RunObservability = Field(default_factory=RunObservability)
    matter_evidence_index: MatterEvidenceIndex = Field(default_factory=MatterEvidenceIndex)
    claim_source_span_map: ClaimSourceSpanMap = Field(
        default_factory=ClaimSourceSpanMap,
        description=(
            "Deterministic support ledger mapping customer-visible claim assertions "
            "to source span IDs and unsupported/review-needed counts."
        ),
    )

    critic_report: CriticReport | None = None
    review_issues: list[CriticFinding] = Field(default_factory=list)

    total_patents_found: int = 0
    patents_after_triage: int = 0
    search_sources_used: list[str] = Field(default_factory=list)
    source_health: SourceHealth = Field(default_factory=SourceHealth)

    scholarly_prior_art_count: int = 0

    analysis_failures: list[AnalysisFailure] = Field(
        default_factory=list,
        description="Patents that failed during analysis — never silently dropped",
    )
    data_limitations: list[DataLimitation] = Field(
        default_factory=list,
        description="Known gaps in data coverage that affect reliability",
    )

    audit_trail: PipelineAuditTrail = Field(default_factory=PipelineAuditTrail)
    patent_narratives: dict[str, str] = Field(
        default_factory=dict,
        description="Per-patent natural language summaries keyed by patent_id",
    )
    disclaimer: str = Field(default=REPORT_DISCLAIMER)
    llm_models_used: dict[str, str] = Field(
        default_factory=dict,
        description="LLM model identifiers used for each pipeline role",
    )

    drawing_analyses: list[PatentDrawingAnalysis] = Field(
        default_factory=list,
        description="Per-patent drawing OCSR analysis from step 2.75",
    )
    drawing_summary: dict = Field(
        default_factory=dict,
        description="Aggregate drawing analysis statistics",
    )

    search_loop_result: SearchLoopResult | None = None

    regulatory_exclusivity: RegulatoryExclusivity | None = None

    execution_profile: Literal["world_class_adaptive"] = Field(
        default="world_class_adaptive",
        description="Runtime profile that produced the report",
    )
    report_pipeline: Literal["world_class_adaptive"] = Field(
        default="world_class_adaptive",
        description="Report assembly profile used by the unified pipeline",
    )
    reasoning_traces: list[dict] = Field(
        default_factory=list,
        description="Serialized ReasoningTrace objects from agentic escalation",
    )

    patent_details: dict[str, dict] = Field(
        default_factory=dict,
        description="Raw PatentHit data keyed by patent_id for frontend display",
    )

    action_items: list[ActionItem] = Field(
        default_factory=list,
        description="Recommended next steps derived from analysis results",
    )

    bibliography: list[dict] = Field(
        default_factory=list,
        description="Reference appendix entries from the unified report pipeline",
    )
    verification_summary: dict = Field(
        default_factory=dict,
        description="LLM verification results from the unified report pipeline",
    )
    factual_accuracy_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of verified claims that are correct in the unified report pipeline",
    )

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    step_token_usage: list[StepTokenUsage] = Field(default_factory=list)

    manifest: ReportManifest | None = Field(
        default=None,
        description="Provenance manifest pinning prompt hashes, models, and run metadata.",
    )

    @model_validator(mode="after")
    def _check_analysis_count_invariant(self) -> FTOReport:
        """Warn if patent analyses + failures doesn't match triaged count."""
        if self.patents_after_triage > 0:
            accounted = len(self.patent_analyses) + len(self.analysis_failures)
            if accounted != self.patents_after_triage:
                import structlog

                structlog.get_logger().warning(
                    "report_patent_count_mismatch",
                    patents_after_triage=self.patents_after_triage,
                    patent_analyses=len(self.patent_analyses),
                    analysis_failures=len(self.analysis_failures),
                    accounted=accounted,
                )
        return self

    @model_validator(mode="after")
    def _check_key_risks_populated(self) -> FTOReport:
        """Warn if high/medium risk but no key_risks listed."""
        if (
            hasattr(self, "risk_summary")
            and self.risk_summary
            and (
                self.risk_summary.overall_risk in (RiskLevel.HIGH, RiskLevel.MEDIUM)
                and not self.risk_summary.key_risks
            )
        ):
            import structlog

            structlog.get_logger().warning(
                "report_missing_key_risks",
                overall_risk=self.risk_summary.overall_risk.value,
            )
        return self


# Resolve the forward reference to ReportManifest now that the symbol exists
# in this module's namespace. Without this rebuild, the `from __future__ import
# annotations` deferral leaves `manifest: ReportManifest | None` as an
# unresolved string, which causes a PydanticUserError at construction time.
FTOReport.model_rebuild(_types_namespace={"ReportManifest": ReportManifest})
