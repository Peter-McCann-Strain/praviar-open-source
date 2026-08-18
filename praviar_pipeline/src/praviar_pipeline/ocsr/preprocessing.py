"""Configurable image preprocessing for patent drawing OCSR inputs.

All functions operate on PIL Image objects. The preprocessing pipeline
runs in the primary Praviar Pipeline venv (only needs Pillow, no torch/tf).
Super-resolution is delegated to the superres_worker.py subprocess.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

try:
    from PIL import Image, ImageFilter
except ImportError as exc:
    raise ImportError(
        "Pillow is required for preprocessing. Install with: "
        "pip install 'praviar_pipeline[drawings]'"
    ) from exc


def binarize(img: Image.Image, threshold: int = 0) -> Image.Image:
    """Binarize image using median thresholding (fallback for no-opencv envs)."""
    gray = img.convert("L")
    if threshold == 0:
        import statistics

        pixels = list(gray.getdata())
        threshold = int(statistics.median(pixels))
    return gray.point(lambda x: 255 if x > threshold else 0, "L").convert("RGB")


def binarize_sauvola(img: Image.Image, window_size: int = 25, k: float = 0.3) -> Image.Image:
    """Binarize using Sauvola adaptive thresholding.

    This configured option adapts its threshold across local windows and
    requires scikit-image. No comparative performance claim is implied.
    """
    try:
        import numpy as np
        from skimage.filters import threshold_sauvola

        gray = np.array(img.convert("L"))
        thresh = threshold_sauvola(gray, window_size=window_size, k=k)
        binary = ((gray > thresh) * 255).astype(np.uint8)
        return Image.fromarray(binary).convert("RGB")
    except ImportError:
        raise ConfigurationError(
            "scikit-image is required for configured Sauvola preprocessing",
            source="scikit-image",
            step="drawing_preprocessing",
        ) from None


def denoise(img: Image.Image, radius: int = 1) -> Image.Image:
    """Apply the configured median filter for noise reduction."""
    return img.filter(ImageFilter.MedianFilter(size=2 * radius + 1))


def enhance_contrast_clahe(img: Image.Image, clip_limit: float = 2.0) -> Image.Image:
    """Apply CLAHE (Contrast-Limited Adaptive Histogram Equalisation).

    Uses OpenCV to apply real CLAHE on tiles.
    """
    try:
        import cv2
        import numpy as np

        gray = np.array(img.convert("L"))
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        return Image.fromarray(enhanced).convert("RGB")
    except ImportError:
        raise ConfigurationError(
            "OpenCV is required for configured CLAHE preprocessing",
            source="opencv",
            step="drawing_preprocessing",
        ) from None


def cleanup_connected_components(
    img: Image.Image,
    min_area: int = 20,
    max_area_ratio: float = 0.8,
) -> Image.Image:
    """Remove small noise and large border artifacts via connected component analysis.

    Removes components smaller than min_area pixels (scanner dust, compression noise)
    and larger than max_area_ratio of image area (borders, background).
    """
    try:
        import cv2
        import numpy as np

        gray = np.array(img.convert("L"))
        # Invert so structures are foreground (white on black)
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

        total_area = gray.shape[0] * gray.shape[1]
        mask = np.zeros_like(binary)
        for i in range(1, n_labels):  # skip background (label 0)
            area = stats[i, cv2.CC_STAT_AREA]
            if min_area <= area <= total_area * max_area_ratio:
                mask[labels == i] = 255

        # Re-invert: structures white, background black → white bg
        result = 255 - mask
        return Image.fromarray(result).convert("RGB")
    except ImportError:
        raise ConfigurationError(
            "OpenCV is required for configured connected-component preprocessing",
            source="opencv",
            step="drawing_preprocessing",
        ) from None


def deskew(img: Image.Image, max_angle: float = 15.0) -> Image.Image:
    """Correct slight rotation in scanned patent pages.

    Uses a simple approach: try small rotations and pick the one
    that maximises horizontal line alignment (via variance of row sums).
    Limited to ±max_angle degrees.

    This deterministic Pillow-only routine considers bounded slight rotations.
    Its use is a configured preprocessing choice, not a comparative robustness
    claim.
    """
    gray = img.convert("L")
    best_angle = 0.0
    best_score = 0.0

    for angle_10x in range(int(-max_angle * 10), int(max_angle * 10) + 1, 5):
        angle = angle_10x / 10.0
        rotated = gray.rotate(angle, expand=False, fillcolor=255)
        # Score: variance of row means (higher = more aligned text/lines)
        width, height = rotated.size
        pixels = list(rotated.getdata())
        row_means = []
        for y in range(height):
            row = pixels[y * width : (y + 1) * width]
            row_means.append(sum(row) / len(row))

        import statistics

        if len(row_means) > 1:
            score = statistics.variance(row_means)
            if score > best_score:
                best_score = score
                best_angle = angle

    if abs(best_angle) > 0.5:  # Only rotate if meaningful skew detected
        logger.debug("deskew_applied", angle=best_angle)
        return img.rotate(best_angle, expand=True, fillcolor=(255, 255, 255))
    return img


def sharpen(img: Image.Image, factor: float = 1.5) -> Image.Image:
    """Apply unsharp mask for edge enhancement."""
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=int(factor * 100), threshold=3))


def pad_to_square(img: Image.Image, fill: int = 255) -> Image.Image:
    """Pad image to square aspect ratio (required by some OCSR models)."""
    w, h = img.size
    if w == h:
        return img
    side = max(w, h)
    padded = Image.new("RGB", (side, side), (fill, fill, fill))
    padded.paste(img, ((side - w) // 2, (side - h) // 2))
    return padded


def resize_to(img: Image.Image, size: int = 512) -> Image.Image:
    """Resize image to target size while preserving aspect ratio, then pad."""
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    return pad_to_square(img)


def preprocess(
    img: Image.Image,
    steps: list[str] | None = None,
) -> tuple[Image.Image, list[str]]:
    """Run the configured preprocessing pipeline.

    Args:
        img: Input image (PIL).
        steps: List of preprocessing step names to apply, in order.
               Valid names: "denoise", "clahe", "binarize", "deskew",
               "sharpen", "pad", "resize_512".
               If None, applies default pipeline: ["clahe", "binarize"].

    Returns:
        Tuple of (processed image, list of steps actually applied).
    """
    if steps is None:
        steps = ["sauvola"]

    applied: list[str] = []
    step_fn: dict[str, Callable[[Image.Image], Image.Image]] = {
        "denoise": denoise,
        "clahe": enhance_contrast_clahe,
        "binarize": binarize,
        "sauvola": binarize_sauvola,
        "connected_components": cleanup_connected_components,
        "deskew": deskew,
        "sharpen": sharpen,
        "pad": pad_to_square,
        "resize_512": lambda i: resize_to(i, 512),
    }

    for step_name in steps:
        fn = step_fn.get(step_name)
        if fn is None:
            logger.warning("preprocessing_unknown_step", step=step_name)
            continue
        try:
            img = fn(img)
            applied.append(step_name)
        except ConfigurationError:
            raise
        except Exception as exc:
            logger.error(
                "preprocessing_step_failed",
                step=step_name,
                error_type=safe_exception_type(exc),
            )
            # Continue with remaining steps — don't let one failure block the pipeline

    return img, applied


def image_to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes for serialisation or API calls."""
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def bytes_to_image(data: bytes) -> Image.Image:
    """Convert raw image bytes to PIL Image."""
    return Image.open(io.BytesIO(data))
