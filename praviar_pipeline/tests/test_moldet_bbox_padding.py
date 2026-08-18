"""Tests for MolDet bbox padding.

YOLO11 returns axis-aligned bboxes that are tight to the foreground pixels.
Without padding, terminal atoms (CH3 / OH / halogens / R-group labels) are
clipped, which collapses OCSR predictions on real patent pages (e.g.
``US20160096916A1_2_1`` polysaccharide → ``C``,
``US20100151379A1_19_11`` sulfonate → ``SOO``).

This module unit-tests the pure ``_pad_bbox`` helper exposed by
``moldet_seg_worker``. The helper is dependency-free (no cv2 / ultralytics),
so we can import it on the dev venv without the moldet venv being installed.
"""

from __future__ import annotations

import pytest

from praviar_pipeline.ocsr.workers.moldet_seg_worker import _pad_bbox


class TestPadBbox:
    """Direct tests of the pure ``_pad_bbox`` helper."""

    def test_pad_fraction_applied(self) -> None:
        """A 200x200 box on a 1000x1000 page with frac=0.10 should expand by 20 px each side.

        max(w, h) = 200, frac * max = 20.0 -> raw_pad = 20.
        With defaults min_px=8 and max_px=32, max(min(20, 32), 8) = 20.
        Box (100,100,300,300) -> (80,80,320,320), no boundary clamping needed.
        """
        x1, y1, x2, y2 = _pad_bbox(
            100,
            100,
            300,
            300,
            page_w=1000,
            page_h=1000,
            frac=0.10,
            min_px=8,
            max_px=32,
        )
        assert (x1, y1, x2, y2) == (80, 80, 320, 320)

    def test_min_pad_floor(self) -> None:
        """A 50x50 box with frac=0.06 (raw=3) should pad by min_px=8 (floor wins)."""
        # Place the box well inside the page to avoid boundary clamping.
        x1, y1, x2, y2 = _pad_bbox(
            500,
            500,
            550,
            550,
            page_w=2000,
            page_h=2000,
            frac=0.06,
            min_px=8,
            max_px=32,
        )
        # raw = round(0.06 * 50) = 3, max(min(3, 32), 8) = 8
        assert (x1, y1, x2, y2) == (492, 492, 558, 558)

    def test_max_pad_cap(self) -> None:
        """A 1000x1000 box with frac=0.06 (raw=60) should cap at max_px=32."""
        # Place box centred on a 2000x2000 page so the cap, not the boundary,
        # determines the result.
        x1, y1, x2, y2 = _pad_bbox(
            500,
            500,
            1500,
            1500,
            page_w=2000,
            page_h=2000,
            frac=0.06,
            min_px=8,
            max_px=32,
        )
        # raw = round(0.06 * 1000) = 60, max(min(60, 32), 8) = 32
        assert (x1, y1, x2, y2) == (468, 468, 1532, 1532)

    def test_page_boundary_clamp_low(self) -> None:
        """A box near the top-left edge (x1=5, y1=5) should clamp to 0, not go negative."""
        # Default 0.06 fraction on a 100x100 box => raw = 6, floor 8 wins => pad = 8.
        # x1 - 8 = -3 -> clamp to 0; y1 - 8 = -3 -> clamp to 0.
        x1, y1, x2, y2 = _pad_bbox(
            5,
            5,
            105,
            105,
            page_w=1000,
            page_h=1000,
            frac=0.06,
            min_px=8,
            max_px=32,
        )
        assert x1 == 0
        assert y1 == 0
        # Far edge has plenty of room: 105 + 8 = 113.
        assert x2 == 113
        assert y2 == 113

    def test_page_boundary_clamp_high(self) -> None:
        """A box near the bottom-right edge should clamp to page_w-1 / page_h-1."""
        # Box at (900, 900, 995, 995) on a 1000x1000 page; pad = 8.
        # x2 + 8 = 1003 -> clamp to 999; y2 + 8 = 1003 -> clamp to 999.
        x1, y1, x2, y2 = _pad_bbox(
            900,
            900,
            995,
            995,
            page_w=1000,
            page_h=1000,
            frac=0.06,
            min_px=8,
            max_px=32,
        )
        assert x1 == 892
        assert y1 == 892
        assert x2 == 999
        assert y2 == 999


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
