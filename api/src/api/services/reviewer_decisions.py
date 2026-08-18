"""Service layer for reviewer accept/reject/edit decisions on FTO findings."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import (
    Analysis,
    AnalysisReviewerDecision,
    AnalysisStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.schemas.reviewer_decisions import ReviewerDecisionIn
from api.services.report_access import (
    filter_current_reviewer_decisions,
    report_payload_fingerprint,
    require_completed_report_payload,
    reviewable_finding_keys,
)


async def assert_analysis_in_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Analysis:
    """Return the analysis row if it belongs to the caller's org; else raise 404.

    We deliberately return 404 (not 403) for cross-org access so existence is
    not leaked.
    """
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


def assert_decision_targets_current_finding(
    analysis: Analysis,
    body: ReviewerDecisionIn,
) -> str:
    """Reject decisions for stale or unknown report findings."""
    finding_ref = body.finding_ref.strip()
    if finding_ref != body.finding_ref:
        raise APIError(
            422,
            "Validation Error",
            "Reviewer decision finding_ref must match a current report finding exactly.",
        )

    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail=(
            "Cannot record reviewer decisions until the analysis has a completed "
            "publishable report payload."
        ),
    )
    if (body.finding_type, finding_ref) not in reviewable_finding_keys(report_data):
        raise APIError(
            422,
            "Validation Error",
            "Reviewer decision finding_ref is not present in the current report findings.",
        )
    if (
        body.decision == "accept"
        and not body.note.strip()
        and body.finding_type == "patent"
        and finding_ref in _high_risk_patent_refs(report_data)
    ):
        raise APIError(
            422,
            "Validation Error",
            "A rationale note is required when accepting a HIGH-risk finding.",
        )
    return report_payload_fingerprint(report_data)


def _high_risk_patent_refs(report_data: Mapping[str, Any]) -> set[str]:
    raw_candidates = (
        report_data.get("patent_analyses")
        or report_data.get("patents")
        or report_data.get("analyses")
        or []
    )
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    refs: set[str] = set()
    for entry in candidates:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("risk_level") or "").strip().lower() != "high":
            continue
        finding_ref = str(
            entry.get("patent_id")
            or entry.get("id")
            or entry.get("publication_number")
            or entry.get("patent_number")
            or ""
        ).strip()
        if finding_ref:
            refs.add(finding_ref)
    return refs


async def find_existing_decision(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    finding_type: str,
    finding_ref: str,
    reviewer_user_id: str,
) -> AnalysisReviewerDecision | None:
    """Look up a reviewer decision by its natural key."""
    result = await db.execute(
        select(AnalysisReviewerDecision)
        .where(
            AnalysisReviewerDecision.analysis_id == analysis_id,
            AnalysisReviewerDecision.org_id == org_id,
            AnalysisReviewerDecision.finding_type == finding_type,
            AnalysisReviewerDecision.finding_ref == finding_ref,
            AnalysisReviewerDecision.reviewer_user_id == reviewer_user_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def upsert_reviewer_decision(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    user: User,
    body: ReviewerDecisionIn,
    report_fingerprint: str,
) -> tuple[AnalysisReviewerDecision, str]:
    """Insert or update a reviewer decision.

    Returns the persisted ORM row plus the audit action string indicating
    whether this was a create or an update.
    """
    existing = await find_existing_decision(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        finding_type=body.finding_type,
        finding_ref=body.finding_ref,
        reviewer_user_id=user.clerk_user_id,
    )

    if existing is not None:
        existing.decision = body.decision
        existing.note = body.note
        existing.edited_text = body.edited_text
        existing.report_fingerprint = report_fingerprint
        existing.reviewer_name = user.full_name or ""
        existing.reviewer_email = user.email or ""
        return existing, "reviewer_decision.update"

    decision_obj = AnalysisReviewerDecision(
        analysis_id=analysis_id,
        org_id=user.org_id,
        finding_type=body.finding_type,
        finding_ref=body.finding_ref,
        report_fingerprint=report_fingerprint,
        decision=body.decision,
        note=body.note,
        edited_text=body.edited_text,
        reviewer_user_id=user.clerk_user_id,
        reviewer_name=user.full_name or "",
        reviewer_email=user.email or "",
    )
    db.add(decision_obj)
    await db.flush()
    return decision_obj, "reviewer_decision.create"


async def list_reviewer_decisions(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    report_data: Mapping[str, Any] | None = None,
    viewer_user_id: str | None = None,
) -> tuple[list[AnalysisReviewerDecision], dict[str, int]]:
    """Return all reviewer decisions for an analysis with per-decision counts."""
    result = await db.execute(
        select(AnalysisReviewerDecision)
        .join(User, User.clerk_user_id == AnalysisReviewerDecision.reviewer_user_id)
        .where(
            AnalysisReviewerDecision.analysis_id == analysis_id,
            AnalysisReviewerDecision.org_id == org_id,
            User.org_id == org_id,
            User.role.in_((UserRole.ADMIN, UserRole.ATTORNEY)),
            User.membership_active.is_(True),
            User.membership_deleted_at.is_(None),
            User.membership_permission_denied_at.is_(None),
        )
        .order_by(AnalysisReviewerDecision.created_at)
    )
    rows = list(result.scalars().all())
    if report_data is not None:
        rows = cast(
            list[AnalysisReviewerDecision],
            filter_current_reviewer_decisions(report_data, rows),
        )
        if viewer_user_id:
            high_risk_refs = _high_risk_patent_refs(report_data)
            rows_by_ref = {
                finding_ref: [
                    row
                    for row in rows
                    if row.finding_type == "patent" and row.finding_ref == finding_ref
                ]
                for finding_ref in high_risk_refs
            }
            concealed_refs = {
                finding_ref
                for finding_ref, finding_rows in rows_by_ref.items()
                if len({row.reviewer_user_id for row in finding_rows}) < 2
                and all(row.reviewer_user_id != viewer_user_id for row in finding_rows)
            }
            rows = [
                row
                for row in rows
                if not (row.finding_type == "patent" and row.finding_ref in concealed_refs)
            ]

    counts: dict[str, int] = {"accept": 0, "reject": 0, "edit": 0}
    for row in rows:
        counts[row.decision] = counts.get(row.decision, 0) + 1
    return rows, counts


async def fetch_decision_for_delete(
    db: AsyncSession,
    *,
    decision_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> AnalysisReviewerDecision:
    """Load a decision row scoped to (analysis, org) or raise 404."""
    result = await db.execute(
        select(AnalysisReviewerDecision).where(
            AnalysisReviewerDecision.id == decision_id,
            AnalysisReviewerDecision.analysis_id == analysis_id,
            AnalysisReviewerDecision.org_id == org_id,
        )
    )
    decision_obj = result.scalar_one_or_none()
    if decision_obj is None:
        raise APIError(404, "Not Found", "Decision not found")
    return decision_obj


def assert_can_delete_decision(decision: AnalysisReviewerDecision, *, user: User) -> None:
    """Raise 403 unless current legal-review authority permits deletion."""
    has_review_authority = user.role in {UserRole.ADMIN, UserRole.ATTORNEY}
    is_author = has_review_authority and decision.reviewer_user_id == user.clerk_user_id
    is_admin = user.role == UserRole.ADMIN
    if not (is_author or is_admin):
        raise APIError(
            403,
            "Forbidden",
            "Only the current attorney reviewer or an org admin may delete this decision",
        )
