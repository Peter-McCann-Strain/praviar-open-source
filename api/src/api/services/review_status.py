"""Business logic for persisted report review workflow state."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError  # noqa: F401 — used in update/handoff impls
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    AnalysisReviewerDecision,
    AnalysisReviewStatus,
    AnalysisStatus,
    Comment,
    ReviewStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.schemas.review_handoff import (
    AnalysisReviewHandoffResponse,
    CreateAnalysisReviewHandoffRequest,
)
from api.schemas.review_status import (
    AnalysisReviewDecisionCounts,
    AnalysisReviewStatusResponse,
    ReviewStatusValue,
    UpdateAnalysisReviewStatusRequest,
)
from api.services.report_access import (
    filter_current_reviewer_decisions,
    require_completed_report_payload,
    reviewable_finding_keys,
    reviewer_decision_finding_key,
)
from api.services.reports import (
    build_export_readiness_blockers,
    load_export_reviewer_decisions,
)


def _publishable_review_status_report_data(analysis: Analysis) -> dict | None:
    try:
        return require_completed_report_payload(analysis)
    except APIError:
        return None


def _fallback_status(
    analysis: Analysis,
    *,
    findings_reviewed: int,
) -> ReviewStatus:
    if analysis.flagged_for_review or findings_reviewed > 0:
        return ReviewStatus.UNDER_REVIEW
    return ReviewStatus.PENDING


def _serialize_review_status(
    *,
    analysis: Analysis,
    review_status: AnalysisReviewStatus | None,
    decisions: list[AnalysisReviewerDecision],
) -> AnalysisReviewStatusResponse:
    decision_counts = AnalysisReviewDecisionCounts()
    report_data = _publishable_review_status_report_data(analysis)
    reviewable_findings = reviewable_finding_keys(report_data)
    current_decisions = filter_current_reviewer_decisions(report_data, decisions)
    reviewed_findings: set[tuple[str, str]] = set()

    for decision in current_decisions:
        finding_key = reviewer_decision_finding_key(decision)
        if decision.decision == "accept":
            decision_counts.accept += 1
        elif decision.decision == "reject":
            decision_counts.reject += 1
        elif decision.decision == "edit":
            decision_counts.edit += 1
        reviewed_findings.add(finding_key)

    findings_total = len(reviewable_findings)
    findings_reviewed = len(reviewed_findings) if findings_total else 0
    completion_pct = round((findings_reviewed / findings_total) * 100, 4) if findings_total else 0.0

    effective_status = (
        review_status.status
        if review_status
        else _fallback_status(
            analysis,
            findings_reviewed=len(reviewed_findings),
        )
    )
    if review_status and _review_status_value(review_status) == ReviewStatus.APPROVED.value:
        if report_data is None:
            effective_status = ReviewStatus.CHANGES_REQUESTED
        else:
            blockers = build_export_readiness_blockers(
                report_data=report_data,
                review_status={"status": ReviewStatus.APPROVED},
                reviewer_decisions=current_decisions,
            )
            if blockers:
                effective_status = ReviewStatus.CHANGES_REQUESTED
    updated_at = (
        (
            review_status.updated_at
            or review_status.reviewed_at
            or analysis.updated_at
            or analysis.created_at
            or datetime.now(UTC)
        )
        if review_status
        else (analysis.updated_at or analysis.created_at or datetime.now(UTC))
    )

    note = review_status.note.strip() if review_status and review_status.note else ""
    reviewer_name = (
        review_status.reviewer_name.strip() if review_status and review_status.reviewer_name else ""
    )
    reviewer_email = (
        review_status.reviewer_email.strip()
        if review_status and review_status.reviewer_email
        else ""
    )

    status_value: ReviewStatusValue = (
        effective_status.value
        if isinstance(effective_status, ReviewStatus)
        else str(effective_status)
    )

    return AnalysisReviewStatusResponse(
        analysis_id=analysis.id,
        status=status_value,
        note=note or None,
        reviewer_name=reviewer_name or None,
        reviewer_email=reviewer_email or None,
        reviewed_at=review_status.reviewed_at if review_status else None,
        updated_at=updated_at,
        decision_counts=decision_counts,
        findings_total=findings_total,
        findings_reviewed=findings_reviewed,
        completion_pct=completion_pct,
    )


async def _get_analysis_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Analysis:
    # Soft-deleted analyses must not surface through the review-status read/write
    # surface; mirror the exclusion enforced by analyses.get_analysis_for_org so
    # a deleted (GDPR-erased) analysis cannot be re-read or re-decisioned by id.
    statement = select(Analysis).where(
        Analysis.id == analysis_id,
        Analysis.org_id == org_id,
        Analysis.status != AnalysisStatus.DELETED,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise APIError(404, "Not Found", "Analysis not found")
    return analysis


async def _get_review_status_row(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> AnalysisReviewStatus | None:
    q = select(AnalysisReviewStatus).where(
        AnalysisReviewStatus.analysis_id == analysis_id,
        AnalysisReviewStatus.org_id == org_id,
    )
    if for_update:
        q = q.with_for_update()
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def _list_decisions(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[AnalysisReviewerDecision]:
    return await load_export_reviewer_decisions(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )


def _ensure_status_transition_allowed(*, user: User, requested_status: ReviewStatus) -> None:
    if requested_status == ReviewStatus.UNDER_REVIEW:
        return

    if user.role not in {UserRole.ADMIN, UserRole.ATTORNEY}:
        raise APIError(
            403,
            "Forbidden",
            "Only attorneys or admins can finalize or reset report review state",
        )


async def _ensure_approval_readiness(
    db: AsyncSession,
    *,
    analysis: Analysis,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    # Monitoring invalidations are a separate legal lifecycle from finding
    # coverage. A report cannot be re-approved while any affected conclusion
    # still lacks an attorney-attested disposition.
    from api.services.monitor_reassessment_lifecycle import (
        has_open_analysis_reassessments,
    )

    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Cannot approve report until the analysis has a completed report payload.",
    )
    reviewer_decisions = await load_export_reviewer_decisions(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    blockers = build_export_readiness_blockers(
        report_data=report_data,
        review_status={"status": ReviewStatus.APPROVED},
        reviewer_decisions=reviewer_decisions,
    )
    if blockers:
        raise APIError(
            409,
            "Conflict",
            "Cannot approve report until export readiness gates pass: " + " ".join(blockers),
        )
    if await has_open_analysis_reassessments(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    ):
        raise APIError(
            409,
            "Conflict",
            "Cannot approve report while monitoring-invalidated conclusions await "
            "attorney reassessment.",
        )


def _review_status_value(review_status: AnalysisReviewStatus) -> str:
    status = review_status.status
    return status.value if isinstance(status, ReviewStatus) else str(status)


async def invalidate_approved_review_status_if_export_blocked(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
) -> list[str]:
    """Downgrade stale approval when export readiness no longer holds."""
    analysis = await _get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        for_update=True,
    )
    # Acquire a row lock so this invalidation serializes with a concurrent
    # update_analysis_review_status_impl (which also locks for_update). Without
    # the lock, an approval and a decision-delete can interleave, leaving an
    # APPROVED status whose export-readiness no longer holds.
    review_status = await _get_review_status_row(
        db, analysis_id=analysis_id, org_id=org_id, for_update=True
    )
    if review_status is None or _review_status_value(review_status) != ReviewStatus.APPROVED.value:
        return []

    report_data = _publishable_review_status_report_data(analysis)
    if report_data is None:
        blockers = ["Analysis report payload is not publishable."]
    else:
        reviewer_decisions = await load_export_reviewer_decisions(
            db,
            analysis_id=analysis_id,
            org_id=org_id,
        )
        blockers = build_export_readiness_blockers(
            report_data=report_data,
            review_status={"status": ReviewStatus.APPROVED},
            reviewer_decisions=reviewer_decisions,
        )
    if not blockers:
        return []

    reviewed_at = datetime.now(UTC)
    review_status.status = ReviewStatus.CHANGES_REQUESTED
    review_status.note = (
        "Approval reverted because reviewer decision coverage changed after approval."
    )
    review_status.reviewer_user_id = user.clerk_user_id
    review_status.reviewer_name = user.full_name or ""
    review_status.reviewer_email = user.email or ""
    review_status.reviewed_at = reviewed_at
    analysis.flagged_for_review = True
    return blockers


async def invalidate_approved_review_status_for_decision_change(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
) -> bool:
    """Downgrade approval when reviewer decisions are changed after approval."""
    analysis = await _get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        for_update=True,
    )
    # Lock the status row so this invalidation serializes with a concurrent
    # update_analysis_review_status_impl approval (which also locks for_update),
    # mirroring the sibling delete-path invalidate_approved_review_status_if_export_blocked.
    # Without the lock, an approval committing after this read (READ COMMITTED) leaves an
    # APPROVED status that does not reflect the just-added/changed reviewer decision.
    review_status = await _get_review_status_row(
        db, analysis_id=analysis_id, org_id=org_id, for_update=True
    )
    if review_status is None or _review_status_value(review_status) != ReviewStatus.APPROVED.value:
        return False

    reviewed_at = datetime.now(UTC)
    review_status.status = ReviewStatus.CHANGES_REQUESTED
    review_status.note = "Approval reverted because reviewer decisions changed after approval."
    review_status.reviewer_user_id = user.clerk_user_id
    review_status.reviewer_name = user.full_name or ""
    review_status.reviewer_email = user.email or ""
    review_status.reviewed_at = reviewed_at
    analysis.flagged_for_review = True
    return True


async def get_analysis_review_status_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> AnalysisReviewStatusResponse:
    analysis = await _get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    review_status = await _get_review_status_row(db, analysis_id=analysis_id, org_id=org_id)
    decisions = await _list_decisions(db, analysis_id=analysis_id, org_id=org_id)
    return _serialize_review_status(
        analysis=analysis,
        review_status=review_status,
        decisions=decisions,
    )


async def update_analysis_review_status_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
    body: UpdateAnalysisReviewStatusRequest,
    request: Request | None = None,
) -> AnalysisReviewStatusResponse:
    analysis = await _get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        for_update=True,
    )
    requested_status = ReviewStatus(body.status)
    _ensure_status_transition_allowed(user=user, requested_status=requested_status)

    review_status = await _get_review_status_row(
        db, analysis_id=analysis_id, org_id=org_id, for_update=True
    )
    if requested_status == ReviewStatus.APPROVED:
        await _ensure_approval_readiness(
            db,
            analysis=analysis,
            analysis_id=analysis_id,
            org_id=org_id,
        )
    reviewed_at = datetime.now(UTC)
    normalized_note = body.note.strip()

    if review_status is None:
        review_status = AnalysisReviewStatus(
            analysis_id=analysis_id,
            org_id=org_id,
            status=requested_status,
            note=normalized_note,
            reviewer_user_id=user.clerk_user_id,
            reviewer_name=user.full_name or "",
            reviewer_email=user.email or "",
            reviewed_at=None if requested_status == ReviewStatus.PENDING else reviewed_at,
        )
        db.add(review_status)
        audit_action = "analysis_review_status.create"
    else:
        review_status.status = requested_status
        review_status.note = normalized_note
        review_status.reviewer_user_id = user.clerk_user_id
        review_status.reviewer_name = user.full_name or ""
        review_status.reviewer_email = user.email or ""
        review_status.reviewed_at = (
            None if requested_status == ReviewStatus.PENDING else reviewed_at
        )
        audit_action = "analysis_review_status.update"

    analysis.flagged_for_review = requested_status in {
        ReviewStatus.UNDER_REVIEW,
        ReviewStatus.CHANGES_REQUESTED,
    }

    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action=audit_action,
            details={
                "status": requested_status.value,
                "note_present": bool(normalized_note),
                "decision_role": user.role.value,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if audit_action == "analysis_review_status.update":
            raise
        raise APIError(
            409,
            "Conflict",
            "Review status was concurrently created. Please retry.",
        ) from exc
    except Exception:
        await db.rollback()
        raise

    decisions = await _list_decisions(db, analysis_id=analysis_id, org_id=org_id)
    return _serialize_review_status(
        analysis=analysis,
        review_status=review_status,
        decisions=decisions,
    )


def _normalize_review_handoff_note(
    body: CreateAnalysisReviewHandoffRequest,
) -> str:
    explicit_note = body.review_note.strip()
    if explicit_note:
        return explicit_note

    target_id = body.target_id.strip()
    target_label = body.target_type.replace("_", " ")
    if target_id:
        return f"Escalated from governed evidence handoff for {target_label} {target_id}."
    return "Escalated from governed evidence handoff."


async def create_analysis_review_handoff_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
    body: CreateAnalysisReviewHandoffRequest,
    request: Request | None = None,
    commit: bool = True,
) -> AnalysisReviewHandoffResponse:
    """Create a targeted review comment and escalate pending analyses into review."""
    analysis = await _get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        for_update=True,
    )
    review_status = await _get_review_status_row(
        db, analysis_id=analysis_id, org_id=org_id, for_update=True
    )

    comment = Comment(
        analysis_id=analysis_id,
        org_id=org_id,
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id.strip(),
        body=body.body.strip(),
        mentions=body.mentions,
    )
    db.add(comment)

    escalated_to_review = False
    if body.promote_to_under_review:
        reviewed_at = datetime.now(UTC)
        normalized_note = _normalize_review_handoff_note(body)
        current_status = review_status.status if review_status else None

        if current_status is None:
            review_status = AnalysisReviewStatus(
                analysis_id=analysis_id,
                org_id=org_id,
                status=ReviewStatus.UNDER_REVIEW,
                note=normalized_note,
                reviewer_user_id=user.clerk_user_id,
                reviewer_name=user.full_name or "",
                reviewer_email=user.email or "",
                reviewed_at=reviewed_at,
            )
            db.add(review_status)
            escalated_to_review = True
        elif review_status is not None and current_status == ReviewStatus.PENDING:
            review_status.status = ReviewStatus.UNDER_REVIEW
            review_status.note = normalized_note
            review_status.reviewer_user_id = user.clerk_user_id
            review_status.reviewer_name = user.full_name or ""
            review_status.reviewer_email = user.email or ""
            review_status.reviewed_at = reviewed_at
            escalated_to_review = True

        if escalated_to_review:
            analysis.flagged_for_review = True

    try:
        await db.flush()
        decisions = await _list_decisions(db, analysis_id=analysis_id, org_id=org_id)
        serialized_review_status = _serialize_review_status(
            analysis=analysis,
            review_status=review_status,
            decisions=decisions,
        )
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="analysis_review_handoff.create",
            details={
                "comment_id": str(comment.id),
                "target_type": body.target_type,
                "target_id": body.target_id.strip(),
                "promote_to_under_review": body.promote_to_under_review,
                "escalated_to_review": escalated_to_review,
            },
            request=request,
            fail_closed=True,
        )
        if commit:
            await db.commit()
    except IntegrityError as exc:
        if commit:
            await db.rollback()
        if not escalated_to_review:
            raise
        raise APIError(
            409,
            "Conflict",
            "Review status was concurrently created. Please retry.",
        ) from exc
    except Exception:
        if commit:
            await db.rollback()
        raise

    return AnalysisReviewHandoffResponse(
        comment_id=comment.id,
        created_at=comment.created_at,
        target_type=body.target_type,
        target_id=body.target_id.strip(),
        escalated_to_review=escalated_to_review,
        review_status=serialized_review_status,
    )
