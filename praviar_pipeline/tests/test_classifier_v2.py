"""Tests for the production drawing classifier (classifier_v2).

These tests exercise the subprocess-backed MolClassifier wire-up. They are
gated on the ``praviar_pipeline/venvs/molclassifier`` venv being present —
absent in CI runners that don't ship the trained model. When the venv is
missing the entire module is skipped (preferred over silent fallbacks per
the project's "no fallbacks" rule).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from praviar_pipeline.ocsr.classifier_v2 import (
    ClassificationResult,
    ImageCategory,
    classify_image,
    classify_persistent_session,
    configure_from_settings,
)
from praviar_pipeline.ocsr.workers.model_integrity import (
    ModelChecksumError,
    verify_model_checksum_from_ml_bom,
)
from praviar_pipeline.ocsr.workers.molclassifier_worker import MOLCLASSIFIER_MODEL_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
MOLCLASSIFIER_PY = REPO_ROOT / "praviar_pipeline" / "venvs" / "molclassifier" / "bin" / "python"
MOLCLASSIFIER_CKPT = (
    REPO_ROOT / "praviar_pipeline" / "models" / "molclassifier" / "molclassifier_model.chpt"
)


def _molclassifier_skip_reason() -> str | None:
    if not MOLCLASSIFIER_PY.exists():
        return "MolClassifier venv not available; skipping classifier_v2 tests"
    if not MOLCLASSIFIER_CKPT.exists():
        return "MolClassifier checkpoint not available; skipping classifier_v2 tests"
    try:
        verify_model_checksum_from_ml_bom(
            MOLCLASSIFIER_CKPT,
            model_id=MOLCLASSIFIER_MODEL_ID,
        )
    except ModelChecksumError as exc:
        return (
            "MolClassifier local model is not release-ready "
            f"({exc}); skipping classifier_v2 integration tests"
        )
    return None


_MOLCLASSIFIER_SKIP_REASON = _molclassifier_skip_reason()

pytestmark = pytest.mark.skipif(
    _MOLCLASSIFIER_SKIP_REASON is not None,
    reason=_MOLCLASSIFIER_SKIP_REASON or "",
)


@pytest.fixture(autouse=True)
def _set_classifier_env_from_settings() -> None:
    """classifier_v2 requires Settings-driven env vars; tests must set them."""
    configure_from_settings(
        SimpleNamespace(
            drawing_classifier_box_score_thresh=0.8,
            drawing_classifier_non_chemical_min_conf=0.95,
        )
    )


def _draw_chemical_structure(w: int = 400, h: int = 400) -> Image.Image:
    """Hexagon + bonds — passes Mask R-CNN molecule detection."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    points = [
        (cx, cy - 60),
        (cx + 52, cy - 30),
        (cx + 52, cy + 30),
        (cx, cy + 60),
        (cx - 52, cy + 30),
        (cx - 52, cy - 30),
    ]
    draw.polygon(points, outline="black", width=4)
    draw.line([(cx, cy - 60), (cx, cy - 110)], fill="black", width=4)
    draw.line([(cx + 52, cy - 30), (cx + 102, cy - 60)], fill="black", width=4)
    return img


def _blank_image(w: int = 400, h: int = 400) -> Image.Image:
    return Image.new("RGB", (w, h), (255, 255, 255))


class TestClassifyImage:
    def test_returns_classification_result(self) -> None:
        result = classify_image(_draw_chemical_structure())
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.category, ImageCategory)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.reason, str) and result.reason

    def test_chemical_structure_routes_to_chemical_category(self) -> None:
        result = classify_image(_draw_chemical_structure())
        # Synthetic hexagon is small / sparse — accept either MOLECULE or
        # MARKUSH (both route to OCSR), reject NON_CHEMICAL/REACTION.
        assert result.category in {ImageCategory.MOLECULE, ImageCategory.MARKUSH}

    def test_blank_image_handled(self) -> None:
        # Should produce a valid result, not crash. Category may vary —
        # MolClassifier is trained on chemical drawings, so very-blank
        # images are out-of-distribution; the test only asserts the
        # call protocol works end to end.
        result = classify_image(_blank_image())
        assert isinstance(result, ClassificationResult)


class TestPersistentSession:
    def test_session_classifies_multiple_images(self) -> None:
        with classify_persistent_session() as session:
            r1 = session.classify(_draw_chemical_structure())
            r2 = session.classify(_draw_chemical_structure(w=300, h=300))
        assert isinstance(r1, ClassificationResult)
        assert isinstance(r2, ClassificationResult)

    def test_session_outside_context_manager_raises(self) -> None:
        session = classify_persistent_session()
        with pytest.raises(RuntimeError, match="not active"):
            session.classify(_draw_chemical_structure())


class TestImageCategory:
    def test_all_four_members_defined(self) -> None:
        assert ImageCategory.MOLECULE.value == "molecule"
        assert ImageCategory.MARKUSH.value == "markush"
        assert ImageCategory.REACTION.value == "reaction"
        assert ImageCategory.NON_CHEMICAL.value == "non_chemical"
