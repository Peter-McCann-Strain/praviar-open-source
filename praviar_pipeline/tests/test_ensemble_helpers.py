"""Tests for pure OCSR ensemble helper logic."""

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble import DEFAULT_WEIGHTS, calibrate_confidence, fuse
from praviar_pipeline.ocsr.ensemble_helpers import copy_weights, vote_key


def test_copy_weights_does_not_alias_defaults() -> None:
    weights = copy_weights(None)
    weights["molscribe"] = 1.0
    assert DEFAULT_WEIGHTS["molscribe"] != 1.0


def test_vote_key_groups_salt_forms() -> None:
    assert vote_key("CCO.Cl") == vote_key("CCO")


def test_fuse_with_text_formula_does_not_mutate_default_weights() -> None:
    result = fuse(
        {
            "molscribe": OCSRResult(smiles="CCO", confidence=0.9, valid=True),
            "molsight": OCSRResult(smiles="CCO", confidence=0.8, valid=True),
        },
        text_formula="C2H6O",
    )
    assert result.valid
    assert DEFAULT_WEIGHTS["molscribe"] == 0.732


def test_calibrate_confidence_unknown_model_is_identity() -> None:
    assert calibrate_confidence(0.42, "unknown_tool") == 0.42
