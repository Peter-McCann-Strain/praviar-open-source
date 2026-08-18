"""Core decisioning models for FTO report outputs."""

from __future__ import annotations

import enum
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def blocker_family_record_id(family_id: str) -> str:
    """Return the stable identifier for one exact patent-family identity."""
    normalized_family_id = str(family_id or "").strip()
    if not normalized_family_id:
        raise ValueError("blocker family identity must be nonempty")
    digest = hashlib.sha256(normalized_family_id.encode("utf-8")).hexdigest()[:16]
    return f"bf_{digest}"


class ClearanceOutcome(enum.StrEnum):
    """Top-line clearance decision for the matter."""

    CLEAR = "clear"
    UNCLEAR = "unclear"
    BLOCKED = "blocked"


class CohortStatus(enum.StrEnum):
    """Certification status of the current matter cohort."""

    CERTIFIED = "certified"
    ATTORNEY_SUPERVISED = "attorney_supervised"
    SUPPORTING_ONLY = "supporting_only"


class DecisionEvidenceCategory(enum.StrEnum):
    """Structured categories for decisive evidence references."""

    BLOCKING_PATENT = "blocking_patent"
    CLEARANCE_SUPPORT = "clearance_support"
    SOURCE_FAILURE = "source_failure"
    COVERAGE_GAP = "coverage_gap"
    VERIFICATION_GAP = "verification_gap"
    FUTURE_RISK = "future_risk"
    PROSECUTION_SIGNAL = "prosecution_signal"


class DecisionEvidenceReference(BaseModel):
    """Machine-readable reference supporting the top-line decision."""

    model_config = ConfigDict(extra="forbid")

    category: DecisionEvidenceCategory
    summary: str
    patent_id: str = ""
    jurisdiction: str = ""
    source_name: str = ""
    signal: str = ""


class EvidenceCoverageSummary(BaseModel):
    """Material evidence coverage and gap summary for the final matter."""

    model_config = ConfigDict(extra="forbid")

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


class ClaimProgramSummary(BaseModel):
    """Claim-program level summary used by the top-line decision engine."""

    model_config = ConfigDict(extra="forbid")

    total_claim_programs_reviewed: int = 0
    patent_level_fallback_count: int = 0
    blocking_claim_ids: list[str] = Field(default_factory=list)
    contested_claim_ids: list[str] = Field(default_factory=list)
    medium_risk_claim_ids: list[str] = Field(default_factory=list)
    claims_with_strong_invalidity: list[str] = Field(default_factory=list)
    claims_with_insufficient_evidence: list[str] = Field(default_factory=list)
    inactive_coverage_claim_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Claims with positive coverage screens but trusted inactive status and "
            "no unresolved past-act or live-family exposure"
        ),
    )
    blocking_patent_ids: list[str] = Field(default_factory=list)
    contested_patent_ids: list[str] = Field(default_factory=list)
    medium_risk_patent_ids: list[str] = Field(default_factory=list)


