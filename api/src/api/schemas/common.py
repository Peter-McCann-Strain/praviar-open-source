"""Shared response schemas used across multiple routes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str


class IdResponse(BaseModel):
    """Generic response with just an id."""

    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """Health/readiness check response."""

    status: str
    version: str


class MarkedCountResponse(BaseModel):
    """Response indicating how many records were updated."""

    marked: int


class SharedReportIntegritySummaryResponse(BaseModel):
    """Public evidence-integrity summary for a shared FTO report."""

    affected_patents_count: int = 0
    recoverable_failures_count: int = 0
    needs_review_count: int = 0
    data_limitations_count: int = 0
    source_caveats_count: int = 0
    evidence_sufficient_for_clearance: bool = True
    metadata_inconsistent: bool = False


class SharedReportKeyPatentResponse(BaseModel):
    """Public patent summary included in a shared FTO report."""

    patent_number: str
    risk_level: str
    assignee: str = ""
    expiry: str = ""
    patent_url: str = ""
    source_reference: str = ""


class SharedReportResponse(BaseModel):
    """Public payload for a shared FTO report."""

    compound_name: str
    report_id: str
    share_id: str
    packet_version: str
    source_snapshot_at: str = ""
    pipeline_version: str = ""
    model_version: str = ""
    integrity_digest: str
    overall_risk: str
    blocking_patents_count: int
    total_patents_found: int
    executive_summary: str
    key_findings: list[str] = Field(default_factory=list)
    generated_at: str
    key_patents: list[SharedReportKeyPatentResponse] = Field(default_factory=list)
    source_coverage: list[str] = Field(default_factory=list)
    jurisdiction_scope: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    integrity_summary: SharedReportIntegritySummaryResponse = Field(
        default_factory=SharedReportIntegritySummaryResponse
    )
    total_material_patents: int = 0
    omitted_key_patents_count: int = 0
    omitted_limitations_count: int = 0
    standard_limitations: list[str] = Field(default_factory=list)
    intended_use: str = ""
    ai_system_notice: str = ""
    reliance_boundary: str = ""
    review_status: str = ""
    share_expires_at: str = ""
    verified_recipient_email: str
    attributable_view_number: int = Field(ge=1)
    verified_session_expires_at: str


class ReportSearchResultResponse(BaseModel):
    """A single keyword search hit within a report."""

    model_config = ConfigDict(extra="allow")


class ReportSearchResponse(BaseModel):
    """Results from a keyword search over a report."""

    query: str
    interpreted_query: str
    results: list[ReportSearchResultResponse] = Field(default_factory=list)
    total: int = 0

    model_config = ConfigDict(extra="allow")
