"""Assignment logic and higher-level service functions for comments.

This module handles comment assignment state, audit details, notifications, and
the service functions that compose assignment and review-queue views. It is not
intended to be imported directly by route handlers; use the
:mod:`api.services.comments` facade instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Comment, Notification, NotificationType, User
from api.db.models_collaboration import CommentAssignmentEvent
from api.services.comments_crud import (
    assert_analysis_in_org,
    coerce_datetime,
    coerce_uuid,
    comment_root_id,
    list_comments_for_analysis,
    list_org_review_queue_rows,
    load_assignment_events,
    load_comment_assignment_events,
    load_comment_assignment_events_for_comments,
    load_reply_counts_for_comments,
    load_reviewer_lookup,
    load_thread_assignment_history,
    load_thread_escalations,
    load_thread_escalations_for_comments,
    load_users_by_ids,
    serialize_assignment_history_event,
    serialize_comment,
    serialize_review_queue_item,
)
from api.services.comments_escalation import (
    build_thread_metadata,
    is_explicitly_escalated,
)

# ── Mutation helpers ──────────────────────────────────────────────────────────


def apply_resolution_change(comment: Comment, *, resolved: bool, user_id: uuid.UUID) -> None:
    """Mutate the comment row for a resolution toggle."""
    comment.resolved = resolved
    comment.resolved_by = user_id if resolved else None
    comment.resolved_at = datetime.now(UTC) if resolved else None


def derive_assignment_event_type(
    *,
    reviewer: User | None,
    current_assigned_to: uuid.UUID | None,
) -> str:
    if reviewer is None:
        return "unassigned"
    if current_assigned_to is None:
        return "assigned"
    return "reassigned"


def apply_assignment_change(
    comment: Comment,
    *,
    reviewer: User | None,
    actor_id: uuid.UUID,
) -> tuple[uuid.UUID | None, datetime | None]:
    """Mutate the comment row to reflect a new assignment state.

    Returns ``(target_assigned_to, assigned_at)``.
    """
    target_assigned_to = reviewer.id if reviewer is not None else None
    assigned_at = datetime.now(UTC) if reviewer is not None else None
    comment.assigned_to = target_assigned_to
    comment.assigned_by = actor_id if reviewer is not None else None
    comment.assigned_at = assigned_at
    return target_assigned_to, assigned_at


def build_assignment_event(
    *,
    comment: Comment,
    target_assigned_to: uuid.UUID | None,
    actor_id: uuid.UUID,
    event_type: str,
    org_id: uuid.UUID,
    has_reviewer: bool,
) -> CommentAssignmentEvent:
    """Construct the CommentAssignmentEvent ORM row for an assignment change."""
    return CommentAssignmentEvent(
        comment_id=comment.id,
        analysis_id=comment.analysis_id,
        org_id=org_id,
        assigned_to=target_assigned_to,
        assigned_by=actor_id if has_reviewer else None,
        event_type=event_type,
    )


def build_assignment_notification(
    *,
    comment: Comment,
    reviewer: User,
    actor: User,
    assigned_at: datetime | None,
    org_id: uuid.UUID,
) -> Notification:
    """Construct the Notification row sent to the assignee."""
    assigner_name = actor.full_name or actor.email or "A team member"
    return Notification(
        user_id=reviewer.id,
        org_id=org_id,
        type=NotificationType.SYSTEM,
        title="Comment assigned for review",
        body=f"{assigner_name} assigned a comment for review.",
        data={
            "kind": "comment_assignment",
            "comment_id": str(comment.id),
            "analysis_id": str(comment.analysis_id),
            "target_type": comment.target_type,
            "target_id": comment.target_id,
            "assigned_to": str(reviewer.id),
            "assigned_by": str(actor.id),
            "assigned_by_name": assigner_name,
            "assigned_at": assigned_at.isoformat() if assigned_at else None,
        },
    )


# ── Audit detail builders ─────────────────────────────────────────────────────


def build_resolution_audit_details(
    comment: Comment, *, body_resolved: bool, user_id: uuid.UUID
) -> dict:
    return {
        "comment_id": str(comment.id),
        "resolved": body_resolved,
        "resolved_by": str(user_id) if body_resolved else None,
        "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
    }


def build_assignment_audit_details(comment: Comment, *, event_type: str) -> dict:
    return {
        "comment_id": str(comment.id),
        "assigned_to": str(comment.assigned_to) if comment.assigned_to else None,
        "assigned_by": str(comment.assigned_by) if comment.assigned_by else None,
        "assigned_at": comment.assigned_at.isoformat() if comment.assigned_at else None,
        "assignment_event_type": event_type,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
    }


# ── Higher-level service functions ────────────────────────────────────────────


async def build_assignment_response(
    db: AsyncSession,
    *,
    comment: Comment,
    reviewer: User | None,
    org_id: uuid.UUID,
) -> dict:
    """Build the response after an assignment update (or no-op)."""
    reviewer_lookup = {reviewer.id: reviewer} if reviewer is not None else {}
    assignment_events = await load_comment_assignment_events(
        db, comment_id=comment.id, org_id=org_id
    )
    thread_metadata = build_thread_metadata(
        root_comment=comment,
        events=assignment_events,
        escalation=None,
        now=datetime.now(UTC),
    )
    return serialize_comment(
        comment, reviewer_lookup=reviewer_lookup, thread_metadata=thread_metadata
    )


async def build_resolved_comment_response(
    db: AsyncSession,
    *,
    comment: Comment,
    org_id: uuid.UUID,
) -> dict:
    """Re-load thread + reviewer state and produce the response after a
    resolution change.
    """
    root_comment, thread_comments, assignment_events = await load_thread_assignment_history(
        db, comment_id=comment.id, org_id=org_id
    )
    reviewer_lookup = await load_reviewer_lookup(db, comments=thread_comments, org_id=org_id)
    thread_metadata = build_thread_metadata(
        root_comment=root_comment,
        events=assignment_events,
        escalation=None,
        now=datetime.now(UTC),
    )
    return serialize_comment(
        comment,
        reviewer_lookup=reviewer_lookup,
        thread_metadata=thread_metadata,
    )


async def build_assignment_history_response(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    comment_id: uuid.UUID,
) -> dict:
    """Build the assignment history payload for a comment thread."""
    root_comment, _comments, events = await load_thread_assignment_history(
        db, comment_id=comment_id, org_id=org_id
    )
    user_ids = {
        u
        for event in events
        for u in (
            coerce_uuid(getattr(event, "assigned_to", None)),
            coerce_uuid(getattr(event, "assigned_by", None)),
        )
        if u is not None
    }
    root_assigned_to = coerce_uuid(getattr(root_comment, "assigned_to", None))
    root_assigned_by = coerce_uuid(getattr(root_comment, "assigned_by", None))
    if root_assigned_to is not None:
        user_ids.add(root_assigned_to)
    if root_assigned_by is not None:
        user_ids.add(root_assigned_by)
    user_lookup = await load_users_by_ids(db, org_id=org_id, user_ids=user_ids)

    history_events = [
        serialize_assignment_history_event(event, user_lookup=user_lookup) for event in events
    ]
    if not history_events and root_assigned_to is not None:
        legacy_assigned_at = coerce_datetime(
            getattr(root_comment, "assigned_at", None)
        ) or coerce_datetime(getattr(root_comment, "created_at", None))
        assigned_to_user = user_lookup.get(root_assigned_to)
        assigned_by_user = user_lookup.get(root_assigned_by) if root_assigned_by else None
        history_events = [
            {
                "id": uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"legacy-comment-assignment:{root_comment.id}",
                ),
                "comment_id": root_comment.id,
                "analysis_id": root_comment.analysis_id,
                "event_type": "assigned",
                "assigned_to": root_assigned_to,
                "assigned_to_name": getattr(assigned_to_user, "full_name", None),
                "assigned_to_email": getattr(assigned_to_user, "email", None),
                "assigned_by": root_assigned_by,
                "assigned_by_name": getattr(assigned_by_user, "full_name", None),
                "assigned_by_email": getattr(assigned_by_user, "email", None),
                "created_at": legacy_assigned_at,
            }
        ]
    last_assignment_at = max(
        (
            event["created_at"]
            for event in history_events
            if isinstance(event.get("created_at"), datetime)
        ),
        default=None,
    )
    return {
        "comment_id": comment_id,
        "thread_root_comment_id": root_comment.id,
        "analysis_id": root_comment.analysis_id,
        "assignment_event_count": len(history_events),
        "last_assignment_at": last_assignment_at,
        "events": history_events,
    }


async def build_listed_comments(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    analysis_id: uuid.UUID,
    assigned_to: uuid.UUID | None,
    assignment_state: str,
    include_resolved: bool,
) -> list[dict]:
    """List comments for an analysis with thread metadata + filters applied."""
    await assert_analysis_in_org(db, analysis_id=analysis_id, org_id=org_id)

    comments = await list_comments_for_analysis(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    if not comments:
        return []

    assignment_events = await load_assignment_events(db, analysis_id=analysis_id, org_id=org_id)
    escalations = await load_thread_escalations(db, analysis_id=analysis_id, org_id=org_id)
    reviewer_lookup = await load_reviewer_lookup(db, comments=comments, org_id=org_id)

    comment_lookup = {comment.id: comment for comment in comments}
    root_cache: dict[uuid.UUID, uuid.UUID] = {}
    root_comments = {
        comment.id: comment
        for comment in comments
        if comment_root_id(comment, comment_lookup, root_cache) == comment.id
    }
    escalation_lookup = {escalation.comment_id: escalation for escalation in escalations}
    events_by_comment_id: dict[uuid.UUID, list[CommentAssignmentEvent]] = {}
    for event in assignment_events:
        events_by_comment_id.setdefault(event.comment_id, []).append(event)

    now = datetime.now(UTC)
    thread_metadata_by_root_id = {
        root_id: build_thread_metadata(
            root_comment=root_comment,
            events=events_by_comment_id.get(root_id, []),
            escalation=escalation_lookup.get(root_id),
            now=now,
        )
        for root_id, root_comment in root_comments.items()
    }
    escalation_user_ids = {
        u
        for escalation in escalations
        for u in (coerce_uuid(getattr(escalation, "escalated_by", None)),)
        if u is not None
    }
    escalation_user_lookup = await load_users_by_ids(
        db, org_id=org_id, user_ids=escalation_user_ids
    )
    for root_id, thread_metadata in thread_metadata_by_root_id.items():
        escalation = escalation_lookup.get(root_id)
        if escalation is not None:
            escalated_by = coerce_uuid(getattr(escalation, "escalated_by", None))
            escalated_user = escalation_user_lookup.get(escalated_by) if escalated_by else None
            thread_metadata["escalated_by_name"] = (
                escalated_user.full_name if escalated_user else None
            )
            thread_metadata["escalated_by_email"] = escalated_user.email if escalated_user else None

    selected_root_ids: set[uuid.UUID] = set()
    for root_id, root_comment in root_comments.items():
        thread_metadata = thread_metadata_by_root_id[root_id]
        root_assigned_to = coerce_uuid(getattr(root_comment, "assigned_to", None))
        if not include_resolved and bool(getattr(root_comment, "resolved", False)):
            continue
        if assigned_to is not None and root_assigned_to != assigned_to:
            continue
        if assignment_state == "assigned" and root_assigned_to is None:
            continue
        if assignment_state == "unassigned" and root_assigned_to is not None:
            continue
        if assignment_state == "overdue" and not thread_metadata["is_overdue"]:
            continue
        if assignment_state == "mine" and root_assigned_to != user_id:
            continue
        selected_root_ids.add(root_id)

    if not selected_root_ids:
        return []

    return [
        serialize_comment(
            comment,
            reviewer_lookup=reviewer_lookup,
            thread_metadata=thread_metadata_by_root_id.get(
                comment_root_id(comment, comment_lookup, root_cache)
            ),
        )
        for comment in comments
        if comment_root_id(comment, comment_lookup, root_cache) in selected_root_ids
    ]


async def build_review_queue_response(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    queue_filter: str,
) -> dict:
    """Build the org-level review queue payload (counts + filtered items)."""
    rows = await list_org_review_queue_rows(db, org_id=org_id)
    if not rows:
        return {
            "counts": {
                "open_total": 0,
                "mine": 0,
                "assigned": 0,
                "unassigned": 0,
                "overdue": 0,
                "escalated": 0,
            },
            "items": [],
        }

    comments = [comment for comment, _analysis in rows]
    analyses_by_id = {analysis.id: analysis for _comment, analysis in rows}
    comment_ids = {comment.id for comment in comments}

    assignment_events = await load_comment_assignment_events_for_comments(
        db, comment_ids=comment_ids, org_id=org_id
    )
    escalations = await load_thread_escalations_for_comments(
        db, comment_ids=comment_ids, org_id=org_id
    )
    user_ids = {
        u
        for comment in comments
        for u in (coerce_uuid(getattr(comment, "assigned_to", None)),)
        if u is not None
    }
    user_ids.update(
        u
        for escalation in escalations
        for u in (coerce_uuid(getattr(escalation, "escalated_by", None)),)
        if u is not None
    )
    reviewer_lookup = await load_users_by_ids(db, org_id=org_id, user_ids=user_ids)
    reply_counts = await load_reply_counts_for_comments(db, comment_ids=comment_ids)

    escalation_lookup = {escalation.comment_id: escalation for escalation in escalations}
    events_by_comment_id: dict[uuid.UUID, list[CommentAssignmentEvent]] = {}
    for event in assignment_events:
        events_by_comment_id.setdefault(event.comment_id, []).append(event)

    now = datetime.now(UTC)
    queue_entries: list[tuple[tuple[int, int, int, float], dict, dict]] = []
    counts = {
        "open_total": 0,
        "mine": 0,
        "assigned": 0,
        "unassigned": 0,
        "overdue": 0,
        "escalated": 0,
    }
    for comment in comments:
        analysis = analyses_by_id[comment.analysis_id]
        thread_metadata = build_thread_metadata(
            root_comment=comment,
            events=events_by_comment_id.get(comment.id, []),
            escalation=escalation_lookup.get(comment.id),
            now=now,
        )
        item = serialize_review_queue_item(
            comment,
            analysis=analysis,
            reviewer_lookup=reviewer_lookup,
            thread_metadata=thread_metadata,
        )
        item["is_mine"] = coerce_uuid(item.get("assigned_to")) == user_id
        item["reply_count"] = reply_counts.get(comment.id, 0)
        queue_entries.append(
            (
                (
                    0 if thread_metadata["is_overdue"] else 1,
                    0 if is_explicitly_escalated(thread_metadata) else 1,
                    -(thread_metadata["queue_age_hours"] or 0),
                    -comment.created_at.timestamp(),
                ),
                item,
                thread_metadata,
            )
        )
        counts["open_total"] += 1
        if coerce_uuid(getattr(comment, "assigned_to", None)) == user_id:
            counts["mine"] += 1
        if coerce_uuid(getattr(comment, "assigned_to", None)) is not None:
            counts["assigned"] += 1
        else:
            counts["unassigned"] += 1
        if thread_metadata["is_overdue"]:
            counts["overdue"] += 1
        if is_explicitly_escalated(thread_metadata):
            counts["escalated"] += 1

    def _matches_filter(item: dict, thread_metadata: dict) -> bool:
        item_assigned_to = coerce_uuid(item.get("assigned_to"))
        if queue_filter == "all":
            return True
        if queue_filter == "mine":
            return item_assigned_to == user_id
        if queue_filter == "unassigned":
            return item_assigned_to is None
        if queue_filter == "overdue":
            return bool(thread_metadata.get("is_overdue", False))
        return is_explicitly_escalated(thread_metadata)

    items = [
        item
        for _sort_key, item, thread_metadata in sorted(queue_entries, key=lambda entry: entry[0])
        if _matches_filter(item, thread_metadata)
    ]
    return {"counts": counts, "items": items}
