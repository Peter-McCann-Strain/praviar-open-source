"""Request/response schemas for comments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    body: str = Field(..., min_length=1, max_length=10000)
    parent_id: uuid.UUID | None = None
    target_type: Literal["analysis", "patent", "claim"] = "analysis"
    target_id: str = Field(default="", max_length=100)
    mentions: list[Annotated[str, Field(max_length=320)]] = Field(
        default_factory=list, max_length=50
    )


class CommentCreatedResponse(BaseModel):
    """Response after creating a comment."""

    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentResponse(BaseModel):
    """Full comment representation for list endpoints."""

    id: uuid.UUID
    user_id: uuid.UUID
    body: str
    target_type: str
    target_id: str
    parent_id: uuid.UUID | None
    resolved: bool
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    assigned_to: uuid.UUID | None = None
    assigned_by: uuid.UUID | None = None
    assigned_at: datetime | None = None
    assigned_reviewer_name: str | None = None
    assigned_reviewer_email: str | None = None
    assignment_event_count: int = 0
    last_assignment_at: datetime | None = None
    queue_age_hours: int | None = None
    is_overdue: bool = False
    escalation_status: str = "none"
    escalated_by: uuid.UUID | None = None
    escalated_at: datetime | None = None
    escalated_by_name: str | None = None
    escalated_by_email: str | None = None
    escalation_event_count: int = 0
    last_escalation_at: datetime | None = None
    escalated_to_review: bool = False
    review_handoff_comment_id: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentReviewQueueCountsResponse(BaseModel):
    """Aggregate open-thread workload counts for the org-level review queue."""

    open_total: int = 0
    mine: int = 0
    assigned: int = 0
    unassigned: int = 0
    overdue: int = 0
    escalated: int = 0

    model_config = ConfigDict(from_attributes=True)


class CommentReviewQueueItemResponse(CommentResponse):
    """Top-level queue item enriched with analysis context."""

    analysis_id: uuid.UUID
    compound_name: str
    analysis_status: str
    overall_risk: str | None = None
    is_mine: bool = False
    reply_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CommentReviewQueueResponse(BaseModel):
    """Org-level legal review queue summary and selected items."""

    counts: CommentReviewQueueCountsResponse
    items: list[CommentReviewQueueItemResponse]

    model_config = ConfigDict(from_attributes=True)


class CommentReviewerResponse(BaseModel):
    """Reviewer candidate for assignment."""

    id: uuid.UUID
    email: str
    full_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class CommentAssignmentHistoryEventResponse(BaseModel):
    """Single assignment event within a thread history."""

    id: uuid.UUID
    comment_id: uuid.UUID
    analysis_id: uuid.UUID
    event_type: str
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    assigned_to_email: str | None = None
    assigned_by: uuid.UUID | None = None
    assigned_by_name: str | None = None
    assigned_by_email: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentAssignmentHistoryResponse(BaseModel):
    """Assignment history for a comment thread."""

    comment_id: uuid.UUID
    thread_root_comment_id: uuid.UUID
    analysis_id: uuid.UUID
    assignment_event_count: int
    last_assignment_at: datetime | None = None
    events: list[CommentAssignmentHistoryEventResponse]

    model_config = ConfigDict(from_attributes=True)


class EscalateCommentThreadRequest(BaseModel):
    """Inbound payload for explicit thread escalation into legal review."""

    model_config = ConfigDict(extra="forbid")

    review_note: str = Field(default="", max_length=4000)
    promote_to_under_review: bool = True


class UpdateCommentResolutionRequest(BaseModel):
    """Inbound payload for toggling comment resolution."""

    model_config = ConfigDict(extra="forbid")

    resolved: bool


class UpdateCommentAssignmentRequest(BaseModel):
    """Inbound payload for assigning or unassigning a comment."""

    model_config = ConfigDict(extra="forbid")

    assigned_to: uuid.UUID | None
