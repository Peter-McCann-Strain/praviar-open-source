#!/usr/bin/env python
"""Super-resolution worker — runs in venvs/superres/ Python.

Protocol:
    python superres_worker.py upscale <image_path> <output_path> [scale]
    → JSON to stdout: {"output_path": "...", "scale": 2, "latency_ms": 123}

Uses Real-ESRGAN for 2x or 4x upscaling of degraded patent drawings.
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

try:
    from .model_policy import verified_model_path as _package_verified_model_path
except ImportError:  # pragma: no cover - script mode in isolated worker venvs
    from model_policy import verified_model_path as _script_verified_model_path

    _verified_model_path = _script_verified_model_path
else:
    _verified_model_path = _package_verified_model_path


def _patch_basicsr():
    """Patch basicsr's removed torchvision import (functional_tensor → functional)."""
    import sys
    import types

    try:
        import torchvision.transforms.functional as functional

        m = types.ModuleType("torchvision.transforms.functional_tensor")
        m.__dict__["rgb_to_grayscale"] = functional.__dict__["rgb_to_grayscale"]
        sys.modules["torchvision.transforms.functional_tensor"] = m
    except Exception:
        pass


def upscale(image_path: str, output_path: str, scale: int = 2) -> dict:
    """Upscale an image using Real-ESRGAN."""
    t0 = time.monotonic()

    if scale not in {2, 4}:
        return {
            "output_path": "",
            "scale": scale,
            "error": "super-resolution scale must be 2 or 4",
        }
    model_id = "real-esrgan/x4plus" if scale == 4 else "real-esrgan/x2plus"
    try:
        model_path = _verified_model_path(model_id)
    except RuntimeError as exc:
        return {
            "output_path": "",
            "scale": scale,
            "error": safe_worker_error("Super-resolution model policy", exc),
        }

    _patch_basicsr()
    try:
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
    except ImportError:
        return {
            "output_path": "",
            "scale": scale,
            "error": "realesrgan/basicsr not installed in this venv",
        }

    try:
        import numpy as np
        import torch
        from PIL import Image

        # Select model based on scale
        if scale == 4:
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
            )
        else:
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2
            )

        # Determine device
        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"

        upsampler = RealESRGANer(
            scale=scale,
            model_path=str(model_path),
            model=model,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=device == "cuda",
            device=device,
        )

        # Load and process
        img = np.array(Image.open(image_path).convert("RGB"))
        output, _ = upsampler.enhance(img, outscale=scale)

        # Save
        Image.fromarray(output).save(output_path)

    except Exception as exc:
        return {
            "output_path": "",
            "scale": scale,
            "error": safe_worker_error("Super-resolution", exc),
        }

    return {
        "output_path": output_path,
        "scale": scale,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "error": "",
    }


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "upscale":
        print(json.dumps({"error": "Usage: superres_worker.py upscale <input> <output> [scale]"}))
        sys.exit(1)
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    result = upscale(sys.argv[2], sys.argv[3], scale)
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
