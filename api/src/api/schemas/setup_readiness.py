"""Schemas for the organization-scoped setup readiness checklist."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SetupReadinessItemId(StrEnum):
    IDENTITY = "identity"
    COLLABORATORS = "collaborators"
    EVIDENCE_POLICY = "evidence_policy"
    BILLING = "billing"
    SSO = "sso"
    FIRST_ANALYSIS = "first_analysis"
    REVIEW_HANDOFF = "review_handoff"
    SHARE_EXPORT = "share_export"


class SetupReadinessItemStatus(StrEnum):
    COMPLETE = "complete"
    ACTION_REQUIRED = "action_required"
    BLOCKED = "blocked"
    NOT_REQUIRED = "not_required"


class SetupReadinessOverallStatus(StrEnum):
    READY = "ready"
    ACTION_REQUIRED = "action_required"


class SetupReadinessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: SetupReadinessItemId
    label: str
    description: str
    status: SetupReadinessItemStatus
    owner: str
    recovery_label: str
    recovery_href: str | None
    evidence: str


class SetupReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_status: SetupReadinessOverallStatus
    current_user_role: Literal["admin", "attorney", "scientist", "client"]
    completed_items: int = Field(ge=0)
    applicable_items: int = Field(ge=0)
    items: list[SetupReadinessItem]
    observed_at: datetime
