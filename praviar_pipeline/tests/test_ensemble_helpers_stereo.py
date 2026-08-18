"""Tests for modal-stereo selection in ``pick_best_stereo``.

When a vote-equivalent group contains multiple candidates with opposing E/Z
bond directions (``C/C=C/C`` vs ``C/C=C\\C``), the picker must choose the
modal isomeric SMILES rather than whichever direction comes from the
highest-weight voter.
"""

from __future__ import annotations

from praviar_pipeline.ocsr.ensemble_helpers import pick_best_stereo


def test_modal_direction_wins_over_weight() -> None:
    """3 voters with `/`, 1 with `\\` whose weight is highest — modal `/` wins."""
    candidates = [
        ("molscribe", "C/C=C/C", 0.9),
        ("decimer", "C/C=C/C", 0.85),
        ("molnextr", "C/C=C/C", 0.8),
        ("molsight", "C/C=C\\C", 0.95),  # highest weight, minority direction
    ]
    weights = {
        "molscribe": 0.7,
        "decimer": 0.65,
        "molnextr": 0.7,
        "molsight": 0.95,  # heaviest voter
    }
    result = pick_best_stereo(list(candidates), weights)
    assert result == "C/C=C/C", (
        f"Expected modal `/` direction to win over heaviest minority voter, got {result!r}"
    )


def test_single_stereo_candidate_unchanged() -> None:
    """Only one E/Z voter — existing tier-then-weight selection still applies."""
    candidates = [
        ("molscribe", "CC=CC", 0.8),
        ("molsight", "C/C=C/C", 0.85),  # only stereo voter
        ("decimer", "CC=CC", 0.7),
        ("molnextr", "CC=CC", 0.75),
    ]
    weights = {
        "molscribe": 0.7,
        "molsight": 0.9,
        "decimer": 0.65,
        "molnextr": 0.7,
    }
    result = pick_best_stereo(list(candidates), weights)
    assert result == "C/C=C/C", (
        f"Single E/Z candidate should be selected by stereo-tier preference, got {result!r}"
    )


def test_tie_on_count_weight_breaks_tie() -> None:
    """2 voters with `/`, 2 with `\\` — modal tie broken by summed voter weight."""
    candidates = [
        ("molscribe", "C/C=C/C", 0.9),
        ("molsight", "C/C=C/C", 0.85),
        ("decimer", "C/C=C\\C", 0.8),
        ("molnextr", "C/C=C\\C", 0.7),
    ]
    # `/` group total weight: 0.9 + 0.95 = 1.85
    # `\` group total weight: 0.65 + 0.7  = 1.35
    weights = {
        "molscribe": 0.9,
        "molsight": 0.95,
        "decimer": 0.65,
        "molnextr": 0.7,
    }
    result = pick_best_stereo(list(candidates), weights)
    assert result == "C/C=C/C", (
        f"On count tie the heavier-weight isomeric group should win, got {result!r}"
    )


def test_no_stereo_input_picks_highest_weight() -> None:
    """No E/Z markers anywhere — fall through to highest-weight tool."""
    candidates = [
        ("molscribe", "CCO", 0.8),
        ("molsight", "CCO", 0.85),
        ("decimer", "CCO", 0.7),
        ("molnextr", "CCO", 0.75),
    ]
    weights = {
        "molscribe": 0.6,
        "molsight": 0.99,  # heaviest
        "decimer": 0.5,
        "molnextr": 0.55,
    }
    result = pick_best_stereo(list(candidates), weights)
    assert result == "CCO"


def test_postmortem_us20020103189a1_88_3_regression() -> None:
    """Direct regression from the failure case that motivated Fix B.

    GT had ``CCC(O/N=c1/c2...)`` — the `/c1/c2` direction. Pred locked in
    ``CCC(O/N=c1\\c2...)`` because ensemble majority used flat keys and the
    minority-direction voter happened to have the highest tool weight.
    """
    gt_smi = "CCC(=O)O/N=c1/sc2ccccc2n1C"
    flipped = "CCC(=O)O/N=c1\\sc2ccccc2n1C"

    candidates = [
        ("molscribe", gt_smi, 0.88),
        ("decimer", gt_smi, 0.84),
        ("molnextr", gt_smi, 0.82),
        ("molgrapher", gt_smi, 0.80),
        ("molsight", flipped, 0.92),  # minority direction, heaviest voter
    ]
    weights = {
        "molscribe": 0.732,
        "decimer": 0.650,
        "molnextr": 0.698,
        "molgrapher": 0.798,
        "molsight": 0.918,  # heaviest under default weights
    }
    result = pick_best_stereo(list(candidates), weights)
    assert result == gt_smi, (
        f"Modal stereo selection must pick the 4-of-5 GT direction, got {result!r}"
    )
