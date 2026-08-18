#!/usr/bin/env python
"""ChemSAM Segmentation worker — runs in venvs/chemsam/ Python.

ChemSAM (Fan et al., J. Cheminform 2024) uses Segment-Anything weights
fine-tuned on patent pages. It is exposed as an optional alternative
backend behind the ``drawing_segmentation_tool`` flag; selection requires
separately reviewed evidence for the intended corpus. This worker lives in
an isolated venv because ChemSAM pulls in a
SAM / torch stack that can conflict with other OCSR tools.

Protocol (mirrors ``decimer_seg_worker.py`` for drop-in swap):
    python chemsam_seg_worker.py segment <page_image_path> <output_dir>
    → JSON array to stdout:
      [{"segment_index": 0, "bbox": [x1,y1,x2,y2], "image_path": "...",
        "width": W, "height": H, "confidence": 0.0..1.0}]

    python chemsam_seg_worker.py segment --persistent
    → reads ``<image_path> <output_dir>`` lines from stdin and writes
      one JSON array per input, one per line (no pretty-printing).
"""

from __future__ import annotations

import json
import os
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

# ChemSAM model checkpoint path — conventional location inside the venv.
# Override via CHEMSAM_CKPT if the operator stored the weights elsewhere.
_DEFAULT_CKPT = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "models"
    / "chemsam"
    / "chemsam_vit_h.pth"
)


def _load_predictor():
    """Import torch + SAM lazily and build a ``SamPredictor``.

    Any ImportError is re-raised as a cleanly-formatted RuntimeError so
    the caller surface a "ChemSAM venv not set up" message rather than a
    raw traceback. We intentionally do *not* swallow other exceptions —
    bad checkpoint paths, CUDA failures, etc. should propagate.
    """
    try:
        import cv2  # noqa: F401 — import probe for opencv availability
        import torch
        from segment_anything import SamPredictor, sam_model_registry
    except ImportError:
        raise RuntimeError("ChemSAM worker dependency is unavailable") from None

    ckpt_path = os.environ.get("CHEMSAM_CKPT", _DEFAULT_CKPT)
    if not Path(ckpt_path).exists():
        raise RuntimeError("ChemSAM checkpoint is unavailable")

    model_type = os.environ.get("CHEMSAM_MODEL_TYPE", "vit_h")
    device = os.environ.get(
        "CHEMSAM_DEVICE",
        "cuda" if torch.cuda.is_available() else "cpu",
    )
    sam = sam_model_registry[model_type](checkpoint=ckpt_path)
    sam.to(device=device)
    return SamPredictor(sam)


def _extract_bboxes(predictor, image_path: str) -> list[tuple[list[int], float]]:
    """Run ChemSAM on a page image and return [(bbox, confidence), ...].

    ChemSAM emits SAM-style masks; we convert each mask to an axis-aligned
    bounding box. Confidence is the SAM predicted-IoU score.
    """
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError("ChemSAM input image could not be read")
    # SAM expects RGB.
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    predictor.set_image(img_rgb)

    # ChemSAM's published pipeline calls ``generate()`` on an
    # automatic-mask-generator over the whole page. We import it lazily to
    # avoid paying the cost when only ``segment()`` is exported for tests.
    from segment_anything import SamAutomaticMaskGenerator

    generator = SamAutomaticMaskGenerator(predictor.model)
    masks = generator.generate(img_rgb)

    results: list[tuple[list[int], float]] = []
    for mask in masks:
        x, y, w, h = mask["bbox"]  # SAM returns xywh
        x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
        score = float(mask.get("predicted_iou", 0.0))
        results.append(([x1, y1, x2, y2], score))

    # Deterministic order so the segment_index is stable between runs.
    results.sort(key=lambda item: (item[0][1], item[0][0]))
    return results


