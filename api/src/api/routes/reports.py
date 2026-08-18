"""Report retrieval and export routes."""

import asyncio
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import ContentStream
from starlette.types import Receive, Scope, Send

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import Analysis, ExportFormat, ExportStatus, User, UserRole
from api.deps import (
    AuthenticatedPrincipal,
    DBSession,
    require_permission,
    require_permission_or_api_key_scope,
)
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.common import ReportSearchResponse, StatusResponse
from api.schemas.report_evidence_search import (
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from api.schemas.reports import (
    ExportJobResponse,
    ExportRequest,
    ExternalReportGrantActivityResponse,
    ExternalReportGrantCreatedResponse,
    ExternalReportGrantCreateRequest,
    ExternalReportGrantListResponse,
    FTOReportResponse,
    ReportIdentityResolutionResponse,
    ReportSearchRequest,
    ReportSummaryResponse,
    ReportWorkspaceSummaryResponse,
)
from api.services.export_authorization import is_export_format_allowed_for_role
from api.services.export_receipts import ExportReceiptIntegrityError, verify_export_receipt
from api.services.external_report_grants import (
    CreatedGrant,
    activate_external_report_grant,
    claim_external_report_delivery_dispatch,
    create_external_report_grant,
    list_external_report_grant_activity,
    list_external_report_grants,
    record_external_report_delivery_result,
    revoke_external_report_grant,
    send_external_report_grant_invitation,
    serialize_grant,
)
from api.services.object_storage import content_disposition_attachment
from api.services.report_access import require_completed_report_payload
from api.services.report_content import (
    filter_risk_ratings as _filter_risk_ratings,
)
from api.services.report_content import (
    get_report_summary_for_org as _get_report_summary_for_org,
)
from api.services.report_content import (
    load_report_for_org as _load_report_for_org,
)
from api.services.report_content import (
    search_report_content as _search_report_content,
)
from api.services.report_content import (
    search_report_evidence_for_org as _search_report_evidence_for_org,
)
from api.services.report_content import (
    search_report_for_org as _search_report_for_org,
)
from api.services.report_evidence_search import (
    search_report_evidence_impl as _search_report_evidence_impl,
)
from api.services.report_workspace import (
    build_report_workspace_summary_for_org_impl as _build_report_workspace_summary_for_org,
)
from api.services.reports import (
    ExportArtifactIntegrityError,
    PreparedExportDownload,
    _media_type_for_export_format,
    delete_export_job,
    ensure_analysis_export_ready,
    get_analysis_for_org,
    get_export_job_for_org,
    iter_prepared_export_download,
    prepare_export_download,
    queue_export_job,
    resolve_export_download,
)

_EXPORT_DOWNLOAD_SLOTS = asyncio.Semaphore(2)
_EXPORT_DOWNLOAD_SLOT_WAIT_SECONDS = 10.0


class _PreparedExportCleanup:
    def __init__(self, prepared: PreparedExportDownload) -> None:
        self._prepared = prepared
        self._completed = False

    async def __call__(self) -> None:
        if self._completed:
            return
        self._completed = True
        try:
            await run_in_threadpool(self._prepared.close)
        finally:
            _EXPORT_DOWNLOAD_SLOTS.release()


class _VerifiedExportStreamingResponse(StreamingResponse):
    """Guarantee verified spool cleanup and slot release on disconnects."""

    def __init__(
        self,
        content: ContentStream,
        *,
        cleanup: _PreparedExportCleanup,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ) -> None:
        self._export_cleanup = cleanup
        super().__init__(
            content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._export_cleanup()


def _export_retry_after_seconds(lease_expires_at: datetime | None) -> int | None:
    if lease_expires_at is None:
        return None
    if lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
    remaining_seconds = int((lease_expires_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())
    return max(0, remaining_seconds)


def _public_export_error_message(error_message: str | None, *, retryable: bool) -> str | None:
    if retryable or not error_message:
        return None
    safe_prefixes = (
        "Export blocked:",
        "Export failed: Report data is unavailable",
        "Export failed: Report payload failed export schema validation.",
        "Export failed: Repeated worker retries were exhausted.",
        "Export failed: Unsupported format:",
    )
    if error_message.startswith(safe_prefixes):
        return _redact_export_error_details(error_message)
    return "Export failed. Please try again or contact support."


_EXPORT_ERROR_REDACTIONS = (
    re.compile(r"\b(?:gs|s3)://[^\s,;)]*"),
    re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s:;,)]+/)*[^\s:;,)]+"),
    re.compile(r"\b[A-Za-z]:\\[^\s,;)]*"),
)


