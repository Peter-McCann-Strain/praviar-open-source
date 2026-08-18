"""Thread escalation logic and metadata builders for comments.

This module handles escalation status computation, thread metadata
assembly, and the higher-level service functions that compose escalation
views. It is not intended to be imported directly by route handlers; use
the :mod:`api.services.comments` facade instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Comment
from api.db.models_collaboration import CommentAssignmentEvent, CommentThreadEscalation
from api.errors import APIError
from api.services.comments_crud import (
    ASSIGNMENT_OVERDUE_ASSIGNED_HOURS,
    ASSIGNMENT_OVERDUE_UNASSIGNED_HOURS,
    coerce_datetime,
    coerce_string,
    coerce_uuid,
    comment_root_id,
    list_comments_for_analysis,
    load_comment_assignment_events,
    load_comment_for_org,
    load_reviewer_lookup,
    load_thread_escalation,
    load_users_by_ids,
    serialize_comment,
)

# ── Thread metadata ───────────────────────────────────────────────────────────


def build_thread_metadata(
    *,
    root_comment: Comment,
    events: list[CommentAssignmentEvent],
    escalation: CommentThreadEscalation | None,
    now: datetime,
) -> dict:
    event_times = [
        event_time
        for event in events
        if (event_time := coerce_datetime(getattr(event, "created_at", None))) is not None
    ]
    assigned_at = coerce_datetime(getattr(root_comment, "assigned_at", None))
    last_assignment_at: datetime | None
    if event_times:
        last_assignment_at = max([*event_times, *([assigned_at] if assigned_at else [])])
        assignment_event_count = len(events)
    elif coerce_uuid(getattr(root_comment, "assigned_to", None)) is not None:
        # Back-compat fallback for comments assigned before the history trail existed.
        last_assignment_at = assigned_at or coerce_datetime(
            getattr(root_comment, "created_at", None)
        )
        assignment_event_count = 1
    else:
        last_assignment_at = None
        assignment_event_count = 0

    queue_age_hours: int | None = None
    is_overdue = False
    escalation_status = "none"
    escalated_by = None
    escalated_at = None
    escalation_event_count = 0
    last_escalation_at = None
    escalated_to_review = False
    review_handoff_comment_id = None
    if not getattr(root_comment, "resolved", False):
        created_at = coerce_datetime(getattr(root_comment, "created_at", None))
        if created_at is not None:
            queue_age_hours = max(0, int((now - created_at).total_seconds() // 3600))
            assigned_to = coerce_uuid(getattr(root_comment, "assigned_to", None))
            if assigned_to is not None:
                is_overdue = queue_age_hours > ASSIGNMENT_OVERDUE_ASSIGNED_HOURS
            else:
                is_overdue = queue_age_hours > ASSIGNMENT_OVERDUE_UNASSIGNED_HOURS
            if is_overdue:
                escalation_status = "overdue"
            elif queue_age_hours >= 24:
                escalation_status = "watch"

    if escalation is not None:
        escalation_status = (
            coerce_string(getattr(escalation, "escalation_status", None)) or "escalated"
        )
        escalated_by = coerce_uuid(getattr(escalation, "escalated_by", None))
        escalated_at = coerce_datetime(getattr(escalation, "escalated_at", None))
        escalation_event_count = 1 if escalated_at is not None or escalated_by is not None else 0
        last_escalation_at = escalated_at
        escalated_to_review = bool(getattr(escalation, "escalated_to_review", False))
        review_handoff_comment_id = coerce_uuid(
            getattr(escalation, "review_handoff_comment_id", None)
        )

    return {
        "assigned_to": coerce_uuid(getattr(root_comment, "assigned_to", None)),
        "assigned_by": coerce_uuid(getattr(root_comment, "assigned_by", None)),
        "assigned_at": assigned_at,
        "assignment_event_count": assignment_event_count,
        "last_assignment_at": last_assignment_at,
        "queue_age_hours": queue_age_hours,
        "is_overdue": is_overdue,
        "escalation_status": escalation_status,
        "escalated_by": escalated_by,
        "escalated_at": escalated_at,
        "escalated_by_name": None,
        "escalated_by_email": None,
        "escalation_event_count": escalation_event_count,
        "last_escalation_at": last_escalation_at,
        "escalated_to_review": escalated_to_review,
        "review_handoff_comment_id": review_handoff_comment_id,
    }


def is_explicitly_escalated(thread_metadata: dict) -> bool:
    return bool(
        thread_metadata.get("escalation_status") == "escalated"
        or thread_metadata.get("escalated_to_review")
        or thread_metadata.get("review_handoff_comment_id") is not None
        or int(thread_metadata.get("escalation_event_count", 0)) > 0
    )


# ── Higher-level escalation service functions ─────────────────────────────────


async def build_thread_metadata_with_actor(
    db: AsyncSession,
    *,
    root_comment: Comment,
    escalation: CommentThreadEscalation | None,
    org_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[dict, list[CommentAssignmentEvent]]:
    """Build thread metadata and resolve actor display names for an escalation."""
    now = now or datetime.now(UTC)
    events = await load_comment_assignment_events(db, comment_id=root_comment.id, org_id=org_id)
    metadata = build_thread_metadata(
        root_comment=root_comment,
        events=events,
        escalation=escalation,
        now=now,
    )
    if escalation is not None:
        actor_id = coerce_uuid(getattr(escalation, "escalated_by", None))
        if actor_id is not None:
            actor_lookup = await load_users_by_ids(db, org_id=org_id, user_ids={actor_id})
            actor = actor_lookup.get(actor_id)
            metadata["escalated_by_name"] = coerce_string(getattr(actor, "full_name", None))
            metadata["escalated_by_email"] = coerce_string(getattr(actor, "email", None))
    return metadata, events


async def load_existing_thread_escalation_view(
    db: AsyncSession,
    *,
    comment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[Comment, list[Comment], CommentThreadEscalation | None]:
    """Resolve the thread root comment + sibling comments + any existing
    escalation row. Raises 404/400 as needed.
    """
    comment = await load_comment_for_org(db, comment_id=comment_id, org_id=org_id)
    comments = await list_comments_for_analysis(
        db,
        analysis_id=comment.analysis_id,
        org_id=org_id,
    )
    comment_lookup = {item.id: item for item in comments}
    root_cache: dict[uuid.UUID, uuid.UUID] = {}
    root_id = comment_root_id(comment, comment_lookup, root_cache)
    root_comment = comment_lookup[root_id]
    if root_comment.parent_id is not None:
        raise APIError(400, "Bad Request", "Only top-level comment threads can be escalated")
    existing = await load_thread_escalation(db, comment_id=root_comment.id, org_id=org_id)
    return root_comment, comments, existing


async def serialize_existing_escalation(
    db: AsyncSession,
    *,
    root_comment: Comment,
    comments: list[Comment],
    escalation: CommentThreadEscalation,
    org_id: uuid.UUID,
) -> dict:
    """Serialise the response when an escalation already exists (idempotent)."""
    reviewer_lookup = await load_reviewer_lookup(db, comments=comments, org_id=org_id)
    thread_metadata, _events = await build_thread_metadata_with_actor(
        db, root_comment=root_comment, escalation=escalation, org_id=org_id
    )
    return serialize_comment(
        root_comment, reviewer_lookup=reviewer_lookup, thread_metadata=thread_metadata
    )


def create_thread_escalation_record(
    *,
    root_comment: Comment,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    promote_to_under_review: bool,
) -> CommentThreadEscalation:
    """Create the unsaved CommentThreadEscalation row for a new escalation."""
    return CommentThreadEscalation(
        comment_id=root_comment.id,
        analysis_id=root_comment.analysis_id,
        org_id=org_id,
        escalated_by=actor_id,
        escalation_status="escalated",
        escalated_to_review=promote_to_under_review,
    )


def build_escalation_audit_details(
    *,
    root_comment: Comment,
    user_id: uuid.UUID,
    thread_metadata: dict,
    handoff_response,
) -> dict:
    return {
        "comment_id": str(root_comment.id),
        "analysis_id": str(root_comment.analysis_id),
        "escalated_by": str(user_id),
        "escalated_at": thread_metadata["escalated_at"].isoformat()
        if thread_metadata["escalated_at"]
        else None,
        "escalated_to_review": handoff_response.escalated_to_review,
        "review_handoff_comment_id": str(handoff_response.comment_id),
        "target_type": root_comment.target_type,
        "target_id": root_comment.target_id,
    }
