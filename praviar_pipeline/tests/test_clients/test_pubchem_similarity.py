"""Tests for PubChem similarity_search async-polling paths."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.pubchem import PubChemClient
from praviar_pipeline.errors import SourceUnavailableError

_SIMILARITY_URL = re.compile(r".*/compound/fastsimilarity_2d/smiles/.*/cids/JSON.*")
_LISTKEY_URL = re.compile(r".*/compound/listkey/TESTKEY123/cids/JSON")
_PROPERTIES_URL = re.compile(r".*/compound/cid/\d+/property/.*")

_PROPERTIES_RESPONSE = {
    "PropertyTable": {
        "Properties": [
            {
                "CID": 1110,
                "IUPACName": "succinic acid",
                "CanonicalSMILES": "OC(=O)CCC(=O)O",
                "MolecularFormula": "C4H6O4",
                "MolecularWeight": "118.09",
                "InChI": "InChI=1S/C4H6O4",
                "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            }
        ]
    }
}


@pytest.fixture
def pubchem_client(mock_settings) -> PubChemClient:
    return PubChemClient()


class TestSimilaritySearchImmediate:
    async def test_immediate_cid_list_no_waiting(
        self, pubchem_client: PubChemClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_SIMILARITY_URL,
            json={"IdentifierList": {"CID": [1110]}},
        )
        httpx_mock.add_response(
            url=_PROPERTIES_URL,
            json=_PROPERTIES_RESPONSE,
        )

        results = await pubchem_client.similarity_search("OC(=O)CCC(=O)O")

        assert len(results) == 1
        assert results[0]["CID"] == 1110
        await pubchem_client.close()

    async def test_immediate_empty_cid_list(
        self, pubchem_client: PubChemClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_SIMILARITY_URL,
            json={"IdentifierList": {"CID": []}},
        )

        results = await pubchem_client.similarity_search("OC(=O)CCC(=O)O")

        assert results == []
        await pubchem_client.close()


class TestSimilaritySearchPolling:
    async def test_waiting_then_ready(
        self, pubchem_client: PubChemClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_SIMILARITY_URL,
            json={"Waiting": {"ListKey": "TESTKEY123"}},
        )
        httpx_mock.add_response(
            url=_LISTKEY_URL,
            json={"IdentifierList": {"CID": [1110]}},
        )
        httpx_mock.add_response(
            url=_PROPERTIES_URL,
            json=_PROPERTIES_RESPONSE,
        )

        with patch("praviar_pipeline.clients.pubchem_client_ops.asyncio.sleep", new=AsyncMock()):
            results = await pubchem_client.similarity_search("OC(=O)CCC(=O)O")

        assert len(results) == 1
        assert results[0]["CID"] == 1110
        await pubchem_client.close()

    async def test_repeated_waiting_until_max_polls_raises(
        self, pubchem_client: PubChemClient, httpx_mock: HTTPXMock
    ) -> None:
        for _ in range(3):
            httpx_mock.add_response(
                url=_LISTKEY_URL,
                json={"Waiting": {"ListKey": "TESTKEY123"}},
            )

        with patch("praviar_pipeline.clients.pubchem_client_ops.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(SourceUnavailableError):
                await pubchem_client._poll_list_key("TESTKEY123", max_polls=3)

        await pubchem_client.close()

    async def test_404_during_listkey_polling_raises(
        self, pubchem_client: PubChemClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=_LISTKEY_URL,
            status_code=404,
        )

        with patch("praviar_pipeline.clients.pubchem_client_ops.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(SourceUnavailableError) as exc_info:
                await pubchem_client._poll_list_key("TESTKEY123", max_polls=3)

        assert exc_info.value.status_code == 404
        await pubchem_client.close()
