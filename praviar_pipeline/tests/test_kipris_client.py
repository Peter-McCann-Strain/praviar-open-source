"""Tests for the KIPRIS Plus (Korea) patent API client.

Covers:
- search_patents: keyword search with mock XML response
- search_patents with empty API key: returns []
- search_by_applicant: applicant search with mock XML response
- XML parsing with missing optional fields
- Authentication error (401) raises AuthenticationError
- 500 responses exhausting retries raise httpx.HTTPStatusError
- Transport errors (ConnectError) propagate
- ServiceKey query parameter is included in outgoing requests
"""

from __future__ import annotations

import re

import httpx
import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.kipris import KIPRISClient
from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

# ---------------------------------------------------------------------------
# Sample XML responses
# ---------------------------------------------------------------------------

KIPRIS_XML_FULL = """\
<response>
  <body>
    <items>
      <item>
        <applicationNumber>1020200012345</applicationNumber>
        <inventionTitle>Method for producing compound X</inventionTitle>
        <applicantName>Samsung Electronics</applicantName>
        <ipcNumber>C07D211/00</ipcNumber>
        <applicationDate>20200115</applicationDate>
        <openDate>20200715</openDate>
        <registerNumber>1022150012345</registerNumber>
        <registerDate>20210301</registerDate>
        <cpcNumber>C07D211/00|C12P7/46</cpcNumber>
        <astrtCont>A method for bio-based production of compound X using fermentation</astrtCont>
      </item>
      <item>
        <applicationNumber>1020210054321</applicationNumber>
        <inventionTitle>Purification of succinic acid</inventionTitle>
        <applicantName>LG Chem|SK Chemicals</applicantName>
        <applicationDate>20210310</applicationDate>
        <cpcNumber>C07C55/10</cpcNumber>
      </item>
    </items>
  </body>
</response>"""

KIPRIS_XML_MISSING_FIELDS = """\
<response>
  <body>
    <items>
      <item>
        <applicationNumber>1020220099999</applicationNumber>
      </item>
    </items>
  </body>
</response>"""

KIPRIS_XML_EMPTY = """\
<response>
  <body>
    <items/>
  </body>
</response>"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kipris_client(mock_settings) -> KIPRISClient:
    """Create a KIPRISClient with a test API key via mock_settings + env override."""
    import os
    from unittest.mock import patch

    extra_env = {"KIPRIS_API_KEY": "test-kipris-key"}

    clear_settings_cache()
    with patch.dict(os.environ, extra_env):
        clear_settings_cache()
        client = KIPRISClient()
    return client


@pytest.fixture
def kipris_client_no_key(mock_settings) -> KIPRISClient:
    """Create a KIPRISClient with no API key."""
    import os
    from unittest.mock import patch

    extra_env = {"KIPRIS_API_KEY": ""}

    clear_settings_cache()
    with patch.dict(os.environ, extra_env):
        clear_settings_cache()
        client = KIPRISClient()
    return client


# ============================================================================
# Tests
# ============================================================================


class TestKIPRISSearchPatents:
    """Tests for KIPRISClient.search_patents."""

    async def test_search_patents_returns_results(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """Keyword search parses KIPRIS XML and returns normalized results."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text=KIPRIS_XML_FULL,
        )

        results = await kipris_client.search_patents(["succinic acid", "fermentation"])

        assert len(results) == 2

        # First result — full fields
        r0 = results[0]
        assert r0["publication_number"] == "KR1020200012345"
        assert r0["title"] == "Method for producing compound X"
        assert (
            r0["abstract"] == "A method for bio-based production of compound X using fermentation"
        )
        assert r0["filing_date"] == "20200115"
        assert r0["assignees"] == ["Samsung Electronics"]
        assert r0["cpc_codes"] == ["C07D211/00", "C12P7/46"]

        # Second result — pipe-separated applicants
        r1 = results[1]
        assert r1["publication_number"] == "KR1020210054321"
        assert r1["title"] == "Purification of succinic acid"
        assert r1["assignees"] == ["LG Chem", "SK Chemicals"]
        assert r1["cpc_codes"] == ["C07C55/10"]

        await kipris_client.close()

    async def test_search_patents_empty_api_key_returns_empty(
        self, kipris_client_no_key: KIPRISClient
    ):
        """When API key is empty/missing, search returns [] without making any request."""
        results = await kipris_client_no_key.search_patents(["succinic acid"])
        assert results == []
        await kipris_client_no_key.close()

    async def test_search_patents_empty_response(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """Empty <items/> element returns an empty list."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text=KIPRIS_XML_EMPTY,
        )

        results = await kipris_client.search_patents(["nonexistent compound"])
        assert results == []
        await kipris_client.close()


class TestKIPRISSearchByApplicant:
    """Tests for KIPRISClient.search_by_applicant."""

    async def test_search_by_applicant(self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock):
        """Applicant search parses XML and returns normalized results."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text=KIPRIS_XML_FULL,
        )

        results = await kipris_client.search_by_applicant("Samsung Electronics")

        assert len(results) == 2
        assert results[0]["assignees"] == ["Samsung Electronics"]
        assert results[0]["publication_number"].startswith("KR")
        await kipris_client.close()

    async def test_search_by_applicant_no_key_returns_empty(
        self, kipris_client_no_key: KIPRISClient
    ):
        """Applicant search returns [] when no API key configured."""
        results = await kipris_client_no_key.search_by_applicant("Samsung Electronics")
        assert results == []
        await kipris_client_no_key.close()


