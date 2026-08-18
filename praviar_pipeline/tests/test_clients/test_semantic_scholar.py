"""Tests for Semantic Scholar client — mocked at the httpx transport level."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients import semantic_scholar
from praviar_pipeline.clients.semantic_scholar import SemanticScholarClient
from praviar_pipeline.errors import AuthenticationError


@pytest.fixture
def s2_client(mock_settings) -> SemanticScholarClient:
    return SemanticScholarClient()


class TestPaperSearch:
    async def test_search_papers(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={
                "data": [
                    {
                        "paperId": "abc123",
                        "title": "Succinic acid production via fermentation",
                        "abstract": "We present a novel method...",
                        "year": 2015,
                        "publicationDate": "2015-06-01",
                        "authors": [{"name": "J. Smith"}],
                        "journal": {"name": "Nature Chemistry"},
                        "externalIds": {"DOI": "10.1234/test"},
                        "citationCount": 42,
                    }
                ]
            },
        )

        papers = await s2_client.search_papers("succinic acid fermentation")
        assert len(papers) == 1
        assert papers[0]["paperId"] == "abc123"
        assert papers[0]["year"] == 2015
        await s2_client.close()

    async def test_success_path_never_logs_confidential_query(
        self,
        s2_client,
        httpx_mock: HTTPXMock,
        monkeypatch,
    ):
        sentinel = "semantic-scholar-confidential-query-sentinel"
        recording_logger = MagicMock()
        monkeypatch.setattr(semantic_scholar, "logger", recording_logger)
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={"data": [{"paperId": "public-paper", "title": "Public title"}]},
        )

        papers = await s2_client.search_papers(sentinel)

        assert papers
        for method_name in ("debug", "info", "warning", "error"):
            for call in getattr(recording_logger, method_name).call_args_list:
                assert sentinel not in repr((call.args, call.kwargs))
        await s2_client.close()

    async def test_search_with_year_filter(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={"data": []},
        )

        await s2_client.search_papers("succinic acid", year_before=2010)
        request = httpx_mock.get_requests()[0]
        assert "year" in str(request.url)
        await s2_client.close()

    async def test_search_with_fields_of_study(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={"data": []},
        )

        await s2_client.search_papers(
            "succinic acid",
            fields_of_study=["Chemistry", "Biology"],
        )
        request = httpx_mock.get_requests()[0]
        assert "fieldsOfStudy" in str(request.url)
        await s2_client.close()

    async def test_search_empty(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={"data": []},
        )

        papers = await s2_client.search_papers("nonexistent_compound_xyz")
        assert papers == []
        await s2_client.close()

    async def test_auth_failure_never_logs_response_credentials(
        self,
        s2_client,
        httpx_mock: HTTPXMock,
        monkeypatch,
    ):
        sentinel = "semantic-scholar-auth-sentinel-must-not-escape"
        logger = MagicMock()
        monkeypatch.setattr(semantic_scholar, "logger", logger)
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            status_code=403,
            text=f"rejected credential: {sentinel}",
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await s2_client.search_papers("succinic acid")
        assert str(exc_info.value) == "Semantic Scholar API key is invalid"
        assert sentinel not in repr(exc_info.value)
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None
        for call in logger.error.call_args_list:
            assert sentinel not in repr((call.args, call.kwargs))
            assert "response_body" not in call.kwargs
            assert "exc_info" not in call.kwargs
        await s2_client.close()

    async def test_rate_limit_retries(self, s2_client, httpx_mock: HTTPXMock):
        """429 responses should be retried with backoff."""
        # First call → 429, second call → success
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            status_code=429,
            headers={"Retry-After": "1"},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/paper/search"),
            json={"data": [{"paperId": "retry_success", "title": "Found after retry"}]},
        )

        papers = await s2_client.search_papers("succinic acid")
        assert len(papers) == 1
        assert papers[0]["paperId"] == "retry_success"
        # Should have made 2 requests (first 429, then success)
        assert len(httpx_mock.get_requests()) == 2
        await s2_client.close()

    async def test_500_exhausts_retries_raises_retry_error(
        self, s2_client, httpx_mock: HTTPXMock, monkeypatch
    ):
        """Persistent 500s exhaust tenacity retries and raise RetryError."""
        from tenacity import RetryError

        async def _no_sleep(_seconds: float) -> None:
            pass

        monkeypatch.setattr(SemanticScholarClient._get_uncached.retry, "sleep", _no_sleep)

        for _ in range(8):
            httpx_mock.add_response(
                url=re.compile(r".*/paper/search"),
                status_code=500,
            )

        with pytest.raises(RetryError):
            await s2_client.search_papers("succinic acid")
        assert len(httpx_mock.get_requests()) == 8
        await s2_client.close()

    async def test_network_error_exhausts_retries_raises_retry_error(
        self, s2_client, httpx_mock: HTTPXMock, monkeypatch
    ):
        """ConnectError exhausts tenacity retries and raises RetryError."""
        import httpx as _httpx
        from tenacity import RetryError

        async def _no_sleep(_seconds: float) -> None:
            pass

        monkeypatch.setattr(SemanticScholarClient._get_uncached.retry, "sleep", _no_sleep)

        for _ in range(8):
            httpx_mock.add_exception(
                _httpx.ConnectError("connection refused"),
                url=re.compile(r".*/paper/search"),
            )

        with pytest.raises(RetryError):
            await s2_client.search_papers("succinic acid")
        assert len(httpx_mock.get_requests()) == 8
        await s2_client.close()


class TestGetPaper:
    async def test_get_paper(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/abc123"),
            json={
                "paperId": "abc123",
                "title": "A paper about succinic acid",
                "abstract": "Details here...",
                "year": 2018,
            },
        )

        paper = await s2_client.get_paper("abc123")
        assert paper["paperId"] == "abc123"
        await s2_client.close()

    async def test_get_paper_not_found(self, s2_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/paper/bogus"),
            status_code=404,
        )

        paper = await s2_client.get_paper("bogus")
        assert paper == {}
        await s2_client.close()
