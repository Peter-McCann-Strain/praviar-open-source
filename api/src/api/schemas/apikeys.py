"""API key management schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

APIKeyScope = Literal[
    "analyses:read",
    "analyses:write",
    "reports:read",
    "reports:export",
    "monitors:manage",
]

MAX_API_KEY_LIFETIME_DAYS = 365


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[APIKeyScope] = Field(..., min_length=1, max_length=5)
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_unique(cls, value: list[APIKeyScope]) -> list[APIKeyScope]:
        if len(value) != len(set(value)):
            raise ValueError("API key scopes must be unique")
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_bounded(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("API key expiry must include a timezone")

        now = datetime.now(UTC)
        if value <= now:
            raise ValueError("API key expiry must be in the future")
        if value > now + timedelta(days=MAX_API_KEY_LIFETIME_DAYS):
            raise ValueError(f"API key expiry cannot exceed {MAX_API_KEY_LIFETIME_DAYS} days")
        return value


class APIKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    secret_key: str  # Only returned once at creation time
    scopes: list[APIKeyScope]
    expires_at: datetime
    created_at: datetime


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[APIKeyScope]
    expires_at: datetime
    last_used_at: datetime | None
    revoked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class APIKeyListResponse(BaseModel):
    items: list[APIKeyResponse]
    total: int