def segment(page_image_path: str, output_dir: str) -> list[dict]:
    """Run ChemSAM segmentation on a full patent page image."""
    t0 = time.monotonic()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    try:
        predictor = _load_predictor()
    except Exception as exc:
        return [{"error": safe_worker_error("ChemSAM model load", exc)}]

    try:
        bboxes = _extract_bboxes(predictor, page_image_path)
    except Exception as exc:
        return [{"error": safe_worker_error("ChemSAM segmentation", exc)}]

    # Crop each bbox from the original page and save as PNG.
    try:
        import cv2
    except ImportError:  # pragma: no cover — caught in _load_predictor
        return [{"error": "ChemSAM venv not set up — opencv missing"}]

    page = cv2.imread(page_image_path)
    if page is None:
        return [{"error": "ChemSAM input image could not be read"}]

    results: list[dict] = []
    page_stem = Path(page_image_path).stem

    for idx, (bbox, score) in enumerate(bboxes):
        x1, y1, x2, y2 = bbox
        crop = page[y1:y2, x1:x2]
        seg_path = out / f"{page_stem}_seg{idx:03d}.png"
        try:
            cv2.imwrite(str(seg_path), crop)
            h, w = crop.shape[:2]
        except Exception as exc:
            results.append(
                {
                    "segment_index": idx,
                    "bbox": bbox,
                    "image_path": "",
                    "width": 0,
                    "height": 0,
                    "error": safe_worker_error("ChemSAM crop write failed", exc),
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
                "confidence": score,
            }
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    # Inject timing into first result for metrics (matches DECIMER pattern).
    if results and "error" not in results[0]:
        results[0]["latency_ms"] = elapsed

    return results


def _run_persistent() -> None:
    """Read '<image_path> <output_dir>' lines from stdin; write one JSON
    array per input on a single line.

    Pre-loads the SAM predictor so the first real request doesn't pay the
    cold-start cost. A failure to load is reported once on stdout and the
    loop exits — callers will then see a clean error via the runner.
    """
    try:
        predictor = _load_predictor()
    except Exception as exc:
        print(json.dumps([{"error": safe_worker_error("ChemSAM model load", exc)}]), flush=True)
        return

    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            break
        # Split on the last space so paths with spaces in parent dirs
        # still work as long as the output_dir itself has no trailing
        # space — matches the DECIMER worker's contract.
        parts = stripped.rsplit(" ", 1)
        if len(parts) != 2:
            print(json.dumps([{"error": "ChemSAM worker input is invalid"}]), flush=True)
            continue
        img, out = parts
        try:
            # Reuse the already-loaded predictor for every call.
            bboxes = _extract_bboxes(predictor, img)
            out_dir = Path(out)
            out_dir.mkdir(parents=True, exist_ok=True)

            import cv2

            page = cv2.imread(img)
            if page is None:
                print(
                    json.dumps([{"error": "ChemSAM input image could not be read"}]),
                    flush=True,
                )
                continue

            results: list[dict] = []
            page_stem = Path(img).stem
            t0 = time.monotonic()
            for idx, (bbox, score) in enumerate(bboxes):
                x1, y1, x2, y2 = bbox
                crop = page[y1:y2, x1:x2]
                seg_path = out_dir / f"{page_stem}_seg{idx:03d}.png"
                cv2.imwrite(str(seg_path), crop)
                h, w = crop.shape[:2]
                results.append(
                    {
                        "segment_index": idx,
                        "bbox": bbox,
                        "image_path": str(seg_path),
                        "width": int(w),
                        "height": int(h),
                        "confidence": score,
                    }
                )
            if results:
                results[0]["latency_ms"] = int((time.monotonic() - t0) * 1000)
            print(json.dumps(results), flush=True)
        except Exception as exc:
            print(
                json.dumps([{"error": safe_worker_error("ChemSAM segmentation", exc)}]),
                flush=True,
            )


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "segment" and sys.argv[2] == "--persistent":
        _run_persistent()
        sys.exit(0)
    if len(sys.argv) < 4 or sys.argv[1] != "segment":
        print(
            json.dumps(
                [
                    {
                        "error": (
                            "Usage: chemsam_seg_worker.py segment <image> "
                            "<output_dir> | segment --persistent"
                        )
                    }
                ]
            )
        )
        sys.exit(1)
    result = segment(sys.argv[2], sys.argv[3])
    print(json.dumps(result))
    has_error = any("error" in r for r in result)
    sys.exit(1 if has_error else 0)
