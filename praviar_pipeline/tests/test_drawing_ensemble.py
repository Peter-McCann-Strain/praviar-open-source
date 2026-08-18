"""Tests for OCSR ensemble fusion and chemical rules reranking."""

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble import fuse
from praviar_pipeline.ocsr.reranking import rerank_candidates, score_plausibility, select_best


class TestChemicalPlausibility:
    """Test the chemical plausibility scoring."""

    def test_nitrile_scores_high(self):
        """Normal nitrile C#N should score 1.0."""
        score = score_plausibility("N#Cc1ccccc1")
        assert score == 1.0

    def test_isocyanide_scores_low(self):
        """Isocyanide [C-]#[N+] should be penalized."""
        score = score_plausibility("[C-]#[N+]c1ccccc1")
        assert score < 0.3

    def test_carbanion_penalized(self):
        """Carbanion [C-] should be penalized."""
        score = score_plausibility("[C-]c1ccccc1")
        assert score < 0.5

    def test_normal_drug_scores_high(self):
        """Common drug molecules should score 1.0."""
        drugs = [
            "CC(=O)Oc1ccccc1C(=O)O",  # aspirin
            "CC(C)Cc1ccc(C(C)C(=O)O)cc1",  # ibuprofen
            "Cn1c(=O)c2c(ncn2C)n(C)c1=O",  # caffeine
        ]
        for smi in drugs:
            assert score_plausibility(smi) == 1.0, f"Failed for {smi}"

    def test_invalid_smiles_scores_zero(self):
        """Invalid SMILES should score 0."""
        assert score_plausibility("not_a_smiles") == 0.0


class TestBeamReranking:
    """Test beam search reranking."""

    def test_rerank_prefers_plausible(self):
        """Reranking should prefer the plausible candidate."""
        candidates = [
            {"smiles": "[C-]#[N+]c1ccccc1", "score": -2.0, "valid": True},  # isocyanide (wrong)
            {"smiles": "N#Cc1ccccc1", "score": -2.5, "valid": True},  # nitrile (right)
        ]
        ranked = rerank_candidates(candidates, plausibility_weight=2.0)
        # Nitrile should be ranked first despite lower model score
        assert "N#C" in ranked[0]["smiles"] or "C#N" in ranked[0]["smiles"]

    def test_rerank_invalid_filtered(self):
        """Invalid candidates should rank last."""
        candidates = [
            {"smiles": "", "score": -1.0, "valid": False},
            {"smiles": "CCO", "score": -3.0, "valid": True},
        ]
        ranked = rerank_candidates(candidates)
        assert ranked[0]["smiles"] == "CCO"
        assert ranked[1]["combined_score"] == -999.0

    def test_select_best(self):
        """select_best should return the top candidate."""
        candidates = [
            {"smiles": "CCO", "score": -2.0, "valid": True},
            {"smiles": "CC", "score": -3.0, "valid": True},
        ]
        best = select_best(candidates)
        assert best["smiles"] == "CCO"


class TestEnsembleFusion:
    """Test multi-model ensemble fusion."""

    def _make_result(
        self, smiles: str, confidence: float = 0.9, valid: bool = True, tool: str = "test"
    ) -> OCSRResult:
        return OCSRResult(
            smiles=smiles,
            confidence=confidence,
            valid=valid,
            tool=tool,
        )

    def test_majority_vote_correct(self):
        """Majority vote should pick the SMILES agreed by most models."""
        results = {
            "molscribe": self._make_result("CCO", 0.9),
            "molsight": self._make_result("CCO", 0.8),
            "decimer": self._make_result("CC", 0.5),
        }
        fused_result = fuse(results, strategy="majority_vote")
        assert fused_result.smiles == "CCO"

    def test_cascade_high_confidence_agreement(self):
        """Cascade accepts when MolScribe and MolSight agree on connectivity."""
        results = {
            "molscribe": self._make_result("CCO", 0.98),
            "molsight": self._make_result("CCO", 0.85),
        }
        fused_result = fuse(results, strategy="confidence_cascade", confidence_threshold=0.8)
        assert fused_result.smiles == "CCO"
        assert "agree" in fused_result.tool or "molscribe" in fused_result.tool

    def test_cascade_plausibility_fallback(self):
        """When MolScribe is implausible, cascade should fall back to plausible model."""
        results = {
            "molscribe": self._make_result("[C-]#[N+]c1ccccc1", 0.9),  # isocyanide
            "decimer": self._make_result("N#Cc1ccccc1", 0.5),  # nitrile (correct)
        }
        fused_result = fuse(results, strategy="confidence_cascade", confidence_threshold=0.8)
        # Should fall back to DECIMER because isocyanide is implausible
        assert "[C-]" not in fused_result.smiles
        assert "decimer" in fused_result.tool

    def test_no_valid_results(self):
        """Should return error when no valid results."""
        results = {
            "molscribe": self._make_result("", 0.0, valid=False),
        }
        fused_result = fuse(results, strategy="majority_vote")
        assert fused_result.error

    def test_empty_results(self):
        """Should handle empty results dict."""
        fused_result = fuse({}, strategy="majority_vote")
        assert fused_result.error
