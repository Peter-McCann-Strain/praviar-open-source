"""Collaboration comments routes (thin layer delegating to ``services.comments``)."""

import uuid
from typing import Literal, cast

import structlog
from fastapi import APIRouter, Query, Request, status
from sqlalchemy.exc import IntegrityError  # noqa: F401 — used in escalate_comment_thread

from api.audit import write_audit_log
from api.db.models import Comment, UserRole
from api.deps import CurrentUser, DBSession
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.comments import (
    CommentAssignmentHistoryResponse,
    CommentCreatedResponse,
    CommentResponse,
    CommentReviewerResponse,
    CommentReviewQueueResponse,
    CreateCommentRequest,
    EscalateCommentThreadRequest,
    UpdateCommentAssignmentRequest,
    UpdateCommentResolutionRequest,
)
from api.schemas.review_handoff import CreateAnalysisReviewHandoffRequest
from api.services.comments import (
    ASSIGNER_ROLES,
    REVIEW_QUEUE_ROLES,
    AssignmentState,
    ReviewQueueFilter,
    apply_assignment_change,
    apply_resolution_change,
    assert_analysis_in_org,
    build_assignment_audit_details,
    build_assignment_event,
    build_assignment_history_response,
    build_assignment_notification,
    build_assignment_response,
    build_escalation_audit_details,
    build_listed_comments,
    build_resolution_audit_details,
    build_resolved_comment_response,
    build_review_queue_response,
    build_thread_metadata_with_actor,
    coerce_uuid,
    create_thread_escalation_record,
    derive_assignment_event_type,
    list_assignable_reviewers,
    load_assignable_reviewer,
    load_comment_for_org,
    load_existing_thread_escalation_view,
    load_reviewer_lookup,
    serialize_comment,
    serialize_existing_escalation,
    serialize_reviewer,
)
from api.services.review_status import create_analysis_review_handoff_impl

logger = structlog.get_logger()

router = APIRouter()
ReviewHandoffTargetType = Literal["analysis", "patent", "claim"]


