"""Tests for the WIPO PatentScope REST API client.

Covers:
- search_patents: keyword search with mock JSON response
- search_patents with empty credentials: returns []
- cross_lingual_search: CLIR search with target languages
- search_by_applicant: applicant search with jurisdiction filter
- Authentication error (401) raises AuthenticationError
- Query building with jurisdictions
- Result parsing with various applicant/CPC formats
"""

from __future__ import annotations

import base64
import re

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.patentscope import PatentScopeClient
from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

# ---------------------------------------------------------------------------
# Sample JSON responses
# ---------------------------------------------------------------------------

PATENTSCOPE_SEARCH_RESPONSE = {
    "response": {
        "numFound": 2,
        "docs": [
            {
                "publicationNumber": "WO2020123456",
                "title": "Method for producing succinic acid",
                "abstract": "A method for bio-based production of succinic acid...",
                "filingDate": "2020-01-15",
                "priorityDate": "2019-06-20",
                "applicants": "BASF SE;Evonik Industries",
                "cpcCodes": "C12P7/46;C07C55/10",
            },
            {
                "publicationNumber": "WO2021098765",
                "title": "Purification process for dicarboxylic acids",
                "abstract": "An improved purification method...",
                "filingDate": "2021-03-10",
                "priorityDate": "2020-09-15",
                "applicants": ["Myriant Technologies"],
                "cpcCodes": ["C07C51/47"],
            },
        ],
    },
}

PATENTSCOPE_CLIR_RESPONSE = {
    "response": {
        "numFound": 1,
        "docs": [
            {
                "publicationNumber": "JP2020567890",
                "title": "Succinic acid fermentation method",
                "abstract": "Translated abstract...",
                "filingDate": "2020-05-01",
                "priorityDate": "2019-11-01",
                "applicants": "Mitsubishi Chemical",
                "cpcCodes": "C12P7/46",
            },
        ],
    },
}

