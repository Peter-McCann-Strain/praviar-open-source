"""Unit tests for the patent abbreviation expander."""

from __future__ import annotations

import pytest
from rdkit import Chem

from praviar_pipeline.ocsr.abbreviations import (
    expand_superatoms,
    has_placeholder_atoms,
    lookup,
)


class TestLookup:
    def test_known_patent_abbreviation(self) -> None:
        assert lookup("Boc") == "*C(=O)OC(C)(C)C"

    def test_known_rdkit_default(self) -> None:
        # RDKit ships CO2Et as a default
        result = lookup("CO2Et")
        assert result is not None and "C(=O)OCC" in result

    def test_case_insensitive_fallback(self) -> None:
        # "BOC" should fall back to "Boc"
        assert lookup("BOC") == lookup("Boc")

    def test_unknown_label(self) -> None:
        assert lookup("NotARealAbbreviation") is None


class TestHasPlaceholderAtoms:
    def test_star_placeholder(self) -> None:
        assert has_placeholder_atoms("*c1ccccc1")

    def test_uranium_placeholder(self) -> None:
        # MolScribe / MolNeXTR's "unknown atom" sentinel
        assert has_placeholder_atoms("c1ccc(C(=[U])N)cc1")

    def test_clean_smiles(self) -> None:
        assert not has_placeholder_atoms("c1ccccc1")
        assert not has_placeholder_atoms("CC(=O)O")

    def test_empty(self) -> None:
        assert not has_placeholder_atoms("")


class TestExpandSuperatoms:
    def test_passthrough_when_no_placeholders(self) -> None:
        smi = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin
        result = expand_superatoms(smi)
        # RDKit-canonicalises to one of the standard forms
        assert Chem.CanonSmiles(result) == Chem.CanonSmiles(smi)

    def test_boc_expansion(self) -> None:
        # `*c1ccccc1` with label `Boc` → Boc-phenyl
        # SMILES expansion of Boc is `*C(=O)OC(C)(C)C` so attaching to phenyl
        # gives c1ccc(C(=O)OC(C)(C)C)cc1
        out = expand_superatoms("*c1ccccc1", ocr_labels=["Boc"])
        assert "C(C)(C)" in out  # tert-butyl signature
        # round-trips RDKit-canonical
        assert Chem.CanonSmiles(out) == out

    def test_falls_through_when_no_label_works(self) -> None:
        # When OCR labels are nonsense, we leave the SMILES alone (canonicalised)
        out = expand_superatoms("*c1ccccc1", ocr_labels=["GibberishLabel123"])
        assert "*" in out  # placeholder retained

    def test_invalid_smiles_raises(self) -> None:
        with pytest.raises(RuntimeError, match="cannot parse"):
            expand_superatoms("not a valid SMILES")

    def test_no_labels_passthrough(self) -> None:
        # Without OCR labels, we don't guess — leave the placeholder alone
        # but still canonicalise.
        out = expand_superatoms("*c1ccccc1")
        assert "*" in out