@router.post(
    "/comments",
    response_model=CommentCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_comment(
    body: CreateCommentRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Create a comment on an analysis."""
    logger.info("create_comment", analysis_id=str(body.analysis_id), user_id=str(user.id))
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST):
        logger.warning("comment_forbidden", user_id=str(user.id), role=user.role.value)
        raise APIError(403, "Forbidden", "Cannot comment")

    await assert_analysis_in_org(db, analysis_id=body.analysis_id, org_id=user.org_id)
    target_type = body.target_type
    target_id = body.target_id
    if body.parent_id is not None:
        parent = await load_comment_for_org(db, comment_id=body.parent_id, org_id=user.org_id)
        if parent.analysis_id != body.analysis_id:
            raise APIError(
                422,
                "Validation Error",
                "Comment parent_id must belong to the same analysis.",
            )
        if parent.parent_id is not None:
            raise APIError(
                422,
                "Validation Error",
                "Replies can only target a top-level comment.",
            )
        # Replies inherit the thread's target so grouping stays consistent.
        target_type = cast(ReviewHandoffTargetType, parent.target_type)
        target_id = parent.target_id

    comment = Comment(
        analysis_id=body.analysis_id,
        org_id=user.org_id,
        user_id=user.id,
        parent_id=body.parent_id,
        target_type=target_type,
        target_id=target_id,
        body=body.body,
        mentions=body.mentions,
    )
    db.add(comment)
    await db.commit()

    return {"id": comment.id, "created_at": comment.created_at}


@router.get("/comments", response_model=list[CommentResponse])
async def list_comments(
    user: CurrentUser,
    db: DBSession,
    analysis_id: uuid.UUID = Query(...),  # noqa: B008
    assigned_to: uuid.UUID | None = Query(None),  # noqa: B008
    assignment_state: AssignmentState = Query("all"),  # noqa: B008
    include_resolved: bool = Query(True),  # noqa: B008
) -> list[dict]:
    """List comments for an analysis."""
    return await build_listed_comments(
        db,
        user_id=user.id,
        org_id=user.org_id,
        analysis_id=analysis_id,
        assigned_to=assigned_to,
        assignment_state=assignment_state,
        include_resolved=include_resolved,
    )


@router.get("/comments/review-queue", response_model=CommentReviewQueueResponse)
async def get_comment_review_queue(
    user: CurrentUser,
    db: DBSession,
    filter: ReviewQueueFilter = Query("all"),  # noqa: B008
) -> dict:
    """Return org-level review queue counts and open top-level threads."""
    if user.role not in REVIEW_QUEUE_ROLES:
        logger.warning("comment_review_queue_forbidden", user_id=str(user.id), role=user.role.value)
        raise APIError(
            403,
            "Forbidden",
            "Only attorneys, admins, or scientists can view the review queue",
        )

    return await build_review_queue_response(
        db,
        user_id=user.id,
        org_id=user.org_id,
        queue_filter=filter,
    )


@router.post("/comments/{comment_id}/escalation", response_model=CommentResponse)
@limiter.limit("30/minute")
async def escalate_comment_thread(
    comment_id: uuid.UUID,
    body: EscalateCommentThreadRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Escalate a top-level comment thread into the legal review flow."""
    if user.role not in ASSIGNER_ROLES:
        logger.warning("comment_escalation_forbidden", user_id=str(user.id), role=user.role.value)
        raise APIError(
            403, "Forbidden", "Only attorneys, admins, or scientists can escalate comments"
        )

    root_comment, comments, existing = await load_existing_thread_escalation_view(
        db, comment_id=comment_id, org_id=user.org_id
    )
    if existing is not None:
        return await serialize_existing_escalation(
            db,
            root_comment=root_comment,
            comments=comments,
            escalation=existing,
            org_id=user.org_id,
        )

    handoff_body = body.review_note.strip() or (
        f"Escalated comment thread for legal review: {root_comment.body[:160]}"
    )
    try:
        escalation_record = create_thread_escalation_record(
            root_comment=root_comment,
            org_id=user.org_id,
            actor_id=user.id,
            promote_to_under_review=body.promote_to_under_review,
        )
        db.add(escalation_record)

        handoff_target_type = root_comment.target_type
        if handoff_target_type not in {"analysis", "patent", "claim"}:
            handoff_target_type = "analysis"

        handoff_response = await create_analysis_review_handoff_impl(
            db,
            analysis_id=root_comment.analysis_id,
            org_id=user.org_id,
            user=user,
            body=CreateAnalysisReviewHandoffRequest(
                body=handoff_body,
                review_note=body.review_note,
                target_type=cast(ReviewHandoffTargetType, handoff_target_type),
                target_id=root_comment.target_id,
                mentions=[],
                promote_to_under_review=body.promote_to_under_review,
            ),
            request=request,
            commit=False,
        )
        escalation_record.review_handoff_comment_id = handoff_response.comment_id
        escalation_record.escalated_to_review = handoff_response.escalated_to_review

        reviewer_lookup = await load_reviewer_lookup(db, comments=comments, org_id=user.org_id)
        thread_metadata, _events = await build_thread_metadata_with_actor(
            db, root_comment=root_comment, escalation=escalation_record, org_id=user.org_id
        )
        if not thread_metadata.get("escalated_by_name"):
            thread_metadata["escalated_by_name"] = user.full_name
            thread_metadata["escalated_by_email"] = user.email

        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=root_comment.analysis_id,
            action="comment.thread_escalated",
            details=build_escalation_audit_details(
                root_comment=root_comment,
                user_id=user.id,
                thread_metadata=thread_metadata,
                handoff_response=handoff_response,
            ),
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        root_comment, comments, existing = await load_existing_thread_escalation_view(
            db, comment_id=comment_id, org_id=user.org_id
        )
        if existing is None:
            raise
        return await serialize_existing_escalation(
            db,
            root_comment=root_comment,
            comments=comments,
            escalation=existing,
            org_id=user.org_id,
        )
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "comment_thread_escalated",
        comment_id=str(root_comment.id),
        analysis_id=str(root_comment.analysis_id),
        escalated_by=str(user.id),
        escalated_to_review=handoff_response.escalated_to_review,
    )
    return serialize_comment(
        root_comment, reviewer_lookup=reviewer_lookup, thread_metadata=thread_metadata
    )


@router.get(
    "/comments/{comment_id}/assignment-history",
    response_model=CommentAssignmentHistoryResponse,
)
async def get_comment_assignment_history(
    comment_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Return thread-scoped assignment history for a comment."""
    if user.role not in ASSIGNER_ROLES:
        logger.warning(
            "comment_assignment_history_forbidden", user_id=str(user.id), role=user.role.value
        )
        raise APIError(
            403, "Forbidden", "Only attorneys, admins, or scientists can view assignment history"
        )

    return await build_assignment_history_response(db, org_id=user.org_id, comment_id=comment_id)


@router.get("/comments/reviewers", response_model=list[CommentReviewerResponse])
async def list_comment_reviewers(
    user: CurrentUser,
    db: DBSession,
    analysis_id: uuid.UUID = Query(...),  # noqa: B008
) -> list[dict]:
    """List assignable reviewers for an analysis in the current org."""
    if user.role not in ASSIGNER_ROLES:
        logger.warning(
            "comment_reviewer_list_forbidden", user_id=str(user.id), role=user.role.value
        )
        raise APIError(403, "Forbidden", "Only attorneys, admins, or scientists can view reviewers")

    await assert_analysis_in_org(db, analysis_id=analysis_id, org_id=user.org_id)
    reviewers = await list_assignable_reviewers(db, org_id=user.org_id)
    return [serialize_reviewer(reviewer) for reviewer in reviewers]


@router.patch("/comments/{comment_id}/resolution", response_model=CommentResponse)
@limiter.limit("30/minute")
async def update_comment_resolution(
    comment_id: uuid.UUID,
    body: UpdateCommentResolutionRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Toggle a comment's resolved state within the current org."""
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        logger.warning("comment_resolution_forbidden", user_id=str(user.id), role=user.role.value)
        raise APIError(403, "Forbidden", "Only attorneys or admins can resolve comments")

    comment = await load_comment_for_org(db, comment_id=comment_id, org_id=user.org_id)
    try:
        apply_resolution_change(comment, resolved=body.resolved, user_id=user.id)
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=comment.analysis_id,
            action="comment.resolution_updated",
            details=build_resolution_audit_details(
                comment, body_resolved=body.resolved, user_id=user.id
            ),
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("comment_resolution_updated", comment_id=str(comment.id))
    return await build_resolved_comment_response(db, comment=comment, org_id=user.org_id)


@router.patch("/comments/{comment_id}/assignment", response_model=CommentResponse)
@limiter.limit("30/minute")
async def update_comment_assignment(
    comment_id: uuid.UUID,
    body: UpdateCommentAssignmentRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Assign or unassign a comment within the current org."""
    if user.role not in ASSIGNER_ROLES:
        logger.warning("comment_assignment_forbidden", user_id=str(user.id), role=user.role.value)
        raise APIError(
            403, "Forbidden", "Only attorneys, admins, or scientists can assign comments"
        )

    comment = await load_comment_for_org(db, comment_id=comment_id, org_id=user.org_id)
    if comment.parent_id is not None:
        raise APIError(400, "Bad Request", "Only top-level comments can be assigned")

    current_assigned_to = coerce_uuid(getattr(comment, "assigned_to", None))

    reviewer = None
    if body.assigned_to is not None:
        reviewer = await load_assignable_reviewer(
            db, reviewer_id=body.assigned_to, org_id=user.org_id
        )

    target_assigned_to = reviewer.id if reviewer is not None else None
    if current_assigned_to == target_assigned_to:
        return await build_assignment_response(
            db, comment=comment, reviewer=reviewer, org_id=user.org_id
        )

    try:
        target_assigned_to, assigned_at = apply_assignment_change(
            comment, reviewer=reviewer, actor_id=user.id
        )
        event_type = derive_assignment_event_type(
            reviewer=reviewer, current_assigned_to=current_assigned_to
        )

        db.add(
            build_assignment_event(
                comment=comment,
                target_assigned_to=target_assigned_to,
                actor_id=user.id,
                event_type=event_type,
                org_id=user.org_id,
                has_reviewer=reviewer is not None,
            )
        )

        if reviewer is not None and reviewer.id != user.id:
            db.add(
                build_assignment_notification(
                    comment=comment,
                    reviewer=reviewer,
                    actor=user,
                    assigned_at=assigned_at,
                    org_id=user.org_id,
                )
            )

        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=comment.analysis_id,
            action="comment.assignment_updated",
            details=build_assignment_audit_details(comment, event_type=event_type),
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("comment_assignment_updated", comment_id=str(comment.id))
    return await build_assignment_response(
        db, comment=comment, reviewer=reviewer, org_id=user.org_id
    )
