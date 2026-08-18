"""Search and redaction helpers for report content."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.report_access import require_completed_report_payload
from api.services.report_content_search_helpers import search_report_content_impl


def filter_risk_ratings_impl(report_data: dict) -> dict:
    """Redact legal-risk conclusions for non-attorney viewers."""
    filtered = copy.deepcopy(report_data)

    if "risk_summary" in filtered and isinstance(filtered["risk_summary"], dict):
        filtered["risk_summary"]["overall_risk"] = None
        filtered["risk_summary"]["blocking_patents_count"] = None
        filtered["risk_summary"]["executive_summary"] = (
            "Risk assessment details are restricted to attorney-role users. "
            "Please contact your organization's patent attorney for the full analysis."
        )
        filtered["risk_summary"]["key_risks"] = []

    filtered.pop("action_items", None)
    filtered.pop("clearance_decision", None)
    filtered.pop("decision_scope", None)
    filtered.pop("supporting_scope", None)
    filtered.pop("certification_scope", None)
    filtered.pop("cohort_status", None)
    filtered.pop("jurisdiction_decisions", None)
    filtered.pop("prosecution_dossiers", None)
    filtered.pop("claim_construction_record", None)
    filtered.pop("future_risk", None)
    filtered.pop("commercial_exposure", None)
    filtered.pop("claim_program_decisions", None)
    filtered.pop("evidence_artifacts", None)
    filtered.pop("evidence_adapter_results", None)
    filtered.pop("collector_runs", None)
    filtered.pop("evidence_collection_plan", None)
    filtered.pop("coverage_gaps", None)
    filtered.pop("matter_graph", None)
    filtered.pop("matter_graph_summary", None)
    filtered.pop("matter_store", None)
    filtered.pop("authority_coverage", None)
    filtered.pop("record_completeness", None)
    filtered.pop("run_observability", None)
    filtered.pop("matter_evidence_index", None)
    filtered.pop("critic_report", None)

    search_loop_result = filtered.get("search_loop_result")
    if isinstance(search_loop_result, dict):
        search_loop_result.pop("pending_collection_directives", None)
        final_assessment = search_loop_result.get("final_assessment")
        if isinstance(final_assessment, dict):
            final_assessment.pop("evidence_collection_directives", None)
        for iteration in search_loop_result.get("iteration_logs", []):
            if isinstance(iteration, dict) and isinstance(iteration.get("assessment"), dict):
                iteration["assessment"].pop("evidence_collection_directives", None)

    if "patent_analyses" in filtered and isinstance(filtered["patent_analyses"], list):
        for analysis in filtered["patent_analyses"]:
            if isinstance(analysis, dict):
                analysis["risk_level"] = None
                analysis.pop("risk_summary", None)
                analysis.pop("design_around_suggestions", None)

    return filtered


async def search_report_for_org_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    query_text: str,
    get_analysis_for_org_fn: Callable[..., Awaitable[Any]],
) -> dict:
    """Load a report for an org-scoped analysis and run keyword search over it."""
    analysis = await get_analysis_for_org_fn(db, analysis_id=analysis_id, org_id=org_id)
    report_data = require_completed_report_payload(analysis)
    return search_report_content_impl(report_data, query_text)
