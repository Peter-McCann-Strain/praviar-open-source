"""Runtime checks for drawing-model supply-chain gates."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from praviar_pipeline.config_paths import REPO_ROOT
from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Iterable

APPROVED_MODEL_LICENSE_STATUS = "approved_for_commercial_use"
DEFAULT_ML_BOM_PATH = "docs/trust/evidence/supply-chain/ml-bom-local-2026-05-25.json"
REQUIRED_DRAWING_MODEL_IDS = frozenset(
    {
        "decimer-segmentation/mask_rcnn_molecule",
        "molscribe/swin_base_char_aux_1m680k",
        "molsight/pubchem_uspto_smiles_edges_30",
        "molclassifier/local",
        "markushgrapher/markushgrapher-2/pytorch_model",
        "markushgrapher/chemicalocr/model",
    }
)
# MolDet uses CC-BY-NC-SA-4.0 (non-commercial only). It is NOT required for the
# default DECIMER segmentation path and must not gate commercial production releases.
# Only add it to the required set when drawing_segmentation_tool="moldet" is
# explicitly configured — see config_sections.py _validate_drawing_thresholds.
MOLDET_MODEL_IDS = frozenset({"moldet/yolo11l_960_doc"})
REQUIRED_DOC2SAR_MODEL_IDS = frozenset({"doc2sar/doc2sar-mllm"})
REQUIRED_RELEASE_READY_FIELDS = {
    "model_id",
    "path",
    "sha256",
    "license_evidence_path",
    "license_status",
    "release_blocker",
}
LICENSE_EVIDENCE_ROOT = Path("docs/trust/evidence/supply-chain/licenses")
APPROVED_LICENSE_EVIDENCE_NEEDLES = (
    "approved_for_commercial_use",
    "primary_source_url",
    "source_kind",
    "retrieved_at",
    "retrieved_sha256",
    "approved_use",
    "review_authority",
)
APPROVED_LICENSE_FORBIDDEN_NEEDLES = (
    "todo",
    "placeholder",
    "pending",
    "local-only",
    "not release evidence",
)


def _resolve_manifest_path(manifest_path: str | Path) -> Path:
    path = Path(manifest_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _entry_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    root = REPO_ROOT if manifest_path.is_relative_to(REPO_ROOT) else manifest_path.parent
    return root / path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _license_evidence_blocker(
    manifest_path: Path,
    entry: dict,
    *,
    model_id: str,
) -> str | None:
    value = str(entry.get("license_evidence_path") or "").strip()
    if not value:
        return "missing license_evidence_path"

    relative_path = Path(value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return "license evidence path must be repo-relative"
    if not relative_path.is_relative_to(LICENSE_EVIDENCE_ROOT):
        return f"license evidence path must be under {LICENSE_EVIDENCE_ROOT}"
    if relative_path.suffix.lower() != ".md":
        return "license evidence path must point to Markdown evidence"

    evidence_path = _entry_path(manifest_path, value)
    if not evidence_path.is_file():
        return "missing license evidence file"

    try:
        evidence_text = evidence_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read license evidence file ({safe_exception_type(exc)})"

    normalized = re.sub(r"\s+", " ", evidence_text.casefold())
    filename_safe_model_id = model_id.replace("/", "_").casefold()
    if model_id.casefold() not in normalized and filename_safe_model_id not in normalized:
        return "license evidence must mention the model_id"

    for needle in APPROVED_LICENSE_EVIDENCE_NEEDLES:
        if needle not in normalized:
            return f"approved license evidence must include {needle!r}"
    for needle in APPROVED_LICENSE_FORBIDDEN_NEEDLES:
        if needle in normalized:
            return f"approved license evidence must not contain {needle!r}"

    return None


def require_resolved_drawing_model_supply_chain(
    manifest_path: str | Path,
    *,
    extra_required_model_ids: Iterable[str] = (),
    segmentation_tool: str = "decimer",
) -> None:
    """Fail closed unless every drawing-model ML-BOM entry is release-ready.

    MolDet (CC-BY-NC-SA-4.0, non-commercial) is excluded from the required set
    unless segmentation_tool="moldet" is explicitly configured, in which case an
    immediate ConfigurationError is raised because MolDet cannot be used commercially.
    """
    if segmentation_tool == "moldet":
        raise ConfigurationError(
            "drawing_segmentation_tool='moldet' cannot be used in beta/production mode: "
            "MolDet weights are licensed CC-BY-NC-SA-4.0 (non-commercial only). "
            "Use drawing_segmentation_tool='decimer' or 'chemsam' for production deployments."
        )
    required_model_ids = REQUIRED_DRAWING_MODEL_IDS | frozenset(extra_required_model_ids)
    path = _resolve_manifest_path(manifest_path)
    load_error_type: str | None = None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        load_error_type = safe_exception_type(exc)
    if load_error_type is not None:
        raise ConfigurationError(
            f"Cannot read drawing ML-BOM manifest ({load_error_type})"
        ) from None

    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ConfigurationError("Drawing ML-BOM manifest must contain entries")

    entries_by_model_id: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("model_id") or f"entry-{index}")
        entries_by_model_id[model_id] = entry

    missing_model_ids = sorted(required_model_ids - set(entries_by_model_id))
    if missing_model_ids:
        preview = ", ".join(missing_model_ids[:5])
        suffix = "" if len(missing_model_ids) <= 5 else f", and {len(missing_model_ids) - 5} more"
        raise ConfigurationError(
            "drawing_analysis_evidence_gate_passed cannot enable beta/production "
            f"while the ML-BOM is missing required drawing model entries: {preview}{suffix}"
        )

    blockers: list[str] = []
    for model_id in sorted(required_model_ids):
        entry = entries_by_model_id[model_id]
        missing_fields = sorted(REQUIRED_RELEASE_READY_FIELDS - set(entry))
        if missing_fields:
            blockers.append(f"{model_id} (missing {', '.join(missing_fields)})")
            continue
        model_path_value = str(entry.get("path") or "").strip()
        if not model_path_value:
            blockers.append(f"{model_id} (missing path)")
            continue
        expected_sha = str(entry.get("sha256") or "").strip()
        if not expected_sha:
            blockers.append(f"{model_id} (missing sha256)")
            continue
        model_path = _entry_path(path, model_path_value)
        if not model_path.is_file():
            blockers.append(f"{model_id} (missing model file)")
            continue
        actual_sha = _sha256_file(model_path)
        if actual_sha != expected_sha:
            blockers.append(f"{model_id} (sha256 mismatch)")
            continue
        license_status = str(entry.get("license_status") or "")
        release_blocker = entry.get("release_blocker")
        if release_blocker is not False or license_status != APPROVED_MODEL_LICENSE_STATUS:
            blockers.append(f"{model_id} ({license_status or 'missing_license_status'})")
            continue
        license_evidence_blocker = _license_evidence_blocker(path, entry, model_id=model_id)
        if license_evidence_blocker:
            blockers.append(f"{model_id} ({license_evidence_blocker})")

    if blockers:
        preview = ", ".join(blockers[:5])
        suffix = "" if len(blockers) <= 5 else f", and {len(blockers) - 5} more"
        raise ConfigurationError(
            "drawing_analysis_evidence_gate_passed cannot enable beta/production "
            "while the ML-BOM has unresolved model evidence or checksum blockers: "
            f"{preview}{suffix}"
        )
