"""Workspace summary schemas for governed report analysis."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.chat import ChatPolicy
from api.schemas.report_evidence_search import EvidenceSearchScopeResponse
from api.schemas.reports_fto_io import ReportSummaryResponse


class WorkspaceEvidenceQueryResponse(BaseModel):
    """A deterministic evidence query suggestion for the analyst workspace."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["compound", "modality", "jurisdiction", "search_strategy", "risk"] = "compound"
    query: str
    rationale: str
    source: str = ""


class MonitorSeedDefaultsResponse(BaseModel):
    """Defaults for creating a monitor from a completed report."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    compound_name: str = ""
    compound_smiles: str = ""
    schedule: Literal["daily", "weekly", "monthly"] = "weekly"
    source_report_id: str = ""
    source_trust_mode: str = "explorer"
    requires_manual_input: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class ReportIdentityResolutionResponse(BaseModel):
    """Tenant-scoped mapping from a report or analysis reference to its analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    report_id: str = ""
    matched_by: Literal["analysis_id", "report_id"]


class ReportWorkspaceSummaryResponse(BaseModel):
    """Read-only workspace summary for a completed FTO analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    report_id: str = ""
    trust_mode: str = "explorer"
    jurisdiction_bundle: str = "custom"
    target_jurisdictions: list[str] = Field(default_factory=list)
    report_summary: ReportSummaryResponse
    capability_metadata: ChatPolicy
    suggested_evidence_queries: list[WorkspaceEvidenceQueryResponse] = Field(default_factory=list)
    monitor_seed_defaults: MonitorSeedDefaultsResponse
    routing_profile: dict[str, Any] = Field(default_factory=dict)
    opinion_readiness: dict[str, Any] = Field(default_factory=dict)
    data_coverage: dict[str, Any] = Field(default_factory=dict)
    source_convergence: dict[str, Any] = Field(default_factory=dict)
    jurisdiction_matrix: list[dict[str, Any]] = Field(default_factory=list)
    jurisdiction_certification: list[dict[str, Any]] = Field(default_factory=list)
    jurisdiction_source_coverage: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_register: list[dict[str, Any]] = Field(default_factory=list)
    evidence_scope: EvidenceSearchScopeResponse = Field(default_factory=EvidenceSearchScopeResponse)
