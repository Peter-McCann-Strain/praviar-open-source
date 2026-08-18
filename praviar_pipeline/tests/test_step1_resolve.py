"""Tests for Step 1: Compound Resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.pipeline.step1_resolve import (
    CAS_PATTERN,
    detect_input_type,
    normalize_cas_input,
    resolve_compound,
)


class TestDetectInputType:
    def test_name(self):
        assert detect_input_type("succinic acid") == "name"
        assert detect_input_type("aspirin") == "name"

    def test_smiles(self):
        assert detect_input_type("OC(=O)CCC(O)=O") == "smiles"
        assert detect_input_type("CC(=O)Oc1ccccc1C(O)=O") == "smiles"
        assert detect_input_type("C:C") == "smiles"
        assert detect_input_type("*CC") == "smiles"
        assert detect_input_type("C$C") == "smiles"
        assert detect_input_type("CO") == "smiles"
        assert detect_input_type("[C@@H](N)C(=O)O") == "smiles"
        assert detect_input_type("[NH4+]") == "smiles"
        assert detect_input_type("boron") == "name"
        assert detect_input_type("iron") == "name"
        assert detect_input_type("\ufeffCCO\ufeff") == "smiles"
        assert detect_input_type("[C\u0085]") == "smiles"
        assert detect_input_type("[C\u001c]") == "smiles"
        assert detect_input_type("[C\ufeff]") == "name"

    def test_cas(self):
        assert detect_input_type("110-15-6") == "cas"
        assert detect_input_type("50-78-2") == "cas"
        assert detect_input_type("CAS 50-78-2") == "cas"
        assert detect_input_type("cas rn 50-78-2") == "cas"
        assert normalize_cas_input("CAS No. 50-78-2") == "50-78-2"
        assert detect_input_type("\u0665\u0660-\u0667\u0668-\u0662") == "name"
        assert detect_input_type("CAS\u00a050-78-2") == "cas"
        assert detect_input_type("CAS\u202f50-78-2") == "cas"
        assert normalize_cas_input("CAS\u202f50-78-2") == "50-78-2"

    def test_inchi(self):
        assert detect_input_type("InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8") == "inchi"

    def test_inchikey(self):
        assert detect_input_type("KDYFGRWQOYBRFD-UHFFFAOYSA-N") == "inchikey"
        assert detect_input_type("kdYfgrwqoybrfd-uhfffaoysa-n") == "inchikey"
        assert detect_input_type("\u212aDYFGRWQOYBRFD-UHFFFAOYSA-N") == "name"

    def test_short_identifier_classification_matches_launch_ui(self):
        assert detect_input_type("C") == "name"
        assert detect_input_type("CO") == "smiles"
        assert detect_input_type("CCO") == "smiles"
        assert detect_input_type("H2O") == "name"


class TestResolveCompound:
    async def test_resolve_by_name(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {
            "CID": 1110,
            "IUPACName": "succinic acid",
            "CanonicalSMILES": "OC(=O)CCC(O)=O",
            "InChI": "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            "MolecularFormula": "C4H6O4",
            "MolecularWeight": "118.09",
        }
        mock_pubchem.get_synonyms.return_value = ["succinic acid", "110-15-6"]
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("succinic acid")

        assert compound.name == "succinic acid"
        assert compound.pubchem_cid == 1110
        assert compound.input_type == "name"
        assert "110-15-6" in compound.cas_numbers

    async def test_resolve_not_found_raises(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {}
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
                return_value=mock_pubchem,
            ),
            pytest.raises(ValueError, match="Could not resolve"),
        ):
            await resolve_compound("definitely_not_a_compound_xyz")

    async def test_prefixed_cas_uses_bare_registry_number_for_pubchem(
        self,
        mock_settings,
    ):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {
            "CID": 2244,
            "IUPACName": "2-acetyloxybenzoic acid",
            "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
            "InChI": "InChI=1S/C9H8O4",
            "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "MolecularFormula": "C9H8O4",
            "MolecularWeight": "180.16",
        }
        mock_pubchem.get_synonyms.return_value = ["aspirin", "50-78-2"]
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("CAS 50-78-2")

        mock_pubchem.resolve_by_name.assert_awaited_once_with("50-78-2")
        assert compound.original_input == "CAS 50-78-2"
        assert compound.input_type == "cas"

    async def test_mixed_case_inchikey_uses_canonical_lookup_form(
        self,
        mock_settings,
    ):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_inchikey.return_value = {
            "CID": 1110,
            "IUPACName": "succinic acid",
            "CanonicalSMILES": "OC(=O)CCC(O)=O",
            "InChI": "InChI=1S/C4H6O4",
            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            "MolecularFormula": "C4H6O4",
            "MolecularWeight": "118.09",
        }
        mock_pubchem.get_synonyms.return_value = ["succinic acid", "110-15-6"]
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("kdyfgrwqoybrfd-uhfffaoysa-n")

        mock_pubchem.resolve_by_inchikey.assert_awaited_once_with("KDYFGRWQOYBRFD-UHFFFAOYSA-N")
        assert compound.original_input == "kdyfgrwqoybrfd-uhfffaoysa-n"
        assert compound.input_type == "inchikey"

    async def test_resolve_by_smiles(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_smiles.return_value = {
            "CID": 1110,
            "IUPACName": "succinic acid",
            "CanonicalSMILES": "OC(=O)CCC(O)=O",
            "InChI": "InChI=1S/C4H6O4",
            "InChIKey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            "MolecularFormula": "C4H6O4",
            "MolecularWeight": "118.09",
        }
        mock_pubchem.get_synonyms.return_value = []
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("OC(=O)CCC(O)=O")

        assert compound.input_type == "smiles"
        assert compound.pubchem_cid == 1110

    async def test_resolve_normalizes_ecmascript_bom_boundaries(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_smiles.return_value = {
            "CID": 702,
            "IUPACName": "ethanol",
            "CanonicalSMILES": "CCO",
            "InChI": "InChI=1S/C2H6O",
            "InChIKey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "MolecularFormula": "C2H6O",
            "MolecularWeight": "46.07",
        }
        mock_pubchem.get_synonyms.return_value = ["ethanol"]
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("\ufeffCCO\ufeff")

        mock_pubchem.resolve_by_smiles.assert_awaited_once_with("CCO")
        assert compound.original_input == "CCO"


class TestCASPattern:
    def test_valid_cas(self):
        assert CAS_PATTERN.match("110-15-6")
        assert CAS_PATTERN.match("50-78-2")
        assert CAS_PATTERN.match("CAS RN 50-78-2")

    def test_invalid_cas(self):
        assert not CAS_PATTERN.match("succinic acid")
        assert not CAS_PATTERN.match("12345")
