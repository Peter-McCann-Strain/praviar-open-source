"""Tests for biologic compound detection and Purple Book routing in Step 1."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.clients.openfda_gsrs import GSRSBiologicIdentity
from praviar_pipeline.pipeline.step1_resolve import (
    _classify_compound,
    _is_biologic_name,
    resolve_compound,
)


def _make_purple_book_mock(lookup_result: dict | None) -> AsyncMock:
    """Create a mock for load_purple_book that returns sync lookup_biologic."""
    mock_index = MagicMock()
    mock_index.lookup_biologic.return_value = lookup_result
    mock_load = AsyncMock(return_value=mock_index)
    return mock_load


def _make_gsrs_client_mock(
    identity: GSRSBiologicIdentity | None,
) -> MagicMock:
    client = AsyncMock()
    client.resolve_exact_biologic.return_value = identity
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


def _gsrs_identity(name: str = "SOME_LARGE_PROTEIN") -> GSRSBiologicIdentity:
    return GSRSBiologicIdentity(
        preferred_name=name,
        aliases=[],
        unii="AAAAAAAAAA",
        uuid="00000000-0000-0000-0000-000000000001",
        substance_class="protein",
        definition_type="PRIMARY",
        definition_level="COMPLETE",
        record_version="1",
        names_last_updated="2026-07-25",
        record_last_updated="2025-09-19",
        protein_subunit_sequences=["ACDEFGHIKLMNPQRSTVWY"],
    )


class TestIsBiologicName:
    def test_monoclonal_antibody_mab(self):
        assert _is_biologic_name("adalimumab") is True
        assert _is_biologic_name("trastuzumab") is True
        assert _is_biologic_name("bevacizumab") is True

    def test_chimeric_antibody_ximab(self):
        assert _is_biologic_name("rituximab") is True
        assert _is_biologic_name("infliximab") is True

    def test_humanized_antibody_zumab(self):
        assert _is_biologic_name("pertuzumab") is True

    def test_fusion_protein_cept(self):
        assert _is_biologic_name("etanercept") is True
        assert _is_biologic_name("aflibercept") is True

    def test_enzyme_ase(self):
        assert _is_biologic_name("agalsidase") is True

    def test_peptide_tide(self):
        assert _is_biologic_name("octreotide") is True

    def test_small_molecule_names(self):
        assert _is_biologic_name("aspirin") is False
        assert _is_biologic_name("ibuprofen") is False
        assert _is_biologic_name("metformin") is False
        assert _is_biologic_name("succinic acid") is False

    def test_case_insensitive(self):
        assert _is_biologic_name("Adalimumab") is True
        assert _is_biologic_name("TRASTUZUMAB") is True

    def test_with_suffix_no_dash(self):
        assert _is_biologic_name("adalimumab") is True

    def test_poetin_suffix(self):
        assert _is_biologic_name("epoetin") is True

    def test_stim_suffix(self):
        assert _is_biologic_name("filgrastim") is True


class TestClassifyCompound:
    def test_biologic_by_name(self):
        assert _classify_compound("adalimumab", "CC(=O)O", 150000.0) == "biologic"

    def test_biologic_by_weight(self):
        assert _classify_compound("some_protein", "CC(=O)O", 50000.0) == "biologic"

    def test_peptide_by_weight(self):
        assert _classify_compound("some_peptide_x", "CC(=O)O", 7000.0) == "peptide"

    def test_biologic_no_smiles(self):
        assert _classify_compound("unknown_bio", "", None) == "biologic"

    def test_small_molecule(self):
        assert _classify_compound("aspirin", "CC(=O)Oc1ccccc1C(O)=O", 180.16) == "small_molecule"

    def test_small_molecule_moderate_weight(self):
        assert _classify_compound("taxol", "CC(=O)OCCCCC", 4000.0) == "small_molecule"


class TestResolveBiologic:
    @pytest.fixture(autouse=True)
    def _reset_purple_book(self):
        from praviar_pipeline.clients.purple_book import reset_purple_book_cache

        reset_purple_book_cache()
        yield
        reset_purple_book_cache()

    async def test_biologic_name_skips_pubchem(self, mock_settings):
        mock_load = _make_purple_book_mock(
            {
                "product_name": "Humira",
                "proper_name": "adalimumab",
                "bla_number": "125057",
                "applicant": "AbbVie Inc.",
                "bla_type": "351(a)",
                "dosage_form": "Injection",
                "route": "Subcutaneous",
                "strength": "40MG/0.8ML",
                "marketing_status": "Rx",
                "approval_date": "31-Dec-02",
                "reference_product": "N/A",
                "exclusivity_expiration": "",
                "orphan_exclusivity_expiration": "",
                "biosimilar_count": 10,
            }
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(_gsrs_identity("adalimumab")),
            ),
        ):
            compound = await resolve_compound("adalimumab")

        assert compound.compound_type == "biologic"
        assert compound.bla_number == "125057"
        assert compound.name == "adalimumab"
        assert compound.biosimilar_count == 10
        assert compound.canonical_smiles == ""
        assert compound.morgan_fp == ""
        assert compound.pubchem_cid is None
        assert compound.protein_subunit_sequences == ["ACDEFGHIKLMNPQRSTVWY"]

    async def test_biologic_name_no_purple_book_match(self, mock_settings):
        mock_load = _make_purple_book_mock(None)

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(None),
            ),
            pytest.raises(ValueError, match="primary, complete FDA GSRS"),
        ):
            await resolve_compound("somemab")

    async def test_biologic_without_purple_book_uses_exact_gsrs_record(self, mock_settings):
        mock_load = _make_purple_book_mock(None)
        identity = _gsrs_identity("EXAMPLEMAB")

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(identity),
            ),
        ):
            compound = await resolve_compound("examplemab")

        assert compound.name == "EXAMPLEMAB"
        assert compound.unii == "AAAAAAAAAA"
        assert compound.gsrs_uuid == "00000000-0000-0000-0000-000000000001"
        assert compound.gsrs_substance_class == "protein"
        assert compound.gsrs_definition_type == "PRIMARY"
        assert compound.gsrs_definition_level == "COMPLETE"
        assert compound.bla_number == ""

    async def test_small_molecule_not_routed_to_biologic(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {
            "CID": 2244,
            "IUPACName": "aspirin",
            "CanonicalSMILES": "CC(=O)Oc1ccccc1C(O)=O",
            "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
            "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "MolecularFormula": "C9H8O4",
            "MolecularWeight": "180.16",
        }
        mock_pubchem.get_synonyms.return_value = ["aspirin", "50-78-2"]
        mock_pubchem.similarity_search.return_value = []
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
            return_value=mock_pubchem,
        ):
            compound = await resolve_compound("aspirin")

        assert compound.compound_type == "small_molecule"
        assert compound.bla_number == ""
        assert compound.pubchem_cid == 2244
        assert compound.canonical_smiles != ""

    async def test_pubchem_failure_falls_back_to_purple_book(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {}
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        mock_load = _make_purple_book_mock(
            {
                "product_name": "Herceptin",
                "proper_name": "trastuzumab",
                "bla_number": "103792",
                "applicant": "Genentech",
                "bla_type": "351(a)",
                "dosage_form": "For Injection",
                "route": "Intravenous",
                "strength": "420MG",
                "marketing_status": "Rx",
                "approval_date": "25-Sep-98",
                "reference_product": "N/A",
                "exclusivity_expiration": "",
                "orphan_exclusivity_expiration": "",
                "biosimilar_count": 5,
            }
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
                return_value=mock_pubchem,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(_gsrs_identity("trastuzumab")),
            ),
        ):
            compound = await resolve_compound("Herceptin")

        assert compound.compound_type == "biologic"
        assert compound.bla_number == "103792"

    async def test_high_mw_post_pubchem_routes_to_biologic(self, mock_settings):
        mock_pubchem = AsyncMock()
        mock_pubchem.resolve_by_name.return_value = {
            "CID": 99999,
            "IUPACName": "some_large_protein",
            "CanonicalSMILES": "CCCC",
            "InChI": "InChI=1S/test",
            "InChIKey": "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
            "MolecularFormula": "C100H200",
            "MolecularWeight": "50000.0",
        }
        mock_pubchem.close = AsyncMock()
        mock_pubchem.__aenter__ = AsyncMock(return_value=mock_pubchem)
        mock_pubchem.__aexit__ = AsyncMock(return_value=False)

        mock_load = _make_purple_book_mock(None)

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.PubChemClient",
                return_value=mock_pubchem,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(_gsrs_identity()),
            ),
        ):
            compound = await resolve_compound("some_large_protein")

        assert compound.compound_type == "biologic"
        assert compound.pubchem_cid == 99999

    async def test_biologic_model_fields(self, mock_settings):
        mock_load = _make_purple_book_mock(
            {
                "product_name": "Rituxan",
                "proper_name": "rituximab",
                "bla_number": "103705",
                "applicant": "Genentech",
                "bla_type": "351(a)",
                "dosage_form": "Injection",
                "route": "Intravenous",
                "strength": "100MG/10ML",
                "marketing_status": "Rx",
                "approval_date": "26-Nov-97",
                "reference_product": "N/A",
                "exclusivity_expiration": "",
                "orphan_exclusivity_expiration": "",
                "biosimilar_count": 3,
            }
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step1_resolve.load_purple_book",
                mock_load,
            ),
            patch(
                "praviar_pipeline.pipeline.step1_resolve.OpenFDAGSRSClient",
                return_value=_make_gsrs_client_mock(_gsrs_identity("rituximab")),
            ),
        ):
            compound = await resolve_compound("rituximab")

        assert compound.compound_type == "biologic"
        assert compound.bla_number == "103705"
        assert compound.reference_product == "N/A"
        assert compound.biosimilar_count == 3
        assert compound.input_type == "name"
        assert compound.original_input == "rituximab"
        assert "Rituxan" in compound.synonyms
