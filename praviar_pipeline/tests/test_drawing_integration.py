"""Tests for Sprint 2: drawing evidence injection, PDF fallback, figure cross-check."""

from __future__ import annotations

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)
from praviar_pipeline.pipeline.step2d_drawings import cross_check_figure_references
from praviar_pipeline.utils.formatting import format_drawing_evidence

# -- Helpers --


def _structure(
    pid: str, tc: float = 0.5, conf: float = 0.9, is_sub: bool = False
) -> DrawingStructure:
    risk = (
        DrawingRiskLevel.HIGH
        if tc >= 0.7
        else DrawingRiskLevel.MEDIUM
        if tc >= 0.3
        else DrawingRiskLevel.LOW
    )
    return DrawingStructure(
        patent_id=pid,
        page_number=1,
        structure_index=0,
        canonical_smiles="c1ccccc1",
        confidence=conf,
        tanimoto_to_target=tc,
        is_substructure_of_target=is_sub,
        drawing_risk_signal=risk,
        rdkit_valid=True,
    )


def _analysis(pid: str, structures: list[DrawingStructure]) -> PatentDrawingAnalysis:
    tc = max((s.tanimoto_to_target for s in structures), default=0.0)
    return PatentDrawingAnalysis(
        patent_id=pid,
        structures_found=len(structures),
        structures=structures,
        highest_tanimoto=round(tc, 4),
        highest_risk_signal=(
            DrawingRiskLevel.HIGH
            if tc >= 0.7
            else DrawingRiskLevel.MEDIUM
            if tc >= 0.3
            else DrawingRiskLevel.LOW
            if structures
            else DrawingRiskLevel.NONE
        ),
    )


def _store(analyses: list[PatentDrawingAnalysis]) -> DrawingEvidenceStore:
    return DrawingEvidenceStore(DrawingAnalysisResults(patent_analyses=analyses))


# -- Figure cross-check tests --


class TestFigureCrossCheck:
    def test_no_references(self) -> None:
        gaps = cross_check_figure_references("This patent claims a method.", 5)
        assert gaps == []

    def test_empty_text(self) -> None:
        gaps = cross_check_figure_references("", 5)
        assert gaps == []

    def test_all_figures_fetched(self) -> None:
        text = "As shown in FIG. 1 and FIG. 2, the compound of Formula I..."
        gaps = cross_check_figure_references(text, 5)
        assert gaps == []

    def test_missing_figure(self) -> None:
        text = "See FIG. 10 for the structure. Also FIG. 3 shows..."
        gaps = cross_check_figure_references(text, 5)
        assert len(gaps) == 1
        assert "Figure 10" in gaps[0]

    def test_multiple_missing(self) -> None:
        text = "FIG. 1, FIG. 5, FIG. 15, and FIG. 20 show compounds."
        gaps = cross_check_figure_references(text, 10)
        assert len(gaps) == 2  # 15 and 20 missing

    def test_formula_references_not_numeric(self) -> None:
        """Formula I, Formula II etc. should not cause gaps (not page numbers)."""
        text = "The compound of Formula I as defined in claim 1."
        gaps = cross_check_figure_references(text, 3)
        assert gaps == []

    def test_case_insensitive(self) -> None:
        text = "fig. 1, Figure 2, FIG 3, figure 50"
        gaps = cross_check_figure_references(text, 5)
        assert len(gaps) == 1
        assert "50" in gaps[0]


# -- Format drawing evidence tests --


class TestFormatDrawingEvidence:
    def test_none_evidence(self) -> None:
        result = format_drawing_evidence(None, "US111")
        assert result == ""

    def test_brief_level(self) -> None:
        store = _store([_analysis("US111", [_structure("US111", tc=0.88)])])
        result = format_drawing_evidence(store, "US111", detail_level="brief")
        assert "DRAWING EVIDENCE" in result
        assert "0.88" in result

    def test_standard_level(self) -> None:
        store = _store(
            [
                _analysis(
                    "US111",
                    [
                        _structure("US111", tc=0.88),
                        _structure("US111", tc=0.15),
                    ],
                )
            ]
        )
        result = format_drawing_evidence(store, "US111", detail_level="standard")
        assert "CHEMICAL STRUCTURES" in result
        assert "0.88" in result

    def test_missing_patent(self) -> None:
        store = _store([])
        result = format_drawing_evidence(store, "US999", detail_level="brief")
        assert result == ""


# -- PatentDrawingAnalysis figure_reference_gaps field test --


class TestPatentDrawingAnalysisGaps:
    def test_figure_reference_gaps_field(self) -> None:
        pa = PatentDrawingAnalysis(
            patent_id="US111",
            figure_reference_gaps=["Figure 10 referenced but only 5 pages fetched"],
        )
        assert len(pa.figure_reference_gaps) == 1

    def test_default_empty(self) -> None:
        pa = PatentDrawingAnalysis(patent_id="US111")
        assert pa.figure_reference_gaps == []
