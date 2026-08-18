"""Prosecution-focused report models used by the decision engine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProsecutionFinding(BaseModel):
    """Structured prosecution and file-wrapper signals for a material patent."""

    model_config = ConfigDict(extra="forbid")

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


class ProsecutionOfficeActionEvent(BaseModel):
    """Normalized office-action event extracted from a prosecution dossier."""

    model_config = ConfigDict(extra="forbid")

    document_code: str = ""
    description: str = ""
    event_date: str = ""
    office_action_type: str = ""
    claims_rejected: list[int] = Field(default_factory=list)
    rejection_bases: list[str] = Field(default_factory=list)


class ProsecutionContinuityEntry(BaseModel):
    """Normalized continuity-chain entry extracted from prosecution data."""

    model_config = ConfigDict(extra="forbid")

    relationship: str = ""
    relationship_type: str = ""  # alias used by the matter-store layer
    application_number: str = ""
    related_application_number: str = ""
    continuity_type: str = ""
    filing_date: str = ""
    status: str = ""
    jurisdiction: str = ""


class ProsecutionAmendmentEvent(BaseModel):
    """Normalized amendment/response event extracted from prosecution data."""

    model_config = ConfigDict(extra="forbid")

    transaction_code: str = ""
    description: str = ""
    event_date: str = ""
    event_type: str = ""
    claim_numbers: list[int] = Field(default_factory=list)


class ProsecutionDossier(BaseModel):
    """Structured prosecution dossier captured during Step 4 enrichment."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    jurisdiction: str = ""
    application_number: str = ""
    source_name: str = "uspto_odp"
    sections_available: list[str] = Field(default_factory=list)
    office_actions_summary: str = ""
    continuity_summary: str = ""
    amendments_summary: str = ""
    office_action_events: list[ProsecutionOfficeActionEvent] = Field(default_factory=list)
    continuity_entries: list[ProsecutionContinuityEntry] = Field(default_factory=list)
    amendment_events: list[ProsecutionAmendmentEvent] = Field(default_factory=list)
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
