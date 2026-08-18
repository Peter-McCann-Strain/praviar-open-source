"""Governed drawing-classifier adapter for PatCID's MolClassifier (Mask R-CNN).

Drop-in replacement for the heuristic ``praviar_pipeline.ocsr.classifier`` module.
Preserves the ``ImageCategory``/``ClassificationResult`` API so callers
(``praviar_pipeline.pipeline.step2d_drawings``) need only swap the import.

This module orchestrates a subprocess call to ``molclassifier_worker.py``
running in ``praviar_pipeline/venvs/molclassifier``. The worker outputs a single
JSON line with ``category`` (one of molecule/markush/no_detections/non_chemical),
``confidence``, ``raw_label``, and ``latency_ms``.

The first call pays model-load cost. Repeated calls within
the same Python process can use ``classify_persistent_session`` to keep one
worker process warm and pipe images via stdin.

Governed routing:
  * Worker box_score_thresh comes from an immutable, task-local run config
    derived from Settings (no hardcoded 0.8 and no process-global mutation).
  * Worker emits ``category="no_detections"`` when nothing exceeds the box
    threshold; this wrapper conservatively maps it to MOLECULE so absence of a
    detection cannot silently discard a potentially relevant crop.
  * Low-confidence ``non_chemical`` predictions are reclassified to MOLECULE
    when ``confidence < drawing_classifier_non_chemical_min_conf`` (default 0.95)
    so only task-locally configured high-confidence negatives may discard a crop.

NO fallback to the heuristic — if the worker errors, we raise. This matches
the project's "NO fallbacks — errors must propagate" rule.
"""

from __future__ import annotations

import contextlib
import enum
import hashlib
import json
import math
import os
import subprocess
import tempfile
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, NamedTuple

import structlog

from praviar_pipeline.ocsr.runner import _safe_worker_env

if TYPE_CHECKING:
    from PIL import Image

logger = structlog.get_logger()


class ImageCategory(enum.StrEnum):
    """Classification categories for patent drawing regions."""

    MOLECULE = "molecule"
    MARKUSH = "markush"
    REACTION = "reaction"
    NON_CHEMICAL = "non_chemical"


class ClassificationResult(NamedTuple):
    category: ImageCategory
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class ClassifierRunConfig:
    """Immutable classifier thresholds for one analysis task."""

    box_score_thresh: float
    non_chemical_min_conf: float


_RUN_CONFIG: ContextVar[ClassifierRunConfig | None] = ContextVar(
    "praviar_ocsr_classifier_run_config",
    default=None,
)


def _current_run_config() -> ClassifierRunConfig:
    config = _RUN_CONFIG.get()
    if config is None:
        raise RuntimeError(
            "MolClassifier run configuration is missing. "
            "Call configure_from_settings(settings) at the analysis boundary."
        )
    return config


_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKER_VENV_PY = _REPO_ROOT / "praviar_pipeline" / "venvs" / "molclassifier" / "bin" / "python"
_WORKER_SCRIPT = (
    _REPO_ROOT
    / "praviar_pipeline"
    / "src"
    / "praviar_pipeline"
    / "ocsr"
    / "workers"
    / "molclassifier_worker.py"
)


def resolve_worker_category(
    raw: str,
    confidence: float,
    run_config: ClassifierRunConfig | None = None,
) -> ImageCategory:
    """Map worker raw category to the governed ImageCategory contract.

    Two conservative routing decisions are made here:

    * ``no_detections`` (worker: MaskRCNN found nothing above box threshold) →
      MOLECULE, preventing a missing detector output from becoming evidence
      that the crop is non-chemical.

    * ``non_chemical`` with confidence below the task-local minimum →
      MOLECULE. Only a prediction meeting the task-local minimum is allowed to
      take the NON_CHEMICAL path.
    """
    raw = (raw or "").strip().lower()
    if raw == "molecule":
        return ImageCategory.MOLECULE
    if raw == "markush":
        return ImageCategory.MARKUSH
    if raw == "reaction":
        return ImageCategory.REACTION
    if raw == "no_detections":
        return ImageCategory.MOLECULE
    if raw == "non_chemical":
        config = run_config or _current_run_config()
        if confidence < config.non_chemical_min_conf:
            return ImageCategory.MOLECULE
        return ImageCategory.NON_CHEMICAL
    raise RuntimeError(
        f"Unknown classifier raw category {raw!r}; expected one of "
        "molecule|markush|reaction|non_chemical|no_detections"
    )


def _worker_env(
    run_config: ClassifierRunConfig | None = None,
) -> dict[str, str]:
    """Build the env dict for the worker subprocess.

    Task-local thresholds are forwarded to the isolated worker subprocess;
    the worker is a standalone Python script in a different venv, so it
    cannot import the in-process run contract.
    """
    config = run_config or _current_run_config()
    return _safe_worker_env(
        {
            "MOLCLASSIFIER_BOX_THRESH": f"{config.box_score_thresh:.6f}",
            "MOLCLASSIFIER_NC_MIN_CONF": f"{config.non_chemical_min_conf:.6f}",
            "MOLCLASSIFIER_CKPT": os.environ.get("MOLCLASSIFIER_CKPT", ""),
            "MOLCLASSIFIER_DEVICE": os.environ.get("MOLCLASSIFIER_DEVICE", ""),
        }
    )


