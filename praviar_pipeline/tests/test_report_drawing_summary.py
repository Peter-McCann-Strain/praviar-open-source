"""Tests for the enriched drawing_summary dict (Phase C confidence/tool/stereo surfacing)."""

from __future__ import annotations

from praviar_pipeline.models.drawing import (
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)
from praviar_pipeline.pipeline.report.finalization import (
    _build_drawing_outputs,
    _confidence_band,
)


def _make_structure(
    *,
    patent_id: str = "US1",
    conf: float = 0.9,
    tool: str = "ensemble:majority_5_of_5",
    stereo_flag: str = "",
    pubchem_match: bool = False,
    risk: DrawingRiskLevel = DrawingRiskLevel.LOW,
    tanimoto: float = 0.2,
) -> DrawingStructure:
    return DrawingStructure(
        patent_id=patent_id,
        page_number=1,
        structure_index=0,
        raw_smiles="CCO",
        canonical_smiles="CCO",
        confidence=conf,
        extraction_tool=tool,
        rdkit_valid=True,
        tanimoto_to_target=tanimoto,
        drawing_risk_signal=risk,
        pubchem_match=pubchem_match,
        stereo_flag=stereo_flag,
    )


def _make_analysis(patent_id: str, structures: list[DrawingStructure]) -> PatentDrawingAnalysis:
    return PatentDrawingAnalysis(
        patent_id=patent_id,
        pages_fetched=1,
        structures_found=len(structures),
        structures=structures,
    )


class TestConfidenceBand:
    def test_high(self):
        assert _confidence_band(0.99) == "HIGH"
        assert _confidence_band(0.90) == "HIGH"

    def test_medium(self):
        assert _confidence_band(0.89) == "MEDIUM"
        assert _confidence_band(0.70) == "MEDIUM"

    def test_low(self):
        assert _confidence_band(0.69) == "LOW"
        assert _confidence_band(0.0) == "LOW"


class TestBuildDrawingOutputs:
    def test_none_store_returns_empty(self):
        analyses, summary = _build_drawing_outputs(None)
        assert analyses == []
        assert summary == {}

    def test_empty_store_returns_empty(self):
        store = DrawingEvidenceStore.__new__(DrawingEvidenceStore)
        store._by_patent = {}  # type: ignore[attr-defined]
        _analyses, summary = _build_drawing_outputs(store)
        assert summary == {}

    def test_counts_confidence_bands(self):
        structures = [
            _make_structure(conf=0.95),  # HIGH
            _make_structure(conf=0.92),  # HIGH
            _make_structure(conf=0.80),  # MEDIUM
            _make_structure(conf=0.50),  # LOW
        ]
        analysis = _make_analysis("US1", structures)
        store = DrawingEvidenceStore.__new__(DrawingEvidenceStore)
        store._by_patent = {"US1": analysis}  # type: ignore[attr-defined]
        _, summary = _build_drawing_outputs(store)
        assert summary["confidence_bands"] == {"HIGH": 2, "MEDIUM": 1, "LOW": 1}
        assert summary["total_structures"] == 4

    def test_per_tool_extraction_counts(self):
        structures = [
            _make_structure(tool="ensemble:majority_5_of_5"),
            _make_structure(tool="ensemble:majority_5_of_5"),
            _make_structure(tool="ensemble:molscribe_primary"),
            _make_structure(tool="markushgrapher"),
        ]
        analysis = _make_analysis("US1", structures)
        store = DrawingEvidenceStore.__new__(DrawingEvidenceStore)
        store._by_patent = {"US1": analysis}  # type: ignore[attr-defined]
        _, summary = _build_drawing_outputs(store)
        counts = summary["per_tool_extraction_counts"]
        assert counts["ensemble:majority_5_of_5"] == 2
        assert counts["ensemble:molscribe_primary"] == 1
        assert counts["markushgrapher"] == 1

    def test_stereo_flag_counts(self):
        structures = [
            _make_structure(stereo_flag="ok"),
            _make_structure(stereo_flag="ok"),
            _make_structure(stereo_flag="stereo_blind"),
            _make_structure(stereo_flag="claim_demands_stereo_but_ocsr_blind"),
            _make_structure(stereo_flag=""),  # not counted
        ]
        analysis = _make_analysis("US1", structures)
        store = DrawingEvidenceStore.__new__(DrawingEvidenceStore)
        store._by_patent = {"US1": analysis}  # type: ignore[attr-defined]
        _, summary = _build_drawing_outputs(store)
        flags = summary["stereo_flag_counts"]
        assert flags["ok"] == 2
        assert flags["stereo_blind"] == 1
        assert flags["claim_demands_stereo_but_ocsr_blind"] == 1
        assert "" not in flags

    def test_text_validated_and_high_risk_counts(self):
        structures = [
            _make_structure(pubchem_match=True, risk=DrawingRiskLevel.HIGH),
            _make_structure(pubchem_match=True, risk=DrawingRiskLevel.MEDIUM),
            _make_structure(pubchem_match=False, risk=DrawingRiskLevel.HIGH),
            _make_structure(pubchem_match=False, risk=DrawingRiskLevel.LOW),
        ]
        analysis = _make_analysis("US1", structures)
        store = DrawingEvidenceStore.__new__(DrawingEvidenceStore)
        store._by_patent = {"US1": analysis}  # type: ignore[attr-defined]
        _, summary = _build_drawing_outputs(store)
        assert summary["text_validated_count"] == 2
        assert summary["high_risk_structures"] == 2
