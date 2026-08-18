"""Business logic facade for report retrieval, validation, and search."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.cache import get_cached_report, set_cached_report
from api.config import get_settings
from api.schemas.report_evidence_search import EvidenceRetrievalMode
from api.services import report_content_load, report_content_search, report_evidence_search
from api.services.analyses import get_analysis_for_org

logger = structlog.get_logger()


def filter_risk_ratings(report_data: dict) -> dict:
    """Redact legal-risk conclusions for non-attorney viewers."""
    return report_content_search.filter_risk_ratings_impl(report_data)


async def load_report_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict:
    """Load, cache, and schema-validate a report payload for an org-scoped analysis."""
    return await report_content_load.load_report_for_org_impl(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        get_cached_report_fn=get_cached_report,
        set_cached_report_fn=set_cached_report,
        get_analysis_for_org_fn=get_analysis_for_org,
        logger=logger,
        settings=get_settings(),
    )


async def get_report_summary_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    risk_ratings_restricted: bool = False,
) -> dict:
    """Return the summary fields exposed to all roles."""
    return await report_content_load.get_report_summary_for_org_impl(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        get_analysis_for_org_fn=get_analysis_for_org,
        risk_ratings_restricted=risk_ratings_restricted,
    )


def search_report_content(report: dict, query_text: str) -> dict:
    """Search report content via keyword matching over core narrative sections."""
    return report_content_search.search_report_content_impl(report, query_text)


async def search_report_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    query_text: str,
) -> dict:
    """Load a report for an org-scoped analysis and run keyword search over it."""
    return await report_content_search.search_report_for_org_impl(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        query_text=query_text,
        get_analysis_for_org_fn=get_analysis_for_org,
    )


async def search_report_evidence_for_org(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    query_text: str,
    retrieval_mode: EvidenceRetrievalMode = "report_evidence",
) -> dict:
    """Load a report for an org-scoped analysis and search its governed evidence fabric."""
    return await report_evidence_search.search_report_evidence_for_org_impl(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        query_text=query_text,
        retrieval_mode=retrieval_mode,
        get_analysis_for_org_fn=get_analysis_for_org,
    )
