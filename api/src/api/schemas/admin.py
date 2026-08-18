"""Admin dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.db.models import OrgPlan

# ── Health ────────────────────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    name: str
    status: str  # "ok" | "error"
    detail: str = ""


class SystemHealthResponse(BaseModel):
    services: list[ServiceHealth]
    table_counts: dict[str, int]


# ── Organizations ─────────────────────────────────────────────────────────────


class AdminCapabilities(BaseModel):
    admin_org_id: uuid.UUID
    is_platform_superadmin: bool = False
    can_manage_org_billing: bool = False
    can_list_cross_org_users: bool = False
    can_manage_cross_org_user_roles: bool = False
    can_inspect_task_queue: bool = False


class OrgSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    user_count: int = 0
    analysis_count: int = 0
    max_analyses_per_month: int
    free_analyses_remaining: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrgListResponse(BaseModel):
    items: list[OrgSummary]
    total: int
    capabilities: AdminCapabilities


class UpdateOrgRequest(BaseModel):
    plan: OrgPlan | None = None
    max_analyses_per_month: int | None = Field(None, ge=1, le=10000)
    free_analyses_remaining: int | None = Field(None, ge=0, le=1000)


# ── Users ─────────────────────────────────────────────────────────────────────


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    org_id: uuid.UUID
    org_name: str = ""
    last_active_at: datetime | None
    membership_active: bool = True
    membership_synchronized: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int
    capabilities: AdminCapabilities


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|attorney|scientist|client)$")


class InviteRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    role: str = Field(default="scientist", pattern="^(admin|attorney|scientist|client)$")


class AdminOperationStatus(BaseModel):
    operation_id: uuid.UUID
    operation_type: str
    state: str
    outcome_confirmed: bool
    reconciliation_required: bool
    recovery_available: bool = False
    recovery_action: Literal["retry_rejected_role"] | None = None
    provider_resource_id: str | None = None
    target_user_id: uuid.UUID | None = None
    target_email_normalized: str | None = None
    requested_role: str
    updated_at: datetime


class AdminOperationRecoveryRequest(BaseModel):
    recovery_action: Literal["retry_rejected_role"] | None = None


class AdminOperationListResponse(BaseModel):
    items: list[AdminOperationStatus]
    open_total: int = Field(ge=0)
    has_more: bool


# ── Metrics ───────────────────────────────────────────────────────────────────


class DailyMetric(BaseModel):
    date: str
    count: int
    cost: float = 0.0
    errors: int = 0


class MetricsResponse(BaseModel):
    daily: list[DailyMetric]
    total_analyses: int
    total_cost: float
    avg_duration_seconds: float | None
    error_rate: float


# ── Audit Logs ────────────────────────────────────────────────────────────────


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    action: str
    user_id: uuid.UUID | None
    user_email: str = ""
    analysis_id: uuid.UUID | None
    details: dict
    ip_address: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int


# ── Tasks ─────────────────────────────────────────────────────────────────────


class TaskInfo(BaseModel):
    id: str
    name: str
    args: list = Field(default_factory=list)
    status: str = "active"


CeleryTaskInfo = TaskInfo


class TaskQueueResponse(BaseModel):
    backend: str = "celery"
    detail: str = ""
    inspectable: bool = True
    active: list[TaskInfo]
    reserved: list[TaskInfo]
    scheduled_count: int
