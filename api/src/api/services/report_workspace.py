"""Workspace-summary helpers for completed report surfaces."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis
from api.errors import APIError
from api.schemas.chat import ChatPolicy
from api.schemas.reports import FTOReportResponse
from api.schemas.reports_fto_io import ReportSummaryResponse
from api.schemas.reports_workspace import (
    MonitorSeedDefaultsResponse,
    ReportWorkspaceSummaryResponse,
    WorkspaceEvidenceQueryResponse,
)
from api.services.chat_history import build_chat_policy
from api.services.report_access import (
    normalize_report_trust_mode,
    require_completed_report_payload,
)
from api.services.report_content import filter_risk_ratings
from api.services.report_evidence_search import build_report_evidence_scope

_MODALITY_QUERY_MAP = {
    "small_molecule": "composition claims",
    "markush_candidate": "Markush claims",
    "biologic_or_sequence": "sequence claims",
    "formulation": "formulation patent",
    "process_or_synthesis": "synthesis patent",
    "combination": "combination therapy patent",
    "unknown": "patent claims",
}

_RISK_TO_SCHEDULE = {
    "critical": "daily",
    "high": "daily",
    "medium": "weekly",
    "low": "monthly",
}

WorkspaceQueryKind = Literal["compound", "modality", "jurisdiction", "search_strategy", "risk"]
MonitorSchedule = Literal["daily", "weekly", "monthly"]


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _report_summary_from_report_data(
    report_data: dict[str, Any],
    analysis: Analysis,
    *,
    risk_restricted: bool,
) -> ReportSummaryResponse:
    risk_summary_raw = report_data.get("risk_summary")
    risk_summary: dict[str, Any] = risk_summary_raw if isinstance(risk_summary_raw, dict) else {}
    return ReportSummaryResponse.model_validate(
        {
            "overall_risk": risk_summary.get("overall_risk"),
            "blocking_patents_count": risk_summary.get(
                "blocking_patents_count",
                analysis.blocking_patents_count or 0,
            ),
            "total_patents_found": report_data.get(
                "total_patents_found",
                analysis.total_patents_found or 0,
            ),
            "executive_summary": risk_summary.get(
                "executive_summary",
                analysis.executive_summary or "",
            ),
            "risk_ratings_restricted": risk_restricted,
        }
    )


def _redact_workspace_report_for_non_attorney(
    report_data: dict[str, Any],
) -> dict[str, Any]:
    """Strip restricted workspace affordances for non-attorney roles."""
    redacted = filter_risk_ratings(copy.deepcopy(report_data))
    risk_summary = redacted.get("risk_summary")
    if isinstance(risk_summary, dict):
        risk_summary["overall_risk"] = None
        risk_summary["blocking_patents_count"] = None
        risk_summary["executive_summary"] = (
            "Risk assessment details are restricted to attorney-role users. "
            "Please contact your organization's patent attorney for the full analysis."
        )

    redacted["trust_mode"] = "explorer"
    redacted.pop("routing_profile", None)
    redacted.pop("opinion_readiness", None)
    redacted.pop("jurisdiction_matrix", None)
    redacted.pop("jurisdiction_certification", None)
    redacted.pop("jurisdiction_source_coverage", None)
    redacted.pop("source_convergence", None)
    redacted.pop("data_coverage", None)
    return redacted


def _build_target_jurisdictions(report_data: dict[str, Any]) -> list[str]:
    jurisdictions: list[str] = []
    seen: set[str] = set()

    for value in report_data.get("target_jurisdictions", []) or []:
        jurisdiction = _normalize_text(value).upper()
        if jurisdiction and jurisdiction not in seen:
            jurisdictions.append(jurisdiction)
            seen.add(jurisdiction)

    routing_profile = report_data.get("routing_profile") or {}
    for value in routing_profile.get("doctrine_packs", []) or []:
        jurisdiction = _normalize_text(value).upper()
        if jurisdiction and jurisdiction not in seen:
            jurisdictions.append(jurisdiction)
            seen.add(jurisdiction)

    for item in report_data.get("jurisdiction_matrix", []) or []:
        if not isinstance(item, dict):
            continue
        jurisdiction = _normalize_text(item.get("jurisdiction")).upper()
        if jurisdiction and jurisdiction not in seen:
            jurisdictions.append(jurisdiction)
            seen.add(jurisdiction)

    return jurisdictions


def _extract_compound_context(report_data: dict[str, Any], analysis: Analysis) -> tuple[str, str]:
    compound_raw = report_data.get("compound")
    compound: dict[str, Any] = compound_raw if isinstance(compound_raw, dict) else {}
    compound_name = _normalize_text(compound.get("name") or analysis.compound_name or "")
    compound_smiles = _normalize_text(
        compound.get("canonical_smiles") or compound.get("smiles") or analysis.compound_smiles or ""
    )
    return compound_name, compound_smiles


def _extract_suggested_terms(report_data: dict[str, Any]) -> dict[str, str]:
    search_loop_result_raw = report_data.get("search_loop_result")
    search_loop_result: dict[str, Any] = (
        search_loop_result_raw if isinstance(search_loop_result_raw, dict) else {}
    )
    final_assessment_raw = search_loop_result.get("final_assessment")
    final_assessment: dict[str, Any] = (
        final_assessment_raw if isinstance(final_assessment_raw, dict) else {}
    )
    suggested_queries_raw = final_assessment.get("suggested_queries")
    suggested_queries: dict[str, Any] = (
        suggested_queries_raw if isinstance(suggested_queries_raw, dict) else {}
    )

    terms: dict[str, str] = {}
    for key in (
        "patent_synonyms",
        "cpc_codes",
        "key_assignees",
        "process_keywords",
        "compound_class_terms",
    ):
        values = suggested_queries.get(key) or []
        if values:
            first = _normalize_text(values[0])
            if first:
                terms[key] = first
    return terms


def _build_suggested_evidence_queries(
    report_data: dict[str, Any],
    *,
    compound_name: str,
    routing_profile: dict[str, Any],
    target_jurisdictions: list[str],
) -> list[WorkspaceEvidenceQueryResponse]:
    queries: list[WorkspaceEvidenceQueryResponse] = []
    seen: set[str] = set()

    def add_query(kind: WorkspaceQueryKind, query: str, rationale: str, source: str) -> None:
        normalized = query.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        queries.append(
            WorkspaceEvidenceQueryResponse(
                kind=kind,
                query=query.strip(),
                rationale=rationale,
                source=source,
            )
        )

    suggested_terms = _extract_suggested_terms(report_data)
    modality = (
        _normalize_text(routing_profile.get("modality")).lower()
        or _normalize_text(report_data.get("asset_type_hint")).lower()
    )

    if compound_name:
        add_query(
            "compound",
            f"{compound_name} patent",
            "Baseline compound search derived from the completed report.",
            "compound.name",
        )

    modality_term = _MODALITY_QUERY_MAP.get(modality, _MODALITY_QUERY_MAP["unknown"])
    if compound_name:
        add_query(
            "modality",
            f"{compound_name} {modality_term}",
            "Specialized query derived from the routed modality profile.",
            "routing_profile.modality",
        )

    if target_jurisdictions and compound_name:
        add_query(
            "jurisdiction",
            f"{compound_name} {target_jurisdictions[0]} patent",
            "Jurisdiction-specific follow-up derived from the report's target coverage.",
            "target_jurisdictions",
        )

    if compound_name and suggested_terms.get("key_assignees"):
        add_query(
            "search_strategy",
            f'{compound_name} assignee "{suggested_terms["key_assignees"]}"',
            "A report-backed assignee query taken from the search loop suggestions.",
            "search_loop_result.final_assessment.suggested_queries.key_assignees",
        )

    if compound_name and suggested_terms.get("cpc_codes"):
        add_query(
            "search_strategy",
            f"{compound_name} CPC {suggested_terms['cpc_codes']}",
            "A CPC-oriented follow-up taken from the report's search suggestions.",
            "search_loop_result.final_assessment.suggested_queries.cpc_codes",
        )

    if compound_name and suggested_terms.get("compound_class_terms"):
        add_query(
            "search_strategy",
            f"{compound_name} {suggested_terms['compound_class_terms']}",
            "A compound-class follow-up taken from the report's search suggestions.",
            "search_loop_result.final_assessment.suggested_queries.compound_class_terms",
        )

    if compound_name and not queries:
        add_query(
            "risk",
            f"{compound_name} claims",
            "Fallback query when no structured search-loop terms are available.",
            "report.compound",
        )

    return queries[:4]


def _build_monitor_seed_defaults(
    *,
    analysis: Analysis,
    report_data: dict[str, Any],
    trust_mode: str,
    compound_name: str,
    compound_smiles: str,
    risk_restricted: bool,
) -> MonitorSeedDefaultsResponse:
    risk_summary_raw = report_data.get("risk_summary")
    risk_summary: dict[str, Any] = risk_summary_raw if isinstance(risk_summary_raw, dict) else {}
    overall_risk_source = risk_summary.get("overall_risk")
    if not risk_restricted:
        overall_risk_source = overall_risk_source or analysis.overall_risk
    overall_risk = _normalize_text(overall_risk_source).lower()
    schedule = cast(MonitorSchedule, _RISK_TO_SCHEDULE.get(overall_risk, "weekly"))
    if trust_mode == "monitor" and schedule == "monthly":
        schedule = "weekly"

    missing_fields: list[str] = []
    if not compound_name:
        missing_fields.append("compound_name")
    if not compound_smiles:
        missing_fields.append("compound_smiles")

    return MonitorSeedDefaultsResponse(
        analysis_id=analysis.id,
        compound_name=compound_name,
        compound_smiles=compound_smiles,
        schedule=schedule,
        source_report_id=_normalize_text(report_data.get("report_id")),
        source_trust_mode=trust_mode,
        requires_manual_input=bool(missing_fields),
        missing_fields=missing_fields,
    )


async def build_report_workspace_summary_for_org_impl(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    get_analysis_for_org_fn: Callable[..., Awaitable[Any]],
    risk_restricted: bool = False,
) -> ReportWorkspaceSummaryResponse:
    """Build a governed, read-only workspace summary for a completed analysis."""
    analysis = await get_analysis_for_org_fn(db, analysis_id=analysis_id, org_id=org_id)
    report_data = require_completed_report_payload(analysis)
    try:
        FTOReportResponse.model_validate(report_data)
    except ValidationError as exc:
        raise APIError(
            500,
            "Internal Server Error",
            "Report data failed schema validation — contact support",
        ) from exc

    if risk_restricted:
        report_data = _redact_workspace_report_for_non_attorney(report_data)

    trust_mode = normalize_report_trust_mode(report_data)
    routing_profile = dict(report_data.get("routing_profile") or {})
    opinion_readiness = dict(report_data.get("opinion_readiness") or {})
    data_coverage = dict(report_data.get("data_coverage") or {})
    source_convergence = dict(report_data.get("source_convergence") or {})
    evidence_scope = build_report_evidence_scope(
        report_data,
        external_retrieval_allowed=False if risk_restricted else None,
        org_id=org_id,
    )
    compound_name, compound_smiles = _extract_compound_context(report_data, analysis)
    target_jurisdictions = _build_target_jurisdictions(report_data)
    capability_metadata: ChatPolicy = build_chat_policy(report_data)
    report_summary = _report_summary_from_report_data(
        report_data,
        analysis,
        risk_restricted=risk_restricted,
    )
    suggested_evidence_queries = _build_suggested_evidence_queries(
        report_data,
        compound_name=compound_name,
        routing_profile=routing_profile,
        target_jurisdictions=target_jurisdictions,
    )
    monitor_seed_defaults = _build_monitor_seed_defaults(
        analysis=analysis,
        report_data=report_data,
        trust_mode=trust_mode,
        compound_name=compound_name,
        compound_smiles=compound_smiles,
        risk_restricted=risk_restricted,
    )

    return ReportWorkspaceSummaryResponse(
        analysis_id=analysis.id,
        report_id=_normalize_text(report_data.get("report_id")),
        trust_mode=trust_mode,
        jurisdiction_bundle=_normalize_text(report_data.get("jurisdiction_bundle") or "custom")
        or "custom",
        target_jurisdictions=target_jurisdictions,
        report_summary=report_summary,
        capability_metadata=capability_metadata,
        suggested_evidence_queries=suggested_evidence_queries,
        monitor_seed_defaults=monitor_seed_defaults,
        routing_profile=routing_profile,
        opinion_readiness=opinion_readiness,
        data_coverage=data_coverage,
        source_convergence=source_convergence,
        jurisdiction_matrix=list(report_data.get("jurisdiction_matrix") or []),
        jurisdiction_certification=list(report_data.get("jurisdiction_certification") or []),
        jurisdiction_source_coverage=list(report_data.get("jurisdiction_source_coverage") or []),
        uncertainty_register=list(report_data.get("uncertainty_register") or []),
        evidence_scope=evidence_scope,
    )
