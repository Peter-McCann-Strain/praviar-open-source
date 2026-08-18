#!/usr/bin/env python
"""IBM PatCID MolClassifier worker — runs in venvs/molclassifier/.

A Mask R-CNN adapter for the upstream PatCID class vocabulary
``['Background', 'Clean', 'Markush', 'Trash']``. The worker is optional and
activation-blocked unless its checkpoint, rights, calibration, and rollout
contracts pass; this module makes no Praviar benchmark or production-readiness
claim.

Protocol (mirrors ``decimer_seg_worker.py`` / ``chemsam_seg_worker.py``):

    python molclassifier_worker.py infer <image_path>
        → JSON object on stdout:
          {"category": "molecule|markush|non_chemical",
           "raw_label": "Clean|Markush|Trash|Background",
           "confidence": 0.0..1.0,
           "n_detections": int,
           "latency_ms": int,
           "error": ""}

    python molclassifier_worker.py infer --persistent
        → reads ``<image_path>`` lines from stdin and writes one JSON object
          per input on a single line. Pre-loads the model so the first real
          request doesn't pay cold-start cost.

The model checkpoint is read from ``MOLCLASSIFIER_CKPT`` if set, otherwise
the conventional path ``<repo-root>/praviar_pipeline/models/molclassifier/molclassifier_model.chpt``.
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
    from .worker_diagnostics import safe_worker_error as _package_safe_worker_error
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from model_integrity import (
        verify_model_checksum_from_ml_bom as _script_verify_model_checksum,
    )
    from worker_diagnostics import safe_worker_error as _script_safe_worker_error

    safe_worker_error = _script_safe_worker_error
    verify_model_checksum_from_ml_bom = _script_verify_model_checksum
else:
    safe_worker_error = _package_safe_worker_error
    verify_model_checksum_from_ml_bom = _package_verify_model_checksum

# Mapping: PatCID label → production ImageCategory string.
# Background and Trash both indicate "not a chemical structure to be OCSR'd";
# Clean is a standard chemical structure; Markush has R-groups / scaffolds.
# Polymer images get classified as Markush by PatCID (per their paper) — we
# accept that mapping rather than introduce a 5th category.
LABEL_MAP: dict[str, str] = {
    "Background": "non_chemical",
    "Clean": "molecule",
    "Markush": "markush",
    "Trash": "non_chemical",
}

_DEFAULT_CKPT = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "models"
    / "molclassifier"
    / "molclassifier_model.chpt"
)
MOLCLASSIFIER_MODEL_ID = "molclassifier/local"


def _required_float_env(name: str) -> float:
    """Read a required float env var; raise if missing or unparseable.

    Thresholds come from Settings, which sets the env vars, not from baked-in
    literals.
    """
    raw = os.environ.get(name)
    if raw is None:
        raise RuntimeError(
            f"Required env var {name} is not set. "
            "Set it via Settings or pass it explicitly when invoking the worker."
        )
    try:
        return float(raw)
    except ValueError:
        pass
    raise RuntimeError(f"{name} must be a valid float") from None


def _load_model():
    """Build MaskRCNN + load checkpoint. Returns ``(model, classes, device)``.

    Any ImportError is re-raised as a cleanly-formatted RuntimeError so the
    caller sees a "venv not set up" message rather than a raw traceback.
    """
    try:
        import torch
        import torchvision
    except ImportError:
        raise RuntimeError("MolClassifier worker dependency is unavailable") from None

    ckpt_path = os.environ.get("MOLCLASSIFIER_CKPT", _DEFAULT_CKPT)
    if not Path(ckpt_path).exists():
        raise RuntimeError("MolClassifier checkpoint is unavailable")

    verify_model_checksum_from_ml_bom(
        ckpt_path,
        model_id=MOLCLASSIFIER_MODEL_ID,
    )
    # Checkpoint loading is restricted to tensors and primitive metadata.
    ckpt = torch.load(  # nosemgrep
        ckpt_path,
        map_location="cpu",
        weights_only=True,
    )
    classes = ckpt["classes"]

    device = torch.device(
        os.environ.get("MOLCLASSIFIER_DEVICE")
        or (
            "mps"
            if torch.backends.mps.is_available()
            else "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )
    )

    box_score_thresh = _required_float_env("MOLCLASSIFIER_BOX_THRESH")
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(
        weights=None,
        box_nms_thresh=0.1,
        box_score_thresh=box_score_thresh,
        num_classes=len(classes),
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    return model, classes, device


def _classify_one(model, classes, device, image_path: str) -> dict:
    """Run inference on a single image; return a result dict."""
    import torch
    from PIL import Image
    from torchvision.transforms import functional

    t0 = time.monotonic()

    # Image read errors and inference errors raise. The caller (the
    # subprocess driver in classifier_v2.py / ensemble runner) sees the
    # non-zero exit + stderr and surfaces it as a real error rather than
    # silently misclassifying the image as non_chemical.
    img = Image.open(image_path).convert("RGB")
    tensor = functional.pil_to_tensor(img)
    tensor = functional.convert_image_dtype(tensor).to(device)

    with torch.no_grad():
        outputs = model([tensor])

    out = outputs[0]
    labels = out["labels"].cpu().tolist()
    scores = out["scores"].cpu().tolist()

    if not labels:
        # No detection above threshold. Do not silently relabel this as
        # non_chemical; that conflates
        # "MaskRCNN definitively saw background" with "MaskRCNN saw nothing
        # above box_score_thresh." The downstream classifier wrapper (or
        # caller) applies the reviewed task-local routing policy instead of
        # silently treating absence of a detection as a semantic negative.
        return {
            "category": "no_detections",
            "raw_label": "no_detections",
            "confidence": 0.0,
            "n_detections": 0,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "error": "",
        }

    # Highest-confidence detection wins
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    raw_label = classes[labels[best_idx]] if labels[best_idx] < len(classes) else "Background"
    category = LABEL_MAP.get(raw_label, "non_chemical")

    return {
        "category": category,
        "raw_label": raw_label,
        "confidence": float(scores[best_idx]),
        "n_detections": len(labels),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "error": "",
    }


def _run_persistent() -> None:
    """Read image paths from stdin; write one JSON object per line."""
    try:
        model, classes, device = _load_model()
    except Exception as exc:
        print(json.dumps({"error": safe_worker_error("MolClassifier model load", exc)}), flush=True)
        return

    for line in sys.stdin:
        image_path = line.strip()
        if not image_path:
            break
        try:
            result = _classify_one(model, classes, device, image_path)
        except Exception as exc:
            result = {"error": safe_worker_error("MolClassifier inference", exc)}
        print(json.dumps(result), flush=True)


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "infer" and sys.argv[2] == "--persistent":
        _run_persistent()
        return 0
    if len(sys.argv) < 3 or sys.argv[1] != "infer":
        print(
            json.dumps(
                {"error": "Usage: molclassifier_worker.py infer <image_path> | infer --persistent"}
            )
        )
        return 1
    try:
        model, classes, device = _load_model()
    except Exception as exc:
        print(json.dumps({"error": safe_worker_error("MolClassifier model load", exc)}))
        return 1
    try:
        result = _classify_one(model, classes, device, sys.argv[2])
    except Exception as exc:
        result = {"error": safe_worker_error("MolClassifier inference", exc)}
    print(json.dumps(result))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
