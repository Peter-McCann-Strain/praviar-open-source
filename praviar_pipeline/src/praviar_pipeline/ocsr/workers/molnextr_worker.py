#!/usr/bin/env python
"""MolNexTR OCSR worker — runs in venvs/molnextr/ Python.

Protocol:
    python molnextr_worker.py predict <image_path>
    → JSON to stdout: {"smiles": "...", "confidence": 0.0, "valid": true}

MolNexTR uses a ConvNeXt+ViT dual-stream encoder. No confidence scores.
Requires: MolNexTR installed from git + checkpoint molnextr_best.pth.
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

try:
    from .model_policy import verified_model_path as _package_verified_model_path
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from model_policy import verified_model_path as _script_verified_model_path

    _verified_model_path = _script_verified_model_path
else:
    _verified_model_path = _package_verified_model_path

# Enable MPS fallback for unsupported ops — transparent CPU fallback
# without crashing the whole model.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

_MODEL_CACHE: dict = {}


def get_model():
    """Get or create cached MolNexTR model via the singleton."""
    if "model" not in _MODEL_CACHE:
        # MolNexTR's upstream singleton uses pystow. Bind it to Praviar's
        # explicit model root and prohibit its runtime download path before
        # asking the singleton to load anything.
        checkpoint_path = _verified_model_path("molnextr/molnextr_best")
        os.environ["PYSTOW_HOME"] = str(checkpoint_path.parents[1])

        # We add the configured MolNexTR source tree to sys.path so the package
        # can be imported in its isolated worker environment.
        molnextr_root = os.environ.get(
            "MOLNEXTR_ROOT",
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "..", "models", "molnextr"
            ),
        )
        if os.path.isdir(molnextr_root) and molnextr_root not in sys.path:
            sys.path.insert(0, molnextr_root)

        import MolNexTR.molnextr as molnextr_module

        def _block_runtime_download(*_args, **_kwargs):
            raise RuntimeError(
                "MolNexTR runtime downloads are disabled; use the model registry CLI"
            )

        molnextr_module.pystow.ensure = _block_runtime_download

        model = molnextr_module.MolNexTRSingleton.get_instance()
        _MODEL_CACHE["model"] = model

    return _MODEL_CACHE["model"]


def predict(image_path: str) -> dict:
    """Run MolNexTR inference on a single image."""
    t0 = time.monotonic()

    try:
        get_model()
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Model load", exc),
            "tool": "molnextr",
            "latency_ms": 0,
        }

    try:
        from MolNexTR.molnextr import get_predictions

        output = get_predictions(image_path, smiles=True)
        smiles = output.get("predicted_smiles", output.get("smiles", ""))
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Inference", exc),
            "tool": "molnextr",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # Validate with RDKit
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
        "confidence": 0.0,  # MolNexTR has no confidence scores
        "valid": valid,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "molnextr",
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(json.dumps({"error": "Usage: molnextr_worker.py predict <image_path>"}))
        sys.exit(1)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
