"""Service-layer helpers for collaboration comments.

This module is a thin facade that re-exports the full public surface of the
comment service so that callers (primarily :mod:`api.routes.comments`) see an
unchanged import path. The implementation is split across three sub-modules:

- :mod:`api.services.comments_crud` -- coercion helpers, thread traversal,
  serialisation, and DB loaders.
- :mod:`api.services.comments_escalation` -- thread metadata, escalation
  records, and escalation view builders.
- :mod:`api.services.comments_assignment` -- assignment mutations, audit
  details, notifications, and higher-level list/queue builders.
"""

from __future__ import annotations

# Standard-library re-exports retained to preserve the public symbol set.
import uuid  # noqa: F401
from datetime import UTC, datetime  # noqa: F401
from typing import Literal  # noqa: F401

from sqlalchemy import select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from api.db.models import (  # noqa: F401
    Analysis,
    Comment,
    Notification,
    NotificationType,
    User,
    UserRole,
)
from api.db.models_collaboration import (  # noqa: F401
    CommentAssignmentEvent,
    CommentThreadEscalation,
)
from api.errors import APIError  # noqa: F401

# Re-export everything from comments_crud
from api.services.comments_assignment import (
    apply_assignment_change,
    apply_resolution_change,
    build_assignment_audit_details,
    build_assignment_event,
    build_assignment_history_response,
    build_assignment_notification,
    build_assignment_response,
    build_listed_comments,
    build_resolution_audit_details,
    build_resolved_comment_response,
    build_review_queue_response,
    derive_assignment_event_type,
)
from api.services.comments_crud import (
    ASSIGNER_ROLES,
    ASSIGNMENT_OVERDUE_ASSIGNED_HOURS,
    ASSIGNMENT_OVERDUE_UNASSIGNED_HOURS,
    REVIEW_QUEUE_ROLES,
    REVIEWER_ROLES,
    AssignmentState,
    ReviewQueueFilter,
    assert_analysis_in_org,
    coerce_datetime,
    coerce_string,
    coerce_string_value,
    coerce_uuid,
    comment_root_id,
    list_assignable_reviewers,
    list_comments_for_analysis,
    list_org_review_queue_rows,
    load_assignable_reviewer,
    load_assignment_events,
    load_comment_assignment_events,
    load_comment_assignment_events_for_comments,
    load_comment_for_org,
    load_reviewer_lookup,
    load_thread_assignment_history,
    load_thread_escalation,
    load_thread_escalations,
    load_thread_escalations_for_comments,
    load_users_by_ids,
    serialize_assignment_history_event,
    serialize_comment,
    serialize_review_queue_item,
    serialize_reviewer,
)
from api.services.comments_escalation import (
    build_escalation_audit_details,
    build_thread_metadata,
    build_thread_metadata_with_actor,
    create_thread_escalation_record,
    is_explicitly_escalated,
    load_existing_thread_escalation_view,
    serialize_existing_escalation,
)

__all__ = [
    # comments_crud
    "ASSIGNER_ROLES",
    "ASSIGNMENT_OVERDUE_ASSIGNED_HOURS",
    "ASSIGNMENT_OVERDUE_UNASSIGNED_HOURS",
    "AssignmentState",
    "REVIEWER_ROLES",
    "REVIEW_QUEUE_ROLES",
    "ReviewQueueFilter",
    "assert_analysis_in_org",
    "coerce_datetime",
    "coerce_string",
    "coerce_string_value",
    "coerce_uuid",
    "comment_root_id",
    "list_assignable_reviewers",
    "list_comments_for_analysis",
    "list_org_review_queue_rows",
    "load_assignable_reviewer",
    "load_assignment_events",
    "load_comment_assignment_events",
    "load_comment_assignment_events_for_comments",
    "load_comment_for_org",
    "load_reviewer_lookup",
    "load_thread_assignment_history",
    "load_thread_escalation",
    "load_thread_escalations",
    "load_thread_escalations_for_comments",
    "load_users_by_ids",
    "serialize_assignment_history_event",
    "serialize_comment",
    "serialize_review_queue_item",
    "serialize_reviewer",
    # comments_escalation
    "build_escalation_audit_details",
    "build_thread_metadata",
    "build_thread_metadata_with_actor",
    "create_thread_escalation_record",
    "is_explicitly_escalated",
    "load_existing_thread_escalation_view",
    "serialize_existing_escalation",
    # comments_assignment
    "apply_assignment_change",
    "apply_resolution_change",
    "build_assignment_audit_details",
    "build_assignment_event",
    "build_assignment_history_response",
    "build_assignment_notification",
    "build_assignment_response",
    "build_listed_comments",
    "build_resolution_audit_details",
    "build_resolved_comment_response",
    "build_review_queue_response",
    "derive_assignment_event_type",
]
