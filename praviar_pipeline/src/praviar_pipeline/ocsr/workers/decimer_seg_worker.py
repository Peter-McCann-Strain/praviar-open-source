#!/usr/bin/env python
"""DECIMER Segmentation worker — runs in venvs/decimer/ Python.

Protocol:
    python decimer_seg_worker.py segment <page_image_path> <output_dir>
    → JSON array to stdout: [{"segment_index": 0, "bbox": [x1,y1,x2,y2], "image_path": "...", ...}]

The bbox is in PAGE coordinates (not crop dimensions). Downstream code that
needs to reason about position on the original page (evidence linking, IoU
evaluation against ground truth) depends on this.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

try:
    from .worker_diagnostics import safe_worker_error as _package_safe_worker_error
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from worker_diagnostics import safe_worker_error as _script_safe_worker_error

    safe_worker_error = _script_safe_worker_error
else:
    safe_worker_error = _package_safe_worker_error


_DECIMER_MODEL_SHA256 = "329120facb69e88add819a3216db0fbfef57e9a37d6b6db0f6149819a11d46a5"


def _verify_model_artifact(path: Path, *, expected_sha256: str) -> None:
    """Reject missing or substituted segmentation weights before importing Keras."""
    if not path.is_file():
        raise RuntimeError("DECIMER segmentation model is not pre-baked")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise RuntimeError("DECIMER segmentation model checksum mismatch")


def _require_decimer_model() -> None:
    python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    model_path = (
        Path(sys.prefix)
        / "lib"
        / python_version
        / "site-packages"
        / "decimer_segmentation"
        / "mask_rcnn_molecule.h5"
    )
    _verify_model_artifact(model_path, expected_sha256=_DECIMER_MODEL_SHA256)


def segment(page_image_path: str, output_dir: str) -> list[dict]:
    """Run DECIMER Segmentation on a full patent page image.

    Uses get_mrcnn_results() rather than segment_chemical_structures_from_file()
    because we need the page-level bounding boxes — the higher-level helper
    discards them and returns only the cropped images.
    """
    t0 = time.monotonic()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Import/runtime errors raise instead of being smuggled into a sentinel
    # result. The caller treats non-zero exit plus stderr as a
    # SegmentationOutputError.
    _require_decimer_model()
    import cv2
    from decimer_segmentation import (
        apply_masks,
        get_mrcnn_results,
    )

    page_bgr = cv2.imread(page_image_path)
    if page_bgr is None:
        raise RuntimeError(f"cv2.imread returned None for {page_image_path}")
    page_rgb = cv2.cvtColor(page_bgr, cv2.COLOR_BGR2RGB)
    masks, bboxes_yxyx, scores = get_mrcnn_results(page_rgb)
    # apply_masks returns (crops_list, bboxes_list) — same length/order as masks.
    # Crops are RGBA ndarrays (alpha = mask), so use RGBA2BGR for cv2.imwrite.
    crops_list, _ = apply_masks(page_rgb, masks)

    results = []
    page_stem = Path(page_image_path).stem

    for idx, (crop_arr, bbox_yxyx, score) in enumerate(
        zip(crops_list, bboxes_yxyx, scores, strict=False)
    ):
        # MRCNN returns (y0, x0, y1, x1); standardise to (x1, y1, x2, y2)
        y0, x0, y1, x1 = (int(v) for v in bbox_yxyx)
        bbox = [x0, y0, x1, y1]

        seg_path = out / f"{page_stem}_seg{idx:03d}.png"
        try:
            channels = crop_arr.shape[2] if crop_arr.ndim == 3 else 1
            cvt_code = cv2.COLOR_RGBA2BGR if channels == 4 else cv2.COLOR_RGB2BGR
            crop_bgr = cv2.cvtColor(crop_arr, cvt_code)
            cv2.imwrite(str(seg_path), crop_bgr)
            h, w = crop_arr.shape[:2]
        except Exception as exc:
            results.append(
                {
                    "segment_index": idx,
                    "bbox": bbox,
                    "image_path": "",
                    "width": 0,
                    "height": 0,
                    "error": safe_worker_error("Segment write", exc),
                }
            )
            continue

        results.append(
            {
                "segment_index": idx,
                "bbox": bbox,
                "image_path": str(seg_path),
                "width": int(w),
                "height": int(h),
                "confidence": float(score),
            }
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    if results and "error" not in results[0]:
        results[0]["latency_ms"] = elapsed

    return results


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "segment":
        print(json.dumps([{"error": "Usage: decimer_seg_worker.py segment <image> <output_dir>"}]))
        sys.exit(1)
    result = segment(sys.argv[2], sys.argv[3])
    print(json.dumps(result))
    has_error = any("error" in r for r in result)
    sys.exit(1 if has_error else 0)
