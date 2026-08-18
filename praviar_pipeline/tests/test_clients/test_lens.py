"""Tests for Lens.org client — mocked at the httpx transport level."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from pytest_httpx import HTTPXMock
from tenacity import RetryError

from praviar_pipeline.clients.lens import LensClient
from praviar_pipeline.errors import AuthenticationError


@pytest.fixture
def lens_client(mock_settings) -> LensClient:
    return LensClient()


class TestScholarlyByPatent:
    async def test_search_scholarly(self, lens_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            json={
                "data": [
                    {
                        "lens_id": "L123",
                        "title": "Prior art paper on succinic acid",
                        "date_published": "2007-05-20",
                        "year_published": 2007,
                        "authors": [{"first_name": "J", "last_name": "Doe"}],
                        "external_ids": [{"type": "doi", "value": "10.1234/prior-art"}],
                    }
                ]
            },
        )

        results = await lens_client.search_scholarly_by_patent("US7851188B2")
        assert len(results) == 1
        assert results[0]["lens_id"] == "L123"
        await lens_client.close()

    async def test_search_scholarly_empty(self, lens_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            json={"data": []},
        )

        results = await lens_client.search_scholarly_by_patent("US0000000B2")
        assert results == []
        await lens_client.close()

    async def test_auth_failure(self, lens_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError):
            await lens_client.search_scholarly_by_patent("US7851188B2")
        await lens_client.close()

    async def test_429_retries_to_success(self, lens_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            status_code=429,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            status_code=429,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            json={"data": [{"lens_id": "L999", "title": "Retry success"}]},
        )

        results = await lens_client.search_scholarly_by_patent("US7851188B2")
        assert len(results) == 1
        assert results[0]["lens_id"] == "L999"
        assert len(httpx_mock.get_requests()) == 3
        await lens_client.close()

    async def test_500_exhausts_retries_raises(self, lens_client, httpx_mock: HTTPXMock):
        for _ in range(3):
            httpx_mock.add_response(
                url=re.compile(r".*/scholarly/search"),
                status_code=500,
            )

        with pytest.raises(RetryError) as exc_info:
            await lens_client.search_scholarly_by_patent("US7851188B2")
        assert isinstance(exc_info.value.last_attempt.exception(), httpx.HTTPStatusError)
        assert len(httpx_mock.get_requests()) == 3
        await lens_client.close()

    async def test_authorization_header_present(self, lens_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            json={"data": []},
        )

        await lens_client.search_scholarly_by_patent("US7851188B2")
        request = httpx_mock.get_requests()[0]
        assert request.headers.get("authorization") == "Bearer test-lens-key"
        await lens_client.close()

    async def test_request_payload_contains_patent_id(self, lens_client, httpx_mock: HTTPXMock):
        patent_id = "US7851188B2"
        httpx_mock.add_response(
            url=re.compile(r".*/scholarly/search"),
            json={"data": []},
        )

        await lens_client.search_scholarly_by_patent(patent_id)
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        must_clauses = body["query"]["bool"]["must"]
        match_values = [
            next(iter(clause["match"].values())) for clause in must_clauses if "match" in clause
        ]
        assert patent_id in match_values
        await lens_client.close()