class TestKIPRISXMLParsing:
    """Tests for XML parsing edge cases."""

    async def test_xml_parsing_handles_missing_fields(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """XML with only applicationNumber (missing optional fields) doesn't crash."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text=KIPRIS_XML_MISSING_FIELDS,
        )

        results = await kipris_client.search_patents(["test"])

        assert len(results) == 1
        r = results[0]
        assert r["publication_number"] == "KR1020220099999"
        assert r["title"] == ""
        assert r["abstract"] == ""
        assert r["filing_date"] == ""
        assert r["assignees"] == []
        assert r["cpc_codes"] == []
        await kipris_client.close()

    async def test_xml_parsing_invalid_xml_raises_source_unavailable(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """Malformed XML indicates API schema drift or data corruption — must raise, not silently return empty."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text="<broken><xml",
        )

        with pytest.raises(SourceUnavailableError) as excinfo:
            await kipris_client.search_patents(["test"])
        assert excinfo.value.source == "kipris"
        await kipris_client.close()

    def test_xml_entities_are_rejected_fail_closed(
        self,
        kipris_client: KIPRISClient,
    ):
        """Untrusted KIPRIS XML must never expand external or inline entities."""
        xml = """\
<!DOCTYPE response [<!ENTITY injected "sensitive-local-content">]>
<response><body><items><item>
  <applicationNumber>&injected;</applicationNumber>
</item></items></body></response>"""

        with pytest.raises(SourceUnavailableError) as excinfo:
            kipris_client._parse_items(xml)

        assert excinfo.value.source == "kipris"
        assert "sensitive-local-content" not in str(excinfo.value)

    async def test_kr_prefix_added_when_missing(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """Publication numbers without KR prefix should get KR prepended."""
        xml = """\
<response><body><items>
  <item><applicationNumber>1020200012345</applicationNumber></item>
</items></body></response>"""
        httpx_mock.add_response(url=re.compile(r".*kipris.*"), text=xml)

        results = await kipris_client.search_patents(["test"])
        assert results[0]["publication_number"] == "KR1020200012345"
        await kipris_client.close()

    async def test_kr_prefix_not_doubled(self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock):
        """Publication numbers already starting with KR should not get double prefix."""
        xml = """\
<response><body><items>
  <item><applicationNumber>KR1020200012345</applicationNumber></item>
</items></body></response>"""
        httpx_mock.add_response(url=re.compile(r".*kipris.*"), text=xml)

        results = await kipris_client.search_patents(["test"])
        assert results[0]["publication_number"] == "KR1020200012345"
        await kipris_client.close()


class TestKIPRISAuthError:
    """Tests for authentication error handling."""

    async def test_auth_error_raises(self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock):
        """401 response from KIPRIS should raise AuthenticationError."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError, match="KIPRIS"):
            await kipris_client.search_patents(["test"])
        await kipris_client.close()

    async def test_403_also_raises_auth_error(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """403 (forbidden) should also raise AuthenticationError."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            status_code=403,
        )

        with pytest.raises(AuthenticationError, match="KIPRIS"):
            await kipris_client.search_patents(["test"])
        await kipris_client.close()


class TestKIPRISErrorPaths:
    """Tests for 500, transport errors, and ServiceKey query parameter."""

    async def test_500_exhausts_retries_raises(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """A persistent 500 response exhausts all tenacity retries and raises RetryError."""
        from tenacity import RetryError

        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            status_code=500,
        )
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            status_code=500,
        )
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            status_code=500,
        )

        with pytest.raises(RetryError) as excinfo:
            await kipris_client.search_patents(["test"])
        assert isinstance(excinfo.value.last_attempt.exception(), httpx.HTTPStatusError)
        await kipris_client.close()

    async def test_connect_error_propagates(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """A ConnectError propagates wrapped in RetryError after tenacity exhausts retries."""
        from tenacity import RetryError

        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=re.compile(r".*kipris.*"),
        )
        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=re.compile(r".*kipris.*"),
        )
        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=re.compile(r".*kipris.*"),
        )

        with pytest.raises(RetryError) as excinfo:
            await kipris_client.search_patents(["test"])
        assert isinstance(excinfo.value.last_attempt.exception(), httpx.ConnectError)
        await kipris_client.close()

    async def test_service_key_included_in_request(
        self, kipris_client: KIPRISClient, httpx_mock: HTTPXMock
    ):
        """The ServiceKey query parameter must be present in every outgoing request."""
        httpx_mock.add_response(
            url=re.compile(r".*kipris.*"),
            text=KIPRIS_XML_EMPTY,
        )

        await kipris_client.search_patents(["test"])

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "ServiceKey" in requests[0].url.params
        assert requests[0].url.params["ServiceKey"] != ""
        await kipris_client.close()
