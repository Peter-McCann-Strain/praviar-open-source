"""Tests for SureChEMBL client — mocked at the httpx transport level.

The SureChEMBL API migrated to an async POST/hash-polling model in 2025.
These tests cover the new flow:
  POST /search/structure → hash
  GET  /search/<hash>/status → finished
  GET  /search/<hash>/results → chemical IDs
  POST /search/documents_for_structures → patent docs (currently 500 server-side)
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.surechembl import SureChEMBLClient
from praviar_pipeline.errors import SourceUnavailableError

SMILES = "OC(=O)CCC(O)=O"
HASH = "abc12345-dead-beef-cafe-000000000001"

STRUCTURE_SEARCH_RESPONSE = {"status": "OK", "data": {"hash": HASH}}
STATUS_FINISHED = {"status": "OK", "data": {"state": "Searching finished."}}
RESULTS_RESPONSE = {
    "status": "OK",
    "data": {"query": {"structures": [1353, 29350479]}},
}
DOCUMENTS_RESPONSE = {
    "status": "OK",
    "data": {"documents": [{"patent_id": "EP1234567", "chemical_id": 1353}]},
}


@pytest.fixture
def surechembl_client(mock_settings) -> SureChEMBLClient:
    return SureChEMBLClient()


@pytest.fixture(autouse=True)
def _no_retry_sleep():
    with patch(
        "praviar_pipeline.clients.surechembl.wait_exponential_jitter",
        return_value=lambda *_a, **_kw: 0,
    ):
        yield


def _mock_full_search(
    httpx_mock: HTTPXMock,
    *,
    documents_status: int = 200,
    documents_json: dict | None = None,
) -> None:
    """Wire all four legs of the hash-polling flow."""
    httpx_mock.add_response(
        url=re.compile(r".*/search/structure"),
        method="POST",
        json=STRUCTURE_SEARCH_RESPONSE,
    )
    httpx_mock.add_response(
        url=re.compile(rf".*/search/{re.escape(HASH)}/status"),
        json=STATUS_FINISHED,
    )
    httpx_mock.add_response(
        url=re.compile(rf".*/search/{re.escape(HASH)}/results"),
        json=RESULTS_RESPONSE,
    )
    httpx_mock.add_response(
        url=re.compile(r".*/search/documents_for_structures"),
        method="POST",
        status_code=documents_status,
        json=documents_json or (DOCUMENTS_RESPONSE if documents_status == 200 else {}),
    )


class TestSearchBySmiles:
    async def test_returns_compounds_when_documents_endpoint_works(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=200, documents_json=DOCUMENTS_RESPONSE)

        results = await surechembl_client.search_by_smiles(SMILES)

        assert len(results) == 1
        assert results[0]["patent_id"] == "EP1234567"
        await surechembl_client.close()

    async def test_raises_when_documents_endpoint_500(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=500)

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.search_by_smiles(SMILES)
        await surechembl_client.close()

    async def test_raises_when_structure_search_fails(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            url=re.compile(r".*/search/structure"),
            method="POST",
            status_code=500,
        )

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.search_by_smiles(SMILES)
        await surechembl_client.close()

    async def test_returns_empty_when_no_chemical_ids(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            url=re.compile(r".*/search/structure"),
            method="POST",
            json=STRUCTURE_SEARCH_RESPONSE,
        )
        httpx_mock.add_response(
            url=re.compile(rf".*/search/{re.escape(HASH)}/status"),
            json=STATUS_FINISHED,
        )
        httpx_mock.add_response(
            url=re.compile(rf".*/search/{re.escape(HASH)}/results"),
            json={"status": "OK", "data": {"query": {"structures": []}}},
        )

        results = await surechembl_client.search_by_smiles(SMILES)

        assert results == []
        await surechembl_client.close()

    async def test_polls_until_finished(self, surechembl_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/search/structure"),
            method="POST",
            json=STRUCTURE_SEARCH_RESPONSE,
        )
        # First poll: still running
        httpx_mock.add_response(
            url=re.compile(rf".*/search/{re.escape(HASH)}/status"),
            json={"status": "OK", "data": {"state": "Searching in progress."}},
        )
        # Second poll: finished
        httpx_mock.add_response(
            url=re.compile(rf".*/search/{re.escape(HASH)}/status"),
            json=STATUS_FINISHED,
        )
        httpx_mock.add_response(
            url=re.compile(rf".*/search/{re.escape(HASH)}/results"),
            json={"status": "OK", "data": {"query": {"structures": []}}},
        )

        with patch("praviar_pipeline.clients.surechembl.asyncio.sleep"):
            results = await surechembl_client.search_by_smiles(SMILES)

        assert results == []
        await surechembl_client.close()


class TestSimilaritySearch:
    async def test_raises_when_documents_endpoint_500(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=500)

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.similarity_search(SMILES, threshold=0.7)
        await surechembl_client.close()

    async def test_returns_compounds_when_documents_endpoint_works(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=200, documents_json=DOCUMENTS_RESPONSE)

        results = await surechembl_client.similarity_search(SMILES)

        assert len(results) == 1
        await surechembl_client.close()

    async def test_raises_on_structure_post_failure(self, surechembl_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/search/structure"),
            method="POST",
            status_code=503,
        )

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.similarity_search(SMILES)
        await surechembl_client.close()


class TestSubstructureSearch:
    async def test_raises_when_documents_endpoint_500(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=500)

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.substructure_search(SMILES)
        await surechembl_client.close()

    async def test_returns_compounds_when_documents_endpoint_works(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        _mock_full_search(httpx_mock, documents_status=200, documents_json=DOCUMENTS_RESPONSE)

        results = await surechembl_client.substructure_search(SMILES)

        assert len(results) == 1
        await surechembl_client.close()

    async def test_raises_on_structure_post_failure(self, surechembl_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/search/structure"),
            method="POST",
            status_code=404,
        )

        with pytest.raises(SourceUnavailableError):
            await surechembl_client.substructure_search(SMILES)
        await surechembl_client.close()


class TestGetUncached:
    async def test_404_ok_on_404_false_raises_source_unavailable(
        self, surechembl_client, httpx_mock: HTTPXMock
    ):
        """_get(ok_on_404=False) on a 404 raises SourceUnavailableError."""
        for _ in range(3):
            httpx_mock.add_response(
                url=re.compile(r".*/some/path"),
                status_code=404,
            )

        from tenacity import RetryError

        with pytest.raises((SourceUnavailableError, RetryError)) as exc_info:
            await surechembl_client._get("/some/path", ok_on_404=False)

        exc = exc_info.value
        if isinstance(exc, RetryError):
            exc = exc.last_attempt.exception()
        assert isinstance(exc, SourceUnavailableError)
        assert exc.status_code == 404
        await surechembl_client.close()

    async def test_404_ok_on_404_true_returns_empty(self, surechembl_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=re.compile(r".*/some/path"), status_code=404)

        result = await surechembl_client._get("/some/path", ok_on_404=True)

        assert result == {}
        await surechembl_client.close()
