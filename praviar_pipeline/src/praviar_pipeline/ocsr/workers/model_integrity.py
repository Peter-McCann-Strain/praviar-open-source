"""Fail-closed checksum verification for local OCSR model weights."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
DEFAULT_ML_BOM_PATH = "docs/trust/evidence/supply-chain/ml-bom-local-2026-05-25.json"
APPROVED_MODEL_LICENSE_STATUS = "approved_for_commercial_use"
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
REQUIRED_APPROVED_LICENSE_FIELDS = {
    "approval_artifact_path",
    "approval_artifact_sha256",
    "approved_model_id",
    "approved_model_sha256",
    "review_authority",
}
APPROVED_LICENSE_FORBIDDEN_NEEDLES = (
    "todo",
    "placeholder",
    "pending",
    "local-only",
    "not release evidence",
)
ALLOWED_LICENSE_REVIEW_AUTHORITIES = {"security_lead", "ml_lead", "release_captain"}
SIMULATED_PATH_PARTS = (
    "docs/trust/human-required/simulated/",
    "docs/trust/research-agent-simulations/",
)
DIRECTORY_TREE_ARTIFACT_KIND = "directory_tree_v1"
DIRECTORY_TREE_SCHEMA = "praviar-model-directory-tree-v1"
_TOKENIZER_FILES = {
    "tokenizer.json",
    "tokenizer.model",
    "spiece.model",
    "vocab.json",
    "vocab.txt",
}
_PROCESSOR_FILES = {
    "preprocessor_config.json",
    "processor_config.json",
}
_WEIGHT_SUFFIXES = {".bin", ".ckpt", ".pt", ".pth", ".safetensors"}
_CRITICAL_SUFFIXES = _WEIGHT_SUFFIXES | {".json", ".model", ".py", ".txt"}


class ModelChecksumError(RuntimeError):
    """Raised when a model weight file does not match its expected digest."""


@dataclass(frozen=True)
class _FilesystemEntryStamp:
    path: str
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


def _resolve_snapshot_root(
    model_directory: str | Path,
    *,
    model_id: str,
) -> Path:
    """Resolve a real directory while rejecting a symlink at the trust root."""
    raw_root = Path(model_directory)
    try:
        raw_stat = raw_root.lstat()
    except OSError:
        raise ModelChecksumError(f"{model_id}: model directory not found") from None
    if stat.S_ISLNK(raw_stat.st_mode):
        raise ModelChecksumError(f"{model_id}: checkpoint snapshot root must not be a symlink")
    if not stat.S_ISDIR(raw_stat.st_mode):
        raise ModelChecksumError(f"{model_id}: model directory not found")
    try:
        resolved_root = raw_root.resolve(strict=True)
        resolved_stat = resolved_root.lstat()
    except OSError:
        raise ModelChecksumError(f"{model_id}: cannot resolve checkpoint snapshot root") from None
    if not stat.S_ISDIR(resolved_stat.st_mode):
        raise ModelChecksumError(f"{model_id}: checkpoint snapshot root is not a directory")
    if (raw_stat.st_dev, raw_stat.st_ino) != (resolved_stat.st_dev, resolved_stat.st_ino):
        raise ModelChecksumError(
            f"{model_id}: checkpoint snapshot root changed while it was resolved"
        )
    return resolved_root


def _filesystem_snapshot_stamp(
    root: Path,
    *,
    model_id: str,
) -> tuple[_FilesystemEntryStamp, ...]:
    """Bind filesystem identity and mutation metadata for the complete tree."""
    entries = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    stamps: list[_FilesystemEntryStamp] = []
    for path in entries:
        try:
            item_stat = path.lstat()
        except OSError:
            raise ModelChecksumError(
                f"{model_id}: checkpoint snapshot changed while it was inspected"
            ) from None
        if stat.S_ISLNK(item_stat.st_mode):
            raise ModelChecksumError(f"{model_id}: checkpoint snapshot contains a symlink")
        if path != root and not (
            stat.S_ISDIR(item_stat.st_mode) or stat.S_ISREG(item_stat.st_mode)
        ):
            raise ModelChecksumError(f"{model_id}: checkpoint snapshot contains a non-regular file")
        relative_path = (
            "."
            if path == root
            else _safe_relative_file(
                path,
                root,
                model_id=model_id,
            )
        )
        stamps.append(
            _FilesystemEntryStamp(
                path=relative_path,
                device=item_stat.st_dev,
                inode=item_stat.st_ino,
                mode=item_stat.st_mode,
                size=item_stat.st_size,
                mtime_ns=item_stat.st_mtime_ns,
                ctime_ns=item_stat.st_ctime_ns,
            )
        )
    return tuple(stamps)


def _normalize_sha256(value: str) -> str:
    digest = value.strip().lower()
    if digest.startswith("sha256:"):
        digest = digest.removeprefix("sha256:")
    if not SHA256_RE.fullmatch(digest):
        raise ModelChecksumError("expected SHA-256 must be a 64-character hex digest")
    return digest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_file(path: Path, root: Path, *, model_id: str) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:  # pragma: no cover - defensive invariant
        raise ModelChecksumError(f"{model_id}: snapshot file escaped checkpoint root") from None
    value = relative.as_posix()
    if not value or value.startswith("/") or ".." in relative.parts or "\x00" in value:
        raise ModelChecksumError(f"{model_id}: invalid checkpoint-relative path")
    return value


def model_directory_tree_sha256(
    model_directory: str | Path,
    *,
    model_id: str,
) -> tuple[str, int, tuple[str, ...]]:
    """Return a deterministic digest over every regular checkpoint file.

    The digest binds each path, byte length, and file SHA-256. Symlinks and
    non-regular filesystem entries are rejected so a verified snapshot cannot
    redirect model loading outside the approved directory after verification.
    """
    root = _resolve_snapshot_root(model_directory, model_id=model_id)

    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ModelChecksumError(f"{model_id}: checkpoint snapshot contains a symlink")
        try:
            mode = path.stat().st_mode
        except OSError:
            raise ModelChecksumError(f"{model_id}: cannot inspect checkpoint snapshot") from None
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ModelChecksumError(f"{model_id}: checkpoint snapshot contains a non-regular file")
        relative = _safe_relative_file(path, root, model_id=model_id)
        records.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    if not records:
        raise ModelChecksumError(f"{model_id}: checkpoint snapshot is empty")
    payload = {
        "schema": DIRECTORY_TREE_SCHEMA,
        "files": records,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    total_size = sum(int(record["size_bytes"]) for record in records)
    return digest, total_size, tuple(str(record["path"]) for record in records)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _resolve_manifest_path(manifest_path: str | Path | None = None) -> Path:
    raw_path = manifest_path or os.environ.get("PRAVIAR_ML_BOM_PATH") or DEFAULT_ML_BOM_PATH
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return _repo_root() / path


def _load_manifest(manifest_path: str | Path | None = None) -> tuple[dict, Path]:
    path = _resolve_manifest_path(manifest_path)
    load_failed = False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        load_failed = True
    if load_failed:
        raise ModelChecksumError("cannot read ML-BOM manifest") from None
    if not isinstance(manifest, dict):
        raise ModelChecksumError("ML-BOM manifest must be a JSON object")
    return manifest, path


def _entry_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repo_root = _repo_root()
    try:
        manifest_path.relative_to(repo_root)
    except ValueError:
        return manifest_path.parent / path
    return repo_root / path


def _structured_evidence_fields(evidence_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in evidence_text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        normalized_key = key.strip().casefold()
        if not normalized_key or normalized_key in fields:
            continue
        fields[normalized_key] = value.strip()
    return fields


def _is_simulated_path(value: str) -> bool:
    return any(part in value for part in SIMULATED_PATH_PARTS)


def _require_approved_license_evidence(
    manifest_path: Path,
    entry: dict,
    *,
    model_id: str,
) -> None:
    value = str(entry.get("license_evidence_path") or "").strip()
    if not value:
        raise ModelChecksumError(f"{model_id}: missing license_evidence_path")

    relative_path = Path(value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ModelChecksumError(f"{model_id}: license evidence path must be repo-relative")
    try:
        under_license_root = relative_path.is_relative_to(LICENSE_EVIDENCE_ROOT)
    except AttributeError:
        under_license_root = str(relative_path).startswith(str(LICENSE_EVIDENCE_ROOT))
    if not under_license_root:
        raise ModelChecksumError(
            f"{model_id}: license evidence path must be under {LICENSE_EVIDENCE_ROOT}"
        )
    if relative_path.suffix.lower() != ".md":
        raise ModelChecksumError(
            f"{model_id}: license evidence path must point to Markdown evidence"
        )

    evidence_path = _entry_path(manifest_path, value)
    if not evidence_path.is_file():
        raise ModelChecksumError(f"{model_id}: missing license evidence file")
    try:
        evidence_text = evidence_path.read_text(encoding="utf-8")
    except OSError:
        raise ModelChecksumError(f"{model_id}: cannot read license evidence file") from None

    normalized = re.sub(r"\s+", " ", evidence_text.casefold())
    filename_safe_model_id = model_id.replace("/", "_").casefold()
    if model_id.casefold() not in normalized and filename_safe_model_id not in normalized:
        raise ModelChecksumError(f"{model_id}: license evidence must mention the model_id")

    for needle in APPROVED_LICENSE_EVIDENCE_NEEDLES:
        if needle not in normalized:
            raise ModelChecksumError(
                f"{model_id}: approved license evidence must include {needle!r}"
            )
    for needle in APPROVED_LICENSE_FORBIDDEN_NEEDLES:
        if needle in normalized:
            raise ModelChecksumError(
                f"{model_id}: approved license evidence must not contain {needle!r}"
            )

    fields = _structured_evidence_fields(evidence_text)
    missing_fields = sorted(REQUIRED_APPROVED_LICENSE_FIELDS - set(fields))
    if missing_fields:
        raise ModelChecksumError(
            f"{model_id}: approved license evidence missing structured fields {missing_fields}"
        )

    approved_model_id = fields.get("approved_model_id", "")
    if approved_model_id != model_id:
        raise ModelChecksumError(
            f"{model_id}: approved license evidence approved_model_id must match model_id"
        )

    expected_sha = _normalize_sha256(str(entry.get("sha256") or ""))
    approved_model_sha = _normalize_sha256(fields.get("approved_model_sha256", ""))
    if approved_model_sha != expected_sha:
        raise ModelChecksumError(
            f"{model_id}: approved license evidence approved_model_sha256 must match ML-BOM sha256"
        )

    authority = fields.get("review_authority", "")
    if authority not in ALLOWED_LICENSE_REVIEW_AUTHORITIES:
        raise ModelChecksumError(
            f"{model_id}: approved license evidence review_authority must be recognized"
        )

    approval_path_value = fields.get("approval_artifact_path", "")
    if _is_simulated_path(approval_path_value):
        raise ModelChecksumError(
            f"{model_id}: approval_artifact_path must not point to simulations"
        )
    relative_approval_path = Path(approval_path_value)
    if (
        not approval_path_value
        or relative_approval_path.is_absolute()
        or ".." in relative_approval_path.parts
    ):
        raise ModelChecksumError(f"{model_id}: approval_artifact_path must be repo-relative")
    approval_path = _entry_path(manifest_path, approval_path_value)
    if not approval_path.is_file():
        raise ModelChecksumError(f"{model_id}: approval_artifact_path is missing")
    approval_sha = _normalize_sha256(fields.get("approval_artifact_sha256", ""))
    if _sha256_file(approval_path) != approval_sha:
        raise ModelChecksumError(
            f"{model_id}: approval_artifact_sha256 must match approval_artifact_path contents"
        )


def _require_release_ready_entry(
    entry: dict,
    *,
    manifest_path: Path,
    model_id: str,
) -> None:
    license_status = str(entry.get("license_status") or "").strip()
    if license_status != APPROVED_MODEL_LICENSE_STATUS:
        raise ModelChecksumError(
            f"{model_id}: ML-BOM license_status must be {APPROVED_MODEL_LICENSE_STATUS}"
        )
    if entry.get("release_blocker") is not False:
        raise ModelChecksumError(f"{model_id}: ML-BOM entry is a release blocker")
    _require_approved_license_evidence(manifest_path, entry, model_id=model_id)


def expected_model_sha256(
    model_id: str,
    *,
    manifest_path: str | Path | None = None,
) -> str:
    """Return the registered SHA-256 for a release-ready ML-BOM model id."""
    manifest, resolved_manifest_path = _load_manifest(manifest_path)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ModelChecksumError("ML-BOM manifest must contain an entries list")

    for entry in entries:
        if isinstance(entry, dict) and entry.get("model_id") == model_id:
            _require_release_ready_entry(
                entry,
                manifest_path=resolved_manifest_path,
                model_id=model_id,
            )
            sha256 = str(entry.get("sha256") or "")
            return _normalize_sha256(sha256)
    raise ModelChecksumError(f"{model_id}: model_id is not registered in the ML-BOM")


def _release_ready_model_entry(
    model_id: str,
    *,
    manifest_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    manifest, resolved_manifest_path = _load_manifest(manifest_path)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ModelChecksumError("ML-BOM manifest must contain an entries list")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("model_id") == model_id:
            _require_release_ready_entry(
                entry,
                manifest_path=resolved_manifest_path,
                model_id=model_id,
            )
            return entry, resolved_manifest_path
    raise ModelChecksumError(f"{model_id}: model_id is not registered in the ML-BOM")


def _required_snapshot_files(entry: dict[str, Any], *, model_id: str) -> set[str]:
    raw_required = entry.get("required_files")
    if not isinstance(raw_required, list) or not raw_required:
        raise ModelChecksumError(f"{model_id}: directory snapshot requires required_files")
    required: set[str] = set()
    for value in raw_required:
        if not isinstance(value, str):
            raise ModelChecksumError(f"{model_id}: required_files must contain strings")
        path = Path(value)
        normalized = path.as_posix()
        if (
            not normalized
            or path.is_absolute()
            or ".." in path.parts
            or "\x00" in normalized
            or normalized in required
        ):
            raise ModelChecksumError(f"{model_id}: required_files contains an invalid path")
        required.add(normalized)
    return required


def _validate_transformer_snapshot_structure(
    root: Path,
    *,
    entry: dict[str, Any],
    actual_files: set[str],
    model_id: str,
) -> None:
    required = _required_snapshot_files(entry, model_id=model_id)
    missing = sorted(required - actual_files)
    if missing:
        raise ModelChecksumError(
            f"{model_id}: checkpoint snapshot is missing required files: {', '.join(missing)}"
        )
    if "config.json" not in required:
        raise ModelChecksumError(f"{model_id}: required_files must include config.json")
    if not (required & _TOKENIZER_FILES):
        raise ModelChecksumError(
            f"{model_id}: required_files must include tokenizer vocabulary/model data"
        )
    if "tokenizer_config.json" not in required:
        raise ModelChecksumError(f"{model_id}: required_files must include tokenizer_config.json")
    if not (required & _PROCESSOR_FILES):
        raise ModelChecksumError(f"{model_id}: required_files must include processor configuration")

    weight_files = {path for path in actual_files if Path(path).suffix in _WEIGHT_SUFFIXES}
    index_files = {path for path in actual_files if path.endswith(".index.json")}
    if not weight_files:
        raise ModelChecksumError(f"{model_id}: checkpoint snapshot has no model weights")
    unsafe_weight_files = sorted(
        path for path in weight_files if Path(path).suffix != ".safetensors"
    )
    if unsafe_weight_files:
        raise ModelChecksumError(
            f"{model_id}: checkpoint snapshot contains unsafe serialized weights: "
            + ", ".join(unsafe_weight_files)
        )
    if not weight_files.issubset(required):
        raise ModelChecksumError(
            f"{model_id}: required_files must list every model weight or shard"
        )

    for index_file in sorted(index_files):
        if index_file not in required:
            raise ModelChecksumError(f"{model_id}: required_files must include every weight index")
        try:
            index_payload = json.loads((root / index_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ModelChecksumError(f"{model_id}: cannot parse weight index") from None
        weight_map = index_payload.get("weight_map") if isinstance(index_payload, dict) else None
        if not isinstance(weight_map, dict) or not weight_map:
            raise ModelChecksumError(f"{model_id}: weight index has no weight_map")
        shards = {str(value) for value in weight_map.values() if str(value)}
        if not shards or not shards.issubset(actual_files):
            raise ModelChecksumError(f"{model_id}: weight index references a missing model shard")
        if not shards.issubset(required):
            raise ModelChecksumError(
                f"{model_id}: required_files must include every indexed model shard"
            )

    extra_critical = sorted(
        path for path in actual_files - required if Path(path).suffix in _CRITICAL_SUFFIXES
    )
    if extra_critical:
        raise ModelChecksumError(
            f"{model_id}: checkpoint snapshot contains unlisted critical files: "
            + ", ".join(extra_critical)
        )


def verify_model_directory_from_ml_bom(
    model_directory: str | Path,
    *,
    model_id: str,
    manifest_path: str | Path | None = None,
) -> str:
    """Verify a complete Transformers checkpoint snapshot before first load."""
    entry, _resolved_manifest_path = _release_ready_model_entry(
        model_id,
        manifest_path=manifest_path,
    )
    if entry.get("artifact_kind") != DIRECTORY_TREE_ARTIFACT_KIND:
        raise ModelChecksumError(
            f"{model_id}: ML-BOM artifact_kind must be {DIRECTORY_TREE_ARTIFACT_KIND}"
        )
    root = _resolve_snapshot_root(model_directory, model_id=model_id)
    digest, total_size, files = model_directory_tree_sha256(root, model_id=model_id)
    _validate_transformer_snapshot_structure(
        root,
        entry=entry,
        actual_files=set(files),
        model_id=model_id,
    )
    expected_size = entry.get("size_bytes")
    if not isinstance(expected_size, int) or total_size != expected_size:
        raise ModelChecksumError(
            f"{model_id}: directory size mismatch: expected {expected_size}, actual {total_size}"
        )
    expected = _normalize_sha256(str(entry.get("sha256") or ""))
    if digest != expected:
        raise ModelChecksumError(
            f"{model_id}: directory tree checksum mismatch: expected {expected}, actual {digest}"
        )
    return digest


@contextmanager
def verified_model_directory_from_ml_bom(
    model_directory: str | Path,
    *,
    model_id: str,
    manifest_path: str | Path | None = None,
) -> Iterator[Path]:
    """Hold a stable, verified snapshot boundary across local model loading.

    Transformers reopens a checkpoint by pathname, so Python cannot hand it an
    already-open directory descriptor portably. This boundary therefore binds
    every entry's device, inode, mode, size, mtime, and ctime before and after
    both verification and loading, and re-hashes the full tree after loading.
    Loaded objects must not be cached or used until the context exits.
    """
    root = _resolve_snapshot_root(model_directory, model_id=model_id)
    before_verification = _filesystem_snapshot_stamp(root, model_id=model_id)
    expected_digest = verify_model_directory_from_ml_bom(
        root,
        model_id=model_id,
        manifest_path=manifest_path,
    )
    verified_stamp = _filesystem_snapshot_stamp(root, model_id=model_id)
    if before_verification != verified_stamp:
        raise ModelChecksumError(f"{model_id}: checkpoint snapshot changed during verification")

    try:
        yield root
    finally:
        before_reverification = _filesystem_snapshot_stamp(root, model_id=model_id)
        observed_digest = verify_model_directory_from_ml_bom(
            root,
            model_id=model_id,
            manifest_path=manifest_path,
        )
        after_reverification = _filesystem_snapshot_stamp(root, model_id=model_id)
        if before_reverification != after_reverification:
            raise ModelChecksumError(
                f"{model_id}: checkpoint snapshot changed during post-load verification"
            )
        if observed_digest != expected_digest or after_reverification != verified_stamp:
            raise ModelChecksumError(
                f"{model_id}: checkpoint snapshot changed across the model load boundary"
            )


def verify_model_checksum(
    model_path: str | Path,
    *,
    expected_sha256: str,
    model_id: str,
) -> str:
    """Verify a model file's SHA-256 before it is deserialized."""
    path = Path(model_path)
    if not path.is_file():
        raise ModelChecksumError(f"{model_id}: model file not found")

    expected = _normalize_sha256(expected_sha256)
    actual = _sha256_file(path)
    if actual != expected:
        raise ModelChecksumError(f"{model_id}: checksum mismatch")
    return actual


def verify_model_checksum_from_ml_bom(
    model_path: str | Path,
    *,
    model_id: str,
    manifest_path: str | Path | None = None,
) -> str:
    """Verify a model file against the ML-BOM entry for its model id."""
    expected_sha256 = expected_model_sha256(model_id, manifest_path=manifest_path)
    return verify_model_checksum(
        model_path,
        expected_sha256=expected_sha256,
        model_id=model_id,
    )
