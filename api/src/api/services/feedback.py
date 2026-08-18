"""Service layer for attorney feedback submissions."""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    AnalysisSearchRelevanceFeedback,
    AnalysisStatus,
    AttorneyFeedbackRecord,
    User,
)
from api.errors import APIError
from api.schemas.feedback import SearchRelevanceFeedbackIn, SubmitFeedbackRequest
from api.services.report_access import (
    report_payload_fingerprint,
    require_completed_report_payload,
)

_CORRECTED_RISK_LEVELS = frozenset({"clear", "low", "medium", "high"})


async def assert_analysis_in_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict:
    """Return the publishable report for an org-scoped feedback target."""
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.org_id == org_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise APIError(404, "Not Found", "Analysis not found")
    return require_completed_report_payload(
        analysis,
        detail="Feedback target report not available",
    )


def _validate_feedback_semantics(
    body: SubmitFeedbackRequest,
    *,
    report_data: dict,
) -> str | None:
    corrected_risk = (body.corrected_risk or "").strip().lower()
    if body.risk_level_correct and corrected_risk:
        raise APIError(
            422,
            "Unprocessable Entity",
            "corrected_risk must be omitted when the report risk is marked correct",
        )
    if not body.risk_level_correct and corrected_risk not in _CORRECTED_RISK_LEVELS:
        raise APIError(
            422,
            "Unprocessable Entity",
            "A valid corrected_risk is required when the report risk is marked incorrect",
        )

    report_patent_ids = {
        str(item.get("patent_id") or "").strip()
        for item in report_data.get("patent_analyses", [])
        if isinstance(item, dict) and str(item.get("patent_id") or "").strip()
    }
    unknown_patent_ids = sorted(
        {
            correction.patent_id.strip()
            for correction in body.corrections
            if correction.patent_id.strip()
            and correction.patent_id.strip() not in report_patent_ids
        }
    )
    if unknown_patent_ids:
        raise APIError(
            422,
            "Unprocessable Entity",
            "Feedback references a patent outside the governed report",
        )
    return corrected_risk or None


