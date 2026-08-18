"""Tests for PubChem client — mocked at the httpx transport level."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.pubchem import PubChemClient


@pytest.fixture
def pubchem_client(mock_settings) -> PubChemClient:
    return PubChemClient()


class TestPubChemResolve:
    async def test_resolve_by_name(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/name/succinic%20acid/property/.*"),
            json={
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 1110,
                            "IUPACName": "succinic acid",
                            "CanonicalSMILES": "OC(=O)CCC(O)=O",
                            "MolecularFormula": "C4H6O4",
                            "MolecularWeight": "118.09",
                            "InChI": "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8",
                            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
                        }
                    ]
                }
            },
        )

        result = await pubchem_client.resolve_by_name("succinic acid")
        assert result["CID"] == 1110
        assert result["CanonicalSMILES"] == "OC(=O)CCC(O)=O"
        await pubchem_client.close()

    async def test_resolve_by_name_not_found(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/name/.*"),
            status_code=404,
        )

        result = await pubchem_client.resolve_by_name("nonexistent_compound_xyz")
        assert result == {}
        await pubchem_client.close()

    async def test_resolve_by_smiles(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/smiles/.*"),
            json={
                "PropertyTable": {
                    "Properties": [{"CID": 1110, "CanonicalSMILES": "OC(=O)CCC(O)=O"}]
                }
            },
        )

        result = await pubchem_client.resolve_by_smiles("OC(=O)CCC(O)=O")
        assert result["CID"] == 1110
        await pubchem_client.close()


class TestPubChemSynonyms:
    async def test_get_synonyms(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/cid/1110/synonyms/.*"),
            json={
                "InformationList": {
                    "Information": [
                        {"CID": 1110, "Synonym": ["succinic acid", "butanedioic acid", "110-15-6"]}
                    ]
                }
            },
        )

        synonyms = await pubchem_client.get_synonyms(1110)
        assert "succinic acid" in synonyms
        assert "110-15-6" in synonyms
        await pubchem_client.close()

    async def test_get_synonyms_empty(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/cid/9999999/synonyms/.*"),
            status_code=404,
        )

        synonyms = await pubchem_client.get_synonyms(9999999)
        assert synonyms == []
        await pubchem_client.close()


class TestPubChemPatentLinks:
    async def test_get_patent_links(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/cid/1110/xrefs/PatentID/.*"),
            json={
                "InformationList": {
                    "Information": [
                        {"CID": 1110, "PatentID": ["US7851188", "US6265190", "US9123456"]}
                    ]
                }
            },
        )

        patents = await pubchem_client.get_patent_links(1110)
        assert len(patents) == 3
        assert "US7851188" in patents
        await pubchem_client.close()


class TestPubChemResolveByInchikey:
    async def test_resolve_by_inchikey(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/inchikey/KDYFGRWQOYBRFD-UHFFFAOYSA-N/property/.*"),
            json={
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 1110,
                            "IUPACName": "succinic acid",
                            "CanonicalSMILES": "OC(=O)CCC(O)=O",
                            "MolecularFormula": "C4H6O4",
                            "MolecularWeight": "118.09",
                            "InChI": "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8",
                            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
                        }
                    ]
                }
            },
        )

        result = await pubchem_client.resolve_by_inchikey("KDYFGRWQOYBRFD-UHFFFAOYSA-N")
        assert result["CID"] == 1110
        assert result["CanonicalSMILES"] == "OC(=O)CCC(O)=O"
        await pubchem_client.close()

    async def test_resolve_by_inchikey_not_found(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/inchikey/.*"),
            status_code=404,
        )

        result = await pubchem_client.resolve_by_inchikey("AAAAAAAAAA-NOTREAL-A")
        assert result == {}
        await pubchem_client.close()


class TestPubChemGetPropertiesForCids:
    async def test_get_properties_for_cids(self, pubchem_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/compound/cid/1110,2723872/property/.*"),
            json={
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 1110,
                            "IUPACName": "succinic acid",
                            "CanonicalSMILES": "OC(=O)CCC(O)=O",
                            "MolecularFormula": "C4H6O4",
                            "MolecularWeight": "118.09",
                            "InChI": "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8",
                            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
                        },
                        {
                            "CID": 2723872,
                            "IUPACName": "fumaric acid",
                            "CanonicalSMILES": "OC(=O)/C=C/C(O)=O",
                            "MolecularFormula": "C4H4O4",
                            "MolecularWeight": "116.07",
                            "InChI": "InChI=1S/C4H4O4/c5-3(6)1-2-4(7)8/h1-2H,(H,5,6)(H,7,8)/b2-1+",
                            "InChIKey": "VZCYOOQTPOCHFL-OWOJBTEDSA-N",
                        },
                    ]
                }
            },
        )

        results = await pubchem_client._get_properties_for_cids([1110, 2723872])
        assert len(results) == 2
        cids = [r["CID"] for r in results]
        assert 1110 in cids
        assert 2723872 in cids
        await pubchem_client.close()

    async def test_get_properties_for_cids_empty(self, pubchem_client, httpx_mock: HTTPXMock):
        results = await pubchem_client._get_properties_for_cids([])
        assert results == []
        await pubchem_client.close()
