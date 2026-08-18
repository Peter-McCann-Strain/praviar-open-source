"""Tests for DrawingEvidenceStore — lookup, serialization, prompt formatting."""

from __future__ import annotations

import pytest

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)


def _make_structure(
    patent_id: str = "US1234567B2",
    tanimoto: float = 0.5,
    confidence: float = 0.9,
    page: int = 1,
    smiles: str = "c1ccccc1",
    is_sub: bool = False,
    target_is_sub: bool = False,
) -> DrawingStructure:
    risk = (
        DrawingRiskLevel.HIGH
        if tanimoto >= 0.7
        else (DrawingRiskLevel.MEDIUM if tanimoto >= 0.3 else DrawingRiskLevel.LOW)
    )
    return DrawingStructure(
        patent_id=patent_id,
        page_number=page,
        structure_index=0,
        canonical_smiles=smiles,
        confidence=confidence,
        tanimoto_to_target=tanimoto,
        is_substructure_of_target=is_sub,
        target_is_substructure=target_is_sub,
        drawing_risk_signal=risk,
        rdkit_valid=True,
    )


def _make_analysis(
    patent_id: str = "US1234567B2",
    structures: list[DrawingStructure] | None = None,
) -> PatentDrawingAnalysis:
    structs = structures or []
    highest_tc = max((s.tanimoto_to_target for s in structs), default=0.0)
    highest_risk = DrawingRiskLevel.NONE
    for s in structs:
        if s.drawing_risk_signal.value == "high":
            highest_risk = DrawingRiskLevel.HIGH
        elif s.drawing_risk_signal.value == "medium" and highest_risk != DrawingRiskLevel.HIGH:
            highest_risk = DrawingRiskLevel.MEDIUM
        elif s.drawing_risk_signal.value == "low" and highest_risk == DrawingRiskLevel.NONE:
            highest_risk = DrawingRiskLevel.LOW
    return PatentDrawingAnalysis(
        patent_id=patent_id,
        pages_fetched=3,
        structures_found=len(structs),
        structures=structs,
        highest_risk_signal=highest_risk,
        highest_tanimoto=round(highest_tc, 4),
    )


@pytest.fixture
def sample_store() -> DrawingEvidenceStore:
    """Store with 3 patents: high TC, medium TC, and no structures."""
    results = DrawingAnalysisResults(
        patent_analyses=[
            _make_analysis(
                "US111",
                [
                    _make_structure("US111", tanimoto=0.92, confidence=0.95, is_sub=True),
                    _make_structure("US111", tanimoto=0.45, confidence=0.88, page=2),
                ],
            ),
            _make_analysis(
                "US222",
                [
                    _make_structure("US222", tanimoto=0.35, confidence=0.80),
                ],
            ),
            _make_analysis("US333"),  # No structures
        ],
    )
    return DrawingEvidenceStore(results)


class TestConstruction:
    def test_len(self, sample_store: DrawingEvidenceStore) -> None:
        assert len(sample_store) == 3

    def test_contains(self, sample_store: DrawingEvidenceStore) -> None:
        assert "US111" in sample_store
        assert "US999" not in sample_store

    def test_patent_ids(self, sample_store: DrawingEvidenceStore) -> None:
        assert set(sample_store.patent_ids) == {"US111", "US222", "US333"}

    def test_empty_store(self) -> None:
        store = DrawingEvidenceStore()
        assert len(store) == 0
        assert store.get("US111") is None

    def test_none_results(self) -> None:
        store = DrawingEvidenceStore(None)
        assert len(store) == 0


class TestLookup:
    def test_get_existing(self, sample_store: DrawingEvidenceStore) -> None:
        pa = sample_store.get("US111")
        assert pa is not None
        assert pa.structures_found == 2

    def test_get_missing(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.get("US999") is None

    def test_has_structures(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.has_structures("US111") is True
        assert sample_store.has_structures("US333") is False
        assert sample_store.has_structures("US999") is False

    def test_get_highest_tanimoto(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.get_highest_tanimoto("US111") == 0.92
        assert sample_store.get_highest_tanimoto("US333") == 0.0
        assert sample_store.get_highest_tanimoto("US999") == 0.0

    def test_get_risk_signal(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.get_risk_signal("US111") == DrawingRiskLevel.HIGH
        assert sample_store.get_risk_signal("US333") == DrawingRiskLevel.NONE

    def test_has_substructure_match(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.has_substructure_match("US111") is True
        assert sample_store.has_substructure_match("US222") is False

    def test_get_structures_with_min_tanimoto(self, sample_store: DrawingEvidenceStore) -> None:
        all_structs = sample_store.get_structures("US111")
        assert len(all_structs) == 2

        high_only = sample_store.get_structures("US111", min_tanimoto=0.5)
        assert len(high_only) == 1
        assert high_only[0].tanimoto_to_target == 0.92


class TestPromptFormatting:
    def test_brief_summary_with_structures(self, sample_store: DrawingEvidenceStore) -> None:
        summary = sample_store.brief_summary("US111")
        assert "DRAWING EVIDENCE" in summary
        assert "0.92" in summary
        assert "HIGH" in summary
        assert "substructure match" in summary

    def test_brief_summary_no_structures(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.brief_summary("US333") == ""

    def test_brief_summary_missing_patent(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.brief_summary("US999") == ""

    def test_summary_for_prompt_standard(self, sample_store: DrawingEvidenceStore) -> None:
        prompt = sample_store.summary_for_prompt("US111", min_tanimoto=0.3)
        assert "CHEMICAL STRUCTURES FROM PATENT DRAWINGS" in prompt
        assert "END DRAWING STRUCTURES" in prompt
        assert "0.92" in prompt  # High TC structure
        assert "0.45" in prompt  # Medium TC structure

    def test_summary_for_prompt_filters_low_tc(self, sample_store: DrawingEvidenceStore) -> None:
        prompt = sample_store.summary_for_prompt("US111", min_tanimoto=0.5)
        assert "0.92" in prompt
        assert "0.45" not in prompt  # Filtered out

    def test_summary_for_prompt_no_relevant(self, sample_store: DrawingEvidenceStore) -> None:
        prompt = sample_store.summary_for_prompt("US222", min_tanimoto=0.5)
        assert "None above Tanimoto" in prompt

    def test_summary_for_prompt_empty(self, sample_store: DrawingEvidenceStore) -> None:
        assert sample_store.summary_for_prompt("US333") == ""


class TestSerialization:
    def test_round_trip(self, sample_store: DrawingEvidenceStore) -> None:
        data = sample_store.to_dict()
        restored = DrawingEvidenceStore.from_dict(data)
        assert len(restored) == len(sample_store)
        assert set(restored.patent_ids) == set(sample_store.patent_ids)
        assert restored.get_highest_tanimoto("US111") == sample_store.get_highest_tanimoto("US111")

    def test_empty_round_trip(self) -> None:
        store = DrawingEvidenceStore()
        data = store.to_dict()
        restored = DrawingEvidenceStore.from_dict(data)
        assert len(restored) == 0

    def test_to_dict_structure(self, sample_store: DrawingEvidenceStore) -> None:
        data = sample_store.to_dict()
        assert isinstance(data, dict)
        assert "US111" in data
        assert "patent_id" in data["US111"]
