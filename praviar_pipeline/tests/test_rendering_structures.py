"""Tests for praviar_pipeline.rendering.structures -- chemical structure SVG/PNG generation."""

from __future__ import annotations

import pytest

rdkit = pytest.importorskip("rdkit")

from praviar_pipeline.rendering.structures import (  # noqa: E402
    _mol_from_smiles,
    render_comparison_svg,
    render_compound_png,
    render_compound_svg,
    render_substructure_svg,
)

# ---------------------------------------------------------------------------
# Test SMILES constants
# ---------------------------------------------------------------------------

ETHANOL_SMILES = "CCO"
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE_SMILES = "Cn1c(=O)c2c(ncn2C)n(C)c1=O"
BENZENE_SMILES = "c1ccccc1"
INVALID_SMILES = "INVALID_SMILES_XYZ"


# ---------------------------------------------------------------------------
# Tests: _mol_from_smiles
# ---------------------------------------------------------------------------


class TestMolFromSmiles:
    """Tests for the internal SMILES parser."""

    def test_valid_smiles_returns_mol(self):
        """Valid SMILES should return a non-None Mol object."""
        mol = _mol_from_smiles(ETHANOL_SMILES)
        assert mol is not None

    def test_valid_complex_smiles(self):
        """Complex SMILES (aspirin) should parse successfully."""
        mol = _mol_from_smiles(ASPIRIN_SMILES)
        assert mol is not None

    def test_invalid_smiles_returns_none(self):
        """Invalid SMILES should return None."""
        mol = _mol_from_smiles(INVALID_SMILES)
        assert mol is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        mol = _mol_from_smiles("")
        assert mol is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string should return None."""
        mol = _mol_from_smiles("   ")
        assert mol is None

    def test_smiles_with_whitespace_stripped(self):
        """SMILES with leading/trailing whitespace should be stripped and parsed."""
        mol = _mol_from_smiles("  CCO  ")
        assert mol is not None


# ---------------------------------------------------------------------------
# Tests: render_compound_svg
# ---------------------------------------------------------------------------


class TestRenderCompoundSvg:
    """Tests for single compound SVG rendering."""

    def test_valid_smiles_returns_svg(self):
        """Valid SMILES should produce an SVG string."""
        result = render_compound_svg(ETHANOL_SMILES)
        assert result is not None
        assert isinstance(result, str)

    def test_svg_starts_with_xml_or_svg(self):
        """SVG output should start with XML declaration or <svg tag."""
        result = render_compound_svg(ETHANOL_SMILES)
        assert result is not None
        stripped = result.strip()
        assert stripped.startswith("<?xml") or stripped.startswith("<svg")

    def test_svg_contains_svg_element(self):
        """SVG output should contain an <svg element."""
        result = render_compound_svg(ETHANOL_SMILES)
        assert result is not None
        assert "<svg" in result

    def test_invalid_smiles_returns_none(self):
        """Invalid SMILES should return None."""
        result = render_compound_svg(INVALID_SMILES)
        assert result is None

    def test_empty_smiles_returns_none(self):
        """Empty SMILES should return None."""
        result = render_compound_svg("")
        assert result is None

    def test_complex_molecule_renders(self):
        """Complex molecule (aspirin) should render successfully."""
        result = render_compound_svg(ASPIRIN_SMILES)
        assert result is not None
        assert "<svg" in result

    def test_caffeine_renders(self):
        """Caffeine SMILES should render successfully."""
        result = render_compound_svg(CAFFEINE_SMILES)
        assert result is not None
        assert "<svg" in result

    def test_custom_dimensions(self):
        """Custom width and height should produce SVG."""
        result = render_compound_svg(ETHANOL_SMILES, width=300, height=200)
        assert result is not None
        assert "<svg" in result

    def test_svg_is_nonempty(self):
        """SVG output should be non-trivial (more than a few bytes)."""
        result = render_compound_svg(ETHANOL_SMILES)
        assert result is not None
        assert len(result) > 100


# ---------------------------------------------------------------------------
# Tests: render_compound_png
# ---------------------------------------------------------------------------


class TestRenderCompoundPng:
    """Tests for single compound PNG rendering."""

    def test_valid_smiles_returns_bytes(self):
        """Valid SMILES should produce PNG bytes."""
        result = render_compound_png(ETHANOL_SMILES)
        assert result is not None
        assert isinstance(result, bytes)

    def test_png_magic_bytes(self):
        """PNG output should start with the PNG magic header."""
        result = render_compound_png(ETHANOL_SMILES)
        assert result is not None
        assert result[:4] == b"\x89PNG"

    def test_invalid_smiles_returns_none(self):
        """Invalid SMILES should return None."""
        result = render_compound_png(INVALID_SMILES)
        assert result is None

    def test_empty_smiles_returns_none(self):
        """Empty SMILES should return None."""
        result = render_compound_png("")
        assert result is None

    def test_aspirin_renders(self):
        """Aspirin should render to PNG successfully."""
        result = render_compound_png(ASPIRIN_SMILES)
        assert result is not None
        assert result[:4] == b"\x89PNG"

    def test_png_nonempty(self):
        """PNG output should be non-trivial size."""
        result = render_compound_png(ETHANOL_SMILES)
        assert result is not None
        assert len(result) > 100


# ---------------------------------------------------------------------------
# Tests: render_comparison_svg
# ---------------------------------------------------------------------------


class TestRenderComparisonSvg:
    """Tests for side-by-side comparison SVG with MCS highlighting."""

    def test_two_valid_smiles_returns_svg(self):
        """Two valid SMILES should produce a comparison SVG."""
        result = render_comparison_svg(ASPIRIN_SMILES, BENZENE_SMILES)
        assert result is not None
        assert isinstance(result, str)

    def test_comparison_svg_contains_svg_element(self):
        """Comparison SVG should contain an <svg element."""
        result = render_comparison_svg(ASPIRIN_SMILES, BENZENE_SMILES)
        assert result is not None
        assert "<svg" in result

    def test_invalid_target_returns_none(self):
        """Invalid target SMILES should return None."""
        result = render_comparison_svg(INVALID_SMILES, BENZENE_SMILES)
        assert result is None

    def test_invalid_patent_returns_none(self):
        """Invalid patent SMILES should return None."""
        result = render_comparison_svg(ASPIRIN_SMILES, INVALID_SMILES)
        assert result is None

    def test_both_invalid_returns_none(self):
        """Both invalid SMILES should return None."""
        result = render_comparison_svg(INVALID_SMILES, INVALID_SMILES)
        assert result is None

    def test_empty_target_returns_none(self):
        """Empty target SMILES should return None."""
        result = render_comparison_svg("", BENZENE_SMILES)
        assert result is None

    def test_empty_patent_returns_none(self):
        """Empty patent SMILES should return None."""
        result = render_comparison_svg(ASPIRIN_SMILES, "")
        assert result is None

    def test_same_molecule_comparison(self):
        """Comparing a molecule with itself should produce SVG (no diff atoms)."""
        result = render_comparison_svg(ETHANOL_SMILES, ETHANOL_SMILES)
        assert result is not None
        assert "<svg" in result

    def test_similar_molecules(self):
        """Comparison of structurally similar molecules should produce SVG."""
        # Aspirin vs salicylic acid
        result = render_comparison_svg(ASPIRIN_SMILES, "OC(=O)c1ccccc1O")
        assert result is not None
        assert "<svg" in result

    def test_custom_dimensions(self):
        """Custom width and height should produce SVG."""
        result = render_comparison_svg(ASPIRIN_SMILES, BENZENE_SMILES, width=1200, height=500)
        assert result is not None
        assert "<svg" in result


# ---------------------------------------------------------------------------
# Tests: render_substructure_svg
# ---------------------------------------------------------------------------


class TestRenderSubstructureSvg:
    """Tests for substructure highlighting SVG rendering."""

    def test_valid_match_returns_svg(self):
        """Valid molecule with matching SMARTS should produce SVG."""
        # Benzene ring in aspirin
        result = render_substructure_svg(ASPIRIN_SMILES, "c1ccccc1")
        assert result is not None
        assert isinstance(result, str)

    def test_svg_contains_svg_element(self):
        """Substructure SVG should contain an <svg element."""
        result = render_substructure_svg(ASPIRIN_SMILES, "c1ccccc1")
        assert result is not None
        assert "<svg" in result

    def test_no_match_returns_none(self):
        """SMARTS with no match in molecule should return None."""
        # Nitrogen heterocycle in ethanol (no match)
        result = render_substructure_svg(ETHANOL_SMILES, "[nR]1cccc1")
        assert result is None

    def test_invalid_smiles_returns_none(self):
        """Invalid molecule SMILES should return None."""
        result = render_substructure_svg(INVALID_SMILES, "c1ccccc1")
        assert result is None

    def test_invalid_smarts_returns_none(self):
        """Invalid SMARTS pattern should return None."""
        result = render_substructure_svg(ASPIRIN_SMILES, "[[[INVALID")
        assert result is None

    def test_empty_smarts_returns_none(self):
        """Empty SMARTS string should return None."""
        result = render_substructure_svg(ASPIRIN_SMILES, "")
        assert result is None

    def test_empty_smiles_returns_none(self):
        """Empty SMILES string should return None."""
        result = render_substructure_svg("", "c1ccccc1")
        assert result is None

    def test_hydroxyl_substructure(self):
        """Hydroxyl group SMARTS in ethanol should match."""
        result = render_substructure_svg(ETHANOL_SMILES, "[OH]")
        assert result is not None
        assert "<svg" in result

    def test_carboxylic_acid_in_aspirin(self):
        """Carboxylic acid SMARTS in aspirin should match."""
        result = render_substructure_svg(ASPIRIN_SMILES, "[CX3](=O)[OX2H1]")
        assert result is not None
        assert "<svg" in result

    def test_custom_dimensions(self):
        """Custom width and height should produce SVG."""
        result = render_substructure_svg(ASPIRIN_SMILES, "c1ccccc1", width=600, height=500)
        assert result is not None
        assert "<svg" in result
