"""Fail-closed validation tests for MarkushGrapher shadow predictions."""

from __future__ import annotations

import pytest

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble_helpers import collect_valid_predictions
from praviar_pipeline.ocsr.workers.markushgrapher_worker import (
    _validate_decoded_structure,
)


def test_plain_smiles_can_be_syntax_validated() -> None:
    assert _validate_decoded_structure("CCO") == (True, False, "passed")


def test_malformed_full_cxsmiles_fails() -> None:
    valid, is_markush, status = _validate_decoded_structure("*C |$R1;$")
    assert (valid, is_markush, status) == (False, True, "failed")


@pytest.mark.parametrize(
    "prediction",
    [
        # Parseable R-group output still needs a reference to detect label
        # transposition or a label attached to the wrong atom.
        "*C |$R1;$|",
        "*C |$;R1$|",
        "*C |$R1;R2$|",
        # RDKit silently drops positional variation, so this can never pass
        # local validation.
        "C[*].C1CCCCC1 |$;R1;;;;;;;$,m:0:2.3.4.5.6.7|",
        # Frequency groups also require reference-aware semantic comparison.
        "*COC(*)=O |$<AP>;;;;<AP>;$,Sg:n:1:n:ht|",
    ],
)
def test_markush_features_remain_reference_required(prediction: str) -> None:
    valid, is_markush, status = _validate_decoded_structure(prediction)
    assert valid is False
    assert is_markush is True
    assert status in {"failed", "reference_required"}


def test_unavailable_confidence_is_explicit_and_cannot_enter_ensemble() -> None:
    result = OCSRResult(
        smiles="CCO",
        confidence=0.0,
        confidence_available=False,
        valid=True,
        tool="markushgrapher",
    )
    valid, vote_keys = collect_valid_predictions({"markushgrapher": result})
    assert valid == {}
    assert vote_keys == {}


def test_unavailable_confidence_rejects_nonzero_score() -> None:
    with pytest.raises(ValueError, match="unavailable confidence"):
        OCSRResult(
            smiles="CCO",
            confidence=0.8,
            confidence_available=False,
            valid=True,
            tool="markushgrapher",
        )
