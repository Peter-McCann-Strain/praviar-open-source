"""Tests for three-tier drawing-based triage auto-filter."""

from __future__ import annotations

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.triage import Relevance
from praviar_pipeline.pipeline.step3_triage import _auto_triage_with_drawings


def _patent(pid: str) -> PatentHit:
    return PatentHit(
        patent_id=pid,
        title=f"Patent {pid}",
        sources=[PatentSource.PUBCHEM],
    )


def _structure(
    pid: str,
    tanimoto: float = 0.5,
    confidence: float = 0.9,
    is_sub: bool = False,
) -> DrawingStructure:
    risk = (
        DrawingRiskLevel.HIGH
        if tanimoto >= 0.7
        else (DrawingRiskLevel.MEDIUM if tanimoto >= 0.3 else DrawingRiskLevel.LOW)
    )
    return DrawingStructure(
        patent_id=pid,
        page_number=1,
        structure_index=0,
        canonical_smiles="c1ccccc1",
        confidence=confidence,
        tanimoto_to_target=tanimoto,
        is_substructure_of_target=is_sub,
        drawing_risk_signal=risk,
        rdkit_valid=True,
    )


def _store(analyses: list[PatentDrawingAnalysis]) -> DrawingEvidenceStore:
    return DrawingEvidenceStore(DrawingAnalysisResults(patent_analyses=analyses))


def _analysis(pid: str, structures: list[DrawingStructure]) -> PatentDrawingAnalysis:
    highest_tc = max((s.tanimoto_to_target for s in structures), default=0.0)
    return PatentDrawingAnalysis(
        patent_id=pid,
        structures_found=len(structures),
        structures=structures,
        highest_tanimoto=round(highest_tc, 4),
        highest_risk_signal=(
            DrawingRiskLevel.HIGH
            if highest_tc >= 0.7
            else DrawingRiskLevel.MEDIUM
            if highest_tc >= 0.3
            else DrawingRiskLevel.LOW
            if structures
            else DrawingRiskLevel.NONE
        ),
    )


class TestTier1AutoRelevant:
    """Tier 1: TC >= 0.85 + substructure match → AUTO_RELEVANT."""

    def test_high_tc_with_substructure(self) -> None:
        patents = [_patent("US111")]
        evidence = _store(
            [
                _analysis("US111", [_structure("US111", tanimoto=0.92, is_sub=True)]),
            ]
        )
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 1
        assert len(remaining) == 0
        assert auto[0].relevance == Relevance.RELEVANT
        assert auto[0].drawing_auto_filtered is True
        assert auto[0].drawing_tanimoto == 0.92

    def test_high_tc_without_substructure_goes_to_llm(self) -> None:
        """Default config requires substructure for auto-relevant."""
        patents = [_patent("US111")]
        evidence = _store(
            [
                _analysis("US111", [_structure("US111", tanimoto=0.92, is_sub=False)]),
            ]
        )
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1

    def test_below_threshold_not_auto_relevant(self) -> None:
        patents = [_patent("US111")]
        evidence = _store(
            [
                _analysis("US111", [_structure("US111", tanimoto=0.80, is_sub=True)]),
            ]
        )
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1


class TestNegativeDrawingSimilaritySafety:
    """Negative OCSR similarity is never sufficient to exclude a patent."""

    def test_low_tc_many_structures_high_confidence(self) -> None:
        patents = [_patent("US111")]
        structures = [
            _structure("US111", tanimoto=0.05, confidence=0.90),
            _structure("US111", tanimoto=0.03, confidence=0.85),
            _structure("US111", tanimoto=0.08, confidence=0.92),
        ]
        evidence = _store([_analysis("US111", structures)])
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert auto == []
        assert [patent.patent_id for patent in remaining] == ["US111"]

    def test_low_tc_too_few_structures(self) -> None:
        """Only 2 structures — doesn't meet min_structures=3 threshold."""
        patents = [_patent("US111")]
        structures = [
            _structure("US111", tanimoto=0.05, confidence=0.90),
            _structure("US111", tanimoto=0.03, confidence=0.85),
        ]
        evidence = _store([_analysis("US111", structures)])
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1

    def test_low_tc_low_confidence(self) -> None:
        """Confidence below threshold — can't trust extraction, go to LLM."""
        patents = [_patent("US111")]
        structures = [
            _structure("US111", tanimoto=0.05, confidence=0.50),
            _structure("US111", tanimoto=0.03, confidence=0.60),
            _structure("US111", tanimoto=0.08, confidence=0.55),
        ]
        evidence = _store([_analysis("US111", structures)])
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1


class TestTier3Safety:
    """Safety rules: zero structures or missing patents always go to LLM."""

    def test_no_structures_goes_to_llm(self) -> None:
        patents = [_patent("US111")]
        evidence = _store([_analysis("US111", [])])
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1

    def test_patent_not_in_evidence_goes_to_llm(self) -> None:
        patents = [_patent("US111")]
        evidence = _store([])  # Empty evidence
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1

    def test_medium_tc_goes_to_llm(self) -> None:
        patents = [_patent("US111")]
        evidence = _store(
            [
                _analysis("US111", [_structure("US111", tanimoto=0.50, confidence=0.90)]),
            ]
        )
        auto, remaining = _auto_triage_with_drawings(patents, evidence)
        assert len(auto) == 0
        assert len(remaining) == 1


class TestMixedBatch:
    """Multiple patents with different tiers."""

    def test_mixed_three_tier(self) -> None:
        patents = [_patent("US_HIGH"), _patent("US_LOW"), _patent("US_MED")]
        evidence = _store(
            [
                _analysis(
                    "US_HIGH",
                    [
                        _structure("US_HIGH", tanimoto=0.95, is_sub=True),
                    ],
                ),
                _analysis(
                    "US_LOW",
                    [
                        _structure("US_LOW", tanimoto=0.02, confidence=0.90),
                        _structure("US_LOW", tanimoto=0.05, confidence=0.85),
                        _structure("US_LOW", tanimoto=0.01, confidence=0.88),
                    ],
                ),
                _analysis(
                    "US_MED",
                    [
                        _structure("US_MED", tanimoto=0.55, confidence=0.90),
                    ],
                ),
            ]
        )
        auto, remaining = _auto_triage_with_drawings(patents, evidence)

        # US_HIGH → Tier 1 AUTO_RELEVANT
        # US_LOW and US_MED both remain for the evidence-aware triage path.
        assert len(auto) == 1
        assert [patent.patent_id for patent in remaining] == ["US_LOW", "US_MED"]

        relevant = [r for r in auto if r.relevance == Relevance.RELEVANT]
        not_relevant = [r for r in auto if r.relevance == Relevance.NOT_RELEVANT]
        assert len(relevant) == 1
        assert relevant[0].patent_id == "US_HIGH"
        assert not_relevant == []
