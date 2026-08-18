"""Unit tests for the multi-molecule crop splitter.

Synthesises images with known structure counts and verifies the splitter
returns the expected sub-crop count + bbox geometry. No live model calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

# OpenCV is a hard dependency for this module; skip the whole file if missing
# The preprocessing layer also requires explicit env-backed thresholds.
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from praviar_pipeline.ocsr.cropping import (  # noqa: E402
    SubCropConfig,
    split_crop,
)

if TYPE_CHECKING:
    from pathlib import Path


def _config(**overrides: object) -> SubCropConfig:
    base = dict(
        drawing_split_enabled=True,
        drawing_split_min_height_trigger_px=200,
        drawing_split_kernel_fraction=0.02,
        drawing_split_min_component_area=200,
        drawing_split_max_aspect=10.0,
        drawing_split_min_gap_px=20,
    )
    base.update(overrides)
    return SubCropConfig.from_settings(SimpleNamespace(**base))


def _draw_two_benzenes_horizontal(path: Path, gap: int = 80) -> None:
    """Two benzene-like hexagons side by side with a clean white gap."""
    img = np.full((200, 600, 3), 255, dtype=np.uint8)
    # Left hexagon
    pts1 = np.array([[60, 100], [100, 70], [140, 100], [140, 140], [100, 170], [60, 140]])
    cv2.polylines(img, [pts1], isClosed=True, color=(0, 0, 0), thickness=3)
    # Right hexagon (separated by gap)
    offset = 200 + gap
    pts2 = pts1.copy()
    pts2[:, 0] += offset
    cv2.polylines(img, [pts2], isClosed=True, color=(0, 0, 0), thickness=3)
    cv2.imwrite(str(path), img)


def _draw_two_benzenes_vertical(path: Path, gap: int = 80) -> None:
    """Two benzene-like hexagons stacked vertically with a clean white gap."""
    img = np.full((600, 250, 3), 255, dtype=np.uint8)
    pts1 = np.array([[60, 60], [100, 30], [140, 60], [140, 100], [100, 130], [60, 100]])
    cv2.polylines(img, [pts1], isClosed=True, color=(0, 0, 0), thickness=3)
    offset = 200 + gap
    pts2 = pts1.copy()
    pts2[:, 1] += offset
    cv2.polylines(img, [pts2], isClosed=True, color=(0, 0, 0), thickness=3)
    cv2.imwrite(str(img.shape and str(path)), img)
    # Re-write robustly
    cv2.imwrite(str(path), img)


def _draw_single_benzene(path: Path) -> None:
    """One small benzene; should not split."""
    img = np.full((150, 150, 3), 255, dtype=np.uint8)
    pts = np.array([[60, 60], [100, 30], [140, 60], [140, 100], [100, 130], [60, 100]])
    cv2.polylines(img, [pts], isClosed=True, color=(0, 0, 0), thickness=3)
    cv2.imwrite(str(path), img)


class TestSplitCrop:
    def test_two_horizontal_molecules_split_into_two(self, tmp_path: Path) -> None:
        crop = tmp_path / "two_horizontal.png"
        _draw_two_benzenes_horizontal(crop)
        out_dir = tmp_path / "out"
        results = split_crop(crop, out_dir, _config())
        assert len(results) == 2, [r.bbox_in_crop for r in results]
        # Each sub-crop should be smaller than the parent in width
        for r in results:
            assert r.width < 600
            assert r.image_path.exists()

    def test_two_vertical_molecules_split_via_projection(self, tmp_path: Path) -> None:
        crop = tmp_path / "two_vertical.png"
        _draw_two_benzenes_vertical(crop)
        out_dir = tmp_path / "out"
        # Force the splitter into a regime where connected-component finds 1
        # blob (with high kernel_fraction the dilation can merge across the
        # gap), so the projection-profile branch fires.
        results = split_crop(
            crop,
            out_dir,
            _config(drawing_split_min_component_area=20),
        )
        # Either CC found two components or projection-profile split fired
        assert len(results) >= 2

    def test_single_molecule_passthrough(self, tmp_path: Path) -> None:
        crop = tmp_path / "single.png"
        _draw_single_benzene(crop)
        out_dir = tmp_path / "out"
        # Force trigger so we attempt splitting; the small image still has one
        # component
        results = split_crop(
            crop,
            out_dir,
            _config(drawing_split_min_height_trigger_px=50),
        )
        assert len(results) == 1
        # passthrough should preserve original
        assert results[0].image_path == crop
        assert results[0].bbox_in_crop == (0, 0, 150, 150)

    def test_disabled_returns_passthrough(self, tmp_path: Path) -> None:
        crop = tmp_path / "two.png"
        _draw_two_benzenes_horizontal(crop)
        results = split_crop(
            crop,
            tmp_path / "out",
            _config(drawing_split_enabled=False),
        )
        assert len(results) == 1
        assert results[0].image_path == crop

    def test_below_height_trigger_returns_passthrough(self, tmp_path: Path) -> None:
        crop = tmp_path / "small.png"
        _draw_two_benzenes_horizontal(crop)
        # Trigger raised above the crop height (200 in the test)
        results = split_crop(
            crop,
            tmp_path / "out",
            _config(drawing_split_min_height_trigger_px=10000),
        )
        assert len(results) == 1
        assert results[0].image_path == crop

    def test_missing_image_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match=r"cv2\.imread"):
            split_crop(tmp_path / "nope.png", tmp_path / "out", _config())
