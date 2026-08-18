"""Governed evidence search over report provenance and evidence fabric.

This module is a thin facade over three split modules:

* ``report_evidence_filter`` — pure helpers / business-rule predicates
* ``report_evidence_format`` — result builders and report-internal searchers
* ``report_external_providers`` — async outbound provider calls

The public functions exposed here keep their original signatures so
existing callers (routes, monitor runtime, report workspace) and existing
tests that ``patch("api.services.report_evidence_search.<name>")`` keep
working without changes.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import APIError
from api.schemas.report_evidence_search import EvidenceRetrievalMode

# Re-export the licensed family overlay binding here so existing tests can
# patch ``api.services.report_evidence_search.search_licensed_family_overlay``
# and have the patched symbol picked up at call time.
from api.services import report_external_evidence
from api.services.licensed_family_overlay import search_licensed_family_overlay
from api.services.report_access import require_completed_report_payload
from api.services.report_evidence_filter import (
    external_retrieval_allowed as _external_retrieval_allowed,
)
from api.services.report_evidence_format import (
    build_scope as _build_scope,
)
from api.services.report_evidence_format import (
    search_report_evidence_impl as _search_report_evidence_impl_inner,
)
from api.services.report_external_providers import (
    build_external_query_context as _build_external_query_context,
)
from api.services.report_external_providers import (
    search_external_evidence_impl as _search_external_evidence_impl_inner,
)


def _external_provider_execution_ready(
    report: dict[str, Any],
    query_text: str,
    *,
    org_id: str | uuid.UUID | None = None,
) -> bool:
    context = _build_external_query_context(
        report,
        query=query_text,
        org_id=org_id,
    )
    return bool(report_external_evidence.active_external_provider_specs(context))


def build_report_evidence_scope(
    report: dict[str, Any],
    *,
    external_retrieval_allowed: bool | None = None,
    org_id: str | uuid.UUID | None = None,
):
    """Build governed evidence-scope metadata for report-grounded analyst surfaces."""
    return _build_scope(
        report,
        external_retrieval_allowed_flag=external_retrieval_allowed,
        org_id=org_id,
        build_external_query_context_fn=_build_external_query_context,
    )


def search_report_evidence_impl(
    report: dict[str, Any],
    query_text: str,
    *,
    external_retrieval_allowed: bool | None = None,
    org_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    return _search_report_evidence_impl_inner(
        report,
        query_text,
        external_retrieval_allowed_flag=external_retrieval_allowed,
        org_id=org_id,
        build_external_query_context_fn=_build_external_query_context,
    )


async def search_external_evidence_impl(
    report: dict[str, Any],
    query_text: str,
    *,
    org_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    # Re-resolve the symbol from this module's namespace so that
    # ``patch("api.services.report_evidence_search.search_licensed_family_overlay", ...)``
    # is honored even though the providers module imported the original
    # binding at import time.
    return await _search_external_evidence_impl_inner(
        report,
        query_text,
        org_id=org_id,
        licensed_family_overlay_fn=search_licensed_family_overlay,
    )


async def search_report_evidence_for_org_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    query_text: str,
    retrieval_mode: EvidenceRetrievalMode = "report_evidence",
    get_analysis_for_org_fn: Callable[..., Awaitable[Any]],
) -> dict[str, Any]:
    """Load a report for an org-scoped analysis and search its evidence fabric."""
    analysis = await get_analysis_for_org_fn(db, analysis_id=analysis_id, org_id=org_id)
    report_data = require_completed_report_payload(analysis)

    if retrieval_mode == "external_evidence":
        if not _external_retrieval_allowed(report_data):
            raise APIError(
                403,
                "Forbidden",
                "Governed external evidence expansion is unavailable for explorer-mode reports",
            )
        if not _external_provider_execution_ready(
            report_data,
            query_text,
            org_id=org_id,
        ):
            raise APIError(
                409,
                "Conflict",
                (
                    "Governed external evidence expansion requires an active live "
                    "provider for this report scope."
                ),
            )
        # Use the local binding so test patches on this module are honored.
        return await search_external_evidence_impl(
            report_data,
            query_text,
            org_id=org_id,
        )

    return search_report_evidence_impl(
        report_data,
        query_text,
        external_retrieval_allowed=_external_retrieval_allowed(report_data),
        org_id=org_id,
    )


__all__ = [
    "build_report_evidence_scope",
    "search_external_evidence_impl",
    "search_licensed_family_overlay",
    "search_report_evidence_for_org_impl",
    "search_report_evidence_impl",
]
