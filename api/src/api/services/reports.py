"""Business logic for report sharing and export orchestration."""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import Request
from praviar_pipeline.models.report import (
    ClaimProgramDecision,
    ClearanceDecision,
    ClearanceOutcome,
    MatterEvidenceIndex,
)
from praviar_pipeline.pipeline.report.blocker_family_records import (
    build_blocker_family_records,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import (
    Analysis,
    AnalysisReviewerDecision,
    AnalysisStatus,
    ExportFormat,
    ExportJob,
    ExportStatus,
    ReviewStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.services.analyses import get_analysis_for_org, load_analysis_review_status
from api.services.blocking_sdk import run_blocking_sdk_call
from api.services.export_receipts import ExportReceiptIntegrityError, verify_export_receipt
from api.services.object_storage import GCSUri, ObjectStorage, parse_gs_uri
from api.services.report_access import (
    analysis_status_value,
    claim_source_span_review_findings,
    filter_current_reviewer_decisions,
    report_payload_fingerprint,
    require_completed_report_payload,
    require_no_pending_claim_source_span_reviews,
)
from api.services.task_dispatcher import build_dispatcher

logger = structlog.get_logger()
GCS_OPERATION_TIMEOUT_SECONDS = 5.0
MAX_EXPORT_DOWNLOAD_BYTES = 256 * 1024 * 1024
EXPORT_DOWNLOAD_SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
EXPORT_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
EXPORT_REVIEWABLE_RISK_LEVELS = {"high", "medium"}
EXPORT_DUAL_REVIEW_RISK_LEVELS = {"high"}
EXPORT_REVIEW_DECISIONS = {"accept", "reject", "edit"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExportDispatchResult:
    job_id: uuid.UUID
    status: str
    format: str


@dataclass(frozen=True)
class ExportDownload:
    job: ExportJob
    filename: str
    local_path: Path | None = None
    gcs_uri: GCSUri | None = None


@dataclass
class PreparedExportDownload:
    """A verified private artifact ready for release to the browser."""

    file: tempfile.SpooledTemporaryFile[bytes]
    size: int

    def close(self) -> None:
        self.file.close()


class ExportArtifactIntegrityError(RuntimeError):
    """The stored artifact does not match its immutable export receipt."""


async def _commit_or_rollback(db: AsyncSession) -> None:
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@dataclass(frozen=True)
class ExportRequiredFindingReview:
    finding_type: str
    finding_ref: str
    risk_level: str
    display_ref: str = ""


def ensure_analysis_can_be_shared(analysis: object) -> None:
    """Require a completed report payload before public sharing is enabled."""
    if analysis_status_value(getattr(analysis, "status", None)) != AnalysisStatus.COMPLETED.value:
        raise APIError(409, "Conflict", "Only completed reports can be shared")
    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Only completed reports with report data can be shared",
    )
    require_no_pending_claim_source_span_reviews(
        report_data,
        status_code=409,
        title="Conflict",
        detail="Report has claim evidence requiring reviewer approval before sharing",
    )
    blocker_contract_blockers = build_blocker_family_contract_blockers(report_data)
    if blocker_contract_blockers:
        raise APIError(
            409,
            "Conflict",
            "Report blocker-family decision contract is incomplete: "
            + " ".join(blocker_contract_blockers),
        )


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _extract_export_required_finding_reviews(
    report_data: dict[str, object],
) -> list[ExportRequiredFindingReview]:
    raw_candidates = (
        report_data.get("patent_analyses")
        or report_data.get("patents")
        or report_data.get("analyses")
        or []
    )
    candidates = raw_candidates if isinstance(raw_candidates, list) else []

    findings_by_key: dict[tuple[str, str], ExportRequiredFindingReview] = {}
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        risk_level = _normalize_text(entry.get("risk_level")).lower()
        if risk_level not in EXPORT_REVIEWABLE_RISK_LEVELS:
            continue
        finding_ref = _normalize_text(
            entry.get("patent_id")
            or entry.get("id")
            or entry.get("publication_number")
            or entry.get("patent_number")
        )
        if not finding_ref:
            continue

        key = ("patent", finding_ref)
        existing = findings_by_key.get(key)
        if existing is None or (
            existing.risk_level not in EXPORT_DUAL_REVIEW_RISK_LEVELS
            and risk_level in EXPORT_DUAL_REVIEW_RISK_LEVELS
        ):
            findings_by_key[key] = ExportRequiredFindingReview(
                finding_type="patent",
                finding_ref=finding_ref,
                risk_level=risk_level,
                display_ref=finding_ref,
            )

    for entry in claim_source_span_review_findings(report_data):
        finding_ref = _normalize_text(entry.assertion_id)
        if not finding_ref:
            continue
        key = ("claim_element", finding_ref)
        if key in findings_by_key:
            continue
        findings_by_key[key] = ExportRequiredFindingReview(
            finding_type="claim_element",
            finding_ref=finding_ref,
            risk_level="medium",
            display_ref=finding_ref,
        )

    return sorted(findings_by_key.values(), key=lambda item: (item.finding_type, item.finding_ref))


async def _load_export_reviewer_decisions(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[AnalysisReviewerDecision]:
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
    )
    return list(result.scalars().all())


async def load_export_reviewer_decisions(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[AnalysisReviewerDecision]:
    """Load export-counted reviewer decisions from active attorney/admin users."""
    return await _load_export_reviewer_decisions(db, analysis_id=analysis_id, org_id=org_id)


def _object_field(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field, "")
    return getattr(value, field, "")


def _reviewer_decision_id(decision: object) -> str:
    return _normalize_text(_object_field(decision, "reviewer_user_id"))


def _find_export_review_blockers(
    *,
    required_reviews: list[ExportRequiredFindingReview],
    decisions: Sequence[object],
    current_report_fingerprint: str,
) -> list[str]:
    decisions_by_finding: dict[tuple[str, str], dict[str, set[str]]] = {}
    for decision in decisions:
        decision_report_fingerprint = _normalize_text(_object_field(decision, "report_fingerprint"))
        if decision_report_fingerprint != current_report_fingerprint:
            continue
        decision_value = _normalize_text(_object_field(decision, "decision")).lower()
        if decision_value not in EXPORT_REVIEW_DECISIONS:
            continue
        reviewer_id = _reviewer_decision_id(decision)
        if not reviewer_id:
            continue
        key = (
            _normalize_text(_object_field(decision, "finding_type")),
            _normalize_text(_object_field(decision, "finding_ref")),
        )
        decisions_by_finding.setdefault(key, {}).setdefault(
            decision_value,
            set(),
        ).add(reviewer_id)

    blockers: list[str] = []
    for finding in required_reviews:
        display_ref = finding.display_ref or finding.finding_ref
        finding_decisions = decisions_by_finding.get(
            (finding.finding_type, finding.finding_ref),
            {},
        )
        rejected_by = finding_decisions.get("reject", set())
        edited_by = finding_decisions.get("edit", set())
        accepted_by = finding_decisions.get("accept", set())
        if rejected_by:
            blockers.append(
                f"{finding.risk_level.upper()} finding {display_ref} has a reviewer "
                "rejection that must be resolved in a new report snapshot."
            )
            continue
        if edited_by:
            blockers.append(
                f"{finding.risk_level.upper()} finding {display_ref} has proposed "
                "reviewer edits that are not applied to the current report snapshot."
            )
            continue
        if not accepted_by:
            blockers.append(
                f"{finding.risk_level.upper()} finding {display_ref} has no reviewer "
                "decision accepting the current report snapshot."
            )
            continue
        if finding.risk_level in EXPORT_DUAL_REVIEW_RISK_LEVELS and len(accepted_by) < 2:
            blockers.append(
                f"HIGH finding {display_ref} requires dual review with two independent "
                "accepting decisions before export."
            )
    return blockers


def build_reviewer_decision_blockers(
    *,
    report_data: dict[str, object],
    reviewer_decisions: Sequence[object],
) -> list[str]:
    """Return missing-review reasons for HIGH/MEDIUM export-relevant findings."""
    return _find_export_review_blockers(
        required_reviews=_extract_export_required_finding_reviews(report_data),
        decisions=filter_current_reviewer_decisions(report_data, reviewer_decisions),
        current_report_fingerprint=report_payload_fingerprint(report_data),
    )


def build_drawing_governance_blockers(
    report_data: Mapping[str, object],
) -> list[str]:
    """Reject unbound or self-contradictory customer-visible drawing evidence."""
    raw_analyses = report_data.get("drawing_analyses")
    analyses = raw_analyses if isinstance(raw_analyses, list) else []
    blockers: list[str] = []
    governance_identities: set[tuple[object, ...]] = set()

    for analysis in analyses:
        if not isinstance(analysis, Mapping):
            blockers.append("A drawing analysis has an invalid report shape.")
            continue
        raw_structures = analysis.get("structures")
        structures = raw_structures if isinstance(raw_structures, list) else []
        if not structures:
            continue
        patent_id = _normalize_text(analysis.get("patent_id")) or "unknown patent"
        provenance = analysis.get("governance_provenance")
        if not isinstance(provenance, Mapping):
            blockers.append(f"Drawing evidence for {patent_id} has no governance provenance.")
            continue
        rollout_state = _normalize_text(provenance.get("rollout_state")).lower()
        influence_permitted = provenance.get("influence_permitted")
        if rollout_state in {"internal", "shadow"}:
            if influence_permitted is not False:
                blockers.append(
                    f"Shadow drawing evidence for {patent_id} has an invalid influence flag."
                )
        elif rollout_state in {"beta", "production"}:
            live_hashes = (
                provenance.get("runtime_roster_sha256"),
                provenance.get("ml_bom_sha256"),
                provenance.get("calibration_artifact_sha256"),
            )
            calibration_revision = provenance.get("calibration_artifact_revision")
            if (
                influence_permitted is not True
                or provenance.get("evidence_gate_passed") is not True
                or any(
                    not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
                    for value in live_hashes
                )
                or not isinstance(provenance.get("worker_image_digest"), str)
                or OCI_DIGEST_RE.fullmatch(str(provenance.get("worker_image_digest"))) is None
                or not _normalize_text(provenance.get("calibration_artifact_id"))
                or not isinstance(calibration_revision, int)
                or isinstance(calibration_revision, bool)
                or calibration_revision < 1
                or not provenance.get("verified_at")
            ):
                blockers.append(
                    f"Live drawing evidence for {patent_id} has incomplete runtime bindings."
                )
        else:
            blockers.append(f"Drawing evidence for {patent_id} has an unknown rollout state.")

        for structure in structures:
            if not isinstance(structure, Mapping):
                blockers.append(
                    f"Drawing evidence for {patent_id} has an invalid structure record."
                )
                continue
            for field, label in (
                ("input_image_sha256", "OCSR input image"),
                ("source_page_image_sha256", "source page image"),
            ):
                value = structure.get(field)
                if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                    blockers.append(
                        f"Drawing evidence for {patent_id} is missing its {label} hash."
                    )

        governance_identities.add(
            (
                rollout_state,
                influence_permitted,
                provenance.get("runtime_roster_sha256"),
                provenance.get("ml_bom_sha256"),
                provenance.get("calibration_artifact_id"),
                provenance.get("calibration_artifact_revision"),
                provenance.get("calibration_artifact_sha256"),
                provenance.get("worker_image_digest"),
            )
        )

    if len(governance_identities) > 1:
        blockers.append("Drawing analyses were produced under inconsistent runtime governance.")
    return blockers


def build_blocker_family_contract_blockers(
    report_data: Mapping[str, object],
) -> list[str]:
    """Validate the canonical blocker-family decision projection."""
    raw_decision = report_data.get("clearance_decision")
    if not isinstance(raw_decision, Mapping):
        return ["The governed clearance decision is missing or invalid."]
    raw_audit = raw_decision.get("decision_audit")
    if str(
        raw_decision.get("decision") or ""
    ).strip().lower() == ClearanceOutcome.BLOCKED.value and (
        not isinstance(raw_audit, Mapping)
        or not isinstance(raw_audit.get("blocker_families"), list)
        or not raw_audit.get("blocker_families")
    ):
        return ["The blocked decision has no canonical blocker-family records."]
    try:
        decision = ClearanceDecision.model_validate(raw_decision)
        raw_claim_program_decisions = report_data.get("claim_program_decisions")
        if not isinstance(raw_claim_program_decisions, list):
            raise ValueError("claim-program decisions are missing")
        claim_program_decisions = [
            ClaimProgramDecision.model_validate(item) for item in raw_claim_program_decisions
        ]
        matter_evidence_index = MatterEvidenceIndex.model_validate(
            report_data.get("matter_evidence_index")
        )
        expected_families = build_blocker_family_records(
            decision=decision.decision,
            claim_program_summary=decision.decision_audit.claim_program_summary,
            claim_program_decisions=claim_program_decisions,
            matter_evidence_index=matter_evidence_index,
        )
    except (TypeError, ValueError, ValidationError):
        return ["The governed clearance decision contract is invalid."]

    blocker_families = decision.decision_audit.blocker_families
    actual_projection = [family.model_dump(mode="json") for family in blocker_families]
    expected_projection = [family.model_dump(mode="json") for family in expected_families]
    if actual_projection != expected_projection:
        return [
            "The blocker-family decision contract does not match its canonical claim "
            "and family evidence."
        ]
    return []


def build_export_readiness_blockers(
    *,
    report_data: dict[str, object],
    review_status: object | None,
    reviewer_decisions: Sequence[object],
) -> list[str]:
    opinion_readiness_raw = report_data.get("opinion_readiness")
    opinion_readiness: dict[str, object] = (
        opinion_readiness_raw if isinstance(opinion_readiness_raw, dict) else {}
    )
    trust_mode = _normalize_text(
        report_data.get("trust_mode") or opinion_readiness.get("trust_mode") or "explorer"
    ).lower()
    export_ready = opinion_readiness.get("export_ready") is True
    blocked_jurisdictions_raw = opinion_readiness.get("jurisdictions_blocking_export")
    blocked_jurisdictions_values = (
        blocked_jurisdictions_raw if isinstance(blocked_jurisdictions_raw, list) else []
    )
    blocked_jurisdictions = [
        _normalize_text(value).upper()
        for value in blocked_jurisdictions_values
        if _normalize_text(value)
    ]
    review_status_value = _object_field(review_status, "status") if review_status else None
    review_approved = review_status_value == ReviewStatus.APPROVED

    blockers: list[str] = []
    if trust_mode != "counsel":
        blockers.append(
            f"Current trust mode is {trust_mode or 'explorer'}, so the report is not "
            "in counsel export mode."
        )
    if not export_ready:
        if blocked_jurisdictions:
            blockers.append(
                "Selected jurisdiction lanes still block export: "
                + ", ".join(blocked_jurisdictions)
                + "."
            )
        else:
            blockers.append(
                "Lane certification or clearance-grade evidence is still incomplete for export."
            )
    if not review_approved:
        review_state = (
            review_status_value.value
            if isinstance(review_status_value, ReviewStatus)
            else _normalize_text(review_status_value) or "pending"
        )
        blockers.append(f"Persisted legal review status is {review_state}, not approved.")

    review_blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=reviewer_decisions,
    )
    if review_blockers:
        blockers.append("Reviewer decisions are incomplete: " + " ".join(review_blockers))
    blockers.extend(build_blocker_family_contract_blockers(report_data))
    blockers.extend(build_drawing_governance_blockers(report_data))
    return blockers


async def ensure_analysis_export_ready(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    analysis: Analysis | None = None,
) -> Analysis:
    analysis = analysis or await get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Export is blocked until the analysis has a completed report payload.",
    )
    review_status = await load_analysis_review_status(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    reviewer_decisions: list[AnalysisReviewerDecision] = []
    if _extract_export_required_finding_reviews(report_data):
        reviewer_decisions = await _load_export_reviewer_decisions(
            db,
            analysis_id=analysis_id,
            org_id=org_id,
        )
    blockers = build_export_readiness_blockers(
        report_data=report_data,
        review_status=review_status,
        reviewer_decisions=reviewer_decisions,
    )
    if not blockers:
        return analysis

    raise APIError(
        409,
        "Conflict",
        "Export is blocked until counsel-mode export readiness is open and legal "
        "review is approved. " + " ".join(blockers),
    )


async def queue_export_job(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    export_format: ExportFormat,
    sections: list[str],
    audience: str = "full",
    analysis: Analysis | None = None,
    request: Request | None = None,
) -> ExportDispatchResult:
    analysis = analysis or await get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )

    job = ExportJob(
        analysis_id=analysis.id,
        org_id=org_id,
        user_id=user_id,
        format=export_format,
        status=ExportStatus.PENDING,
        sections=sections,
        audience=audience,
    )
    db.add(job)
    await db.flush()
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis.id,
            action="report.export.queued",
            details={
                "job_id": str(job.id),
                "analysis_id": str(analysis.id),
                "user_id": str(user_id),
                "format": export_format.value,
                "audience": audience,
                "sections": sections,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    try:
        await build_dispatcher().dispatch_export_job(
            export_job_id=str(job.id),
            org_id=str(org_id),
        )
    except Exception as exc:
        # Provider/SDK exceptions can include private queue URLs and request
        # metadata. Emit only the stable operation identity and exception type.
        logger.error(
            "export_dispatch_failed",
            job_id=str(job.id),
            error_type=type(exc).__name__,
        )
        job.status = ExportStatus.FAILED
        await _commit_or_rollback(db)
        raise APIError(503, "Service Unavailable", "Export dispatch failed") from exc

    logger.info("export_dispatched", job_id=str(job.id), format=export_format.value)
    return ExportDispatchResult(job_id=job.id, status="pending", format=export_format.value)


async def get_export_job_for_org(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> ExportJob:
    statement = (
        select(ExportJob)
        .join(Analysis, ExportJob.analysis_id == Analysis.id)
        .where(
            ExportJob.id == job_id,
            ExportJob.org_id == org_id,
            Analysis.org_id == org_id,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    job = result.scalar_one_or_none()
    if not job:
        raise APIError(404, "Not Found", "Export job not found")
    return job


async def delete_export_job(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    allow_org_wide: bool = False,
    request: Request | None = None,
) -> None:
    """Delete a terminal export record and its private artifact.

    Active jobs cannot be removed while a worker may still publish an object.
    A durable, worker-terminal deletion intent is committed before external
    storage is touched. If artifact or completion cleanup fails, a retry safely
    resumes from that audited intent.
    """
    job = await get_export_job_for_org(
        db,
        job_id=job_id,
        org_id=org_id,
        for_update=True,
    )
    if not allow_org_wide and job.user_id != user_id:
        raise APIError(
            403,
            "Forbidden",
            "Only the export owner or counsel can delete this export",
        )
    if job.status in (ExportStatus.PENDING, ExportStatus.PROCESSING) or (
        job.status == ExportStatus.FAILED
        and getattr(job, "processing_lease_expires_at", None) is not None
    ):
        raise APIError(409, "Conflict", "An active export cannot be deleted")

    original_status = job.status
    artifact_url = job.file_url
    analysis_id = job.analysis_id
    format_value = job.format.value
    gcs_cleanup: tuple[str, str, str | None] | None = None
    local_cleanup: Path | None = None

    # Validate the complete artifact authority boundary before changing state.
    # No external deletion occurs until the intent audit below is committed.
    if artifact_url:
        settings = get_settings()
        if artifact_url.startswith("gs://"):
            try:
                gcs_uri = parse_gs_uri(artifact_url)
            except ValueError as exc:
                raise APIError(403, "Forbidden", "Invalid export object path") from exc
            if not settings.gcs_bucket_name or gcs_uri.bucket != settings.gcs_bucket_name:
                raise APIError(403, "Forbidden", "Invalid export object bucket")
            expected_prefix = f"exports/{org_id}/{analysis_id}/{job_id}/"
            if not gcs_uri.blob_path.startswith(expected_prefix):
                raise APIError(403, "Forbidden", "Invalid export object path")
            gcs_cleanup = (
                gcs_uri.bucket,
                gcs_uri.blob_path,
                settings.gcp_project_id or None,
            )
        else:
            export_dir = Path(settings.export_dir).resolve()
            resolved = Path(artifact_url).resolve()
            if not resolved.is_relative_to(export_dir):
                raise APIError(403, "Forbidden", "Invalid export file path")
            local_cleanup = resolved

    # Commit a durable deletion intent before touching external storage. FAILED
    # with no retry lease is an existing terminal state that workers refuse to
    # reclaim, so it also closes the worker race without a schema migration.
    job.status = ExportStatus.FAILED
    job.processing_execution_id = None
    job.processing_lease_expires_at = None
    job.error_message = "Export deletion requested"
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis_id,
            action="report.export.deletion_requested",
            details={
                "job_id": str(job.id),
                "format": format_value,
                "previous_status": original_status.value,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    if gcs_cleanup is not None:
        bucket, blob_path, project = gcs_cleanup
        storage = ObjectStorage(bucket=bucket, project=project)
        await run_blocking_sdk_call(
            "gcs.export.delete",
            storage.delete_blob,
            blob_path,
            timeout_seconds=GCS_OPERATION_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
    elif local_cleanup is not None:
        local_cleanup.unlink(missing_ok=True)

    # Re-lock after the intent commit. The terminal no-lease state prevents a
    # worker from claiming the job while the external delete is in progress.
    job = await get_export_job_for_org(
        db,
        job_id=job_id,
        org_id=org_id,
        for_update=True,
    )
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis_id,
            action="report.export.deleted",
            details={
                "job_id": str(job.id),
                "format": format_value,
                "previous_status": original_status.value,
            },
            request=request,
            fail_closed=True,
        )
        await db.delete(job)
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def resolve_export_download(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExportDownload:
    job = await get_export_job_for_org(db, job_id=job_id, org_id=org_id)
    if isinstance(getattr(job, "superseded_at", None), datetime):
        raise APIError(
            409,
            "Conflict",
            "This export was superseded by monitoring evidence and cannot be relied upon. "
            "Complete counsel reassessment and generate a new export.",
        )
    if job.status != ExportStatus.COMPLETED or not job.file_url:
        raise APIError(404, "Not Found", "Export not ready")

    if job.file_url.startswith("gs://"):
        from api.services.object_storage import parse_gs_uri

        settings = get_settings()
        try:
            gcs_uri = parse_gs_uri(job.file_url)
        except ValueError as exc:
            logger.error("export_gcs_uri_invalid", job_id=str(job_id))
            raise APIError(403, "Forbidden", "Invalid export object path") from exc

        expected_bucket = settings.gcs_bucket_name
        if not expected_bucket or gcs_uri.bucket != expected_bucket:
            logger.error(
                "export_gcs_bucket_mismatch",
                job_id=str(job_id),
            )
            raise APIError(403, "Forbidden", "Invalid export object bucket")

        expected_prefix = f"exports/{org_id}/{job.analysis_id}/{job_id}/"
        if not gcs_uri.blob_path.startswith(expected_prefix):
            logger.error("export_gcs_path_mismatch", job_id=str(job_id))
            raise APIError(403, "Forbidden", "Invalid export object path")

        file_size_bytes = job.file_size_bytes
        if not isinstance(file_size_bytes, int) or not (
            0 < file_size_bytes <= MAX_EXPORT_DOWNLOAD_BYTES
        ):
            logger.error("export_gcs_size_invalid", job_id=str(job_id))
            raise APIError(409, "Conflict", "Export artifact size is invalid")

        artifact_sha256 = job.artifact_sha256
        if not isinstance(artifact_sha256, str) or len(artifact_sha256) != 64:
            logger.error("export_gcs_digest_invalid", job_id=str(job_id))
            raise APIError(409, "Conflict", "Export artifact digest is invalid")
        try:
            bytes.fromhex(artifact_sha256)
        except ValueError as exc:
            logger.error("export_gcs_digest_invalid", job_id=str(job_id))
            raise APIError(409, "Conflict", "Export artifact digest is invalid") from exc

        _ensure_export_receipt_integrity(job, job_id=job_id)
        return ExportDownload(
            job=job,
            filename=Path(gcs_uri.blob_path).name,
            gcs_uri=gcs_uri,
        )

    file_path = Path(job.file_url)
    export_dir = Path(get_settings().export_dir).resolve()
    resolved = file_path.resolve()
    if not resolved.is_relative_to(export_dir):
        logger.error("path_traversal_blocked", job_id=str(job_id))
        raise APIError(403, "Forbidden", "Invalid file path")
    if not resolved.exists():
        logger.error("export_file_missing", job_id=str(job_id))
        raise APIError(404, "Not Found", "Export file not found on disk")

    _ensure_export_receipt_integrity(job, job_id=job_id)
    return ExportDownload(job=job, filename=resolved.name, local_path=resolved)


def _ensure_export_receipt_integrity(job: object, *, job_id: uuid.UUID) -> None:
    try:
        verify_export_receipt(job)
    except ExportReceiptIntegrityError as exc:
        logger.error(
            "export_receipt_integrity_failed",
            job_id=str(job_id),
            reason=str(exc),
        )
        raise APIError(
            409,
            "Conflict",
            "Export receipt failed integrity verification",
        ) from exc


def prepare_export_download(export: ExportDownload) -> PreparedExportDownload:
    """Verify a GCS export in bounded private storage before releasing a 2xx."""
    if export.gcs_uri is None:
        raise ValueError("GCS export location is required")

    expected_size = export.job.file_size_bytes
    artifact_sha256 = export.job.artifact_sha256
    if not isinstance(expected_size, int) or not (0 < expected_size <= MAX_EXPORT_DOWNLOAD_BYTES):
        raise ValueError("Valid export artifact size is required")
    if not isinstance(artifact_sha256, str):
        raise ValueError("Valid export artifact digest is required")
    expected_sha256 = artifact_sha256.lower()
    settings = get_settings()
    storage = ObjectStorage(
        bucket=export.gcs_uri.bucket,
        project=settings.gcp_project_id or None,
        operation_timeout=GCS_OPERATION_TIMEOUT_SECONDS,
    )
    digest = hashlib.sha256()
    # Ownership transfers to PreparedExportDownload and is closed by the
    # response background task; every exceptional path closes it below.
    prepared_file = tempfile.SpooledTemporaryFile(  # noqa: SIM115
        max_size=EXPORT_DOWNLOAD_SPOOL_MEMORY_BYTES,
        mode="w+b",
    )
    prepared_size = 0

    try:
        for chunk in storage.iter_blob(export.gcs_uri.blob_path):
            prepared_size += len(chunk)
            if prepared_size > expected_size:
                raise ExportArtifactIntegrityError("Export artifact exceeds its recorded size")
            digest.update(chunk)
            prepared_file.write(chunk)

        if prepared_size != expected_size:
            raise ExportArtifactIntegrityError("Export artifact size does not match its record")
        if digest.hexdigest() != expected_sha256:
            raise ExportArtifactIntegrityError("Export artifact digest does not match its record")
        prepared_file.seek(0)
        return PreparedExportDownload(file=prepared_file, size=prepared_size)
    except BaseException:
        prepared_file.close()
        raise


def iter_prepared_export_download(
    prepared: PreparedExportDownload,
) -> Iterator[bytes]:
    """Read an already verified artifact in bounded chunks."""
    while chunk := prepared.file.read(EXPORT_DOWNLOAD_CHUNK_BYTES):
        yield chunk


def _media_type_for_export_format(fmt: ExportFormat) -> str:
    media_types = {
        ExportFormat.PDF: "application/pdf",
        ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ExportFormat.CSV: "application/zip",
        ExportFormat.JSON: "application/json",
        ExportFormat.DOCX: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ExportFormat.PPTX: (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    }
    return media_types.get(fmt, "application/octet-stream")
