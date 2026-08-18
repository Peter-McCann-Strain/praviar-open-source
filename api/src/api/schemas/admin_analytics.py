"""Analytics schemas for the LLM cost dashboard and usage tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Cost Breakdown ───────────────────────────────────────────────────────────


class DailyCost(BaseModel):
    """Cost total for a single day."""

    date: str
    total_cost_usd: float = 0.0
    analysis_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class StepCost(BaseModel):
    """Cost breakdown for a single pipeline step."""

    step_name: str
    total_cost_usd: float = 0.0
    analysis_count: int = 0
    avg_cost_usd: float = 0.0


class ModelCost(BaseModel):
    """Cost breakdown for a single LLM model."""

    model_name: str
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    request_count: int = 0


class CostBreakdownResponse(BaseModel):
    """Full cost breakdown: daily totals, per-step, per-model."""

    daily_costs: list[DailyCost] = Field(default_factory=list)
    step_costs: list[StepCost] = Field(default_factory=list)
    model_costs: list[ModelCost] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    period: str = "month"  # day | week | month
    start_date: str | None = None
    end_date: str | None = None


# ── Usage Analytics ──────────────────────────────────────────────────────────


class OrgUsage(BaseModel):
    """Usage stats for a single organization."""

    org_id: uuid.UUID
    org_name: str = ""
    analysis_count: int = 0
    total_cost_usd: float = 0.0
    avg_cost_usd: float = 0.0


class StatusBreakdown(BaseModel):
    """Count of analyses by status."""

    status: str
    count: int = 0


class TopCompound(BaseModel):
    """Most frequently analyzed compound."""

    compound_name: str
    compound_smiles: str = ""
    analysis_count: int = 0


class UsageAnalyticsResponse(BaseModel):
    """Usage statistics: by org, by status, by compound."""

    org_usage: list[OrgUsage] = Field(default_factory=list)
    status_breakdown: list[StatusBreakdown] = Field(default_factory=list)
    top_compounds: list[TopCompound] = Field(default_factory=list)
    total_analyses: int = 0
    avg_cost_per_analysis: float = 0.0
    avg_duration_seconds: float | None = None
    period: str = "month"


# ── Model Usage ──────────────────────────────────────────────────────────────


class ModelUsageDetail(BaseModel):
    """Detailed usage for a single LLM model."""

    model_name: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    request_count: int = 0
    cache_hit_rate: float | None = None


class ModelUsageResponse(BaseModel):
    """LLM model usage breakdown."""

    models: list[ModelUsageDetail] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    overall_cache_hit_rate: float | None = None
    period: str = "month"


# ── Audit Log (extended) ────────────────────────────────────────────────────


class AuditLogEntryExtended(BaseModel):
    """Extended audit log entry with additional metadata for the analytics view."""

    id: uuid.UUID
    org_id: uuid.UUID
    action: str
    user_id: uuid.UUID | None = None
    user_email: str = ""
    analysis_id: uuid.UUID | None = None
    details: dict = Field(default_factory=dict)
    ip_address: str = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListExtendedResponse(BaseModel):
    """Paginated audit log response with export support."""

    items: list[AuditLogEntryExtended] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 50
    has_next: bool = False
