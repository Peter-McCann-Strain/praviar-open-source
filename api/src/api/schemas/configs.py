"""Request/response schemas for configuration presets."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.analyses import AnalysisConfigSchema


class CreatePresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    config: AnalysisConfigSchema
    is_default: bool = False


class SetOrgDefaultsRequest(BaseModel):
    """Validated request body for setting org-wide default config."""

    model_config = ConfigDict(extra="forbid")

    search_max_ranked_results: int | None = Field(default=None, ge=50, le=500)
    search_tanimoto_threshold: float | None = Field(default=None, gt=0.0, le=1.0)
    include_expired: bool | None = None
    search_jurisdictions: list[str] | None = Field(default=None, max_length=20)
    enable_pubchem: bool | None = None
    enable_bigquery: bool | None = None
    enable_surechembl: bool | None = None
    enable_patcid: bool | None = None
    max_analysis_patents: int | None = Field(default=None, ge=5, le=30)
    max_doe_candidates: int | None = Field(default=None, ge=5, le=20)
    triage_batch_size: int | None = Field(default=None, ge=5, le=15)
    citation_traversal_enabled: bool | None = None
    citation_max_depth: int | None = Field(default=None, ge=1, le=3)
    search_expired_grace_years: int | None = Field(default=None, ge=1, le=10)
    analysis_thinking_budget_tokens: int | None = Field(default=None, ge=4000, le=32000)
    thinking_effort_analysis: str | None = None
    thinking_effort_triage: str | None = None
    thinking_effort_report: str | None = None
    search_loop_enabled: bool | None = None
    matter_type: str | None = None
    jurisdiction_policy: str | None = None
    clearance_threshold_profile: str | None = None
    max_run_duration_hours: int | None = Field(default=None, ge=1, le=72)
    source_authority_policy: str | None = None
    required_record_components: list[str] | None = Field(default=None, max_length=20)
    hitl_enabled: bool | None = None
    hitl_checkpoints: list[str] | None = Field(default=None, max_length=20)
    hitl_auto_skip_minutes: int | None = Field(default=None, ge=1, le=120)

    def normalized_config(self) -> dict[str, Any]:
        """Return the partial config after validation against analysis config."""
        config = self.model_dump(exclude_none=True)
        normalized = AnalysisConfigSchema.model_validate(config)
        return normalized.model_dump(include=set(config), exclude_none=True)


class PresetResponse(BaseModel):
    """Full config preset representation."""

    id: uuid.UUID
    name: str
    description: str
    config: dict[str, Any]
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class PresetCreatedResponse(BaseModel):
    """Response after creating a preset."""

    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class OrgDefaultsResponse(BaseModel):
    """Organization-wide default analysis configuration."""

    config: dict[str, Any]
    can_manage: bool
