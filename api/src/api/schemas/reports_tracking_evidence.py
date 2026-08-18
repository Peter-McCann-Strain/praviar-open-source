"""Evidence-fabric and critic report models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.schemas.reports_tracking_audit_prosecution import (
    ClaimProgramDecisionResponse,
    ProsecutionDossierResponse,
)
from api.schemas.reports_types import (
    CriticIssueSeverity,
    CriticIssueType,
    EvidenceAdapterKind,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    EvidenceCollectionState,
    EvidenceDirectivePriority,
    RecordComponentStatusValue,
    SourceStatus,
)


class EvidenceArtifactResponse(BaseModel):
    """Typed evidence artifact emitted by the runtime evidence fabric."""

    artifact_id: str
    artifact_type: EvidenceArtifactType
    source_name: str = ""
    authority_tier: EvidenceAuthorityTier = "supporting"
    jurisdiction: str = ""
    patent_id: str = ""
    family_id: str = ""
    claim_number: int | None = None
    summary: str = ""
    record_basis: list[str] = Field(default_factory=list)
    linked_node_ids: list[str] = Field(default_factory=list)


class EvidenceAdapterResultResponse(BaseModel):
    """Standardized adapter result emitted by the evidence fabric."""

    adapter_name: str
    adapter_kind: EvidenceAdapterKind = "derived"
    authority_tier: EvidenceAuthorityTier = "supporting"
    status: SourceStatus = "ok"
    collection_state: EvidenceCollectionState = "collected"
    required_before_clear: bool = False
    target_patent_ids: list[str] = Field(default_factory=list)
    covered_patent_ids: list[str] = Field(default_factory=list)
    missing_patent_ids: list[str] = Field(default_factory=list)
    artifacts: list[EvidenceArtifactResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None
    retry_after_seconds: float | None = None
    freshness_note: str = ""
    artifact_count: int = 0
    covered_components: list[str] = Field(default_factory=list)
    expected_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    supports_authoritative_findings: bool = False


class EvidenceCollectionDirectiveResponse(BaseModel):
    """Actionable evidence-collection directive emitted by the runtime."""

    directive_id: str
    directive_type: str
    priority: EvidenceDirectivePriority = "medium"
    required_before_clear: bool = True
    target_patent_ids: list[str] = Field(default_factory=list)
    target_claim_ids: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    recommended_adapters: list[str] = Field(default_factory=list)
    summary: str = ""
    rationale: str = ""


class EvidenceCollectorDefinitionResponse(BaseModel):
    """Static collector metadata used by the runtime collection ledger."""

    collector_name: str
    adapter_kind: EvidenceAdapterKind = "derived"
    authority_tier: EvidenceAuthorityTier = "supporting"
    supports_authoritative_findings: bool = False
    expected_components: list[str] = Field(default_factory=list)


class CollectionTargetResponse(BaseModel):
    """Patent-scoped collection target tracked by a runtime collector."""

    patent_id: str
    jurisdiction: str = ""
    required_components: list[str] = Field(default_factory=list)
    covered_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    required_before_clear: bool = False


class CollectionAttemptResponse(BaseModel):
    """One deterministic collector attempt captured in the runtime ledger."""

    attempt_number: int = 1
    status: SourceStatus = "ok"
    collection_state: EvidenceCollectionState = "collected"
    artifact_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None
    retry_after_seconds: float | None = None
    summary: str = ""


class EvidenceCollectorRunResponse(BaseModel):
    """First-class runtime state for one collector over the current matter."""

    definition: EvidenceCollectorDefinitionResponse
    collection_state: EvidenceCollectionState = "collected"
    required_before_clear: bool = False
    target_patent_ids: list[str] = Field(default_factory=list)
    covered_patent_ids: list[str] = Field(default_factory=list)
    missing_patent_ids: list[str] = Field(default_factory=list)
    expected_components: list[str] = Field(default_factory=list)
    covered_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    retry_budget_remaining: int = 0
    freshness_note: str = ""
    triggered_directive_ids: list[str] = Field(default_factory=list)
    collection_targets: list[CollectionTargetResponse] = Field(default_factory=list)
    attempts: list[CollectionAttemptResponse] = Field(default_factory=list)


class MatterNodeResponse(BaseModel):
    """Node in the matter graph."""

    node_id: str
    node_type: str
    label: str
    jurisdiction: str = ""
    patent_id: str = ""
    family_id: str = ""
    application_number: str = ""


class MatterEdgeResponse(BaseModel):
    """Edge in the matter graph."""

    edge_type: str
    from_node_id: str
    to_node_id: str
    summary: str = ""


class MatterGraphResponse(BaseModel):
    """Canonical matter graph for the final matter."""

    nodes: list[MatterNodeResponse] = Field(default_factory=list)
    edges: list[MatterEdgeResponse] = Field(default_factory=list)


class MatterGraphSummaryResponse(BaseModel):
    """Compact summary of the matter graph."""

    root_compound: str = ""
    node_count: int = 0
    edge_count: int = 0
    node_counts_by_type: dict[str, int] = Field(default_factory=dict)
    edge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    patent_node_ids: list[str] = Field(default_factory=list)
    family_node_ids: list[str] = Field(default_factory=list)


class RecordContradictionResponse(BaseModel):
    """Typed unresolved contradiction carried inside the matter store."""

    contradiction_id: str
    category: str = ""
    summary: str = ""
    severity: str = "medium"
    affected_patent_ids: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)


class MatterStoreCoverageGapResponse(BaseModel):
    """Coverage-gap record persisted inside the matter store."""

    gap_type: str = ""
    description: str = ""
    suggested_action: str = ""


class AuthorityCoverageResponse(BaseModel):
    """Authority-tier coverage for the final matter record."""

    policy: str = ""
    authoritative_source_names: list[str] = Field(default_factory=list)
    supporting_source_names: list[str] = Field(default_factory=list)
    authoritative_categories_covered: list[str] = Field(default_factory=list)
    authoritative_categories_missing: list[str] = Field(default_factory=list)
    patents_with_authoritative_records: int = 0
    patents_without_authoritative_records: int = 0
    clearance_grade_ready_patents: int = 0


class RecordCompletenessResponse(BaseModel):
    """Record-completeness policy evaluation."""

    profile: str = ""
    matter_type: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    required_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    clearance_grade_ready: bool = False


class RunObservabilityResponse(BaseModel):
    """Run-level observability metrics and false-clear risk flags."""

    authoritative_source_hit_rate: float = 0.0
    claims_text_coverage: float = 0.0
    family_context_coverage: float = 0.0
    us_file_wrapper_dossier_coverage: float = 0.0
    ep_register_coverage: float = 0.0
    failed_adapter_names: list[str] = Field(default_factory=list)
    false_clear_risk_flags: list[str] = Field(default_factory=list)
    unresolved_contradictions: list[str] = Field(default_factory=list)


class RecordComponentStatusResponse(BaseModel):
    """Per-component collection ledger entry for a patent or family record."""

    component: str
    status: RecordComponentStatusValue = "missing"
    source_name: str = ""
    authority_expected: bool = False
    required_before_clear: bool = False
    note: str = ""


class PatentEvidenceRecordResponse(BaseModel):
    """Canonical evidence inventory for one material patent."""

    patent_id: str
    title: str = ""
    jurisdiction: str = ""
    legal_status: str = ""
    is_granted: bool = True
    source_names: list[str] = Field(default_factory=list)
    authoritative_source_names: list[str] = Field(default_factory=list)
    supporting_source_names: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    family_id: str = ""
    family_member_count: int = 0
    family_jurisdictions: list[str] = Field(default_factory=list)
    family_broadest: bool = False
    application_number: str = ""
    has_claims_text: bool = False
    has_family_context: bool = False
    has_us_prosecution_context: bool = False
    has_us_file_wrapper_dossier: bool = False
    prosecution_dossier_sections: list[str] = Field(default_factory=list)
    has_ep_register_context: bool = False
    ep_register_status: str = ""
    ep_validation_states: list[str] = Field(default_factory=list)
    ep_validation_state_incomplete: bool = False
    ep_unitary_effect_status: str = ""
    ep_upc_opt_out_status: str = ""
    has_uk_post_grant_context: bool = False
    uk_register_status: str = ""
    uk_post_grant_event_count: int = 0
    has_assignments: bool = False
    has_priority_claims: bool = False
    has_ptab_proceedings: bool = False
    has_orange_book_listing: bool = False
    has_opposition_events: bool = False
    authoritative_record_categories: list[str] = Field(default_factory=list)
    component_statuses: list[RecordComponentStatusResponse] = Field(default_factory=list)
    analysis_completed: bool = False
    analysis_failed: bool = False
    claims_analyzed_count: int = 0
    risk_level: str = ""
    doe_assessed: bool = False
    invalidity_assessed: bool = False
    clearance_grade_ready: bool = False
    gate_failures: list[str] = Field(default_factory=list)
    critic_issue_count: int = 0
    critic_issue_severities: list[str] = Field(default_factory=list)
    prosecution_signals: list[str] = Field(default_factory=list)
    future_risk_signals: list[str] = Field(default_factory=list)


class FamilyEvidenceRecordResponse(BaseModel):
    """Canonical family-level evidence summary."""

    family_id: str
    material_patent_ids: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    broadest_patent_id: str = ""
    member_count: int = 0
    pending_member_count: int = 0
    blocking_patent_ids: list[str] = Field(default_factory=list)
    orange_book_listed_patent_ids: list[str] = Field(default_factory=list)
    authoritative_record_categories: list[str] = Field(default_factory=list)
    component_statuses: list[RecordComponentStatusResponse] = Field(default_factory=list)
    clearance_grade_ready: bool = False
    gate_failures: list[str] = Field(default_factory=list)
    clearance_grade_ready_patent_ids: list[str] = Field(default_factory=list)
    incomplete_patent_ids: list[str] = Field(default_factory=list)


class MatterEvidenceIndexResponse(BaseModel):
    """Canonical per-matter evidence inventory."""

    source_names: list[str] = Field(default_factory=list)
    authoritative_source_names: list[str] = Field(default_factory=list)
    supporting_source_names: list[str] = Field(default_factory=list)
    material_patent_count: int = 0
    family_count: int = 0
    analysis_failure_patent_ids: list[str] = Field(default_factory=list)
    critic_flagged_patent_ids: list[str] = Field(default_factory=list)
    clearance_grade_ready_patent_ids: list[str] = Field(default_factory=list)
    incomplete_patent_ids: list[str] = Field(default_factory=list)
    clearance_grade_ready_family_ids: list[str] = Field(default_factory=list)
    incomplete_family_ids: list[str] = Field(default_factory=list)
    patent_records: list[PatentEvidenceRecordResponse] = Field(default_factory=list)
    family_records: list[FamilyEvidenceRecordResponse] = Field(default_factory=list)


class MatterStoreResponse(BaseModel):
    """Persistent runtime evidence substrate shared across stages."""

    matter_graph: MatterGraphResponse = Field(default_factory=MatterGraphResponse)
    matter_graph_summary: MatterGraphSummaryResponse = Field(
        default_factory=MatterGraphSummaryResponse
    )
    matter_evidence_index: MatterEvidenceIndexResponse = Field(
        default_factory=MatterEvidenceIndexResponse
    )
    prosecution_dossiers: list[ProsecutionDossierResponse] = Field(default_factory=list)
    claim_program_decisions: list[ClaimProgramDecisionResponse] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifactResponse] = Field(default_factory=list)
    evidence_adapter_results: list[EvidenceAdapterResultResponse] = Field(default_factory=list)
    collector_runs: list[EvidenceCollectorRunResponse] = Field(default_factory=list)
    evidence_collection_plan: list[EvidenceCollectionDirectiveResponse] = Field(
        default_factory=list
    )
    coverage_gaps: list[MatterStoreCoverageGapResponse] = Field(default_factory=list)
    authority_coverage: AuthorityCoverageResponse = Field(default_factory=AuthorityCoverageResponse)
    record_completeness: RecordCompletenessResponse = Field(
        default_factory=RecordCompletenessResponse
    )
    run_observability: RunObservabilityResponse = Field(default_factory=RunObservabilityResponse)
    record_contradictions: list[RecordContradictionResponse] = Field(default_factory=list)


class CriticFindingResponse(BaseModel):
    """A single critic finding surfaced by portfolio review."""

    issue_type: CriticIssueType
    patent_id: str
    severity: CriticIssueSeverity
    description: str
    suggested_correction: str = ""
    claim_numbers: list[int] = Field(default_factory=list)
    related_patent_ids: list[str] = Field(default_factory=list)


class CriticReportResponse(BaseModel):
    """Portfolio-level critic review payload."""

    findings: list[CriticFindingResponse] = Field(default_factory=list)
    patents_reviewed: int = 0
    patents_flagged_for_revision: list[str] = Field(default_factory=list)
    overall_quality_score: float = 0.0
    portfolio_level_observations: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