def _redact_export_error_details(message: str) -> str:
    redacted = message
    for pattern in _EXPORT_ERROR_REDACTIONS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _export_manifest_hash_for_response(job: object) -> str | None:
    value = getattr(job, "manifest_hash", None)
    if isinstance(value, str) and len(value) == 64:
        return value
    return None


def _export_sha256_for_response(job: object, field_name: str) -> str | None:
    value = getattr(job, field_name, None)
    if isinstance(value, str) and len(value) == 64:
        return value
    return None


def _export_completed_at_for_response(job: object) -> datetime | None:
    value = getattr(job, "completed_at", None)
    if isinstance(value, datetime):
        return value
    return None


def _export_superseded_at_for_response(job: object) -> datetime | None:
    value = getattr(job, "superseded_at", None)
    if isinstance(value, datetime):
        return value
    return None


def _export_superseded_reason_for_response(job: object) -> str | None:
    value = getattr(job, "superseded_reason", None)
    if isinstance(value, str) and value:
        return value
    return None


def _export_superseded_conclusion_ids_for_response(job: object) -> list[str]:
    value = getattr(job, "superseded_conclusion_ids", None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _export_manifest_schema_version_for_response(job: object) -> str | None:
    value = getattr(job, "manifest_schema_version", None)
    if isinstance(value, str) and value:
        return value
    return None


def _export_manifest_snapshot_for_response(job: object) -> dict | None:
    value = getattr(job, "manifest_snapshot", None)
    return _sanitize_export_manifest_snapshot(value)


def _sanitize_export_manifest_snapshot(value: object) -> dict | None:
    if not isinstance(value, dict) or not value:
        return None

    artifact = _dict_value(value, "artifact")
    branding = _dict_value(value, "branding")
    readiness = _dict_value(value, "readiness")
    report = _dict_value(value, "report")
    review = _dict_value(value, "review")
    source_health = _dict_value(value, "source_health")
    snapshot: dict = {}
    version = _str_value(value, "version")
    generated_at = _str_value(value, "generated_at")

    if version:
        snapshot["version"] = version
    if generated_at:
        snapshot["generated_at"] = generated_at
    if artifact:
        snapshot["artifact"] = {
            key: artifact[key]
            for key in (
                "audience",
                "audience_label",
                "file_size_bytes",
                "format",
                "format_label",
                "sections",
                "sha256",
                "title",
            )
            if key in artifact
        }
    if report:
        snapshot["report"] = {
            key: report[key]
            for key in ("fingerprint", "generated_at", "pipeline_version", "report_id", "risk")
            if key in report
        }
    if readiness:
        snapshot["readiness"] = {
            key: readiness[key]
            for key in (
                "blocking_jurisdictions",
                "export_ready",
                "review_status",
                "trust_mode",
            )
            if key in readiness
        }
    if review:
        snapshot["review"] = {
            key: review[key]
            for key in (
                "completion_pct",
                "decision_counts",
                "reviewer_decision_count",
            )
            if key in review
        }
    if source_health:
        snapshot["source_health"] = {
            key: source_health[key]
            for key in (
                "healthy_count",
                "listed_source_count",
                "total_count",
            )
            if key in source_health
        }
    if branding:
        snapshot["branding"] = {
            key: branding[key]
            for key in (
                "accent_color",
                "display_name",
                "firm_name",
                "has_custom_logo",
                "primary_color",
                "suppresses_praviar_branding",
                "white_label",
            )
            if key in branding
        }

    return snapshot or None


def _dict_value(value: dict, key: str) -> dict:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def _str_value(value: dict, key: str) -> str | None:
    nested = value.get(key)
    return nested if isinstance(nested, str) and nested else None


# Reusable 4xx Problem Details response schemas for OpenAPI spec
_PROBLEM_4XX = {
    "403": {
        "description": "Forbidden",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "404": {
        "description": "Not found",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "422": {
        "description": "Validation error",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "429": {
        "description": "Rate limit exceeded",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
}

logger = structlog.get_logger()

router = APIRouter()

ReportFullPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("report.view_full", "reports:read")),
]
ReportSummaryPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("report.view_summary", "reports:read")),
]
ReportExportPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("report.export", "reports:export")),
]


