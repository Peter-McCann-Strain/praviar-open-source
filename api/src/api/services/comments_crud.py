"""Coercion helpers, thread-tree traversal, serialisation, and DB loaders for comments.

This module contains the foundational helpers used across all comment operations.
It is not intended to be imported directly by route handlers; use the
:mod:`api.services.comments` facade instead.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, AnalysisStatus, Comment, User, UserRole
from api.db.models_collaboration import CommentAssignmentEvent, CommentThreadEscalation
from api.errors import APIError

REVIEWER_ROLES = (UserRole.ADMIN, UserRole.ATTORNEY)
ASSIGNER_ROLES = (UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST)
REVIEW_QUEUE_ROLES = ASSIGNER_ROLES
ASSIGNMENT_OVERDUE_ASSIGNED_HOURS = 72
ASSIGNMENT_OVERDUE_UNASSIGNED_HOURS = 48

AssignmentState = Literal["all", "assigned", "unassigned", "overdue", "mine"]
ReviewQueueFilter = Literal["all", "mine", "unassigned", "overdue", "escalated"]


# ── Coercion helpers ─────────────────────────────────────────────────────────


def coerce_uuid(value: object) -> uuid.UUID | None:
    return value if isinstance(value, uuid.UUID) else None


def coerce_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def coerce_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def coerce_string_value(value: object) -> str | None:
    string_value = coerce_string(value)
    if string_value is not None:
        return string_value
    enum_value = getattr(value, "value", None)
    return coerce_string(enum_value)


# ── Thread-tree traversal ────────────────────────────────────────────────────


def comment_root_id(
    comment: Comment,
    comment_lookup: dict[uuid.UUID, Comment],
    cache: dict[uuid.UUID, uuid.UUID],
) -> uuid.UUID:
    cached = cache.get(comment.id)
    if cached is not None:
        return cached

    # Walk iteratively to avoid RecursionError on arbitrarily deep chains
    # (can occur with legacy data predating the 2-level depth enforcement).
    # A visited set also guards against any cyclic parent_id data.
    path: list[uuid.UUID] = []
    visited: set[uuid.UUID] = set()
    current = comment
    while True:
        if current.id in cache:
            root_id = cache[current.id]
            break
        if current.id in visited:
            # Cycle detected — treat this node as its own root
            root_id = current.id
            break
        visited.add(current.id)
        path.append(current.id)
        parent_id = coerce_uuid(getattr(current, "parent_id", None))
        if parent_id is None or parent_id not in comment_lookup:
            root_id = current.id
            break
        current = comment_lookup[parent_id]

    for node_id in path:
        cache[node_id] = root_id
    return root_id


# ── Serialisation ────────────────────────────────────────────────────────────


def serialize_comment(
    comment: Comment,
    *,
    reviewer_lookup: dict[uuid.UUID, User] | None = None,
    thread_metadata: dict | None = None,
) -> dict:
    resolved_by = coerce_uuid(getattr(comment, "resolved_by", None))
    resolved_at = coerce_datetime(getattr(comment, "resolved_at", None))
    assigned_to = (
        coerce_uuid(thread_metadata.get("assigned_to")) if thread_metadata else None
    ) or coerce_uuid(getattr(comment, "assigned_to", None))
    assigned_by = (
        coerce_uuid(thread_metadata.get("assigned_by")) if thread_metadata else None
    ) or coerce_uuid(getattr(comment, "assigned_by", None))
    assigned_at = (
        coerce_datetime(thread_metadata.get("assigned_at")) if thread_metadata else None
    ) or coerce_datetime(getattr(comment, "assigned_at", None))
    assigned_reviewer = (
        reviewer_lookup.get(assigned_to) if reviewer_lookup and assigned_to else None
    )

    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "body": comment.body,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
        "parent_id": comment.parent_id,
        "resolved": comment.resolved,
        "resolved_by": resolved_by,
        "resolved_at": resolved_at,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
        "assigned_at": assigned_at,
        "assigned_reviewer_name": coerce_string(getattr(assigned_reviewer, "full_name", None)),
        "assigned_reviewer_email": coerce_string(getattr(assigned_reviewer, "email", None)),
        "assignment_event_count": int(thread_metadata.get("assignment_event_count", 0))
        if thread_metadata
        else 0,
        "last_assignment_at": thread_metadata.get("last_assignment_at")
        if thread_metadata
        else None,
        "queue_age_hours": thread_metadata.get("queue_age_hours") if thread_metadata else None,
        "is_overdue": bool(thread_metadata.get("is_overdue", False)) if thread_metadata else False,
        "escalation_status": thread_metadata.get("escalation_status", "none")
        if thread_metadata
        else "none",
        "escalated_by": thread_metadata.get("escalated_by") if thread_metadata else None,
        "escalated_at": thread_metadata.get("escalated_at") if thread_metadata else None,
        "escalated_by_name": thread_metadata.get("escalated_by_name") if thread_metadata else None,
        "escalated_by_email": thread_metadata.get("escalated_by_email")
        if thread_metadata
        else None,
        "escalation_event_count": int(thread_metadata.get("escalation_event_count", 0))
        if thread_metadata
        else 0,
        "last_escalation_at": thread_metadata.get("last_escalation_at")
        if thread_metadata
        else None,
        "escalated_to_review": bool(thread_metadata.get("escalated_to_review", False))
        if thread_metadata
        else False,
        "review_handoff_comment_id": thread_metadata.get("review_handoff_comment_id")
        if thread_metadata
        else None,
        "created_at": comment.created_at,
    }


def serialize_reviewer(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
    }


def serialize_review_queue_item(
    comment: Comment,
    *,
    analysis: Analysis,
    reviewer_lookup: dict[uuid.UUID, User],
    thread_metadata: dict,
) -> dict:
    item = serialize_comment(
        comment,
        reviewer_lookup=reviewer_lookup,
        thread_metadata=thread_metadata,
    )
    item.update(
        {
            "analysis_id": analysis.id,
            "compound_name": coerce_string_value(getattr(analysis, "compound_name", None)) or "",
            "analysis_status": coerce_string_value(getattr(analysis, "status", None)) or "pending",
            "overall_risk": coerce_string_value(getattr(analysis, "overall_risk", None)),
        }
    )
    return item


def serialize_assignment_history_event(
    event: CommentAssignmentEvent,
    *,
    user_lookup: dict[uuid.UUID, User],
) -> dict:
    assigned_to = coerce_uuid(getattr(event, "assigned_to", None))
    assigned_by = coerce_uuid(getattr(event, "assigned_by", None))
    assigned_to_user = user_lookup.get(assigned_to) if assigned_to else None
    assigned_by_user = user_lookup.get(assigned_by) if assigned_by else None
    return {
        "id": event.id,
        "comment_id": event.comment_id,
        "analysis_id": event.analysis_id,
        "event_type": event.event_type,
        "assigned_to": assigned_to,
        "assigned_to_name": coerce_string(getattr(assigned_to_user, "full_name", None)),
        "assigned_to_email": coerce_string(getattr(assigned_to_user, "email", None)),
        "assigned_by": assigned_by,
        "assigned_by_name": coerce_string(getattr(assigned_by_user, "full_name", None)),
        "assigned_by_email": coerce_string(getattr(assigned_by_user, "email", None)),
        "created_at": event.created_at,
    }


# ── DB loaders ───────────────────────────────────────────────────────────────


async def load_comment_for_org(
    db: AsyncSession,
    *,
    comment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Comment:
    result = await db.execute(
        select(Comment)
        .join(Analysis, Comment.analysis_id == Analysis.id)
        .where(
            Comment.id == comment_id,
            Analysis.org_id == org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise APIError(404, "Not Found", "Comment not found")
    return comment


async def load_assignable_reviewer(
    db: AsyncSession,
    *,
    reviewer_id: uuid.UUID,
    org_id: uuid.UUID,
) -> User:
    result = await db.execute(select(User).where(User.id == reviewer_id, User.org_id == org_id))
    reviewer = result.scalar_one_or_none()
    if reviewer is None:
        raise APIError(404, "Not Found", "Reviewer not found")
    if reviewer.role not in REVIEWER_ROLES:
        raise APIError(403, "Forbidden", "Comments can only be assigned to attorneys or admins")
    return reviewer


async def load_reviewer_lookup(
    db: AsyncSession,
    *,
    comments: list[Comment],
    org_id: uuid.UUID,
) -> dict[uuid.UUID, User]:
    reviewer_ids = {
        assigned_to
        for comment in comments
        if (assigned_to := coerce_uuid(getattr(comment, "assigned_to", None))) is not None
    }
    if not reviewer_ids:
        return {}

    result = await db.execute(select(User).where(User.org_id == org_id, User.id.in_(reviewer_ids)))
    reviewers = result.scalars().all()
    return {reviewer.id: reviewer for reviewer in reviewers}


async def load_users_by_ids(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_ids: set[uuid.UUID],
) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}

    result = await db.execute(select(User).where(User.org_id == org_id, User.id.in_(user_ids)))
    users = result.scalars().all()
    return {user.id: user for user in users}


async def load_assignment_events(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[CommentAssignmentEvent]:
    result = await db.execute(
        select(CommentAssignmentEvent)
        .where(
            CommentAssignmentEvent.analysis_id == analysis_id,
            CommentAssignmentEvent.org_id == org_id,
        )
        .order_by(CommentAssignmentEvent.created_at)
    )
    return list(result.scalars().all())


async def load_thread_escalation(
    db: AsyncSession,
    *,
    comment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> CommentThreadEscalation | None:
    result = await db.execute(
        select(CommentThreadEscalation).where(
            CommentThreadEscalation.comment_id == comment_id,
            CommentThreadEscalation.org_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def load_thread_escalations(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[CommentThreadEscalation]:
    result = await db.execute(
        select(CommentThreadEscalation).where(
            CommentThreadEscalation.analysis_id == analysis_id,
            CommentThreadEscalation.org_id == org_id,
        )
    )
    return list(result.scalars().all())


async def load_thread_escalations_for_comments(
    db: AsyncSession,
    *,
    comment_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> list[CommentThreadEscalation]:
    if not comment_ids:
        return []

    result = await db.execute(
        select(CommentThreadEscalation).where(
            CommentThreadEscalation.comment_id.in_(comment_ids),
            CommentThreadEscalation.org_id == org_id,
        )
    )
    return list(result.scalars().all())


async def load_comment_assignment_events(
    db: AsyncSession,
    *,
    comment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[CommentAssignmentEvent]:
    result = await db.execute(
        select(CommentAssignmentEvent)
        .where(
            CommentAssignmentEvent.comment_id == comment_id,
            CommentAssignmentEvent.org_id == org_id,
        )
        .order_by(CommentAssignmentEvent.created_at)
    )
    return list(result.scalars().all())


async def load_comment_assignment_events_for_comments(
    db: AsyncSession,
    *,
    comment_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> list[CommentAssignmentEvent]:
    if not comment_ids:
        return []

    result = await db.execute(
        select(CommentAssignmentEvent)
        .where(
            CommentAssignmentEvent.comment_id.in_(comment_ids),
            CommentAssignmentEvent.org_id == org_id,
        )
        .order_by(CommentAssignmentEvent.created_at)
    )
    return list(result.scalars().all())


async def assert_analysis_in_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Verify a comment's analysis belongs to the caller's org."""
    result = await db.execute(
        select(Analysis.id).where(
            Analysis.id == analysis_id,
            Analysis.org_id == org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
    )
    if not result.scalar_one_or_none():
        raise APIError(404, "Not Found", "Analysis not found")


async def list_comments_for_analysis(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[Comment]:
    result = await db.execute(
        select(Comment)
        .join(Analysis, Comment.analysis_id == Analysis.id)
        .where(
            Comment.analysis_id == analysis_id,
            Analysis.org_id == org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
        .order_by(Comment.created_at)
    )
    return list(result.scalars().all())


async def list_org_review_queue_rows(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> list[tuple[Comment, Analysis]]:
    result = await db.execute(
        select(Comment, Analysis)
        .join(Analysis, Comment.analysis_id == Analysis.id)
        .where(
            Analysis.org_id == org_id,
            Analysis.status != AnalysisStatus.DELETED,
            Comment.parent_id.is_(None),
            Comment.resolved.is_(False),
        )
        .order_by(Comment.created_at, Comment.id)
    )
    return [(comment, analysis) for comment, analysis in result.tuples().all()]


async def load_reply_counts_for_comments(
    db: AsyncSession,
    *,
    comment_ids: set[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not comment_ids:
        return {}
    result = await db.execute(select(Comment.parent_id).where(Comment.parent_id.in_(comment_ids)))
    counts: dict[uuid.UUID, int] = {}
    for parent_id in result.scalars():
        if parent_id is not None:
            counts[parent_id] = counts.get(parent_id, 0) + 1
    return counts


async def list_assignable_reviewers(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.org_id == org_id, User.role.in_(REVIEWER_ROLES))
        .order_by(User.full_name, User.email)
    )
    return list(result.scalars().all())


async def load_thread_assignment_history(
    db: AsyncSession,
    *,
    comment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[Comment, list[Comment], list[CommentAssignmentEvent]]:
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
    events = await load_comment_assignment_events(db, comment_id=root_id, org_id=org_id)
    return root_comment, comments, events
