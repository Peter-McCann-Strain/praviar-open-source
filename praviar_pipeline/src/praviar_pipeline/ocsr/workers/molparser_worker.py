#!/usr/bin/env python
"""MolParser-Base OCSR worker — optional ICCV 2025 research adapter.

Runs in ``venvs/molparser/`` (Python 3.11) with torch + transformers +
pillow. MolParser-Base pairs a Swin-B encoder with a 2-layer MLP +
BART decoder to emit **E-SMILES** — an extended SMILES dialect with
XML-like Markush annotations (``<a>``, ``<r>``, ``<c>``, ``<dum>``).
Reference: arXiv 2411.11098. The upstream paper does not constitute a Praviar
benchmark, checkpoint-rights review, or production-readiness receipt.

Protocol (matches the rest of the OCSR worker family):

    python molparser_worker.py predict <image_path>
    → one JSON line to stdout:
       {
         "smiles": "...",          # canonical RDKit SMILES; "" for Markush
         "confidence": 0.85,       # fixed-default — decoder emits no score
         "valid": true | false,
         "tool": "molparser",
         "latency_ms": int,
         "error": "",
         "is_markush": bool,
         "cxsmiles": "..."         # only when is_markush=True
       }

    python molparser_worker.py predict --persistent
    → stdin loop: read image path, write one JSON line per input.
      Terminated by an empty line / EOF.
"""

from __future__ import annotations

import json
import os
import sys
import time

try:
    from .model_integrity import (
        verified_model_directory_from_ml_bom as _package_verified_model_directory,
    )
    from .worker_diagnostics import (
        SUPPRESSED_DEPENDENCY_OUTPUT as _PACKAGE_SUPPRESSED_DEPENDENCY_OUTPUT,
    )
    from .worker_diagnostics import safe_worker_error as _package_safe_worker_error
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from model_integrity import (
        verified_model_directory_from_ml_bom as _script_verified_model_directory,
    )
    from worker_diagnostics import (
        SUPPRESSED_DEPENDENCY_OUTPUT as _SCRIPT_SUPPRESSED_DEPENDENCY_OUTPUT,
    )
    from worker_diagnostics import safe_worker_error as _script_safe_worker_error

    SUPPRESSED_DEPENDENCY_OUTPUT = _SCRIPT_SUPPRESSED_DEPENDENCY_OUTPUT
    safe_worker_error = _script_safe_worker_error
    verified_model_directory_from_ml_bom = _script_verified_model_directory
else:
    SUPPRESSED_DEPENDENCY_OUTPUT = _PACKAGE_SUPPRESSED_DEPENDENCY_OUTPUT
    safe_worker_error = _package_safe_worker_error
    verified_model_directory_from_ml_bom = _package_verified_model_directory

# Root for the MolParser package/checkpoint. Overridable via env so the
# installer can point at wherever it actually dropped the weights.
MOLPARSER_ROOT = os.environ.get(
    "MOLPARSER_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "models", "molparser"),
)
if os.path.isdir(MOLPARSER_ROOT):
    sys.path.insert(0, MOLPARSER_ROOT)

# The adapter lives in the main package; the worker imports it via the
# parent directory so both one-shot and persistent modes can reach it
# without requiring a full praviar_pipeline install inside the molparser venv.
_OCSR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _OCSR_DIR not in sys.path:
    sys.path.insert(0, _OCSR_DIR)

_MODEL_CACHE: dict = {}
_MOLPARSER_MODEL_ID = "molparser/molparser-base"

# Default confidence for MolParser outputs. The paper's decoder does
# not emit per-sequence logit probabilities, so we assign a fixed value
# to any RDKit-valid output and 0.0 to invalid ones. The ensemble
# layer above reconciles this with model-specific priors.
_DEFAULT_VALID_CONFIDENCE = 0.85


def _get_device():
    """Return best available torch device (MPS → CUDA → CPU)."""
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_model():
    """Load MolParser-Base model + tokenizer (cached).

    Raises:
        ImportError: with a clear message if the molparser venv has
            not been set up (torch / transformers / molparser missing).
        FileNotFoundError: if weights can't be located.
    """
    if "model" in _MODEL_CACHE:
        return (
            _MODEL_CACHE["model"],
            _MODEL_CACHE["processor"],
            _MODEL_CACHE["tokenizer"],
            _MODEL_CACHE["device"],
        )

    try:
        import torch  # noqa: F401
        from transformers import AutoProcessor, AutoTokenizer, VisionEncoderDecoderModel
    except ImportError:
        raise ImportError(
            "molparser venv not set up — install torch, transformers, pillow "
            "into praviar_pipeline/venvs/molparser/. See "
            "praviar_pipeline/venvs/molparser/README.md for the full recipe."
        ) from None

    ckpt_path = os.environ.get("MOLPARSER_CKPT", "")
    if not ckpt_path:
        for candidate in (
            os.path.join(MOLPARSER_ROOT, "molparser-base"),
            os.path.join(MOLPARSER_ROOT, "checkpoints", "molparser-base"),
            os.path.expanduser("~/.cache/molparser/molparser-base"),
        ):
            if os.path.isdir(candidate):
                ckpt_path = candidate
                break

    if not ckpt_path or not os.path.isdir(ckpt_path):
        raise FileNotFoundError(
            "MolParser-Base weights not found. Set MOLPARSER_CKPT to the "
            "HuggingFace snapshot directory (default lookup: "
            f"{MOLPARSER_ROOT}/molparser-base/). See "
            "praviar_pipeline/venvs/molparser/README.md for download instructions."
        )

    device = _get_device()

    # Network/remote code are disabled. The context re-verifies the complete
    # filesystem identity and tree digest after every loader has finished.
    with verified_model_directory_from_ml_bom(
        ckpt_path,
        model_id=_MOLPARSER_MODEL_ID,
    ) as verified_ckpt_path:
        model = VisionEncoderDecoderModel.from_pretrained(  # nosec B615
            verified_ckpt_path,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        )
        model = model.to(device).eval()
        processor = AutoProcessor.from_pretrained(  # nosec B615
            verified_ckpt_path,
            local_files_only=True,
            trust_remote_code=False,
        )
        tokenizer = AutoTokenizer.from_pretrained(  # nosec B615
            verified_ckpt_path,
            local_files_only=True,
            trust_remote_code=False,
        )

    _MODEL_CACHE["model"] = model
    _MODEL_CACHE["processor"] = processor
    _MODEL_CACHE["tokenizer"] = tokenizer
    _MODEL_CACHE["device"] = device
    return model, processor, tokenizer, device