def configure_from_settings(settings: object) -> ClassifierRunConfig:
    """Install immutable, task-local classifier thresholds for one analysis."""
    box_thresh = getattr(settings, "drawing_classifier_box_score_thresh", None)
    nc_min_conf = getattr(settings, "drawing_classifier_non_chemical_min_conf", None)
    if box_thresh is None:
        raise RuntimeError(
            "settings.drawing_classifier_box_score_thresh missing — "
            "config_sections.py is out of sync."
        )
    if nc_min_conf is None:
        raise RuntimeError(
            "settings.drawing_classifier_non_chemical_min_conf missing — "
            "config_sections.py is out of sync."
        )
    values = {
        "drawing_classifier_box_score_thresh": float(box_thresh),
        "drawing_classifier_non_chemical_min_conf": float(nc_min_conf),
    }
    for name, value in values.items():
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise RuntimeError(f"settings.{name} must be a finite value in [0, 1].")
    config = ClassifierRunConfig(
        box_score_thresh=values["drawing_classifier_box_score_thresh"],
        non_chemical_min_conf=values["drawing_classifier_non_chemical_min_conf"],
    )
    _RUN_CONFIG.set(config)
    return config


def _save_temp(img: Image.Image) -> Path:
    with tempfile.NamedTemporaryFile(
        prefix="molclf_",
        suffix=".png",
        delete=False,
    ) as fd:
        p = Path(fd.name)
    img.save(p, format="PNG")
    return p


def classify_image(img: Image.Image) -> ClassificationResult:
    """Classify a single drawing crop. Spawns a fresh subprocess.

    For multiple crops, prefer ``classify_persistent_session`` to amortize
    model-initialization overhead across calls.
    """
    if not _WORKER_VENV_PY.exists():
        raise RuntimeError(
            f"MolClassifier venv not found at {_WORKER_VENV_PY}. "
            "Run the molclassifier setup before classifying."
        )

    run_config = _current_run_config()
    tmp = _save_temp(img)
    try:
        proc = subprocess.run(
            [str(_WORKER_VENV_PY), str(_WORKER_SCRIPT), "infer", str(tmp)],
            capture_output=True,
            text=True,
            timeout=120,
            env=_worker_env(run_config),
        )
        if proc.returncode != 0:
            stderr_sha256 = hashlib.sha256(proc.stderr.encode()).hexdigest()
            raise RuntimeError(
                f"MolClassifier worker exited (code={proc.returncode}, "
                f"stderr_sha256={stderr_sha256})"
            )
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                payload = json.loads(line)
                break
        else:
            raise RuntimeError("MolClassifier worker produced no JSON output")
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()

    if payload.get("error"):
        raise RuntimeError("MolClassifier worker reported an error")

    confidence = float(payload.get("confidence", 0.0))
    category = resolve_worker_category(
        payload.get("category", ""),
        confidence,
        run_config,
    )
    raw_label = payload.get("raw_label", "")
    return ClassificationResult(
        category=category,
        confidence=confidence,
        reason=f"MolClassifier raw_label={raw_label} conf={confidence:.3f}",
    )


class _PersistentSession:
    """Long-running MolClassifier worker — pipe paths in, read JSON lines out.

    Use ``with classify_persistent_session() as session: session.classify(img)``
    to amortize model initialization across many crops.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._stdin: IO[str] | None = None
        self._stdout: IO[str] | None = None
        self._run_config: ClassifierRunConfig | None = None

    def __enter__(self) -> _PersistentSession:
        if not _WORKER_VENV_PY.exists():
            raise RuntimeError(f"MolClassifier venv missing at {_WORKER_VENV_PY}")
        self._run_config = _current_run_config()
        self._proc = subprocess.Popen(
            [
                str(_WORKER_VENV_PY),
                str(_WORKER_SCRIPT),
                "infer",
                "--persistent",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=_worker_env(self._run_config),
        )
        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._proc is None:
            return
        try:
            if self._stdin is not None and not self._stdin.closed:
                self._stdin.close()
            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def classify(self, img: Image.Image) -> ClassificationResult:
        if self._proc is None or self._stdin is None or self._stdout is None:
            raise RuntimeError("Persistent classifier session is not active")
        if self._proc.poll() is not None:
            raise RuntimeError(f"Classifier worker died with exit {self._proc.returncode}")
        tmp = _save_temp(img)
        try:
            self._stdin.write(f"{tmp}\n")
            self._stdin.flush()
            line = self._stdout.readline()
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        if not line:
            raise RuntimeError("Classifier worker closed unexpectedly")
        payload = json.loads(line.strip())
        if payload.get("error"):
            raise RuntimeError("MolClassifier worker reported an error")
        confidence = float(payload.get("confidence", 0.0))
        if self._run_config is None:
            raise RuntimeError("Persistent classifier session has no run configuration")
        category = resolve_worker_category(
            payload.get("category", ""),
            confidence,
            self._run_config,
        )
        raw_label = payload.get("raw_label", "")
        return ClassificationResult(
            category=category,
            confidence=confidence,
            reason=f"MolClassifier raw_label={raw_label} conf={confidence:.3f}",
        )


def classify_persistent_session() -> _PersistentSession:
    """Open a persistent classifier session for batched calls."""
    return _PersistentSession()