def _must_filter_risk_for_user(user: AuthenticatedPrincipal) -> bool:
    return get_settings().require_attorney_role_for_risk_ratings and user.role not in (
        UserRole.ATTORNEY,
        UserRole.ADMIN,
    )


@router.get(
    "/reports/resolve/{identifier}",
    response_model=ReportIdentityResolutionResponse,
)
async def resolve_report_identity(
    identifier: str,
    user: ReportFullPrincipal,
    db: DBSession,
) -> ReportIdentityResolutionResponse:
    """Resolve an org-scoped analysis ID or immutable report ID to its analysis."""
    normalized_identifier = identifier.strip()
    if not normalized_identifier or len(normalized_identifier) > 200:
        raise APIError(422, "Unprocessable Entity", "Invalid report reference")

    analysis: Analysis | None = None
    try:
        analysis_id = uuid.UUID(normalized_identifier)
    except ValueError:
        analysis_id = None

    # Prefer an exact analysis identity if a UUID happens to collide with a
    # report reference. This preserves the canonical analysis route contract.
    if analysis_id is not None:
        result = await db.execute(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.org_id == user.org_id,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is not None:
            analysis = candidate

    matched_by: Literal["analysis_id", "report_id"] = "analysis_id"
    if analysis is None:
        result = await db.execute(
            select(Analysis).where(
                Analysis.org_id == user.org_id,
                Analysis.report_data.isnot(None),
                func.jsonb_typeof(Analysis.report_data) == "object",
                Analysis.report_data["report_id"].astext == normalized_identifier,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is not None:
            analysis = candidate
            matched_by = "report_id"

    if analysis is None:
        raise APIError(404, "Not Found", "Report reference not found")

    report_data = require_completed_report_payload(
        analysis,
        detail="Report reference not found",
    )
    return ReportIdentityResolutionResponse(
        analysis_id=analysis.id,
        report_id=str(report_data.get("report_id") or ""),
        matched_by=matched_by,
    )


@router.get(
    "/reports/{analysis_id}",
    response_model=FTOReportResponse,
    openapi_extra={
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "aspirin_report": {
                                "summary": "Completed FTO report for aspirin",
                                "value": {
                                    "analysis_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                                    "compound_name": "aspirin",
                                    "compound_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                                    "overall_risk_rating": "low",
                                    "executive_summary": (
                                        "No blocking patents were identified in"
                                        " the recorded US/EP evidence reviewed."
                                        " Counsel review is required before"
                                        " relying on absence-of-risk conclusions."
                                    ),
                                    "patent_landscape": [],
                                    "jurisdictions_searched": ["US", "EP"],
                                    "completed_at": "2026-05-29T09:04:12Z",
                                },
                            }
                        }
                    }
                }
            },
            **_PROBLEM_4XX,
        }
    },
)
async def get_report(
    analysis_id: uuid.UUID,
    user: ReportFullPrincipal,
    db: DBSession,
) -> dict:
    """Get the full FTO report for a completed analysis."""
    logger.info("get_report", analysis_id=str(analysis_id), user_id=str(user.id))

    report_data = await _load_report_for_org(db, analysis_id=analysis_id, org_id=user.org_id)

    if _must_filter_risk_for_user(user):
        logger.warning(
            "get_report_risk_restricted",
            user_role=user.role.value,
            analysis_id=str(analysis_id),
        )
        raise APIError(
            403,
            "Forbidden",
            "Full report conclusions are restricted to attorney-role users; use the report summary",
        )

    return report_data


@router.get("/reports/{analysis_id}/summary", response_model=ReportSummaryResponse)
async def get_report_summary(
    analysis_id: uuid.UUID,
    user: ReportSummaryPrincipal,
    db: DBSession,
) -> dict:
    """Get executive summary (available to all roles including clients)."""
    try:
        return await _get_report_summary_for_org(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            risk_ratings_restricted=_must_filter_risk_for_user(user),
        )
    except APIError:
        logger.warning("get_summary_not_found", analysis_id=str(analysis_id))
        raise


