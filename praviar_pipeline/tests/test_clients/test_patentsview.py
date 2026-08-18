"""Tests for the USPTO ODP client (replacement for decommissioned PatentsView)."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.patentsview import PatentsViewClient
from praviar_pipeline.clients.patentsview_queries import (
    build_assignee_search_query,
    build_compound_keyword_query,
    build_cpc_search_query,
    build_patent_query,
)
from praviar_pipeline.clients.patentsview_requests import (
    build_claims_request_params,
    build_search_request_params,
)
from praviar_pipeline.clients.patentsview_results import (
    extract_first_patent,
    extract_patent_citations,
    extract_patents,
    format_claims_text,
)
from praviar_pipeline.errors import ConfigurationError

_ODP_RECORD = {
    "applicationNumberText": "18951096",
    "applicationMetaData": {
        "patentNumber": "12274767",
        "inventionTitle": "Lip Balm Containing Caffeine",
        "grantDate": "2025-04-15",
        "filingDate": "2024-11-18",
        "effectiveFilingDate": "2024-11-18",
        "cpcClassificationBag": ["A61K   8/0216", "A61K   8/4926"],
        "applicationStatusCode": 150,
        "applicationStatusDescriptionText": "Patented Case",
        "applicantBag": [{"applicantNameText": "Test Corp"}],
    },
    "assignmentBag": [
        {
            "assigneeBag": [{"assigneeNameText": "TEST CORP"}],
        }
    ],
}


@pytest.fixture
def patentsview_client(mock_settings) -> PatentsViewClient:
    return PatentsViewClient()


class TestUSPTOODPRequestBuilders:
    def test_build_search_request_params_structure(self) -> None:
        body = build_search_request_params("applicationMetaData.inventionTitle:caffeine", size=200)
        assert body["q"] == "applicationMetaData.inventionTitle:caffeine"
        assert body["pagination"]["limit"] == 200
        assert body["pagination"]["offset"] == 0

    def test_build_search_request_params_caps_limit(self) -> None:
        body = build_search_request_params("q:x", size=2000)
        assert body["pagination"]["limit"] == 500

    def test_build_claims_request_params_extracts_number(self) -> None:
        body = build_claims_request_params("US7851188B2")
        assert "applicationMetaData.patentNumber:7851188" in body["q"]
        assert body["pagination"]["limit"] == 1


class TestUSPTOODPQueryBuilders:
    def test_build_cpc_search_query_no_keywords(self) -> None:
        q = build_cpc_search_query("A61K")
        assert "applicationMetaData.cpcClassificationBag:A61K" in q
        assert "AND" not in q

    def test_build_cpc_search_query_with_keywords(self) -> None:
        q = build_cpc_search_query("A61K", ["succinic", "acid"])
        assert "applicationMetaData.cpcClassificationBag:A61K" in q
        assert 'applicationMetaData.inventionTitle:"succinic"' in q
        assert "AND" in q

    def test_build_assignee_search_query(self) -> None:
        q = build_assignee_search_query("Acme Corp")
        assert 'assignmentBag.assigneeBag.assigneeNameText:"Acme Corp"' in q

    def test_build_patent_query_strips_prefix_and_kind(self) -> None:
        q = build_patent_query("US7851188B2")
        assert q == "applicationMetaData.patentNumber:7851188"

    def test_build_compound_keyword_query_includes_synonyms(self) -> None:
        q = build_compound_keyword_query("caffeine", ["theine"], cpc_prefix="A61K")
        assert "applicationMetaData.cpcClassificationBag:A61K" in q
        assert 'applicationMetaData.inventionTitle:"caffeine"' in q
        assert 'applicationMetaData.inventionTitle:"theine"' in q

    def test_build_compound_keyword_query_limits_synonyms(self) -> None:
        synonyms = [f"syn{i}" for i in range(20)]
        q = build_compound_keyword_query("base", synonyms, cpc_prefix="A61K")
        # compound_name + 9 synonyms = 10 terms max
        assert q.count("inventionTitle") <= 10


class TestUSPTOODPResultHelpers:
    def test_extract_patents_returns_normalised_records(self) -> None:
        data = {"patentFileWrapperDataBag": [_ODP_RECORD]}
        results = extract_patents(data)
        assert len(results) == 1
        rec = results[0]
        assert rec["patent_id"] == "US12274767B2"
        assert rec["patent_kind"] == "B2"
        assert rec["patent_title"] == "Lip Balm Containing Caffeine"
        assert rec["patent_date"] == "2025-04-15"
        assert rec["assignee_organization"] == "Test Corp"
        assert "A61K 8/0216" in rec["cpc_subgroup_ids"]

    def test_extract_patents_pending_application_uses_pub_number(self) -> None:
        rec = {
            "applicationNumberText": "19123456",
            "applicationMetaData": {
                "patentNumber": None,
                "inventionTitle": "Pending Patent",
                "earliestPublicationNumber": "US20250073133A1",
                "grantDate": None,
                "effectiveFilingDate": "2025-01-01",
                "cpcClassificationBag": [],
                "applicantBag": [],
            },
            "assignmentBag": [],
        }
        results = extract_patents({"patentFileWrapperDataBag": [rec]})
        assert results[0]["patent_id"] == "US20250073133A1"
        assert results[0]["patent_kind"] == "A1"

    def test_extract_patents_empty_response(self) -> None:
        assert extract_patents({}) == []
        assert extract_patents(None) == []

    def test_extract_first_patent(self) -> None:
        patents = [{"patent_id": "US1"}, {"patent_id": "US2"}]
        assert extract_first_patent(patents) == {"patent_id": "US1"}
        assert extract_first_patent([]) == {}

    def test_extract_patent_citations_returns_empty(self) -> None:
        # ODP file wrapper endpoint does not expose citation networks
        assert (
            extract_patent_citations([{"us_patent_citations": [{"citation_patent_id": "US2"}]}])
            == []
        )

    def test_format_claims_text_sorts_by_number(self) -> None:
        claims = [
            {"claim_number": 2, "claim_text": "second"},
            {"claim_number": 1, "claim_text": "first"},
        ]
        assert format_claims_text(claims) == "1. first\n\n2. second"

    def test_cpc_whitespace_normalised(self) -> None:
        data = {
            "patentFileWrapperDataBag": [
                {
                    "applicationNumberText": "123",
                    "applicationMetaData": {
                        "patentNumber": "9999999",
                        "inventionTitle": "Test",
                        "grantDate": "2024-01-01",
                        "effectiveFilingDate": "2023-01-01",
                        "cpcClassificationBag": ["A61K   31/522"],
                        "applicantBag": [],
                    },
                    "assignmentBag": [],
                }
            ]
        }
        results = extract_patents(data)
        assert "A61K 31/522" in results[0]["cpc_subgroup_ids"]


class TestPatentsViewClient:
    async def test_search_patents_posts_to_odp_endpoint(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 1, "patentFileWrapperDataBag": [_ODP_RECORD]},
        )

        results = await patentsview_client.search_patents(
            "applicationMetaData.inventionTitle:caffeine"
        )
        assert len(results) == 1
        assert results[0]["patent_id"] == "US12274767B2"

        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert "/patent/applications/search" in str(request.url)

        await patentsview_client.close()

    async def test_get_patent_citations_returns_empty(
        self,
        patentsview_client: PatentsViewClient,
    ) -> None:
        citations = await patentsview_client.get_patent_citations("US7851188B2")
        assert citations == []

    async def test_missing_key_raises_configuration_error(self) -> None:
        with patch(
            "praviar_pipeline.clients.patentsview.get_settings",
            return_value=SimpleNamespace(
                patentsview_api_key="",
                uspto_odp_api_key="",
                http_timeout_default=30,
                http_connect_timeout=5,
                http_max_connections=10,
                http_max_keepalive=5,
                patentsview_requests_per_minute=1000,
            ),
        ):
            client = PatentsViewClient()
            with pytest.raises(ConfigurationError):
                await client.search_patents("applicationMetaData.inventionTitle:caffeine")
            await client.close()

    async def test_429_retries_and_succeeds(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            status_code=429,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 1, "patentFileWrapperDataBag": [_ODP_RECORD]},
        )

        results = await patentsview_client.search_patents(
            "applicationMetaData.inventionTitle:caffeine"
        )
        assert len(results) == 1
        assert results[0]["patent_id"] == "US12274767B2"
        assert len(httpx_mock.get_requests()) == 2
        await patentsview_client.close()

    async def test_search_by_cpc_uses_correct_lucene_query(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 1, "patentFileWrapperDataBag": [_ODP_RECORD]},
        )

        results = await patentsview_client.search_by_cpc("A61K", keywords=["caffeine"])
        assert len(results) == 1

        import json

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert "applicationMetaData.cpcClassificationBag:A61K" in body["q"]
        assert 'applicationMetaData.inventionTitle:"caffeine"' in body["q"]
        await patentsview_client.close()

    async def test_search_by_assignee_uses_correct_lucene_query(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 1, "patentFileWrapperDataBag": [_ODP_RECORD]},
        )

        results = await patentsview_client.search_by_assignee("Test Corp")
        assert len(results) == 1

        import json

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert 'assignmentBag.assigneeBag.assigneeNameText:"Test Corp"' in body["q"]
        await patentsview_client.close()

    async def test_get_patent_single_lookup_ok_on_404(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 1, "patentFileWrapperDataBag": [_ODP_RECORD]},
        )

        result = await patentsview_client.get_patent("US12274767B2")
        assert result["patent_id"] == "US12274767B2"

        import json

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert "applicationMetaData.patentNumber:12274767" in body["q"]
        assert body["pagination"]["limit"] == 1
        await patentsview_client.close()

    async def test_get_patent_returns_empty_on_404(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            status_code=404,
        )

        result = await patentsview_client.get_patent("US99999999B2")
        assert result == {}
        await patentsview_client.close()

    async def test_api_key_sent_in_header(
        self,
        patentsview_client: PatentsViewClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(
            url=re.compile(r".*/patent/applications/search"),
            json={"count": 0, "patentFileWrapperDataBag": []},
        )

        await patentsview_client.search_patents("applicationMetaData.inventionTitle:caffeine")

        request = httpx_mock.get_requests()[0]
        assert "X-API-KEY" in request.headers
        assert request.headers["X-API-KEY"] == "test-odp-key"
        await patentsview_client.close()
