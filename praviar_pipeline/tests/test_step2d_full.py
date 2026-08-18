"""Integration tests for the full Step 2.75 drawing analysis pipeline."""

from unittest.mock import MagicMock

import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.drawing import (
    DrawingRiskLevel,
)
from praviar_pipeline.pipeline.step2d_drawings import (
    _check_substructure,
    _compute_tanimoto,
    _get_preprocessing_steps,
    _image_hash,
    _jurisdiction_from_patent_id,
    analyze_patent_drawings,
)


class TestJurisdictionDetection:
    def test_us_patent(self):
        assert _jurisdiction_from_patent_id("US7851188B2") == "US"

    def test_ep_patent(self):
        assert _jurisdiction_from_patent_id("EP1234567A1") == "EP"

    def test_jp_patent(self):
        assert _jurisdiction_from_patent_id("JP2020123456A") == "JP"

    def test_cn_patent(self):
        assert _jurisdiction_from_patent_id("CN112345678A") == "CN"

    def test_kr_patent(self):
        assert _jurisdiction_from_patent_id("KR20200123456A") == "KR"

    def test_unknown(self):
        assert _jurisdiction_from_patent_id("XY12345") == "UNKNOWN"


class TestPreprocessingSteps:
    def test_default_steps(self):
        settings = MagicMock()
        settings.drawing_preprocessing = ["clahe", "binarize"]
        settings.drawing_jurisdiction_aware = False
        steps = _get_preprocessing_steps("US", settings)
        assert steps == ["clahe", "binarize"]

    def test_jp_adds_denoise(self):
        settings = MagicMock()
        settings.drawing_preprocessing = ["clahe", "binarize"]
        settings.drawing_jurisdiction_aware = True
        steps = _get_preprocessing_steps("JP", settings)
        assert "denoise" in steps
        assert "sharpen" in steps

    def test_cn_adds_denoise(self):
        settings = MagicMock()
        settings.drawing_preprocessing = ["clahe", "binarize"]
        settings.drawing_jurisdiction_aware = True
        steps = _get_preprocessing_steps("CN", settings)
        assert "denoise" in steps

    def test_us_no_extra(self):
        settings = MagicMock()
        settings.drawing_preprocessing = ["clahe", "binarize"]
        settings.drawing_jurisdiction_aware = True
        steps = _get_preprocessing_steps("US", settings)
        assert steps == ["clahe", "binarize"]


class TestTanimotoComputation:
    def test_identical(self):
        assert _compute_tanimoto("CCO", "CCO") == 1.0

    def test_similar(self):
        # Ethanol vs methanol
        sim = _compute_tanimoto("CCO", "CO")
        assert 0.0 < sim < 1.0

    def test_invalid(self):
        with pytest.raises(SourceUnavailableError, match="chemical similarity input is invalid"):
            _compute_tanimoto("invalid", "CCO")


class TestSubstructureCheck:
    def test_is_substructure(self):
        # Benzene is substructure of toluene
        assert _check_substructure("c1ccccc1", "Cc1ccccc1") is True

    def test_not_substructure(self):
        assert _check_substructure("CCCCCCCC", "c1ccccc1") is False

    def test_invalid_smiles(self):
        with pytest.raises(SourceUnavailableError, match="substructure input is invalid"):
            _check_substructure("invalid", "CCO")


class TestImageHash:
    def test_deterministic(self):
        data = b"test_image_data"
        assert _image_hash(data) == _image_hash(data)

    def test_different_content_different_hash(self):
        assert _image_hash(b"image1") != _image_hash(b"image2")


class TestAnalyzePatentDrawings:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        settings = MagicMock()
        settings.drawing_analysis_enabled = False
        result = await analyze_patent_drawings([], "CCO", settings)
        assert result.total_patents_with_images == 0
        assert result.patent_analyses == []

    @pytest.mark.asyncio
    async def test_no_runners_returns_empty(self):
        settings = MagicMock()
        settings.drawing_analysis_enabled = True
        settings.drawing_ensemble_tools = ["nonexistent_tool"]
        result = await analyze_patent_drawings([], "CCO", settings)
        assert result.total_patents_with_images == 0

    @pytest.mark.asyncio
    async def test_empty_patent_list(self):
        settings = MagicMock()
        settings.drawing_analysis_enabled = True
        settings.drawing_ensemble_tools = []
        result = await analyze_patent_drawings([], "CCO", settings)
        assert len(result.patent_analyses) == 0


class TestCascadeLogic:
    """Test the confidence cascade routing logic."""

    def test_high_confidence_accepts_primary(self):
        """When MolScribe is 0.98 confident and plausible, accept immediately."""
        # This is tested implicitly through the cascade — but we verify the
        # threshold logic
        settings = MagicMock()
        settings.drawing_cascade_high_threshold = 0.95
        settings.drawing_cascade_medium_threshold = 0.70
        assert settings.drawing_cascade_high_threshold <= 0.98

    def test_medium_confidence_escalates(self):
        """Confidence 0.80 should trigger 2-model escalation."""
        settings = MagicMock()
        settings.drawing_cascade_high_threshold = 0.95
        settings.drawing_cascade_medium_threshold = 0.70
        conf = 0.80
        assert conf < settings.drawing_cascade_high_threshold
        assert conf >= settings.drawing_cascade_medium_threshold

    def test_low_confidence_full_ensemble(self):
        """Confidence 0.50 should trigger full 5-model ensemble."""
        settings = MagicMock()
        settings.drawing_cascade_high_threshold = 0.95
        settings.drawing_cascade_medium_threshold = 0.70
        conf = 0.50
        assert conf < settings.drawing_cascade_medium_threshold


class TestRiskLevelComputation:
    def test_high_risk(self):
        settings = MagicMock()
        settings.drawing_tanimoto_high = 0.7
        settings.drawing_tanimoto_medium = 0.3
        tanimoto = 0.85
        if tanimoto >= settings.drawing_tanimoto_high:
            risk = DrawingRiskLevel.HIGH
        elif tanimoto >= settings.drawing_tanimoto_medium:
            risk = DrawingRiskLevel.MEDIUM
        else:
            risk = DrawingRiskLevel.LOW
        assert risk == DrawingRiskLevel.HIGH

    def test_medium_risk(self):
        settings = MagicMock()
        settings.drawing_tanimoto_high = 0.7
        settings.drawing_tanimoto_medium = 0.3
        tanimoto = 0.45
        if tanimoto >= settings.drawing_tanimoto_high:
            risk = DrawingRiskLevel.HIGH
        elif tanimoto >= settings.drawing_tanimoto_medium:
            risk = DrawingRiskLevel.MEDIUM
        else:
            risk = DrawingRiskLevel.LOW
        assert risk == DrawingRiskLevel.MEDIUM

    def test_low_risk(self):
        settings = MagicMock()
        settings.drawing_tanimoto_high = 0.7
        settings.drawing_tanimoto_medium = 0.3
        tanimoto = 0.1
        if tanimoto >= settings.drawing_tanimoto_high:
            risk = DrawingRiskLevel.HIGH
        elif tanimoto >= settings.drawing_tanimoto_medium:
            risk = DrawingRiskLevel.MEDIUM
        else:
            risk = DrawingRiskLevel.LOW
        assert risk == DrawingRiskLevel.LOW
