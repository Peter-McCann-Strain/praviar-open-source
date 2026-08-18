from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.report_evidence_search import (
    EvidenceSearchProviderCapabilityResponse,
    EvidenceSearchResultResponse,
)
from api.services import report_external_evidence
from api.services.report_external_providers import (
    _execute_external_provider,
    _extract_uspto_search_rows,
    _provider_error_message,
    _search_external_epo_ops,
    _search_external_licensed_family_overlay,
    _search_external_orange_book,
    _search_external_patentscope,
    _search_external_patentsview,
    _search_external_ptab,
    _search_external_pubchem,
    _search_external_purple_book,
    _search_external_uspto_odp,
    build_external_query_context,
    search_external_evidence_impl,
)


def _context(*, specialist: bool = False):
    modalities = ["antibody"] if specialist else ["small_molecule"]
    return report_external_evidence.build_external_query_context(
        query="aspirin",
        trust_mode="screening",
        org_id=str(uuid.uuid4()),
        modalities=modalities,
        jurisdictions=["US"],
        patent_identifier=None,
        compound_name="Aspirin",
        compound_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
        compound_cid=2244,
    )


def _result(result_id: str, relevance: float) -> EvidenceSearchResultResponse:
    return EvidenceSearchResultResponse(
        result_id=result_id,
        title=f"Result {result_id}",
        summary="Governed evidence",
        source_name="pubchem",
        relevance=relevance,
    )


def _spec(name: str, provider_id: str | None = None):
    return report_external_evidence.ExternalEvidenceProviderSpec(
        provider_id=provider_id or name,
        name=name,
        provider_class="public_open",
        live_retrieval_supported=True,
        governance_note="Test provider",
    )


class _AsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def _client_factory(client: _AsyncClient) -> MagicMock:
    return MagicMock(return_value=client)


def test_build_external_query_context_normalises_report_routing_inputs() -> None:
    with (
        patch(
            "api.services.report_external_providers.report_compound_context",
            return_value=("Aspirin", "CCO", 2244),
        ),
        patch(
            "api.services.report_external_providers.normalized_trust_mode",
            return_value="screening",
        ),
        patch(
            "api.services.report_external_providers.collect_modalities",
            return_value=["small_molecule"],
        ),
        patch(
            "api.services.report_external_providers.collect_jurisdictions",
            return_value=["US"],
        ),
        patch(
            "api.services.report_external_providers.query_patent_identifier",
            return_value="US-123-A1",
        ),
    ):
        context = build_external_query_context(
            {},
            query="aspirin",
            org_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        )

    assert context.query == "aspirin"
    assert context.org_id == "12345678-1234-5678-1234-567812345678"
    assert context.modalities == ("small_molecule",)
    assert context.jurisdictions == ("US",)
    assert context.patent_identifier == "US-123-A1"
    assert context.compound_cid == 2244


@pytest.mark.asyncio
async def test_pubchem_search_uses_report_identity_fallback_and_limits_patent_links() -> None:
    client = _AsyncClient()
    client.resolve_by_name = AsyncMock(return_value=None)
    client.get_synonyms = AsyncMock(return_value=["ASA", "Acetylsalicylic acid"])
    client.get_patent_links = AsyncMock(
        return_value=["US-1-A1", "", "US-2-A1", "US-3-A1", "US-4-A1", "US-5-A1"]
    )

    with (
        patch(
            "api.services.report_external_providers.report_compound_context",
            return_value=("Aspirin", "CCO", 2244),
        ),
        patch(
            "praviar_pipeline.clients.pubchem.PubChemClient",
            _client_factory(client),
        ),
    ):
        results = await _search_external_pubchem({}, "aspirin")

    assert results[0].result_id == "pubchem:compound:2244"
    assert results[0].authority_tier == "authoritative"
    assert [result.patent_id for result in results[1:]] == [
        "US-1-A1",
        "US-2-A1",
        "US-3-A1",
        "US-4-A1",
    ]
    client.get_synonyms.assert_awaited_once_with(2244)
    client.get_patent_links.assert_awaited_once_with(2244)


