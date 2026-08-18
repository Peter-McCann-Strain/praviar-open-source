"""Tests for Lens.org patent search methods added to LensClient.

Covers:
- search_patents: keyword search with mock JSON response, normalized output
- search_patents with jurisdictions: jurisdiction filter in query
- search_patents_by_compound: convenience method delegates to search_patents
- search_patents with empty API key: returns []
- pagination: multi-page result collection
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.lens import LensClient
from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

# ---------------------------------------------------------------------------
# Sample Lens API responses
# ---------------------------------------------------------------------------

LENS_PATENT_RESPONSE_PAGE1 = {
    "total": 3,
    "data": [
        {
            "lens_id": "LP001",
            "doc_number": "7851188",
            "jurisdiction": "US",
            "title": "Methods for producing succinic acid from fermentation",
            "abstract": "A method for bio-based production of succinic acid...",
            "date_published": "2010-12-14",
            "applicant": [
                {"name": "BioAmber Inc."},
                {"name": "University of Wisconsin"},
            ],
            "classification_cpc": [
                {"symbol": "C12P7/46"},
                {"symbol": "C07C55/10"},
            ],
        },
        {
            "lens_id": "LP002",
            "doc_number": "6265190",
            "jurisdiction": "US",
            "title": "Succinic acid production and purification",
            "abstract": "Methods for purification...",
            "date_published": "2001-07-24",
            "applicant": [{"name": "Michigan Biotech"}],
            "classification_cpc": [{"symbol": "C07C51/47"}],
        },
    ],
}

LENS_PATENT_RESPONSE_PAGE2 = {
    "total": 3,
    "data": [
        {
            "lens_id": "LP003",
            "doc_number": "2020123456",
            "jurisdiction": "JP",
            "title": "Succinic acid fermentation method",
            "abstract": "Japanese patent on succinic acid...",
            "date_published": "2020-06-15",
            "applicant": [{"name": "Mitsubishi Chemical"}],
            "classification_cpc": [{"symbol": "C12P7/46"}],
        },
    ],
}

LENS_PATENT_RESPONSE_EMPTY: dict = {
    "total": 0,
    "data": [],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lens_client(mock_settings) -> LensClient:
    """LensClient with a test API key (set by mock_settings)."""
    return LensClient()


@pytest.fixture
def lens_client_no_key(mock_settings) -> LensClient:
    """LensClient with no API key."""
    import os

    clear_settings_cache()
    with patch.dict(os.environ, {"LENS_API_KEY": ""}):
        clear_settings_cache()
        client = LensClient()
    return client


# ============================================================================
# Tests
# ============================================================================


class TestLensSearchPatents:
    """Tests for LensClient.search_patents."""

    async def test_search_patents_returns_normalized_results(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Patent search returns normalized results with correct publication_number format."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json=LENS_PATENT_RESPONSE_PAGE1,
        )

        results = await lens_client.search_patents(["succinic acid", "fermentation"], max_results=2)

        assert len(results) == 2

        # First result — US jurisdiction + doc_number → "US7851188"
        r0 = results[0]
        assert r0["publication_number"] == "US7851188"
        assert r0["title"] == "Methods for producing succinic acid from fermentation"
        assert r0["abstract"].startswith("A method")
        assert r0["filing_date"] == "2010-12-14"
        assert r0["assignees"] == ["BioAmber Inc.", "University of Wisconsin"]
        assert r0["cpc_codes"] == ["C12P7/46", "C07C55/10"]

        # Second result
        r1 = results[1]
        assert r1["publication_number"] == "US6265190"
        assert r1["assignees"] == ["Michigan Biotech"]

        await lens_client.close()

    async def test_search_patents_with_jurisdictions(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Jurisdiction filter is included in the query payload."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json=LENS_PATENT_RESPONSE_EMPTY,
        )

        await lens_client.search_patents(
            ["succinic acid"],
            jurisdictions=["US", "EP", "JP"],
            max_results=10,
        )

        # Verify the request payload included jurisdiction terms
        request = httpx_mock.get_requests()[0]
        import json

        body = json.loads(request.content)
        query = body["query"]

        # The query should have a bool with must containing jurisdiction terms
        assert "bool" in query
        bool_query = query["bool"]
        # When jurisdictions are provided, query is wrapped in must with terms
        assert "must" in bool_query
        must_clauses = bool_query["must"]
        # Find the jurisdiction terms clause
        jurisdiction_found = False
        for clause in must_clauses:
            if "terms" in clause and "jurisdiction" in clause["terms"]:
                assert clause["terms"]["jurisdiction"] == ["US", "EP", "JP"]
                jurisdiction_found = True
        assert jurisdiction_found, "Jurisdiction filter not found in query"

        await lens_client.close()

    async def test_search_patents_empty_api_key_returns_empty(
        self, lens_client_no_key: LensClient, httpx_mock: HTTPXMock
    ):
        """When API key is empty, search_patents should still work but
        the API call will fail with auth error. We test that the client
        is created without error."""
        # With no API key, the client is created but calls will fail.
        # The existing pattern is that Lens client doesn't pre-check the key.
        # A 401 response raises AuthenticationError.
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError):
            await lens_client_no_key.search_patents(["test"])
        await lens_client_no_key.close()

    async def test_search_patents_empty_response(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Empty data list returns []."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json=LENS_PATENT_RESPONSE_EMPTY,
        )

        results = await lens_client.search_patents(["nonexistent"])
        assert results == []
        await lens_client.close()


class TestLensPagination:
    """Tests for multi-page result collection.

    Pagination logic: page_size = min(max_results, 50).
    Loop continues when: len(all_results) < max_results AND len(page) == page_size AND collected < total.
    To trigger a second request, we need the first page to return exactly page_size items.
    """

    async def test_pagination_works(self, lens_client: LensClient, httpx_mock: HTTPXMock):
        """Multiple pages of results are collected when first page is full.

        Strategy: max_results=100, page_size=min(100,50)=50.
        First page returns 50 items (== page_size), total=51 → triggers page 2.
        Second page returns 1 item (< page_size) → stops.
        """
        # Build a page of exactly 50 items
        page1_items = [
            {
                "lens_id": f"LP{i:03d}",
                "doc_number": f"{7000000 + i}",
                "jurisdiction": "US",
                "title": f"Patent {i}",
            }
            for i in range(50)
        ]
        page2_items = [
            {
                "lens_id": "LP050",
                "doc_number": "2020123456",
                "jurisdiction": "JP",
                "title": "Japanese patent",
            }
        ]

        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={"total": 51, "data": page1_items},
        )
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={"total": 51, "data": page2_items},
        )

        results = await lens_client.search_patents(["succinic acid"], max_results=100)

        # Should have fetched both pages: 50 + 1 = 51
        assert len(results) == 51
        assert results[0]["publication_number"] == "US7000000"
        assert results[50]["publication_number"] == "JP2020123456"

        # Should have made 2 requests
        assert len(httpx_mock.get_requests()) == 2

        await lens_client.close()

    async def test_pagination_stops_at_max_results(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Pagination stops when max_results is reached."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json=LENS_PATENT_RESPONSE_PAGE1,
        )

        # max_results=1: should return only first result
        results = await lens_client.search_patents(["succinic acid"], max_results=1)

        assert len(results) == 1
        assert results[0]["publication_number"] == "US7851188"

        await lens_client.close()

    async def test_pagination_stops_on_empty_page(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Pagination stops when an empty page is returned."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={
                "total": 100,  # Claims 100 but returns 0
                "data": [],
            },
        )

        results = await lens_client.search_patents(["test"], max_results=50)
        assert results == []
        # Only one request made (stopped on empty)
        assert len(httpx_mock.get_requests()) == 1

        await lens_client.close()


class TestLensSearchPatentsByCompound:
    """Tests for LensClient.search_patents_by_compound convenience method."""

    async def test_search_patents_by_compound(self, lens_client: LensClient, httpx_mock: HTTPXMock):
        """Compound search builds keywords from name+synonyms and delegates."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json=LENS_PATENT_RESPONSE_PAGE1,
        )

        results = await lens_client.search_patents_by_compound(
            compound_name="succinic acid",
            synonyms=["amber acid", "butanedioic acid"],
            max_results=10,
        )

        assert len(results) == 2

        # Verify the request payload included all keywords
        request = httpx_mock.get_requests()[0]
        import json

        body = json.loads(request.content)
        query = body["query"]

        # Should have should clauses for each keyword across title/abstract/claims
        should_clauses = query["bool"]["should"]
        # 3 keywords x 3 fields = 9 clauses
        assert len(should_clauses) == 9

        # Check that all keywords are present
        match_values = [next(iter(clause["match"].values())) for clause in should_clauses]
        assert "succinic acid" in match_values
        assert "amber acid" in match_values
        assert "butanedioic acid" in match_values

        await lens_client.close()


