"""Result builders and provider-capability helpers for report evidence search.

Operates on already-loaded report data; no outbound network or DB calls.

This module is not intended to be imported directly by callers; use the
:mod:`api.services.report_evidence_format` facade instead.
"""

from __future__ import annotations

import uuid
from typing import Any

from api.schemas.report_evidence_search import (
    EvidenceSearchFollowUpTargetResponse,
    EvidenceSearchProviderCapabilityResponse,
    EvidenceSearchResponse,
    EvidenceSearchResultResponse,
    EvidenceSearchScopeResponse,
)
from api.services import report_external_evidence
from api.services.report_evidence_filter import (
    PROVIDER_EXECUTION_PRIORITY,
    PROVIDER_STATUS_PRIORITY,
    classify_provider,
    collect_blocking_patent_ids,
    collect_jurisdictions,
    collect_modalities,
    collect_sources,
    excerpt,
    external_retrieval_allowed,
    provider_id_from_source,
    query_has_blocking_intent,
    text,
)
from api.services.report_evidence_searchers import (
    build_follow_up,
    build_provenance,
    search_adapter_results,
    search_coverage_and_uncertainty,
    search_evidence_artifacts,
    search_family_records,
    search_patent_records,
    search_prosecution_dossiers,
    search_search_loop,
)


def merge_text_notes(*values: str) -> str:
    notes: list[str] = []
    for value in values:
        note = value.strip()
        if note and note not in notes:
            notes.append(note)
    return " ".join(notes)


