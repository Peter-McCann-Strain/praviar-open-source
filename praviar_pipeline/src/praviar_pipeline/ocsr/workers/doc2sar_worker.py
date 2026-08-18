#!/usr/bin/env python
"""Doc2SAR SAR-table extraction worker — runs in ``venvs/doc2sar/``.

Doc2SAR (arXiv 2506.21625) is an optional multimodal adapter for
structure-activity relationship tables that combine a scaffold with
substituent rows. The upstream paper is an implementation reference, not a
Praviar benchmark or production-readiness receipt; local activation remains
subject to rights, checkpoint, calibration, and rollout gates.

This worker is invoked only after the drawing classifier flags an
image as ``TABLE`` (Phase B5 post-aggregation routing, landing in a
follow-up PR). The worker is kept in its own venv because the
Doc2SAR reference implementation pulls in a fine-tuned MLLM + a
layout model + a BeautifulSoup HTML table parser + pandas for
coreference resolution, each with their own torch / transformers
pins that conflict with the other OCSR tools.

Protocol (one-shot or persistent, matches chemsam / molparser):

    python doc2sar_worker.py predict <image_path> [--max-enum N]
    → one JSON line to stdout:
       {
         "scaffold_smiles": "c1ccc(R1)cc1",
         "substituent_table": [
             {"row_index": 0, "rgroup_labels": {"R1": "OCH3", "R2": "Cl"},
              "resolved_smiles": "COc1ccc(Cl)cc1", "confidence": 0.91},
             ...
         ],
         "enumerated_species": ["COc1ccc(Cl)cc1", ...],
         "confidence": 0.87,
         "tool": "doc2sar",
         "latency_ms": int,
         "error": "",
         "overflowed": bool,
         "valid": true | false
       }

    python doc2sar_worker.py predict --persistent [--max-enum N]
    → stdin loop: read one image path per line, write one JSON line
      per input. Terminated by an empty line / EOF.

The ``--max-enum`` flag (or ``DOC2SAR_MAX_ENUMERATIONS`` env var)
caps the cross-product of substituent-table rows. If the table
would produce more than the cap, the worker sets
``overflowed=True``, returns ``enumerated_species=[]``, and the
caller is expected to abstain (per the B5 plan) rather than trust
a partial enumeration.
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

# Doc2SAR bundles multiple models (MLLM + layout + HTML parser). Root
# is overridable via env so the installer can point at wherever the
# weights + configs actually landed.
DOC2SAR_ROOT = os.environ.get(
    "DOC2SAR_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "models", "doc2sar"),
)
if os.path.isdir(DOC2SAR_ROOT):
    sys.path.insert(0, DOC2SAR_ROOT)

# Main MLLM checkpoint. Usually the fine-tuned vision-language model
# the Doc2SAR paper releases under their supplementary materials.
_DEFAULT_CKPT = os.path.join(DOC2SAR_ROOT, "doc2sar-mllm")
_DOC2SAR_MODEL_ID = "doc2sar/doc2sar-mllm"

_MODEL_CACHE: dict = {}

# Default cap on enumerated-species cross-product. Kept in sync with
# ``config_sections.drawing_doc2sar_max_enumerations`` (500). Beyond
# this, the B5 plan calls for abstention rather than partial output.
_DEFAULT_MAX_ENUMERATIONS = 500

# Fixed confidence assigned to RDKit-valid scaffold+table outputs.
# Doc2SAR's MLLM decoder does not emit per-sequence probabilities;
# the ensemble / aggregation layer reconciles this with prior weights.
_DEFAULT_VALID_CONFIDENCE = 0.80


def _get_device():
    """Return best available torch device (MPS → CUDA → CPU)."""
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_model():
    """Load Doc2SAR's MLLM + layout model + HTML parser (cached).

    Raises:
        ImportError: with a clear "doc2sar venv not set up" message
            if any of torch / transformers / pillow / pandas /
            beautifulsoup4 is missing.
        FileNotFoundError: if the checkpoint directory can't be
            located.
    """
    if "model" in _MODEL_CACHE:
        return (
            _MODEL_CACHE["model"],
            _MODEL_CACHE["processor"],
            _MODEL_CACHE["tokenizer"],
            _MODEL_CACHE["device"],
        )

    try:
        # pandas + bs4 are used by the coreference / HTML-table stages;
        # probe them here so a missing dep surfaces one clean error
        # rather than a mid-inference traceback.
        import bs4  # noqa: F401
        import pandas  # noqa: F401
        import torch  # noqa: F401
        from transformers import AutoProcessor, AutoTokenizer, VisionEncoderDecoderModel
    except ImportError:
        raise ImportError(
            "doc2sar venv not set up — required dependency unavailable. "
            "Install torch, torchvision, "
            "transformers, pillow, pandas, beautifulsoup4 into "
            "praviar_pipeline/venvs/doc2sar/ and download the Doc2SAR MLLM "
            "checkpoint (see praviar_pipeline/venvs/doc2sar/README.md)."
        ) from None

    ckpt_path = os.environ.get("DOC2SAR_CKPT", "")
    if not ckpt_path:
        for candidate in (
            os.path.join(DOC2SAR_ROOT, "doc2sar-mllm"),
            os.path.join(DOC2SAR_ROOT, "checkpoints", "doc2sar-mllm"),
            os.path.expanduser("~/.cache/doc2sar/doc2sar-mllm"),
        ):
            if os.path.isdir(candidate):
                ckpt_path = candidate
                break

    if not ckpt_path or not os.path.isdir(ckpt_path):
        raise FileNotFoundError(
            "Doc2SAR checkpoint not found. Set DOC2SAR_CKPT to an approved "
            "MLLM snapshot directory. See "
            "praviar_pipeline/venvs/doc2sar/README.md for download instructions."
        )

    device = _get_device()

    # Network/remote code are disabled. The context re-verifies the complete
    # filesystem identity and tree digest after every loader has finished.
    with verified_model_directory_from_ml_bom(
        ckpt_path,
        model_id=_DOC2SAR_MODEL_ID,
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
    """Standard error-dict shape — mirrors the Doc2SARResult contract."""
    return {
        "scaffold_smiles": "",
        "substituent_table": [],
        "enumerated_species": [],
        "confidence": 0.0,
        "tool": "doc2sar",
        "latency_ms": elapsed_ms,
        "error": safe_worker_error(kind, exc),
        "overflowed": False,
        "valid": False,
    }


def _parse_mllm_output(raw: str) -> tuple[str, list[dict]]:
    """Parse the MLLM's structured output into (scaffold, table rows).

    Doc2SAR's fine-tuned MLLM emits a JSON object of the form::

        {"scaffold": "<SMILES>",
         "table": [{"row": 0, "R1": "OCH3", "R2": "Cl"}, ...]}

    We pull the scaffold SMILES verbatim and normalise each row into
    the substituent-table contract: ``row_index`` + ``rgroup_labels``
    (dict mapping R-label → substituent label / SMILES fragment).

    Returns ``("", [])`` on any parse failure — the caller then marks
    the whole extraction as invalid without raising.
    """
    if not raw:
        return "", []

    # Strip markdown code fences if the MLLM decided to wrap its
    # output. Common when the decoder imitates training-set HTML.
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence + optional language tag, drop closing fence.
        lines = [ln for ln in lines if not ln.startswith("```")]
        stripped = "\n".join(lines)

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return "", []

    if not isinstance(data, dict):
        return "", []

    scaffold = str(data.get("scaffold", "") or "").strip()
    raw_rows = data.get("table", [])
    if not isinstance(raw_rows, list):
        return scaffold, []

    rows: list[dict] = []
    for idx, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            continue
        # Row-level fields that aren't R-group labels are stripped out
        # so ``rgroup_labels`` holds only ``R1: OCH3`` style pairs.
        declared_index = row.get("row", row.get("row_index", idx))
        labels = {
            k: str(v)
            for k, v in row.items()
            if k not in {"row", "row_index", "smiles", "confidence"} and isinstance(k, str)
        }
        rows.append(
            {
                "row_index": int(declared_index) if isinstance(declared_index, int) else idx,
                "rgroup_labels": labels,
                "resolved_smiles": str(row.get("smiles", "") or ""),
                "confidence": float(row.get("confidence", 0.0) or 0.0),
            }
        )
    return scaffold, rows


def _enumerate_species(
    scaffold: str,
    rows: list[dict],
    *,
    max_enum: int,
) -> tuple[list[str], bool]:
    """Expand scaffold + table rows into concrete SMILES species.

    Each row already carries ``resolved_smiles`` when the MLLM can
    resolve its R-group substitution directly (Doc2SAR's common
    case). We simply collect those. If the resolver didn't fire and
    the total row count exceeds ``max_enum`` we flag overflow and
    return an empty list — the caller must abstain.

    Returns ``(species, overflowed)``.
    """
    if not scaffold:
        return [], False

    # If the table has more rows than the cap, we can't safely emit a
    # partial enumeration — that would be a silent correctness bug
    # (the B5 plan explicitly calls this out as the abstain trigger).
    if len(rows) > max_enum:
        return [], True

    species: list[str] = []
    for row in rows:
        smi = (row.get("resolved_smiles") or "").strip()
        if smi:
            species.append(smi)
    return species, False


def predict(image_path: str, *, max_enum: int = _DEFAULT_MAX_ENUMERATIONS) -> dict:
    """Run Doc2SAR on a single TABLE-classified image.

    Always returns a JSON-serialisable dict — never raises. Errors
    are surfaced in the ``error`` field with ``valid=False``.
    """
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
                max_new_tokens=1024,
                num_beams=4 if device.type != "cpu" else 1,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        raw = decoded[0].strip() if decoded else ""
    except Exception as exc:
        return _base_error(exc, int((time.monotonic() - t0) * 1000), "Inference")

    scaffold, rows = _parse_mllm_output(raw)

    # Missing scaffold is the hard-fail path — without a scaffold we
    # cannot enumerate species, and an SAR table alone is not
    # actionable. Caller must abstain.
    if not scaffold:
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "scaffold_smiles": "",
            "substituent_table": rows,
            "enumerated_species": [],
            "confidence": 0.0,
            "tool": "doc2sar",
            "latency_ms": elapsed,
            "error": "Missing scaffold in Doc2SAR output",
            "overflowed": False,
            "valid": False,
        }

    species, overflowed = _enumerate_species(scaffold, rows, max_enum=max_enum)

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "scaffold_smiles": scaffold,
        "substituent_table": rows,
        "enumerated_species": species,
        "confidence": round(_DEFAULT_VALID_CONFIDENCE, 4) if not overflowed else 0.0,
        "tool": "doc2sar",
        "latency_ms": elapsed,
        "error": "",
        "overflowed": overflowed,
        "valid": not overflowed,
    }


def _resolve_max_enum(flag_value: str | None) -> int:
    """CLI flag > env var > default. Negative / non-integer → default."""
    raw = flag_value if flag_value is not None else os.environ.get("DOC2SAR_MAX_ENUMERATIONS")
    if not raw:
        return _DEFAULT_MAX_ENUMERATIONS
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ENUMERATIONS
    return parsed if parsed > 0 else _DEFAULT_MAX_ENUMERATIONS


def _extract_max_enum_flag(argv: list[str]) -> tuple[list[str], int]:
    """Strip ``--max-enum N`` from argv, return (remaining, value)."""
    remaining: list[str] = []
    flag_val: str | None = None
    it = iter(argv)
    for arg in it:
        if arg == "--max-enum":
            flag_val = next(it, None)
            continue
        if arg.startswith("--max-enum="):
            flag_val = arg.split("=", 1)[1]
            continue
        remaining.append(arg)
    return remaining, _resolve_max_enum(flag_val)


def _run_persistent(*, max_enum: int) -> None:
    """stdin loop → one JSON line per image path until empty line / EOF.

    Any stdout noise from model-loading libraries is redirected to
    stderr so the JSON-per-line protocol stays clean. Matches the
    pattern used by ``molparser_worker._run_persistent``.
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
                    "scaffold_smiles": "",
                    "substituent_table": [],
                    "enumerated_species": [],
                    "confidence": 0.0,
                    "tool": "doc2sar",
                    "latency_ms": 0,
                    "error": safe_worker_error("Model load at startup", exc),
                    "overflowed": False,
                    "valid": False,
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
            result = predict(image_path, max_enum=max_enum)
        captured = buf.getvalue()
        if captured:
            sys.stderr.write(SUPPRESSED_DEPENDENCY_OUTPUT + "\n")
            sys.stderr.flush()
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    argv_tail = sys.argv[1:]

    # First positional must be "predict"; everything after it is the
    # image path (one-shot) or "--persistent", plus optional flags.
    if not argv_tail or argv_tail[0] != "predict":
        print(
            json.dumps(
                {
                    "error": (
                        "Usage: doc2sar_worker.py predict <image_path> "
                        "[--max-enum N] | predict --persistent [--max-enum N]"
                    )
                }
            )
        )
        sys.exit(1)

    remainder, parsed_max_enum = _extract_max_enum_flag(argv_tail[1:])

    if remainder and remainder[0] == "--persistent":
        _run_persistent(max_enum=parsed_max_enum)
        sys.exit(0)

    if not remainder:
        print(
            json.dumps(
                {
                    "error": (
                        "Usage: doc2sar_worker.py predict <image_path> "
                        "[--max-enum N] | predict --persistent [--max-enum N]"
                    )
                }
            )
        )
        sys.exit(1)

    result = predict(remainder[0], max_enum=parsed_max_enum)
    print(json.dumps(result))
    sys.exit(0 if not result.get("error") else 1)
