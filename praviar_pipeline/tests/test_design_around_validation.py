"""Unit tests for design-around feasibility validation.

Gates the entire module on RDKit being importable.  If RDKit is absent the
test session continues normally — the module is simply skipped.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rdkit")

from praviar_pipeline.models.analysis_claims import DesignAroundSuggestion
from praviar_pipeline.pipeline.doe.design_around_validation import (
    _TANIMOTO_HIGH,
    _TANIMOTO_LOW,
    validate_design_around,
)

# ---------------------------------------------------------------------------
# Test SMILES constants
# ---------------------------------------------------------------------------

# Aspirin: reasonably complex, well-known, reliably parsed by RDKit.
_ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"

# Salicylic acid: structurally closely related to aspirin (just missing the
# acetyl group).  Morgan r=2 Tanimoto to aspirin is ~0.45, comfortably within
# the pharmacophore-preserved band [0.35, 0.85].  Good representative for the
# "genuine design-around" scenario.
_SALICYLIC_ACID_SMILES = "OC(=O)c1ccccc1O"

# Benzene: structurally very unlike aspirin — scaffold is destroyed.
# Morgan r=2 Tanimoto to aspirin is ~0.125, well below the lower band limit.
_BENZENE_SMILES = "c1ccccc1"

# Definitely invalid SMILES.
_INVALID_SMILES = "NOT_A_SMILES(())"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suggestion(smiles: str | None = None, element_avoided: int = 1) -> DesignAroundSuggestion:
    """Create a minimal DesignAroundSuggestion for testing."""
    return DesignAroundSuggestion(
        element_avoided=element_avoided,
        suggestion="Replace X with Y",
        smiles=smiles,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidateDesignAroundNoSmiles:
    """When no SMILES is provided the suggestion is returned unchanged."""

    def test_returns_same_instance_when_smiles_is_none(self):
        suggestion = _make_suggestion(smiles=None)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        # All structured fields remain None.
        assert result.rdkit_valid is None
        assert result.tanimoto_to_original is None
        assert result.pharmacophore_preserved is None

    def test_original_instance_not_mutated(self):
        suggestion = _make_suggestion(smiles=None)
        validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert suggestion.rdkit_valid is None


class TestValidateDesignAroundInvalidSmiles:
    """An unparseable SMILES is recorded as rdkit_valid=False without raising."""

    def test_invalid_smiles_sets_rdkit_valid_false(self):
        suggestion = _make_suggestion(smiles=_INVALID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.rdkit_valid is False

    def test_invalid_smiles_does_not_raise(self):
        suggestion = _make_suggestion(smiles=_INVALID_SMILES)
        # Must not raise — a bad LLM-generated SMILES is data, not a system error.
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result is not None

    def test_invalid_smiles_tanimoto_is_none(self):
        suggestion = _make_suggestion(smiles=_INVALID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.tanimoto_to_original is None

    def test_invalid_smiles_pharmacophore_preserved_is_false(self):
        suggestion = _make_suggestion(smiles=_INVALID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.pharmacophore_preserved is False


class TestValidateDesignAroundValidSmiles:
    """A valid SMILES is parsed and Tanimoto / pharmacophore fields are populated."""

    def test_valid_smiles_sets_rdkit_valid_true(self):
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.rdkit_valid is True

    def test_valid_smiles_tanimoto_in_unit_interval(self):
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.tanimoto_to_original is not None
        assert 0.0 <= result.tanimoto_to_original <= 1.0

    def test_reasonable_tanimoto_mid_range_structure(self):
        """Salicylic acid vs aspirin: closely related, sits in the mid-range band."""
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        # We do not assert the exact value (brittle against RDKit version
        # differences), but we confirm it is non-trivially above zero and
        # below identity, and falls within the pharmacophore-preserved band.
        assert result.tanimoto_to_original is not None
        assert result.tanimoto_to_original > 0.0
        assert result.tanimoto_to_original < 1.0
        assert result.pharmacophore_preserved is True

    def test_identical_smiles_gives_tanimoto_one(self):
        suggestion = _make_suggestion(smiles=_ASPIRIN_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.tanimoto_to_original == pytest.approx(1.0)

    def test_identical_smiles_pharmacophore_preserved_is_false(self):
        """Tanimoto == 1.0 exceeds the upper band, so no real change was made."""
        suggestion = _make_suggestion(smiles=_ASPIRIN_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        # Should be False because Tanimoto > _TANIMOTO_HIGH (no genuine design-around).
        assert result.pharmacophore_preserved is False

    def test_element_number_preserved(self):
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES, element_avoided=3)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.element_avoided == 3


class TestPharmacophorePreservationBand:
    """Tests covering the three regions of the Tanimoto band heuristic.

    The three regions are:
      below _TANIMOTO_LOW  -- scaffold destroyed (pharmacophore_preserved=False)
      [_TANIMOTO_LOW, _TANIMOTO_HIGH] -- genuine design-around (pharmacophore_preserved=True)
      above _TANIMOTO_HIGH -- no real change (pharmacophore_preserved=False)

    Test compounds against aspirin (Morgan r=2):
      benzene        ~0.125 -- below lower bound (scaffold destroyed)
      salicylic acid ~0.448 -- within band (pharmacophore preserved)
      aspirin itself  1.000 -- above upper bound (identical, no change)
    """

    def test_scaffold_destroying_structure_pharmacophore_not_preserved(self):
        """Benzene is too dissimilar from aspirin: scaffold destroyed."""
        suggestion = _make_suggestion(smiles=_BENZENE_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        # Morgan r=2 Tanimoto benzene vs aspirin is ~0.125, well below 0.35.
        assert result.rdkit_valid is True
        assert result.tanimoto_to_original is not None
        assert result.tanimoto_to_original < _TANIMOTO_LOW, (
            f"Expected benzene/aspirin Tanimoto < {_TANIMOTO_LOW}, "
            f"got {result.tanimoto_to_original:.4f}"
        )
        assert result.pharmacophore_preserved is False

    def test_mid_band_structure_pharmacophore_preserved(self):
        """Salicylic acid vs aspirin: mid-range Tanimoto, genuine design-around."""
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.rdkit_valid is True
        assert result.tanimoto_to_original is not None
        # Morgan r=2 Tanimoto is ~0.448, within [0.35, 0.85].
        assert _TANIMOTO_LOW <= result.tanimoto_to_original <= _TANIMOTO_HIGH, (
            f"Expected salicylic acid/aspirin Tanimoto in [{_TANIMOTO_LOW}, {_TANIMOTO_HIGH}], "
            f"got {result.tanimoto_to_original:.4f}"
        )
        assert result.pharmacophore_preserved is True

    def test_identical_structure_above_upper_band_pharmacophore_not_preserved(self):
        """Aspirin vs itself: Tanimoto = 1.0, no real structural change."""
        suggestion = _make_suggestion(smiles=_ASPIRIN_SMILES)
        result = validate_design_around(suggestion, _ASPIRIN_SMILES)
        assert result.tanimoto_to_original == pytest.approx(1.0)
        assert result.tanimoto_to_original > _TANIMOTO_HIGH
        assert result.pharmacophore_preserved is False

    def test_tanimoto_band_constants_are_sensible(self):
        """Confirm the module-level constants satisfy the documented invariant."""
        assert 0.0 < _TANIMOTO_LOW < _TANIMOTO_HIGH < 1.0


class TestValidateDesignAroundInvalidOriginalSmiles:
    """An invalid original compound SMILES is a data-integrity error and must raise."""

    def test_invalid_original_smiles_raises_value_error(self):
        suggestion = _make_suggestion(smiles=_SALICYLIC_ACID_SMILES)
        with pytest.raises(ValueError, match="Original compound SMILES"):
            validate_design_around(suggestion, "NOT_VALID")
