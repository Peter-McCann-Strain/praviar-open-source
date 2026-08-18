"""Tests for OpenAlex client — mocked at the httpx transport level."""

from __future__ import annotations

import re
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock
from tenacity import RetryError

from praviar_pipeline.clients.openalex import OpenAlexClient
from praviar_pipeline.errors import AuthenticationError, ConfigurationError


@pytest.fixture
def oa_client(mock_settings) -> OpenAlexClient:
    return OpenAlexClient()


class TestWorksSearch:
    @pytest.mark.parametrize("api_key", ["", "   "])
    def test_missing_api_key_fails_before_client_creation(self, api_key: str) -> None:
        with patch("praviar_pipeline.clients.openalex.get_settings") as settings:
            settings.return_value.openalex_api_key = api_key
            with pytest.raises(ConfigurationError, match="OpenAlex API key not configured"):
                OpenAlexClient()

    async def test_search_works(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            json={
                "results": [
                    {
                        "id": "W123",
                        "title": "Bio-based succinic acid production",
                        "publication_date": "2014-03-15",
                        "doi": "https://doi.org/10.1234/test",
                        "authorships": [{"author": {"display_name": "A. Researcher"}}],
                    }
                ]
            },
        )

        works = await oa_client.search_works("succinic acid production")
        assert len(works) == 1
        assert works[0]["id"] == "W123"
        await oa_client.close()

    async def test_search_with_year_filter(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            json={"results": []},
        )

        await oa_client.search_works("succinic acid", year_before=2010)
        request = httpx_mock.get_requests()[0]
        assert "filter" in str(request.url)
        await oa_client.close()

    async def test_search_with_year_and_max(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            json={"results": []},
        )

        await oa_client.search_works(
            "succinic acid",
            year_before=2010,
            max_results=50,
        )
        request = httpx_mock.get_requests()[0]
        assert "publication_year" in str(request.url)
        await oa_client.close()

    async def test_search_empty(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            json={"results": []},
        )

        works = await oa_client.search_works("nonexistent_xyz")
        assert works == []
        await oa_client.close()

    async def test_auth_failure(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            status_code=403,
        )

        with pytest.raises(AuthenticationError):
            await oa_client.search_works("succinic acid")
        await oa_client.close()

    async def test_429_exhausts_retries(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            status_code=429,
            headers={"Retry-After": "0"},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            status_code=429,
            headers={"Retry-After": "0"},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            status_code=429,
            headers={"Retry-After": "0"},
        )

        with pytest.raises(RetryError):
            await oa_client.search_works("succinic acid")
        await oa_client.close()

    async def test_500_raises(self, oa_client, httpx_mock: HTTPXMock):
        for _ in range(3):
            httpx_mock.add_response(
                url=re.compile(r".*/works.*"),
                status_code=500,
            )

        with pytest.raises(RetryError) as exc_info:
            await oa_client.search_works("succinic acid")
        assert isinstance(exc_info.value.last_attempt.exception(), httpx.HTTPStatusError)
        await oa_client.close()

    async def test_api_key_appended_to_query_params(self, oa_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/works.*"),
            json={"results": []},
        )

        await oa_client.search_works("succinic acid")
        request = httpx_mock.get_requests()[0]
        assert "api_key=test%40example.com" in str(request.url)
        await oa_client.close()
