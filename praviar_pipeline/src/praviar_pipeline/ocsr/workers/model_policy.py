"""Standard-library-only model policy checks for isolated OCSR workers."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

_SHARED_WRITE_BITS = stat.S_IWGRP | stat.S_IWOTH


def _assert_not_shared_writable(path: Path, *, label: str, directory: bool) -> None:
    try:
        file_stat = path.stat()
    except FileNotFoundError:
        raise RuntimeError(f"{label} does not exist") from None
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(file_stat.st_mode):
        kind = "directory" if directory else "regular file"
        raise RuntimeError(f"{label} must be a {kind}")
    if file_stat.st_mode & _SHARED_WRITE_BITS:
        raise RuntimeError(f"{label} must not be group- or world-writable")


def _strict_json_object(raw: str) -> dict:
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(f"Praviar model registry repeats key {key!r}")
            result[key] = value
        return result

    def reject_non_json_constant(value):
        raise RuntimeError(f"Praviar model registry contains non-JSON number {value}")

    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_json_constant,
        )
    except json.JSONDecodeError:
        raise RuntimeError("Praviar model registry is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("Praviar model registry must be a JSON object")
    return parsed


def verified_model_path(model_id: str) -> Path:
    """Resolve a model only when the packaged registry approves and verifies it."""
    registry_path = Path(__file__).resolve().parents[2] / "model_registry.json"
    try:
        registry_raw = registry_path.read_text(encoding="utf-8")
    except OSError:
        raise RuntimeError("Praviar model registry cannot be read") from None
    registry = _strict_json_object(registry_raw)
    if (
        registry.get("schema_version") != "praviar.model-registry.v1"
        or registry.get("default_policy") != "fail_closed"
    ):
        raise RuntimeError("Praviar model registry policy is invalid")
    entries = registry.get("entries")
    if not isinstance(entries, list) or any(
        not isinstance(candidate, dict) for candidate in entries
    ):
        raise RuntimeError("Praviar model registry entries are invalid")
    entry = next(
        (candidate for candidate in entries if candidate.get("model_id") == model_id), None
    )
    if entry is None:
        raise RuntimeError(f"model {model_id} is absent from the Praviar registry")
    if entry.get("license_status") != "approved" or entry.get("permitted_use") != "approved":
        raise RuntimeError(f"model {model_id} activation is disabled by registry policy")
    expected_sha256 = entry.get("sha256")
    expected_size = entry.get("expected_size_bytes")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
        or type(expected_size) is not int
        or expected_size <= 0
    ):
        raise RuntimeError(f"model {model_id} has no approved checksum and size")

    configured_root = Path(
        os.environ.get(
            "PRAVIAR_MODEL_HOME",
            str(Path.home() / ".cache" / "praviar" / "models"),
        )
    ).expanduser()
    if configured_root.is_symlink():
        raise RuntimeError("Praviar model root must not be a symlink")
    model_root = configured_root.resolve()
    if model_root.exists():
        _assert_not_shared_writable(model_root, label="Praviar model root", directory=True)
    raw_destination = entry.get("runtime_destination")
    if (
        not isinstance(raw_destination, str)
        or not raw_destination
        or "\\" in raw_destination
        or "\x00" in raw_destination
        or any(part in {"", ".", ".."} or ":" in part for part in raw_destination.split("/"))
    ):
        raise RuntimeError(f"model {model_id} has an unsafe registry destination")
    relative_destination = Path(raw_destination)
    allowed_filenames = entry.get("allowed_filenames")
    if (
        not isinstance(allowed_filenames, list)
        or relative_destination.name not in allowed_filenames
    ):
        raise RuntimeError(f"model {model_id} destination is not allowlisted")
    cursor = model_root
    for part in relative_destination.parts[:-1]:
        cursor /= part
        if cursor.is_symlink():
            raise RuntimeError(f"model {model_id} path must not contain symlinks")
        if cursor.exists():
            _assert_not_shared_writable(
                cursor,
                label=f"model {model_id} directory",
                directory=True,
            )
    unresolved = model_root / relative_destination
    if unresolved.is_symlink():
        raise RuntimeError(f"model {model_id} must not be a symlink")
    destination = unresolved.resolve()
    if model_root not in destination.parents:
        raise RuntimeError(f"model {model_id} destination escapes the model root")
    try:
        file_stat = destination.stat()
    except FileNotFoundError:
        raise RuntimeError(f"model {model_id} is not installed") from None
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_mode & _SHARED_WRITE_BITS
        or file_stat.st_size != expected_size
    ):
        raise RuntimeError(f"model {model_id} does not match its registered size")

    receipt_path = unresolved.with_suffix(f"{unresolved.suffix}.receipt.json")
    if receipt_path.is_symlink():
        raise RuntimeError(f"model {model_id} receipt must not be a symlink")
    _assert_not_shared_writable(
        receipt_path,
        label=f"model {model_id} receipt",
        directory=False,
    )
    try:
        receipt = _strict_json_object(receipt_path.read_text(encoding="utf-8"))
    except OSError:
        raise RuntimeError(f"model {model_id} receipt cannot be read") from None
    if set(receipt) != {
        "schema_version",
        "model_id",
        "registry_as_of_date",
        "acquisition_kind",
        "sha256",
        "size_bytes",
        "runtime_destination",
        "verified_at",
    }:
        raise RuntimeError(f"model {model_id} receipt fields are invalid")
    if (
        receipt.get("schema_version") != "praviar.model-receipt.v1"
        or receipt.get("model_id") != model_id
        or receipt.get("registry_as_of_date") != registry.get("as_of_date")
        or receipt.get("acquisition_kind") not in {"download", "register-local"}
        or receipt.get("sha256") != expected_sha256
        or receipt.get("size_bytes") != expected_size
        or receipt.get("runtime_destination") != raw_destination
        or not isinstance(receipt.get("verified_at"), str)
    ):
        raise RuntimeError(f"model {model_id} receipt does not match registry policy")

    digest = hashlib.sha256()
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise RuntimeError(f"model {model_id} does not match its registered SHA-256")
    return destination
