"""Report-internal evidence searchers.

Each function searches a specific section of an already-loaded report dict
and returns a list of :class:`EvidenceSearchResultResponse` items. No outbound
network or DB calls are made here.

This module is not intended to be imported directly by callers; use the
:mod:`api.services.report_evidence_format` facade instead.
"""

from __future__ import annotations

from typing import Any

from api.schemas.report_evidence_search import (
    EvidenceSearchFollowUpTargetResponse,
    EvidenceSearchResultResponse,
)
from api.services.report_evidence_filter import (
    collect_blocking_patent_ids,
    excerpt,
    matches,
    query_has_blocking_intent,
    text,
)


def patent_search_context(report: dict[str, Any], patent_id: str) -> list[str]:
    """Attach decision-bearing patent context to otherwise generic artifacts."""

    context: list[str] = []
    for analysis in report.get("patent_analyses", []) or []:
        if not isinstance(analysis, dict) or text(analysis.get("patent_id")) != patent_id:
            continue
        context.extend(
            value
            for value in (
                text(analysis.get("title")),
                text(analysis.get("assignee")),
                text(analysis.get("risk_level")),
                text(analysis.get("risk_summary")),
            )
            if value
        )
        break
    if patent_id and patent_id in collect_blocking_patent_ids(report):
        context.append("blocking patent")
    return context


def build_follow_up(
    *,
    patent_id: str = "",
    target_id: str = "",
    artifact_label: str = "",
) -> EvidenceSearchFollowUpTargetResponse | None:
    resolved_patent_id = text(patent_id)
    resolved_target_id = text(target_id)
    if resolved_patent_id:
        return EvidenceSearchFollowUpTargetResponse(
            target_type="patent",
            target_id=resolved_patent_id,
            suggested_note=(
                f"Review follow-up requested for {resolved_patent_id}"
                + (f" via {artifact_label}" if artifact_label else "")
            ),
        )
    if resolved_target_id:
        return EvidenceSearchFollowUpTargetResponse(
            target_type="analysis",
            target_id=resolved_target_id,
            suggested_note=(
                "Review follow-up requested for governed evidence result"
                + (f" {artifact_label}" if artifact_label else "")
            ),
        )
    return None


def build_provenance(items: list[tuple[str, object]]) -> list:
    from api.schemas.report_evidence_search import EvidenceSearchProvenanceItemResponse

    provenance = []
    for label, raw_value in items:
        value = raw_value
        if isinstance(raw_value, list):
            normalized = [item for item in (text(item) for item in raw_value) if item]
            if not normalized:
                continue
            value = ", ".join(normalized)
        text_value = text(value)
        if not text_value:
            continue
        provenance.append(EvidenceSearchProvenanceItemResponse(label=label, value=text_value))
    return provenance[:6]


