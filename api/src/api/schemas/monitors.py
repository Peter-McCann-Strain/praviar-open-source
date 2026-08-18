"""Monitor and alert schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MonitorConclusionImpact(BaseModel):
    """A prior report conclusion made stale by a monitoring delta."""

    conclusion_id: str = Field(min_length=1, max_length=160)
    conclusion_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=500)
    previous_outcome: str = Field(max_length=100)
    status: Literal["review_required"] = "review_required"
    source_report_id: str = Field(default="", max_length=100)
    dependency_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    invalidated_at: AwareDatetime
    latest_observed_at: AwareDatetime
    reason_codes: list[str] = Field(default_factory=list)
    trigger_patent_ids: list[str] = Field(default_factory=list)
    trigger_event_ids: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    reassessment_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    evidence_digest: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")
    evidence_version: str = Field(default="", max_length=64)
    evidence_observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _validate_observation_order(self) -> MonitorConclusionImpact:
        if self.latest_observed_at < self.invalidated_at:
            raise ValueError("latest_observed_at must be on or after invalidated_at")
        return self


class ResolveMonitorConclusionRequest(BaseModel):
    """Counsel-only disposition of one invalidated report conclusion."""

    model_config = ConfigDict(extra="forbid")

    resolution: Literal["reaffirmed", "superseded", "withdrawn"]
    resolution_note: str = Field(min_length=20, max_length=5000)
    attestation_accepted: Literal[True]
    reassessment_id: uuid.UUID
    alert_id: uuid.UUID
    dependency_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_version: str = Field(min_length=1, max_length=64)
    evidence_observed_at: AwareDatetime
    replacement_analysis_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_replacement(self) -> ResolveMonitorConclusionRequest:
        if self.resolution == "superseded" and self.replacement_analysis_id is None:
            raise ValueError("replacement_analysis_id is required when a conclusion is superseded")
        if self.resolution != "superseded" and self.replacement_analysis_id is not None:
            raise ValueError(
                "replacement_analysis_id is only valid when a conclusion is superseded"
            )
        return self


class MonitorConclusionReassessmentResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID | None
    source_analysis_id: uuid.UUID
    source_report_id: str
    conclusion_id: str
    conclusion_type: str
    conclusion_label: str
    previous_outcome: str
    dependency_fingerprint: str
    status: Literal["open", "reaffirmed", "superseded", "withdrawn"]
    trigger_evidence: dict
    invalidated_at: datetime
    latest_observed_at: datetime
    resolved_at: datetime | None
    reviewer_role: str
    reviewer_name: str
    reviewer_email: str
    resolution_note: str
    attestation_version: str
    attestation_statement: str
    attestation_accepted: bool
    replacement_analysis_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitorConclusionReassessmentListResponse(BaseModel):
    items: list[MonitorConclusionReassessmentResponse]
    total: int


class CreateMonitorRequest(BaseModel):
    compound_smiles: str = Field(default="", max_length=5000)
    compound_name: str = Field(default="", max_length=500)
    analysis_id: uuid.UUID | None = None
    schedule: str = Field(default="weekly", pattern="^(daily|weekly|monthly)$")

    @model_validator(mode="after")
    def _require_compound_or_analysis(self) -> CreateMonitorRequest:
        if not self.compound_smiles.strip() and self.analysis_id is None:
            raise ValueError("compound_smiles is required when analysis_id is not provided")
        return self


class UpdateMonitorRequest(BaseModel):
    schedule: str | None = Field(None, pattern="^(daily|weekly|monthly)$")
    is_active: bool | None = None
    compound_name: str | None = Field(None, max_length=500)


class MonitorResponse(BaseModel):
    id: uuid.UUID
    compound_smiles: str
    compound_name: str
    source_analysis_id: uuid.UUID | None = None
    source_report_id: str = ""
    source_trust_mode: str = ""
    schedule: str
    is_active: bool
    jurisdiction_bundle: str = "custom"
    target_jurisdictions: list[str] = Field(default_factory=list)
    strategy_version: str = ""
    monitoring_strategy: dict = Field(default_factory=dict)
    watch_targets: list[dict] = Field(default_factory=list)
    last_run_at: datetime | None
    last_full_refresh_at: datetime | None = None
    last_run_mode: str = ""
    last_run_status: str = ""
    last_run_summary: str = ""
    last_patent_count: int
    conclusion_status: str = "unbound"
    stale_conclusions: list[MonitorConclusionImpact] = Field(default_factory=list)
    stale_conclusion_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitorListResponse(BaseModel):
    items: list[MonitorResponse]
    total: int


class MonitorAlertResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    alert_type: str = "new_patent_delta"
    severity: str = "medium"
    summary: str = ""
    strategy_mode: str = ""
    new_patent_ids: list[str]
    new_event_ids: list[str] = Field(default_factory=list)
    jurisdiction_deltas: dict = Field(default_factory=dict)
    affected_conclusions: list[MonitorConclusionImpact] = Field(default_factory=list)
    stale_conclusion_count: int = 0
    new_patent_count: int
    run_at: datetime
    dismissed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitorAlertListResponse(BaseModel):
    items: list[MonitorAlertResponse]
    total: int


class RunMonitorRequest(BaseModel):
    force_full_refresh: bool = False


class MonitorRunResponse(BaseModel):
    monitor_id: uuid.UUID
    run_mode: str
    status: str
    summary: str = ""
    query_count: int = 0
    alert_created: bool = False
    alert_id: uuid.UUID | None = None
    new_patent_count: int = 0
    new_patent_ids: list[str] = Field(default_factory=list)
    new_event_ids: list[str] = Field(default_factory=list)
    next_recommended_mode: str = ""
    provider_names: list[str] = Field(default_factory=list)
    conclusion_status: str = "unbound"
    affected_conclusions: list[MonitorConclusionImpact] = Field(default_factory=list)
    stale_conclusion_count: int = 0
    coverage_complete: bool = False
    coverage_cursor: int = Field(default=0, ge=0)
    coverage_total: int = Field(default=0, ge=0)
