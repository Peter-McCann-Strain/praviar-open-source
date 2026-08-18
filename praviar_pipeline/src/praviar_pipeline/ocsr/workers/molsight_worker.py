#!/usr/bin/env python
"""MolSight OCSR worker — EfficientViT + RL-trained SMILES decoder.

Runs in the optional MolSight environment. Upstream architecture and licence
labels are recorded in ``MODEL_LICENSES.md``; they are not Praviar benchmark,
checkpoint-rights, or production-readiness evidence. The model remains
activation-blocked unless the runtime's independent supply-chain and
calibration gates pass.

Protocol:
    python molsight_worker.py predict <image_path>
    → JSON to stdout: {"smiles": "...", "confidence": 0.87, "valid": true}

    python molsight_worker.py predict_beam <image_path> [beam_size]
    → JSON with beam candidates

Requires: MolSight cloned to MOLSIGHT_ROOT, checkpoint in MOLSIGHT_CKPT.
"""

from __future__ import annotations

import argparse
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

MOLSIGHT_ROOT = os.environ.get(
    "MOLSIGHT_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "models", "molsight"),
)
if os.path.isdir(MOLSIGHT_ROOT):
    sys.path.insert(0, MOLSIGHT_ROOT)

MOLSIGHT_CKPT = os.environ.get(
    "MOLSIGHT_CKPT",
    os.path.join(MOLSIGHT_ROOT, "ckpts", "pubchem_uspto_smiles_edges_30.pth"),  # MolSight-extra
)
MOLSIGHT_MODEL_ID = "molsight/pubchem_uspto_smiles_edges_30"

# Whether to use LoRA (for stereo variant only)
MOLSIGHT_LORA = os.environ.get("MOLSIGHT_LORA", "0") == "1"
MOLSIGHT_FORMATS = os.environ.get("MOLSIGHT_FORMATS", "char,edges")

_MODEL_CACHE: dict = {}


def _build_args(formats: str = "char,edges", lora: bool = False) -> argparse.Namespace:
    """Build minimal args namespace for MolsightModel."""
    vocab_path = os.path.join(MOLSIGHT_ROOT, "vocab", "vocab_chars.json")
    return argparse.Namespace(
        encoder="efficientvit",
        use_checkpoint=False,
        embed_dim=512,
        dec_n_layer=6,
        dec_n_head=8,
        use_qknorm=True,
        use_swiglu=True,
        use_rmsnorm=True,
        lora=lora,
        regression=False,
        input_size=512,
        formats=formats.split(","),
        vocab_file=vocab_path,
        resume=True,
        max_len=320,
        beam_size=1,
        n_samples=1,
        save_attns=False,
        molblock=False,
        compute_confidence=False,
        keep_main_molecule=False,
    )


def get_model(device=None):
    """Get or create cached MolSight model."""
    import torch

    if device is None:
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

    if "model" not in _MODEL_CACHE:
        from molsight.model import MolsightModel
        from molsight.tokenizer import CharTokenizer

        args = _build_args(formats=MOLSIGHT_FORMATS, lora=MOLSIGHT_LORA)
        tokenizer = CharTokenizer(args.vocab_file)
        model = MolsightModel(args, tokenizer)
        model.to(device)

        verify_model_checksum_from_ml_bom(
            MOLSIGHT_CKPT,
            model_id=MOLSIGHT_MODEL_ID,
        )
        # Checkpoint loading is restricted to tensors and primitive metadata.
        checkpoint = torch.load(  # nosemgrep
            MOLSIGHT_CKPT,
            map_location="cpu",
            weights_only=True,
        )
        state_dict = checkpoint.get("model", checkpoint)
        # Strip DDP 'module.' prefix
        state_dict = {(k[7:] if k.startswith("module.") else k): v for k, v in state_dict.items()}
        model.load_state_dict(state_dict, strict=False)
        model.eval()

        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["args"] = args
        _MODEL_CACHE["device"] = device

    return _MODEL_CACHE["model"], _MODEL_CACHE["args"], _MODEL_CACHE["device"]


def predict(image_path: str) -> dict:
    """Run MolSight inference on a single image."""
    t0 = time.monotonic()

    try:
        model, args, device = get_model()
    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Model load", exc),
            "tool": "molsight",
            "latency_ms": 0,
        }

    try:
        import cv2
        import torch
        from molsight.dataset import get_transforms

        # Load and preprocess image
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        transform = get_transforms(args, augment=False, rotate=False)
        augmented = transform(image=image)
        image_tensor = augmented["image"].unsqueeze(0).to(device)

        with torch.no_grad():
            kv_cache, hooks = model.install_kv_cache_hooks()
            batch_preds, _inter = model.generate(image=image_tensor, kv_cache=kv_cache)
            for hook in hooks:
                hook.remove()

        raw_smiles = batch_preds["smiles"][0]
        avg_logprob = float(batch_preds.get("avg_logprob", [0.0])[0])

        # Post-process
        try:
            from molsight.chemistry import _postprocess_smiles

            processed, _, _success = _postprocess_smiles(raw_smiles)
        except Exception:
            processed = raw_smiles

        smiles = processed

    except Exception as exc:
        return {
            "smiles": "",
            "confidence": 0.0,
            "valid": False,
            "error": safe_worker_error("Inference", exc),
            "tool": "molsight",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # Validate and canonicalise
    valid = False
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            valid = True
            smiles = Chem.MolToSmiles(mol)
    except Exception:
        pass

    # Convert avg_logprob to 0-1 confidence (sigmoid-like mapping)
    # avg_logprob is negative; closer to 0 = more confident
    import math

    confidence = 1.0 / (1.0 + math.exp(-avg_logprob - 1.0))  # sigmoid shifted

    return {
        "smiles": smiles,
        "confidence": round(confidence, 4),
        "valid": valid,
        "avg_logprob": round(avg_logprob, 4),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "tool": "molsight",
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "predict":
        print(json.dumps({"error": "Usage: molsight_worker.py predict <image_path>"}))
        sys.exit(1)
    result = predict(sys.argv[2])
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
