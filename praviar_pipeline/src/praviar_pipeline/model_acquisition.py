"""Fail-closed acquisition for optional third-party model artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

if TYPE_CHECKING:
    from collections.abc import Iterable

_REGISTRY_RESOURCE = "model_registry.json"
_SHA256_PATTERN = r"^[a-f0-9]{64}$"
_MODEL_ID_PATTERN = r"^[a-z0-9][a-z0-9._/-]+$"
_MAX_MODEL_SIZE_BYTES = 10 * 1024 * 1024 * 1024
_SHARED_WRITE_BITS = stat.S_IWGRP | stat.S_IWOTH


class ModelAcquisitionError(RuntimeError):
    """Raised when a model operation cannot satisfy the registry policy."""


class ModelEntry(BaseModel):
    """A single immutable model acquisition policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(pattern=_MODEL_ID_PATTERN)
    component: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source_kind: Literal["github", "huggingface", "upstream_project"]
    upstream_page_url: str
    upstream_revision: str | None
    acquisition_url: str | None
    allowed_filenames: tuple[str, ...] = Field(min_length=1)
    expected_size_bytes: int | None = Field(
        default=None,
        gt=0,
        le=_MAX_MODEL_SIZE_BYTES,
    )
    sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    serialization_format: str = Field(min_length=1)
    license_identifier: str = Field(min_length=1)
    license_status: Literal["approved", "pending_review", "noncommercial", "unknown"]
    redistribution_allowed: bool
    automated_download_allowed: bool
    permitted_use: Literal["approved", "research_noncommercial_only", "unapproved"]
    acknowledgement_required: bool
    runtime_destination: str

    @field_validator("upstream_page_url", "acquisition_url")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = httpx.URL(value)
        except httpx.InvalidURL as exc:
            raise ValueError("model URLs must be valid absolute HTTPS URLs") from exc
        if (
            parsed.scheme != "https"
            or not parsed.is_absolute_url
            or not parsed.host
            or parsed.userinfo
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "model URLs must be absolute HTTPS URLs without embedded credentials, "
                "queries, or fragments"
            )
        return value

    @field_validator("allowed_filenames")
    @classmethod
    def _safe_filenames(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            Path(name).name != name
            or name in {"", ".", ".."}
            or any(character in name for character in ("/", "\\", ":", "\x00"))
            for name in value
        ):
            raise ValueError("allowed filenames must be plain basenames")
        return value

    @field_validator("runtime_destination")
    @classmethod
    def _safe_destination(cls, value: str) -> str:
        path = PurePosixPath(value)
        unsafe_part = any(part in {"", ".", ".."} or ":" in part for part in path.parts)
        if path.is_absolute() or not path.parts or unsafe_part or "\\" in value or "\x00" in value:
            raise ValueError("runtime destination must be a safe relative path")
        return value

    @model_validator(mode="after")
    def _coherent_policy(self) -> ModelEntry:
        filename = PurePosixPath(self.runtime_destination).name
        if filename not in self.allowed_filenames:
            raise ValueError("runtime destination filename must be allowlisted")
        if self.automated_download_allowed:
            if self.license_status != "approved" or self.permitted_use != "approved":
                raise ValueError("automatic downloads require an approved use policy")
            if not self.acquisition_url or not self.sha256 or not self.expected_size_bytes:
                raise ValueError("automatic downloads require URL, size and SHA-256")
            if not self.upstream_revision:
                raise ValueError("automatic downloads require an immutable upstream revision")
        if self.permitted_use == "approved" and self.license_status != "approved":
            raise ValueError("approved use requires an approved license status")
        if self.redistribution_allowed and self.license_status != "approved":
            raise ValueError("redistribution requires an approved license status")
        if self.license_status == "noncommercial":
            if self.permitted_use != "research_noncommercial_only":
                raise ValueError("non-commercial models require research-only use")
        elif self.permitted_use == "research_noncommercial_only":
            raise ValueError("research-only use requires a noncommercial rights status")
        return self


