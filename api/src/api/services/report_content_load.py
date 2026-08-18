"""Report loading and validation helpers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import APISettings
from api.db.models import Analysis, AnalysisStatus
from api.errors import APIError
from api.schemas.reports import FTOReportResponse
from api.services.report_access import (
    analysis_status_value,
    build_governed_report_summary,
    report_payload_fingerprint,
    require_completed_report_payload,
    require_report_publishability,
)


async def _authorize_report_content_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> str:
    result = await db.execute(
        select(Analysis.status).where(Analysis.id == analysis_id, Analysis.org_id == org_id)
    )
    analysis_status = result.scalar_one_or_none()
    if analysis_status is None:
        raise APIError(404, "Not Found", "Analysis not found")

    if analysis_status_value(analysis_status) != AnalysisStatus.COMPLETED.value:
        raise APIError(404, "Not Found", "Report not yet available")

    result = await db.execute(
        select(Analysis.report_data).where(
            Analysis.id == analysis_id,
            Analysis.org_id == org_id,
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.report_data.isnot(None),
            func.jsonb_typeof(Analysis.report_data) == "object",
            Analysis.report_data != {},
        )
    )
    raw_report_data: object = result.scalar_one_or_none()
    if not isinstance(raw_report_data, dict):
        raise APIError(404, "Not Found", "Report not yet available")
    report_data: dict[str, Any] = raw_report_data
    require_report_publishability(
        report_data,
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        detail="Report not yet available",
    )
    return report_payload_fingerprint(report_data)


def _fail_closed_on_report_cache_error(settings: APISettings | None = None) -> bool:
    return getattr(settings, "app_env", None) == "prod"


def _raise_report_cache_backend_unavailable(action: str, exc: Exception) -> None:
    raise APIError(
        503,
        "Service Unavailable",
        f"Report cache backend is unavailable; refusing to {action}.",
    ) from exc


async def load_report_for_org_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    get_cached_report_fn: Callable[..., Awaitable[dict | None]],
    set_cached_report_fn: Callable[..., Awaitable[None]],
    get_analysis_for_org_fn: Callable[..., Awaitable[Any]],
    logger: structlog.stdlib.BoundLogger,
    settings: APISettings | None = None,
) -> dict:
    """Load, cache, and schema-validate a report payload for an org-scoped analysis."""
    org_cache_key = str(org_id)
    analysis_cache_key = str(analysis_id)
    report_version = await _authorize_report_content_for_org(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
    )

    try:
        cached = await get_cached_report_fn(
            org_cache_key,
            analysis_cache_key,
            version=report_version,
        )
    except Exception as exc:
        logger.warning(
            "report_cache_load_failed",
            analysis_id=str(analysis_id),
            exc_info=True,
        )
        if _fail_closed_on_report_cache_error(settings):
            _raise_report_cache_backend_unavailable("load report content", exc)
        cached = None

    if cached is not None:
        try:
            require_report_publishability(
                cached,
                analysis_id=analysis_cache_key,
                org_id=org_cache_key,
            )
        except APIError:
            logger.warning(
                "report_cache_payload_failed_publishability",
                analysis_id=str(analysis_id),
            )
            cached = None
        else:
            cached_version = report_payload_fingerprint(cached)
            if cached_version != report_version:
                logger.warning(
                    "report_cache_version_mismatch",
                    analysis_id=str(analysis_id),
                    cached_version=cached_version,
                    authoritative_version=report_version,
                )
                cached = None

    if cached is None:
        analysis = await get_analysis_for_org_fn(db, analysis_id=analysis_id, org_id=org_id)
        report_data = require_completed_report_payload(analysis)

        try:
            await set_cached_report_fn(
                org_cache_key,
                analysis_cache_key,
                report_data,
                version=report_version,
            )
        except Exception as exc:
            logger.warning(
                "cache_set_failed_after_db_load",
                analysis_id=str(analysis_id),
                exc_info=True,
            )
            if _fail_closed_on_report_cache_error(settings):
                _raise_report_cache_backend_unavailable("persist report content", exc)
    else:
        report_data = cached

    try:
        FTOReportResponse.model_validate(report_data)
    except ValidationError as exc:
        logger.error(
            "report_validation_failed",
            analysis_id=str(analysis_id),
            error_count=exc.error_count(),
            errors=str(exc.errors()[:5]),
            exc_info=True,
        )
        raise APIError(
            500,
            "Internal Server Error",
            "Report data failed schema validation — contact support",
        ) from exc

    return report_data


async def get_report_summary_for_org_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    get_analysis_for_org_fn: Callable[..., Awaitable[Any]],
    risk_ratings_restricted: bool = False,
) -> dict:
    """Return the summary fields exposed to all roles."""
    analysis = await get_analysis_for_org_fn(db, analysis_id=analysis_id, org_id=org_id)
    return build_governed_report_summary(
        analysis,
        risk_ratings_restricted=risk_ratings_restricted,
    )
