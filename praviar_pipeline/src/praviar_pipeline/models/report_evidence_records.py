"""Record, coverage, and index models for the evidence fabric."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from praviar_pipeline.models._base import PatentBase
from praviar_pipeline.utils.patent_ids import canonical_publication_id


class ClaimProgramDecision(PatentBase):
    """Claim-scoped decision object used to synthesize the top-line outcome.

    Internal pipeline-state model. Uses ``extra="forbid"`` (inherited
    from :class:`PatentBase`). ``patent_id`` and ``jurisdiction`` are
    inherited.
    """

    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(ge=0)
    literal_outcome: str = ""
    literal_risk: str = ""
    doe_risk: str = ""
    invalidity_strength: str = ""
    prosecution_risk_flags: list[str] = Field(default_factory=list)
    prosecution_risk_level: str = ""
    post_grant_risk_level: str = ""
    scope_constrained: bool = False
    future_risk_flags: list[str] = Field(default_factory=list)
    legal_status: str = ""
    legal_status_provenance_verified: bool = False
    prospective_enforceability: str = Field(
        default="unresolved",
        description=(
            "active, inactive, pending, conflicting, or unresolved based only on "
            "trusted current legal-status evidence"
        ),
    )
    accused_acts: list[str] = Field(default_factory=list)
    accused_acts_verified: bool = False
    past_acts_in_scope: bool = False
    commercial_severity: str = ""
    evidence_sufficient: bool = False
    missing_components: list[str] = Field(default_factory=list)
    record_basis: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)

    @field_validator("patent_id")
    @classmethod
    def _canonicalize_patent_id(cls, value: str) -> str:
        return canonical_publication_id(value)


class AuthorityCoverage(BaseModel):
    """Authority and provenance coverage for the final matter record."""

    model_config = ConfigDict(extra="forbid")

    policy: str = ""
    authoritative_source_names: list[str] = Field(default_factory=list)
    supporting_source_names: list[str] = Field(default_factory=list)
    authoritative_categories_covered: list[str] = Field(default_factory=list)
    authoritative_categories_missing: list[str] = Field(default_factory=list)
    patents_with_authoritative_records: int = 0
    patents_without_authoritative_records: int = 0
    clearance_grade_ready_patents: int = 0


class RecordCompleteness(BaseModel):
    """Record-completeness policy evaluation for the final matter."""

    model_config = ConfigDict(extra="forbid")

    profile: str = ""
    matter_type: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    required_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    clearance_grade_ready: bool = False


class RunObservability(BaseModel):
    """Run-level observability metrics and false-clear risk signals."""

    model_config = ConfigDict(extra="forbid")

    authoritative_source_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    claims_text_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    family_context_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    us_file_wrapper_dossier_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    ep_register_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    failed_adapter_names: list[str] = Field(default_factory=list)
    false_clear_risk_flags: list[str] = Field(default_factory=list)
    unresolved_contradictions: list[str] = Field(default_factory=list)


class RecordComponentStatusValue(enum.StrEnum):
    """Collection status for one required evidence component."""

    COLLECTED = "collected"
    MISSING = "missing"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class RecordComponentStatus(BaseModel):
    """Per-component collection ledger entry for a patent or family record."""

    model_config = ConfigDict(extra="forbid")

    component: str
    status: RecordComponentStatusValue = RecordComponentStatusValue.MISSING
    source_name: str = ""
    authority_expected: bool = False
    required_before_clear: bool = False
    note: str = ""


class PatentEvidenceRecord(PatentBase):
    """Canonical evidence inventory for one material patent in the matter.

    External-boundary model: assembled from authoritative source records
    consumed by report generation. Uses ``extra="forbid"`` (inherited
    from :class:`PatentBase`) — schema drift here would silently weaken
    the audit trail. ``patent_id`` and ``jurisdiction`` are inherited.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = ""
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
    has_assignments: bool = False
    has_priority_claims: bool = False
    has_ptab_proceedings: bool = False
    has_orange_book_listing: bool = False
    has_opposition_events: bool = False
    authoritative_record_categories: list[str] = Field(default_factory=list)
    component_statuses: list[RecordComponentStatus] = Field(default_factory=list)
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


class FamilyEvidenceRecord(BaseModel):
    """Canonical family-level evidence summary for material patents."""

    model_config = ConfigDict(extra="forbid")

    family_id: str
    material_patent_ids: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    broadest_patent_id: str = ""
    member_count: int = 0
    pending_member_count: int = 0
    blocking_patent_ids: list[str] = Field(default_factory=list)
    orange_book_listed_patent_ids: list[str] = Field(default_factory=list)
    authoritative_record_categories: list[str] = Field(default_factory=list)
    component_statuses: list[RecordComponentStatus] = Field(default_factory=list)
    clearance_grade_ready: bool = False
    gate_failures: list[str] = Field(default_factory=list)
    clearance_grade_ready_patent_ids: list[str] = Field(default_factory=list)
    incomplete_patent_ids: list[str] = Field(default_factory=list)


class MatterEvidenceIndex(BaseModel):
    """Canonical per-matter evidence inventory derived from the final record."""

    model_config = ConfigDict(extra="forbid")

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
    patent_records: list[PatentEvidenceRecord] = Field(default_factory=list)
    family_records: list[FamilyEvidenceRecord] = Field(default_factory=list)