def merge_coverage_values(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            item = text(value)
            if item and item not in merged:
                merged.append(item)
    return merged


def merge_provider_capabilities(
    capabilities: list[EvidenceSearchProviderCapabilityResponse],
) -> list[EvidenceSearchProviderCapabilityResponse]:
    merged: dict[tuple[str, str], EvidenceSearchProviderCapabilityResponse] = {}
    for capability in capabilities:
        key = (
            text(capability.provider_id or capability.provider_name).lower(),
            capability.provider_class,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = capability
            continue

        materialized_in_report = (
            existing.materialized_in_report or capability.materialized_in_report
        )
        execution_mode = max(
            (existing.execution_mode, capability.execution_mode),
            key=lambda item: PROVIDER_EXECUTION_PRIORITY.get(item, 0),
        )
        if materialized_in_report and "report_materialized" in {
            existing.execution_mode,
            capability.execution_mode,
        }:
            execution_mode = "report_materialized"

        merged[key] = existing.model_copy(
            update={
                "provider_id": capability.provider_id or existing.provider_id,
                "provider_name": existing.provider_name or capability.provider_name,
                "provider_status": max(
                    (existing.provider_status, capability.provider_status),
                    key=lambda item: PROVIDER_STATUS_PRIORITY.get(item, 0),
                ),
                "live_retrieval_supported": existing.live_retrieval_supported
                or capability.live_retrieval_supported,
                "configured": existing.configured or capability.configured,
                "configured_for_org": existing.configured_for_org or capability.configured_for_org,
                "materialized_in_report": materialized_in_report,
                "execution_mode": execution_mode,
                "modality_coverage": merge_coverage_values(
                    existing.modality_coverage, capability.modality_coverage
                ),
                "jurisdiction_coverage": merge_coverage_values(
                    existing.jurisdiction_coverage, capability.jurisdiction_coverage
                ),
                "governance_note": merge_text_notes(
                    existing.governance_note, capability.governance_note
                ),
                "retrieved_at": existing.retrieved_at or capability.retrieved_at,
                "source_as_of": existing.source_as_of or capability.source_as_of,
                "dataset_version": existing.dataset_version or capability.dataset_version,
            }
        )
    return list(merged.values())


def build_provider_capabilities(
    report: dict[str, Any],
    *,
    sources: list[str],
    external_retrieval_allowed_flag: bool = False,
    org_id: str | uuid.UUID | None = None,
    build_external_query_context_fn,
) -> list[EvidenceSearchProviderCapabilityResponse]:
    modalities = collect_modalities(report)
    jurisdictions = collect_jurisdictions(report)
    capabilities = [
        EvidenceSearchProviderCapabilityResponse(
            provider_id="report_derived",
            provider_name="Report-derived evidence layer",
            provider_class="report_derived",
            live_retrieval_supported=False,
            configured=True,
            configured_for_org=True,
            materialized_in_report=True,
            execution_mode="report_materialized",
            modality_coverage=modalities,
            jurisdiction_coverage=jurisdictions,
            governance_note=(
                "Search runs against evidence already captured in this report. "
                "No fresh external retrieval is executed from this workspace."
            ),
            source_as_of="Completed report snapshot",
            dataset_version="report_record",
        )
    ]

    for source in sources:
        provider_class = classify_provider(source)
        if not provider_class:
            continue
        capabilities.append(
            EvidenceSearchProviderCapabilityResponse(
                provider_id=provider_id_from_source(source),
                provider_name=source,
                provider_class=provider_class,
                provider_status="active",
                live_retrieval_supported=False,
                configured=False,
                configured_for_org=False,
                materialized_in_report=True,
                execution_mode="report_materialized",
                modality_coverage=modalities,
                jurisdiction_coverage=jurisdictions,
                governance_note=(
                    f"{source} evidence is already materialized in the report. "
                    f"This governed search does not execute fresh {source} retrieval."
                ),
                source_as_of="Completed report snapshot",
                dataset_version="report_evidence_source",
            )
        )

    if external_retrieval_allowed_flag:
        context = build_external_query_context_fn(report, query="", org_id=org_id)
        capabilities.extend(report_external_evidence.build_external_provider_capabilities(context))
    return merge_provider_capabilities(capabilities)


def has_active_hybrid_layer(
    capabilities: list[EvidenceSearchProviderCapabilityResponse],
) -> bool:
    return any(
        capability.provider_class != "report_derived"
        and capability.provider_status == "active"
        and (
            capability.configured
            or capability.materialized_in_report
            or capability.live_retrieval_supported
        )
        for capability in capabilities
    )


def has_live_external_provider(
    capabilities: list[EvidenceSearchProviderCapabilityResponse],
) -> bool:
    return any(capability.live_retrieval_supported for capability in capabilities)


def build_external_result(
    *,
    result_id: str,
    title: str,
    summary: str,
    source_name: str,
    artifact_type: str,
    section: str,
    authority_tier: str = "authoritative",
    freshness: str = "",
    patent_id: str = "",
    relevance: float = 0.7,
    provenance: list[tuple[str, object]] | None = None,
    follow_up_target: EvidenceSearchFollowUpTargetResponse | None = None,
) -> EvidenceSearchResultResponse:
    return EvidenceSearchResultResponse(
        result_id=result_id,
        title=title,
        summary=summary,
        source_name=source_name,
        authority_tier=authority_tier,
        freshness=freshness,
        artifact_type=artifact_type,
        section=section,
        patent_id=patent_id,
        relevance=relevance,
        provenance=build_provenance(provenance or []),
        follow_up_target=follow_up_target,
    )


def provider_notice_result(
    provider_name: str,
    *,
    message: str,
    query: str,
    live_retrieval: bool,
) -> EvidenceSearchResultResponse:
    return build_external_result(
        result_id=f"provider_notice:{provider_name}",
        title=f"{provider_name.replace('_', ' ').title()} provider notice",
        summary=excerpt(message, query, limit=280),
        source_name=provider_name,
        authority_tier="governance",
        freshness="Generated during this external evidence expansion.",
        artifact_type="provider_notice",
        section="external_provider_notice",
        relevance=0.18,
        provenance=[
            ("Provider", provider_name),
            ("Live retrieval attempted", "yes" if live_retrieval else "no"),
        ],
        follow_up_target=build_follow_up(
            target_id=provider_name,
            artifact_label="provider notice",
        ),
    )


def build_scope(
    report: dict[str, Any],
    *,
    external_retrieval_allowed_flag: bool | None = None,
    org_id: str | uuid.UUID | None = None,
    build_external_query_context_fn,
) -> EvidenceSearchScopeResponse:
    sources = collect_sources(report)
    allow_external = (
        external_retrieval_allowed(report)
        if external_retrieval_allowed_flag is None
        else external_retrieval_allowed_flag
    )
    provider_capabilities = build_provider_capabilities(
        report,
        sources=sources,
        external_retrieval_allowed_flag=allow_external,
        org_id=org_id,
        build_external_query_context_fn=build_external_query_context_fn,
    )
    hybrid_evidence_ready = has_active_hybrid_layer(provider_capabilities)
    external_live_retrieval = allow_external and has_live_external_provider(provider_capabilities)
    governed_note = (
        "Searches evidence already collected into the report: artifacts, adapters, patent records,"
        " prosecution dossiers, search-loop history, and coverage gaps."
    )
    if external_live_retrieval:
        governed_note += " Governed external expansion is also available in this workspace."
    elif allow_external:
        governed_note += (
            " Governed external expansion is policy-scoped for this workspace, "
            "but no live providers are active for the current routed evidence posture."
        )

    return EvidenceSearchScopeResponse(
        mode="report_evidence",
        external_live_retrieval=external_live_retrieval,
        sources_considered=sources,
        governed_note=governed_note,
        provider_capabilities=provider_capabilities,
        providers=provider_capabilities,
        hybrid_evidence_ready=hybrid_evidence_ready,
    )


def search_report_evidence_impl(
    report: dict[str, Any],
    query_text: str,
    *,
    external_retrieval_allowed_flag: bool | None = None,
    org_id: str | uuid.UUID | None = None,
    build_external_query_context_fn,
) -> dict[str, Any]:
    query = query_text.strip()
    results: list[EvidenceSearchResultResponse] = []
    results.extend(search_evidence_artifacts(report, query))
    results.extend(search_adapter_results(report, query))
    results.extend(search_patent_records(report, query))
    results.extend(search_family_records(report, query))
    results.extend(search_prosecution_dossiers(report, query))
    results.extend(search_coverage_and_uncertainty(report, query))
    results.extend(search_search_loop(report, query))

    if query_has_blocking_intent(query):
        blocking_patent_ids = collect_blocking_patent_ids(report)
        results = [
            result
            for result in results
            if result.patent_id and result.patent_id in blocking_patent_ids
        ]

    deduped: dict[str, EvidenceSearchResultResponse] = {}
    for result in sorted(results, key=lambda item: item.relevance, reverse=True):
        if result.result_id not in deduped:
            deduped[result.result_id] = result

    final_results = list(deduped.values())[:25]
    response = EvidenceSearchResponse(
        query=query,
        interpreted_query=f'Governed evidence search: "{query}"',
        scope=build_scope(
            report,
            external_retrieval_allowed_flag=external_retrieval_allowed_flag,
            org_id=org_id,
            build_external_query_context_fn=build_external_query_context_fn,
        ),
        results=final_results,
        total=len(deduped),
    )
    return response.model_dump(mode="json")
