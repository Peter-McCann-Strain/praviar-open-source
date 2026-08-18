"""Tests for extract_text_smiles_signal (Phase C text fusion)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.pipeline.drawings.structure_analysis_helpers import (
    extract_text_smiles_signal,
)


class TestExtractTextSmilesSignal:
    """Validates the text → SMILES producer that unlocks the
    ensemble:text_confirmed_{tool} code path."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        smi, err = await extract_text_smiles_signal("")
        assert smi == ""
        assert err is None

    @pytest.mark.asyncio
    async def test_resolves_iupac_name_via_opsin(self):
        patent_text = "The compound is ethanol, a common solvent."
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=["ethanol"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.opsin_resolve",
                new=AsyncMock(return_value="CCO"),
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=[],
            ),
        ):
            smi, err = await extract_text_smiles_signal(patent_text)
        assert smi == "CCO"
        assert err is None

    @pytest.mark.asyncio
    async def test_falls_back_to_cas_when_names_fail(self):
        patent_text = "CAS 64-17-5 is ethanol."
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=["nonsense-name-does-not-resolve"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.opsin_resolve",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=["64-17-5"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation_clients._pubchem_cas_lookup",
                new=AsyncMock(return_value="CCO"),
            ),
        ):
            smi, err = await extract_text_smiles_signal(patent_text)
        assert smi == "CCO"
        assert err is None

    @pytest.mark.asyncio
    async def test_respects_max_names_cap(self):
        """max_names=2 should only call opsin twice even if 5 names extracted."""
        names = [f"compound-{i}" for i in range(5)]
        opsin = AsyncMock(return_value=None)
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=names,
            ),
            patch("praviar_pipeline.ocsr.text_validation.opsin_resolve", new=opsin),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=[],
            ),
        ):
            await extract_text_smiles_signal("text", max_names=2)
        assert opsin.await_count == 2

    @pytest.mark.asyncio
    async def test_respects_max_cas_cap(self):
        cas = [f"100-00-{i}" for i in range(10)]
        pubchem = AsyncMock(return_value=None)
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=[],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=cas,
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation_clients._pubchem_cas_lookup",
                new=pubchem,
            ),
        ):
            await extract_text_smiles_signal("text", max_cas=3)
        assert pubchem.await_count == 3

    @pytest.mark.asyncio
    async def test_opsin_exception_falls_through(self):
        """Transient OPSIN error should not raise; move to next candidate or CAS."""
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=["ethanol"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.opsin_resolve",
                new=AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=[],
            ),
        ):
            smi, err = await extract_text_smiles_signal("text")
        assert smi == ""
        assert err is None

    @pytest.mark.asyncio
    async def test_canonicalises_result(self):
        """OPSIN may return non-canonical SMILES; output must be RDKit-canonical."""
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=["benzene"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.opsin_resolve",
                new=AsyncMock(return_value="c1ccccc1"),
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=[],
            ),
        ):
            smi, err = await extract_text_smiles_signal("text")
        # RDKit canonical form of benzene
        assert smi == "c1ccccc1"
        assert err is None

    @pytest.mark.asyncio
    async def test_invalid_smiles_from_opsin_is_skipped(self):
        with (
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_chemical_names",
                return_value=["garbage-name"],
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.opsin_resolve",
                new=AsyncMock(return_value="NOT_A_SMILES"),
            ),
            patch(
                "praviar_pipeline.ocsr.text_validation.extract_cas_numbers",
                return_value=[],
            ),
        ):
            smi, _err = await extract_text_smiles_signal("text")
        assert smi == ""
