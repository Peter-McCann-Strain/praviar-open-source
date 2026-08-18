"""Authenticated user role and capability contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PrincipalCapabilitiesResponse(BaseModel):
    """UI-safe capabilities derived from the authenticated application role."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["admin", "attorney", "scientist", "client"]
    can_create_analysis: bool
    can_view_patents: bool
    can_manage_monitors: bool
    can_view_review_queue: bool
    can_assign_review: bool
    can_resolve_review: bool
    can_escalate_review: bool
    can_create_batch: bool
    can_manage_config: bool
    can_export_report: bool
    can_share_report: bool
    can_deliver_report: bool
    can_view_billing: bool
    can_manage_billing: bool
    can_manage_api_keys: bool
    can_view_platform_admin: bool
    risk_ratings_restricted: bool
    api_key_report_export_scope_available: bool
