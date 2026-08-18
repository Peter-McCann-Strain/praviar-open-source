"""Prosecution, future-risk, and claim-program response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProsecutionFindingResponse(BaseModel):
    """Structured prosecution/file-wrapper signal for a material patent."""

    patent_id: str
    jurisdiction: str = ""
    application_number: str = ""
    prosecution_history_available: bool = False
    transaction_count: int = 0
    amendment_event_count: int = 0
    office_action_count: int = 0
    continuity_entry_count: int = 0
    narrowing_signal: bool = False
    terminal_disclaimer: bool = False
    terminal_disclaimer_linked_patent: str = ""
    ptab_challenged: bool = False
    ptab_proceeding_count: int = 0
    pending_family_signal: bool = False
    pending_family_member_count: int = 0
    ep_register_status: str = ""
    ep_opposition_event_count: int = 0
    ep_limitation_event_count: int = 0
    ep_revocation_event_count: int = 0
    ep_lapse_event_count: int = 0
    office_action_types: list[str] = Field(default_factory=list)
    amendment_types: list[str] = Field(default_factory=list)
    continuity_types: list[str] = Field(default_factory=list)
    rejected_claim_numbers: list[int] = Field(default_factory=list)
    narrowing_claim_numbers: list[int] = Field(default_factory=list)
    rejection_bases: list[str] = Field(default_factory=list)
    estoppel_risk_flags: list[str] = Field(default_factory=list)
    continuation_parent_count: int = 0
    continuation_child_count: int = 0
    divisional_parent_count: int = 0
    divisional_child_count: int = 0
    cip_parent_count: int = 0
    cip_child_count: int = 0
    response_after_final_count: int = 0
    rce_count: int = 0
    interview_event_count: int = 0
    appeal_event_count: int = 0
    record_basis: list[str] = Field(default_factory=list)
    summary: str = ""


class ProsecutionOfficeActionEventResponse(BaseModel):
    """Normalized office-action event extracted from prosecution context."""

    document_code: str = ""
    description: str = ""
    event_date: str = ""
    office_action_type: str = ""
    claims_rejected: list[int] = Field(default_factory=list)
    rejection_bases: list[str] = Field(default_factory=list)


class ProsecutionContinuityEntryResponse(BaseModel):
    """Normalized continuity-chain entry extracted from prosecution context."""

    relationship: str = ""
    application_number: str = ""
    related_application_number: str = ""
    continuity_type: str = ""
    filing_date: str = ""


class ProsecutionAmendmentEventResponse(BaseModel):
    """Normalized amendment/response event extracted from prosecution context."""

    transaction_code: str = ""
    description: str = ""
    event_date: str = ""
    event_type: str = ""
    claim_numbers: list[int] = Field(default_factory=list)


class ProsecutionDossierResponse(BaseModel):
    """Structured prosecution dossier from Step 4 enrichment."""

    patent_id: str
    jurisdiction: str = ""
    application_number: str = ""
    source_name: str = "uspto_odp"
    sections_available: list[str] = Field(default_factory=list)
    office_actions_summary: str = ""
    continuity_summary: str = ""
    amendments_summary: str = ""
    office_action_events: list[ProsecutionOfficeActionEventResponse] = Field(default_factory=list)
    continuity_entries: list[ProsecutionContinuityEntryResponse] = Field(default_factory=list)
    amendment_events: list[ProsecutionAmendmentEventResponse] = Field(default_factory=list)
    office_action_count: int = 0
    continuity_entry_count: int = 0
    amendment_entry_count: int = 0
    office_action_types: list[str] = Field(default_factory=list)
    amendment_types: list[str] = Field(default_factory=list)
    continuity_types: list[str] = Field(default_factory=list)
    rejected_claim_numbers: list[int] = Field(default_factory=list)
    narrowing_claim_numbers: list[int] = Field(default_factory=list)
    rejection_bases: list[str] = Field(default_factory=list)
    estoppel_risk_flags: list[str] = Field(default_factory=list)
    continuation_parent_count: int = 0
    continuation_child_count: int = 0
    divisional_parent_count: int = 0
    divisional_child_count: int = 0
    cip_parent_count: int = 0
    cip_child_count: int = 0
    response_after_final_count: int = 0
    rce_count: int = 0
    interview_event_count: int = 0
    appeal_event_count: int = 0
    narrowing_signal: bool = False
    terminal_disclaimer: bool = False
    terminal_disclaimer_linked_patent: str = ""
    ptab_challenged: bool = False
    pending_family_signal: bool = False
    record_basis: list[str] = Field(default_factory=list)
    summary: str = ""


class ClaimConstructionRecordResponse(BaseModel):
    """Matter-level claim-construction record."""

    standard: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    disputed_terms: list[str] = Field(default_factory=list)
    summary: str = ""


class FutureRiskFindingResponse(BaseModel):
    """Forward-looking risk not captured by current issued-claim exposure alone."""

    patent_id: str
    jurisdiction: str = ""
    risk_type: str = ""
    severity: str = ""
    monitoring_required: bool = False
    related_patent_ids: list[str] = Field(default_factory=list)
    record_basis: list[str] = Field(default_factory=list)
    summary: str = ""


class CommercialExposureResponse(BaseModel):
    """Commercial launch-at-risk framing."""

    damages_injunction_risk: str = ""
    business_severity: str = ""
    blocking_patent_ids: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    summary: str = ""


class ClaimProgramDecisionResponse(BaseModel):
    """Claim-scoped decision object used to synthesize the top-line outcome."""

    patent_id: str
    claim_number: int
    jurisdiction: str = ""
    literal_outcome: str = ""
    literal_risk: str = ""
    doe_risk: str = ""
    invalidity_strength: str = ""
    prosecution_risk_flags: list[str] = Field(default_factory=list)
    prosecution_risk_level: str = ""
    post_grant_risk_level: str = ""
    scope_constrained: bool = False
    future_risk_flags: list[str] = Field(default_factory=list)
    commercial_severity: str = ""
    evidence_sufficient: bool = False
    missing_components: list[str] = Field(default_factory=list)
    record_basis: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