def search_evidence_artifacts(
    report: dict[str, Any], query: str
) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []
    for artifact in report.get("evidence_artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        patent_id = text(artifact.get("patent_id"))
        matched, relevance, joined = matches(
            query,
            artifact.get("artifact_id"),
            artifact.get("artifact_type"),
            artifact.get("source_name"),
            artifact.get("summary"),
            artifact.get("patent_id"),
            artifact.get("family_id"),
            artifact.get("record_basis"),
            artifact.get("linked_node_ids"),
            patent_search_context(report, patent_id),
            require_all_discriminative_tokens=query_has_blocking_intent(query),
        )
        if not matched:
            continue
        artifact_id = text(artifact.get("artifact_id"))
        artifact_type = text(artifact.get("artifact_type"))
        summary = text(artifact.get("summary")) or joined
        results.append(
            EvidenceSearchResultResponse(
                result_id=artifact_id or f"artifact:{artifact_type}:{patent_id}",
                title=patent_id or artifact_type.replace("_", " ").title() or "Evidence artifact",
                summary=excerpt(summary, query),
                source_name=text(artifact.get("source_name")),
                authority_tier=text(artifact.get("authority_tier")) or "supporting",
                freshness="Captured during the current pipeline run.",
                artifact_type=artifact_type or "evidence_artifact",
                section="evidence_artifact",
                patent_id=patent_id,
                relevance=relevance,
                provenance=build_provenance(
                    [
                        ("Artifact ID", artifact_id),
                        ("Jurisdiction", artifact.get("jurisdiction")),
                        ("Family", artifact.get("family_id")),
                        ("Record basis", artifact.get("record_basis")),
                        ("Linked nodes", artifact.get("linked_node_ids")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    target_id=artifact_id,
                    artifact_label=artifact_type,
                ),
            )
        )
    return results


def search_adapter_results(
    report: dict[str, Any], query: str
) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []
    for adapter in report.get("evidence_adapter_results", []) or []:
        if not isinstance(adapter, dict):
            continue
        matched, relevance, joined = matches(
            query,
            adapter.get("adapter_name"),
            adapter.get("adapter_kind"),
            adapter.get("warnings"),
            adapter.get("freshness_note"),
            adapter.get("target_patent_ids"),
            adapter.get("covered_patent_ids"),
            adapter.get("missing_patent_ids"),
            adapter.get("expected_components"),
            adapter.get("missing_components"),
        )
        if not matched:
            continue

        target_patent_ids = adapter.get("target_patent_ids") or []
        patent_id = text(target_patent_ids[0] if target_patent_ids else "")
        warnings = adapter.get("warnings") or []
        summary = (
            text(warnings[0] if warnings else "") or text(adapter.get("freshness_note")) or joined
        )
        adapter_name = text(adapter.get("adapter_name")) or "adapter"
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"adapter:{adapter_name}",
                title=f"{adapter_name} adapter",
                summary=excerpt(summary, query),
                source_name=adapter_name,
                authority_tier=text(adapter.get("authority_tier")) or "supporting",
                freshness=text(adapter.get("freshness_note")) or "No freshness note recorded.",
                artifact_type=text(adapter.get("adapter_kind")) or "adapter",
                section="evidence_adapter",
                patent_id=patent_id,
                relevance=min(relevance + 0.03, 0.99),
                provenance=build_provenance(
                    [
                        ("Collection state", adapter.get("collection_state")),
                        ("Status", adapter.get("status")),
                        ("Covered patents", adapter.get("covered_patent_ids")),
                        ("Missing patents", adapter.get("missing_patent_ids")),
                        ("Expected components", adapter.get("expected_components")),
                        ("Missing components", adapter.get("missing_components")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    target_id=adapter_name,
                    artifact_label="adapter result",
                ),
            )
        )
    return results


def search_patent_records(report: dict[str, Any], query: str) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []
    evidence_index = report.get("matter_evidence_index") or {}
    for record in evidence_index.get("patent_records", []) or []:
        if not isinstance(record, dict):
            continue
        patent_id = text(record.get("patent_id"))
        matched, relevance, joined = matches(
            query,
            record.get("patent_id"),
            record.get("title"),
            record.get("legal_status"),
            record.get("authoritative_source_names"),
            record.get("supporting_source_names"),
            record.get("gate_failures"),
            record.get("prosecution_signals"),
            record.get("future_risk_signals"),
            patent_search_context(report, patent_id),
            require_all_discriminative_tokens=query_has_blocking_intent(query),
        )
        if not matched:
            continue
        title = text(record.get("title")) or patent_id or "Patent evidence record"
        summary = (
            " ".join(
                item
                for item in [
                    text(record.get("legal_status")),
                    text(record.get("risk_level")),
                    ", ".join(
                        [text(item) for item in record.get("gate_failures", []) if text(item)]
                    ),
                ]
                if item
            )
            or joined
        )
        source_names = record.get("authoritative_source_names") or record.get("source_names") or []
        authority_tier = (
            "authoritative" if record.get("authoritative_source_names") else "supporting"
        )
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"patent_record:{patent_id}",
                title=title,
                summary=excerpt(summary, query),
                source_name=", ".join([text(item) for item in source_names if text(item)]),
                authority_tier=authority_tier,
                freshness="Patent evidence inventory derived from the final matter record.",
                artifact_type="patent_record",
                section="matter_evidence_index",
                patent_id=patent_id,
                relevance=min(relevance + 0.05, 0.99),
                provenance=build_provenance(
                    [
                        ("Legal status", record.get("legal_status")),
                        ("Family", record.get("family_id")),
                        ("Authoritative sources", record.get("authoritative_source_names")),
                        ("Supporting sources", record.get("supporting_source_names")),
                        ("Gate failures", record.get("gate_failures")),
                        ("Prosecution signals", record.get("prosecution_signals")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    artifact_label="patent evidence record",
                ),
            )
        )
    return results


def search_family_records(report: dict[str, Any], query: str) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []
    evidence_index = report.get("matter_evidence_index") or {}
    for record in evidence_index.get("family_records", []) or []:
        if not isinstance(record, dict):
            continue
        matched, relevance, joined = matches(
            query,
            record.get("family_id"),
            record.get("material_patent_ids"),
            record.get("jurisdictions"),
            record.get("broadest_patent_id"),
            record.get("blocking_patent_ids"),
            record.get("authoritative_record_categories"),
            record.get("gate_failures"),
        )
        if not matched:
            continue
        family_id = text(record.get("family_id"))
        broadest_patent_id = text(record.get("broadest_patent_id"))
        title = family_id or broadest_patent_id or "Family evidence record"
        summary = (
            " ".join(
                item
                for item in [
                    f"Family {family_id}" if family_id else "",
                    f"Broadest patent {broadest_patent_id}" if broadest_patent_id else "",
                    ", ".join(
                        [text(item) for item in record.get("gate_failures", []) if text(item)]
                    ),
                ]
                if item
            )
            or joined
        )
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"family_record:{family_id or broadest_patent_id}",
                title=title,
                summary=excerpt(summary, query),
                source_name="matter_evidence_index",
                authority_tier="authoritative",
                freshness="Family evidence inventory derived from the final matter record.",
                artifact_type="family_record",
                section="matter_evidence_index",
                patent_id=broadest_patent_id,
                relevance=min(relevance + 0.04, 0.99),
                provenance=build_provenance(
                    [
                        ("Family", family_id),
                        ("Jurisdictions", record.get("jurisdictions")),
                        ("Material patents", record.get("material_patent_ids")),
                        ("Blocking patents", record.get("blocking_patent_ids")),
                        ("Gate failures", record.get("gate_failures")),
                        (
                            "Authoritative categories",
                            record.get("authoritative_record_categories"),
                        ),
                    ]
                ),
                follow_up_target=build_follow_up(
                    patent_id=broadest_patent_id,
                    target_id=family_id,
                    artifact_label="family evidence record",
                ),
            )
        )
    return results


def search_prosecution_dossiers(
    report: dict[str, Any], query: str
) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []
    for dossier in report.get("prosecution_dossiers", []) or []:
        if not isinstance(dossier, dict):
            continue
        matched, relevance, joined = matches(
            query,
            dossier.get("patent_id"),
            dossier.get("application_number"),
            dossier.get("source_name"),
            dossier.get("sections_available"),
            dossier.get("office_actions_summary"),
            dossier.get("continuity_summary"),
            dossier.get("amendments_summary"),
            dossier.get("rejection_bases"),
            dossier.get("estoppel_risk_flags"),
            dossier.get("record_basis"),
        )
        if not matched:
            continue
        patent_id = text(dossier.get("patent_id"))
        summary = (
            text(dossier.get("summary"))
            or text(dossier.get("office_actions_summary"))
            or text(dossier.get("continuity_summary"))
            or joined
        )
        source_name = text(dossier.get("source_name")) or "prosecution_dossier"
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"prosecution:{patent_id or source_name}",
                title=f"{patent_id or 'Matter'} prosecution dossier",
                summary=excerpt(summary, query),
                source_name=source_name,
                authority_tier="authoritative",
                freshness=f"Collected from {source_name} during the pipeline run.",
                artifact_type="prosecution_dossier",
                section="prosecution_dossier",
                patent_id=patent_id,
                relevance=min(relevance + 0.08, 0.99),
                provenance=build_provenance(
                    [
                        ("Application", dossier.get("application_number")),
                        ("Jurisdiction", dossier.get("jurisdiction")),
                        ("Sections", dossier.get("sections_available")),
                        ("Rejection bases", dossier.get("rejection_bases")),
                        ("Estoppel flags", dossier.get("estoppel_risk_flags")),
                        ("Record basis", dossier.get("record_basis")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    artifact_label="prosecution dossier",
                ),
            )
        )
    return results


def search_coverage_and_uncertainty(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    results: list[EvidenceSearchResultResponse] = []

    for gap in report.get("coverage_gaps", []) or []:
        if not isinstance(gap, dict):
            continue
        matched, relevance, joined = matches(
            query,
            gap.get("gap_type"),
            gap.get("description"),
            gap.get("suggested_action"),
        )
        if not matched:
            continue
        gap_type = text(gap.get("gap_type")) or "coverage_gap"
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"coverage_gap:{gap_type}",
                title=gap_type.replace("_", " ").title(),
                summary=excerpt(text(gap.get("description")) or joined, query),
                source_name="coverage_gap",
                authority_tier="discovery",
                freshness="Derived from the final evidence coverage assessment.",
                artifact_type="coverage_gap",
                section="coverage_gap",
                relevance=max(relevance - 0.04, 0.2),
                provenance=build_provenance(
                    [
                        ("Gap", gap_type),
                        ("Suggested action", gap.get("suggested_action")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    target_id=gap_type,
                    artifact_label="coverage gap",
                ),
            )
        )

    source_convergence = report.get("source_convergence") or {}
    if isinstance(source_convergence, dict):
        matched, relevance, joined = matches(
            query,
            source_convergence.get("score"),
            source_convergence.get("source_count"),
            source_convergence.get("agreement_summary"),
            source_convergence.get("notes"),
        )
        if matched:
            results.append(
                EvidenceSearchResultResponse(
                    result_id="source_convergence",
                    title="Source convergence",
                    summary=excerpt(
                        text(source_convergence.get("agreement_summary")) or joined,
                        query,
                    ),
                    source_name="source_convergence",
                    authority_tier="supporting",
                    freshness="Derived from the final cross-source agreement snapshot.",
                    artifact_type="source_convergence",
                    section="source_convergence",
                    relevance=max(relevance - 0.05, 0.2),
                    provenance=build_provenance(
                        [
                            ("Score", source_convergence.get("score")),
                            ("Source count", source_convergence.get("source_count")),
                            ("Notes", source_convergence.get("notes")),
                        ]
                    ),
                    follow_up_target=build_follow_up(
                        target_id="source_convergence",
                        artifact_label="source convergence",
                    ),
                )
            )

    for index, uncertainty in enumerate(report.get("uncertainty_register", []) or []):
        if not isinstance(uncertainty, dict):
            continue
        matched, relevance, joined = matches(
            query,
            uncertainty.get("title"),
            uncertainty.get("summary"),
            uncertainty.get("category"),
            uncertainty.get("severity"),
            uncertainty.get("recommended_action"),
        )
        if not matched:
            continue
        category = text(uncertainty.get("category")) or "uncertainty"
        title = text(uncertainty.get("title")) or category.replace("_", " ").title()
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"uncertainty:{category}:{index}",
                title=title,
                summary=excerpt(text(uncertainty.get("summary")) or joined, query),
                source_name="uncertainty_register",
                authority_tier="discovery",
                freshness="Derived from the report uncertainty register.",
                artifact_type="uncertainty",
                section="uncertainty_register",
                relevance=max(relevance - 0.06, 0.18),
                provenance=build_provenance(
                    [
                        ("Category", category),
                        ("Severity", uncertainty.get("severity")),
                        ("Recommended action", uncertainty.get("recommended_action")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    target_id=category,
                    artifact_label="uncertainty register item",
                ),
            )
        )

    return results


def search_search_loop(report: dict[str, Any], query: str) -> list[EvidenceSearchResultResponse]:
    search_loop = report.get("search_loop_result") or {}
    results: list[EvidenceSearchResultResponse] = []

    iteration_logs = search_loop.get("iteration_logs") or []
    for iteration in iteration_logs:
        if not isinstance(iteration, dict):
            continue
        assessment_raw = iteration.get("assessment")
        assessment: dict[str, Any] = assessment_raw if isinstance(assessment_raw, dict) else {}
        suggested_queries_raw = assessment.get("suggested_queries")
        suggested_queries = suggested_queries_raw if isinstance(suggested_queries_raw, dict) else {}
        directives = assessment.get("evidence_collection_directives") or []

        matched, relevance, joined = matches(
            query,
            iteration.get("queries_used"),
            assessment.get("iteration_summary"),
            assessment.get("gaps_identified"),
            suggested_queries,
            directives,
        )
        if matched:
            summary = text(assessment.get("iteration_summary")) or joined
            iteration_number = iteration.get("iteration_number") or "?"
            results.append(
                EvidenceSearchResultResponse(
                    result_id=f"search_loop:iteration:{iteration_number}",
                    title=f"Search iteration {iteration_number}",
                    summary=excerpt(summary, query),
                    source_name="search_loop",
                    authority_tier="discovery",
                    freshness="Derived from the completed search-loop assessment.",
                    artifact_type="search_iteration",
                    section="search_loop",
                    relevance=relevance,
                    provenance=build_provenance(
                        [
                            ("Queries used", iteration.get("queries_used")),
                            ("Coverage adequate", assessment.get("coverage_adequate")),
                            ("Confidence", assessment.get("confidence")),
                            ("Suggested queries", suggested_queries),
                            ("Directives", directives),
                        ]
                    ),
                    follow_up_target=build_follow_up(
                        target_id=f"search_loop:{iteration_number}",
                        artifact_label="search iteration",
                    ),
                )
            )

    for log_entry in report.get("search_strategy_log", []) or []:
        if not isinstance(log_entry, dict):
            continue
        matched, relevance, joined = matches(
            query,
            log_entry.get("stage"),
            log_entry.get("execution_profile"),
            log_entry.get("trust_mode"),
            log_entry.get("jurisdictions"),
            log_entry.get("sources"),
        )
        if not matched:
            continue
        stage = text(log_entry.get("stage")) or "search strategy"
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"search_strategy:{stage}",
                title=f"{stage.replace('_', ' ').title()} strategy",
                summary=excerpt(joined, query),
                source_name="search_strategy_log",
                authority_tier="discovery",
                freshness="Derived from the report search strategy log.",
                artifact_type="search_strategy",
                section="search_strategy_log",
                relevance=max(relevance - 0.05, 0.2),
                provenance=build_provenance(
                    [
                        ("Jurisdictions", log_entry.get("jurisdictions")),
                        ("Sources", log_entry.get("sources")),
                        (
                            "Execution profile",
                            log_entry.get("execution_profile"),
                        ),
                        ("Trust mode", log_entry.get("trust_mode")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    target_id=stage,
                    artifact_label="search strategy",
                ),
            )
        )

    for negative_entry in report.get("negative_search_log", []) or []:
        if not isinstance(negative_entry, dict):
            continue
        matched, relevance, joined = matches(query, negative_entry)
        if not matched:
            continue
        label = (
            text(negative_entry.get("source"))
            or text(negative_entry.get("stage"))
            or "negative search"
        )
        results.append(
            EvidenceSearchResultResponse(
                result_id=f"negative_search:{label}",
                title=f"{label.replace('_', ' ').title()} gap",
                summary=excerpt(joined, query),
                source_name=label,
                authority_tier="discovery",
                freshness="Logged as an incomplete or failed evidence path.",
                artifact_type="negative_search",
                section="negative_search_log",
                relevance=max(relevance - 0.08, 0.18),
                provenance=build_provenance(
                    [
                        ("Gap", negative_entry.get("gap_type")),
                        ("Suggested action", negative_entry.get("suggested_action")),
                        ("Description", negative_entry.get("description")),
                    ]
                ),
                follow_up_target=build_follow_up(
                    target_id=label,
                    artifact_label="negative search gap",
                ),
            )
        )

    return results