@pytest.mark.asyncio
async def test_pubchem_search_returns_empty_when_resolution_has_no_numeric_cid() -> None:
    client = _AsyncClient()
    client.resolve_by_name = AsyncMock(return_value={"CID": "unknown"})

    with (
        patch(
            "api.services.report_external_providers.report_compound_context",
            return_value=("Different compound", "", None),
        ),
        patch(
            "praviar_pipeline.clients.pubchem.PubChemClient",
            _client_factory(client),
        ),
    ):
        results = await _search_external_pubchem({}, "aspirin")

    assert results == []


@pytest.mark.asyncio
async def test_patentsview_search_maps_only_bounded_provider_rows() -> None:
    client = _AsyncClient()
    client.search_by_compound_keywords = AsyncMock(
        return_value=[
            {
                "patent_id": f"US-{index}-A1",
                "patent_title": f"Patent {index}",
                "patent_abstract": "Aspirin formulation and method.",
                "patent_date": "2026-01-01",
                "patent_kind": "A1",
                "patent_num_claims": 20,
                "assignees": [
                    {"assignee_organization": "Example Pharma"},
                    "invalid",
                    {"assignee_organization": ""},
                ],
            }
            for index in range(7)
        ]
    )

    with patch(
        "praviar_pipeline.clients.patentsview.PatentsViewClient",
        _client_factory(client),
    ):
        results = await _search_external_patentsview({}, "aspirin")

    assert len(results) == 5
    assert results[0].result_id == "patentsview:US-0-A1"
    assert results[0].patent_id == "US-0-A1"
    client.search_by_compound_keywords.assert_awaited_once_with("aspirin", size=5)


@pytest.mark.asyncio
async def test_uspto_odp_search_maps_nested_and_flat_application_metadata() -> None:
    client = _AsyncClient()
    client.search_patents = AsyncMock(
        return_value={
            "results": [
                {
                    "applicationNumberText": "18123456",
                    "applicationMetaData": {
                        "patentNumber": "US-123-A1",
                        "inventionTitle": "Aspirin composition",
                        "applicationStatusDescriptionText": "Pending",
                        "filingDate": "2025-01-01",
                    },
                },
                {
                    "patentNumber": "US-456-A1",
                    "inventionTitle": "Fallback title",
                    "applicationMetaData": "invalid",
                },
            ]
        }
    )

    with patch(
        "praviar_pipeline.clients.uspto_odp.USPTOODPClient",
        _client_factory(client),
    ):
        results = await _search_external_uspto_odp({}, "aspirin")

    assert [result.patent_id for result in results] == ["US-123-A1", "US-456-A1"]
    assert results[0].title == "Aspirin composition"
    assert results[1].title == "Fallback title"
    client.search_patents.assert_awaited_once_with("aspirin", limit=5)


@pytest.mark.asyncio
async def test_epo_and_patentscope_searches_preserve_jurisdiction_provenance() -> None:
    epo = _AsyncClient()
    epo.search_published_data = AsyncMock(
        return_value=[
            {
                "doc_number": "EP-123-A1",
                "title": "Aspirin salt",
                "abstract": "Aspirin salt disclosure.",
                "applicant": ["Example Pharma"],
                "country": "EP",
            }
        ]
    )
    patentscope = _AsyncClient()
    patentscope.search_patents = AsyncMock(
        return_value=[
            {
                "publication_number": "WO-123-A1",
                "title": "Aspirin formulation",
                "abstract": "Aspirin formulation disclosure.",
                "applicants": ["Example Pharma"],
                "filing_date": "2024-01-01",
            }
        ]
    )

    with patch(
        "praviar_pipeline.clients.epo_ops.EPOOPSClient",
        _client_factory(epo),
    ):
        epo_results = await _search_external_epo_ops({}, "aspirin salt")
    with (
        patch(
            "api.services.report_external_providers.external_query_jurisdictions",
            return_value=["US", "EP"],
        ),
        patch(
            "praviar_pipeline.clients.patentscope.PatentScopeClient",
            _client_factory(patentscope),
        ),
    ):
        patentscope_results = await _search_external_patentscope({}, "aspirin")

    assert epo_results[0].patent_id == "EP-123-A1"
    epo.search_published_data.assert_awaited_once_with(
        claim_keywords=["aspirin", "salt"],
        max_results=5,
    )
    assert patentscope_results[0].patent_id == "WO-123-A1"
    patentscope.search_patents.assert_awaited_once_with(
        keywords=["aspirin"],
        jurisdictions=["US", "EP"],
        max_results=5,
    )


