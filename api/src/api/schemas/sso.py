"""SSO configuration schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SSOUnavailableReason = Literal[
    "missing_secret",
    "circuit_open",
    "transport_error",
    "not_found",
    "provider_error",
    "malformed_response",
]


class SSOStatusResponse(BaseModel):
    sso_enabled: bool
    provider: str | None
    domains: list[str]
    status: Literal["active", "pending", "inactive"]
    clerk_dashboard_url: str | None = None
    sso_status_available: bool
    sso_last_synced_at: datetime | None
    sso_status_stale: bool
    sso_unavailable_reason: SSOUnavailableReason | None = None


class SSOConfigureRequest(BaseModel):
    enable: bool


class SSOConfigureResponse(BaseModel):
    status: str
    message: str
    next_steps: list[str]
    clerk_dashboard_url: str | None = None
