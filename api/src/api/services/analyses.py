"""Business logic for analysis lifecycle orchestration."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import Request
from praviar_pipeline.models.accused_acts import AccusedActRecord
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    AnalysisReviewStatus,
    AnalysisStatus,
    Organization,
    ReviewStatus,
)
from api.errors import APIError, problem_type_uri
from api.schemas.analyses import CreateAnalysisRequest
from api.services.analysis_dispatch import reserve_pipeline_reconciliation
from api.services.billing_queries import (
    AnalysisCreditReservation,
    check_usage_limit,
    consume_analysis_credits,
    refund_cancelled_analysis_credits,
)
from api.services.configs import load_org_default_config
from api.services.risk_access import RISK_RESTRICTION_SUMMARY

logger = structlog.get_logger()

_LAUNCH_CONTEXT_PRODUCT_TEXT_FIELDS = {
    "product_name",
    "dosage_form",
    "route_of_administration",
    "strength",
    "release_profile",
    "salt_polymorph_form",
    "indication",
    "patient_population",
    "reference_product",
    "manufacturing_route",
    "commercial_action",
    "decision_deadline",
}
_LAUNCH_CONTEXT_PRODUCT_LIST_FIELDS = {
    "key_excipients",
    "combination_assets",
    "commercial_territories",
    "known_patents_or_assignees",
}
_LEGAL_REVIEW_ROLES = {"admin", "attorney"}
_LIKE_ESCAPE_CHARACTER = "\\"


def _compound_input_metadata(
    value: str,
    *,
    input_type: str,
) -> dict[str, object]:
    return {
        "compound_input_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "compound_input_length": len(value),
        "compound_input_type": input_type,
        "submitted_identity_confirmed": True,
    }


@dataclass(frozen=True)
class AnalysisPage:
    items: list[Analysis]
    total: int
    page: int
    per_page: int
    status_counts: dict[str, int]


@dataclass(frozen=True)
class AnalysisCursorPage:
    """Result set for cursor-based pagination on GET /analyses."""

    items: list[Analysis]
    next_cursor: str | None


@dataclass(frozen=True)
class AnalysisCreationResult:
    analysis: Analysis
    replayed: bool


def _validate_launch_idempotency_key(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        ord(character) < 0x21 or ord(character) > 0x7E for character in value
    ):
        raise APIError(
            422,
            "Validation Error",
            "Idempotency-Key must contain 16 to 128 visible ASCII characters",
        )
    return value


def _launch_idempotency_key_digest(
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> str:
    return hashlib.sha256(
        b"praviar:analysis-launch:idempotency:v1\0"
        + org_id.bytes
        + b"\0"
        + idempotency_key.encode("ascii")
    ).hexdigest()


def _launch_payload_digest(body: CreateAnalysisRequest) -> str:
    canonical_payload = json.dumps(
        body.normalized_idempotency_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


async def _lock_analysis_launch_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> None:
    """Serialize launch receipt lookup and capacity reservation per tenant."""
    result = await db.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise APIError(404, "Not Found", "Organization not found")


async def _get_analysis_by_launch_key(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    key_digest: str,
) -> Analysis | None:
    result = await db.execute(
        select(Analysis)
        .where(
            Analysis.org_id == org_id,
            Analysis.launch_idempotency_key_digest == key_digest,
        )
        .with_for_update()
    )
    analysis = result.scalar_one_or_none()
    return analysis if isinstance(analysis, Analysis) else None


def _replay_analysis_or_conflict(
    analysis: Analysis,
    *,
    payload_digest: str,
) -> AnalysisCreationResult:
    if analysis.launch_payload_digest != payload_digest:
        raise APIError(
            409,
            "Conflict",
            "Idempotency-Key was already used with a different analysis launch request",
        )
    return AnalysisCreationResult(analysis=analysis, replayed=True)


async def _redrive_pending_analysis(
    db: AsyncSession,
    analysis: Analysis,
    *,
    org_id: uuid.UUID,
) -> None:
    """Redrive one persisted PENDING launch without reserving capacity again."""
    if analysis.status != AnalysisStatus.PENDING:
        return
    if analysis.pipeline_execution_id is not None:
        reservation_expiry = analysis.pipeline_lease_expires_at
        if reservation_expiry is None or reservation_expiry > datetime.now(UTC):
            return
        analysis.pipeline_execution_id = None
        analysis.pipeline_lease_expires_at = None

    from api.services.task_dispatcher import build_dispatcher

    reservation = reserve_pipeline_reconciliation(analysis)
    if reservation is None:
        return
    if reservation.exhausted:
        await db.rollback()
        raise APIError(
            503,
            "Service Unavailable",
            "Pipeline dispatch reconciliation attempts are exhausted",
        )
    await db.commit()

    try:
        await build_dispatcher().dispatch_pipeline_run(
            analysis_id=str(analysis.id),
            org_id=str(org_id),
            reconciliation_key=reservation.task_key,
        )
    except Exception as exc:
        logger.error(
            "pending_analysis_redrive_failed",
            analysis_id=str(analysis.id),
            org_id=str(org_id),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise APIError(
            503,
            "Service Unavailable",
            "Pipeline dispatch reconciliation failed",
        ) from exc


def _analysis_sort_clauses(sort_by: str):
    """Return deterministic Analysis ordering clauses for list views."""
    risk_rank_desc = case(
        (Analysis.overall_risk == "high", 4),
        (Analysis.overall_risk == "medium", 3),
        (Analysis.overall_risk == "low", 2),
        (Analysis.overall_risk == "clear", 1),
        else_=0,
    )
    risk_rank_asc = case(
        (Analysis.overall_risk == "clear", 1),
        (Analysis.overall_risk == "low", 2),
        (Analysis.overall_risk == "medium", 3),
        (Analysis.overall_risk == "high", 4),
        else_=5,
    )

    sort_map = {
        "date-desc": (Analysis.created_at.desc(),),
        "date-asc": (Analysis.created_at.asc(),),
        "risk-desc": (risk_rank_desc.desc(), Analysis.created_at.desc()),
        "risk-asc": (risk_rank_asc.asc(), Analysis.created_at.desc()),
    }
    return sort_map.get(sort_by, sort_map["date-desc"])


def _encode_cursor(created_at: datetime, analysis_id: uuid.UUID) -> str:
    """Encode a stable opaque cursor from a (created_at, id) pair."""
    raw = f"{created_at.astimezone(UTC).isoformat()}|{analysis_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor back to (created_at, id). Raises ValueError on bad input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_part, id_part = raw.rsplit("|", 1)
        created_at = datetime.fromisoformat(ts_part)
        analysis_id = uuid.UUID(id_part)
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor!r}") from exc
    return created_at, analysis_id


def _serialize_analysis_review_status_summary(
    analysis: Analysis,
    review_status: AnalysisReviewStatus | None,
) -> dict:
    if review_status is None:
        fallback_status = (
            ReviewStatus.UNDER_REVIEW if analysis.flagged_for_review else ReviewStatus.PENDING
        )
        return {
            "status": fallback_status.value,
            "is_persisted": False,
            "note": None,
            "reviewer_name": None,
            "reviewer_email": None,
            "reviewed_at": None,
            "updated_at": analysis.updated_at or analysis.created_at,
        }

    status_value = (
        review_status.status.value
        if isinstance(review_status.status, ReviewStatus)
        else str(review_status.status)
    )
    if status_value == ReviewStatus.APPROVED.value and analysis.flagged_for_review:
        status_value = ReviewStatus.CHANGES_REQUESTED.value

    return {
        "status": status_value,
        "is_persisted": True,
        "note": (review_status.note or "").strip() or None,
        "reviewer_name": (review_status.reviewer_name or "").strip() or None,
        "reviewer_email": (review_status.reviewer_email or "").strip() or None,
        "reviewed_at": review_status.reviewed_at,
        "updated_at": review_status.updated_at or review_status.reviewed_at,
    }


def review_status_visible_for_role(role: str | None) -> bool:
    """Return whether a principal may receive internal legal-review metadata."""
    return role is None or role in _LEGAL_REVIEW_ROLES


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (raw.strip() for raw in value if isinstance(raw, str)) if item]


def _text_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _escape_like_pattern(value: str) -> str:
    """Treat user search text literally instead of as a SQL LIKE pattern."""
    return (
        value.replace(_LIKE_ESCAPE_CHARACTER, _LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{_LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{_LIKE_ESCAPE_CHARACTER}_")
    )


def _serialize_launch_context(config: object) -> dict | None:
    if not isinstance(config, Mapping):
        return None

    product_context = config.get("product_context")
    normalized_product_context: dict[str, object] = {}
    if isinstance(product_context, Mapping):
        for key_text in _LAUNCH_CONTEXT_PRODUCT_TEXT_FIELDS:
            text_value = _text_or_none(product_context.get(key_text))
            if text_value is not None:
                normalized_product_context[key_text] = text_value
        for key_text in _LAUNCH_CONTEXT_PRODUCT_LIST_FIELDS:
            value = product_context.get(key_text)
            if isinstance(value, list):
                list_value = _text_list(value)
                if list_value:
                    normalized_product_context[key_text] = list_value
        accused_acts = product_context.get("accused_acts")
        if isinstance(accused_acts, list) and accused_acts:
            with suppress(TypeError, ValueError):
                normalized_product_context["accused_acts"] = [
                    AccusedActRecord.model_validate(record).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    for record in accused_acts
                ]

    launch_context = {
        "trust_mode": _text_or_none(config.get("trust_mode")),
        "jurisdiction_bundle": _text_or_none(config.get("jurisdiction_bundle")),
        "target_jurisdictions": _text_list(config.get("target_jurisdictions")),
        "development_stage": _text_or_none(config.get("development_stage")),
        "asset_type_hint": _text_or_none(config.get("asset_type_hint")),
        "matter_type": _text_or_none(config.get("matter_type")),
        "intended_actions": _text_list(config.get("intended_actions")),
        "product_context": normalized_product_context,
    }

    if (
        any(value for key, value in launch_context.items() if key != "product_context")
        or normalized_product_context
    ):
        return launch_context
    return None


def _is_development_fixture(config: object) -> bool:
    """Return whether an analysis is an explicitly labelled dev-only fixture."""
    return isinstance(config, Mapping) and config.get("development_fixture") is True


def _invalidity_assessments_count(report_data: object) -> int | None:
    """Expose report coverage without implying that pipeline completion is assessment coverage."""
    if not isinstance(report_data, Mapping):
        return None
    assessments = report_data.get("invalidity_assessments")
    return len(assessments) if isinstance(assessments, list) else None


def serialize_analysis(
    analysis: Analysis,
    *,
    review_status: AnalysisReviewStatus | None = None,
    current_user_role: str | None = None,
    risk_ratings_restricted: bool = False,
    include_report_coverage: bool = True,
) -> dict:
    raw_input_type = getattr(analysis, "input_type", "name")
    submitted_input_type = (
        raw_input_type
        if raw_input_type in {"name", "smiles", "cas", "inchi", "inchikey"}
        else "name"
    )
    submitted_identity_confirmed = getattr(analysis, "submitted_identity_confirmed", False) is True
    raw_submitted_identity_value = getattr(
        analysis,
        "submitted_identity_value",
        None,
    )
    submitted_identity_value = (
        raw_submitted_identity_value
        if submitted_identity_confirmed and isinstance(raw_submitted_identity_value, str)
        else None
    )
    share_expires_at = analysis.share_active_until
    if share_expires_at is not None and share_expires_at.tzinfo is None:
        share_expires_at = share_expires_at.replace(tzinfo=UTC)
    share_active = analysis.share_active_grant_count > 0 and (
        share_expires_at is None or share_expires_at > datetime.now(UTC)
    )

    visible_review_status = (
        review_status if review_status_visible_for_role(current_user_role) else None
    )

    return {
        "id": analysis.id,
        "compound_input": analysis.compound_input,
        "compound_name": analysis.compound_name,
        "compound_smiles": analysis.compound_smiles,
        "input_type": submitted_input_type,
        "submitted_identity_confirmed": submitted_identity_confirmed,
        "submitted_identity_value": submitted_identity_value,
        "status": analysis.status,
        "current_step": analysis.current_step,
        "progress_pct": analysis.progress_pct,
        "development_fixture": _is_development_fixture(getattr(analysis, "config", None)),
        "invalidity_assessments_count": _invalidity_assessments_count(
            getattr(analysis, "report_data", None)
        )
        if include_report_coverage
        else None,
        "overall_risk": None if risk_ratings_restricted else analysis.overall_risk,
        "blocking_patents_count": (
            None if risk_ratings_restricted else analysis.blocking_patents_count
        ),
        "total_patents_found": analysis.total_patents_found,
        "executive_summary": (
            RISK_RESTRICTION_SUMMARY
            if risk_ratings_restricted and analysis.status == AnalysisStatus.COMPLETED
            else analysis.executive_summary
        ),
        "risk_ratings_restricted": risk_ratings_restricted,
        "estimated_cost_usd": analysis.estimated_cost_usd,
        "pipeline_duration_seconds": analysis.pipeline_duration_seconds,
        "flagged_for_review": analysis.flagged_for_review,
        "review_status": _serialize_analysis_review_status_summary(
            analysis,
            visible_review_status,
        ),
        "launch_context": _serialize_launch_context(getattr(analysis, "config", None)),
        "current_user_role": current_user_role,
        "share_active": share_active,
        "share_recipient_bound": share_active,
        "share_view_count": analysis.share_view_count,
        "share_last_viewed_at": analysis.share_last_viewed_at,
        "created_at": analysis.created_at,
        "updated_at": analysis.updated_at,
    }


def serialize_analysis_page(
    page: AnalysisPage,
    *,
    review_status_by_analysis_id: dict[uuid.UUID, AnalysisReviewStatus] | None = None,
    current_user_role: str | None = None,
    risk_ratings_restricted: bool = False,
) -> dict:
    return {
        "items": [
            serialize_analysis(
                analysis,
                review_status=(review_status_by_analysis_id or {}).get(analysis.id),
                current_user_role=current_user_role,
                risk_ratings_restricted=risk_ratings_restricted,
                include_report_coverage=False,
            )
            for analysis in page.items
        ],
        "total": page.total,
        "page": page.page,
        "per_page": page.per_page,
        "status_counts": page.status_counts,
    }


def serialize_cursor_page(
    page: AnalysisCursorPage,
    *,
    review_status_by_analysis_id: dict[uuid.UUID, AnalysisReviewStatus] | None = None,
    current_user_role: str | None = None,
    risk_ratings_restricted: bool = False,
) -> dict:
    return {
        "items": [
            serialize_analysis(
                analysis,
                review_status=(review_status_by_analysis_id or {}).get(analysis.id),
                current_user_role=current_user_role,
                risk_ratings_restricted=risk_ratings_restricted,
                include_report_coverage=False,
            )
            for analysis in page.items
        ],
        "next_cursor": page.next_cursor,
    }


async def get_analysis_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    include_deleted: bool = False,
    for_update: bool = False,
) -> Analysis:
    """Fetch a single org-scoped analysis.

    Soft-deleted rows (``status == DELETED``) are hidden by default so that the
    public read/report/export/share surfaces cannot resurrect an analysis that a
    tenant deleted (GDPR Art. 17 erasure intent — list queries already filter
    ``status != DELETED``; this closes the by-id fetch path that bypassed them).

    Only lifecycle callers that must observe the terminal DELETED state — the
    idempotent delete no-op and the flag-for-review rejection — pass
    ``include_deleted=True``.
    """
    conditions = [Analysis.id == analysis_id, Analysis.org_id == org_id]
    if not include_deleted:
        conditions.append(Analysis.status != AnalysisStatus.DELETED)
    statement = select(Analysis).where(*conditions)
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise APIError(404, "Not Found", "Analysis not found")
    return analysis


async def create_analysis(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: CreateAnalysisRequest,
    request: Request,
    idempotency_key: str,
) -> AnalysisCreationResult:
    normalized_idempotency_key = _validate_launch_idempotency_key(idempotency_key)
    key_digest = _launch_idempotency_key_digest(
        org_id=org_id,
        idempotency_key=normalized_idempotency_key,
    )
    payload_digest = _launch_payload_digest(body)

    await _lock_analysis_launch_org(db, org_id=org_id)
    existing_analysis = await _get_analysis_by_launch_key(
        db,
        org_id=org_id,
        key_digest=key_digest,
    )
    if existing_analysis is not None:
        creation = _replay_analysis_or_conflict(
            existing_analysis,
            payload_digest=payload_digest,
        )
        await _redrive_pending_analysis(db, existing_analysis, org_id=org_id)
        return creation

    analysis_id = uuid.uuid4()
    credit_reservation_id = str(uuid.uuid4())
    credit_reservations: list[AnalysisCreditReservation] = []
    within_limit, used, limit = await check_usage_limit(
        db,
        org_id,
        reservation_id=credit_reservation_id,
        reservation_details={"source": "analysis.create"},
        credit_reservations=credit_reservations,
        analysis_id=analysis_id,
        defer_credit_consumption=True,
    )
    if not within_limit:
        raise APIError(
            429,
            "Too Many Requests",
            (
                "No FTO report request capacity remains this period. "
                f"{used} of {limit} report requests used."
            ),
            type_uri=problem_type_uri("analysis-capacity-exhausted"),
        )

    compound_metadata = _compound_input_metadata(
        body.compound_input,
        input_type=body.input_type,
    )
    logger.info(
        "create_analysis",
        user_id=str(user_id),
        org_id=str(org_id),
        **compound_metadata,
        trust_mode=body.trust_mode,
    )

    org_default_config = await load_org_default_config(db, org_id=org_id)
    runtime_config = body.runtime_config(org_default_config=org_default_config)
    analysis = Analysis(
        id=analysis_id,
        org_id=org_id,
        compound_input=body.compound_input,
        input_type=body.input_type,
        submitted_identity_confirmed=body.submitted_identity_confirmed,
        submitted_identity_value=body.submitted_identity_value,
        launch_idempotency_key_digest=key_digest,
        launch_payload_digest=payload_digest,
        config=runtime_config,
        initiated_by=user_id,
        status=AnalysisStatus.PENDING,
    )
    db.add(analysis)
    try:
        await db.flush()
        for reservation in credit_reservations:
            await consume_analysis_credits(
                db,
                org_id=org_id,
                credits=reservation.credits,
                analysis_id=analysis.id,
                details={
                    "requested_analyses": 1,
                    "included_remaining": 0,
                    "source": "analysis.create",
                },
                reservation_id=reservation.reservation_id,
            )
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis.id,
            action="analysis.created",
            details=compound_metadata,
            request=request,
            fail_closed=True,
        )
        await db.commit()
        await db.refresh(analysis)
    except Exception:
        await db.rollback()
        raise

    from api.services.task_dispatcher import build_dispatcher

    try:
        await build_dispatcher().dispatch_pipeline_run(
            analysis_id=str(analysis.id),
            org_id=str(org_id),
        )
    except Exception as exc:
        logger.error(
            "pipeline_dispatch_failed",
            analysis_id=str(analysis.id),
            org_id=str(org_id),
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        # A dispatcher timeout is ambiguous: the queue may have accepted the
        # task even though the response never reached this process. Preserve
        # the durable PENDING launch receipt and its bound credit reservation.
        # Same-key replay can redrive it without reserving capacity again, and
        # the stale-launch reconciler only terminalizes/refunds after a later
        # authoritative redrive also fails.
        raise APIError(503, "Service Unavailable", "Pipeline dispatch failed") from exc

    logger.info("analysis_created", analysis_id=str(analysis.id), user_id=str(user_id))
    return AnalysisCreationResult(analysis=analysis, replayed=False)


async def list_analyses_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
    status_filter: AnalysisStatus | None = None,
    risk_filter: str | None = None,
    search: str | None = None,
    sort_by: str = "date-desc",
) -> AnalysisPage:
    base_filters = [
        Analysis.org_id == org_id,
        Analysis.status != AnalysisStatus.DELETED,
    ]
    if risk_filter:
        base_filters.append(Analysis.overall_risk == risk_filter)
    if search:
        pattern = f"%{_escape_like_pattern(search)}%"
        base_filters.append(
            or_(
                Analysis.compound_input.ilike(pattern, escape=_LIKE_ESCAPE_CHARACTER),
                Analysis.compound_name.ilike(pattern, escape=_LIKE_ESCAPE_CHARACTER),
            )
        )

    status_count_query = (
        select(Analysis.status, func.count()).where(*base_filters).group_by(Analysis.status)
    )
    status_count_rows = (await db.execute(status_count_query)).all()
    status_counts = {
        "all": 0,
        AnalysisStatus.PENDING.value: 0,
        AnalysisStatus.RUNNING.value: 0,
        AnalysisStatus.COMPLETED.value: 0,
        AnalysisStatus.FAILED.value: 0,
        AnalysisStatus.CANCELLED.value: 0,
    }
    for status, count in status_count_rows:
        status_key = status.value if isinstance(status, AnalysisStatus) else str(status)
        if status_key in status_counts and status_key != "all":
            status_counts[status_key] = int(count)
    status_counts["all"] = sum(count for key, count in status_counts.items() if key != "all")

    query = select(Analysis).options(defer(Analysis.report_data)).where(*base_filters)

    if status_filter:
        query = query.where(Analysis.status == status_filter)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(*_analysis_sort_clauses(sort_by))
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    return AnalysisPage(
        items=list(result.scalars().all()),
        total=total,
        page=page,
        per_page=per_page,
        status_counts=status_counts,
    )


async def list_analyses_cursor(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 20,
    status_filter: AnalysisStatus | None = None,
    risk_filter: str | None = None,
) -> AnalysisCursorPage:
    """Return a cursor-based page of analyses ordered by created_at DESC.

    The opaque cursor encodes (created_at, id) so that pages are stable even
    when new analyses are inserted between requests.
    """
    limit = min(max(limit, 1), 100)

    query = (
        select(Analysis)
        .options(defer(Analysis.report_data))
        .where(
            Analysis.org_id == org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
    )

    if status_filter:
        query = query.where(Analysis.status == status_filter)
    if risk_filter:
        query = query.where(Analysis.overall_risk == risk_filter)

    if cursor is not None:
        try:
            cursor_ts, cursor_id = _decode_cursor(cursor)
        except ValueError as err:
            raise APIError(400, "Bad Request", "Invalid pagination cursor") from err
        # Return rows strictly before the cursor position (created_at DESC, id DESC tiebreak)
        query = query.where(
            (Analysis.created_at < cursor_ts)
            | ((Analysis.created_at == cursor_ts) & (Analysis.id < cursor_id))
        )

    query = query.order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows: list[Analysis] = list(result.scalars().all())

    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor: str | None = _encode_cursor(last.created_at, last.id)
    else:
        next_cursor = None

    return AnalysisCursorPage(items=rows, next_cursor=next_cursor)


async def load_analysis_review_status_lookup(
    db: AsyncSession,
    *,
    analyses: list[Analysis],
    org_id: uuid.UUID,
) -> dict[uuid.UUID, AnalysisReviewStatus]:
    analysis_ids = [analysis.id for analysis in analyses]
    if not analysis_ids:
        return {}

    result = await db.execute(
        select(AnalysisReviewStatus).where(
            AnalysisReviewStatus.org_id == org_id,
            AnalysisReviewStatus.analysis_id.in_(analysis_ids),
        )
    )
    rows = result.scalars().all()
    return {row.analysis_id: row for row in rows}


async def load_analysis_review_status(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> AnalysisReviewStatus | None:
    result = await db.execute(
        select(AnalysisReviewStatus).where(
            AnalysisReviewStatus.analysis_id == analysis_id,
            AnalysisReviewStatus.org_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_analysis(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> Analysis:
    logger.info("delete_analysis", analysis_id=str(analysis_id), org_id=str(org_id))
    # include_deleted: re-deleting an already-deleted analysis is an idempotent
    # no-op, so the terminal DELETED row must remain visible to this caller.
    analysis = await get_analysis_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        include_deleted=True,
        for_update=True,
    )

    previous_status = analysis.status
    audit_action = "analysis.deleted"

    if analysis.status in (AnalysisStatus.PENDING, AnalysisStatus.RUNNING):
        refunded_credits = await refund_cancelled_analysis_credits(
            db,
            org_id=org_id,
            analysis_id=analysis_id,
        )
        analysis.status = AnalysisStatus.CANCELLED
        audit_action = "analysis.cancelled"
        logger.info(
            "analysis_cancelled",
            analysis_id=str(analysis_id),
            previous_status=previous_status.value,
            refunded_credits=refunded_credits,
        )
    elif analysis.status == AnalysisStatus.DELETED:
        audit_action = "analysis.delete.noop"
        logger.info("analysis_already_deleted", analysis_id=str(analysis_id))
    else:
        analysis.status = AnalysisStatus.DELETED
        logger.info(
            "analysis_soft_deleted",
            analysis_id=str(analysis_id),
            previous_status=previous_status.value,
        )

    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis_id,
            action=audit_action,
            details={
                "previous_status": previous_status.value,
                "new_status": analysis.status.value,
                "refunded_credits": refunded_credits
                if previous_status in (AnalysisStatus.PENDING, AnalysisStatus.RUNNING)
                else 0,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return analysis


async def flag_analysis_for_review(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> dict:
    # include_deleted: this path must observe DELETED in order to reject it with
    # a 409 rather than a misleading 404.
    analysis = await get_analysis_for_org(
        db, analysis_id=analysis_id, org_id=org_id, include_deleted=True
    )
    if analysis.status in (AnalysisStatus.DELETED, AnalysisStatus.CANCELLED):
        raise APIError(409, "Conflict", "Cannot flag a deleted or cancelled analysis for review")
    analysis.flagged_for_review = True
    analysis.flagged_by = user_id
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis_id,
            action="analysis.flagged_for_review",
            details={"flagged_for_review": True},
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "analysis_flagged_for_review",
        analysis_id=str(analysis_id),
        user_id=str(user_id),
    )
    return {"status": "flagged"}
