"""Decision and evidence-coverage response models."""

from __future__ import annotations

from praviar_pipeline.models.report import BlockerFamilyRecord
from pydantic import BaseModel, Field

from api.schemas.reports_types import ClearanceOutcome, DecisionEvidenceCategory


class DecisionEvidenceReferenceResponse(BaseModel):
    """Machine-readable reference supporting the top-line decision."""

    category: DecisionEvidenceCategory
    summary: str
    patent_id: str = ""
    jurisdiction: str = ""
    source_name: str = ""
    signal: str = ""


class EvidenceCoverageSummaryResponse(BaseModel):
    """Coverage and gap summary for material evidence in the matter."""

    queried_source_names: list[str] = Field(default_factory=list)
    successful_source_names: list[str] = Field(default_factory=list)
    failed_source_names: list[str] = Field(default_factory=list)
    authoritative_source_names: list[str] = Field(default_factory=list)
    supporting_source_names: list[str] = Field(default_factory=list)
    reviewed_patent_ids: list[str] = Field(default_factory=list)
    reviewed_us_patent_ids: list[str] = Field(default_factory=list)
    reviewed_ep_patent_ids: list[str] = Field(default_factory=list)
    patents_missing_claims: list[str] = Field(default_factory=list)
    patents_missing_claim_level_analysis: list[str] = Field(default_factory=list)
    patents_missing_authoritative_records: list[str] = Field(default_factory=list)
    patents_missing_family_context: list[str] = Field(default_factory=list)
    us_patents_missing_prosecution_context: list[str] = Field(default_factory=list)
    us_patents_missing_file_wrapper_dossier: list[str] = Field(default_factory=list)
    ep_patents_missing_register_context: list[str] = Field(default_factory=list)
    failed_analysis_patent_ids: list[str] = Field(default_factory=list)
    clearance_grade_ready_patent_ids: list[str] = Field(default_factory=list)
    incomplete_patent_ids: list[str] = Field(default_factory=list)
    clearance_grade_ready_family_ids: list[str] = Field(default_factory=list)
    incomplete_family_ids: list[str] = Field(default_factory=list)
    verification_gaps: list[str] = Field(default_factory=list)
    required_record_components: list[str] = Field(default_factory=list)


class ClaimProgramSummaryResponse(BaseModel):
    """Claim-program summary used by the deterministic decision layer."""

    total_claim_programs_reviewed: int = 0
    patent_level_fallback_count: int = 0
    blocking_claim_ids: list[str] = Field(default_factory=list)
    contested_claim_ids: list[str] = Field(default_factory=list)
    medium_risk_claim_ids: list[str] = Field(default_factory=list)
    claims_with_strong_invalidity: list[str] = Field(default_factory=list)
    claims_with_insufficient_evidence: list[str] = Field(default_factory=list)
    blocking_patent_ids: list[str] = Field(default_factory=list)
    contested_patent_ids: list[str] = Field(default_factory=list)
    medium_risk_patent_ids: list[str] = Field(default_factory=list)


class ClearanceDecisionAuditResponse(BaseModel):
    """Structured evidence metrics supporting the top-line decision."""

    queried_sources_count: int = 0
    successful_sources_count: int = 0
    material_patents_reviewed: int = 0
    material_us_patents: int = 0
    material_ep_patents: int = 0
    patents_with_claims: int = 0
    patents_with_family: int = 0
    us_patents_with_prosecution_context: int = 0
    us_patents_with_file_wrapper_dossier: int = 0
    ep_patents_with_register_context: int = 0
    analysis_failures_count: int = 0
    authoritative_sources_count: int = 0
    clearance_grade_ready_patents: int = 0
    incomplete_material_patents: int = 0
    clearance_grade_ready_families: int = 0
    incomplete_material_families: int = 0
    failed_sources: list[str] = Field(default_factory=list)
    evidence_sufficient_for_clearance: bool = False
    insufficiency_reasons: list[str] = Field(default_factory=list)
    evidence_warnings: list[str] = Field(default_factory=list)
    search_iterations: int = 0
    coverage_summary: EvidenceCoverageSummaryResponse = Field(
        default_factory=EvidenceCoverageSummaryResponse
    )
    claim_program_summary: ClaimProgramSummaryResponse = Field(
        default_factory=ClaimProgramSummaryResponse
    )
    blocker_families: list[BlockerFamilyRecord] = Field(default_factory=list)
    decisive_references: list[DecisionEvidenceReferenceResponse] = Field(default_factory=list)


class ClearanceDecisionResponse(BaseModel):
    """Top-line matter decision."""

    decision: ClearanceOutcome
    decision_confidence: float = 0.0
    evidence_quality: float = 0.0
    decision_reasoning: list[str] = Field(default_factory=list)
    decision_audit: ClearanceDecisionAuditResponse = Field(
        default_factory=ClearanceDecisionAuditResponse
    )


class DecisionScopeResponse(BaseModel):
    """Matter scope that may or may not support a positive clearance conclusion."""

    matter_type: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    supports_positive_clearance: bool = False
    summary: str = ""


class CertificationScopeResponse(BaseModel):
    """Program certification boundaries relevant to the current matter."""

    certified_jurisdictions: list[str] = Field(default_factory=list)
    supported_jurisdictions: list[str] = Field(default_factory=list)
    certified_matter_types: list[str] = Field(default_factory=list)
    certified_asset_classes: list[str] = Field(default_factory=list)
    attorney_supervised_matter_types: list[str] = Field(default_factory=list)
    attorney_supervised_asset_classes: list[str] = Field(default_factory=list)
    supporting_only_jurisdictions: list[str] = Field(default_factory=list)
    current_matter_type_certified: bool = False
    attorney_supervision_required: bool = True
    evidence_verified: bool = False
    evidence_verification_status: str = "unverified"
    evidence_receipt_dsse: str = ""
    evidence_receipt_id: str = ""
    evidence_receipt_sha256: str = ""
    evidence_pipeline_git_sha: str = ""
    evidence_source_tree_sha256: str = ""
    evidence_expires_at: str = ""
    evidence_issuer_verifier_id: str = ""
    evidence_key_id: str = ""
    evidence_gate_run_id: str = ""
    evidence_benchmark_aggregate_sha256: str = ""
    verified_lane_ids: list[str] = Field(default_factory=list)
    evidence_failures: list[str] = Field(default_factory=list)
    summary: str = ""


class JurisdictionDecisionResponse(BaseModel):
    """Decision breakdown for a specific jurisdiction."""

    jurisdiction: str
    decision: ClearanceOutcome
    decision_confidence: float = 0.0
    evidence_quality: float = 0.0
    evidence_sufficient_for_clearance: bool = False
    supports_positive_clearance: bool = False
    lane_status: str = "screening_only"
    local_review_required: bool = True
    authority_grade: str = ""
    gate_failures: list[str] = Field(default_factory=list)
    reviewed_patent_ids: list[str] = Field(default_factory=list)
    blocking_patent_ids: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
