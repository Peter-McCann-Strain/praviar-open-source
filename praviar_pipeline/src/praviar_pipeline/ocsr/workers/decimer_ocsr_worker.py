#!/usr/bin/env python
"""DECIMER OCSR worker — runs in venvs/decimer/ Python.

Protocol:
    python decimer_ocsr_worker.py predict <image_path>
    → JSON to stdout: {"smiles": "...", "confidence": 0.0, "valid": true}

Note: DECIMER does not produce confidence scores (always 0.0).
"""

from __future__ import annotations

import json
import sys
import time

try:
    from .worker_diagnostics import safe_worker_error as _package_safe_worker_error
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from worker_diagnostics import safe_worker_error as _script_safe_worker_error

    safe_worker_error = _script_safe_worker_error
else:
    safe_worker_error = _package_safe_worker_error


def predict(image_path: str) -> dict:
    """Run DECIMER prediction on a single image."""
    t0 = time.monotonic()

    try:
        from DECIMER import predict_SMILES
    except ImportError:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": "DECIMER not installed in this venv",
        }

    try:
        smiles = predict_SMILES(image_path)
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("DECIMER prediction", exc),
        }

    # Validate with RDKit
    valid = False
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            valid = True
            smiles = Chem.MolToSmiles(mol)  # Canonicalise
    except Exception:
        pass

    return {
        "smiles": smiles,
        "confidence": 0.0,  # DECIMER has no confidence scores
        "valid": valid,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "decimer",
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(json.dumps({"error": "Usage: decimer_ocsr_worker.py predict <image_path>"}))
        sys.exit(1)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
