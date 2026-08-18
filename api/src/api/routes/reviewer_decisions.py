"""Reviewer accept / reject / edit decision routes.

Captures per-finding decisions that an attorney makes while reviewing an FTO
report. The decisions are scoped to a single analysis and to the reviewer's
organization. A reviewer may have at most one decision per
(analysis, finding_type, finding_ref) — re-POST upserts.
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response, status

from api.audit import write_audit_log
from api.db.models import AnalysisReviewerDecision, User
from api.deps import DBSession, require_permission
from api.ratelimit import limiter
from api.schemas.reviewer_decisions import (
    ReviewerDecisionIn,
    ReviewerDecisionListResponse,
    ReviewerDecisionOut,
)
from api.services.review_status import (
    invalidate_approved_review_status_for_decision_change,
    invalidate_approved_review_status_if_export_blocked,
)
from api.services.reviewer_decisions import (
    assert_analysis_in_org,
    assert_can_delete_decision,
    assert_decision_targets_current_finding,
    fetch_decision_for_delete,
    list_reviewer_decisions,
    upsert_reviewer_decision,
)

logger = structlog.get_logger()

router = APIRouter()


@router.post(
    "/analyses/{analysis_id}/decisions",
    response_model=ReviewerDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def create_decision(
    analysis_id: uuid.UUID,
    body: ReviewerDecisionIn,
    user: Annotated[User, Depends(require_permission("reviewer_decision.create"))],
    db: DBSession,
    request: Request,
) -> AnalysisReviewerDecision:
    """Upsert a reviewer decision for a finding on this analysis.

    The unique key is (analysis_id, finding_type, finding_ref, reviewer_user_id).
    Re-POST by the same reviewer on the same finding replaces the prior row.
    """
    analysis = await assert_analysis_in_org(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        for_update=True,
    )
    report_fingerprint = assert_decision_targets_current_finding(analysis, body)

    try:
        decision_obj, audit_action = await upsert_reviewer_decision(
            db,
            analysis_id=analysis_id,
            user=user,
            body=body,
            report_fingerprint=report_fingerprint,
        )

        await db.flush()
        approval_invalidated = await invalidate_approved_review_status_for_decision_change(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            user=user,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action=audit_action,
            details={
                "finding_type": body.finding_type,
                "finding_ref": body.finding_ref,
                "decision": body.decision,
                "report_fingerprint": report_fingerprint,
                "rationale_present": bool(body.note.strip()),
                "edited_text_present": bool(body.edited_text.strip()),
                "approval_invalidated": approval_invalidated,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "reviewer_decision_saved",
        analysis_id=str(analysis_id),
        finding_type=body.finding_type,
        decision=body.decision,
        reviewer_user_id=user.clerk_user_id,
    )
    return decision_obj


@router.get(
    "/analyses/{analysis_id}/decisions",
    response_model=ReviewerDecisionListResponse,
)
async def list_decisions(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("reviewer_decision.view"))],
    db: DBSession,
) -> ReviewerDecisionListResponse:
    """List all reviewer decisions for this analysis, org-scoped."""
    analysis = await assert_analysis_in_org(db, analysis_id=analysis_id, org_id=user.org_id)

    rows, counts = await list_reviewer_decisions(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        report_data=analysis.report_data,
        viewer_user_id=user.clerk_user_id,
    )
    return ReviewerDecisionListResponse(
        items=[ReviewerDecisionOut.model_validate(r) for r in rows],
        counts=counts,
    )


@router.delete(
    "/analyses/{analysis_id}/decisions/{decision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_decision(
    analysis_id: uuid.UUID,
    decision_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("reviewer_decision.create"))],
    db: DBSession,
    request: Request,
) -> Response:
    """Delete a reviewer decision.

    Only the current attorney reviewer who authored it, or an org admin, may delete.
    """
    await assert_analysis_in_org(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        for_update=True,
    )

    decision_obj = await fetch_decision_for_delete(
        db,
        decision_id=decision_id,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    assert_can_delete_decision(decision_obj, user=user)

    try:
        await db.delete(decision_obj)
        await db.flush()
        approval_blockers = await invalidate_approved_review_status_if_export_blocked(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            user=user,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="reviewer_decision.delete",
            details={
                "decision_id": str(decision_id),
                "approval_invalidated": bool(approval_blockers),
                "approval_blockers": approval_blockers,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
