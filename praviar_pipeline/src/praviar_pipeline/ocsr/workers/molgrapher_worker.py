#!/usr/bin/env python
"""MolGrapher OCSR worker — graph-based molecular structure recognition.

Runs in venvs/molgrapher/ Python (3.11). Uses keypoint detection + GNN
for a fundamentally different approach from captioning-based models
(MolScribe, DECIMER, MolNexTR). Provides maximum ensemble diversity.

Protocol:
    python molgrapher_worker.py predict <image_path>
    → JSON to stdout: {"smiles": "...", "confidence": 0.87, "valid": true}

MIT License (IBM Research / DS4SD).
"""

from __future__ import annotations

import json
import os
import sys
import time

try:
    from .worker_diagnostics import safe_worker_error as _package_safe_worker_error
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from worker_diagnostics import safe_worker_error as _script_safe_worker_error

    safe_worker_error = _script_safe_worker_error
else:
    safe_worker_error = _package_safe_worker_error

# Cairo library needed by CairoSVG — set path to Homebrew location
if sys.platform == "darwin":
    os.environ.setdefault(
        "DYLD_FALLBACK_LIBRARY_PATH",
        "/opt/homebrew/opt/cairo/lib:/opt/homebrew/lib:/usr/local/lib",
    )

_MODEL_CACHE: dict = {}


def get_model():
    """Get or create cached MolGrapher model."""
    if "model" not in _MODEL_CACHE:
        from molgrapher.models.molgrapher_model import MolgrapherModel

        model = MolgrapherModel(
            args={
                "force_cpu": True,  # No MPS support; CPU only on macOS
                "force_no_multiprocessing": True,
                "visualize": False,
                "visualize_rdkit": False,
                "save_mol_folder": "",
                "predict": True,
                "preprocess": True,
                "clean": False,
                "remove_captions": True,
                "node_classifier_variant": "gc_no_stereo_model",
            }
        )
        _MODEL_CACHE["model"] = model

    return _MODEL_CACHE["model"]


def predict(image_path: str) -> dict:
    """Run MolGrapher inference on a single image."""
    t0 = time.monotonic()

    try:
        model = get_model()
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Model load", exc),
            "tool": "molgrapher",
            "latency_ms": 0,
        }

    try:
        annotations = model.predict_batch([image_path])
        if not annotations:
            return {
                "smiles": "",
                "confidence": 0.0,
                "valid": False,
                "error": "No predictions returned",
                "tool": "molgrapher",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }

        result = annotations[0]
        smiles = result.get("smi", "") or ""
        confidence = float(result.get("conf", 0.0) or 0.0)
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Inference", exc),
            "tool": "molgrapher",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # Validate and canonicalise with RDKit
    valid = False
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            valid = True
            smiles = Chem.MolToSmiles(mol)
    except Exception:
        pass

    return {
        "smiles": smiles,
        "confidence": round(confidence, 4),
        "valid": valid,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "molgrapher",
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(json.dumps({"error": "Usage: molgrapher_worker.py predict <image_path>"}))
        sys.exit(1)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