@router.get(
    "/reports/{analysis_id}/workspace-summary", response_model=ReportWorkspaceSummaryResponse
)
async def get_report_workspace_summary(
    analysis_id: uuid.UUID,
    user: ReportFullPrincipal,
    db: DBSession,
) -> ReportWorkspaceSummaryResponse:
    """Return governed workspace metadata for a completed report."""
    logger.info(
        "get_report_workspace_summary",
        analysis_id=str(analysis_id),
        user_id=str(user.id),
        org_id=str(user.org_id),
    )
    return await _build_report_workspace_summary_for_org(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        get_analysis_for_org_fn=get_analysis_for_org,
        risk_restricted=_must_filter_risk_for_user(user),
    )


@router.post("/reports/{analysis_id}/export", response_model=ExportJobResponse)
@limiter.limit("20/minute")
async def export_report(
    analysis_id: uuid.UUID,
    body: ExportRequest,
    user: ReportExportPrincipal,
    db: DBSession,
    request: Request,
) -> dict:
    """Trigger report export (PDF/DOCX/XLSX/CSV/JSON)."""
    fmt = ExportFormat(body.format)
    logger.info(
        "export_report",
        analysis_id=str(analysis_id),
        format=fmt.value,
        sections=body.sections,
        user_id=str(user.id),
    )

    if _must_filter_risk_for_user(user):
        logger.warning(
            "export_risk_restricted",
            analysis_id=str(analysis_id),
            user_id=str(user.id),
            role=user.role.value,
            format=fmt.value,
            audience=body.audience,
        )
        raise APIError(
            403,
            "Forbidden",
            "Report exports containing restricted risk conclusions are "
            "restricted to attorney-role users",
        )

    # Role-based format restrictions
    if not is_export_format_allowed_for_role(user.role, fmt):
        if user.role == UserRole.CLIENT:
            logger.warning("export_forbidden_role", user_id=str(user.id), format=fmt.value)
            raise APIError(403, "Forbidden", "Clients cannot export full reports")
        if user.role == UserRole.SCIENTIST:
            logger.warning("export_forbidden_format", user_id=str(user.id), format=fmt.value)
            raise APIError(403, "Forbidden", "Scientists can export PDF, JSON, CSV, or XLSX")
        logger.warning("export_forbidden_role", user_id=str(user.id), format=fmt.value)
        raise APIError(403, "Forbidden", "Role cannot export full reports")

    analysis = await get_analysis_for_org(db, analysis_id=analysis_id, org_id=user.org_id)

    await ensure_analysis_export_ready(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        analysis=analysis,
    )

    dispatch = await queue_export_job(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        user_id=user.id,
        export_format=fmt,
        sections=[str(section) for section in body.sections or []],
        audience=body.audience,
        analysis=analysis,
        request=request,
    )
    return {"job_id": dispatch.job_id, "status": dispatch.status, "format": dispatch.format}


@router.get("/exports/{job_id}", response_model=ExportJobResponse)
async def get_export_status(
    job_id: uuid.UUID,
    user: ReportExportPrincipal,
    db: DBSession,
) -> dict:
    """Poll export job status. Returns download_url when completed."""
    if _must_filter_risk_for_user(user):
        raise APIError(
            403,
            "Forbidden",
            "Report export status is restricted to attorney-role users",
        )
    job = await get_export_job_for_org(db, job_id=job_id, org_id=user.org_id)
    if job.status == ExportStatus.COMPLETED:
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
    superseded_at = _export_superseded_at_for_response(job)

    download_url = None
    if job.status == ExportStatus.COMPLETED and job.file_url and superseded_at is None:
        settings = get_settings()
        download_url = f"{settings.api_prefix}/exports/{job.id}/download"

    processing_lease_expires_at = getattr(job, "processing_lease_expires_at", None)
    retryable = job.status == ExportStatus.FAILED and processing_lease_expires_at is not None

    return {
        "job_id": job.id,
        "status": ExportStatus.PROCESSING.value if retryable else job.status.value,
        "download_url": download_url,
        "format": job.format.value,
        "file_size_bytes": job.file_size_bytes,
        "manifest_schema_version": _export_manifest_schema_version_for_response(job),
        "manifest_hash": _export_manifest_hash_for_response(job),
        "manifest_snapshot": _export_manifest_snapshot_for_response(job),
        "artifact_sha256": _export_sha256_for_response(job, "artifact_sha256"),
        "report_payload_sha256": _export_sha256_for_response(job, "report_payload_sha256"),
        "artifact_currency": "superseded" if superseded_at is not None else "current",
        "superseded_at": superseded_at,
        "superseded_reason": _export_superseded_reason_for_response(job),
        "superseded_conclusion_ids": _export_superseded_conclusion_ids_for_response(job),
        "completed_at": _export_completed_at_for_response(job),
        "error_message": _public_export_error_message(
            job.error_message or None,
            retryable=retryable,
        ),
        "retryable": retryable,
        "retry_after_seconds": (
            _export_retry_after_seconds(processing_lease_expires_at) if retryable else None
        ),
    }


