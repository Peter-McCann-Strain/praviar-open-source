"""Tests for praviar_pipeline.rendering.structures.render_comparison_png.

These tests verify that the render_comparison_png function correctly
produces PNG bytes (or None) for various SMILES input combinations.
RDKit must be installed for these tests to pass.
"""

# isort: skip_file

from __future__ import annotations

from praviar_pipeline.rendering.structures import render_comparison_png


# Simple, well-known SMILES for testing
ETHANOL = "CCO"
METHANOL = "CO"
ACETIC_ACID = "CC(O)=O"
SUCCINIC_ACID = "OC(=O)CCC(O)=O"
ASPIRIN = "CC(=O)Oc1ccccc1C(O)=O"
BENZENE = "c1ccccc1"


def _is_png(data: bytes) -> bool:
    """Check whether raw bytes start with the PNG magic header."""
    return data[:4] == b"\x89PNG"


class TestRenderComparisonPng:
    """Tests for render_comparison_png side-by-side molecule comparison."""

    def test_returns_png_bytes(self):
        """Basic call with two valid SMILES returns PNG bytes."""
        result = render_comparison_png(ETHANOL, METHANOL)
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 100
        assert _is_png(result)

    def test_identical_molecules(self):
        """Comparing a molecule with itself should still produce a valid PNG."""
        result = render_comparison_png(ETHANOL, ETHANOL)
        assert result is not None
        assert _is_png(result)

    def test_invalid_target_smiles_returns_none(self):
        """Invalid target SMILES should return None, not crash."""
        result = render_comparison_png("INVALID_SMILES!!!", ETHANOL)
        assert result is None

    def test_invalid_patent_smiles_returns_none(self):
        """Invalid patent SMILES should return None, not crash."""
        result = render_comparison_png(ETHANOL, "NOT_A_MOLECULE")
        assert result is None

    def test_both_invalid_returns_none(self):
        """Both SMILES invalid should return None."""
        result = render_comparison_png("XXX", "YYY")
        assert result is None

    def test_empty_target_returns_none(self):
        """Empty target SMILES should return None."""
        result = render_comparison_png("", ETHANOL)
        assert result is None

    def test_empty_patent_returns_none(self):
        """Empty patent SMILES should return None."""
        result = render_comparison_png(ETHANOL, "")
        assert result is None

    def test_structurally_similar_molecules(self):
        """Two related molecules should produce a valid PNG with MCS highlighting."""
        result = render_comparison_png(SUCCINIC_ACID, ACETIC_ACID)
        assert result is not None
        assert _is_png(result)

    def test_structurally_different_molecules(self):
        """Two quite different molecules should still render."""
        result = render_comparison_png(BENZENE, SUCCINIC_ACID)
        assert result is not None
        assert _is_png(result)

    def test_custom_dimensions(self):
        """Custom width/height should still produce valid PNG."""
        result = render_comparison_png(ETHANOL, METHANOL, width=600, height=250)
        assert result is not None
        assert _is_png(result)

    def test_aromatic_vs_aliphatic(self):
        """Aromatic vs aliphatic comparison should work."""
        result = render_comparison_png(ASPIRIN, ETHANOL)
        assert result is not None
        assert _is_png(result)