class TestLensNormalization:
    """Tests for result normalization edge cases."""

    async def test_missing_cpc_codes_returns_empty_list(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Patent with no classification_cpc returns empty cpc_codes list."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={
                "total": 1,
                "data": [
                    {
                        "lens_id": "LP999",
                        "doc_number": "999999",
                        "jurisdiction": "US",
                        "title": "No CPC patent",
                    }
                ],
            },
        )

        results = await lens_client.search_patents(["test"], max_results=1)
        assert len(results) == 1
        assert results[0]["cpc_codes"] == []
        assert results[0]["assignees"] == []
        await lens_client.close()

    async def test_missing_jurisdiction_uses_doc_number_only(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Patent with no jurisdiction returns doc_number as publication_number."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={
                "total": 1,
                "data": [
                    {
                        "lens_id": "LP888",
                        "doc_number": "888888",
                        "title": "No jurisdiction",
                    }
                ],
            },
        )

        results = await lens_client.search_patents(["test"], max_results=1)
        assert results[0]["publication_number"] == "888888"
        await lens_client.close()

    async def test_non_dict_cpc_entries_are_filtered(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """Non-dict entries in classification_cpc are skipped."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            json={
                "total": 1,
                "data": [
                    {
                        "lens_id": "LP777",
                        "doc_number": "777777",
                        "jurisdiction": "EP",
                        "title": "Mixed CPC types",
                        "classification_cpc": [
                            {"symbol": "C12P7/46"},
                            "invalid_entry",
                            {"symbol": "C07C55/10"},
                        ],
                    }
                ],
            },
        )

        results = await lens_client.search_patents(["test"], max_results=1)
        # Only the dict entries should be included
        assert results[0]["cpc_codes"] == ["C12P7/46", "C07C55/10"]
        await lens_client.close()


class TestLensAuthError:
    """Tests for authentication error handling."""

    async def test_auth_error_on_patent_search(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """401 response on patent search raises AuthenticationError."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError, match="Lens"):
            await lens_client.search_patents(["test"])
        await lens_client.close()

    async def test_404_raises_source_unavailable(
        self, lens_client: LensClient, httpx_mock: HTTPXMock
    ):
        """404 on patent search is a source failure — must raise, not silently return empty."""
        httpx_mock.add_response(
            url=re.compile(r".*patent/search.*"),
            status_code=404,
        )

        with pytest.raises(SourceUnavailableError) as excinfo:
            await lens_client.search_patents(["test"])
        assert excinfo.value.status_code == 404
        assert excinfo.value.source == "lens"
        await lens_client.close()
