"""Commercial exposure models used by FTO report decisioning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClaimConstructionRecord(BaseModel):
    """Matter-level record of claim construction standards used in the report."""

    model_config = ConfigDict(extra="forbid")

    standard: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    disputed_terms: list[str] = Field(default_factory=list)
    summary: str = ""


class FutureRiskFinding(BaseModel):
    """Forward-looking risk item not captured by current issued-claim exposure alone."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    jurisdiction: str = ""
    risk_type: str = ""
    severity: str = ""
    monitoring_required: bool = False
    related_patent_ids: list[str] = Field(default_factory=list)
    record_basis: list[str] = Field(default_factory=list)
    summary: str = ""


class CommercialExposure(BaseModel):
    """Commercial impact framing for launch-at-risk scenarios."""

    model_config = ConfigDict(extra="forbid")

    damages_injunction_risk: str = ""
    business_severity: str = ""
    blocking_patent_ids: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    summary: str = ""