class BlockerClaimRecord(BaseModel):
    """Exact decision-bearing claim that passed every blocker gate."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]+#claim[1-9][0-9]*$")
    patent_id: str
    claim_number: int = Field(ge=1)
    jurisdiction: str = Field(min_length=1)
    literal_risk: str = Field(min_length=1)
    doe_risk: str = ""
    invalidity_strength: str = ""
    legal_status: Literal["active"]
    legal_status_provenance_verified: Literal[True]
    prospective_enforceability: Literal["active"]
    accused_acts: list[str] = Field(min_length=1)
    accused_acts_verified: Literal[True]
    evidence_sufficient: Literal[True]
    record_basis: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_claim_identity(self) -> BlockerClaimRecord:
        if self.claim_id != f"{self.patent_id}#claim{self.claim_number}":
            raise ValueError("blocker claim identity fields must agree")
        if "high" not in {
            self.literal_risk.strip().lower(),
            self.doe_risk.strip().lower(),
        }:
            raise ValueError("blocker claims require a high literal or equivalents risk")
        if self.invalidity_strength.strip().lower() == "strong":
            raise ValueError("strong-invalidity claims cannot be blockers")
        for values, label in (
            (self.accused_acts, "blocker accused acts"),
            (self.record_basis, "blocker record basis"),
        ):
            if any(not value.strip() or value != value.strip() for value in values):
                raise ValueError(f"{label} must contain only nonblank normalized values")
            if values != sorted(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        return self


class BlockerFamilyRecord(BaseModel):
    """Canonical family projection of governed blocking claim decisions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["blocker-family-v1"] = "blocker-family-v1"
    blocker_id: str = Field(pattern=r"^bf_[0-9a-f]{16}$")
    family_id: str = Field(min_length=1)
    primary_blocking_patent_id: str
    material_family_patent_ids: list[str] = Field(min_length=1)
    blocking_patent_ids: list[str] = Field(min_length=1)
    jurisdictions: list[str] = Field(min_length=1)
    blocking_claims: list[BlockerClaimRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_family_membership(self) -> BlockerFamilyRecord:
        if self.blocker_id != blocker_family_record_id(self.family_id):
            raise ValueError("blocker ID must match the canonical family identity")
        claim_patent_ids = {claim.patent_id for claim in self.blocking_claims}
        blocking_patent_ids = set(self.blocking_patent_ids)
        if self.primary_blocking_patent_id not in blocking_patent_ids:
            raise ValueError("primary blocker must be a blocking patent")
        if self.primary_blocking_patent_id != self.blocking_patent_ids[0]:
            raise ValueError("primary blocker must be the first canonical blocking patent")
        if not blocking_patent_ids.issubset(set(self.material_family_patent_ids)):
            raise ValueError("blocking patents must belong to the material family")
        if claim_patent_ids != blocking_patent_ids:
            raise ValueError("every blocking patent requires an exact blocking claim")
        claim_jurisdictions = sorted({claim.jurisdiction for claim in self.blocking_claims})
        if self.jurisdictions != claim_jurisdictions:
            raise ValueError("blocker family jurisdictions must exactly match its blocking claims")
        for values, label in (
            (self.material_family_patent_ids, "material family patents"),
            (self.blocking_patent_ids, "blocking patents"),
            (self.jurisdictions, "jurisdictions"),
        ):
            if any(not value.strip() or value != value.strip() for value in values):
                raise ValueError(f"{label} must contain only nonblank normalized values")
            if values != sorted(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        claim_identities = [(claim.patent_id, claim.claim_number) for claim in self.blocking_claims]
        if claim_identities != sorted(set(claim_identities)):
            raise ValueError("blocking claims must be sorted and unique")
        return self


class ClearanceDecisionAudit(BaseModel):
    """Structured evidence metrics used to support the top-line decision."""

    model_config = ConfigDict(extra="forbid")

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
    coverage_summary: EvidenceCoverageSummary = Field(default_factory=EvidenceCoverageSummary)
    claim_program_summary: ClaimProgramSummary = Field(default_factory=ClaimProgramSummary)
    blocker_families: list[BlockerFamilyRecord] = Field(default_factory=list)
    decisive_references: list[DecisionEvidenceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_blocker_projection(self) -> ClearanceDecisionAudit:
        summary_claim_ids = set(self.claim_program_summary.blocking_claim_ids)
        summary_patent_ids = set(self.claim_program_summary.blocking_patent_ids)
        if bool(summary_claim_ids) != bool(summary_patent_ids):
            raise ValueError("blocking claim and patent summaries must both be present")
        if not self.blocker_families:
            if summary_claim_ids:
                raise ValueError("blocking claim summaries require canonical blocker families")
            return self
        family_claim_ids = [
            claim.claim_id for family in self.blocker_families for claim in family.blocking_claims
        ]
        family_patent_ids = [
            patent_id
            for family in self.blocker_families
            for patent_id in family.blocking_patent_ids
        ]
        if sorted(family_claim_ids) != sorted(summary_claim_ids):
            raise ValueError("blocker families must exactly cover blocking claim IDs")
        if sorted(family_patent_ids) != sorted(summary_patent_ids):
            raise ValueError("blocker families must exactly cover blocking patent IDs")
        if len(family_patent_ids) != len(set(family_patent_ids)):
            raise ValueError("each blocking patent must belong to exactly one blocker family")
        blocker_ids = [family.blocker_id for family in self.blocker_families]
        if blocker_ids != sorted(set(blocker_ids)):
            raise ValueError("blocker families must be sorted and unique")
        return self


class ClearanceDecision(BaseModel):
    """Explicit top-line clearance decision for the report."""

    model_config = ConfigDict(extra="forbid")

    decision: ClearanceOutcome = ClearanceOutcome.UNCLEAR
    decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    decision_reasoning: list[str] = Field(default_factory=list)
    decision_audit: ClearanceDecisionAudit = Field(default_factory=ClearanceDecisionAudit)


class DecisionScope(BaseModel):
    """Current report scope that may or may not support a positive clearance conclusion."""

    model_config = ConfigDict(extra="forbid")

    matter_type: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    intended_actions: list[str] = Field(default_factory=list)
    supports_positive_clearance: bool = False
    summary: str = ""


class CertificationScope(BaseModel):
    """Program-level certification boundaries relevant to the current matter."""

    model_config = ConfigDict(extra="forbid")

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


class OpinionReadiness(BaseModel):
    """Signed report-level authorization inputs for counsel export workflows."""

    model_config = ConfigDict(extra="forbid")

    trust_mode: Literal["explorer", "counsel", "monitor"] = "explorer"
    attorney_supervision_required: bool = True
    export_ready: bool = False
    jurisdictions_blocking_export: list[str] = Field(default_factory=list)
    gate_failures: list[str] = Field(default_factory=list)
    summary: str = ""


class JurisdictionDecision(BaseModel):
    """Decision breakdown for a specific jurisdiction."""

    model_config = ConfigDict(extra="forbid")

    jurisdiction: str
    decision: ClearanceOutcome = ClearanceOutcome.UNCLEAR
    decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_sufficient_for_clearance: bool = False
    supports_positive_clearance: bool = False
    lane_status: str = ""
    local_review_required: bool = False
    authority_grade: str = ""
    gate_failures: list[str] = Field(default_factory=list)
    reviewed_patent_ids: list[str] = Field(default_factory=list)
    blocking_patent_ids: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
