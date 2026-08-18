"""Tests for PTAB fail-closed behavior and broader scholarly search.

Tests:
- PTAB auth failure propagates instead of hiding the source gap
- PTAB network failure propagates instead of hiding the source gap
- Scholarly queries include InChIKey prefix for complex molecules
- Scholarly queries include functional group broadening for large molecules
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.pipeline.step6_invalid import (
    _build_scholarly_queries,
    _check_ptab,
)


@pytest.fixture
def semaglutide() -> ResolvedCompound:
    """Semaglutide — a large peptide drug (mol weight >4000)."""
    return ResolvedCompound(
        name="semaglutide",
        canonical_smiles="CC(=O)NCCCC",  # Simplified
        inchi="InChI=1S/C187H291N45O59",
        inchi_key="DLSWIYLPEUIQAV-UHFFFAOYSA-N",
        pubchem_cid=56843331,
        synonyms=["Ozempic", "Wegovy", "Rybelsus"],
        cas_numbers=["910463-68-2"],
        molecular_formula="C187H291N45O59",
        molecular_weight=4113.58,
        functional_groups=["amide", "peptide_bond", "carboxylic_acid"],
        original_input="semaglutide",
        input_type="name",
    )


@pytest.fixture
def small_compound() -> ResolvedCompound:
    """Small molecule for comparison."""
    return ResolvedCompound(
        name="aspirin",
        canonical_smiles="CC(=O)Oc1ccccc1C(O)=O",
        inchi="InChI=1S/C9H8O4",
        inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        pubchem_cid=2244,
        synonyms=["acetylsalicylic acid"],
        cas_numbers=["50-78-2"],
        molecular_formula="C9H8O4",
        molecular_weight=180.16,
        functional_groups=["ester", "carboxylic_acid"],
        original_input="aspirin",
        input_type="name",
    )


class TestPTABFailClosed:
    """PTAB source failures should fail the invalidity evidence step."""

    async def test_auth_error_propagates(self, mock_settings):
        """AuthenticationError should propagate instead of returning empty PTAB evidence."""
        mock_ptab = AsyncMock()
        mock_ptab.get_proceedings.side_effect = AuthenticationError(
            "PTAB API key invalid",
            source="ptab",
        )
        mock_ptab.__aenter__ = AsyncMock(return_value=mock_ptab)
        mock_ptab.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step6_invalid.PTABClient",
            return_value=mock_ptab,
        ):
            with pytest.raises(AuthenticationError):
                await _check_ptab("US7851188B2")

    async def test_network_error_raises_source_unavailable(self, mock_settings):
        """Network errors should surface as source-unavailable coverage gaps."""
        mock_ptab = AsyncMock()
        mock_ptab.get_proceedings.side_effect = httpx.ConnectError("Connection refused")
        mock_ptab.__aenter__ = AsyncMock(return_value=mock_ptab)
        mock_ptab.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step6_invalid.PTABClient",
            return_value=mock_ptab,
        ):
            with pytest.raises(SourceUnavailableError):
                await _check_ptab("US7851188B2")

    async def test_timeout_error_raises_source_unavailable(self, mock_settings):
        """TimeoutError should surface as source-unavailable coverage gaps."""
        mock_ptab = AsyncMock()
        mock_ptab.get_proceedings.side_effect = TimeoutError("Request timed out")
        mock_ptab.__aenter__ = AsyncMock(return_value=mock_ptab)
        mock_ptab.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step6_invalid.PTABClient",
            return_value=mock_ptab,
        ):
            with pytest.raises(SourceUnavailableError):
                await _check_ptab("US7851188B2")

    async def test_successful_ptab_still_works(self, mock_settings):
        """Normal PTAB results should still be returned correctly."""
        mock_ptab = AsyncMock()
        mock_ptab.get_proceedings.return_value = [
            {
                "trialNumber": "IPR2020-00123",
                "trialTypeCode": "IPR",
                "trialMetaData": {
                    "trialTypeCode": "102",
                    "trialStatusCategory": "Final Written Decision",
                },
            },
        ]
        mock_ptab.get_decisions.return_value = [
            {
                "trialNumber": "IPR2020-00123",
                "decisionData": {"decisionTypeCategory": "Final Written Decision"},
            },
        ]
        mock_ptab.__aenter__ = AsyncMock(return_value=mock_ptab)
        mock_ptab.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step6_invalid.PTABClient",
            return_value=mock_ptab,
        ):
            result = await _check_ptab("US7851188B2")

        assert result.has_been_challenged is True
        assert len(result.proceedings) == 1
        assert result.proceedings[0].final_written_decision_verified is True
        assert result.all_claims_cancelled == []


class TestScholarlyQueryBroadening:
    """Test broader scholarly search queries for complex molecules."""

    def test_basic_queries(self, small_compound, mock_settings):
        """Basic compound should have name, synonyms, CAS."""
        queries = _build_scholarly_queries(small_compound)
        assert queries[0] == '"aspirin"'
        assert '"acetylsalicylic acid"' in queries
        assert "50-78-2" in queries

    def test_inchikey_prefix_added(self, small_compound, mock_settings):
        """InChIKey prefix should be added for structural analog search."""
        queries = _build_scholarly_queries(small_compound)
        assert "BSYNRYMUTXBXSQ" in queries

    def test_large_molecule_gets_functional_group_query(self, semaglutide, mock_settings):
        """Large molecules (MW > 500) should get functional group broadening."""
        queries = _build_scholarly_queries(semaglutide)
        # Should have a query with functional groups
        has_group_query = any("amide" in q or "peptide_bond" in q for q in queries)
        assert has_group_query, f"Expected functional group query in {queries}"

    def test_small_molecule_no_functional_group_query(self, small_compound, mock_settings):
        """Small molecules (MW < 500) should NOT get functional group broadening."""
        queries = _build_scholarly_queries(small_compound)
        # Should NOT have functional group broadening
        has_group_query = any("ester" in q and small_compound.name in q for q in queries)
        assert not has_group_query

    def test_query_ordering(self, semaglutide, mock_settings):
        """Queries should be ordered by specificity: name first, then broader."""
        queries = _build_scholarly_queries(semaglutide)
        assert queries[0] == '"semaglutide"'
        # Synonyms should come next
        assert any('"Ozempic"' in q for q in queries[:5])
