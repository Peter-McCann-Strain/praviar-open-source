"""Async outbound provider calls for governed external evidence expansion."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from api.schemas.report_evidence_search import (
    EvidenceSearchProviderExecutionResponse,
    EvidenceSearchProviderNoticeResponse,
    EvidenceSearchResponse,
    EvidenceSearchResultResponse,
    EvidenceSearchScopeResponse,
)
from api.services import report_external_evidence
from api.services.licensed_family_overlay import search_licensed_family_overlay
from api.services.report_evidence_filter import (
    collect_jurisdictions,
    collect_modalities,
    excerpt,
    external_query_jurisdictions,
    normalized_trust_mode,
    query_patent_identifier,
    report_compound_context,
    text,
)
from api.services.report_evidence_format import (
    build_external_result,
    build_follow_up,
    has_active_hybrid_layer,
    merge_provider_capabilities,
)


def build_external_query_context(
    report: dict[str, Any],
    *,
    query: str,
    org_id: str | uuid.UUID | None = None,
) -> report_external_evidence.ExternalEvidenceQueryContext:
    compound_name, compound_smiles, compound_cid = report_compound_context(report)
    return report_external_evidence.build_external_query_context(
        query=query,
        trust_mode=normalized_trust_mode(report),
        org_id=text(org_id) or None,
        modalities=collect_modalities(report),
        jurisdictions=collect_jurisdictions(report),
        patent_identifier=query_patent_identifier(query),
        compound_name=compound_name,
        compound_smiles=compound_smiles,
        compound_cid=compound_cid,
    )


async def _search_external_pubchem(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.pubchem import PubChemClient

    report_compound_name, report_smiles, report_cid = report_compound_context(report)

    async with PubChemClient() as client:
        resolved = await client.resolve_by_name(query)
        if not resolved and report_compound_name and report_compound_name.lower() == query.lower():
            resolved = {
                "CID": report_cid or "",
                "CanonicalSMILES": report_smiles,
                "IUPACName": report_compound_name,
                "MolecularFormula": "",
                "MolecularWeight": "",
            }

        cid_raw = resolved.get("CID")
        cid: int | None
        if isinstance(cid_raw, int):
            cid = cid_raw
        elif cid_raw is not None and str(cid_raw).isdigit():
            cid = int(str(cid_raw))
        else:
            cid = None
        if not cid:
            return []

        synonyms = await client.get_synonyms(cid)
        patent_links = await client.get_patent_links(cid)
        display_name = text(resolved.get("IUPACName")) or report_compound_name or query

        results = [
            build_external_result(
                result_id=f"pubchem:compound:{cid}",
                title=f"{display_name} compound record",
                summary=(
                    f"PubChem resolved {display_name} to CID {cid}. "
                    f"Found {len(patent_links)} patent cross-reference"
                    f"{'' if len(patent_links) == 1 else 's'} and {len(synonyms)} synonym"
                    f"{'' if len(synonyms) == 1 else 's'}."
                ),
                source_name="pubchem",
                authority_tier="authoritative",
                freshness="Retrieved live from PubChem.",
                artifact_type="compound_record",
                section="external_pubchem",
                relevance=0.96,
                provenance=[
                    ("CID", cid),
                    ("Canonical SMILES", resolved.get("CanonicalSMILES") or report_smiles),
                    ("Molecular formula", resolved.get("MolecularFormula")),
                    ("Molecular weight", resolved.get("MolecularWeight")),
                    ("Synonyms", synonyms[:5]),
                ],
                follow_up_target=build_follow_up(
                    target_id=str(cid),
                    artifact_label="PubChem compound record",
                ),
            )
        ]

        for patent_id in patent_links[:5]:
            normalized_patent_id = text(patent_id)
            if not normalized_patent_id:
                continue
            results.append(
                build_external_result(
                    result_id=f"pubchem:patent:{normalized_patent_id}",
                    title=f"PubChem patent cross-reference {normalized_patent_id}",
                    summary=(
                        f"PubChem links {display_name} to patent {normalized_patent_id}. "
                        "Use this as a governed cross-reference, not a dispositive "
                        "clearance conclusion."
                    ),
                    source_name="pubchem",
                    authority_tier="supporting",
                    freshness="Retrieved live from PubChem patent links.",
                    artifact_type="patent_link",
                    section="external_pubchem",
                    patent_id=normalized_patent_id,
                    relevance=0.9,
                    provenance=[
                        ("CID", cid),
                        ("Compound", display_name),
                    ],
                    follow_up_target=build_follow_up(
                        patent_id=normalized_patent_id,
                        artifact_label="PubChem patent link",
                    ),
                )
            )

        return results


async def _search_external_patentsview(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.patentsview import PatentsViewClient

    async with PatentsViewClient() as client:
        patents = await client.search_by_compound_keywords(query, size=5)

    results: list[EvidenceSearchResultResponse] = []
    for patent in patents[:5]:
        patent_id = text(patent.get("patent_id"))
        title = text(patent.get("patent_title")) or patent_id or "PatentsView result"
        assignees = [
            text(item.get("assignee_organization"))
            for item in patent.get("assignees", []) or []
            if isinstance(item, dict) and text(item.get("assignee_organization"))
        ]
        results.append(
            build_external_result(
                result_id=f"patentsview:{patent_id or title}",
                title=title,
                summary=excerpt(
                    text(patent.get("patent_abstract"))
                    or "PatentsView returned a keyword-aligned US patent result.",
                    query,
                ),
                source_name="patentsview",
                authority_tier="authoritative",
                freshness="Retrieved live from PatentsView.",
                artifact_type="patent_search_result",
                section="external_patentsview",
                patent_id=patent_id,
                relevance=0.88,
                provenance=[
                    ("Patent date", patent.get("patent_date")),
                    ("Kind", patent.get("patent_kind")),
                    ("Assignees", assignees),
                    ("Claim count", patent.get("patent_num_claims")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    artifact_label="PatentsView result",
                ),
            )
        )
    return results


def _extract_uspto_search_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("patentFileWrapperDataBag", "results", "hits"):
        values = data.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
    return []


async def _search_external_uspto_odp(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.uspto_odp import USPTOODPClient

    async with USPTOODPClient() as client:
        data = await client.search_patents(query, limit=5)

    rows = _extract_uspto_search_rows(data)
    results: list[EvidenceSearchResultResponse] = []
    for row in rows[:5]:
        metadata = row.get("applicationMetaData")
        metadata = metadata if isinstance(metadata, dict) else {}
        patent_id = text(metadata.get("patentNumber") or row.get("patentNumber"))
        application_number = text(row.get("applicationNumberText"))
        title = (
            text(metadata.get("inventionTitle"))
            or text(row.get("inventionTitle"))
            or patent_id
            or application_number
            or "USPTO application search result"
        )
        results.append(
            build_external_result(
                result_id=f"uspto_odp:{application_number or patent_id or title}",
                title=title,
                summary=("USPTO ODP returned an application-side result aligned to this query."),
                source_name="uspto_odp",
                authority_tier="authoritative",
                freshness="Retrieved live from USPTO ODP.",
                artifact_type="application_search_result",
                section="external_uspto_odp",
                patent_id=patent_id,
                relevance=0.82,
                provenance=[
                    ("Application number", application_number),
                    ("Patent number", patent_id),
                    ("Application status", metadata.get("applicationStatusDescriptionText")),
                    ("Filing date", metadata.get("filingDate")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    target_id=application_number,
                    artifact_label="USPTO ODP result",
                ),
            )
        )
    return results


async def _search_external_epo_ops(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    tokens = [token for token in query.split() if token][:5]
    async with EPOOPSClient() as client:
        rows = await client.search_published_data(
            claim_keywords=tokens or [query],
            max_results=5,
        )

    results: list[EvidenceSearchResultResponse] = []
    for row in rows[:5]:
        publication_number = text(
            row.get("publication_number") or row.get("doc_number") or row.get("patent_id")
        )
        title = text(row.get("title")) or publication_number or "EPO OPS result"
        applicants = row.get("applicant") or row.get("applicants") or []
        results.append(
            build_external_result(
                result_id=f"epo_ops:{publication_number or title}",
                title=title,
                summary=excerpt(
                    text(row.get("abstract"))
                    or "EPO OPS returned a publication aligned to the current monitoring query.",
                    query,
                ),
                source_name="epo_ops",
                authority_tier="authoritative",
                freshness="Retrieved live from EPO OPS.",
                artifact_type="publication_search_result",
                section="external_epo_ops",
                patent_id=publication_number,
                relevance=0.83,
                provenance=[
                    ("Publication", publication_number),
                    ("Applicants", applicants),
                    ("Jurisdiction", row.get("jurisdiction") or row.get("country")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=publication_number,
                    artifact_label="EPO OPS result",
                ),
            )
        )
    return results


async def _search_external_patentscope(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.patentscope import PatentScopeClient

    jurisdictions = external_query_jurisdictions(report)
    async with PatentScopeClient() as client:
        rows = await client.search_patents(
            keywords=[query],
            jurisdictions=jurisdictions or None,
            max_results=5,
        )

    results: list[EvidenceSearchResultResponse] = []
    for row in rows[:5]:
        publication_number = text(
            row.get("publication_number") or row.get("patent_id") or row.get("doc_number")
        )
        title = text(row.get("title")) or publication_number or "PatentScope result"
        assignees = row.get("assignees") or row.get("applicants") or []
        results.append(
            build_external_result(
                result_id=f"patentscope:{publication_number or title}",
                title=title,
                summary=excerpt(
                    text(row.get("abstract"))
                    or "PatentScope returned a publication aligned to this monitoring query.",
                    query,
                ),
                source_name="patentscope",
                authority_tier="supporting",
                freshness="Retrieved live from WIPO PatentScope.",
                artifact_type="publication_search_result",
                section="external_patentscope",
                patent_id=publication_number,
                relevance=0.8,
                provenance=[
                    ("Publication", publication_number),
                    ("Jurisdictions", jurisdictions),
                    ("Assignees", assignees),
                    ("Filing date", row.get("filing_date")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=publication_number,
                    artifact_label="PatentScope result",
                ),
            )
        )
    return results


async def _search_external_ptab(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.ptab import PTABClient

    patent_id = query_patent_identifier(query)
    if not patent_id:
        return []

    async with PTABClient() as client:
        proceedings = await client.get_proceedings(patent_id)

    results: list[EvidenceSearchResultResponse] = []
    for index, proceeding in enumerate(proceedings[:5], start=1):
        proceeding_number = text(
            proceeding.get("proceedingNumber")
            or proceeding.get("trialNumber")
            or proceeding.get("caseNumber")
        )
        results.append(
            build_external_result(
                result_id=f"ptab:{proceeding_number or patent_id}:{index}",
                title=proceeding_number or f"PTAB proceeding for {patent_id}",
                summary=("PTAB returned a proceeding connected to the queried US patent."),
                source_name="ptab",
                authority_tier="authoritative",
                freshness="Retrieved live from USPTO PTAB.",
                artifact_type="proceeding",
                section="external_ptab",
                patent_id=patent_id,
                relevance=0.84,
                provenance=[
                    ("Patent", patent_id),
                    ("Proceeding type", proceeding.get("proceedingType")),
                    ("Status", proceeding.get("status") or proceeding.get("proceedingStatus")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    target_id=proceeding_number,
                    artifact_label="PTAB proceeding",
                ),
            )
        )
    return results


async def _search_external_orange_book(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.orange_book import load_orange_book

    patent_id = query_patent_identifier(query)
    if not patent_id:
        return []

    index = await load_orange_book()
    listings = index.lookup(patent_id)
    results: list[EvidenceSearchResultResponse] = []
    for entry in listings[:5]:
        results.append(
            build_external_result(
                result_id=f"orange_book:{entry.patent_number}:{entry.nda_number}",
                title=entry.product_name or entry.active_ingredient or entry.patent_number,
                summary=(
                    f"FDA Orange Book lists patent {entry.patent_number} against "
                    f"{entry.product_name or entry.active_ingredient or 'an approved product'}."
                ),
                source_name="orange_book",
                authority_tier="authoritative",
                freshness="Retrieved from the bundled FDA Orange Book dataset.",
                artifact_type="regulatory_listing",
                section="external_orange_book",
                patent_id=entry.patent_number,
                relevance=0.86,
                provenance=[
                    ("NDA", entry.nda_number),
                    ("Active ingredient", entry.active_ingredient),
                    ("Patent expiry", entry.patent_expiry),
                    ("Patent use code", entry.patent_use_code),
                ],
                follow_up_target=build_follow_up(
                    patent_id=entry.patent_number,
                    artifact_label="Orange Book listing",
                ),
            )
        )
    return results


async def _search_external_purple_book(
    report: dict[str, Any],
    query: str,
) -> list[EvidenceSearchResultResponse]:
    from praviar_pipeline.clients.purple_book import load_purple_book

    index = await load_purple_book()
    record = index.lookup_biologic(query)
    if not record:
        return []

    title = text(record.get("product_name")) or text(record.get("proper_name")) or query
    return [
        build_external_result(
            result_id=f"purple_book:{text(record.get('bla_number')) or title}",
            title=title,
            summary=(
                f"FDA Purple Book matched {title} with BLA {record.get('bla_number', 'unknown')}."
            ),
            source_name="purple_book",
            authority_tier="authoritative",
            freshness="Retrieved from the bundled FDA Purple Book dataset.",
            artifact_type="biologic_listing",
            section="external_purple_book",
            relevance=0.84,
            provenance=[
                ("Proper name", record.get("proper_name")),
                ("BLA", record.get("bla_number")),
                ("Applicant", record.get("applicant")),
                ("Marketing status", record.get("marketing_status")),
                ("Biosimilar count", record.get("biosimilar_count")),
            ],
            follow_up_target=build_follow_up(
                target_id=text(record.get("bla_number")) or title,
                artifact_label="Purple Book listing",
            ),
        )
    ]


async def _search_external_licensed_family_overlay(
    report: dict[str, Any],
    query: str,
    *,
    context: report_external_evidence.ExternalEvidenceQueryContext,
    licensed_family_overlay_fn=search_licensed_family_overlay,
) -> list[EvidenceSearchResultResponse]:
    rows = await licensed_family_overlay_fn(
        {
            "query": query,
            "trust_mode": context.trust_mode,
            "org_id": context.org_id,
            "modalities": list(context.modalities),
            "jurisdictions": list(context.jurisdictions),
            "patent_identifier": context.patent_identifier,
            "compound_name": context.compound_name,
            "compound_smiles": context.compound_smiles,
            "compound_cid": context.compound_cid,
        }
    )

    results: list[EvidenceSearchResultResponse] = []
    for index, row in enumerate(rows[:5], start=1):
        patent_id = text(
            row.get("patent_id") or row.get("publication_number") or row.get("document_number")
        )
        family_id = text(row.get("family_id") or row.get("simple_family_id"))
        title = (
            text(row.get("title") or row.get("family_title"))
            or patent_id
            or family_id
            or f"Licensed family overlay result {index}"
        )
        summary = (
            text(row.get("summary"))
            or text(row.get("legal_status_summary"))
            or text(row.get("ownership_summary"))
            or "Licensed family/legal-status overlay returned a governed result."
        )
        assignees = row.get("assignees") or row.get("owners") or row.get("applicants") or []
        results.append(
            build_external_result(
                result_id=text(row.get("result_id") or row.get("id"))
                or f"licensed_family_overlay:{family_id or patent_id or index}",
                title=title,
                summary=excerpt(summary, query),
                source_name="licensed_family_overlay",
                authority_tier=text(row.get("authority_tier")) or "authoritative",
                freshness=text(row.get("freshness"))
                or "Retrieved live from the configured licensed family/legal-status overlay.",
                artifact_type=text(row.get("artifact_type")) or "licensed_family_result",
                section="external_licensed_family_overlay",
                patent_id=patent_id,
                relevance=float(row.get("relevance") or 0.89),
                provenance=[
                    ("Family", family_id),
                    ("Jurisdictions", row.get("jurisdictions")),
                    ("Legal status", row.get("legal_status")),
                    ("Assignees", assignees),
                    ("Ownership", row.get("ownership_summary")),
                    ("Confidence", row.get("confidence_note")),
                ],
                follow_up_target=build_follow_up(
                    patent_id=patent_id,
                    target_id=family_id,
                    artifact_label="licensed family overlay result",
                ),
            )
        )
    return results


def _provider_error_message(provider_name: str, exc: Exception) -> str:
    if provider_name.startswith("licensed_"):
        return (
            f"{provider_name} could not complete governed external retrieval. "
            "Review provider access, quota, or upstream contract status."
        )
    return f"{provider_name} could not complete governed external retrieval: {exc}"


async def _execute_external_provider(
    provider_name: str,
    *,
    provider_id: str,
    runner: Callable[[], Awaitable[list[EvidenceSearchResultResponse]]],
) -> tuple[
    list[EvidenceSearchResultResponse],
    EvidenceSearchProviderExecutionResponse,
    EvidenceSearchProviderNoticeResponse | None,
]:
    try:
        results = await runner()
    except Exception as exc:
        return (
            [],
            EvidenceSearchProviderExecutionResponse(
                provider_id=provider_id,
                provider_name=provider_name,
                status="failed",
                result_count=0,
                explicit_zero_results=False,
                completed_at=datetime.now(UTC),
                error_type=type(exc).__name__,
            ),
            EvidenceSearchProviderNoticeResponse(
                provider_name=provider_name,
                notice_type="execution_failure",
                message=_provider_error_message(provider_name, exc),
            ),
        )
    return (
        results,
        EvidenceSearchProviderExecutionResponse(
            provider_id=provider_id,
            provider_name=provider_name,
            status="succeeded",
            result_count=len(results),
            explicit_zero_results=not results,
            completed_at=datetime.now(UTC),
        ),
        None,
    )


async def search_external_evidence_impl(
    report: dict[str, Any],
    query_text: str,
    *,
    org_id: str | uuid.UUID | None = None,
    licensed_family_overlay_fn=search_licensed_family_overlay,
) -> dict[str, Any]:
    query = query_text.strip()
    context = build_external_query_context(report, query=query, org_id=org_id)
    provider_capabilities = merge_provider_capabilities(
        report_external_evidence.build_external_provider_capabilities(context)
    )
    executable_specs = report_external_evidence.active_external_provider_specs(context)
    runners: dict[str, Callable[[], Awaitable[list[EvidenceSearchResultResponse]]]] = {
        "pubchem": lambda: _search_external_pubchem(report, query),
        "patentsview": lambda: _search_external_patentsview(report, query),
        "uspto_odp": lambda: _search_external_uspto_odp(report, query),
        "epo_ops": lambda: _search_external_epo_ops(report, query),
        "patentscope": lambda: _search_external_patentscope(report, query),
        "ptab": lambda: _search_external_ptab(report, query),
        "orange_book": lambda: _search_external_orange_book(report, query),
        "purple_book": lambda: _search_external_purple_book(report, query),
        "licensed_family_overlay": lambda: _search_external_licensed_family_overlay(
            report,
            query,
            context=context,
            licensed_family_overlay_fn=licensed_family_overlay_fn,
        ),
    }

    results: list[EvidenceSearchResultResponse] = []
    provider_executions: list[EvidenceSearchProviderExecutionResponse] = []
    provider_notices: list[EvidenceSearchProviderNoticeResponse] = []
    tasks: list[
        Awaitable[
            tuple[
                list[EvidenceSearchResultResponse],
                EvidenceSearchProviderExecutionResponse,
                EvidenceSearchProviderNoticeResponse | None,
            ]
        ]
    ] = []
    runnable_specs: list[report_external_evidence.ExternalEvidenceProviderSpec] = []
    for spec in executable_specs:
        runner = runners.get(spec.name)
        if runner is None:
            provider_executions.append(
                EvidenceSearchProviderExecutionResponse(
                    provider_id=spec.provider_id,
                    provider_name=spec.name,
                    status="failed",
                    result_count=0,
                    explicit_zero_results=False,
                    completed_at=datetime.now(UTC),
                    error_type="MissingRuntimeHandler",
                )
            )
            provider_notices.append(
                EvidenceSearchProviderNoticeResponse(
                    provider_name=spec.name,
                    notice_type="missing_handler",
                    message=(
                        f"{spec.name} is configured for governed retrieval, but no "
                        "runtime handler is registered."
                    ),
                )
            )
            continue
        runnable_specs.append(spec)
        tasks.append(
            _execute_external_provider(
                spec.name,
                provider_id=spec.provider_id,
                runner=runner,
            )
        )

    gathered = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30) if tasks else []
    for batch, receipt, notice in gathered:
        results.extend(batch)
        provider_executions.append(receipt)
        if notice is not None:
            provider_notices.append(notice)
    for caution_note in report_external_evidence.build_external_caution_notes(context):
        provider_notices.append(
            EvidenceSearchProviderNoticeResponse(
                provider_name="routing_policy",
                notice_type="routing_policy",
                message=caution_note,
            )
        )
    deduped: dict[str, EvidenceSearchResultResponse] = {}
    for result in sorted(results, key=lambda item: item.relevance, reverse=True):
        if result.result_id not in deduped:
            deduped[result.result_id] = result

    final_results = list(deduped.values())[:25]
    external_sources = [item.provider_name for item in provider_capabilities]
    live_provider_count = len(runnable_specs)
    caution_note = (
        "Runs bounded governed external retrieval across configured public and regulatory sources. "
        "Provider failures are surfaced explicitly; no silent fallback occurs."
    )
    if context.routed_specialist_modality:
        caution_note += (
            f" Current modality {context.primary_modality_label} remains in supervised "
            "screening mode "
            "until specialist packs are certified."
        )
    if live_provider_count == 0:
        caution_note += " No live provider is currently active for this routed workspace."
    response = EvidenceSearchResponse(
        query=query,
        interpreted_query=f'Governed external evidence expansion: "{query}"',
        scope=EvidenceSearchScopeResponse(
            mode="external_evidence",
            external_live_retrieval=live_provider_count > 0,
            comment_routing_available=True,
            sources_considered=external_sources,
            governed_note=caution_note,
            provider_capabilities=provider_capabilities,
            providers=provider_capabilities,
            hybrid_evidence_ready=has_active_hybrid_layer(provider_capabilities),
        ),
        results=final_results,
        provider_executions=provider_executions,
        provider_notices=provider_notices,
        total=len(deduped),
    )
    return response.model_dump(mode="json")