async def submit_attorney_feedback(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    body: SubmitFeedbackRequest,
    request: Request | None = None,
) -> AttorneyFeedbackRecord:
    """Persist an attorney feedback record for a report.

    Validates that the analysis is in the user's org, then writes the record
    and a fail-closed audit-log row. Attorney corrections can override the
    system's risk assessment in a regulated FTO product, so the mutation must
    leave an audit trail consistent with every other user-initiated mutating
    service (config presets, review status, monitors, etc.).
    """
    report_data = await assert_analysis_in_org(
        db,
        analysis_id=body.analysis_id,
        org_id=org_id,
    )
    corrected_risk = _validate_feedback_semantics(body, report_data=report_data)

    record = AttorneyFeedbackRecord(
        analysis_id=body.analysis_id,
        org_id=org_id,
        user_id=user_id,
        overall_accuracy=body.overall_accuracy,
        risk_level_correct=body.risk_level_correct,
        corrected_risk=corrected_risk,
        corrections=[c.model_dump() for c in body.corrections],
    )
    db.add(record)
    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=body.analysis_id,
            action="attorney_feedback.submitted",
            details={
                "feedback_id": str(record.id),
                "overall_accuracy": body.overall_accuracy,
                "risk_level_correct": body.risk_level_correct,
                "corrected_risk": corrected_risk,
                "corrections_count": len(body.corrections),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record


async def _load_feedback_analysis(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Analysis:
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


def _validate_search_relevance_target(
    analysis: Analysis,
    body: SearchRelevanceFeedbackIn,
) -> tuple[str, str]:
    """Bind a relevance judgment to a current patent and immutable query plan."""
    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Search relevance feedback requires a completed publishable report.",
    )
    audit_trail = report_data.get("audit_trail")
    audit_payload = audit_trail if isinstance(audit_trail, dict) else {}
    query_plan = audit_payload.get("query_plan")
    query_plan_payload = query_plan if isinstance(query_plan, dict) else {}
    query_plan_sha256 = str(query_plan_payload.get("plan_sha256") or "")
    if len(query_plan_sha256) != 64:
        raise APIError(
            409,
            "Conflict",
            "The report does not contain a governed search query plan.",
        )
    if body.expected_query_plan_sha256 != query_plan_sha256:
        raise APIError(
            409,
            "Conflict",
            "The search query plan changed; refresh the report before submitting feedback.",
        )

    search_funnel = audit_payload.get("search_funnel")
    funnel_rows = search_funnel if isinstance(search_funnel, list) else []
    governed_patent_ids = {
        str(row.get("patent_id") or "")
        for row in funnel_rows
        if isinstance(row, dict) and str(row.get("patent_id") or "")
    }
    if body.patent_id not in governed_patent_ids:
        raise APIError(
            422,
            "Unprocessable Entity",
            "Search relevance feedback references a patent outside the governed search funnel.",
        )
    return query_plan_sha256, report_payload_fingerprint(report_data)


async def _find_existing_search_relevance_feedback(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    patent_id: str,
    reviewer_user_id: uuid.UUID,
) -> AnalysisSearchRelevanceFeedback | None:
    result = await db.execute(
        select(AnalysisSearchRelevanceFeedback)
        .where(
            AnalysisSearchRelevanceFeedback.analysis_id == analysis_id,
            AnalysisSearchRelevanceFeedback.org_id == org_id,
            AnalysisSearchRelevanceFeedback.patent_id == patent_id,
            AnalysisSearchRelevanceFeedback.reviewer_user_id == reviewer_user_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def submit_search_relevance_feedback(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    user: User,
    body: SearchRelevanceFeedbackIn,
    request: Request | None = None,
) -> AnalysisSearchRelevanceFeedback:
    """Upsert a case-scoped label without silently changing production ranking."""
    analysis = await _load_feedback_analysis(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        for_update=True,
    )
    query_plan_sha256, report_fingerprint = _validate_search_relevance_target(
        analysis,
        body,
    )
    existing = await _find_existing_search_relevance_feedback(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        patent_id=body.patent_id,
        reviewer_user_id=user.id,
    )
    if existing is None:
        record = AnalysisSearchRelevanceFeedback(
            analysis_id=analysis_id,
            org_id=user.org_id,
            patent_id=body.patent_id,
            reviewer_user_id=user.id,
        )
        db.add(record)
        audit_action = "search_relevance_feedback.create"
    else:
        record = existing
        audit_action = "search_relevance_feedback.update"

    record.relevance = body.relevance
    record.reason_codes = list(body.reason_codes)
    record.note = body.note
    record.suggested_queries = body.suggested_queries
    record.query_plan_sha256 = query_plan_sha256
    record.report_fingerprint = report_fingerprint
    record.reviewer_name = user.full_name or ""
    record.reviewer_email = user.email or ""

    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action=audit_action,
            details={
                "feedback_id": str(record.id),
                "patent_id": record.patent_id,
                "relevance": record.relevance,
                "reason_codes": record.reason_codes,
                "suggested_query_count": len(record.suggested_queries),
                "query_plan_sha256": record.query_plan_sha256,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record


async def list_search_relevance_feedback(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[list[AnalysisSearchRelevanceFeedback], dict[str, int]]:
    """List durable relevance labels for one org-scoped analysis."""
    await _load_feedback_analysis(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    result = await db.execute(
        select(AnalysisSearchRelevanceFeedback)
        .where(
            AnalysisSearchRelevanceFeedback.analysis_id == analysis_id,
            AnalysisSearchRelevanceFeedback.org_id == org_id,
        )
        .order_by(
            AnalysisSearchRelevanceFeedback.created_at,
            AnalysisSearchRelevanceFeedback.patent_id,
        )
    )
    rows = list(result.scalars().all())
    counts = {"relevant": 0, "not_relevant": 0, "uncertain": 0}
    for row in rows:
        counts[row.relevance] = counts.get(row.relevance, 0) + 1
    return rows, counts
