"""Export job helpers for worker tasks."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path
from typing import Any, TypeAlias, cast

from sqlalchemy.orm import Session

from api.services.export_receipts import (
    EXPORT_MANIFEST_SCHEMA_VERSION,
    export_manifest_hash,
    export_manifest_signature,
)
from api.services.report_access import filter_current_reviewer_decisions, report_payload_fingerprint

MAX_EXPORT_ERROR_MESSAGE_CHARS = 1000
MIN_EXPORT_PROCESSING_LEASE_SECONDS = 60
EXPORT_PROCESSING_LEASE_BUFFER_SECONDS = 300
MAX_EXPORT_RETRYABLE_FAILURE_ATTEMPTS = 3
EXPORT_REQUESTER_NOT_AUTHORIZED_ERROR = "export_requester_not_authorized"
EXPORT_REQUESTER_FULL_REPORT_DENIED_DETAIL = (
    "Export requesting user is not permitted to render full reports."
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")

ExportJobResult: TypeAlias = dict[str, object]


@dataclass
class _ExportExecutionState:
    execution_id: uuid.UUID | None = None


@dataclass(frozen=True)
class _ExportWorkerRuntime:
    settings: Any
    analysis_model: Any
    export_format_enum: Any
    export_job_model: Any
    export_status_enum: Any
    organization_model: Any
    user_model: Any
    load_branding: Any


@dataclass(frozen=True)
class _ExportClaim:
    job: Any
    execution_id: uuid.UUID


@dataclass(frozen=True)
class _ExportReportSnapshot:
    report_data: dict[str, Any]
    report: Any
    review_status: Any
    reviewer_decision_rows: list[Any]
    reviewer_decisions: list[dict[str, Any]]
    rendered_report_fingerprint: str
    rendered_decision_state: list[dict[str, Any]]
    rendered_review_state: dict[str, str | int | None]


@dataclass(frozen=True)
class _ExportPreparation:
    job: Any
    analysis: Any
    report_snapshot: _ExportReportSnapshot
    export_options: Any
    export_branding: Any


@dataclass(frozen=True)
class _RenderedExport:
    preparation: _ExportPreparation
    file_path: Path
    file_size_bytes: int
    artifact_sha256: str


@dataclass(frozen=True)
class _PersistenceSnapshot:
    rendered: _RenderedExport
    job: Any
    analysis: Any
    report_data: dict[str, Any]
    review_status: Any
    reviewer_decision_rows: list[Any]
    reviewer_decisions: list[dict[str, Any]]


@dataclass(frozen=True)
class _FailedClaimTransition:
    job: Any | None = None
    stale_result: ExportJobResult | None = None


def _safe_export_error_message(prefix: str, detail: str = "") -> str:
    normalized_detail = " ".join(_CONTROL_CHARS_RE.sub(" ", detail).split())
    message = prefix if not normalized_detail else f"{prefix}: {normalized_detail}"
    if len(message) > MAX_EXPORT_ERROR_MESSAGE_CHARS:
        return message[: MAX_EXPORT_ERROR_MESSAGE_CHARS - 3].rstrip() + "..."
    return message


def _validate_export_report_payload(report_data: dict):
    from praviar_pipeline.models.report import FTOReport

    known_keys = set(FTOReport.model_fields)
    return FTOReport.model_validate({k: v for k, v in report_data.items() if k in known_keys})


def _mark_export_failed(job, message: str) -> None:
    from api.db.models import ExportStatus

    job.status = ExportStatus.FAILED
    job.error_message = message
    job.processing_execution_id = None
    job.processing_lease_expires_at = None


def _full_export_requester_block_reason(db: Session, user_model, job) -> str:
    """Return the fail-closed reason when a queued full export lacks an authorized user."""
    from api.db.models import ExportFormat, UserRole
    from api.services.export_authorization import is_export_format_allowed_for_role
    from api.services.risk_access import risk_ratings_restricted_for_role

    user_id = getattr(job, "user_id", None)
    if user_id is None:
        return "Export job has no requesting user."

    user = db.get(user_model, user_id)
    if user is None:
        return "Export requesting user no longer exists."

    if str(getattr(user, "org_id", "")) != str(getattr(job, "org_id", "")):
        return "Export requesting user does not belong to the export organization."

    role = getattr(user, "role", None)
    role_value = str(getattr(role, "value", role) or "")
    format_value = getattr(job, "format", None)
    if not isinstance(format_value, str):
        return EXPORT_REQUESTER_FULL_REPORT_DENIED_DETAIL
    try:
        current_role = UserRole(role_value)
        current_format = ExportFormat(format_value)
    except ValueError:
        return EXPORT_REQUESTER_FULL_REPORT_DENIED_DETAIL
    if not is_export_format_allowed_for_role(current_role, current_format):
        return EXPORT_REQUESTER_FULL_REPORT_DENIED_DETAIL
    if risk_ratings_restricted_for_role(current_role):
        return EXPORT_REQUESTER_FULL_REPORT_DENIED_DETAIL

    return ""


def _mark_export_retryable_failure(job, message: str, *, now: datetime) -> bool:
    from api.db.models import ExportStatus

    retry_attempts = _export_retry_attempts(job) + 1
    job.retry_attempts = retry_attempts
    if retry_attempts >= MAX_EXPORT_RETRYABLE_FAILURE_ATTEMPTS:
        _mark_export_failed(
            job,
            _safe_export_error_message(
                "Export failed",
                "Repeated worker retries were exhausted.",
            ),
        )
        return False

    job.status = ExportStatus.FAILED
    job.error_message = message
    # Exponential back-off: 60s, 120s, ... so rapid retries don't exhaust all
    # attempts instantly. Setting lease = now would make the job immediately
    # reclaimable with zero enforced delay.
    from datetime import timedelta

    job.processing_lease_expires_at = now + timedelta(seconds=60 * retry_attempts)
    return True


def _commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _export_retry_attempts(job) -> int:
    retry_attempts = getattr(job, "retry_attempts", 0)
    if isinstance(retry_attempts, int):
        return max(0, retry_attempts)
    return 0


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _export_processing_lease_ttl_seconds(settings) -> int:
    try:
        hard_limit_seconds = int(getattr(settings, "celery_hard_time_limit", 0))
    except (TypeError, ValueError):
        hard_limit_seconds = 0
    return max(hard_limit_seconds, MIN_EXPORT_PROCESSING_LEASE_SECONDS) + (
        EXPORT_PROCESSING_LEASE_BUFFER_SECONDS
    )


def _as_aware_utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _processing_export_is_reclaimable(
    job,
    *,
    now: datetime,
    lease_ttl_seconds: int,
) -> bool:
    lease_expires_at = _as_aware_utc(getattr(job, "processing_lease_expires_at", None))
    if lease_expires_at is not None:
        return lease_expires_at <= now

    created_at = _as_aware_utc(getattr(job, "created_at", None))
    if created_at is None:
        return False
    return created_at + timedelta(seconds=lease_ttl_seconds) <= now


def _export_retry_later_result(
    job,
    *,
    export_job_id: str,
    now: datetime,
    reason: str,
) -> dict:
    lease_expires_at = _as_aware_utc(getattr(job, "processing_lease_expires_at", None))
    retry_after_seconds = 1
    if lease_expires_at is not None and lease_expires_at > now:
        retry_after_seconds = max(1, int((lease_expires_at - now).total_seconds()))
    return {
        "status": "retry_later",
        "job_id": export_job_id,
        "reason": reason,
        "retry_after_seconds": retry_after_seconds,
    }


def _lock_current_export_claim(db: Session, export_job_model, *, export_job_id: str, execution_id):
    job = db.get(
        export_job_model,
        export_job_id,
        with_for_update=True,
        populate_existing=True,
    )
    if not job:
        return None
    if getattr(job, "processing_execution_id", None) != execution_id:
        return None
    return job


def _stale_export_execution_result(
    logger,
    *,
    export_job_id: str,
    execution_id,
    event_name: str,
) -> dict:
    logger.warning(
        event_name,
        job_id=export_job_id,
        execution_id=str(execution_id),
    )
    return {
        "status": "retry_later",
        "job_id": export_job_id,
        "reason": "stale_execution_lost",
        "retry_after_seconds": 1,
    }


def _load_reviewer_decision_rows(db: Session, *, analysis_id, org_id) -> list:
    from sqlalchemy import select

    from api.db.models import AnalysisReviewerDecision, User, UserRole

    return list(
        db.execute(
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
        .scalars()
        .all()
    )


def _serialize_reviewer_decisions(rows: list) -> list[dict]:
    return [
        {
            "finding_type": r.finding_type,
            "finding_ref": r.finding_ref,
            "decision": r.decision,
            "note": r.note or "",
            "edited_text": r.edited_text or "",
            "reviewer_name": r.reviewer_name or "",
            "reviewer_email": r.reviewer_email or "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


def _reviewer_decision_state(rows: list) -> list[dict]:
    """Return the exact mutable decision state bound to an export render."""
    return [
        {
            "id": str(getattr(row, "id", "") or ""),
            "reviewer_user_id": str(getattr(row, "reviewer_user_id", "") or ""),
            "report_fingerprint": str(getattr(row, "report_fingerprint", "") or ""),
            **serialized,
        }
        for row, serialized in zip(
            rows,
            _serialize_reviewer_decisions(rows),
            strict=True,
        )
    ]


def _review_status_state(review_status) -> dict[str, str | int | None]:
    """Return the persisted review fields that an exported packet represents."""

    def timestamp(field: str) -> str:
        value = getattr(review_status, field, None)
        return value.isoformat() if isinstance(value, datetime) else ""

    return {
        "status": _review_status_value(review_status),
        "completion_pct": _review_completion_pct(review_status),
        "reviewer_name": str(getattr(review_status, "reviewer_name", "") or ""),
        "reviewer_email": str(getattr(review_status, "reviewer_email", "") or ""),
        "reviewed_at": timestamp("reviewed_at"),
        "updated_at": timestamp("updated_at"),
    }


def _load_review_status(db: Session, *, analysis_id, org_id):
    from sqlalchemy import select

    from api.db.models import AnalysisReviewStatus

    return db.execute(
        select(AnalysisReviewStatus).where(
            AnalysisReviewStatus.analysis_id == analysis_id,
            AnalysisReviewStatus.org_id == org_id,
        )
    ).scalar_one_or_none()


def _review_status_value(review_status) -> str:
    status = getattr(review_status, "status", None)
    return str(getattr(status, "value", status) or "")


def _review_completion_pct(review_status) -> int | None:
    value = getattr(review_status, "completion_pct", None)
    if isinstance(value, (int, float)):
        return int(round(value))
    return None


def _decision_counts(reviewer_decisions: list[dict]) -> dict[str, int]:
    counts = {"accept": 0, "edit": 0, "reject": 0}
    for decision in reviewer_decisions:
        value = str(decision.get("decision", "")).strip().lower()
        if value in counts:
            counts[value] += 1
    return counts


def _source_health_manifest(report_data: dict) -> dict:
    source_health = report_data.get("source_health")
    entries = source_health.get("entries", []) if isinstance(source_health, dict) else []
    entries = entries if isinstance(entries, list) else []
    listed_sources = report_data.get("search_sources_used")
    listed_sources = listed_sources if isinstance(listed_sources, list) else []
    summarized_entries = []
    status_counts: dict[str, int] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source", "")).strip()
        status = str(entry.get("status", "")).strip().lower() or "unknown"
        if source:
            summarized_entries.append({"source": source, "status": status})
        status_counts[status] = status_counts.get(status, 0) + 1

    healthy_count = sum(
        count
        for status, count in status_counts.items()
        if status in {"ok", "success", "healthy", "available"}
    )
    total_count = max(len(entries), len(listed_sources))

    return {
        "entries": summarized_entries,
        "healthy_count": healthy_count,
        "listed_source_count": len(listed_sources),
        "status_counts": status_counts,
        "total_count": total_count,
    }


def _branding_manifest(branding) -> dict:
    if branding is None:
        from praviar_pipeline.rendering.branding import get_default_branding

        branding = get_default_branding()

    firm_name = str(getattr(branding, "firm_name", "") or "").strip()
    display_name = str(getattr(branding, "display_name", "") or "").strip()
    logo_path = str(getattr(branding, "logo_path", "") or "").strip()
    suppresses_praviar_branding = bool(
        getattr(branding, "suppresses_praviar_branding", False),
    )
    return {
        "display_name": display_name,
        "firm_name": firm_name,
        "has_custom_logo": bool(logo_path),
        "primary_color": str(getattr(branding, "primary_color", "") or ""),
        "accent_color": str(getattr(branding, "accent_color", "") or ""),
        "suppresses_praviar_branding": suppresses_praviar_branding,
        "white_label": suppresses_praviar_branding,
    }


def _build_export_manifest_snapshot(
    *,
    analysis,
    audience: str,
    branding,
    durable_url: str,
    export_format: str,
    file_size_bytes: int,
    job,
    report_data: dict,
    report_payload_sha256: str,
    review_status,
    reviewer_decisions: list[dict],
    sections: list[str],
) -> dict:
    from praviar_pipeline.rendering.export_options import (
        export_artifact_title,
        export_audience_label,
        export_format_label,
    )

    report_id = str(report_data.get("report_id", "") or "")
    audience_label = export_audience_label(audience)
    format_label = export_format_label(export_format)
    raw_opinion_readiness = report_data.get("opinion_readiness")
    opinion_readiness = raw_opinion_readiness if isinstance(raw_opinion_readiness, dict) else {}
    raw_risk_summary = report_data.get("risk_summary")
    risk_summary = raw_risk_summary if isinstance(raw_risk_summary, dict) else {}
    return {
        "version": EXPORT_MANIFEST_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "job": {
            "id": str(getattr(job, "id", "")),
            "analysis_id": str(getattr(analysis, "id", "")),
        },
        "artifact": {
            "audience": audience,
            "audience_label": audience_label,
            "file_size_bytes": file_size_bytes,
            "format": export_format,
            "format_label": format_label,
            "sections": sections,
            "storage_locator_hash": hashlib.sha256(
                str(durable_url).encode("utf-8"),
            ).hexdigest(),
            "title": export_artifact_title(audience, export_format),
        },
        "report": {
            "fingerprint": report_payload_sha256,
            "generated_at": str(report_data.get("generated_at", "") or ""),
            "pipeline_version": str(report_data.get("praviar_pipeline_version", "") or ""),
            "report_id": report_id,
            "risk": str(risk_summary.get("overall_risk", "") or ""),
        },
        "readiness": {
            "blocking_jurisdictions": opinion_readiness.get(
                "jurisdictions_blocking_export",
                [],
            )
            if isinstance(opinion_readiness.get("jurisdictions_blocking_export"), list)
            else [],
            "export_ready": opinion_readiness.get("export_ready"),
            "review_status": _review_status_value(review_status),
            "trust_mode": str(report_data.get("trust_mode", "") or ""),
        },
        "review": {
            "completion_pct": _review_completion_pct(review_status),
            "decision_counts": _decision_counts(reviewer_decisions),
            "reviewer_decision_count": len(reviewer_decisions),
        },
        "source_health": _source_health_manifest(report_data),
        "branding": _branding_manifest(branding),
    }


def render_export_artifact(
    report,
    fmt,
    export_format_enum,
    *,
    reviewer_decisions: list[dict] | None = None,
    sections: list[str] | tuple[str, ...] | None = None,
    audience: str | None = "full",
    branding=None,
) -> Path | None:
    """Render a report to the requested format, returning the file path."""
    return _render_export_artifact(
        report,
        fmt,
        export_format_enum,
        tempdir_getter=tempfile.gettempdir,
        reviewer_decisions=reviewer_decisions,
        sections=sections,
        audience=audience,
        branding=branding,
    )


def _render_export_artifact(
    report,
    fmt,
    export_format_enum,
    *,
    tempdir_getter,
    reviewer_decisions: list[dict] | None = None,
    sections: list[str] | tuple[str, ...] | None = None,
    audience: str | None = "full",
    branding=None,
) -> Path | None:
    """Render a report to the requested format, returning the file path.

    The artifact is rendered into a unique per-invocation subdirectory under
    the export root so that concurrent export jobs never share an on-disk
    path. ``report_id`` is stable for the life of an analysis and the filename
    slug is only an 8-char prefix of it, so deriving the path from the slug
    alone made two concurrent same-analysis+format exports (and any two
    analyses whose report_ids share an 8-hex-char prefix) race on the same
    file: one job could upload a half-written or unlinked artifact while the
    other was still rendering. The unique subdirectory keeps the customer-
    facing filename clean (``fto_<slug>.<ext>``) while the path is collision
    free. See the durable GCS blob path which already namespaces by
    job/execution id.
    """
    export_root = _resolve_export_dir(tempdir_getter=tempdir_getter)
    export_dir = export_root / uuid.uuid4().hex
    export_dir.mkdir(parents=True, exist_ok=True)
    report_slug = _safe_export_report_slug(getattr(report, "report_id", ""))
    from praviar_pipeline.rendering.export_options import ExportRenderOptions

    options = ExportRenderOptions.from_values(sections, audience=audience)

    if fmt == export_format_enum.XLSX:
        from praviar_pipeline.rendering.xlsx import render_xlsx

        file_path = export_dir / f"{report_slug}.xlsx"
        file_path.write_bytes(render_xlsx(report, options=options, branding=branding))
        return file_path

    if fmt == export_format_enum.PDF:
        from praviar_pipeline.rendering.pdf import render_pdf

        file_path = export_dir / f"{report_slug}.pdf"
        render_pdf(
            report,
            file_path,
            branding=branding,
            reviewer_decisions=reviewer_decisions,
            options=options,
        )
        return file_path

    if fmt == export_format_enum.CSV:
        import zipfile

        from praviar_pipeline.rendering.csv import render_csv

        csv_files = render_csv(report, options=options)
        file_path = export_dir / f"{report_slug}.zip"
        with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in csv_files.items():
                zf.writestr(filename, content)
        return file_path

    if fmt == export_format_enum.JSON:
        file_path = export_dir / f"{report_slug}.json"
        file_path.write_text(
            json.dumps(
                _scoped_report_dump(
                    report,
                    options=options,
                    reviewer_decisions=reviewer_decisions,
                ),
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return file_path

    if fmt == export_format_enum.PPTX:
        from praviar_pipeline.rendering.pptx_report import render_pptx

        file_path = export_dir / f"{report_slug}.pptx"
        file_path.write_bytes(render_pptx(report, branding=branding, options=options))
        return file_path

    if fmt == export_format_enum.DOCX:
        from praviar_pipeline.rendering.docx_report import render_docx

        file_path = export_dir / f"{report_slug}.docx"
        file_path.write_bytes(render_docx(report, branding=branding, options=options))
        return file_path

    return None


def _scoped_report_dump(
    report,
    *,
    options,
    reviewer_decisions: list[dict] | None = None,
) -> dict:
    """Return a JSON artifact payload that respects the requested export scope."""
    from praviar_pipeline.output_safety import sanitize_error_fields_for_output

    data = cast(
        dict,
        sanitize_error_fields_for_output(dict(report.model_dump(mode="json"))),
    )
    data["export_options"] = options.model_dump()

    if options.audience in {"executive", "investor"}:
        return _restricted_audience_json_projection(data)

    if not options.includes("patent_analysis", "claim_charts", "invalidity_assessment"):
        for key in (
            "patent_analyses",
            "patent_details",
            "patent_narratives",
            "doe_assessments",
            "search_sources_used",
            "search_queries_used",
        ):
            data.pop(key, None)

    if not options.includes("claim_charts") and "patent_analyses" in data:
        analyses = data.get("patent_analyses")
        if isinstance(analyses, list):
            data["patent_analyses"] = [
                {k: v for k, v in item.items() if k != "claims_analyzed"}
                if isinstance(item, dict)
                else item
                for item in analyses
            ]

    if not options.includes("invalidity_assessment"):
        data.pop("invalidity_assessments", None)

    if options.includes("audit_trail"):
        data["reviewer_decisions"] = list(reviewer_decisions or [])
    else:
        for key in (
            "audit_trail",
            "verification",
            "analysis_failures",
            "data_limitations",
            "reviewer_decisions",
        ):
            data.pop(key, None)

    if not options.includes("pipeline_metadata"):
        for key in (
            "manifest",
            "llm_models_used",
            "total_input_tokens",
            "total_output_tokens",
            "estimated_cost_usd",
            "step_token_usage",
            "execution_profile",
        ):
            data.pop(key, None)

    if options.audience == "scientist":
        for key in (
            "claim_source_span_map",
            "evidence_artifacts",
            "matter_evidence_index",
            "patent_details",
            "prosecution_dossiers",
            "reviewer_decisions",
        ):
            data.pop(key, None)
        analyses = data.get("patent_analyses")
        if isinstance(analyses, list):
            allowed = {"patent_id", "title", "assignee", "risk_level", "expiry_date"}
            data["patent_analyses"] = [
                {key: value for key, value in item.items() if key in allowed}
                for item in analyses
                if isinstance(item, dict)
            ]
    elif options.audience not in {"attorney", "full"}:
        raise ValueError(f"Unsupported JSON audience projection: {options.audience}")
    return data


def _restricted_audience_json_projection(data: dict) -> dict:
    """Project summary JSON without claim, evidence, or patent identifiers.

    This is intentionally additive: new report fields remain private until they
    are explicitly reviewed and admitted here. Subtractive redaction is unsafe
    because nested evidence structures evolve independently of export code.
    """

    def mapping(key: str) -> dict:
        value = data.get(key)
        return value if isinstance(value, dict) else {}

    def pick(source: dict, keys: tuple[str, ...]) -> dict:
        return {key: source[key] for key in keys if key in source}

    clearance = mapping("clearance_decision")
    decision = str(clearance.get("decision") or "unclear").strip().lower()
    governed_risk = {"clear": "clear", "unclear": "medium", "blocked": "high"}.get(
        decision,
        "medium",
    )
    risk_summary = mapping("risk_summary")
    projection = pick(
        data,
        (
            "report_id",
            "generated_at",
            "praviar_pipeline_version",
            "cohort_status",
            "total_patents_found",
            "patents_after_triage",
            "scholarly_prior_art_count",
        ),
    )
    projection["compound"] = pick(
        mapping("compound"),
        ("name", "molecular_formula", "molecular_weight"),
    )
    projection["risk_summary"] = {
        "overall_risk": governed_risk,
        **pick(
            risk_summary,
            ("blocking_patents_count", "total_patents_analyzed"),
        ),
    }
    projection["clearance_decision"] = pick(
        clearance,
        ("decision", "decision_confidence", "evidence_quality"),
    )
    projection["decision_scope"] = pick(
        mapping("decision_scope"),
        ("matter_type", "jurisdictions", "asset_classes", "supports_positive_clearance"),
    )
    projection["certification_scope"] = pick(
        mapping("certification_scope"),
        (
            "certified_jurisdictions",
            "supported_jurisdictions",
            "current_matter_type_certified",
            "attorney_supervision_required",
        ),
    )
    projection["jurisdiction_decisions"] = [
        pick(
            item,
            (
                "jurisdiction",
                "decision",
                "decision_confidence",
                "evidence_quality",
                "evidence_sufficient_for_clearance",
                "supports_positive_clearance",
                "lane_status",
                "local_review_required",
                "authority_grade",
            ),
        )
        for item in data.get("jurisdiction_decisions", [])
        if isinstance(item, dict)
    ]
    projection["export_options"] = mapping("export_options")
    return projection


def _safe_export_report_slug(report_id: object) -> str:
    """Build a filesystem-safe report filename slug."""
    candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", str(report_id or "").strip())[:8]
    candidate = candidate.strip("._-")
    return f"fto_{candidate or 'report'}"


def _resolve_export_dir(*, tempdir_getter) -> Path:
    """Resolve the export directory without masking pipeline config failures."""
    try:
        pipeline_config_spec = find_spec("praviar_pipeline.config")
    except ModuleNotFoundError as exc:
        if exc.name == "praviar_pipeline":
            return Path(tempdir_getter()) / "praviar-exports"
        raise

    if pipeline_config_spec is None:
        return Path(tempdir_getter()) / "praviar-exports"

    from praviar_pipeline.config import get_settings as get_sg_settings

    return Path(get_sg_settings().resolved_output_dir) / "exports"


def _export_content_type(fmt, export_format_enum) -> str:
    if fmt == export_format_enum.PDF:
        return "application/pdf"
    if fmt == export_format_enum.XLSX:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == export_format_enum.CSV:
        return "application/zip"
    if fmt == export_format_enum.JSON:
        return "application/json"
    if fmt == export_format_enum.PPTX:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if fmt == export_format_enum.DOCX:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _persist_export_artifact(
    *,
    file_path: Path,
    job,
    analysis,
    settings,
    export_format_enum,
    execution_id,
    artifact_sha256: str,
) -> str:
    """Persist rendered export artifact and return the durable URL/key.

    Production uses GCS via ADC. Dev/test keep the local file path so local
    tests and one-off exports work without provisioning cloud storage.
    """
    if getattr(settings, "app_env", None) != "prod":
        return str(file_path)

    bucket_name = settings.gcs_bucket_name
    if not bucket_name:
        raise RuntimeError("GCS_BUCKET_NAME is required for production export storage")

    from api.services.object_storage import ObjectStorage

    blob_path = f"exports/{analysis.org_id}/{analysis.id}/{job.id}/{execution_id}/{file_path.name}"
    storage = ObjectStorage(
        bucket=bucket_name,
        project=settings.gcp_project_id or None,
    )
    try:
        with file_path.open("rb") as artifact:
            url = storage.upload_file(
                blob_path,
                artifact,
                content_type=_export_content_type(job.format, export_format_enum),
                cache_control="private, max-age=0, no-store",
                metadata={
                    "analysis_id": str(analysis.id),
                    "org_id": str(analysis.org_id),
                    "export_job_id": str(job.id),
                    "export_execution_id": str(execution_id),
                    "format": job.format.value,
                    "artifact_sha256": artifact_sha256,
                },
            )
    finally:
        # The artifact lives in a per-invocation ``uuid4().hex`` subdirectory
        # (see ``_render_export_artifact``). Once the durable copy is in GCS the
        # local file *and* its unique container directory are disposable, so we
        # remove the whole directory rather than leaking an empty inode per
        # export on long-lived workers.
        _cleanup_local_export_artifact(file_path)
    return url


def _cleanup_local_export_artifact(file_path: Path) -> None:
    """Remove a rendered local artifact and its unique per-invocation directory.

    Best-effort: a cleanup failure must never mask a successful upload, so any
    filesystem error is swallowed (the artifact already has a durable copy).
    """
    import shutil

    parent = file_path.parent
    file_path.unlink(missing_ok=True)
    try:
        # Only remove the directory when it is the disposable per-invocation
        # ``uuid4().hex`` container — a 32-char lowercase hex name — so a
        # misconfigured export root can never trigger a wider deletion.
        if len(parent.name) == 32 and all(c in "0123456789abcdef" for c in parent.name):
            shutil.rmtree(parent, ignore_errors=True)
    except OSError:
        pass


def _load_export_worker_runtime() -> _ExportWorkerRuntime:
    from api.config import get_settings
    from api.db.models import (
        Analysis,
        ExportFormat,
        ExportJob,
        ExportStatus,
        Organization,
        User,
    )
    from api.services.export_branding import load_export_branding_for_org_sync

    return _ExportWorkerRuntime(
        settings=get_settings(),
        analysis_model=Analysis,
        export_format_enum=ExportFormat,
        export_job_model=ExportJob,
        export_status_enum=ExportStatus,
        organization_model=Organization,
        user_model=User,
        load_branding=load_export_branding_for_org_sync,
    )


def _fail_current_export_claim(
    db: Session,
    runtime: _ExportWorkerRuntime,
    *,
    export_job_id: str,
    execution_id: uuid.UUID,
    logger,
    message: str,
    stale_event_name: str,
) -> _FailedClaimTransition:
    job = _lock_current_export_claim(
        db,
        runtime.export_job_model,
        export_job_id=export_job_id,
        execution_id=execution_id,
    )
    if job is None:
        return _FailedClaimTransition(
            stale_result=_stale_export_execution_result(
                logger,
                export_job_id=export_job_id,
                execution_id=execution_id,
                event_name=stale_event_name,
            )
        )
    _mark_export_failed(job, message)
    _commit_or_rollback(db)
    return _FailedClaimTransition(job=job)


def _claim_export_job(
    db: Session,
    runtime: _ExportWorkerRuntime,
    *,
    export_job_id: str,
    org_id: str,
    lease_ttl_seconds: int,
    logger,
    execution_state: _ExportExecutionState,
) -> _ExportClaim | ExportJobResult:
    job = db.get(runtime.export_job_model, export_job_id, with_for_update=True)
    if not job:
        logger.error("export_job_not_found", id=export_job_id)
        return {"error": "not_found"}
    if str(job.org_id) != str(org_id):
        logger.error(
            "export_task_org_mismatch",
            job_id=export_job_id,
            expected_org_id=org_id,
            actual_org_id=str(job.org_id),
        )
        return {"status": "blocked", "error": "export_org_mismatch"}

    status = runtime.export_status_enum
    if job.status == status.COMPLETED:
        logger.info("export_job_duplicate_completed", job_id=export_job_id)
        return {
            "status": "already_completed",
            "file_url": job.file_url,
            "size_bytes": job.file_size_bytes,
            "manifest_hash": getattr(job, "manifest_hash", None),
            "artifact_sha256": getattr(job, "artifact_sha256", None),
        }
    if job.status == status.PROCESSING:
        processing_result = _handle_processing_export_claim(
            job,
            export_job_id=export_job_id,
            lease_ttl_seconds=lease_ttl_seconds,
            logger=logger,
        )
        if processing_result is not None:
            return processing_result
    if job.status == status.FAILED:
        failure_result = _handle_failed_export_claim(
            job,
            export_job_id=export_job_id,
            lease_ttl_seconds=lease_ttl_seconds,
            logger=logger,
        )
        if failure_result is not None:
            return failure_result

    lease_now = datetime.now(UTC)
    execution_id = uuid.uuid4()
    execution_state.execution_id = execution_id
    job.status = status.PROCESSING
    job.processing_execution_id = execution_id
    job.processing_lease_expires_at = lease_now + timedelta(seconds=lease_ttl_seconds)
    job.error_message = ""
    _commit_or_rollback(db)
    return _ExportClaim(job=job, execution_id=execution_id)


def _handle_processing_export_claim(
    job,
    *,
    export_job_id: str,
    lease_ttl_seconds: int,
    logger,
) -> ExportJobResult | None:
    lease_now = datetime.now(UTC)
    if not _processing_export_is_reclaimable(
        job,
        now=lease_now,
        lease_ttl_seconds=lease_ttl_seconds,
    ):
        logger.info(
            "export_job_duplicate_processing",
            job_id=export_job_id,
            processing_lease_expires_at=getattr(job, "processing_lease_expires_at", None),
        )
        return _export_retry_later_result(
            job,
            export_job_id=export_job_id,
            now=lease_now,
            reason="processing_lease_active",
        )
    logger.warning(
        "export_job_reclaiming_stale_processing",
        job_id=export_job_id,
        processing_lease_expires_at=getattr(job, "processing_lease_expires_at", None),
    )
    return None


def _handle_failed_export_claim(
    job,
    *,
    export_job_id: str,
    lease_ttl_seconds: int,
    logger,
) -> ExportJobResult | None:
    lease_now = datetime.now(UTC)
    if getattr(job, "processing_lease_expires_at", None) is None:
        logger.info("export_job_duplicate_failed", job_id=export_job_id)
        return {"status": "already_failed", "job_id": export_job_id}
    if not _processing_export_is_reclaimable(
        job,
        now=lease_now,
        lease_ttl_seconds=lease_ttl_seconds,
    ):
        logger.info(
            "export_job_retryable_failure_waiting",
            job_id=export_job_id,
            processing_lease_expires_at=getattr(job, "processing_lease_expires_at", None),
        )
        return _export_retry_later_result(
            job,
            export_job_id=export_job_id,
            now=lease_now,
            reason="retryable_failure_lease_active",
        )
    logger.warning(
        "export_job_reclaiming_retryable_failure",
        job_id=export_job_id,
        processing_lease_expires_at=getattr(job, "processing_lease_expires_at", None),
    )
    return None


def _load_claimed_export_analysis(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    *,
    export_job_id: str,
    logger,
) -> Any | ExportJobResult:
    analysis = db.get(runtime.analysis_model, str(claim.job.analysis_id))
    if not analysis:
        transition = _fail_current_export_claim(
            db,
            runtime,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
            logger=logger,
            message=_safe_export_error_message(
                "Export failed",
                "Report data is unavailable",
            ),
            stale_event_name="export_job_stale_execution_lost_no_report",
        )
        if transition.stale_result is not None:
            return transition.stale_result
        return {"error": "no_report_data"}
    if str(getattr(analysis, "org_id", "")) != str(getattr(claim.job, "org_id", "")):
        transition = _fail_current_export_claim(
            db,
            runtime,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
            logger=logger,
            message=_safe_export_error_message(
                "Export blocked",
                "Analysis does not belong to the export job organization.",
            ),
            stale_event_name="export_job_stale_execution_lost_tenant_mismatch",
        )
        if transition.stale_result is not None:
            return transition.stale_result
        assert transition.job is not None
        logger.error(
            "export_blocked_tenant_mismatch",
            job_id=export_job_id,
            analysis_id=str(analysis.id),
            job_org_id=str(getattr(transition.job, "org_id", "")),
            analysis_org_id=str(getattr(analysis, "org_id", "")),
        )
        return {
            "status": "blocked",
            "error": "export_tenant_mismatch",
            "message": transition.job.error_message,
        }
    return analysis


def _authorize_export_requester(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    *,
    export_job_id: str,
    logger,
) -> ExportJobResult | None:
    block_reason = _full_export_requester_block_reason(db, runtime.user_model, claim.job)
    if not block_reason:
        return None
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=_safe_export_error_message("Export blocked", block_reason),
        stale_event_name="export_job_stale_execution_lost_requester_auth",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    assert transition.job is not None
    logger.error(
        "export_blocked_requester_not_authorized",
        job_id=export_job_id,
        org_id=str(getattr(transition.job, "org_id", "")),
        user_id=str(getattr(transition.job, "user_id", "")),
        reason=block_reason,
    )
    return {
        "status": "blocked",
        "error": EXPORT_REQUESTER_NOT_AUTHORIZED_ERROR,
        "message": transition.job.error_message,
    }


def _load_export_report_snapshot(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    export_job_id: str,
    logger,
) -> _ExportReportSnapshot | ExportJobResult:
    from api.errors import APIError
    from api.services.report_access import require_completed_report_payload
    from api.services.reports import build_export_readiness_blockers

    try:
        report_data = require_completed_report_payload(
            analysis,
            status_code=409,
            title="Conflict",
            detail="Export is blocked until the analysis has a completed report payload.",
        )
    except APIError:
        return _block_incomplete_export_report(
            db,
            runtime,
            claim,
            analysis,
            export_job_id=export_job_id,
            logger=logger,
        )
    review_status = _load_review_status(
        db,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    decision_rows = _load_reviewer_decision_rows(
        db,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    decision_rows = filter_current_reviewer_decisions(report_data, decision_rows)
    readiness_blockers = build_export_readiness_blockers(
        report_data=report_data,
        review_status=review_status,
        reviewer_decisions=decision_rows,
    )
    if readiness_blockers:
        return _block_unready_export_report(
            db,
            runtime,
            claim,
            analysis,
            readiness_blockers=readiness_blockers,
            export_job_id=export_job_id,
            logger=logger,
        )
    try:
        report = _validate_export_report_payload(report_data)
    except ValueError:
        return _block_invalid_export_report(
            db,
            runtime,
            claim,
            analysis,
            export_job_id=export_job_id,
            logger=logger,
        )
    reviewer_decisions = _serialize_reviewer_decisions(decision_rows)
    return _ExportReportSnapshot(
        report_data=report_data,
        report=report,
        review_status=review_status,
        reviewer_decision_rows=decision_rows,
        reviewer_decisions=reviewer_decisions,
        rendered_report_fingerprint=report_payload_fingerprint(report_data),
        rendered_decision_state=_reviewer_decision_state(decision_rows),
        rendered_review_state=_review_status_state(review_status),
    )


def _block_incomplete_export_report(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    export_job_id: str,
    logger,
) -> ExportJobResult:
    reason = "Analysis does not have a completed report payload."
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=_safe_export_error_message("Export blocked", reason),
        stale_event_name="export_job_stale_execution_lost_incomplete_report",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    assert transition.job is not None
    logger.warning(
        "export_blocked_incomplete_report",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
    )
    return {
        "status": "blocked",
        "error": "export_not_ready",
        "message": transition.job.error_message,
        "reasons": [reason],
    }


def _block_unready_export_report(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    readiness_blockers: list[str],
    export_job_id: str,
    logger,
) -> ExportJobResult:
    blocked_message = _safe_export_error_message(
        "Export blocked",
        " ".join(readiness_blockers),
    )
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=blocked_message,
        stale_event_name="export_job_stale_execution_lost_readiness_block",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    logger.warning(
        "export_blocked_not_ready",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
        reasons=readiness_blockers,
    )
    return {
        "status": "blocked",
        "error": "export_not_ready",
        "message": blocked_message,
        "reasons": readiness_blockers,
    }


def _block_invalid_export_report(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    export_job_id: str,
    logger,
) -> ExportJobResult:
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=_safe_export_error_message(
            "Export failed",
            "Report payload failed export schema validation.",
        ),
        stale_event_name="export_job_stale_execution_lost_report_validation",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    assert transition.job is not None
    logger.error(
        "export_report_payload_invalid",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
    )
    return {
        "status": "blocked",
        "error": "export_invalid_report",
        "message": transition.job.error_message,
    }


def _build_export_preparation(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    report_snapshot: _ExportReportSnapshot,
    *,
    export_job_id: str,
    logger,
) -> _ExportPreparation | ExportJobResult:
    from praviar_pipeline.rendering.export_options import ExportRenderOptions

    raw_sections = getattr(claim.job, "sections", None)
    if not isinstance(raw_sections, (list, tuple, set)):
        raw_sections = None
    raw_audience = getattr(claim.job, "audience", None)
    if not isinstance(raw_audience, str):
        raw_audience = "full"
    try:
        export_options = ExportRenderOptions.from_values(
            raw_sections,
            audience=raw_audience,
        )
    except ValueError as exc:
        return _block_invalid_export_scope(
            db,
            runtime,
            claim,
            analysis,
            exc=exc,
            export_job_id=export_job_id,
            logger=logger,
        )
    try:
        branding = runtime.load_branding(
            db,
            runtime.organization_model,
            org_id=analysis.org_id,
        )
    except Exception as exc:
        return _block_invalid_export_branding(
            db,
            runtime,
            claim,
            analysis,
            exc=exc,
            export_job_id=export_job_id,
            logger=logger,
        )
    return _ExportPreparation(
        job=claim.job,
        analysis=analysis,
        report_snapshot=report_snapshot,
        export_options=export_options,
        export_branding=branding,
    )


def _block_invalid_export_scope(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    exc: ValueError,
    export_job_id: str,
    logger,
) -> ExportJobResult:
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=_safe_export_error_message("Export blocked", str(exc)),
        stale_event_name="export_job_stale_execution_lost_invalid_scope",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    assert transition.job is not None
    logger.warning(
        "export_blocked_invalid_scope",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
        reason=str(exc),
    )
    return {
        "status": "blocked",
        "error": "export_invalid_scope",
        "message": transition.job.error_message,
    }


def _block_invalid_export_branding(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    analysis,
    *,
    exc: Exception,
    export_job_id: str,
    logger,
) -> ExportJobResult:
    transition = _fail_current_export_claim(
        db,
        runtime,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
        logger=logger,
        message=_safe_export_error_message("Export blocked", str(exc)),
        stale_event_name="export_job_stale_execution_lost_branding",
    )
    if transition.stale_result is not None:
        return transition.stale_result
    assert transition.job is not None
    logger.warning(
        "export_blocked_invalid_branding",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
        reason=str(exc),
    )
    return {
        "status": "blocked",
        "error": "export_invalid_branding",
        "message": transition.job.error_message,
    }


def _prepare_claimed_export(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    *,
    export_job_id: str,
    logger,
) -> _ExportPreparation | ExportJobResult:
    analysis = _load_claimed_export_analysis(
        db,
        runtime,
        claim,
        export_job_id=export_job_id,
        logger=logger,
    )
    if isinstance(analysis, dict):
        return analysis
    authorization_result = _authorize_export_requester(
        db,
        runtime,
        claim,
        export_job_id=export_job_id,
        logger=logger,
    )
    if authorization_result is not None:
        return authorization_result
    report_snapshot = _load_export_report_snapshot(
        db,
        runtime,
        claim,
        analysis,
        export_job_id=export_job_id,
        logger=logger,
    )
    if isinstance(report_snapshot, dict):
        return report_snapshot
    return _build_export_preparation(
        db,
        runtime,
        claim,
        analysis,
        report_snapshot,
        export_job_id=export_job_id,
        logger=logger,
    )


def _render_prepared_export(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    preparation: _ExportPreparation,
    *,
    export_job_id: str,
    logger,
    render_export_fn,
) -> _RenderedExport | ExportJobResult:
    snapshot = preparation.report_snapshot
    file_path = render_export_fn(
        snapshot.report,
        preparation.job.format,
        runtime.export_format_enum,
        reviewer_decisions=snapshot.reviewer_decisions,
        sections=list(preparation.export_options.sections),
        audience=preparation.export_options.audience,
        branding=preparation.export_branding,
    )
    if file_path is None:
        transition = _fail_current_export_claim(
            db,
            runtime,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
            logger=logger,
            message=_safe_export_error_message(
                "Export failed",
                f"Unsupported format: {preparation.job.format}",
            ),
            stale_event_name="export_job_stale_execution_lost_unsupported_format",
        )
        if transition.stale_result is not None:
            return transition.stale_result
        assert transition.job is not None
        return {"error": f"Unsupported format: {transition.job.format}"}
    return _RenderedExport(
        preparation=preparation,
        file_path=file_path,
        file_size_bytes=file_path.stat().st_size,
        artifact_sha256=_sha256_file(file_path),
    )


def _lock_export_persistence_scope(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    rendered: _RenderedExport,
    *,
    export_job_id: str,
    logger,
) -> Any | ExportJobResult:
    analysis = rendered.preparation.analysis
    organization = db.get(
        runtime.organization_model,
        analysis.org_id,
        with_for_update=True,
        populate_existing=True,
    )
    deletion_status = (
        getattr(organization, "deletion_status", None) if organization is not None else "missing"
    )
    if deletion_status not in {None, "pending"}:
        current_job = _lock_current_export_claim(
            db,
            runtime.export_job_model,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
        )
        if current_job is not None:
            _mark_export_failed(
                current_job,
                _safe_export_error_message(
                    "Export cancelled",
                    "Organization erasure is in progress.",
                ),
            )
            _commit_or_rollback(db)
        _cleanup_local_export_artifact(rendered.file_path)
        logger.warning(
            "export_blocked_org_erasure_in_progress",
            job_id=export_job_id,
            org_id=str(analysis.org_id),
            deletion_status=deletion_status,
        )
        return {
            "status": "blocked",
            "error": "organization_erasure_in_progress",
            "message": "Export cancelled because organization erasure is in progress.",
        }
    job = _lock_current_export_claim(
        db,
        runtime.export_job_model,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
    )
    if job is None:
        _cleanup_local_export_artifact(rendered.file_path)
        return _stale_export_execution_result(
            logger,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
            event_name="export_job_stale_execution_lost_before_persistence",
        )
    return job


def _revalidate_export_inputs(
    db: Session,
    runtime: _ExportWorkerRuntime,
    rendered: _RenderedExport,
    job,
    *,
    export_job_id: str,
    logger,
) -> _PersistenceSnapshot | ExportJobResult:
    from api.errors import APIError
    from api.services.report_access import require_completed_report_payload
    from api.services.reports import build_export_readiness_blockers

    original_analysis = rendered.preparation.analysis
    original_snapshot = rendered.preparation.report_snapshot
    current_analysis = db.get(
        runtime.analysis_model,
        original_analysis.id,
        with_for_update=True,
        populate_existing=True,
    )
    final_blockers: list[str] = []
    current_report_data: dict[str, Any] | None = None
    current_review_status = None
    current_decision_rows: list[Any] = []
    if current_analysis is None or str(getattr(current_analysis, "org_id", "")) != str(
        getattr(job, "org_id", "")
    ):
        final_blockers.append("The report or its tenant binding changed during export generation.")
    else:
        requester_block = _full_export_requester_block_reason(db, runtime.user_model, job)
        if requester_block:
            final_blockers.append(requester_block)
        try:
            current_report_data = require_completed_report_payload(
                current_analysis,
                status_code=409,
                title="Conflict",
                detail="Export is blocked until the analysis has a completed report payload.",
            )
        except APIError:
            final_blockers.append("The analysis no longer has a completed report payload.")

    if current_report_data is not None and current_analysis is not None:
        current_review_status = _load_review_status(
            db,
            analysis_id=current_analysis.id,
            org_id=current_analysis.org_id,
        )
        current_decision_rows = _load_reviewer_decision_rows(
            db,
            analysis_id=current_analysis.id,
            org_id=current_analysis.org_id,
        )
        current_decision_rows = filter_current_reviewer_decisions(
            current_report_data,
            current_decision_rows,
        )
        final_blockers.extend(
            build_export_readiness_blockers(
                report_data=current_report_data,
                review_status=current_review_status,
                reviewer_decisions=current_decision_rows,
            )
        )
        if _export_inputs_changed(
            current_report_data=current_report_data,
            current_review_status=current_review_status,
            current_decision_rows=current_decision_rows,
            original_snapshot=original_snapshot,
        ):
            final_blockers.append(
                "Report or review inputs changed during export generation; "
                "generate a new packet from the current snapshot."
            )

    if final_blockers:
        return _block_changed_export_inputs(
            db,
            rendered,
            job,
            final_blockers=final_blockers,
            export_job_id=export_job_id,
            logger=logger,
        )
    assert current_analysis is not None
    assert current_report_data is not None
    return _PersistenceSnapshot(
        rendered=rendered,
        job=job,
        analysis=current_analysis,
        report_data=current_report_data,
        review_status=current_review_status,
        reviewer_decision_rows=current_decision_rows,
        reviewer_decisions=_serialize_reviewer_decisions(current_decision_rows),
    )


def _export_inputs_changed(
    *,
    current_report_data: dict[str, Any],
    current_review_status,
    current_decision_rows: list[Any],
    original_snapshot: _ExportReportSnapshot,
) -> bool:
    return (
        report_payload_fingerprint(current_report_data)
        != original_snapshot.rendered_report_fingerprint
        or _reviewer_decision_state(current_decision_rows)
        != original_snapshot.rendered_decision_state
        or _review_status_state(current_review_status) != original_snapshot.rendered_review_state
    )


def _block_changed_export_inputs(
    db: Session,
    rendered: _RenderedExport,
    job,
    *,
    final_blockers: list[str],
    export_job_id: str,
    logger,
) -> ExportJobResult:
    analysis = rendered.preparation.analysis
    blocked_message = _safe_export_error_message(
        "Export blocked",
        " ".join(final_blockers),
    )
    _mark_export_failed(job, blocked_message)
    _commit_or_rollback(db)
    _cleanup_local_export_artifact(rendered.file_path)
    logger.warning(
        "export_blocked_final_readiness_recheck",
        job_id=export_job_id,
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
        reasons=final_blockers,
    )
    return {
        "status": "blocked",
        "error": "export_inputs_changed",
        "message": blocked_message,
        "reasons": final_blockers,
    }


def _authorize_export_persistence(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    rendered: _RenderedExport,
    *,
    export_job_id: str,
    logger,
) -> _PersistenceSnapshot | ExportJobResult:
    job = _lock_export_persistence_scope(
        db,
        runtime,
        claim,
        rendered,
        export_job_id=export_job_id,
        logger=logger,
    )
    if isinstance(job, dict):
        return job
    return _revalidate_export_inputs(
        db,
        runtime,
        rendered,
        job,
        export_job_id=export_job_id,
        logger=logger,
    )


def _persist_and_complete_export(
    db: Session,
    runtime: _ExportWorkerRuntime,
    claim: _ExportClaim,
    snapshot: _PersistenceSnapshot,
    *,
    export_job_id: str,
    logger,
) -> ExportJobResult:
    rendered = snapshot.rendered
    preparation = rendered.preparation
    durable_url = _persist_export_artifact(
        file_path=rendered.file_path,
        job=snapshot.job,
        analysis=snapshot.analysis,
        settings=runtime.settings,
        export_format_enum=runtime.export_format_enum,
        execution_id=claim.execution_id,
        artifact_sha256=rendered.artifact_sha256,
    )
    report_payload_sha256 = report_payload_fingerprint(snapshot.report_data)
    completed_at = datetime.now(UTC)
    manifest_snapshot = _build_export_manifest_snapshot(
        analysis=snapshot.analysis,
        audience=preparation.export_options.audience,
        branding=preparation.export_branding,
        durable_url=durable_url,
        export_format=snapshot.job.format.value,
        file_size_bytes=rendered.file_size_bytes,
        job=snapshot.job,
        report_data=snapshot.report_data,
        report_payload_sha256=report_payload_sha256,
        review_status=snapshot.review_status,
        reviewer_decisions=snapshot.reviewer_decisions,
        sections=list(preparation.export_options.sections),
    )
    manifest_snapshot["artifact"]["sha256"] = rendered.artifact_sha256
    manifest_snapshot["completed_at"] = completed_at.isoformat()
    manifest_hash = export_manifest_hash(manifest_snapshot)
    manifest_signature = export_manifest_signature(manifest_hash)

    job = _lock_current_export_claim(
        db,
        runtime.export_job_model,
        export_job_id=export_job_id,
        execution_id=claim.execution_id,
    )
    if job is None:
        return _stale_export_execution_result(
            logger,
            export_job_id=export_job_id,
            execution_id=claim.execution_id,
            event_name="export_job_stale_execution_lost_completion",
        )
    job.status = runtime.export_status_enum.COMPLETED
    job.file_url = durable_url
    job.file_size_bytes = rendered.file_size_bytes
    job.manifest_schema_version = EXPORT_MANIFEST_SCHEMA_VERSION
    job.manifest_hash = manifest_hash
    job.manifest_signature = manifest_signature
    job.manifest_snapshot = manifest_snapshot
    job.artifact_sha256 = rendered.artifact_sha256
    job.report_payload_sha256 = report_payload_sha256
    job.completed_at = completed_at
    job.retry_attempts = 0
    job.processing_execution_id = None
    job.processing_lease_expires_at = None
    _commit_or_rollback(db)
    logger.info(
        "export_completed",
        job_id=export_job_id,
        format=job.format.value,
        size_bytes=job.file_size_bytes,
        file_url=durable_url,
        manifest_hash=manifest_hash,
    )
    return {
        "status": "completed",
        "file_url": durable_url,
        "size_bytes": job.file_size_bytes,
        "manifest_hash": manifest_hash,
        "artifact_sha256": rendered.artifact_sha256,
    }


def _execute_export_job_session(
    db: Session,
    *,
    export_job_id: str,
    org_id: str,
    logger,
    render_export_fn,
    execution_state: _ExportExecutionState,
) -> ExportJobResult:
    from api.db.session import bind_org_to_sync_session

    runtime = _load_export_worker_runtime()
    lease_ttl_seconds = _export_processing_lease_ttl_seconds(runtime.settings)
    bind_org_to_sync_session(db, org_id)
    claim = _claim_export_job(
        db,
        runtime,
        export_job_id=export_job_id,
        org_id=org_id,
        lease_ttl_seconds=lease_ttl_seconds,
        logger=logger,
        execution_state=execution_state,
    )
    if isinstance(claim, dict):
        return claim
    preparation = _prepare_claimed_export(
        db,
        runtime,
        claim,
        export_job_id=export_job_id,
        logger=logger,
    )
    if isinstance(preparation, dict):
        return preparation
    rendered = _render_prepared_export(
        db,
        runtime,
        claim,
        preparation,
        export_job_id=export_job_id,
        logger=logger,
        render_export_fn=render_export_fn,
    )
    if isinstance(rendered, dict):
        return rendered
    persistence_snapshot = _authorize_export_persistence(
        db,
        runtime,
        claim,
        rendered,
        export_job_id=export_job_id,
        logger=logger,
    )
    if isinstance(persistence_snapshot, dict):
        return persistence_snapshot
    return _persist_and_complete_export(
        db,
        runtime,
        claim,
        persistence_snapshot,
        export_job_id=export_job_id,
        logger=logger,
    )


def _record_export_job_failure(
    *,
    engine,
    export_job_id: str,
    org_id: str,
    execution_id: uuid.UUID | None,
    logger,
) -> ExportJobResult:
    retry_exhausted = False
    retry_after_seconds = 60
    try:
        with Session(engine) as db:
            from api.db.models import ExportJob
            from api.db.session import bind_org_to_sync_session

            bind_org_to_sync_session(db, org_id)
            if execution_id is not None:
                job = _lock_current_export_claim(
                    db,
                    ExportJob,
                    export_job_id=export_job_id,
                    execution_id=execution_id,
                )
            else:
                job = db.get(ExportJob, export_job_id, with_for_update=True)
            if job:
                failure_recorded_at = datetime.now(UTC)
                retryable = _mark_export_retryable_failure(
                    job,
                    _safe_export_error_message(
                        "Export failed",
                        "See worker logs for traceback",
                    ),
                    now=failure_recorded_at,
                )
                retry_exhausted = not retryable
                if retryable and job.processing_lease_expires_at is not None:
                    retry_after_seconds = max(
                        1,
                        int(
                            (job.processing_lease_expires_at - failure_recorded_at).total_seconds()
                        ),
                    )
                _commit_or_rollback(db)
    except Exception:
        logger.exception("failed_to_update_export_status")
    if retry_exhausted:
        return {
            "status": "blocked",
            "error": "export_retry_exhausted",
            "message": _safe_export_error_message(
                "Export failed",
                "Repeated worker retries were exhausted.",
            ),
        }
    return {
        "status": "failed",
        "error": "export_failed",
        "retry_after_seconds": retry_after_seconds,
        "message": _safe_export_error_message(
            "Export failed",
            "See worker logs for traceback",
        ),
    }


def run_export_job(
    *,
    engine,
    export_job_id: str,
    org_id: str,
    logger,
    render_export_fn,
) -> ExportJobResult:
    """Run the export job lifecycle against the sync worker session."""
    if not org_id:
        raise ValueError("org_id is required for export jobs")
    execution_state = _ExportExecutionState()
    try:
        with Session(engine) as db:
            return _execute_export_job_session(
                db,
                export_job_id=export_job_id,
                org_id=org_id,
                logger=logger,
                render_export_fn=render_export_fn,
                execution_state=execution_state,
            )
    except Exception:
        logger.exception("export_failed", job_id=export_job_id)
        return _record_export_job_failure(
            engine=engine,
            export_job_id=export_job_id,
            org_id=org_id,
            execution_id=execution_state.execution_id,
            logger=logger,
        )
