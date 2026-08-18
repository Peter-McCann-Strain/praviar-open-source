"""Focused unit tests for drawing-evidence influence in triage prompts.

Drawing evidence may enter customer-facing triage prompts only when the
explicit rollout state is beta/production and the reviewed evidence gate has
passed. Legacy shadow-mode settings alone must not permit influence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.drawing_rollout import drawing_evidence_can_influence
from praviar_pipeline.pipeline.triage.prompting import format_patent_for_triage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_patent(patent_id: str = "US12345678") -> PatentHit:
    """Minimal PatentHit good enough for prompt formatting."""
    return PatentHit(
        patent_id=patent_id,
        title="Example patent",
        abstract="An example patent abstract mentioning ethanol derivatives.",
        claims_text="1. A composition comprising ethanol.",
        sources=[PatentSource.BIGQUERY],
        confidence_score=0.9,
    )


def _make_populated_store(
    patent_id: str = "US12345678",
    structures_found: int = 1,
    highest_tanimoto: float = 0.92,
    risk: DrawingRiskLevel = DrawingRiskLevel.HIGH,
) -> DrawingEvidenceStore:
    """Build a DrawingEvidenceStore that answers `has_structures` True and
    produces a non-empty `brief_summary`."""
    structures: list[DrawingStructure] = []
    for i in range(structures_found):
        structures.append(
            DrawingStructure(
                patent_id=patent_id,
                page_number=1,
                structure_index=i,
                canonical_smiles="CCO",
                tanimoto_to_target=highest_tanimoto,
                rdkit_valid=True,
                confidence=0.9,
                extraction_tool="molscribe",
            )
        )
    pa = PatentDrawingAnalysis(
        patent_id=patent_id,
        structures_found=structures_found,
        structures_valid=structures_found,
        structures=structures,
        highest_risk_signal=risk if structures_found else DrawingRiskLevel.NONE,
        highest_tanimoto=highest_tanimoto if structures_found else 0.0,
    )
    return DrawingEvidenceStore(DrawingAnalysisResults(patent_analyses=[pa]))


def _make_settings(
    *,
    shadow_mode: bool = False,
    rollout_state: str = "shadow",
    evidence_gate_passed: bool = False,
    max_abstract: int = 400,
    max_claims: int = 800,
    calibration_config: dict[str, object] | None = None,
) -> SimpleNamespace:
    values: dict[str, object] = {
        "drawing_analysis_enabled": True,
        "drawing_analysis_shadow_mode": shadow_mode,
        "drawing_analysis_rollout_state": rollout_state,
        "drawing_analysis_evidence_gate_passed": evidence_gate_passed,
        "drawing_analysis_jurisdictions": ["US"],
        "triage_max_abstract_chars": max_abstract,
        "triage_max_claims_chars": max_claims,
    }
    values.update(calibration_config or {})
    return SimpleNamespace(**values)


def _compute_drawing_summary_for_triage(
    *,
    patent_id: str,
    drawing_evidence: DrawingEvidenceStore | None,
    settings: SimpleNamespace,
) -> str:
    """Pure-python replica of the rollout gate used by `step3_triage`."""
    if (
        drawing_evidence is not None
        and drawing_evidence.has_structures(patent_id)
        and drawing_evidence_can_influence(settings)
    ):
        return drawing_evidence.brief_summary(patent_id)
    return ""


def _format(
    patent: PatentHit,
    *,
    drawing_evidence: DrawingEvidenceStore | None,
    settings: SimpleNamespace,
) -> str:
    summary = _compute_drawing_summary_for_triage(
        patent_id=patent.patent_id,
        drawing_evidence=drawing_evidence,
        settings=settings,
    )
    return format_patent_for_triage(
        patent,
        max_abstract=settings.triage_max_abstract_chars,
        max_claims=settings.triage_max_claims_chars,
        drawing_summary=summary,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_live_rollout_with_evidence_gate_injects_drawing_section(
    verified_calibration_config: dict[str, object],
) -> None:
    patent = _make_patent()
    store = _make_populated_store()
    settings = _make_settings(
        shadow_mode=False,
        rollout_state="beta",
        evidence_gate_passed=True,
        calibration_config=verified_calibration_config,
    )

    prompt = _format(patent, drawing_evidence=store, settings=settings)

    assert "DRAWING EVIDENCE:" in prompt
    assert "1 structures extracted" in prompt
    assert "0.92" in prompt


def test_shadow_rollout_with_evidence_suppresses_drawing_section() -> None:
    patent = _make_patent()
    store = _make_populated_store()
    settings = _make_settings(
        shadow_mode=True,
        rollout_state="shadow",
        evidence_gate_passed=True,
    )

    assert "DRAWING EVIDENCE:" in store.brief_summary(patent.patent_id)

    prompt = _format(patent, drawing_evidence=store, settings=settings)
    assert "DRAWING EVIDENCE:" not in prompt


def test_live_rollout_without_evidence_gate_suppresses_drawing_section() -> None:
    patent = _make_patent()
    store = _make_populated_store()
    settings = _make_settings(
        shadow_mode=False,
        rollout_state="production",
        evidence_gate_passed=False,
    )

    prompt = _format(patent, drawing_evidence=store, settings=settings)

    assert "DRAWING EVIDENCE:" not in prompt


def test_no_evidence_never_injects_drawing_section_regardless_of_shadow() -> None:
    patent = _make_patent()
    settings_variants = [
        _make_settings(rollout_state="shadow", evidence_gate_passed=True),
        _make_settings(
            shadow_mode=False,
            rollout_state="beta",
            evidence_gate_passed=True,
        ),
    ]

    for settings in settings_variants:
        prompt = _format(patent, drawing_evidence=None, settings=settings)
        assert "DRAWING EVIDENCE:" not in prompt


def test_evidence_with_zero_structures_suppresses_section() -> None:
    patent = _make_patent()
    empty_store = _make_populated_store(structures_found=0)
    assert empty_store.has_structures(patent.patent_id) is False
    settings_variants = [
        _make_settings(rollout_state="shadow", evidence_gate_passed=True),
        _make_settings(
            shadow_mode=False,
            rollout_state="beta",
            evidence_gate_passed=True,
        ),
    ]

    for settings in settings_variants:
        prompt = _format(patent, drawing_evidence=empty_store, settings=settings)
        assert "DRAWING EVIDENCE:" not in prompt


def test_live_rollout_prompt_is_bit_identical_to_drawings_enabled_prompt(
    verified_calibration_config: dict[str, object],
) -> None:
    patent = _make_patent()
    store = _make_populated_store()
    settings = _make_settings(
        shadow_mode=False,
        rollout_state="production",
        evidence_gate_passed=True,
        calibration_config=verified_calibration_config,
    )

    via_gate = _format(patent, drawing_evidence=store, settings=settings)

    direct_summary = store.brief_summary(patent.patent_id)
    direct = format_patent_for_triage(
        patent,
        max_abstract=settings.triage_max_abstract_chars,
        max_claims=settings.triage_max_claims_chars,
        drawing_summary=direct_summary,
    )

    assert via_gate == direct, (
        "Live rollout path diverged from the canonical drawings-enabled prompt.\n"
        f"via_gate:\n{via_gate!r}\n\ndirect:\n{direct!r}"
    )


def test_missing_rollout_state_fails_closed() -> None:
    patent = _make_patent()
    store = _make_populated_store()

    settings_without_rollout = SimpleNamespace(
        drawing_analysis_enabled=True,
        drawing_analysis_shadow_mode=False,
        drawing_analysis_evidence_gate_passed=True,
        triage_max_abstract_chars=400,
        triage_max_claims_chars=800,
    )
    assert not hasattr(settings_without_rollout, "drawing_analysis_rollout_state")

    prompt = _format(patent, drawing_evidence=store, settings=settings_without_rollout)
    assert "DRAWING EVIDENCE:" not in prompt


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
