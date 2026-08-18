#!/usr/bin/env python
"""MarkushGrapher 2.0 worker — runs in venvs/markushgrapher/ (Python 3.10).

Full v2 pipeline: ChemicalOCR (text+bbox extraction) → MarkushGrapher (CXSMILES prediction).
ChemicalOCR uses mlx-vlm on Apple Silicon for fast inference.

Architecture:
  1. ChemicalOCR (Idefics3-based) extracts text labels and bounding boxes from the image
  2. MarkushGrapher (UDOP-based) takes image + text + boxes → predicts CXSMILES

Protocol:
    python markushgrapher_worker.py predict <image_path>
    → JSON to stdout: {
        "smiles": "...",
        "confidence": 0.0,
        "confidence_available": false,
        "valid": false,
        ...
      }

MarkushGrapher-2 does not emit a calibrated per-prediction confidence.  Its
numeric confidence is therefore a transport sentinel, explicitly marked
unavailable, and can only be collected for shadow evaluation.  A decoded
Markush result also remains review-only until the official reference-aware
evaluator has checked the backbone and all R-group, positional, and frequency
features.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Any

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

# Paths — all permanent under the venvs/markushgrapher/src/ directory
_VENV_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "venvs", "markushgrapher", "src"
)
_MARKUSHGRAPHER_ROOT = os.path.abspath(os.path.join(_VENV_SRC, "MarkushGrapher"))
_MODEL_DIR = os.path.join(_MARKUSHGRAPHER_ROOT, "models", "markushgrapher-2")
_OCR_MODEL_DIR = os.path.join(_MARKUSHGRAPHER_ROOT, "models", "chemicalocr")
_MARKUSHGRAPHER_WEIGHT_PATH = os.path.join(_MODEL_DIR, "pytorch_model.bin")
_CHEMICALOCR_WEIGHT_PATH = os.path.join(_OCR_MODEL_DIR, "model.safetensors")
_MARKUSHGRAPHER_MODEL_ID = "markushgrapher/markushgrapher-2/pytorch_model"
_CHEMICALOCR_MODEL_ID = "markushgrapher/chemicalocr/model"
_UPSTREAM_REPOSITORY = "https://github.com/DS4SD/MarkushGrapher"
_UPSTREAM_INFERENCE_CONFIG = "config/predict.yaml"
_UPSTREAM_IMAGE_SIZE = 512
_ALLOW_NO_OCR_FALLBACK = os.environ.get("PRAVIAR_MARKUSHGRAPHER_ALLOW_NO_OCR", "").lower() in {
    "1",
    "true",
    "yes",
}

# Add MarkushGrapher to path for its submodules
sys.path.insert(0, _MARKUSHGRAPHER_ROOT)

_CACHE: dict = {}


def _aspect_preserving_resize(image, target: int = 512):
    """Letterbox to the upstream 512-square contract without distorting geometry."""
    from PIL import Image

    img = image.convert("RGB")
    width, height = img.size
    if width <= 0 or height <= 0:
        return img.resize((target, target))

    scale = min(target / width, target / height)
    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))
    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target, target), "white")
    canvas.paste(resized, ((target - new_width) // 2, (target - new_height) // 2))
    return canvas


def _validate_decoded_structure(smiles: str) -> tuple[bool, bool, str]:
    """Validate what can be validated locally, and fail closed on Markush semantics.

    The official MG2 metric is reference-aware: a Markush prediction is correct
    only when its molecular backbone and every R-group, positional (``m:``),
    and frequency (``Sg:``) feature match ground truth.  RDKit can strictly
    parse a complete CXSMILES string, but it silently drops positional
    variation in supported releases.  A worker with no reference structure
    therefore cannot honestly call a Markush prediction semantically valid.
    """
    candidate = (smiles or "").strip()
    is_markush = "|" in candidate
    if not candidate:
        return False, is_markush, "failed"

    try:
        from rdkit import Chem

        if is_markush:
            # RDKit's generated stubs expose the Boost.Python setters without
            # their boolean types. Keep the runtime properties explicit while
            # isolating that upstream type gap to this boundary.
            params = cast("Any", Chem.SmilesParserParams())
            params.allowCXSMILES = True
            params.strictCXSMILES = True
            params.parseName = False
            molecule = Chem.MolFromSmiles(candidate, params)
        else:
            molecule = Chem.MolFromSmiles(candidate)
    except Exception:
        molecule = None

    if molecule is None:
        return False, is_markush, "failed"
    if is_markush:
        # Syntax is parseable, but semantic validity requires the official
        # tokenizer/evaluator plus a reference.  Never promote this locally.
        return False, True, "reference_required"
    return True, False, "passed"


def _get_device():
    """Return best available torch device."""
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_ocr_model():
    """Load ChemicalOCR model (cached)."""
    if "ocr" not in _CACHE:
        from markushgrapher.ocr.chemical_ocr import Chemical_OCR

        verify_model_checksum_from_ml_bom(
            _CHEMICALOCR_WEIGHT_PATH,
            model_id=_CHEMICALOCR_MODEL_ID,
        )
        ocr = Chemical_OCR(model_path=_OCR_MODEL_DIR, batch_size=1)
        _CACHE["ocr"] = ocr
    return _CACHE["ocr"]


def run_ocr(image) -> tuple[list[str], list[list[float]]]:
    """Run ChemicalOCR on a PIL image, return (words, normalized_boxes)."""
    from markushgrapher.ocr.chemical_ocr import clean_ocr_text, parse_ocr_string

    ocr = get_ocr_model()
    prompt = ocr.prepare_prompt()

    if ocr.backend == "mlx":
        texts = ocr._generate_mlx([image], prompt)
    elif ocr.backend == "vllm":
        texts = ocr._generate_vllm([image], prompt)
    else:
        texts = ocr._generate_transformers([image], prompt)

    if not texts or not texts[0]:
        return [], []

    cleaned = clean_ocr_text(texts[0])
    words, boxes = parse_ocr_string(cleaned)
    return words, boxes


def get_model():
    """Load MarkushGrapher 2.0 model (cached)."""
    if "model" not in _CACHE:
        import torch
        from transformers.models.markushgrapher.configuration_markushgrapher import (
            MarkushgrapherConfig,
        )
        from transformers.models.markushgrapher.image_processing_markushgrapher import (
            MarkushgrapherImageProcessor,
        )
        from transformers.models.markushgrapher.modeling_markushgrapher import (
            MarkushgrapherForConditionalGeneration,
        )
        from transformers.models.markushgrapher.processing_markushgrapher import (
            MarkushgrapherProcessor,
        )
        from transformers.models.markushgrapher.tokenization_markushgrapher import (
            MarkushgrapherTokenizer,
        )

        device = _get_device()

        # Local-only loading follows whole-tree model-integrity verification.
        config = MarkushgrapherConfig.from_pretrained(  # nosec B615
            _MODEL_DIR,
            local_files_only=True,
        )
        config.output_attentions = False
        config.image_size = _UPSTREAM_IMAGE_SIZE
        config.architecture_variant = "me-lf-stack-1"

        tokenizer = MarkushgrapherTokenizer.from_pretrained(  # nosec B615
            _MODEL_DIR,
            local_files_only=True,
        )

        verify_model_checksum_from_ml_bom(
            _MARKUSHGRAPHER_WEIGHT_PATH,
            model_id=_MARKUSHGRAPHER_MODEL_ID,
        )
        model = MarkushgrapherForConditionalGeneration.from_pretrained(  # nosec B615
            _MODEL_DIR,
            config=config,
            local_files_only=True,
        )

        # Use MPS if available, but fall back to CPU for generation if needed
        if device.type == "mps":
            try:
                model = model.to(device).eval()
            except Exception:
                device = torch.device("cpu")
                model = model.to(device).eval()
        else:
            model = model.to(device).eval()

        # Image processor (no OCR — we use ChemicalOCR separately)
        image_processor = MarkushgrapherImageProcessor(
            apply_ocr=False,
            size={"height": _UPSTREAM_IMAGE_SIZE, "width": _UPSTREAM_IMAGE_SIZE},
        )

        processor = MarkushgrapherProcessor(
            image_processor=image_processor,
            tokenizer=tokenizer,
        )

        _CACHE["model"] = model
        _CACHE["tokenizer"] = tokenizer
        _CACHE["processor"] = processor
        _CACHE["device"] = device

    return (_CACHE["model"], _CACHE["tokenizer"], _CACHE["processor"], _CACHE["device"])


def predict(image_path: str) -> dict:
    """Run full MarkushGrapher 2.0 pipeline on a single image."""
    t0 = time.monotonic()

    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        # ChemicalOCR returns 0..1 boxes relative to the image it sees.  Feed
        # both OCR and MG2 the identical letterboxed canvas so those boxes
        # remain aligned with the visual encoder input.
        img_resized = _aspect_preserving_resize(img, _UPSTREAM_IMAGE_SIZE)
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "confidence_available": False,
            "valid": False,
            "error": safe_worker_error("Image load", exc),
            "tool": "markushgrapher",
            "latency_ms": 0,
        }

    # Step 1: Run ChemicalOCR to extract text + bounding boxes.
    try:
        words, boxes = run_ocr(img_resized)
        ocr_time = time.monotonic() - t0
    except Exception as exc:
        ocr_time = time.monotonic() - t0
        if not _ALLOW_NO_OCR_FALLBACK:
            return {
                "smiles": "",
                "confidence": 0.0,
                "confidence_available": False,
                "valid": False,
                "error": safe_worker_error("ChemicalOCR", exc),
                "tool": "markushgrapher",
                "latency_ms": int(ocr_time * 1000),
                "is_markush": False,
                "ocr_words": 0,
                "ocr_time_ms": int(ocr_time * 1000),
            }
        words, boxes = [], []
        sys.stderr.write(safe_worker_error("ChemicalOCR explicit no-OCR fallback", exc) + "\n")

    # Step 2: Run MarkushGrapher
    try:
        model_parts = get_model()
        if len(model_parts) != 6:
            raise RuntimeError(
                "paper-faithful MarkushTokenizer and CXSMILESTokenizer are unavailable"
            )
        model, _tokenizer, processor, device = model_parts[:4]
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "confidence_available": False,
            "valid": False,
            "error": safe_worker_error("Model load", exc),
            "tool": "markushgrapher",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    try:
        import torch

        # The official inference config uses a 512-square input.  Letterbox
        # instead of stretching molecular geometry to that square.
        # If OCR found text, provide it to the processor
        if words and boxes:
            inputs = processor(
                images=img_resized,
                text=words,
                boxes=boxes,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding="max_length",
            )
        else:
            # No-OCR fallback: provide a single PAD token
            inputs = processor(
                images=img_resized,
                text=[""],
                boxes=[[0, 0, 0, 0]],
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding="max_length",
            )

        # Move all inputs to device
        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.no_grad():
            generated = model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                bbox=inputs.get("bbox"),
                pixel_values=inputs["pixel_values"],
                max_new_tokens=512,
                num_beams=4 if device.type != "cpu" else 1,
            )

        markush_tokenizer = model_parts[4]
        cxsmiles_tokenizer = model_parts[5]
        generated_ids = generated[0][1:-1]
        decoded_text = markush_tokenizer.decode_plus_decode_other_tokens(generated_ids)
        match = re.search(r"<cxsmi>(.*?)</cxsmi>", decoded_text, re.DOTALL)
        if match is None:
            raise ValueError("decoder output omitted the required <cxsmi> block")
        optimized = re.sub(r"\s+|</s>", "", match.group(1))
        expanded = cxsmiles_tokenizer.convert_opt_to_out(optimized)
        if not expanded:
            raise ValueError("CXSMILES expansion failed")
        smiles = expanded

    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "confidence_available": False,
            "valid": False,
            "error": safe_worker_error("Inference", exc),
            "tool": "markushgrapher",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    valid, is_markush, markush_validation = _validate_decoded_structure(smiles)

    latency = int((time.monotonic() - t0) * 1000)

    return {
        "smiles": smiles,
        "cxsmiles": smiles if is_markush else "",
        "confidence": 0.0,
        "confidence_available": False,
        "valid": valid,
        "latency_ms": latency,
        "tool": "markushgrapher",
        "error": "",
        "is_markush": is_markush,
        "markush_validation": markush_validation,
        "ocr_words": len(words),
        "ocr_time_ms": int(ocr_time * 1000),
    }


def _run_persistent() -> None:
    """Run the JSON-lines worker protocol used by drawing tool runners."""
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            image_path = payload.get("image_path") or payload.get("path") or ""
            result = predict(image_path)
        except Exception as exc:
            result = {
                "smiles": "",
                "confidence": 0.0,
                "confidence_available": False,
                "valid": False,
                "error": safe_worker_error("MarkushGrapher request", exc),
                "tool": "markushgrapher",
                "latency_ms": 0,
            }
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(
            json.dumps(
                {
                    "error": "Usage: markushgrapher_worker.py predict <image_path> | predict --persistent"
                }
            )
        )
        sys.exit(1)
    if sys.argv[2] == "--persistent":
        _run_persistent()
        sys.exit(0)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
