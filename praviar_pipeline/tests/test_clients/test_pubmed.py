"""Tests for PubMedClient — mocked at the httpx transport level."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.pubmed import PubMedClient
from praviar_pipeline.errors import SourceUnavailableError


@pytest.fixture
def pubmed_client(mock_settings) -> PubMedClient:
    return PubMedClient()


_ESEARCH_URL = re.compile(r".*/esearch\.fcgi.*")
_ESUMMARY_URL = re.compile(r".*/esummary\.fcgi.*")


class TestSearchPapers:
    async def test_happy_path_calls_esearch_then_esummary(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": ["11111", "22222"], "count": "2"}},
        )
        httpx_mock.add_response(
            url=_ESUMMARY_URL,
            json={
                "result": {
                    "11111": {
                        "title": "Succinic acid biosynthesis",
                        "authors": [{"name": "Smith J"}],
                        "fulljournalname": "Nature Chemistry",
                        "pubdate": "2020 Jan 01",
                        "articleids": [{"idtype": "doi", "value": "10.1234/test"}],
                        "volume": "12",
                        "issue": "3",
                        "pages": "45-50",
                    },
                    "22222": {
                        "title": "Fermentation routes",
                        "authors": [],
                        "fulljournalname": "Science",
                        "pubdate": "2019",
                        "articleids": [],
                        "volume": "",
                        "issue": "",
                        "pages": "",
                    },
                }
            },
        )

        papers = await pubmed_client.search_papers("succinic acid")

        requests = httpx_mock.get_requests()
        urls = [str(r.url) for r in requests]
        assert any("esearch" in u for u in urls)
        assert any("esummary" in u for u in urls)

        assert len(papers) == 2
        assert papers[0]["pmid"] == "11111"
        assert papers[0]["title"] == "Succinic acid biosynthesis"
        assert papers[0]["doi"] == "10.1234/test"
        assert papers[0]["source"] == "pubmed"
        await pubmed_client.close()

    async def test_search_papers_404_raises_source_unavailable(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        from tenacity import RetryError

        for _ in range(3):
            httpx_mock.add_response(url=_ESEARCH_URL, status_code=404)

        with (
            pytest.MonkeyPatch().context() as mp,
            pytest.raises((SourceUnavailableError, RetryError)) as excinfo,
        ):
            mp.setattr(
                "praviar_pipeline.clients.pubmed.wait_exponential_jitter",
                lambda *_a, **_kw: lambda *__a, **__kw: 0,
            )
            await pubmed_client.search_papers("succinic acid")

        if isinstance(excinfo.value, RetryError):
            assert isinstance(excinfo.value.last_attempt.exception(), SourceUnavailableError)
            assert excinfo.value.last_attempt.exception().source == "pubmed"
        else:
            assert excinfo.value.source == "pubmed"

        await pubmed_client.close()

    async def test_search_papers_500_raises(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:

        for _ in range(3):
            httpx_mock.add_response(url=_ESEARCH_URL, status_code=500)

        with (
            pytest.MonkeyPatch().context() as mp,
            pytest.raises((Exception,)),
        ):
            mp.setattr(
                "praviar_pipeline.clients.pubmed.wait_exponential_jitter",
                lambda *_a, **_kw: lambda *__a, **__kw: 0,
            )
            await pubmed_client.search_papers("succinic acid")

        await pubmed_client.close()

    async def test_search_papers_no_results_returns_empty(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": [], "count": "0"}},
        )

        papers = await pubmed_client.search_papers("xyzzy_nonexistent_compound")

        assert papers == []
        assert len(httpx_mock.get_requests()) == 1
        await pubmed_client.close()

    async def test_search_papers_429_retry_to_success(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(url=_ESEARCH_URL, status_code=429)
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": ["99999"], "count": "1"}},
        )
        httpx_mock.add_response(
            url=_ESUMMARY_URL,
            json={
                "result": {
                    "99999": {
                        "title": "Retry success paper",
                        "authors": [],
                        "fulljournalname": "Journal",
                        "pubdate": "2021",
                        "articleids": [],
                        "volume": "",
                        "issue": "",
                        "pages": "",
                    }
                }
            },
        )

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "praviar_pipeline.clients.pubmed.wait_exponential_jitter",
                lambda *_a, **_kw: lambda *__a, **__kw: 0,
            )
            papers = await pubmed_client.search_papers("succinic acid")

        assert len(papers) == 1
        assert papers[0]["pmid"] == "99999"
        await pubmed_client.close()


class TestGetPaperDetails:
    async def test_delegates_to_fetch_summaries(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESUMMARY_URL,
            json={
                "result": {
                    "12345": {
                        "title": "A detailed paper",
                        "authors": [{"name": "Doe J"}],
                        "fulljournalname": "JACS",
                        "pubdate": "2018 Mar",
                        "articleids": [{"idtype": "doi", "value": "10.1021/test"}],
                        "volume": "140",
                        "issue": "5",
                        "pages": "1234-1240",
                    }
                }
            },
        )

        result = await pubmed_client.get_paper_details("12345")

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "esummary" in str(requests[0].url)
        assert "12345" in str(requests[0].url)

        assert result["pmid"] == "12345"
        assert result["title"] == "A detailed paper"
        assert result["doi"] == "10.1021/test"
        await pubmed_client.close()

    async def test_get_paper_details_not_found_returns_empty(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(url=_ESUMMARY_URL, status_code=404)

        result = await pubmed_client.get_paper_details("00000")

        assert result == {}
        await pubmed_client.close()


class TestSearchCompoundLiterature:
    async def test_builds_or_joined_query_with_synonyms_and_cas(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": [], "count": "0"}},
        )

        await pubmed_client.search_compound_literature(
            "succinic acid",
            synonyms=["butanedioic acid", "amber acid"],
            cas_numbers=["110-15-6"],
        )

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        query_str = str(requests[0].url)
        assert (
            "succinic%20acid" in query_str
            or "succinic+acid" in query_str
            or "succinic" in query_str
        )
        assert "OR" in query_str or "%20OR%20" in query_str or "+OR+" in query_str
        assert "110-15-6" in query_str or "110" in query_str
        await pubmed_client.close()

    async def test_compound_literature_no_synonyms(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": [], "count": "0"}},
        )

        await pubmed_client.search_compound_literature("ibuprofen")

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "ibuprofen" in str(requests[0].url)
        await pubmed_client.close()

    async def test_compound_literature_returns_papers(
        self, pubmed_client: PubMedClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_ESEARCH_URL,
            json={"esearchresult": {"idlist": ["55555"], "count": "1"}},
        )
        httpx_mock.add_response(
            url=_ESUMMARY_URL,
            json={
                "result": {
                    "55555": {
                        "title": "Compound paper",
                        "authors": [],
                        "fulljournalname": "Journal",
                        "pubdate": "2022",
                        "articleids": [],
                        "volume": "",
                        "issue": "",
                        "pages": "",
                    }
                }
            },
        )

        papers = await pubmed_client.search_compound_literature(
            "succinic acid",
            synonyms=["butanedioic acid"],
            cas_numbers=["110-15-6"],
        )

        assert len(papers) == 1
        assert papers[0]["pmid"] == "55555"
        await pubmed_client.close()
