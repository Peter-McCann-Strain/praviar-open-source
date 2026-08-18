#!/usr/bin/env python
"""MolScribe OCSR worker — inference-only, modern stack.

Runs in venvs/molscribe/ with torch>=2.11, numpy>=2, timm>=1.0,
albumentations>=2.0, rdkit. Uses the lucas-morin MolScribe fork
with patched swin_transformer.py and augment.py for modern deps.

Protocol:
    python molscribe_worker.py predict <image_path>
    → JSON to stdout: {"smiles": "...", "confidence": 0.87, "valid": true}
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

MOLSCRIBE_ROOT = os.environ.get(
    "MOLSCRIBE_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "models", "molscribe"),
)
if os.path.isdir(MOLSCRIBE_ROOT):
    sys.path.insert(0, MOLSCRIBE_ROOT)

MOLSCRIBE_MODEL_ID = "molscribe/swin_base_char_aux_1m680k"
_MODEL_CACHE: dict = {}


def get_model(device=None):
    """Get or create cached model instance."""
    import torch

    if device is None:
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

    if "model" not in _MODEL_CACHE:
        from molscribe import MolScribe

        ckpt_path = os.environ.get("MOLSCRIBE_CKPT", "")
        if not ckpt_path:
            for c in [
                os.path.join(MOLSCRIBE_ROOT, "ckpts", "swin_base_char_aux_1m680k.pth"),
                os.path.expanduser("~/.cache/molscribe/swin_base_char_aux_1m680k.pth"),
            ]:
                if os.path.isfile(c):
                    ckpt_path = c
                    break

        if not ckpt_path or not os.path.isfile(ckpt_path):
            raise FileNotFoundError(
                f"MolScribe checkpoint not found. Set MOLSCRIBE_CKPT or place "
                f"swin_base_char_aux_1m680k.pth in {MOLSCRIBE_ROOT}/ckpts/"
            )

        verify_model_checksum_from_ml_bom(
            ckpt_path,
            model_id=MOLSCRIBE_MODEL_ID,
        )
        model = MolScribe(ckpt_path, device=device)
        _MODEL_CACHE["model"] = model

    return _MODEL_CACHE["model"]


def predict(image_path: str) -> dict:
    """Run MolScribe inference on a single image."""
    t0 = time.monotonic()

    try:
        model = get_model()
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Model load", exc),
            "tool": "molscribe",
            "latency_ms": 0,
        }

    try:
        output = model.predict_image_file(image_path, return_confidence=True)
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Inference", exc),
            "tool": "molscribe",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    smiles = output.get("smiles", "")
    confidence = float(output.get("confidence", 0.0))

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
        "tool": "molscribe",
        "error": "",
    }


def predict_beam(image_path: str, beam_size: int = 5, n_best: int = 5) -> dict:
    """Run MolScribe with beam search, returning top-N candidates for reranking."""
    t0 = time.monotonic()

    try:
        model = get_model()
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "candidates": [],
            "error": safe_worker_error("Model load", exc),
            "tool": "molscribe",
            "latency_ms": 0,
        }

    try:
        output = model.predict_image_file(
            image_path,
            return_confidence=True,
            beam_size=beam_size,
            n_best=n_best,
        )
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "candidates": [],
            "error": safe_worker_error("Inference", exc),
            "tool": "molscribe",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    smiles = output.get("smiles", "")
    confidence = float(output.get("confidence", 0.0))

    # Extract beam candidates
    candidates = []
    for cand in output.get("beam_candidates", []):
        cand_smi = cand.get("smiles", "")
        cand_score = cand.get("score", 0.0)
        # Validate each candidate
        cand_valid = False
        try:
            from rdkit import Chem

            mol = Chem.MolFromSmiles(cand_smi)
            if mol is not None:
                cand_valid = True
                cand_smi = Chem.MolToSmiles(mol)
        except Exception:
            pass
        candidates.append(
            {
                "smiles": cand_smi,
                "score": round(float(cand_score), 4),
                "valid": cand_valid,
            }
        )

    # Validate top prediction
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
        "candidates": candidates,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "molscribe",
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("predict", "predict_beam"):
        print(json.dumps({"error": "Usage: molscribe_worker.py predict|predict_beam <image_path>"}))
        sys.exit(1)
    if sys.argv[1] == "predict_beam":
        beam_size = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        result = predict_beam(sys.argv[2], beam_size=beam_size, n_best=beam_size)
    else:
        result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