@router.delete(
    "/exports/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_export(
    job_id: uuid.UUID,
    user: ReportExportPrincipal,
    db: DBSession,
    request: Request,
) -> Response:
    """Delete a terminal export record and its private artifact."""
    if _must_filter_risk_for_user(user):
        raise APIError(
            403,
            "Forbidden",
            "Report export deletion is restricted to attorney-role users",
        )
    await delete_export_job(
        db,
        job_id=job_id,
        org_id=user.org_id,
        user_id=user.id,
        allow_org_wide=user.role in {UserRole.ADMIN, UserRole.ATTORNEY},
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/exports/{job_id}/download", response_model=None)
async def download_export_file(
    job_id: uuid.UUID,
    user: ReportExportPrincipal,
    db: DBSession,
) -> FileResponse | StreamingResponse:
    """Download a completed export file."""
    if _must_filter_risk_for_user(user):
        raise APIError(
            403,
            "Forbidden",
            "Report export downloads are restricted to attorney-role users",
        )
    export = await resolve_export_download(db, job_id=job_id, org_id=user.org_id)

    if export.gcs_uri is not None:
        try:
            await asyncio.wait_for(
                _EXPORT_DOWNLOAD_SLOTS.acquire(),
                timeout=_EXPORT_DOWNLOAD_SLOT_WAIT_SECONDS,
            )
        except TimeoutError as exc:
            raise APIError(
                503,
                "Service Unavailable",
                "Export download capacity is temporarily unavailable",
            ) from exc
        try:
            prepared = await run_in_threadpool(prepare_export_download, export)
        except ExportArtifactIntegrityError as exc:
            _EXPORT_DOWNLOAD_SLOTS.release()
            logger.error(
                "export_download_integrity_failed",
                job_id=str(job_id),
                error_type=type(exc).__name__,
            )
            raise APIError(
                409,
                "Conflict",
                "Export artifact failed integrity verification",
            ) from exc
        except Exception as exc:
            _EXPORT_DOWNLOAD_SLOTS.release()
            logger.error(
                "export_download_preparation_failed",
                job_id=str(job_id),
                error_type=type(exc).__name__,
            )
            raise APIError(
                503,
                "Service Unavailable",
                "Export download is temporarily unavailable",
            ) from exc
        except BaseException:
            _EXPORT_DOWNLOAD_SLOTS.release()
            raise
        cleanup = _PreparedExportCleanup(prepared)
        return _VerifiedExportStreamingResponse(
            iter_prepared_export_download(prepared),
            media_type=_media_type_for_export_format(export.job.format),
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": content_disposition_attachment(export.filename),
                "Content-Length": str(export.job.file_size_bytes),
                "X-Content-Type-Options": "nosniff",
            },
            background=BackgroundTask(cleanup),
            cleanup=cleanup,
        )

    if export.local_path is None:
        raise APIError(404, "Not Found", "Export file not found")
    # Defence-in-depth: re-resolve at the call site even though
    # resolve_export_download() already performs this check.  Guards against
    # future refactors that short-circuit the service layer.
    resolved = Path(export.local_path).resolve()
    expected_export_dir = Path(get_settings().export_dir).resolve()
    if not resolved.is_relative_to(expected_export_dir):
        raise APIError(403, "Forbidden", "Export path resolves outside allowed directory")
    return FileResponse(
        path=resolved,
        media_type=_media_type_for_export_format(export.job.format),
        filename=export.filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/reports/{analysis_id}/share",
    response_model=ExternalReportGrantCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def create_share_grant(
    analysis_id: uuid.UUID,
    body: ExternalReportGrantCreateRequest,
    user: Annotated[User, Depends(require_permission("report.share"))],
    db: DBSession,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict:
    """Create and email a recipient-bound external report grant."""
    try:
        created = await create_external_report_grant(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            created_by=user.id,
            recipient_email=str(body.recipient_email),
            expires_in_days=body.expires_in_days,
            max_views=body.max_views,
            idempotency_key=idempotency_key,
        )
        if not created.is_replay:
            await write_audit_log(
                db,
                org_id=user.org_id,
                user_id=user.id,
                analysis_id=analysis_id,
                action="report.share.grant_created",
                details={
                    "external_grant_id": str(created.grant.id),
                    "recipient_email": created.grant.recipient_email_normalized,
                    "recipient_domain": created.grant.recipient_domain,
                    "expires_at": created.grant.expires_at.isoformat(),
                    "max_views": created.grant.max_views,
                    "download_allowed": False,
                },
                request=request,
                fail_closed=True,
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    try:
        dispatch = await claim_external_report_delivery_dispatch(
            db,
            grant_id=created.grant.id,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        if dispatch.needs_provider_submission:
            await write_audit_log(
                db,
                org_id=user.org_id,
                user_id=user.id,
                analysis_id=analysis_id,
                action="report.share.delivery_dispatch_started",
                details={
                    "external_grant_id": str(dispatch.grant.id),
                    "recipient_domain": dispatch.grant.recipient_domain,
                    "provider_submission_attempt": 1,
                },
                request=request,
                fail_closed=True,
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    if dispatch.grant.delivery_state == "active":
        return {
            **serialize_grant(dispatch.grant),
            "share_token": None,
            "invitation_status": "provider_accepted",
            "replayed": True,
        }

    if dispatch.needs_provider_submission:
        submission = await send_external_report_grant_invitation(
            CreatedGrant(
                grant=dispatch.grant,
                raw_token=dispatch.raw_token,
                is_replay=created.is_replay,
            )
        )
        try:
            delivery = await record_external_report_delivery_result(
                db,
                grant_id=created.grant.id,
                analysis_id=analysis_id,
                org_id=user.org_id,
                result=submission,
            )
            if submission.status != "accepted":
                action = (
                    "report.share.delivery_rejected"
                    if submission.status == "rejected"
                    else "report.share.delivery_outcome_unknown"
                )
                await write_audit_log(
                    db,
                    org_id=user.org_id,
                    user_id=user.id,
                    analysis_id=analysis_id,
                    action=action,
                    details={
                        "external_grant_id": str(delivery.id),
                        "recipient_domain": delivery.recipient_domain,
                        "provider_resubmission_blocked": True,
                    },
                    request=request,
                    fail_closed=True,
                )
            else:
                await write_audit_log(
                    db,
                    org_id=user.org_id,
                    user_id=user.id,
                    analysis_id=analysis_id,
                    action="report.share.delivery_provider_accepted",
                    details={
                        "external_grant_id": str(delivery.id),
                        "recipient_domain": delivery.recipient_domain,
                        "provider_message_id": delivery.delivery_provider_message_id,
                    },
                    request=request,
                    fail_closed=True,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        if submission.status == "rejected":
            raise APIError(
                503,
                "Invitation rejected",
                "The email provider rejected this invitation; use a new Idempotency-Key to retry",
            )
        if submission.status == "outcome_unknown":
            raise APIError(
                503,
                "Invitation outcome unknown",
                "The provider outcome could not be confirmed and this invitation "
                "will not be resent",
            )

    try:
        activated = await activate_external_report_grant(
            db,
            grant_id=created.grant.id,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="report.share.invitation_sent",
            details={
                "external_grant_id": str(activated.grant.id),
                "recipient_email": activated.grant.recipient_email_normalized,
                "recipient_domain": activated.grant.recipient_domain,
            },
            request=request,
            fail_closed=True,
        )
        for rotated_grant_id in activated.rotated_grant_ids:
            await write_audit_log(
                db,
                org_id=user.org_id,
                user_id=user.id,
                analysis_id=analysis_id,
                action="report.share.grant_revoked_by_reissue",
                details={
                    "external_grant_id": str(rotated_grant_id),
                    "replacement_external_grant_id": str(activated.grant.id),
                    "recipient_domain": activated.grant.recipient_domain,
                },
                request=request,
                fail_closed=True,
            )
        if activated.rotated_grant_ids:
            await write_audit_log(
                db,
                org_id=user.org_id,
                user_id=user.id,
                analysis_id=analysis_id,
                action="report.share.recipient_grants_rotated",
                details={
                    "replacement_external_grant_id": str(activated.grant.id),
                    "recipient_email": activated.grant.recipient_email_normalized,
                    "recipient_domain": activated.grant.recipient_domain,
                    "revoked_external_grant_ids": [
                        str(grant_id) for grant_id in activated.rotated_grant_ids
                    ],
                    "revoked_grant_count": len(activated.rotated_grant_ids),
                },
                request=request,
                fail_closed=True,
            )
        await db.commit()
    except Exception:
        await db.rollback()
        # An unconfirmed invitation is structurally incapable of challenge or
        # report access because invitation_sent_at remains NULL.
        raise
    return {
        **serialize_grant(activated.grant),
        "share_token": dispatch.raw_token,
        "invitation_status": "provider_accepted",
        "replayed": created.is_replay,
    }


@router.get(
    "/reports/{analysis_id}/share",
    response_model=ExternalReportGrantListResponse,
)
@limiter.limit("10/minute")
async def get_share_grants(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("report.share"))],
    db: DBSession,
    request: Request,
) -> dict:
    """List recipient-bound grants without exposing any secret."""
    grants = await list_external_report_grants(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    return {"items": [serialize_grant(grant) for grant in grants]}


@router.get(
    "/reports/{analysis_id}/share/{grant_id}/activity",
    response_model=ExternalReportGrantActivityResponse,
)
@limiter.limit("20/minute")
async def get_share_grant_activity(
    analysis_id: uuid.UUID,
    grant_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("report.share"))],
    db: DBSession,
    request: Request,
) -> dict:
    """List immutable non-secret events for one exact recipient grant."""
    items = await list_external_report_grant_activity(
        db,
        grant_id=grant_id,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    return {"items": items}


@router.delete(
    "/reports/{analysis_id}/share/{grant_id}",
    response_model=StatusResponse,
)
@limiter.limit("10/minute")
async def revoke_share_grant(
    analysis_id: uuid.UUID,
    grant_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("report.share"))],
    db: DBSession,
    request: Request,
) -> dict:
    """Revoke one recipient grant and invalidate every outstanding proof."""
    try:
        grant = await revoke_external_report_grant(
            db,
            grant_id=grant_id,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="report.share.grant_revoked",
            details={
                "external_grant_id": str(grant.id),
                "recipient_email": grant.recipient_email_normalized,
                "recipient_domain": grant.recipient_domain,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"status": "revoked"}


@router.post("/reports/{analysis_id}/search", response_model=ReportSearchResponse)
async def search_report(
    analysis_id: uuid.UUID,
    body: ReportSearchRequest,
    user: ReportFullPrincipal,
    db: DBSession,
) -> dict:
    """Search within a report's content using keyword matching."""
    query_text = body.query.strip()
    if _must_filter_risk_for_user(user):
        analysis = await get_analysis_for_org(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        report_data = require_completed_report_payload(analysis)
        logger.info(
            "search_report_upl_risk_filtered",
            user_role=user.role.value,
            analysis_id=str(analysis_id),
        )
        return _search_report_content(_filter_risk_ratings(report_data), query_text)

    return await _search_report_for_org(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        query_text=query_text,
    )


@router.post("/reports/{analysis_id}/evidence-search", response_model=EvidenceSearchResponse)
@limiter.limit("10/minute")
async def search_report_evidence(
    analysis_id: uuid.UUID,
    body: EvidenceSearchRequest,
    user: ReportFullPrincipal,
    db: DBSession,
    request: Request,
) -> dict:
    """Search governed evidence already collected into a completed report."""
    query_text = body.query.strip()
    if _must_filter_risk_for_user(user):
        if body.retrieval_mode == "external_evidence":
            raise APIError(
                403,
                "Forbidden",
                "Governed external evidence expansion is restricted to attorney-role users",
            )
        analysis = await get_analysis_for_org(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        report_data = require_completed_report_payload(analysis)
        logger.info(
            "search_report_evidence_upl_risk_filtered",
            user_role=user.role.value,
            analysis_id=str(analysis_id),
            retrieval_mode=body.retrieval_mode,
        )
        return _search_report_evidence_impl(
            _filter_risk_ratings(report_data),
            query_text,
            external_retrieval_allowed=False,
            org_id=user.org_id,
        )

    logger.info(
        "search_report_evidence",
        analysis_id=str(analysis_id),
        user_id=str(user.id),
        org_id=str(user.org_id),
        retrieval_mode=body.retrieval_mode,
    )
    return await _search_report_evidence_for_org(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        query_text=query_text,
        retrieval_mode=body.retrieval_mode,
    )
