"""ChemSAM-style multi-molecule crop splitter.

The pixel-level visual diff showed that region-level detector boxes can be
correct in IoU while still covering 2-4 molecules drawn together as a Markush
+ R-group table or stacked stereoisomers. The OCSR ensemble is trained on
single-molecule images, so composite crops are split before recognition.

Approach (per Wang et al. 2024, J. Cheminform., DOI 10.1186/s13321-024-00823-2):

    1. Otsu-binarize the crop
    2. Morphologically dilate with a kernel sized as a fraction of the
       smaller dimension (bridges atom-label gaps without merging
       separate molecules)
    3. ``cv2.connectedComponentsWithStats`` (8-connectivity)
    4. Filter components by area + aspect ratio (drop noise/lines)
    5. If only 1 component but the original crop is tall and narrow,
       fall back to projection-profile white-space gap detection — split
       on the largest gap above a configurable threshold

All thresholds come from Settings — no magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.utils.private_artifacts import atomic_write_bytes, ensure_private_directory

if TYPE_CHECKING:
    from pathlib import Path

    from praviar_pipeline.config import Settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class SubCropConfig:
    """All splitter knobs come from this struct (sourced from Settings).

    No defaults are baked in and None is not a fallback. Callers construct this
    from a Settings instance via ``from_settings(settings)``.
    """

    enabled: bool
    min_height_trigger_px: int
    kernel_fraction: float
    min_component_area: int
    max_aspect: float
    min_gap_px: int

    @classmethod
    def from_settings(cls, settings: Settings) -> SubCropConfig:
        return cls(
            enabled=bool(settings.drawing_split_enabled),
            min_height_trigger_px=int(settings.drawing_split_min_height_trigger_px),
            kernel_fraction=float(settings.drawing_split_kernel_fraction),
            min_component_area=int(settings.drawing_split_min_component_area),
            max_aspect=float(settings.drawing_split_max_aspect),
            min_gap_px=int(settings.drawing_split_min_gap_px),
        )


@dataclass(frozen=True)
class SubCropResult:
    """One sub-crop produced by ``split_crop``.

    bbox is in COORDINATES OF THE ORIGINAL CROP, not the page. Callers that
    need page-coords add the parent's page-bbox top-left.
    """

    bbox_in_crop: tuple[int, int, int, int]
    image_path: Path
    width: int
    height: int


def split_crop(
    crop_path: Path,
    output_dir: Path,
    config: SubCropConfig,
) -> list[SubCropResult]:
    """Split a multi-molecule crop into sub-crops; return one ``SubCropResult`` per.

    If the crop is short enough or splitting is disabled, returns a single
    result containing the original crop (with bbox = full image).

    Args:
        crop_path: PNG of the DECIMER crop.
        output_dir: Where to write sub-crop PNGs.
        config: Splitter thresholds from Settings.

    Returns:
        At least one SubCropResult. Length 1 means no split occurred.
    """
    ensure_private_directory(output_dir)

    import cv2

    bgr = cv2.imread(str(crop_path))
    if bgr is None:
        raise RuntimeError(f"cv2.imread returned None for {crop_path}")
    h, w = bgr.shape[:2]

    if not config.enabled or h < config.min_height_trigger_px:
        return [_passthrough(crop_path, output_dir, w, h)]

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Otsu — invert so structures become white-on-black for dilation
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    smaller = min(h, w)
    kernel_size = max(int(smaller * config.kernel_fraction), 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    dilated = cv2.dilate(binary, kernel, iterations=1)

    n_components, _, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    # stats columns: x, y, w, h, area; component 0 is background
    components = []
    for i in range(1, n_components):
        cx, cy, cw, ch, area = stats[i]
        if area < config.min_component_area:
            continue
        aspect = max(cw, ch) / max(min(cw, ch), 1)
        if aspect > config.max_aspect:
            continue
        components.append((cx, cy, cw, ch))

    if len(components) <= 1:
        # No clean split; try projection-profile gap detection on the
        # un-dilated binary if the crop is tall (vertical stack of molecules).
        if h >= config.min_height_trigger_px and h > w:
            split_y = _find_horizontal_gap(binary, config.min_gap_px)
            if split_y is not None:
                logger.debug(
                    "split_crop_projection_profile",
                    crop=str(crop_path),
                    split_y=split_y,
                )
                return _emit_horizontal_split(bgr, crop_path, output_dir, split_y)
        return [_passthrough(crop_path, output_dir, w, h)]

    components.sort(key=lambda c: (c[1], c[0]))
    out: list[SubCropResult] = []
    stem = crop_path.stem
    for idx, (cx, cy, cw, ch) in enumerate(components):
        sub = bgr[cy : cy + ch, cx : cx + cw]
        sub_path = output_dir / f"{stem}_sub{idx:03d}.png"
        ok, encoded = cv2.imencode(".png", sub)
        if not ok:
            raise RuntimeError("OpenCV could not encode private sub-crop")
        atomic_write_bytes(sub_path, encoded.tobytes())
        out.append(
            SubCropResult(
                bbox_in_crop=(int(cx), int(cy), int(cx + cw), int(cy + ch)),
                image_path=sub_path,
                width=int(cw),
                height=int(ch),
            )
        )
    logger.debug(
        "split_crop_components",
        crop=str(crop_path),
        n_components=len(components),
    )
    return out


def _passthrough(crop_path: Path, output_dir: Path, w: int, h: int) -> SubCropResult:
    """Return the original crop unchanged."""
    return SubCropResult(
        bbox_in_crop=(0, 0, w, h),
        image_path=crop_path,
        width=w,
        height=h,
    )


def _find_horizontal_gap(binary, min_gap_px: int) -> int | None:
    """Find the longest run of empty rows; return the middle row of that run."""

    row_sums = binary.sum(axis=1)
    empty_rows = row_sums == 0
    if not empty_rows.any():
        return None
    in_run = False
    best_run = (0, 0)  # (length, mid)
    run_start = 0
    for y, is_empty in enumerate(empty_rows):
        if is_empty and not in_run:
            run_start = y
            in_run = True
        elif not is_empty and in_run:
            run_len = y - run_start
            if run_len > best_run[0]:
                best_run = (run_len, run_start + run_len // 2)
            in_run = False
    if in_run:
        run_len = len(empty_rows) - run_start
        if run_len > best_run[0]:
            best_run = (run_len, run_start + run_len // 2)
    if best_run[0] < min_gap_px:
        return None
    return int(best_run[1])


def _emit_horizontal_split(
    bgr,
    crop_path: Path,
    output_dir: Path,
    split_y: int,
) -> list[SubCropResult]:
    """Split a crop horizontally at split_y and emit two sub-crops."""
    import cv2

    h, w = bgr.shape[:2]
    stem = crop_path.stem
    top = bgr[:split_y, :]
    bot = bgr[split_y:, :]
    top_path = output_dir / f"{stem}_sub000.png"
    bot_path = output_dir / f"{stem}_sub001.png"
    top_ok, top_encoded = cv2.imencode(".png", top)
    bot_ok, bot_encoded = cv2.imencode(".png", bot)
    if not top_ok or not bot_ok:
        raise RuntimeError("OpenCV could not encode private split crop")
    atomic_write_bytes(top_path, top_encoded.tobytes())
    atomic_write_bytes(bot_path, bot_encoded.tobytes())
    return [
        SubCropResult(
            bbox_in_crop=(0, 0, w, split_y),
            image_path=top_path,
            width=w,
            height=split_y,
        ),
        SubCropResult(
            bbox_in_crop=(0, split_y, w, h),
            image_path=bot_path,
            width=w,
            height=h - split_y,
        ),
    ]