@pytest.mark.asyncio
async def test_ptab_search_requires_patent_identifier_and_maps_proceedings() -> None:
    with patch(
        "api.services.report_external_providers.query_patent_identifier",
        return_value=None,
    ):
        assert await _search_external_ptab({}, "aspirin") == []

    client = _AsyncClient()
    client.get_proceedings = AsyncMock(
        return_value=[
            {
                "trialNumber": "IPR2026-00001",
                "proceedingType": "IPR",
                "proceedingStatus": "Instituted",
            }
        ]
    )
    with (
        patch(
            "api.services.report_external_providers.query_patent_identifier",
            return_value="US-123-A1",
        ),
        patch(
            "praviar_pipeline.clients.ptab.PTABClient",
            _client_factory(client),
        ),
    ):
        results = await _search_external_ptab({}, "US-123-A1")

    assert results[0].result_id == "ptab:IPR2026-00001:1"
    assert results[0].patent_id == "US-123-A1"


@pytest.mark.asyncio
async def test_fda_regulatory_searches_map_patent_and_biologic_records() -> None:
    orange_index = SimpleNamespace(
        lookup=MagicMock(
            return_value=[
                SimpleNamespace(
                    patent_number="US-123-A1",
                    nda_number="NDA-1",
                    product_name="Aspirin",
                    active_ingredient="aspirin",
                    patent_expiry="2030-01-01",
                    patent_use_code="U-1",
                )
            ]
        )
    )
    purple_index = SimpleNamespace(
        lookup_biologic=MagicMock(
            return_value={
                "product_name": "Example biologic",
                "bla_number": "BLA-1",
                "proper_name": "examplemab",
                "applicant": "Example Pharma",
                "marketing_status": "active",
                "biosimilar_count": 2,
            }
        )
    )

    with (
        patch(
            "api.services.report_external_providers.query_patent_identifier",
            return_value="US-123-A1",
        ),
        patch(
            "praviar_pipeline.clients.orange_book.load_orange_book",
            new=AsyncMock(return_value=orange_index),
        ),
    ):
        orange_results = await _search_external_orange_book({}, "US-123-A1")
    with patch(
        "praviar_pipeline.clients.purple_book.load_purple_book",
        new=AsyncMock(return_value=purple_index),
    ):
        purple_results = await _search_external_purple_book({}, "examplemab")

    assert orange_results[0].result_id == "orange_book:US-123-A1:NDA-1"
    assert orange_results[0].patent_id == "US-123-A1"
    assert purple_results[0].result_id == "purple_book:BLA-1"
    assert purple_results[0].title == "Example biologic"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"patentFileWrapperDataBag": [{"id": 1}, "invalid"]}, [{"id": 1}]),
        ({"results": [{"id": 2}]}, [{"id": 2}]),
        ({"hits": [{"id": 3}]}, [{"id": 3}]),
        ({"hits": "not-a-list"}, []),
    ],
)
def test_extract_uspto_search_rows_accepts_known_response_envelopes(payload, expected) -> None:
    assert _extract_uspto_search_rows(payload) == expected


@pytest.mark.asyncio
async def test_execute_external_provider_records_success_and_explicit_zero_results() -> None:
    results, receipt, notice = await _execute_external_provider(
        "pubchem",
        provider_id="pubchem",
        runner=AsyncMock(return_value=[]),
    )

    assert results == []
    assert receipt.status == "succeeded"
    assert receipt.result_count == 0
    assert receipt.explicit_zero_results is True
    assert receipt.error_type == ""
    assert notice is None


@pytest.mark.asyncio
async def test_execute_external_provider_surfaces_sanitised_licensed_provider_failure() -> None:
    async def fail():
        raise RuntimeError("secret upstream detail")

    results, receipt, notice = await _execute_external_provider(
        "licensed_family_overlay",
        provider_id="licensed-family",
        runner=fail,
    )

    assert results == []
    assert receipt.status == "failed"
    assert receipt.error_type == "RuntimeError"
    assert receipt.explicit_zero_results is False
    assert notice is not None
    assert notice.notice_type == "execution_failure"
    assert "secret upstream detail" not in notice.message
    assert "provider access, quota, or upstream contract status" in notice.message
    assert "network down" in _provider_error_message("pubchem", RuntimeError("network down"))