PATENTSCOPE_EMPTY_RESPONSE: dict = {
    "response": {
        "numFound": 0,
        "docs": [],
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patentscope_client(mock_settings) -> PatentScopeClient:
    """Create a PatentScopeClient with test credentials via env override."""
    import os
    from unittest.mock import patch

    extra_env = {
        "PATENTSCOPE_USERNAME": "test-user",
        "PATENTSCOPE_PASSWORD": "test-pass",
    }

    clear_settings_cache()
    with patch.dict(os.environ, extra_env):
        clear_settings_cache()
        client = PatentScopeClient()
    return client


@pytest.fixture
def patentscope_client_no_creds(mock_settings) -> PatentScopeClient:
    """Create a PatentScopeClient with no credentials."""
    import os
    from unittest.mock import patch

    extra_env = {
        "PATENTSCOPE_USERNAME": "",
        "PATENTSCOPE_PASSWORD": "",
    }

    clear_settings_cache()
    with patch.dict(os.environ, extra_env):
        clear_settings_cache()
        client = PatentScopeClient()
    return client


# ============================================================================
# Tests
# ============================================================================


class TestPatentScopeSearchPatents:
    """Tests for PatentScopeClient.search_patents."""

    async def test_search_patents_returns_results(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """Keyword search parses JSON and returns normalized results."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=PATENTSCOPE_SEARCH_RESPONSE,
        )

        results = await patentscope_client.search_patents(["succinic acid", "fermentation"])

        assert len(results) == 2

        # First result — semicolon-separated applicants and CPC codes
        r0 = results[0]
        assert r0["publication_number"] == "WO2020123456"
        assert r0["title"] == "Method for producing succinic acid"
        assert r0["abstract"].startswith("A method")
        assert r0["filing_date"] == "2020-01-15"
        assert r0["priority_date"] == "2019-06-20"
        assert r0["assignees"] == ["BASF SE", "Evonik Industries"]
        assert r0["cpc_codes"] == ["C12P7/46", "C07C55/10"]

        # Second result — list-format applicants and CPC codes
        r1 = results[1]
        assert r1["publication_number"] == "WO2021098765"
        assert r1["assignees"] == ["Myriant Technologies"]
        assert r1["cpc_codes"] == ["C07C51/47"]

        await patentscope_client.close()

    async def test_search_patents_empty_credentials_returns_empty(
        self, patentscope_client_no_creds: PatentScopeClient
    ):
        """When credentials are missing, search returns [] without making requests."""
        results = await patentscope_client_no_creds.search_patents(["succinic acid"])
        assert results == []
        await patentscope_client_no_creds.close()

    async def test_search_patents_empty_keywords_returns_empty(
        self, patentscope_client: PatentScopeClient
    ):
        """Empty keyword list returns [] without making request."""
        results = await patentscope_client.search_patents([])
        assert results == []
        await patentscope_client.close()

    async def test_search_patents_empty_response(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """Empty docs list returns []."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=PATENTSCOPE_EMPTY_RESPONSE,
        )

        results = await patentscope_client.search_patents(["nonexistent"])
        assert results == []
        await patentscope_client.close()


class TestPatentScopeCrossLingualSearch:
    """Tests for PatentScopeClient.cross_lingual_search."""

    async def test_cross_lingual_search(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """CLIR search includes clir params and parses results correctly."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=PATENTSCOPE_CLIR_RESPONSE,
        )

        results = await patentscope_client.cross_lingual_search(
            keywords=["succinic acid"],
            source_lang="EN",
            target_langs=["JA", "KO", "ZH"],
        )

        assert len(results) == 1
        r = results[0]
        assert r["publication_number"] == "JP2020567890"
        assert r["title"] == "Succinic acid fermentation method"
        # Semicolon-separated string applicant → list
        assert r["assignees"] == ["Mitsubishi Chemical"]
        assert r["cpc_codes"] == ["C12P7/46"]

        # Verify CLIR params were sent in request
        request = httpx_mock.get_requests()[0]
        url_str = str(request.url)
        assert "clir=true" in url_str or "clir" in url_str

        await patentscope_client.close()

    async def test_cross_lingual_search_no_creds_returns_empty(
        self, patentscope_client_no_creds: PatentScopeClient
    ):
        """CLIR search returns [] when no credentials configured."""
        results = await patentscope_client_no_creds.cross_lingual_search(
            keywords=["succinic acid"],
            target_langs=["JA"],
        )
        assert results == []
        await patentscope_client_no_creds.close()

    async def test_cross_lingual_search_empty_keywords_returns_empty(
        self, patentscope_client: PatentScopeClient
    ):
        """CLIR search with no keywords returns [] immediately."""
        results = await patentscope_client.cross_lingual_search(keywords=[])
        assert results == []
        await patentscope_client.close()


class TestPatentScopeSearchByApplicant:
    """Tests for PatentScopeClient.search_by_applicant."""

    async def test_search_by_applicant(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """Applicant search returns parsed results."""
        response = {
            "response": {
                "numFound": 1,
                "docs": [
                    {
                        "publicationNumber": "WO2019111222",
                        "title": "BASF bio-acid patent",
                        "abstract": "An advanced process...",
                        "filingDate": "2019-02-01",
                        "priorityDate": "2018-08-01",
                        "applicants": "BASF SE",
                        "cpcCodes": "C12P7/46",
                    },
                ],
            },
        }
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=response,
        )

        results = await patentscope_client.search_by_applicant("BASF SE")

        assert len(results) == 1
        assert results[0]["publication_number"] == "WO2019111222"
        assert results[0]["assignees"] == ["BASF SE"]

        # Verify pa: query qualifier was used
        request = httpx_mock.get_requests()[0]
        url_str = str(request.url)
        assert "pa%3A" in url_str or 'pa:"BASF' in url_str or "pa:" in url_str

        await patentscope_client.close()

    async def test_search_by_applicant_with_jurisdictions(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """Applicant search with jurisdictions includes dp: filter."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=PATENTSCOPE_EMPTY_RESPONSE,
        )

        await patentscope_client.search_by_applicant("BASF SE", jurisdictions=["US", "EP"])

        request = httpx_mock.get_requests()[0]
        url_str = str(request.url)
        # The query should contain dp: filter for jurisdictions
        assert "dp" in url_str

        await patentscope_client.close()

    async def test_search_by_applicant_no_creds_returns_empty(
        self, patentscope_client_no_creds: PatentScopeClient
    ):
        """Applicant search returns [] when no credentials configured."""
        results = await patentscope_client_no_creds.search_by_applicant("BASF SE")
        assert results == []
        await patentscope_client_no_creds.close()

    async def test_search_by_applicant_empty_string_returns_empty(
        self, patentscope_client: PatentScopeClient
    ):
        """Applicant search with empty string returns []."""
        results = await patentscope_client.search_by_applicant("")
        assert results == []
        await patentscope_client.close()


class TestPatentScopeAuthError:
    """Tests for authentication error handling."""

    async def test_auth_error_raises(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """401 response should raise AuthenticationError."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            status_code=401,
            text="Unauthorized",
        )

        with pytest.raises(AuthenticationError, match="PatentScope"):
            await patentscope_client.search_patents(["test"])
        await patentscope_client.close()

    async def test_403_also_raises_auth_error(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """403 (forbidden) should also raise AuthenticationError."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            status_code=403,
            text="Forbidden",
        )

        with pytest.raises(AuthenticationError, match="PatentScope"):
            await patentscope_client.search_patents(["test"])
        await patentscope_client.close()

    async def test_404_returns_empty_dict(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """404 response returns empty dict (no results), not an error."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            status_code=404,
        )

        results = await patentscope_client.search_patents(["test"])
        assert results == []
        await patentscope_client.close()

    async def test_500_raises_source_unavailable(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """500 response raises SourceUnavailableError."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            status_code=500,
            text="Internal Server Error",
        )

        with pytest.raises(SourceUnavailableError):
            await patentscope_client.search_patents(["test"])
        await patentscope_client.close()

    async def test_basic_auth_header_present(
        self, patentscope_client: PatentScopeClient, httpx_mock: HTTPXMock
    ):
        """Requests include a Basic Auth Authorization header with the configured credentials."""
        httpx_mock.add_response(
            url=re.compile(r".*patentscope.*"),
            json=PATENTSCOPE_EMPTY_RESPONSE,
        )

        await patentscope_client.search_patents(["test"])

        request = httpx_mock.get_requests()[0]
        auth_header = request.headers.get("authorization", "")
        assert auth_header.startswith("Basic ")
        decoded = base64.b64decode(auth_header[len("Basic ") :]).decode()
        assert decoded == "test-user:test-pass"
        await patentscope_client.close()


class TestPatentScopeQueryBuilding:
    """Tests for _build_keyword_query helper."""

    def test_query_without_jurisdictions(self, patentscope_client: PatentScopeClient):
        """Keywords joined with OR, no jurisdiction filter."""
        query = patentscope_client._build_keyword_query(["succinic acid", "amber acid"])
        assert '"succinic acid"' in query
        assert '"amber acid"' in query
        assert "OR" in query
        assert "dp:" not in query

    def test_query_with_jurisdictions(self, patentscope_client: PatentScopeClient):
        """Keywords with jurisdiction filter includes dp: clauses."""
        query = patentscope_client._build_keyword_query(
            ["succinic acid"], jurisdictions=["US", "EP"]
        )
        assert '"succinic acid"' in query
        assert "dp:US" in query
        assert "dp:EP" in query

    def test_query_empty_keywords(self, patentscope_client: PatentScopeClient):
        """Empty keywords returns empty string."""
        query = patentscope_client._build_keyword_query([])
        assert query == ""


class TestPatentScopeResultParsing:
    """Tests for _parse_results with various data formats."""

    def test_parse_string_applicants(self, patentscope_client: PatentScopeClient):
        """Semicolon-separated applicant string is split into list."""
        data = {
            "response": {
                "docs": [
                    {
                        "publicationNumber": "WO2020111222",
                        "applicants": "BASF SE;Evonik Industries;DuPont",
                    }
                ]
            }
        }
        results = patentscope_client._parse_results(data)
        assert results[0]["assignees"] == ["BASF SE", "Evonik Industries", "DuPont"]

    def test_parse_list_applicants(self, patentscope_client: PatentScopeClient):
        """List-format applicants are used directly."""
        data = {
            "response": {
                "docs": [
                    {
                        "publicationNumber": "WO2020111222",
                        "applicants": ["BASF SE"],
                    }
                ]
            }
        }
        results = patentscope_client._parse_results(data)
        assert results[0]["assignees"] == ["BASF SE"]

    def test_parse_skips_entries_without_pub_number(self, patentscope_client: PatentScopeClient):
        """Entries without publicationNumber are skipped."""
        data = {
            "response": {
                "docs": [
                    {"title": "No pub number"},
                    {"publicationNumber": "WO2020111222", "title": "Has pub number"},
                ]
            }
        }
        results = patentscope_client._parse_results(data)
        assert len(results) == 1
        assert results[0]["publication_number"] == "WO2020111222"

    def test_parse_results_top_level_format(self, patentscope_client: PatentScopeClient):
        """Results can also come in a top-level 'results' key."""
        data = {
            "results": [
                {
                    "publicationNumber": "WO2020111222",
                    "title": "Top level format",
                }
            ]
        }
        results = patentscope_client._parse_results(data)
        assert len(results) == 1
        assert results[0]["title"] == "Top level format"
