"""Shared path and cache constants for the drawing pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.models.drawing import OCSRResult

# Drawing tool assembly for the Step 2.75 drawing-analysis path.
# Walking up 5 parents lands at praviar_pipeline/, where venvs/, src/, and models/ live.
_PRAVIAR_PIPELINE_ROOT = Path(__file__).resolve().parents[4]
VENVS_DIR = _PRAVIAR_PIPELINE_ROOT / "venvs"
# WORKERS_DIR walks up 3 to reach praviar_pipeline/src/praviar_pipeline, then into ocsr/workers
WORKERS_DIR = Path(__file__).resolve().parents[2] / "ocsr" / "workers"
MODELS_DIR = _PRAVIAR_PIPELINE_ROOT / "models"

TOOL_CONFIGS = {
    "molscribe": {
        "venv": VENVS_DIR / "molscribe",
        "worker": WORKERS_DIR / "molscribe_worker.py",
        "env": {
            "MOLSCRIBE_ROOT": str(MODELS_DIR / "molscribe"),
            "MOLSCRIBE_CKPT": str(
                MODELS_DIR / "molscribe" / "ckpts" / "swin_base_char_aux_1m680k.pth"
            ),
        },
    },
    "molsight": {
        "venv": VENVS_DIR / "molsight",
        "worker": WORKERS_DIR / "molsight_worker.py",
        "env": {
            "MOLSIGHT_ROOT": str(MODELS_DIR / "molsight"),
            "MOLSIGHT_CKPT": str(
                MODELS_DIR / "molsight" / "ckpts" / "pubchem_uspto_smiles_edges_30.pth"
            ),
        },
    },
    "decimer": {
        "venv": VENVS_DIR / "decimer",
        "worker": WORKERS_DIR / "decimer_ocsr_worker.py",
        "env": {},
    },
    "molnextr": {
        "venv": VENVS_DIR / "molnextr",
        "worker": WORKERS_DIR / "molnextr_worker.py",
        "env": {},
    },
    "molgrapher": {
        "venv": VENVS_DIR / "molgrapher",
        "worker": WORKERS_DIR / "molgrapher_worker.py",
        "env": {},
    },
    "molparser": {
        "venv": VENVS_DIR / "molparser",
        "worker": WORKERS_DIR / "molparser_worker.py",
        "env": {
            "MOLPARSER_ROOT": str(MODELS_DIR / "molparser"),
            "MOLPARSER_CKPT": str(MODELS_DIR / "molparser" / "molparser-base"),
        },
    },
    # Markush specialist parallel path.
    # The classifier_v2 routing in structure_analysis.py:77-99 dispatches
    # MARKUSH-classified crops here, bypassing the 5-tool molecule ensemble.
    # MarkushGrapher is a specialist path, not a regular-molecule ensemble
    # voter. This separation is an architecture boundary, not a performance
    # assertion.
    "markushgrapher": {
        "venv": VENVS_DIR / "markushgrapher",
        "worker": WORKERS_DIR / "markushgrapher_worker.py",
        "env": {},
    },
    "doc2sar": {
        "venv": VENVS_DIR / "doc2sar",
        "worker": WORKERS_DIR / "doc2sar_worker.py",
        "env": {
            "DOC2SAR_ROOT": str(MODELS_DIR / "doc2sar"),
            "DOC2SAR_CKPT": str(MODELS_DIR / "doc2sar" / "checkpoints" / "doc2sar.pt"),
        },
    },
}

SEGMENTATION_BACKENDS: dict[str, dict[str, Path]] = {
    "decimer": {
        "venv": VENVS_DIR / "decimer",
        "worker": WORKERS_DIR / "decimer_seg_worker.py",
    },
    "moldet": {
        "venv": VENVS_DIR / "moldet",
        "worker": WORKERS_DIR / "moldet_seg_worker.py",
    },
    "chemsam": {
        "venv": VENVS_DIR / "chemsam",
        "worker": WORKERS_DIR / "chemsam_seg_worker.py",
    },
}

DRAWING_RESULT_CACHE: dict[str, OCSRResult] = {}