@pytest.mark.asyncio
async def test_licensed_family_overlay_maps_governed_rows_and_context() -> None:
    overlay = AsyncMock(
        return_value=[
            {
                "family_id": "FAM-1",
                "publication_number": "US-123-A1",
                "title": "Aspirin family",
                "legal_status_summary": "Pending family members in the US.",
                "jurisdictions": ["US", "EP"],
                "legal_status": "pending",
                "owners": ["Example Pharma"],
                "relevance": 0.91,
            }
        ]
    )
    context = _context()

    results = await _search_external_licensed_family_overlay(
        {},
        "aspirin",
        context=context,
        licensed_family_overlay_fn=overlay,
    )

    assert len(results) == 1
    assert results[0].result_id == "licensed_family_overlay:FAM-1"
    assert results[0].patent_id == "US-123-A1"
    assert results[0].source_name == "licensed_family_overlay"
    overlay.assert_awaited_once()
    request = overlay.await_args.args[0]
    assert request["query"] == "aspirin"
    assert request["org_id"] == context.org_id
    assert request["compound_cid"] == 2244


@pytest.mark.asyncio
async def test_search_external_evidence_deduplicates_results_and_exposes_failures() -> None:
    context = _context()
    capability = EvidenceSearchProviderCapabilityResponse(
        provider_id="pubchem",
        provider_name="pubchem",
        provider_class="public_open",
        provider_status="active",
        live_retrieval_supported=True,
        configured=True,
        configured_for_org=True,
        execution_mode="live_api",
    )
    pubchem_results = [_result("same", 0.98), _result("same", 0.4)]

    with (
        patch(
            "api.services.report_external_providers.build_external_query_context",
            return_value=context,
        ),
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "build_external_provider_capabilities",
            return_value=[capability],
        ),
        patch(
            "api.services.report_external_providers.merge_provider_capabilities",
            return_value=[capability],
        ),
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "active_external_provider_specs",
            return_value=[_spec("pubchem"), _spec("future_provider", "future")],
        ),
        patch(
            "api.services.report_external_providers._search_external_pubchem",
            new=AsyncMock(return_value=pubchem_results),
        ) as pubchem,
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "build_external_caution_notes",
            return_value=["Jurisdiction routing caution."],
        ),
        patch(
            "api.services.report_external_providers.has_active_hybrid_layer",
            return_value=True,
        ),
    ):
        payload = await search_external_evidence_impl({}, "  aspirin  ")

    assert payload["query"] == "aspirin"
    assert payload["total"] == 1
    assert [item["result_id"] for item in payload["results"]] == ["same"]
    assert payload["results"][0]["relevance"] == 0.98
    assert payload["scope"]["external_live_retrieval"] is True
    assert payload["scope"]["hybrid_evidence_ready"] is True
    assert {item["status"] for item in payload["provider_executions"]} == {
        "succeeded",
        "failed",
    }
    assert {item["notice_type"] for item in payload["provider_notices"]} == {
        "missing_handler",
        "routing_policy",
    }
    pubchem.assert_awaited_once_with({}, "aspirin")


@pytest.mark.asyncio
async def test_search_external_evidence_explains_when_no_live_provider_is_routed() -> None:
    context = _context(specialist=True)

    with (
        patch(
            "api.services.report_external_providers.build_external_query_context",
            return_value=context,
        ),
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "build_external_provider_capabilities",
            return_value=[],
        ),
        patch(
            "api.services.report_external_providers.merge_provider_capabilities",
            return_value=[],
        ),
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "active_external_provider_specs",
            return_value=[],
        ),
        patch(
            "api.services.report_external_providers.report_external_evidence."
            "build_external_caution_notes",
            return_value=[],
        ),
        patch(
            "api.services.report_external_providers.has_active_hybrid_layer",
            return_value=False,
        ),
    ):
        payload = await search_external_evidence_impl({}, "antibody")

    assert payload["provider_executions"] == []
    assert payload["scope"]["external_live_retrieval"] is False
    note = payload["scope"]["governed_note"]
    assert "supervised screening mode" in note
    assert "No live provider is currently active" in note
