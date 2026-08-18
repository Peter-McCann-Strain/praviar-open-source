"""Core quality and search-health report models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.schemas.reports_types import RiskLevel, SourceStatus, VerificationSeverity


class RiskSummaryResponse(BaseModel):
    """Executive risk summary nested inside the report."""

    overall_risk: RiskLevel
    blocking_patents_count: int = 0
    total_patents_analyzed: int = 0
    key_risks: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    summary_validation_issues: list[str] = Field(default_factory=list)


class SourceHealthEntryResponse(BaseModel):
    """Health record for one queried source."""

    source: str
    status: SourceStatus
    patent_count: int = 0
    attempted_count: int = 0
    covered_count: int = 0
    error_message: str = ""


class SourceHealthResponse(BaseModel):
    """Aggregated search-source health."""

    entries: list[SourceHealthEntryResponse] = Field(default_factory=list)


class AnalysisFailureResponse(BaseModel):
    """A patent analysis failure retained in the final report."""

    patent_id: str
    step: str
    error_type: str
    error_message: str
    recoverable: bool = False


class DataLimitationResponse(BaseModel):
    """A known data/evidence limitation for the matter."""

    category: str
    description: str
    impact: str


class VerificationCheckResponse(BaseModel):
    """A single deterministic verification check."""

    check_name: str
    passed: bool
    severity: VerificationSeverity = "pass"
    details: str = ""


class VerificationResultResponse(BaseModel):
    """Full deterministic verification result."""

    checks: list[VerificationCheckResponse] = Field(default_factory=list)
    all_citations_valid: bool = False
    all_claims_grounded: bool = False
    all_entities_valid: bool = False
    dates_consistent: bool = False
    risk_levels_justified: bool = False
    issues: list[str] = Field(default_factory=list)


class StepTokenUsageResponse(BaseModel):
    """Token usage for a single pipeline step."""

    step_name: str
    model_role: str
    model_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


__all__ = [
    "AnalysisFailureResponse",
    "DataLimitationResponse",
    "RiskSummaryResponse",
    "SourceHealthEntryResponse",
    "SourceHealthResponse",
    "StepTokenUsageResponse",
    "VerificationCheckResponse",
    "VerificationResultResponse",
]