class ModelRegistry(BaseModel):
    """Versioned registry with unique model identities and destinations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.model-registry.v1"]
    as_of_date: str
    default_policy: Literal["fail_closed"]
    entries: tuple[ModelEntry, ...]

    @model_validator(mode="after")
    def _unique_entries(self) -> ModelRegistry:
        identifiers = [entry.model_id for entry in self.entries]
        destinations = [entry.runtime_destination for entry in self.entries]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("model registry IDs must be unique")
        if len(destinations) != len(set(destinations)):
            raise ValueError("model registry destinations must be unique")
        return self

    def get(self, model_id: str) -> ModelEntry:
        for entry in self.entries:
            if entry.model_id == model_id:
                return entry
        raise ModelAcquisitionError(f"unknown model ID: {model_id}")


class ModelReceipt(BaseModel):
    """Machine-readable record written after an explicit acquisition command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.model-receipt.v1"] = "praviar.model-receipt.v1"
    model_id: str
    registry_as_of_date: str
    acquisition_kind: Literal["download", "register-local", "verify"]
    sha256: str
    size_bytes: int
    runtime_destination: str
    verified_at: str


def _strict_registry_json(raw: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = value
        return result

    def reject_non_json_constant(value: str) -> None:
        raise ValueError(f"non-JSON number {value}")

    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ModelAcquisitionError(f"model registry is not strict JSON: {exc}") from exc


def load_registry() -> ModelRegistry:
    """Load and validate the registry bundled with the Python package."""
    resource = files("praviar_pipeline").joinpath(_REGISTRY_RESOURCE)
    raw = _strict_registry_json(resource.read_text(encoding="utf-8"))
    try:
        return ModelRegistry.model_validate(raw)
    except ValidationError as exc:
        raise ModelAcquisitionError(f"model registry failed schema validation: {exc}") from exc


def default_model_root() -> Path:
    """Return the explicit override or a user-local, non-repository cache root."""
    configured = os.environ.get("PRAVIAR_MODEL_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "praviar" / "models"


def _resolved_model_root(root: Path | None) -> Path:
    configured = (root or default_model_root()).expanduser()
    if configured.is_symlink():
        raise ModelAcquisitionError(f"model root must not be a symlink: {configured}")
    return configured.resolve()


def model_path(entry: ModelEntry, *, root: Path | None = None) -> Path:
    """Resolve a registry destination while enforcing root containment."""
    model_root = _resolved_model_root(root)
    destination = (model_root / entry.runtime_destination).resolve()
    if destination == model_root or model_root not in destination.parents:
        raise ModelAcquisitionError("model destination escapes the configured model root")
    return destination


def _assert_regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise ModelAcquisitionError(f"{label} must not be a symlink: {path}")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise ModelAcquisitionError(f"{label} does not exist: {path}") from exc
    if not stat.S_ISREG(mode):
        raise ModelAcquisitionError(f"{label} must be a regular file: {path}")


def _assert_private_directory(path: Path, *, label: str) -> None:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise ModelAcquisitionError(f"{label} does not exist: {path}") from exc
    if not stat.S_ISDIR(mode):
        raise ModelAcquisitionError(f"{label} must be a directory: {path}")
    if mode & _SHARED_WRITE_BITS:
        raise ModelAcquisitionError(f"{label} must not be group- or world-writable: {path}")


def _assert_safe_parent(destination: Path, model_root: Path) -> None:
    model_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    relative_parent = destination.parent.relative_to(model_root)
    cursor = model_root
    if cursor.is_symlink():
        raise ModelAcquisitionError(f"model root must not be a symlink: {cursor}")
    _assert_private_directory(cursor, label="model root")
    for part in relative_parent.parts:
        cursor /= part
        if cursor.exists() and cursor.is_symlink():
            raise ModelAcquisitionError(f"model directory must not be a symlink: {cursor}")
        cursor.mkdir(exist_ok=True, mode=0o700)
        _assert_private_directory(cursor, label="model directory")
    if destination.is_symlink():
        raise ModelAcquisitionError(f"model destination must not be a symlink: {destination}")


def _copy_chunks_to_staging(
    chunks: Iterable[bytes],
    *,
    destination: Path,
    expected_sha256: str,
    expected_size_bytes: int,
) -> tuple[str, int]:
    # The caller has already resolved containment; use the destination parent for
    # staging so os.replace remains atomic on the same filesystem.
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".part",
            dir=destination.parent,
            delete=False,
        ) as staging:
            temp_path = Path(staging.name)
            for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > expected_size_bytes:
                    raise ModelAcquisitionError("model artifact exceeds the registered size")
                digest.update(chunk)
                staging.write(chunk)
            staging.flush()
            os.fsync(staging.fileno())
        observed = digest.hexdigest()
        if size != expected_size_bytes:
            raise ModelAcquisitionError(
                f"model size mismatch: expected {expected_size_bytes}, observed {size}"
            )
        if observed != expected_sha256:
            raise ModelAcquisitionError(
                f"model SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
            )
        os.replace(temp_path, destination)
        temp_path = None
        return observed, size
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _require_verifiable(entry: ModelEntry) -> tuple[str, int]:
    if entry.sha256 is None or entry.expected_size_bytes is None:
        raise ModelAcquisitionError(
            f"{entry.model_id} has no approved checksum/size; "
            "use the upstream page and do not activate it"
        )
    return entry.sha256, entry.expected_size_bytes


def _receipt_path(destination: Path) -> Path:
    return destination.with_suffix(f"{destination.suffix}.receipt.json")


def _assert_safe_receipt_path(destination: Path) -> None:
    receipt_path = _receipt_path(destination)
    if receipt_path.is_symlink():
        raise ModelAcquisitionError(f"model receipt must not be a symlink: {receipt_path}")
    if receipt_path.exists() and not receipt_path.is_file():
        raise ModelAcquisitionError(f"model receipt must be a regular file: {receipt_path}")


def _write_receipt(
    entry: ModelEntry,
    registry: ModelRegistry,
    *,
    destination: Path,
    acquisition_kind: Literal["download", "register-local"],
    sha256: str,
    size_bytes: int,
) -> ModelReceipt:
    receipt = ModelReceipt(
        model_id=entry.model_id,
        registry_as_of_date=registry.as_of_date,
        acquisition_kind=acquisition_kind,
        sha256=sha256,
        size_bytes=size_bytes,
        runtime_destination=entry.runtime_destination,
        verified_at=datetime.now(UTC).isoformat(),
    )
    receipt_path = _receipt_path(destination)
    _assert_safe_receipt_path(destination)
    encoded = (json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{receipt_path.name}.",
            suffix=".part",
            dir=receipt_path.parent,
            delete=False,
        ) as staging:
            temp_path = Path(staging.name)
            staging.write(encoded)
            staging.flush()
            os.fsync(staging.fileno())
        if receipt_path.is_symlink():
            raise ModelAcquisitionError(f"model receipt must not be a symlink: {receipt_path}")
        os.replace(temp_path, receipt_path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return receipt


def register_local_model(
    model_id: str,
    source: Path,
    *,
    acknowledge_license: bool,
    registry: ModelRegistry | None = None,
    root: Path | None = None,
) -> ModelReceipt:
    """Verify and atomically copy an operator-acquired file into the model root."""
    active_registry = registry or load_registry()
    entry = active_registry.get(model_id)
    if entry.license_status != "approved" or entry.permitted_use != "approved":
        raise ModelAcquisitionError(
            f"local activation is disabled for {model_id}; upstream: {entry.upstream_page_url}"
        )
    if entry.acknowledgement_required and not acknowledge_license:
        raise ModelAcquisitionError("explicit --accept-license acknowledgement is required")
    expected_sha256, expected_size = _require_verifiable(entry)
    source = source.expanduser()
    _assert_regular_file(source, label="local model")
    destination = model_path(entry, root=root)
    model_root = _resolved_model_root(root)
    _assert_safe_parent(destination, model_root)
    _assert_safe_receipt_path(destination)
    with source.open("rb") as handle:
        observed, size = _copy_chunks_to_staging(
            iter(lambda: handle.read(1024 * 1024), b""),
            destination=destination,
            expected_sha256=expected_sha256,
            expected_size_bytes=expected_size,
        )
    try:
        return _write_receipt(
            entry,
            active_registry,
            destination=destination,
            acquisition_kind="register-local",
            sha256=observed,
            size_bytes=size,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def fetch_model(
    model_id: str,
    *,
    acknowledge_license: bool,
    registry: ModelRegistry | None = None,
    root: Path | None = None,
    client: httpx.Client | None = None,
) -> ModelReceipt:
    """Download an explicitly approved model; current shipped entries are link-only."""
    active_registry = registry or load_registry()
    entry = active_registry.get(model_id)
    if not entry.automated_download_allowed:
        raise ModelAcquisitionError(
            f"automatic download is disabled for {model_id}; upstream: {entry.upstream_page_url}"
        )
    if entry.acknowledgement_required and not acknowledge_license:
        raise ModelAcquisitionError("explicit --accept-license acknowledgement is required")
    expected_sha256, expected_size = _require_verifiable(entry)
    acquisition_url = entry.acquisition_url
    if acquisition_url is None:
        raise ModelAcquisitionError("approved model has no acquisition URL")
    destination = model_path(entry, root=root)
    model_root = _resolved_model_root(root)
    _assert_safe_parent(destination, model_root)
    _assert_safe_receipt_path(destination)

    def download(active_client: httpx.Client) -> tuple[str, int]:
        approved_url = httpx.URL(acquisition_url)
        approved_origin = (
            approved_url.scheme,
            approved_url.host,
            approved_url.port or 443,
        )
        current_url = approved_url
        for _redirect_count in range(6):
            # Do not let a caller-supplied Client's redirect setting issue a
            # request to an unreviewed host before policy can inspect it.
            with active_client.stream("GET", current_url, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ModelAcquisitionError(
                            "model server returned a redirect without a location"
                        )
                    redirect_url = response.url.join(location)
                    redirect_origin = (
                        redirect_url.scheme,
                        redirect_url.host,
                        redirect_url.port or 443,
                    )
                    if redirect_url.scheme != "https":
                        raise ModelAcquisitionError("model download redirected away from HTTPS")
                    if redirect_origin != approved_origin:
                        raise ModelAcquisitionError(
                            "model download redirected to an unapproved origin"
                        )
                    current_url = redirect_url
                    continue

                response.raise_for_status()
                declared_size = response.headers.get("content-length")
                if declared_size:
                    try:
                        parsed_size = int(declared_size)
                    except ValueError as exc:
                        raise ModelAcquisitionError(
                            "model server returned an invalid Content-Length"
                        ) from exc
                    if parsed_size < 0:
                        raise ModelAcquisitionError(
                            "model server returned an invalid Content-Length"
                        )
                    if parsed_size > expected_size:
                        raise ModelAcquisitionError("model server declared an oversized artifact")
                return _copy_chunks_to_staging(
                    response.iter_bytes(1024 * 1024),
                    destination=destination,
                    expected_sha256=expected_sha256,
                    expected_size_bytes=expected_size,
                )
        raise ModelAcquisitionError(
            "model download exceeded the maximum of five same-origin redirects"
        )

    if client is None:
        with httpx.Client(timeout=60.0, follow_redirects=False) as owned_client:
            observed, size = download(owned_client)
    else:
        observed, size = download(client)
    try:
        return _write_receipt(
            entry,
            active_registry,
            destination=destination,
            acquisition_kind="download",
            sha256=observed,
            size_bytes=size,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def verify_model(
    model_id: str,
    *,
    registry: ModelRegistry | None = None,
    root: Path | None = None,
) -> ModelReceipt:
    """Verify an installed model and return an in-memory verification receipt."""
    active_registry = registry or load_registry()
    entry = active_registry.get(model_id)
    expected_sha256, expected_size = _require_verifiable(entry)
    destination = model_path(entry, root=root)
    _assert_regular_file(destination, label="installed model")
    digest = hashlib.sha256()
    size = 0
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            if size > expected_size:
                raise ModelAcquisitionError("installed model exceeds the registered size")
            digest.update(chunk)
    observed = digest.hexdigest()
    if size != expected_size or observed != expected_sha256:
        raise ModelAcquisitionError("installed model does not match the registry")
    return ModelReceipt(
        model_id=entry.model_id,
        registry_as_of_date=active_registry.as_of_date,
        acquisition_kind="verify",
        sha256=observed,
        size_bytes=size,
        runtime_destination=entry.runtime_destination,
        verified_at=datetime.now(UTC).isoformat(),
    )
