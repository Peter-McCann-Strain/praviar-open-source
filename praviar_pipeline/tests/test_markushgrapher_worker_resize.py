"""Tests for MarkushGrapher-2 worker's aspect-preserving resize (Phase B4.1).

The worker lives in an isolated venv (Python 3.10 + UDOP + mlx-vlm) and has
top-of-file sys.path manipulation that fails when imported outside that venv.
We test the pure-PIL resize helper in isolation by extracting its source via
regex and exec-ing it into the test-local namespace. This keeps the worker's
runtime dependencies isolated while still exercising the critical fix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    pytest.skip("PIL not available in dev venv", allow_module_level=True)


WORKER_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "praviar_pipeline"
    / "ocsr"
    / "workers"
    / "markushgrapher_worker.py"
)


def _load_resize_helper():
    """Extract the _aspect_preserving_resize function from the worker source."""
    text = WORKER_PATH.read_text()
    match = re.search(
        r"def _aspect_preserving_resize\(.*?(?=\ndef _get_device)",
        text,
        re.DOTALL,
    )
    if match is None:  # pragma: no cover
        raise RuntimeError("Could not extract _aspect_preserving_resize from worker")
    ns: dict = {}
    exec(match.group(0), ns)
    return ns["_aspect_preserving_resize"]


# Load once per module
_resize = _load_resize_helper()


def test_markushgrapher_weights_are_verified_before_model_load() -> None:
    source = WORKER_PATH.read_text()

    assert "_MARKUSHGRAPHER_MODEL_ID" in source
    assert "_CHEMICALOCR_MODEL_ID" in source
    assert source.index(
        "verify_model_checksum_from_ml_bom(\n            _CHEMICALOCR_WEIGHT_PATH"
    ) < source.index("Chemical_OCR(model_path=_OCR_MODEL_DIR")
    assert source.index(
        "verify_model_checksum_from_ml_bom(\n            _MARKUSHGRAPHER_WEIGHT_PATH"
    ) < source.index("MarkushgrapherForConditionalGeneration.from_pretrained")


class TestAspectPreservingResize:
    def test_square_is_identity_shape(self):
        img = Image.new("RGB", (512, 512), "black")
        out = _resize(img, 512)
        assert out.size == (512, 512)

    def test_landscape_resized_and_padded(self):
        img = Image.new("RGB", (1024, 512), "black")
        out = _resize(img, 512)
        assert out.size == (512, 512)

    def test_landscape_padding_is_white(self):
        """White pad bars top and bottom for a 2:1 landscape image."""
        img = Image.new("RGB", (1024, 512), "black")
        out = _resize(img, 512)
        px = out.load()
        # Top-left corner lies in the white padding zone
        assert px[0, 0] == (255, 255, 255)
        # Bottom-left corner also in padding
        assert px[0, 511] == (255, 255, 255)
        # Centre of the image lies in the scaled black region
        assert px[256, 256] == (0, 0, 0)

    def test_portrait_resized_and_padded(self):
        img = Image.new("RGB", (200, 500), "black")
        out = _resize(img, 512)
        assert out.size == (512, 512)

    def test_portrait_padding_is_white(self):
        img = Image.new("RGB", (256, 512), "black")
        out = _resize(img, 512)
        px = out.load()
        # Left edge near top should be white padding
        assert px[0, 128] == (255, 255, 255)
        # Right edge should also be white padding
        assert px[511, 128] == (255, 255, 255)

    def test_tiny_input_upscaled(self):
        img = Image.new("RGB", (10, 30), "black")
        out = _resize(img, 512)
        assert out.size == (512, 512)

    def test_rgba_mode_converted_to_rgb(self):
        img = Image.new("RGBA", (256, 512), (0, 0, 0, 255))
        out = _resize(img, 512)
        assert out.size == (512, 512)
        assert out.mode == "RGB"

    def test_zero_width_falls_back_gracefully(self):
        # Edge case: if somehow a degenerate image gets through, we should not
        # raise — fall back to the naive resize and let the downstream model
        # handle the noise.
        img = Image.new("RGB", (1, 1), "black")
        out = _resize(img, 512)
        assert out.size == (512, 512)

    def test_bond_angle_preserved_for_wide_image(self):
        """Proxy test: a horizontal line stays horizontal after resize.

        Hard-square resize would skew proportions enough to distort a 1024x128
        line; aspect-preserving resize scales uniformly so the line stays flat.
        LANCZOS anti-aliases a 1px line so the centre is dark-grey, not pure
        black — correct behaviour that preserves fine detail.
        """
        img = Image.new("RGB", (1024, 128), "white")
        for x in range(1024):
            img.putpixel((x, 64), (0, 0, 0))

        out = _resize(img, 512)

        # Scale factor 0.5; scaled image is 512x64 centred at y=224..288 in the
        # 512x512 canvas. Line centre lands at y=256.
        px = out.load()
        # Line centre must be notably darker than mid-grey
        r, g, b = px[256, 256][:3]
        line_luminance = (r + g + b) / 3
        assert line_luminance < 160, (
            f"expected dark line at (256, 256), got luminance {line_luminance}"
        )
        # Rows well away from the line must be clearly lighter (white padding
        # or the white background of the scaled image)
        for y_far in (200, 300):
            far_r, far_g, far_b = px[256, y_far][:3]
            far_luminance = (far_r + far_g + far_b) / 3
            assert far_luminance > 240, (
                f"expected white at (256, {y_far}), got luminance {far_luminance}"
            )
