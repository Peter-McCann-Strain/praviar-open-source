"""Tests for governed evidence search over report provenance."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from conftest import bind_report_data, make_analysis_mock, valid_report_data
from pydantic import ValidationError

from api.db.models import AnalysisStatus
from api.errors import APIError
from api.schemas.report_evidence_search import (
    EvidenceSearchProviderCapabilityResponse,
    EvidenceSearchRequest,
)
from api.services import report_external_evidence
from api.services.licensed_family_overlay import LicensedFamilyOverlayRuntimeConfig
from api.services.report_evidence_search import (
    build_report_evidence_scope,
    search_external_evidence_impl,
    search_report_evidence_for_org_impl,
    search_report_evidence_impl,
)


def _evidence_search_report() -> dict:
    return valid_report_data(
        trust_mode="counsel",
        routing_profile={
            "modality": "small_molecule",
        },
        evidence_artifacts=[
            {
                "artifact_id": "artifact-1",
                "artifact_type": "search_hit",
                "source_name": "patentsview",
                "authority_tier": "authoritative",
                "jurisdiction": "US",
                "patent_id": "US12345678A1",
                "family_id": "fam-123",
                "summary": "Aspirin evidence artifact with governed provenance.",
                "record_basis": "Current report evidence fabric",
                "linked_node_ids": ["claim-1", "patent-1"],
            }
        ],
        matter_evidence_index={
            "material_patent_count": 1,
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["pubchem_sdq"],
            "incomplete_family_ids": [],
            "patent_records": [
                {
                    "patent_id": "US12345678A1",
                    "title": "Aspirin formulation patent",
                    "jurisdiction": "US",
                    "legal_status": "active",
                    "risk_level": "high",
                    "family_id": "fam-123",
                    "authoritative_source_names": ["patentsview"],
                    "supporting_source_names": ["pubchem_sdq"],
                    "gate_failures": ["blocking_patent_missing_invalidity_assessment"],
                    "prosecution_signals": ["narrowing amendment"],
                    "future_risk_signals": ["continuation family remains active"],
                }
            ],
        },
        search_strategy_log=[
            {
                "stage": "initial_gathering",
                "execution_profile": "world_class_adaptive",
                "trust_mode": "counsel",
                "jurisdictions": ["US", "EP"],
                "sources": ["aspirin patent", "patentsview"],
            }
        ],
        negative_search_log=[
            {
                "source": "patentsview",
                "gap_type": "missing_prosecution_context",
                "suggested_action": "Review the US file wrapper.",
                "description": "No prosecution wrapper found for a family member.",
            }
        ],
    )


def _external_evidence_ready_report(*, trust_mode: str) -> dict:
    report = _evidence_search_report()
    report["trust_mode"] = trust_mode
    report["routing_profile"] = {
        **(report.get("routing_profile") or {}),
        "capability_profile": "core_certified",
    }
    report["target_jurisdictions"] = ["US", "EP"]
    report["search_sources_used"] = [
        "patentsview",
        "pubchem_sdq",
        "orange_book",
    ]
    report["certification_scope"] = {
        "certified_jurisdictions": ["US", "EP"],
        "attorney_supervision_required": True,
    }
    if trust_mode == "monitor":
        report["search_loop_result"] = {"status": "ok"}
    return report


def _external_evidence_no_live_provider_report(*, trust_mode: str = "counsel") -> dict:
    report = _external_evidence_ready_report(trust_mode=trust_mode)
    report["routing_profile"] = {
        **(report.get("routing_profile") or {}),
        "modality": "biologic_or_sequence",
        "matter_type": "biologic_or_sequence",
    }
    report["decision_scope"] = {
        "matter_type": "biologic_or_sequence",
        "jurisdictions": ["JP"],
    }
    report["target_jurisdictions"] = ["JP"]
    report["certification_scope"] = {
        "certified_jurisdictions": ["JP"],
        "attorney_supervision_required": True,
    }
    report["search_sources_used"] = ["purple_book"]
    report["search_strategy_log"] = [
        {
            "stage": "external_expansion",
            "execution_profile": "world_class_adaptive",
            "trust_mode": trust_mode,
            "jurisdictions": ["JP"],
            "sources": ["purple_book"],
        }
    ]
    return report


def _ep_only_external_report(*, modality: str = "small_molecule") -> dict:
    report = _external_evidence_ready_report(trust_mode="counsel")
    report["routing_profile"] = {
        **(report.get("routing_profile") or {}),
        "modality": modality,
    }
    report["decision_scope"] = {
        "matter_type": modality,
        "jurisdictions": ["EP"],
    }
    report["target_jurisdictions"] = ["EP"]
    report["certification_scope"] = {
        "certified_jurisdictions": ["EP"],
        "attorney_supervision_required": True,
    }
    report["search_strategy_log"] = [
        {
            "stage": "external_expansion",
            "execution_profile": "world_class_adaptive",
            "trust_mode": "counsel",
            "jurisdictions": ["EP"],
            "sources": ["epo", "patentscope"],
        }
    ]
    return report


def test_search_report_evidence_impl_returns_governed_results_with_scope_metadata():
    report = _evidence_search_report()

    results = search_report_evidence_impl(report, "aspirin")

    assert results["query"] == "aspirin"
    assert results["interpreted_query"] == 'Governed evidence search: "aspirin"'
    assert results["scope"]["mode"] == "report_evidence"
    assert results["scope"]["external_live_retrieval"] is True
    assert results["scope"]["comment_routing_available"] is True
    assert results["scope"]["hybrid_evidence_ready"] is True
    assert "artifacts" in results["scope"]["governed_note"].lower()
    assert "patent records" in results["scope"]["governed_note"].lower()
    assert results["scope"]["provider_capabilities"] == results["scope"]["providers"]
    provider_names = {item["provider_name"] for item in results["scope"]["provider_capabilities"]}
    assert provider_names == {
        "Report-derived evidence layer",
        "patentsview",
        "pubchem_sdq",
        "pubchem",
        "uspto_odp",
        "ptab",
        "orange_book",
        "epo_ops",
        "patentscope",
        "licensed_family_overlay",
        "licensed_markush_overlay",
    }
    report_layer = next(
        item
        for item in results["scope"]["provider_capabilities"]
        if item["provider_class"] == "report_derived"
    )
    assert report_layer["live_retrieval_supported"] is False
    assert report_layer["jurisdiction_coverage"] == ["EP", "US"]
    assert report_layer["modality_coverage"] == ["small_molecule"]
    patentsview_layer = next(
        item
        for item in results["scope"]["provider_capabilities"]
        if item["provider_name"] == "patentsview"
    )
    assert patentsview_layer["provider_class"] == "public_open"
    assert patentsview_layer["live_retrieval_supported"] is True
    assert patentsview_layer["materialized_in_report"] is True
    assert patentsview_layer["execution_mode"] == "report_materialized"
    assert patentsview_layer["source_as_of"] == "Completed report snapshot"
    assert results["total"] == 3

    sections = {item["section"] for item in results["results"]}
    assert sections == {"evidence_artifact", "matter_evidence_index", "search_strategy_log"}

    artifact_result = next(
        item for item in results["results"] if item["section"] == "evidence_artifact"
    )
    patent_result = next(
        item for item in results["results"] if item["section"] == "matter_evidence_index"
    )
    strategy_result = next(
        item for item in results["results"] if item["section"] == "search_strategy_log"
    )

    assert artifact_result["source_name"] == "patentsview"
    assert artifact_result["authority_tier"] == "authoritative"
    assert artifact_result["provenance"][0]["label"] == "Artifact ID"
    assert artifact_result["follow_up_target"]["target_type"] == "patent"
    assert artifact_result["follow_up_target"]["target_id"] == "US12345678A1"

    assert patent_result["title"] == "Aspirin formulation patent"
    assert patent_result["authority_tier"] == "authoritative"
    assert patent_result["provenance"][0]["label"] == "Legal status"
    assert patent_result["follow_up_target"]["target_type"] == "patent"

    assert strategy_result["source_name"] == "search_strategy_log"
    assert strategy_result["authority_tier"] == "discovery"
    assert strategy_result["follow_up_target"]["target_type"] == "analysis"
    assert strategy_result["provenance"][0]["label"] == "Jurisdictions"


def _blocking_intent_search_report(*, include_explicit_blockers: bool = True) -> dict:
    patent_rows = [
        (
            "WO0000000002A1",
            "Nucleoside phosphoramidate prodrugs",
            "high",
            "Core compound patent. Commercialisation is blocked.",
        ),
        (
            "WO0000000004A1",
            "Solid forms of an antiviral compound",
            "high",
            "Blocking polymorph patent if Form 1 is used.",
        ),
        (
            "WO0000000001A1",
            "Nucleoside compounds for treating viral infections",
            "clear",
            "Expired patent with no current infringement risk.",
        ),
        (
            "WO0000000003A1",
            "Pharmaceutical compositions",
            "low",
            "Low-risk formulation record.",
        ),
    ]
    blocking_patent_ids = [row[0] for row in patent_rows[:2]]
    return {
        "trust_mode": "explorer",
        "evidence_artifacts": [
            {
                "artifact_id": f"{patent_id}:search_hit",
                "artifact_type": "search_hit",
                "source_name": "pubchem_sdq,bigquery",
                "authority_tier": "supporting",
                "jurisdiction": "US",
                "patent_id": patent_id,
                "summary": "Patent retained as material record.",
            }
            for patent_id, *_ in patent_rows
        ],
        "patent_analyses": [
            {
                "patent_id": patent_id,
                "title": title,
                "assignee": "Fictional Helix Therapeutics",
                "risk_level": risk_level,
                "risk_summary": risk_summary,
            }
            for patent_id, title, risk_level, risk_summary in patent_rows
        ],
        "clearance_decision": {
            "decision_audit": {
                "claim_program_summary": {
                    "blocking_patent_ids": (
                        blocking_patent_ids if include_explicit_blockers else []
                    )
                }
            }
        },
        "matter_evidence_index": {"patent_records": []},
    }


@pytest.mark.parametrize("intent", ["blocking", "blocker", "blocked"])
def test_blocking_intent_search_excludes_non_blocking_patents_with_common_assignee(intent):
    results = search_report_evidence_impl(
        _blocking_intent_search_report(),
        f"Fictional Helix {intent} patent",
    )

    assert [result["patent_id"] for result in results["results"]] == [
        "WO0000000002A1",
        "WO0000000004A1",
    ]
    assert results["total"] == 2
    assert all(result["relevance"] > 0.6 for result in results["results"])


def test_blocking_intent_search_fails_closed_without_explicit_blocking_ids():
    results = search_report_evidence_impl(
        _blocking_intent_search_report(include_explicit_blockers=False),
        "Fictional Helix blocking patent",
    )

    assert results["results"] == []
    assert results["total"] == 0


def test_evidence_search_preserves_generic_and_exact_identifier_queries():
    report = _blocking_intent_search_report()

    generic_results = search_report_evidence_impl(report, "patent")
    exact_results = search_report_evidence_impl(report, "WO0000000001A1")

    assert generic_results["total"] == 4
    assert [result["patent_id"] for result in exact_results["results"]] == ["WO0000000001A1"]
    assert exact_results["results"][0]["relevance"] == 0.99


@pytest.mark.asyncio
async def test_search_report_evidence_for_org_impl_scopes_by_org_and_searches_loaded_report(
    mock_db,
):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = _evidence_search_report()
    bind_report_data(report, analysis_id=analysis_id, org_id=org_id)
    analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    get_analysis_for_org = AsyncMock(return_value=analysis)

    results = await search_report_evidence_for_org_impl(
        mock_db,
        analysis_id=analysis_id,
        org_id=org_id,
        query_text="aspirin",
        get_analysis_for_org_fn=get_analysis_for_org,
    )

    get_analysis_for_org.assert_awaited_once_with(
        mock_db,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    assert results["query"] == "aspirin"
    assert results["total"] == 3
    assert results["scope"]["mode"] == "report_evidence"
    assert results["scope"]["external_live_retrieval"] is True
    assert results["scope"]["hybrid_evidence_ready"] is True


@pytest.mark.asyncio
async def test_search_report_evidence_for_org_impl_raises_404_when_report_missing(mock_db):
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(status=AnalysisStatus.COMPLETED, report_data=None)
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_evidence_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="aspirin",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Report not yet available"


@pytest.mark.asyncio
async def test_search_report_evidence_for_org_impl_rejects_non_completed_report_payload(mock_db):
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(
            status=AnalysisStatus.DELETED,
            report_data=_evidence_search_report(),
        )
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_evidence_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="aspirin",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Report not yet available"


@pytest.mark.asyncio
async def test_search_report_evidence_for_org_impl_rejects_unsupported_patent_records(mock_db):
    report = valid_report_data()
    report["matter_evidence_index"]["patent_records"] = [
        {
            "patent_id": "US99999999A1",
            "title": "Unsupported orphan patent record",
            "legal_status": "active",
            "risk_level": "high",
            "authoritative_source_names": ["patentsview"],
        }
    ]
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(status=AnalysisStatus.COMPLETED, report_data=report)
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_evidence_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="US99999999A1",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Report not yet available"


@pytest.mark.asyncio
async def test_report_evidence_search_route_returns_governed_payload(scientist_client):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(id=analysis_id, report_data=_evidence_search_report())
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    response = await client.post(
        f"/api/v1/reports/{analysis_id}/evidence-search",
        json={"query": "aspirin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"]["mode"] == "report_evidence"
    assert payload["scope"]["comment_routing_available"] is True
    assert payload["scope"]["provider_capabilities"][0]["provider_class"] == "report_derived"
    assert payload["results"][0]["follow_up_target"]["target_type"] in {"analysis", "patent"}


@pytest.mark.asyncio
async def test_report_evidence_search_route_uses_redacted_report_for_non_attorney_when_required(
    scientist_client,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        report_data=valid_report_data(
            trust_mode="counsel",
            evidence_artifacts=[
                {
                    "artifact_id": "artifact-sensitive",
                    "artifact_type": "search_hit",
                    "source_name": "patentsview",
                    "authority_tier": "authoritative",
                    "jurisdiction": "US",
                    "patent_id": "US12345678A1",
                    "summary": "Restricted structural similarity risk language.",
                }
            ],
            matter_evidence_index={
                "patent_records": [
                    {
                        "patent_id": "US12345678A1",
                        "title": "Aspirin formulation",
                        "risk_level": "high",
                        "gate_failures": ["Restricted structural similarity risk language."],
                    }
                ]
            },
        ),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with patch(
        "api.routes.reports.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "structural similarity"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["scope"]["external_live_retrieval"] is False


@pytest.mark.asyncio
async def test_report_evidence_search_route_rejects_redacted_non_completed_report_payload(
    scientist_client,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        status=AnalysisStatus.RUNNING,
        report_data=_evidence_search_report(),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with patch(
        "api.routes.reports.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "aspirin"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not yet available"


def test_search_report_evidence_impl_keeps_hybrid_readiness_false_for_report_only_scope():
    report = {
        "routing_profile": {
            "modality": "small_molecule",
        },
        "decision_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
        },
        "target_jurisdictions": ["US", "EP"],
        "search_sources_used": [],
        "evidence_adapter_results": [],
        "evidence_artifacts": [
            {
                "artifact_id": "artifact-1",
                "artifact_type": "internal_note",
                "source_name": "report_artifact_store",
                "summary": "Internal governed artifact only.",
            }
        ],
        "search_strategy_log": [],
        "matter_evidence_index": {"material_patent_count": 0},
    }

    results = search_report_evidence_impl(report, "internal")

    assert results["scope"]["provider_capabilities"] == [
        {
            "provider_id": "report_derived",
            "provider_name": "Report-derived evidence layer",
            "provider_class": "report_derived",
            "provider_status": "active",
            "live_retrieval_supported": False,
            "configured": True,
            "configured_for_org": True,
            "materialized_in_report": True,
            "execution_mode": "report_materialized",
            "modality_coverage": ["small_molecule"],
            "jurisdiction_coverage": ["EP", "US"],
            "governance_note": (
                "Search runs against evidence already captured in this report. "
                "No fresh external retrieval is executed from this workspace."
            ),
            "retrieved_at": "",
            "source_as_of": "Completed report snapshot",
            "dataset_version": "report_record",
        }
    ]
    assert results["scope"]["providers"] == results["scope"]["provider_capabilities"]
    assert results["scope"]["external_live_retrieval"] is False
    assert results["scope"]["hybrid_evidence_ready"] is False


def test_build_report_evidence_scope_keeps_declared_licensed_overlays_non_live():
    report = _external_evidence_ready_report(trust_mode="counsel")
    report["search_sources_used"] = [
        *report["search_sources_used"],
        "clarivate_derwent",
        "questel_global_families",
    ]

    scope = build_report_evidence_scope(report, external_retrieval_allowed=True)

    overlay_capabilities = [
        capability
        for capability in scope.provider_capabilities
        if capability.provider_class == "licensed_overlay"
        and capability.provider_status == "active"
    ]

    assert {capability.provider_name for capability in overlay_capabilities} == {
        "clarivate_derwent",
        "questel_global_families",
    }
    assert all(capability.live_retrieval_supported is False for capability in overlay_capabilities)
    assert all(
        "materialized in the report" in capability.governance_note
        for capability in overlay_capabilities
    )
    assert all(
        "does not execute fresh" in capability.governance_note
        for capability in overlay_capabilities
    )


def test_external_provider_registry_filters_or_cautions_us_only_providers_for_ep_scope():
    context = report_external_evidence.build_external_query_context(
        query="aspirin",
        trust_mode="counsel",
        modalities=["small_molecule"],
        jurisdictions=["EP"],
        patent_identifier=None,
        compound_name="aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
        compound_cid=2244,
    )
    capabilities = report_external_evidence.build_external_provider_capabilities(context)
    capability_by_name = {capability.provider_name: capability for capability in capabilities}

    patentsview = capability_by_name.get("patentsview")
    assert patentsview is not None
    assert patentsview.provider_status == "caution_only"
    assert patentsview.live_retrieval_supported is False
    assert patentsview.jurisdiction_coverage == []
    assert "outside this provider's certified coverage" in patentsview.governance_note

    uspto = capability_by_name["uspto_odp"]
    assert uspto.provider_status == "caution_only"
    assert uspto.live_retrieval_supported is False
    assert uspto.jurisdiction_coverage == []

    ptab = capability_by_name["ptab"]
    assert ptab.provider_status == "caution_only"
    assert ptab.live_retrieval_supported is False
    assert "Executes only when the query resolves to a patent identifier." in ptab.governance_note


def test_external_provider_registry_elevates_caution_for_specialist_modalities():
    context = report_external_evidence.build_external_query_context(
        query="markush aspirin scaffold",
        trust_mode="counsel",
        modalities=["markush_candidate"],
        jurisdictions=["EP"],
        patent_identifier=None,
        compound_name="aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
        compound_cid=2244,
    )
    capabilities = report_external_evidence.build_external_provider_capabilities(context)
    notes = report_external_evidence.build_external_caution_notes(context)
    capability_by_name = {capability.provider_name: capability for capability in capabilities}

    assert "pubchem" not in capability_by_name
    assert capability_by_name["patentsview"].provider_status == "caution_only"
    assert capability_by_name["licensed_markush_overlay"].provider_status == "declared_only"
    assert any("supervised screening mode for modality markush_candidate" in note for note in notes)
    assert any("Current jurisdiction scope is non-US" in note for note in notes)


def test_external_provider_registry_declares_licensed_overlay_placeholders_as_non_live():
    context = report_external_evidence.build_external_query_context(
        query="aspirin",
        trust_mode="counsel",
        org_id=None,
        modalities=["small_molecule"],
        jurisdictions=["US", "EP"],
        patent_identifier=None,
        compound_name="aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
        compound_cid=2244,
    )
    capabilities = report_external_evidence.build_external_provider_capabilities(context)
    capability_by_name = {capability.provider_name: capability for capability in capabilities}

    family_overlay = capability_by_name["licensed_family_overlay"]
    assert family_overlay.provider_class == "licensed_overlay"
    assert family_overlay.provider_status == "declared_only"
    assert family_overlay.live_retrieval_supported is False
    assert (
        "No licensed provider is configured in this workspace yet."
        in family_overlay.governance_note
    )


def test_external_provider_registry_activates_configured_licensed_overlay_for_allowed_org():
    org_id = uuid.uuid4()
    runtime_config = LicensedFamilyOverlayRuntimeConfig(
        provider_name="Acme Family Overlay",
        search_url="https://licensed.example/search",
        api_key="secret",
        allowed_org_ids=frozenset({str(org_id)}),
        timeout_seconds=12.0,
    )

    with patch(
        "api.services.report_external_evidence.get_licensed_family_overlay_runtime_config",
        return_value=runtime_config,
    ):
        context = report_external_evidence.build_external_query_context(
            query="aspirin",
            trust_mode="counsel",
            org_id=str(org_id),
            modalities=["small_molecule"],
            jurisdictions=["US", "EP"],
            patent_identifier=None,
            compound_name="aspirin",
            compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
            compound_cid=2244,
        )
        capabilities = report_external_evidence.build_external_provider_capabilities(context)

    family_overlay = next(
        capability
        for capability in capabilities
        if capability.provider_id == "licensed_family_overlay"
    )
    assert family_overlay.provider_status == "active"
    assert family_overlay.live_retrieval_supported is True
    assert family_overlay.configured is True
    assert family_overlay.configured_for_org is True
    assert family_overlay.execution_mode == "live_api"
    assert "Acme Family Overlay" in family_overlay.governance_note


def test_external_provider_registry_holds_configured_licensed_overlay_for_disallowed_org():
    allowed_org_id = uuid.uuid4()
    runtime_config = LicensedFamilyOverlayRuntimeConfig(
        provider_name="Acme Family Overlay",
        search_url="https://licensed.example/search",
        api_key="secret",
        allowed_org_ids=frozenset({str(allowed_org_id)}),
        timeout_seconds=12.0,
    )

    with patch(
        "api.services.report_external_evidence.get_licensed_family_overlay_runtime_config",
        return_value=runtime_config,
    ):
        context = report_external_evidence.build_external_query_context(
            query="aspirin",
            trust_mode="counsel",
            org_id=str(uuid.uuid4()),
            modalities=["small_molecule"],
            jurisdictions=["US", "EP"],
            patent_identifier=None,
            compound_name="aspirin",
            compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
            compound_cid=2244,
        )
        capabilities = report_external_evidence.build_external_provider_capabilities(context)

    family_overlay = next(
        capability
        for capability in capabilities
        if capability.provider_id == "licensed_family_overlay"
    )
    assert family_overlay.provider_status == "caution_only"
    assert family_overlay.live_retrieval_supported is False
    assert family_overlay.configured is True
    assert family_overlay.configured_for_org is False
    assert "not enabled for the current org" in family_overlay.governance_note


def test_evidence_search_request_accepts_external_retrieval_mode():
    body = EvidenceSearchRequest.model_validate(
        {
            "query": "aspirin",
            "retrieval_mode": "external_evidence",
        }
    )

    assert body.query == "aspirin"
    assert body.retrieval_mode == "external_evidence"


def test_evidence_search_request_rejects_padded_one_character_query():
    with pytest.raises(ValidationError) as exc_info:
        EvidenceSearchRequest.model_validate({"query": " x "})

    assert "at least 2 non-whitespace characters" in str(exc_info.value)


def test_provider_capability_response_exposes_source_timing_metadata():
    capability = EvidenceSearchProviderCapabilityResponse(
        provider_id="pubchem",
        provider_name="pubchem",
        provider_class="public_open",
        live_retrieval_supported=True,
        configured=True,
        configured_for_org=True,
        execution_mode="live_api",
        retrieved_at="2026-06-18T14:30:00Z",
        source_as_of="Provider live endpoint",
        dataset_version="live",
        governance_note="Fresh PubChem retrieval is permitted.",
    )

    assert capability.retrieved_at == "2026-06-18T14:30:00Z"
    assert capability.source_as_of == "Provider live endpoint"
    assert capability.dataset_version == "live"


@pytest.mark.asyncio
async def test_search_external_evidence_impl_executes_configured_licensed_overlay_for_allowed_org():
    org_id = uuid.uuid4()
    report = _ep_only_external_report(modality="markush_candidate")
    runtime_config = LicensedFamilyOverlayRuntimeConfig(
        provider_name="Acme Family Overlay",
        search_url="https://licensed.example/search",
        api_key="secret",
        allowed_org_ids=frozenset({str(org_id)}),
        timeout_seconds=12.0,
    )
    overlay_spec = report_external_evidence.ExternalEvidenceProviderSpec(
        provider_id="licensed_family_overlay",
        name="licensed_family_overlay",
        provider_class="licensed_overlay",
        live_retrieval_supported=True,
        governance_note="Runs governed commercial family/legal-status retrieval.",
        configured=True,
        execution_mode="live_api",
        org_allowlist=runtime_config.allowed_org_ids,
    )

    with (
        patch(
            "api.services.report_external_evidence.get_licensed_family_overlay_runtime_config",
            return_value=runtime_config,
        ),
        patch(
            "api.services.report_external_evidence.active_external_provider_specs",
            return_value=[overlay_spec],
        ),
        patch(
            "api.services.report_evidence_search.search_licensed_family_overlay",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "licensed-1",
                        "title": "Celecoxib family overlay result",
                        "summary": "Commercial family overlay found a live legal-status family match.",
                        "patent_id": "EP1234567A1",
                        "family_id": "FAM-200",
                        "jurisdictions": ["EP", "JP"],
                        "assignees": ["Example Pharma"],
                        "legal_status": "pending",
                    }
                ]
            ),
        ),
    ):
        results = await search_external_evidence_impl(
            report,
            "celecoxib scaffold",
            org_id=org_id,
        )

    assert results["scope"]["mode"] == "external_evidence"
    assert results["scope"]["external_live_retrieval"] is True
    family_overlay = next(
        capability
        for capability in results["scope"]["provider_capabilities"]
        if capability["provider_id"] == "licensed_family_overlay"
    )
    assert family_overlay["provider_status"] == "active"
    assert family_overlay["configured"] is True
    assert family_overlay["configured_for_org"] is True
    assert family_overlay["live_retrieval_supported"] is True
    assert family_overlay["execution_mode"] == "live_api"
    assert any(
        item["source_name"] == "licensed_family_overlay"
        and item["section"] == "external_licensed_family_overlay"
        for item in results["results"]
    )


@pytest.mark.asyncio
async def test_report_evidence_search_route_forbids_client_role(client_role_client):
    client, db = client_role_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(id=analysis_id, report_data=_evidence_search_report())
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    response = await client.post(
        f"/api/v1/reports/{analysis_id}/evidence-search",
        json={"query": "aspirin"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == ("Insufficient permissions: requires report.view_full")


@pytest.mark.asyncio
async def test_report_evidence_search_route_external_mode_still_forbids_client_role(
    client_role_client,
):
    client, db = client_role_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        report_data=_external_evidence_ready_report(trust_mode="counsel"),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    response = await client.post(
        f"/api/v1/reports/{analysis_id}/evidence-search",
        json={"query": "aspirin", "retrieval_mode": "external_evidence"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == ("Insufficient permissions: requires report.view_full")


@pytest.mark.asyncio
async def test_report_evidence_search_route_external_mode_forbids_non_attorney_when_required(
    scientist_client,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()

    with (
        patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
        ),
        patch(
            "api.services.report_evidence_search.search_external_evidence_impl",
            new=AsyncMock(),
        ) as external_search,
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "aspirin", "retrieval_mode": "external_evidence"},
        )

    assert response.status_code == 403
    assert "restricted to attorney-role users" in response.json()["detail"]
    external_search.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_evidence_search_route_external_mode_requires_live_provider_scope(
    scientist_client,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        report_data=_external_evidence_no_live_provider_report(),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with (
        patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
        ),
        patch(
            "api.services.report_evidence_search.search_external_evidence_impl",
            new=AsyncMock(),
        ) as external_search,
        patch(
            "api.services.report_evidence_search.report_external_evidence.active_external_provider_specs",
            return_value=[],
        ),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "sequence claim", "retrieval_mode": "external_evidence"},
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Governed external evidence expansion requires an active live provider for this report scope."
    )
    external_search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("trust_mode", ["counsel", "monitor"])
async def test_report_evidence_search_route_external_mode_exposes_live_scope_for_permitted_trust_modes(
    scientist_client,
    trust_mode: str,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        report_data=_external_evidence_ready_report(trust_mode=trust_mode),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with (
        patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
        ),
        patch(
            "api.services.report_evidence_search.search_external_evidence_impl",
            new=AsyncMock(
                return_value={
                    "query": "aspirin",
                    "interpreted_query": 'Governed external evidence expansion: "aspirin"',
                    "scope": {
                        "mode": "external_evidence",
                        "external_live_retrieval": True,
                        "comment_routing_available": True,
                        "sources_considered": ["pubchem", "patentsview", "uspto_odp"],
                        "governed_note": "Runs bounded governed external retrieval across configured sources.",
                        "provider_capabilities": [
                            {
                                "provider_name": "pubchem",
                                "provider_class": "public_open",
                                "live_retrieval_supported": True,
                                "modality_coverage": ["small_molecule"],
                                "jurisdiction_coverage": ["US", "EP"],
                                "governance_note": "Fresh PubChem retrieval is permitted.",
                            },
                            {
                                "provider_name": "patentsview",
                                "provider_class": "public_open",
                                "live_retrieval_supported": True,
                                "modality_coverage": ["small_molecule"],
                                "jurisdiction_coverage": ["US"],
                                "governance_note": "Fresh PatentsView retrieval is permitted.",
                            },
                        ],
                        "providers": [
                            {
                                "provider_name": "pubchem",
                                "provider_class": "public_open",
                                "live_retrieval_supported": True,
                                "modality_coverage": ["small_molecule"],
                                "jurisdiction_coverage": ["US", "EP"],
                                "governance_note": "Fresh PubChem retrieval is permitted.",
                            },
                            {
                                "provider_name": "patentsview",
                                "provider_class": "public_open",
                                "live_retrieval_supported": True,
                                "modality_coverage": ["small_molecule"],
                                "jurisdiction_coverage": ["US"],
                                "governance_note": "Fresh PatentsView retrieval is permitted.",
                            },
                        ],
                        "hybrid_evidence_ready": True,
                    },
                    "results": [
                        {
                            "result_id": "pubchem:compound:2244",
                            "title": "aspirin compound record",
                            "summary": "PubChem resolved aspirin to CID 2244.",
                            "source_name": "pubchem",
                            "authority_tier": "authoritative",
                            "freshness": "Retrieved live from PubChem.",
                            "artifact_type": "compound_record",
                            "section": "external_pubchem",
                            "patent_id": "",
                            "relevance": 0.96,
                            "provenance": [{"label": "CID", "value": "2244"}],
                            "follow_up_target": {
                                "target_type": "analysis",
                                "target_id": "2244",
                                "suggested_note": "Review PubChem compound record",
                            },
                        }
                    ],
                    "total": 1,
                }
            ),
        ),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "aspirin", "retrieval_mode": "external_evidence"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"]["mode"] == "external_evidence"
    assert payload["scope"]["external_live_retrieval"] is True
    assert payload["scope"]["comment_routing_available"] is True
    assert payload["scope"]["hybrid_evidence_ready"] is True
    assert any(
        item["live_retrieval_supported"] for item in payload["scope"]["provider_capabilities"]
    )
    assert {item["provider_class"] for item in payload["scope"]["provider_capabilities"]} >= {
        "public_open"
    }
    assert payload["results"][0]["source_name"] in {"pubchem", "patentsview"}


@pytest.mark.asyncio
async def test_report_evidence_search_route_external_mode_forbids_explorer_reports(
    scientist_client,
):
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    analysis = make_analysis_mock(
        id=analysis_id,
        report_data=_external_evidence_ready_report(trust_mode="explorer"),
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with patch(
        "api.routes.reports.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/evidence-search",
            json={"query": "aspirin", "retrieval_mode": "external_evidence"},
        )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Governed external evidence expansion is unavailable for explorer-mode reports"
    )
