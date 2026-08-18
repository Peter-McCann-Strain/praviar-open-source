"""Preparation helpers for Step 4 adaptive claim analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.pipeline.analysis.enrichment import enrich_patents_for_analysis_impl
from praviar_pipeline.pipeline.analysis.prep_helpers import (
    build_enabled_analysis_tools,
)
from praviar_pipeline.pipeline.analysis.prep_helpers import (
    build_triage_map as build_triage_map_impl,
)
from praviar_pipeline.pipeline.analysis.prosecution import fetch_prosecution_context_impl
from praviar_pipeline.tools import FTOToolkit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult

logger = structlog.get_logger()


async def fetch_prosecution_context(patent_id: str) -> dict[str, Any] | None:
    return await fetch_prosecution_context_impl(patent_id)


async def enrich_patents_for_analysis(
    patents_to_analyze: list[PatentHit],
    settings: Settings,
    *,
    bigquery_client_cls: Any,
    fetch_prosecution_context: Callable[[str], Awaitable[dict[str, Any] | None]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    return await enrich_patents_for_analysis_impl(
        patents_to_analyze,
        settings,
        bigquery_client_cls=bigquery_client_cls,
        fetch_prosecution_context=fetch_prosecution_context,
    )


def build_triage_map(triage_results: list[TriageResult] | None) -> dict[str, TriageResult]:
    return build_triage_map_impl(triage_results)


def build_analysis_toolkit(
    patents_to_analyze: list[PatentHit],
    settings: Settings,
) -> FTOToolkit | None:
    enabled_tools = build_enabled_analysis_tools(
        tools_enabled=settings.tools_enabled,
        has_uspto_odp_api_key=bool(settings.uspto_odp_api_key),
    )
    if enabled_tools is None:
        return None
    if "check_patent_status" not in enabled_tools:
        logger.info(
            "check_patent_status_disabled",
        )

    toolkit = FTOToolkit.from_patent_hits(patents_to_analyze, enabled_tools=enabled_tools)
    logger.info(
        "tools_enabled",
        tool_count=len(toolkit.tool_definitions),
        tools=enabled_tools,
        cached_patents=len(patents_to_analyze),
    )
    return toolkit
