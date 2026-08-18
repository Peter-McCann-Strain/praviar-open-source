"""Request/response schemas for notifications."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(enum.StrEnum):
    """Types of in-app notifications."""

    ANALYSIS_COMPLETE = "analysis_complete"
    MONITOR_ALERT = "monitor_alert"
    EXPORT_READY = "export_ready"
    TEAM_INVITE = "team_invite"
    SYSTEM = "system"


class DigestFrequency(enum.StrEnum):
    """Email digest frequency options."""

    OFF = "off"
    WEEKLY = "weekly"


class NotificationResponse(BaseModel):
    """Single notification item."""

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    read: bool
    data: dict = Field(default_factory=dict)
    actionable: bool = False
    tombstoned: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Paginated notification list with unread count."""

    items: list[NotificationResponse]
    unread_count: int
    total: int


class UnreadCountResponse(BaseModel):
    """Just the unread notification count (for badge polling)."""

    unread_count: int


class MarkReadRequest(BaseModel):
    """Mark specific notifications as read."""

    notification_ids: list[uuid.UUID] = Field(..., max_length=200)


class NotificationActionResponse(BaseModel):
    """Server-authoritative result for a notification action."""

    notification_id: uuid.UUID
    actionable: bool
    destination: str | None = None
    marked_read: bool


class NotificationPreferencesSchema(BaseModel):
    """User notification preferences (stored in User.preferences JSONB)."""

    email_on_analysis_complete: bool = True
    email_on_monitor_alert: bool = True
    email_digest_frequency: DigestFrequency = DigestFrequency.WEEKLY


class DigestUnsubscribeRequest(BaseModel):
    """Signed one-click request forwarded from the public web endpoint."""

    model_config = ConfigDict(extra="forbid")

    # Shape validation happens inside the service so malformed capabilities are
    # response-indistinguishable from expired, consumed, or unknown ones.
    token: str = Field(max_length=2048)


class DigestUnsubscribeResponse(BaseModel):
    """Idempotent result of disabling recurring digest delivery."""

    status: Literal["unsubscribed"]
