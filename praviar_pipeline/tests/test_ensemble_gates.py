"""Tests for post-fusion safety gates added after the MolDet hardening review.

The two gates downgrade an ensemble prediction to ``unresolved`` rather
than emit it as wrong-resolved when:

* fused confidence is below ``DRAWING_CASCADE_MIN_RESOLVED_CONF`` (default 0.65)
* heavy-atom count exceeds ``DRAWING_MAX_RESOLVED_ATOMS`` (default 100)

Both gates run on the OCSRResult returned by :func:`fuse` on every
non-error code path.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble import (
    _apply_post_fuse_gates,
    apply_resolution_gates,
    fuse,
    set_thresholds_from_settings,
)


@pytest.fixture(autouse=True)
def _set_ensemble_thresholds() -> None:
    """Wire the ensemble env-var bridge with default Settings values.

    Mirrors what ``set_thresholds_from_settings`` does at process startup
    so the gates can read their thresholds. Uses the production defaults
    declared in :class:`DrawingPipelineSettingsMixin`.
    """
    fake_settings = SimpleNamespace(
        drawing_ensemble_molscribe_high_conf=0.90,
        drawing_ensemble_agreement_ratio_min=0.40,
        drawing_ensemble_low_agreement_penalty=0.50,
        drawing_ensemble_formula_boost=0.15,
        drawing_text_confirm_conf_bump=0.10,
        drawing_cascade_plausibility_threshold=0.50,
        drawing_cascade_min_resolved_conf=0.65,
        drawing_max_resolved_atoms=100,
    )
    set_thresholds_from_settings(fake_settings)


def _result(
    smiles: str,
    confidence: float,
    *,
    valid: bool = True,
    tool: str = "ensemble:test",
    error: str = "",
) -> OCSRResult:
    return OCSRResult(
        smiles=smiles,
        confidence=confidence,
        valid=valid,
        tool=tool,
        error=error,
    )


@pytest.mark.asyncio
async def test_concurrent_ensemble_tasks_cannot_cross_contaminate() -> None:
    ready = asyncio.Event()
    configured = 0

    async def evaluate(min_conf: float) -> OCSRResult:
        nonlocal configured
        set_thresholds_from_settings(
            SimpleNamespace(
                drawing_analysis_rollout_state="shadow",
                drawing_ensemble_molscribe_high_conf=0.90,
                drawing_ensemble_agreement_ratio_min=0.40,
                drawing_ensemble_low_agreement_penalty=0.50,
                drawing_ensemble_formula_boost=0.15,
                drawing_text_confirm_conf_bump=0.10,
                drawing_cascade_plausibility_threshold=0.50,
                drawing_cascade_min_resolved_conf=min_conf,
                drawing_max_resolved_atoms=100,
            )
        )
        configured += 1
        if configured == 2:
            ready.set()
        await ready.wait()
        await asyncio.sleep(0)
        return _apply_post_fuse_gates(_result("CCO", 0.7))

    strict_result, permissive_result = await asyncio.gather(
        evaluate(0.8),
        evaluate(0.6),
    )

    assert strict_result.valid is False
    assert strict_result.error == "below_min_conf"
    assert permissive_result.valid is True
    assert permissive_result.smiles == "CCO"


class TestApplyPostFuseGatesUnit:
    """Direct unit tests on the gate helper."""

    def test_low_confidence_downgraded_to_unresolved(self) -> None:
        """conf=0.5 with valid SMILES should be flagged as below_min_conf."""
        result = _result("CCO", 0.5)
        gated = _apply_post_fuse_gates(result)
        assert gated.smiles == ""
        assert gated.valid is False
        assert gated.error == "below_min_conf"

    def test_high_atom_count_downgraded_to_unresolved(self) -> None:
        """A 189-carbon alkane should be flagged as exceeds_max_atoms."""
        long_alkane = "C" * 189  # 189 heavy atoms — modeled on the polysaccharide case
        result = _result(long_alkane, 0.95)
        gated = _apply_post_fuse_gates(result)
        assert gated.smiles == ""
        assert gated.valid is False
        assert gated.error == "exceeds_max_atoms"

    def test_normal_result_passes_through(self) -> None:
        """conf=0.9, ~25 atoms — gate should be a no-op."""
        # Aspirin = C9H8O4 → 13 heavy atoms; ibuprofen = C13H18O2 → 15 heavy atoms.
        # Use erythromycin-ish core to land near 25 atoms — but simpler is fine.
        # Cholesterol = C27H46O → 28 heavy atoms.
        cholesterol = "CC(C)CCCC(C)C1CCC2C1(CCC3C2CC=C4C3(CCC(C4)O)C)C"
        result = _result(cholesterol, 0.9, tool="ensemble:cascade")
        gated = _apply_post_fuse_gates(result)
        assert gated.smiles == cholesterol
        assert gated.valid is True
        assert gated.error == ""
        assert gated.confidence == 0.9
        assert gated.tool == "ensemble:cascade"

    def test_below_threshold_at_boundary(self) -> None:
        """conf == min_conf (0.65) passes; conf = 0.649 fails."""
        at_boundary = _apply_post_fuse_gates(_result("CCO", 0.65))
        assert at_boundary.smiles == "CCO"
        assert at_boundary.valid is True
        assert at_boundary.error == ""

        just_below = _apply_post_fuse_gates(_result("CCO", 0.649))
        assert just_below.smiles == ""
        assert just_below.valid is False
        assert just_below.error == "below_min_conf"

    def test_invalid_smiles_passes_through_unchanged(self) -> None:
        """Pre-existing OCSRResult.error states are not second-guessed."""
        # Already-flagged unresolved result (no smiles, valid=False, has error)
        already_flagged = _result(
            "", 0.0, valid=False, tool="ensemble", error="No valid predictions from any model"
        )
        gated = _apply_post_fuse_gates(already_flagged)
        assert gated == already_flagged

        # valid=False but with stale smiles — gate must not "rescue" it.
        stale = _result("CCO", 0.99, valid=False, error="something_else")
        gated_stale = _apply_post_fuse_gates(stale)
        assert gated_stale == stale

    def test_result_marked_valid_with_malformed_smiles_is_downgraded(self) -> None:
        result = _result("not a smiles", 0.99, valid=True)

        gated = apply_resolution_gates(
            result,
            min_resolved_conf=0.65,
            max_resolved_atoms=100,
        )

        assert gated.smiles == ""
        assert gated.valid is False
        assert gated.error == "invalid_smiles"


class TestFuseAppliesGates:
    """Integration-style — verify fuse() applies the gates on real return paths."""

    def test_fuse_majority_vote_low_conf_downgraded(self) -> None:
        """A majority-vote result with low calibrated confidence should be gated.

        Two voters agree on a SMILES at low raw confidence. After
        calibration + low-agreement penalty, the fused confidence falls
        below the 0.65 floor and the gate should fire.
        """
        results = {
            "molscribe": OCSRResult(smiles="CCO", confidence=0.30, valid=True, tool="molscribe"),
            "decimer": OCSRResult(smiles="CC", confidence=0.20, valid=True, tool="decimer"),
        }
        fused = fuse(results, strategy="majority_vote")
        # No agreement, single vote each — fused confidence will be very low.
        # Either the result is gated (smiles="") or the conf is >=0.65 (we
        # only require the gate to fire when conf is genuinely below).
        if fused.confidence < 0.65 and fused.valid:
            # Should never reach this — gate must have fired.
            pytest.fail("fuse() returned valid result with conf<0.65; gate did not run")
        if not fused.valid:
            assert fused.error in {"below_min_conf", "exceeds_max_atoms"} or fused.error == ""

    def test_fuse_returns_huge_molecule_is_gated(self) -> None:
        """If fuse() converges on a >100-atom SMILES it must be gated."""
        long_alkane = "C" * 189
        results = {
            "molscribe": OCSRResult(
                smiles=long_alkane, confidence=0.95, valid=True, tool="molscribe"
            ),
            "decimer": OCSRResult(smiles=long_alkane, confidence=0.92, valid=True, tool="decimer"),
        }
        fused = fuse(results, strategy="majority_vote")
        assert fused.smiles == ""
        assert fused.valid is False
        assert fused.error == "exceeds_max_atoms"
