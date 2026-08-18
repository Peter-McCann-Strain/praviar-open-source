#!/usr/bin/env python
"""MolDet (UniParser) detector worker — runs in venvs/moldet/.

Optional YOLO11-based per-molecule detector adapter with the same JSON contract
as ``decimer_seg_worker.py``. Its upstream training and evaluation are not a
Praviar benchmark or production-readiness receipt, and its non-commercial
licence keeps it blocked from beta/production use.

Why this exists
---------------
The adapter exists to evaluate one-bounding-box-per-molecule segmentation on
dense drawing pages. That is an experimental routing choice, not a claim that
the upstream checkpoint is superior on the private or public Praviar corpus.

Protocol (mirrors decimer_seg_worker.py exactly):

    python moldet_seg_worker.py segment <page_image_path> <output_dir>
        → JSON array on stdout: [
            {"segment_index": 0,
             "bbox": [x1,y1,x2,y2],         # PAGE coordinates
             "image_path": "...",            # cropped PNG saved here
             "width": int, "height": int,
             "confidence": float}, ...
          ]

Bboxes are returned in page coordinates (not crop dimensions). Crops are
plain RGB sub-images (no RGBA mask edge effects - YOLO doesn't produce
masks, just axis-aligned boxes).

Bbox padding
------------
YOLO11 returns axis-aligned bboxes tight to foreground pixels. This adapter
applies explicitly configurable padding before cropping so terminal labels are
not clipped. The values below are implementation defaults, not benchmark-derived
accuracy claims:

    MOLDET_BBOX_PAD_FRACTION (default 0.06)
        Fraction of ``max(w, h)`` to pad on each side.
    MOLDET_BBOX_PAD_MIN_PX (default 8)
        Minimum pad in pixels (so very small boxes still get breathing
        room).
    MOLDET_BBOX_PAD_MAX_PX (default 32)
        Cap to avoid pulling in adjacent molecules on dense pages.

The bbox returned in the JSON record reflects the **padded** bbox so
downstream IoU matching uses the same coordinates as the saved crop.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    from .model_integrity import (
        verify_model_checksum_from_ml_bom as _package_verify_model_checksum,
    )
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from model_integrity import (
        verify_model_checksum_from_ml_bom as _script_verify_model_checksum,
    )

    verify_model_checksum_from_ml_bom = _script_verify_model_checksum
else:
    verify_model_checksum_from_ml_bom = _package_verify_model_checksum

# Default checkpoint location — overridable via MOLDET_CKPT env var.
_DEFAULT_CKPT = (
    Path(__file__).resolve().parents[4] / "models" / "moldet" / "moldet_yolo11l_960_doc.pt"
)
MOLDET_MODEL_ID = "moldet/yolo11l_960_doc"


def _required_float_env(name: str, default: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None:
        if default is not None:
            return default
        raise RuntimeError(
            f"Required env var {name} is not set. Set it via Settings or "
            "pass it explicitly when invoking the worker."
        )
    try:
        return float(raw)
    except ValueError:
        pass
    raise RuntimeError(f"{name} must be a valid float") from None


def _required_int_env(name: str, default: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None:
        if default is not None:
            return default
        raise RuntimeError(
            f"Required env var {name} is not set. Set it via Settings or "
            "pass it explicitly when invoking the worker."
        )
    try:
        return int(raw)
    except ValueError:
        pass
    raise RuntimeError(f"{name} must be a valid integer") from None


def _pad_bbox(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    page_w: int,
    page_h: int,
    frac: float,
    min_px: int,
    max_px: int,
) -> tuple[int, int, int, int]:
    """Pad a YOLO bbox by ``max(min(frac * max(w, h), max_px), min_px)`` and clamp.

    Pure helper so it can be unit-tested without spinning up YOLO. The pad
    is symmetric on all four sides; the resulting box is clamped to the
    page boundary ``[0, page_w-1] x [0, page_h-1]``. Returns the new
    ``(x1, y1, x2, y2)`` as ints.
    """
    w = x2 - x1
    h = y2 - y1
    raw_pad = round(frac * max(w, h))
    pad = max(min(raw_pad, max_px), min_px)

    nx1 = max(0, x1 - pad)
    ny1 = max(0, y1 - pad)
    nx2 = min(page_w - 1, x2 + pad)
    ny2 = min(page_h - 1, y2 + pad)
    return nx1, ny1, nx2, ny2


def segment(page_image_path: str, output_dir: str) -> list[dict]:
    """Run MolDet on a full patent page; return one record per detected molecule.

    Import and runtime errors raise instead of being smuggled into sentinel
    results. The caller treats non-zero exit plus stderr as a
    SegmentationOutputError.
    """
    t0 = time.monotonic()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    import cv2
    from ultralytics import YOLO

    ckpt_path = os.environ.get("MOLDET_CKPT", str(_DEFAULT_CKPT))
    if not Path(ckpt_path).exists():
        raise RuntimeError(
            f"MolDet checkpoint not found at {ckpt_path}. "
            "Download from https://huggingface.co/UniParser/MolDet"
        )
    verify_model_checksum_from_ml_bom(
        ckpt_path,
        model_id=MOLDET_MODEL_ID,
    )

    # Inference parameters are Settings-driven via env vars.
    # Defaults match UniParser's recommended values for moldet_yolo11l_960_doc.
    imgsz = _required_int_env("MOLDET_IMGSZ", default=960)
    conf_thresh = _required_float_env("MOLDET_CONF_THRESHOLD", default=0.25)
    iou_thresh = _required_float_env("MOLDET_IOU_THRESHOLD", default=0.7)

    # Bbox padding params — see module docstring (Fix A).
    pad_frac = _required_float_env("MOLDET_BBOX_PAD_FRACTION", default=0.06)
    pad_min_px = _required_int_env("MOLDET_BBOX_PAD_MIN_PX", default=8)
    pad_max_px = _required_int_env("MOLDET_BBOX_PAD_MAX_PX", default=32)

    model = YOLO(ckpt_path)
    page_bgr = cv2.imread(page_image_path)
    if page_bgr is None:
        raise RuntimeError(f"cv2.imread returned None for {page_image_path}")
    page_h, page_w = page_bgr.shape[:2]

    results = model.predict(
        page_image_path,
        imgsz=imgsz,
        conf=conf_thresh,
        iou=iou_thresh,
        verbose=False,
    )

    page_stem = Path(page_image_path).stem
    records: list[dict] = []

    for r in results:
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            break
        # Boxes are sorted by confidence descending by default; keep that order
        for idx in range(len(boxes)):
            x1, y1, x2, y2 = boxes.xyxy[idx].cpu().numpy().astype(int).tolist()
            score = float(boxes.conf[idx].cpu())

            # Pad tight YOLO boxes before slicing so terminal atoms and
            # R-group labels are not clipped.
            px1, py1, px2, py2 = _pad_bbox(
                x1,
                y1,
                x2,
                y2,
                page_w,
                page_h,
                pad_frac,
                pad_min_px,
                pad_max_px,
            )

            # Crop in PAGE coordinates — YOLO produces axis-aligned boxes,
            # no mask, so the crop is a plain BGR sub-image (no RGBA edge
            # effects, in contrast to DECIMER's apply_masks output).
            crop = page_bgr[py1:py2, px1:px2]
            ch, cw = crop.shape[:2]
            if ch == 0 or cw == 0:
                # Defensive — should not happen with valid YOLO output, but
                # raise rather than silently emit a blank record.
                raise RuntimeError(
                    f"MolDet emitted zero-area bbox idx={idx} on {page_image_path}: "
                    f"[{x1},{y1},{x2},{y2}] padded=[{px1},{py1},{px2},{py2}]"
                )

            seg_path = out / f"{page_stem}_seg{idx:03d}.png"
            cv2.imwrite(str(seg_path), crop)

            records.append(
                {
                    "segment_index": idx,
                    # Emit the *padded* bbox so downstream IoU matching
                    # uses the same coords as the saved crop.
                    "bbox": [px1, py1, px2, py2],
                    "image_path": str(seg_path),
                    "width": int(cw),
                    "height": int(ch),
                    "confidence": score,
                }
            )

    elapsed = int((time.monotonic() - t0) * 1000)
    if records:
        records[0]["latency_ms"] = elapsed

    return records


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "segment":
        print(json.dumps([{"error": "Usage: moldet_seg_worker.py segment <image> <output_dir>"}]))
        sys.exit(1)
    result = segment(sys.argv[2], sys.argv[3])
    print(json.dumps(result))
    sys.exit(0)
