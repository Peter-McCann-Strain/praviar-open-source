"""Durable lifecycle for monitoring-invalidated report conclusions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    AnalysisReviewStatus,
    AnalysisStatus,
    ExportJob,
    Monitor,
    MonitorConclusionReassessment,
    ReviewStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.schemas.monitors import MonitorConclusionImpact, ResolveMonitorConclusionRequest
from api.services.monitor_conclusion_dependencies import merge_stale_conclusions
from api.services.report_access import require_completed_report_payload

ATTESTATION_VERSION = "2026-07-counsel-reassessment-v1"
ATTESTATION_STATEMENT = (
    "I attest that I reviewed the cited monitoring changes, the affected source-report "
    "conclusion, and the supporting evidence, and that this recorded disposition reflects "
    "my professional reassessment."
)


def _review_status_value(row: AnalysisReviewStatus) -> str:
    value = row.status
    return value.value if isinstance(value, ReviewStatus) else str(value)


def _role_value(user: User) -> str:
    role = user.role
    return role.value if isinstance(role, UserRole) else str(role)


def _validated_impact(raw: dict[str, Any]) -> tuple[MonitorConclusionImpact, dict[str, Any]]:
    impact = MonitorConclusionImpact.model_validate(raw)
    return impact, impact.model_dump(mode="json")


async def record_monitor_conclusion_invalidations(
    db: AsyncSession,
    *,
    monitor: Monitor,
    impacts: list[dict[str, Any]],
) -> list[MonitorConclusionReassessment]:
    """Persist impacts and atomically stale approval/export consumers.

    The caller owns the transaction. Audit insertion is fail-closed so a scan
    cannot commit an invalidated conclusion without its legal lifecycle record.
    """

    if not impacts:
        return []
    if monitor.source_analysis_id is None:
        raise APIError(
            409,
            "Conflict",
            "Conclusion invalidation requires a surviving source analysis.",
        )

    analysis_result = await db.execute(
        select(Analysis)
        .where(
            Analysis.id == monitor.source_analysis_id,
            Analysis.org_id == monitor.org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
        .with_for_update()
    )
    analysis = analysis_result.scalar_one_or_none()
    if analysis is None:
        raise APIError(
            409,
            "Conflict",
            "The source analysis is unavailable; monitoring invalidation cannot be recorded.",
        )

    existing_result = await db.execute(
        select(MonitorConclusionReassessment)
        .where(
            MonitorConclusionReassessment.org_id == monitor.org_id,
            MonitorConclusionReassessment.monitor_id == monitor.id,
            MonitorConclusionReassessment.status == "open",
        )
        .with_for_update()
    )
    existing_by_conclusion = {row.conclusion_id: row for row in existing_result.scalars().all()}

    review_result = await db.execute(
        select(AnalysisReviewStatus)
        .where(
            AnalysisReviewStatus.analysis_id == monitor.source_analysis_id,
            AnalysisReviewStatus.org_id == monitor.org_id,
        )
        .with_for_update()
    )
    review_status = review_result.scalar_one_or_none()
    approval_invalidated = bool(
        review_status is not None
        and _review_status_value(review_status) == ReviewStatus.APPROVED.value
    )
    approval_snapshot: dict[str, Any] | None = None
    if approval_invalidated and review_status is not None:
        approval_snapshot = {
            "status": ReviewStatus.APPROVED.value,
            "reviewer_user_id": review_status.reviewer_user_id,
            "reviewer_name": review_status.reviewer_name,
            "reviewer_email": review_status.reviewer_email,
            "reviewed_at": (
                review_status.reviewed_at.isoformat() if review_status.reviewed_at else None
            ),
            "note": review_status.note,
        }

    records: list[MonitorConclusionReassessment] = []
    conclusion_ids: list[str] = []
    now = datetime.now(UTC)
    for raw_impact in impacts:
        impact, payload = _validated_impact(raw_impact)
        conclusion_ids.append(impact.conclusion_id)
        if approval_snapshot is not None:
            payload["review_approval_at_invalidation"] = approval_snapshot
        record = existing_by_conclusion.get(impact.conclusion_id)
        if record is None:
            record = MonitorConclusionReassessment(
                org_id=monitor.org_id,
                monitor_id=monitor.id,
                source_analysis_id=monitor.source_analysis_id,
                source_report_id=impact.source_report_id or monitor.source_report_id,
                conclusion_id=impact.conclusion_id,
                conclusion_type=impact.conclusion_type,
                conclusion_label=impact.label,
                previous_outcome=impact.previous_outcome,
                dependency_fingerprint=impact.dependency_fingerprint,
                status="open",
                trigger_evidence=payload,
                invalidated_at=impact.invalidated_at,
                latest_observed_at=impact.latest_observed_at,
            )
            db.add(record)
            existing_by_conclusion[impact.conclusion_id] = record
        else:
            prior_payload = dict(record.trigger_evidence or {})
            merged_payload = merge_stale_conclusions([prior_payload], [payload])[0]
            if approval_snapshot is not None:
                merged_payload["review_approval_at_invalidation"] = approval_snapshot
            record.trigger_evidence = merged_payload
            record.latest_observed_at = impact.latest_observed_at
            record.dependency_fingerprint = impact.dependency_fingerprint
            record.source_report_id = impact.source_report_id or monitor.source_report_id
        records.append(record)

    unique_conclusion_ids = list(dict.fromkeys(conclusion_ids))
    analysis.flagged_for_review = True
    if approval_invalidated and review_status is not None:
        review_status.status = ReviewStatus.CHANGES_REQUESTED
        review_status.note = (
            f"Monitoring invalidated {len(unique_conclusion_ids)} report conclusion"
            f"{'' if len(unique_conclusion_ids) == 1 else 's'}. "
            "The prior approval must not be relied upon until counsel completes reassessment."
        )
        review_status.reviewed_at = now

    export_result = await db.execute(
        select(ExportJob)
        .where(
            ExportJob.org_id == monitor.org_id,
            ExportJob.analysis_id == monitor.source_analysis_id,
        )
        .with_for_update()
    )
    superseded_export_ids: list[str] = []
    for export in export_result.scalars().all():
        if export.superseded_at is None:
            export.superseded_at = now
        export.superseded_reason = "monitor_conclusion_invalidation"
        export.superseded_conclusion_ids = list(
            dict.fromkeys(
                [
                    *list(export.superseded_conclusion_ids or []),
                    *unique_conclusion_ids,
                ]
            )
        )
        superseded_export_ids.append(str(export.id))

    await db.flush()
    await write_audit_log(
        db,
        org_id=monitor.org_id,
        user_id=monitor.user_id,
        analysis_id=monitor.source_analysis_id,
        action="monitor.conclusions.invalidated",
        details={
            "actor_type": "monitoring_system",
            "monitor_id": str(monitor.id),
            "source_report_id": monitor.source_report_id,
            "conclusion_ids": unique_conclusion_ids,
            "reassessment_ids": [str(record.id) for record in records],
            "review_approval_invalidated": approval_invalidated,
            "superseded_export_ids": superseded_export_ids,
        },
        fail_closed=True,
    )
    return records


async def list_monitor_conclusion_reassessments(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[MonitorConclusionReassessment]:
    result = await db.execute(
        select(MonitorConclusionReassessment)
        .where(
            MonitorConclusionReassessment.monitor_id == monitor_id,
            MonitorConclusionReassessment.org_id == org_id,
        )
        .order_by(MonitorConclusionReassessment.invalidated_at.desc())
    )
    return list(result.scalars().all())


async def has_open_analysis_reassessments(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(MonitorConclusionReassessment.id)
        .where(
            MonitorConclusionReassessment.source_analysis_id == analysis_id,
            MonitorConclusionReassessment.org_id == org_id,
            MonitorConclusionReassessment.status == "open",
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def has_open_monitor_reassessments(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
) -> bool:
    """Check the durable ledger instead of trusting the mutable monitor cache."""

    result = await db.execute(
        select(MonitorConclusionReassessment.id)
        .where(
            MonitorConclusionReassessment.monitor_id == monitor_id,
            MonitorConclusionReassessment.org_id == org_id,
            MonitorConclusionReassessment.status == "open",
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def resolve_monitor_conclusion(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    conclusion_id: str,
    org_id: uuid.UUID,
    user: User,
    body: ResolveMonitorConclusionRequest,
    request: Request | None = None,
) -> MonitorConclusionReassessment:
    """Record one attorney-attested disposition and close its open episode."""

    if user.role != UserRole.ATTORNEY:
        raise APIError(
            403,
            "Forbidden",
            "Only an active attorney-role user may attest to a conclusion reassessment.",
        )
    reviewer_name = (user.full_name or "").strip()
    reviewer_email = (user.email or "").strip()
    if not reviewer_name or not reviewer_email:
        raise APIError(
            409,
            "Conflict",
            "Counsel profile name and email are required for a durable legal attestation.",
        )

    monitor_result = await db.execute(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.org_id == org_id).with_for_update()
    )
    monitor = monitor_result.scalar_one_or_none()
    if monitor is None:
        raise APIError(404, "Not Found", "Monitor not found")

    record_result = await db.execute(
        select(MonitorConclusionReassessment)
        .where(
            MonitorConclusionReassessment.id == body.reassessment_id,
            MonitorConclusionReassessment.monitor_id == monitor_id,
            MonitorConclusionReassessment.org_id == org_id,
            MonitorConclusionReassessment.conclusion_id == conclusion_id,
        )
        .with_for_update()
    )
    record = record_result.scalar_one_or_none()
    if record is None:
        raise APIError(
            409,
            "Conflict",
            "The requested reassessment episode is stale, historical, or no longer current.",
        )
    normalized_note = body.resolution_note.strip()
    if record.status != "open":
        raise APIError(
            409,
            "Conflict",
            "Historical reassessment episodes are read-only.",
        )
    trigger_evidence = dict(record.trigger_evidence or {})
    try:
        bound_observed_at = datetime.fromisoformat(
            str(trigger_evidence.get("evidence_observed_at") or "").replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        bound_observed_at = None
    stale_impact = next(
        (
            impact
            for impact in list(monitor.stale_conclusions or [])
            if isinstance(impact, dict)
            and str(impact.get("conclusion_id") or "") == conclusion_id
            and str(impact.get("reassessment_id") or "") == str(body.reassessment_id)
        ),
        None,
    )
    episode_matches = bool(
        stale_impact is not None
        and record.dependency_fingerprint == body.dependency_fingerprint
        and str(trigger_evidence.get("alert_id") or "") == str(body.alert_id)
        and str(trigger_evidence.get("evidence_digest") or "") == body.evidence_digest
        and str(trigger_evidence.get("evidence_version") or "") == body.evidence_version
        and bound_observed_at == body.evidence_observed_at
        and str(stale_impact.get("dependency_fingerprint") or "") == body.dependency_fingerprint
        and str(stale_impact.get("alert_id") or "") == str(body.alert_id)
        and str(stale_impact.get("evidence_digest") or "") == body.evidence_digest
        and str(stale_impact.get("evidence_version") or "") == body.evidence_version
    )
    if not episode_matches:
        raise APIError(
            409,
            "Conflict",
            "The reassessment evidence episode changed. Reload the exact alert evidence "
            "before recording a disposition.",
        )

    if body.replacement_analysis_id is not None:
        if body.replacement_analysis_id == record.source_analysis_id:
            raise APIError(
                422,
                "Unprocessable Entity",
                "A superseded conclusion must reference a different completed analysis.",
            )
        replacement_result = await db.execute(
            select(Analysis).where(
                Analysis.id == body.replacement_analysis_id,
                Analysis.org_id == org_id,
                Analysis.status == AnalysisStatus.COMPLETED,
            )
        )
        replacement = replacement_result.scalar_one_or_none()
        if replacement is None:
            raise APIError(
                422,
                "Unprocessable Entity",
                "Replacement analysis must be a completed analysis in the same organization.",
            )
        require_completed_report_payload(
            replacement,
            status_code=422,
            title="Unprocessable Entity",
            detail="Replacement analysis must contain a publishable completed report.",
        )

    now = datetime.now(UTC)
    record.status = body.resolution
    record.resolved_at = now
    record.resolved_by_user_id = user.id
    record.reviewer_role = _role_value(user)
    record.reviewer_name = reviewer_name
    record.reviewer_email = reviewer_email
    record.resolution_note = normalized_note
    record.attestation_version = ATTESTATION_VERSION
    record.attestation_statement = ATTESTATION_STATEMENT
    record.attestation_accepted = True
    record.replacement_analysis_id = body.replacement_analysis_id

    stale_conclusions = [
        impact
        for impact in list(monitor.stale_conclusions or [])
        if isinstance(impact, dict) and str(impact.get("conclusion_id") or "") != conclusion_id
    ]
    monitor.stale_conclusions = stale_conclusions
    monitor.conclusion_status = (
        "review_required"
        if stale_conclusions
        else ("reassessed" if monitor.source_analysis_id is not None else "unbound")
    )
    monitor.last_run_status = "review_required" if stale_conclusions else "reassessed"

    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user.id,
            analysis_id=record.source_analysis_id,
            action="monitor.conclusion.reassessed",
            details={
                "monitor_id": str(monitor_id),
                "reassessment_id": str(record.id),
                "conclusion_id": conclusion_id,
                "resolution": body.resolution,
                "replacement_analysis_id": (
                    str(body.replacement_analysis_id)
                    if body.replacement_analysis_id is not None
                    else None
                ),
                "attestation_version": ATTESTATION_VERSION,
                "reviewer_role": _role_value(user),
                "alert_id": str(body.alert_id),
                "dependency_fingerprint": body.dependency_fingerprint,
                "evidence_digest": body.evidence_digest,
                "evidence_version": body.evidence_version,
                "evidence_observed_at": body.evidence_observed_at.isoformat(),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
        await db.refresh(record)
    except Exception:
        await db.rollback()
        raise
    return record