def _base_error(exc: Exception, elapsed_ms: int, kind: str) -> dict:
    return {
        "smiles": "",
        "confidence": 0.0,
        "valid": False,
        "error": safe_worker_error(kind, exc),
        "tool": "molparser",
        "latency_ms": elapsed_ms,
        "is_markush": False,
        "cxsmiles": "",
    }


def predict(image_path: str) -> dict:
    """Run MolParser-Base on a single image → normalised worker dict."""
    t0 = time.monotonic()

    try:
        from PIL import Image
    except ImportError as exc:
        return _base_error(exc, 0, "Pillow import")

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as exc:
        return _base_error(exc, 0, "Image load")

    try:
        model, processor, tokenizer, device = get_model()
    except (ImportError, FileNotFoundError) as exc:
        return _base_error(exc, int((time.monotonic() - t0) * 1000), "Model load")
    except Exception as exc:
        return _base_error(exc, int((time.monotonic() - t0) * 1000), "Model load")

    try:
        import torch

        inputs = processor(images=img, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(device)
        with torch.no_grad():
            generated = model.generate(
                pixel_values=pixel_values,
                max_new_tokens=512,
                num_beams=4 if device.type != "cpu" else 1,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        esmiles = decoded[0].strip() if decoded else ""
    except Exception as exc:
        return _base_error(exc, int((time.monotonic() - t0) * 1000), "Inference")

    # Import the adapter lazily — the worker venv doesn't necessarily
    # have praviar_pipeline installed, but esmiles_adapter is pure-python and
    # is resolvable via the sys.path hack at module top.
    try:
        from esmiles_adapter import esmiles_to_cxsmiles, esmiles_to_rdkit, parse_esmiles
    except ImportError:
        # Fall back to the fully-qualified path if the worker is being
        # run from the main venv (e.g. unit tests).
        from praviar_pipeline.ocsr.esmiles_adapter import (
            esmiles_to_cxsmiles,
            esmiles_to_rdkit,
            parse_esmiles,
        )

    parsed = parse_esmiles(esmiles)
    is_markush = bool(parsed["is_markush"])

    canonical_smiles = ""
    cxsmiles = ""
    valid = False
    confidence = 0.0

    try:
        if not esmiles:
            # Decoder emitted nothing intelligible.
            pass
        elif is_markush:
            # RDKit can't canonicalise Markush — hand back CXSMILES, mark
            # smiles empty, valid=False (ensemble layer does not trust the
            # SMILES channel for Markush; downstream Markush handling takes
            # over). is_markush=True signals the routing.
            cxsmiles = esmiles_to_cxsmiles(esmiles)
            # Valid remains False — Markush is not an RDKit-valid compound.
        else:
            canonical_smiles = esmiles_to_rdkit(esmiles)
            if canonical_smiles:
                valid = True
                confidence = _DEFAULT_VALID_CONFIDENCE
    except Exception as exc:
        return _base_error(exc, int((time.monotonic() - t0) * 1000), "Conversion")

    return {
        "smiles": canonical_smiles,
        "confidence": round(float(confidence), 4),
        "valid": valid,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "molparser",
        "error": "",
        "is_markush": is_markush,
        "cxsmiles": cxsmiles,
    }


def _run_persistent() -> None:
    """stdin loop → one JSON line per image path until empty-line / EOF.

    Stdout noise from model-loading libraries (transformers banners,
    torch device hints) is redirected to stderr so the JSON-per-line
    protocol isn't corrupted. Matches the pattern used by
    ``markushgrapher_worker.py``.
    """
    import contextlib
    import io

    loader_output = io.StringIO()
    try:
        with (
            contextlib.redirect_stdout(loader_output),
            contextlib.redirect_stderr(loader_output),
        ):
            get_model()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "smiles": "",
                    "confidence": 0.0,
                    "valid": False,
                    "error": safe_worker_error("Model load at startup", exc),
                    "tool": "molparser",
                    "latency_ms": 0,
                    "is_markush": False,
                    "cxsmiles": "",
                }
            ),
            flush=True,
        )
        return

    for line in sys.stdin:
        image_path = line.strip()
        if not image_path:
            break
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            result = predict(image_path)
        captured = buf.getvalue()
        if captured:
            sys.stderr.write(SUPPRESSED_DEPENDENCY_OUTPUT + "\n")
            sys.stderr.flush()
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "predict" and sys.argv[2] == "--persistent":
        _run_persistent()
        sys.exit(0)
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(
            json.dumps(
                {"error": "Usage: molparser_worker.py predict <image_path> | predict --persistent"}
            )
        )
        sys.exit(1)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
