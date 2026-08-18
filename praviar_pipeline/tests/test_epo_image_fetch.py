"""Tests for EPO OPS patent drawing image fetch."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from praviar_pipeline.clients.epo_ops import EPOOPSClient, _to_docdb_format
from praviar_pipeline.errors import SourceUnavailableError


class TestDocdbFormat:
    """Test patent ID to DOCDB format conversion."""

    def test_compact_us(self):
        assert _to_docdb_format("US7851188B2") == "US.7851188.B2"

    def test_hyphenated(self):
        assert _to_docdb_format("US-2024294466-A1") == "US.2024294466.A1"

    def test_ep_patent(self):
        assert _to_docdb_format("EP1234567A1") == "EP.1234567.A1"

    def test_jp_patent(self):
        assert _to_docdb_format("JP2020123456A") == "JP.2020123456.A"


class TestDrawingPageCount:
    """Test get_drawing_page_count method."""

    @pytest.fixture
    def mock_client(self):
        client = EPOOPSClient.__new__(EPOOPSClient)
        client._consumer_key = "test_key"
        client._consumer_secret = "test_secret"
        client._access_token = "test_token"
        client._token_expires_at = 9999999999.0
        client._client = AsyncMock()
        client._limiter = AsyncMock()
        client._external_client = False
        return client

    @pytest.mark.asyncio
    async def test_no_drawings_returns_zero(self, mock_client):
        mock_client._get = AsyncMock(return_value={})
        count = await mock_client.get_drawing_page_count("US7851188B2")
        assert count == 0

    @pytest.mark.asyncio
    async def test_parses_page_count(self, mock_client):
        mock_client._get = AsyncMock(
            return_value={
                "ops:world-patent-data": {
                    "ops:document-inquiry": {
                        "ops:inquiry-result": {
                            "ops:document-instance": [
                                {
                                    "@desc": "Drawing",
                                    "@number-of-pages": "12",
                                }
                            ]
                        }
                    }
                }
            }
        )
        count = await mock_client.get_drawing_page_count("US7851188B2")
        assert count == 12

    @pytest.mark.asyncio
    async def test_single_instance_dict(self, mock_client):
        """Handle case where OPS returns a dict instead of list."""
        mock_client._get = AsyncMock(
            return_value={
                "ops:world-patent-data": {
                    "ops:document-inquiry": {
                        "ops:inquiry-result": {
                            "ops:document-instance": {
                                "@desc": "Drawing",
                                "@number-of-pages": "5",
                            }
                        }
                    }
                }
            }
        )
        count = await mock_client.get_drawing_page_count("EP1234567A1")
        assert count == 5


class TestFetchDrawingPage:
    """Test fetch_drawing_page method."""

    @pytest.fixture
    def mock_client(self):
        client = EPOOPSClient.__new__(EPOOPSClient)
        client._consumer_key = "test_key"
        client._consumer_secret = "test_secret"
        client._access_token = "test_token"
        client._token_expires_at = 9999999999.0
        client._client = AsyncMock()
        client._limiter = AsyncMock()
        client._external_client = False
        return client

    @pytest.mark.asyncio
    async def test_returns_bytes(self, mock_client):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client._get_binary = AsyncMock(return_value=fake_png)
        result = await mock_client.fetch_drawing_page("US7851188B2", page=1)
        assert result == fake_png

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, mock_client):
        mock_client._get_binary = AsyncMock(return_value=None)
        result = await mock_client.fetch_drawing_page("USNOTEXIST", page=1)
        assert result is None


class TestFetchAllDrawings:
    """Test fetch_all_drawings method."""

    @pytest.fixture
    def mock_client(self):
        client = EPOOPSClient.__new__(EPOOPSClient)
        client._consumer_key = "test_key"
        client._consumer_secret = "test_secret"
        client._access_token = "test_token"
        client._token_expires_at = 9999999999.0
        client._client = AsyncMock()
        client._limiter = AsyncMock()
        client._external_client = False
        return client

    @pytest.mark.asyncio
    async def test_fetches_all_pages(self, mock_client):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.get_drawing_page_count = AsyncMock(return_value=3)
        mock_client.fetch_drawing_page = AsyncMock(return_value=fake_png)

        result = await mock_client.fetch_all_drawings("US7851188B2")
        assert len(result) == 3
        assert all(page_num >= 1 for page_num, _ in result)
        assert all(data == fake_png for _, data in result)

    @pytest.mark.asyncio
    async def test_respects_max_pages(self, mock_client):
        fake_png = b"\x89PNG" + b"\x00" * 100
        mock_client.get_drawing_page_count = AsyncMock(return_value=50)
        mock_client.fetch_drawing_page = AsyncMock(return_value=fake_png)

        result = await mock_client.fetch_all_drawings("US7851188B2", max_pages=5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_zero_page_setting_uses_hard_safety_cap(self, mock_client):
        fake_png = b"\x89PNG"
        mock_client.get_drawing_page_count = AsyncMock(return_value=101)
        mock_client.fetch_drawing_page = AsyncMock(return_value=fake_png)

        result = await mock_client.fetch_all_drawings("US7851188B2", max_pages=0)

        assert len(result) == 100

    @pytest.mark.asyncio
    async def test_no_credentials_raises_credentials_missing(self, mock_client):
        """Missing credentials is a configuration choice — raise a distinct
        error (subclass of AuthenticationError) so the orchestrator can mark
        EPO OPS as SKIPPED instead of silently returning empty drawings."""
        from praviar_pipeline.errors import AuthenticationError, EPOCredentialsMissingError

        mock_client._consumer_key = ""
        mock_client._consumer_secret = ""
        with pytest.raises(EPOCredentialsMissingError) as excinfo:
            await mock_client.fetch_all_drawings("US7851188B2")
        # Still an AuthenticationError subclass for existing handlers.
        assert isinstance(excinfo.value, AuthenticationError)
        assert excinfo.value.source == "epo_ops"

    @pytest.mark.asyncio
    async def test_no_drawings_returns_empty(self, mock_client):
        mock_client.get_drawing_page_count = AsyncMock(return_value=0)
        result = await mock_client.fetch_all_drawings("US7851188B2")
        assert result == []

    @pytest.mark.asyncio
    async def test_continues_on_page_failure(self, mock_client):
        """Should skip failed pages and continue with remaining."""
        fake_png = b"\x89PNG" + b"\x00" * 100
        mock_client.get_drawing_page_count = AsyncMock(return_value=3)

        call_count = 0

        async def side_effect(patent_id, page, image_format="image/png"):
            nonlocal call_count
            call_count += 1
            if page == 2:
                raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
            return fake_png

        mock_client.fetch_drawing_page = side_effect
        result = await mock_client.fetch_all_drawings("US7851188B2")
        assert len(result) == 2  # Pages 1 and 3 succeeded

    @pytest.mark.asyncio
    async def test_live_mode_rejects_partial_page_acquisition(self, mock_client):
        fake_png = b"\x89PNG" + b"\x00" * 100
        mock_client.get_drawing_page_count = AsyncMock(return_value=3)

        async def side_effect(patent_id, page, image_format="image/png"):
            if page == 2:
                raise httpx.ReadTimeout(
                    "timed out",
                    request=httpx.Request("GET", "https://ops.epo.org/images"),
                )
            return fake_png

        mock_client.fetch_drawing_page = side_effect

        with pytest.raises(SourceUnavailableError, match="advertised drawing pages"):
            await mock_client.fetch_all_drawings("US7851188B2", fail_closed=True)

    @pytest.mark.asyncio
    async def test_live_mode_rejects_advertised_pages_returning_no_bytes(self, mock_client):
        mock_client.get_drawing_page_count = AsyncMock(return_value=2)
        mock_client.fetch_drawing_page = AsyncMock(return_value=None)

        with pytest.raises(SourceUnavailableError, match="advertised drawing pages"):
            await mock_client.fetch_all_drawings("US7851188B2", fail_closed=True)
