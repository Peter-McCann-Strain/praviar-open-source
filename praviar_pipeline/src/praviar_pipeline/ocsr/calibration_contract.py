"""Signed, fail-closed calibration contract for live OCSR evidence."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from praviar_pipeline.config_paths import REPO_ROOT
from praviar_pipeline.vision_production import (
    DEFAULT_ROSTER_PATH,
    VisionProductionRoster,
    load_roster,
)

SCHEMA_VERSION = "praviar-ocsr-calibration/v1"
EXACTNESS_DEFINITION = "canonical_isomeric_smiles_exact_v1"
CALIBRATION_DOMAIN = "patent_pdf_chemical_structure_images"
MAX_ARTIFACT_VALIDITY = timedelta(days=180)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class CalibrationContractError(RuntimeError):
    """Raised when live OCSR calibration evidence is absent or invalid."""


class CalibrationModelBinding(BaseModel):
    """One immutable model artifact used by a calibrated OCSR tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_RE.pattern)


class CalibrationToolBinding(BaseModel):
    """Tool calibration bound to exact models and an immutable runtime image."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str = Field(min_length=1)
    models: tuple[CalibrationModelBinding, ...] = Field(min_length=1)
    container_image_digest: str = Field(pattern=OCI_DIGEST_RE.pattern)
    calibration_method: Literal["platt"] = "platt"
    platt_a: float = Field(gt=0)
    platt_b: float

    @model_validator(mode="after")
    def validate_binding(self) -> CalibrationToolBinding:
        model_ids = [model.model_id for model in self.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("calibration tool model_id values must be unique")
        if not math.isfinite(self.platt_a) or not math.isfinite(self.platt_b):
            raise ValueError("calibration parameters must be finite")
        return self


class CalibrationSignature(BaseModel):
    """Detached Ed25519 signature metadata for the canonical artifact payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm: Literal["Ed25519"] = "Ed25519"
    key_id: str = Field(min_length=1)
    value_b64: str = Field(min_length=1)


class OCSRCalibrationArtifact(BaseModel):
    """Versioned release artifact governing calibrated live OCSR output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar-ocsr-calibration/v1"]
    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    revocation_epoch: int = Field(ge=0)
    issued_at: datetime
    expires_at: datetime
    calibration_corpus_sha256: str = Field(pattern=SHA256_RE.pattern)
    runtime_roster_sha256: str = Field(pattern=SHA256_RE.pattern)
    ml_bom_sha256: str = Field(pattern=SHA256_RE.pattern)
    exactness_definition: Literal["canonical_isomeric_smiles_exact_v1"]
    domain: Literal["patent_pdf_chemical_structure_images"]
    jurisdictions: tuple[Literal["US", "EP", "WO", "JP", "CN", "KR"], ...] = Field(min_length=1)
    minimum_resolved_confidence: float = Field(ge=0, le=1)
    tools: tuple[CalibrationToolBinding, ...] = Field(min_length=1)
    signature: CalibrationSignature

    @model_validator(mode="after")
    def validate_artifact(self) -> OCSRCalibrationArtifact:
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("calibration validity timestamps must be timezone-aware")
        issued_at = self.issued_at.astimezone(UTC)
        expires_at = self.expires_at.astimezone(UTC)
        if expires_at <= issued_at:
            raise ValueError("calibration artifact expires_at must follow issued_at")
        if expires_at - issued_at > MAX_ARTIFACT_VALIDITY:
            raise ValueError("calibration artifact validity exceeds 180 days")
        if len(set(self.jurisdictions)) != len(self.jurisdictions):
            raise ValueError("calibration jurisdictions must be unique")
        tool_ids = [tool.tool_id for tool in self.tools]
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("calibration tool_id values must be unique")
        return self


class VerifiedCalibration(BaseModel):
    """Minimal runtime material emitted only after complete verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    artifact_revision: int
    revocation_epoch: int
    artifact_sha256: str
    runtime_roster_sha256: str
    ml_bom_sha256: str
    minimum_resolved_confidence: float
    parameters: dict[str, tuple[float, float]]


def _canonical_unsigned_bytes(artifact: OCSRCalibrationArtifact) -> bytes:
    payload = artifact.model_dump(mode="json", exclude={"signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_calibration_artifact(
    payload: dict[str, Any],
    *,
    private_key: Ed25519PrivateKey,
    key_id: str,
) -> dict[str, Any]:
    """Return a validated artifact signed over its canonical unsigned payload.

    This helper exists for offline release tooling and tests. Production
    runtime code verifies artifacts and never writes or repairs them.
    """
    unsigned = dict(payload)
    unsigned["signature"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "value_b64": base64.b64encode(b"\x00" * 64).decode(),
    }
    artifact = OCSRCalibrationArtifact.model_validate(unsigned)
    signature = private_key.sign(_canonical_unsigned_bytes(artifact))
    signed = artifact.model_dump(mode="json")
    signed["signature"]["value_b64"] = base64.b64encode(signature).decode()
    return signed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _secret_value(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value or "")


def _load_ml_bom_model_hashes(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationContractError("cannot read calibration-bound ML-BOM") from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise CalibrationContractError("calibration-bound ML-BOM has no entries")
    model_hashes: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("model_id")
        digest = entry.get("sha256")
        if (
            isinstance(model_id, str)
            and model_id
            and isinstance(digest, str)
            and SHA256_RE.fullmatch(digest)
        ):
            if model_id in model_hashes:
                raise CalibrationContractError("calibration-bound ML-BOM has duplicate model IDs")
            model_hashes[model_id] = digest
    return model_hashes


def _configured_tool_ids(settings: object) -> tuple[str, ...]:
    values = getattr(settings, "drawing_ensemble_tools", ()) or ()
    tool_ids = [str(value).strip().lower() for value in values if str(value).strip()]
    if (
        bool(getattr(settings, "drawing_markushgrapher_enabled", False))
        and str(getattr(settings, "drawing_markush_rollout_state", "")).strip().lower()
        in {"beta", "production"}
        and "markushgrapher" not in tool_ids
    ):
        tool_ids.append("markushgrapher")
    if not tool_ids or len(set(tool_ids)) != len(tool_ids):
        raise CalibrationContractError("live drawing_ensemble_tools must be non-empty and unique")
    return tuple(tool_ids)


def _load_pinned_artifact(settings: object) -> tuple[OCSRCalibrationArtifact, str]:
    artifact_path_value = str(
        getattr(settings, "drawing_analysis_calibration_artifact_path", "") or ""
    ).strip()
    if not artifact_path_value:
        raise CalibrationContractError("live drawing evidence requires a calibration artifact")
    artifact_path = _resolve_repo_path(artifact_path_value)
    try:
        artifact_bytes = artifact_path.read_bytes()
        payload = json.loads(artifact_bytes)
        artifact = OCSRCalibrationArtifact.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CalibrationContractError("cannot load a valid calibration artifact") from exc

    expected_artifact_sha = str(
        getattr(settings, "drawing_analysis_calibration_artifact_sha256", "") or ""
    ).strip()
    if (
        not SHA256_RE.fullmatch(expected_artifact_sha)
        or hashlib.sha256(artifact_bytes).hexdigest() != expected_artifact_sha
    ):
        raise CalibrationContractError("calibration artifact SHA-256 pin mismatch")
    return artifact, expected_artifact_sha


def _verify_anti_replay(settings: object, artifact: OCSRCalibrationArtifact) -> None:
    minimum_revision = getattr(settings, "drawing_analysis_calibration_min_revision", None)
    if (
        isinstance(minimum_revision, bool)
        or not isinstance(minimum_revision, int)
        or minimum_revision < 1
        or artifact.artifact_revision < minimum_revision
    ):
        raise CalibrationContractError("calibration artifact revision is below the live floor")

    minimum_revocation_epoch = getattr(
        settings,
        "drawing_analysis_calibration_revocation_epoch",
        None,
    )
    if (
        isinstance(minimum_revocation_epoch, bool)
        or not isinstance(minimum_revocation_epoch, int)
        or minimum_revocation_epoch < 0
        or artifact.revocation_epoch < minimum_revocation_epoch
    ):
        raise CalibrationContractError("calibration artifact revocation epoch is stale")

    revoked_artifact_ids = {
        str(value).strip()
        for value in (
            getattr(settings, "drawing_analysis_revoked_calibration_artifact_ids", ()) or ()
        )
        if str(value).strip()
    }
    if artifact.artifact_id in revoked_artifact_ids:
        raise CalibrationContractError("calibration artifact is revoked")


def _verify_artifact_signature(settings: object, artifact: OCSRCalibrationArtifact) -> None:
    public_key_b64 = _secret_value(getattr(settings, "drawing_analysis_calibration_public_key", ""))
    try:
        public_key_bytes = base64.b64decode(public_key_b64, validate=True)
        signature_bytes = base64.b64decode(artifact.signature.value_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CalibrationContractError(
            "live drawing evidence requires a valid calibration public key"
        ) from exc
    if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
        raise CalibrationContractError(
            "live drawing evidence requires a valid calibration public key"
        )

    expected_key_id = str(
        getattr(settings, "drawing_analysis_calibration_key_id", "") or ""
    ).strip()
    if not expected_key_id or artifact.signature.key_id != expected_key_id:
        raise CalibrationContractError("calibration signature key ID mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            _canonical_unsigned_bytes(artifact),
        )
    except (InvalidSignature, ValueError):
        raise CalibrationContractError("calibration artifact signature mismatch") from None


def _verify_artifact_lifetime_and_corpus(
    settings: object,
    artifact: OCSRCalibrationArtifact,
    *,
    now: datetime | None,
) -> None:
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if checked_at < artifact.issued_at.astimezone(UTC):
        raise CalibrationContractError("calibration artifact is not yet valid")
    if checked_at >= artifact.expires_at.astimezone(UTC):
        raise CalibrationContractError("calibration artifact is stale")

    expected_corpus_sha = str(
        getattr(settings, "drawing_analysis_calibration_corpus_sha256", "") or ""
    ).strip()
    if not SHA256_RE.fullmatch(expected_corpus_sha):
        raise CalibrationContractError("live calibration corpus SHA-256 is not pinned")
    if artifact.calibration_corpus_sha256 != expected_corpus_sha:
        raise CalibrationContractError("calibration corpus SHA-256 mismatch")


def _load_calibration_runtime(
    settings: object,
    artifact: OCSRCalibrationArtifact,
) -> tuple[VisionProductionRoster, dict[str, str]]:
    roster_path_value = (
        getattr(settings, "drawing_analysis_vision_roster_path", "") or DEFAULT_ROSTER_PATH
    )
    roster_path = _resolve_repo_path(roster_path_value)
    try:
        roster, roster_sha256 = load_roster(roster_path)
    except (OSError, ValueError) as exc:
        raise CalibrationContractError("cannot load calibration-bound vision roster") from exc
    if artifact.runtime_roster_sha256 != roster_sha256:
        raise CalibrationContractError("calibration vision roster SHA-256 mismatch")

    configured_segmentation = (
        str(getattr(settings, "drawing_segmentation_tool", "")).strip().lower()
    )
    if configured_segmentation != roster.runtime_contract.segmentation_tool:
        raise CalibrationContractError(
            "live segmentation tool does not match the calibration-bound vision roster"
        )
    if roster.runtime_contract.classifier_required and not bool(
        getattr(settings, "drawing_classifier_enabled", False)
    ):
        raise CalibrationContractError("live vision roster requires the chemical-image classifier")

    ml_bom_path = _resolve_repo_path(
        str(getattr(settings, "drawing_analysis_ml_bom_path", "") or "")
    )
    if not ml_bom_path.is_file():
        raise CalibrationContractError("calibration-bound ML-BOM is unavailable")
    if artifact.ml_bom_sha256 != _sha256_file(ml_bom_path):
        raise CalibrationContractError("calibration ML-BOM SHA-256 mismatch")
    return roster, _load_ml_bom_model_hashes(ml_bom_path)


def _verify_tool_allowlist(
    configured_tools: tuple[str, ...],
    roster: VisionProductionRoster,
) -> None:
    production_tools = (
        set(roster.runtime_contract.primary_ocsr_tools)
        | set(roster.runtime_contract.markush_ocsr_tools)
        | set(roster.runtime_contract.sar_table_tools)
    )
    prohibited_tools = set(roster.runtime_contract.prohibited_production_tools)
    unknown_tools = set(configured_tools) - production_tools
    if unknown_tools or set(configured_tools) & prohibited_tools:
        raise CalibrationContractError(
            "live drawing configuration contains an unknown or prohibited OCSR tool"
        )


def _load_expected_container_digests(
    settings: object,
    configured_tools: tuple[str, ...],
    roster: VisionProductionRoster,
) -> dict[Any, Any]:
    expected_container_digests = getattr(
        settings,
        "drawing_analysis_container_image_digests",
        {},
    )
    if not isinstance(expected_container_digests, dict) or set(expected_container_digests) != set(
        configured_tools
    ):
        raise CalibrationContractError(
            "live OCSR container image digests must exactly cover the configured tools"
        )
    if roster.architecture == "subprocess_venv_workers":
        worker_image_digest = str(
            getattr(settings, "certification_worker_oci_image_digest", "") or ""
        ).strip()
        if not OCI_DIGEST_RE.fullmatch(worker_image_digest) or set(
            expected_container_digests.values()
        ) != {worker_image_digest}:
            raise CalibrationContractError(
                "subprocess vision calibration must bind every tool to the "
                "executing worker OCI image digest"
            )
    return expected_container_digests


def _bind_tool_parameters(
    configured_tools: tuple[str, ...],
    artifact_tools: dict[str, CalibrationToolBinding],
    expected_container_digests: dict[Any, Any],
    roster: VisionProductionRoster,
    model_hashes: dict[str, str],
) -> dict[str, tuple[float, float]]:
    roster_models_by_tool = {
        component.component_id.removeprefix("ocsr."): tuple(
            model.model_id for model in component.models
        )
        for component in roster.components
        if component.role in {"primary_ocsr", "markush_ocsr", "sar_table"}
    }
    parameters: dict[str, tuple[float, float]] = {}
    for tool_id in configured_tools:
        binding = artifact_tools[tool_id]
        roster_model_ids = roster_models_by_tool.get(tool_id)
        if roster_model_ids is None:
            raise CalibrationContractError("live OCSR tool has no roster model binding")
        if tuple(model.model_id for model in binding.models) != roster_model_ids:
            raise CalibrationContractError("calibration model roster mismatch")
        if any(model_hashes.get(model.model_id) != model.sha256 for model in binding.models):
            raise CalibrationContractError("calibration model SHA-256 mismatch")
        expected_container_digest = expected_container_digests.get(tool_id)
        if (
            not isinstance(expected_container_digest, str)
            or not OCI_DIGEST_RE.fullmatch(expected_container_digest)
            or binding.container_image_digest != expected_container_digest
        ):
            raise CalibrationContractError("calibration container image digest mismatch")
        parameters[tool_id] = (binding.platt_a, binding.platt_b)
    return parameters


def _verify_configured_tools(
    settings: object,
    artifact: OCSRCalibrationArtifact,
    roster: VisionProductionRoster,
    model_hashes: dict[str, str],
) -> dict[str, tuple[float, float]]:
    configured_tools = _configured_tool_ids(settings)
    _verify_tool_allowlist(configured_tools, roster)
    artifact_tools = {tool.tool_id: tool for tool in artifact.tools}
    if set(artifact_tools) != set(configured_tools):
        raise CalibrationContractError(
            "calibration artifact tool set does not match the live OCSR tool set"
        )
    expected_container_digests = _load_expected_container_digests(
        settings,
        configured_tools,
        roster,
    )
    return _bind_tool_parameters(
        configured_tools,
        artifact_tools,
        expected_container_digests,
        roster,
        model_hashes,
    )


def _verify_calibration_scope(settings: object, artifact: OCSRCalibrationArtifact) -> None:
    allowlist = {
        str(value).strip().upper()
        for value in (getattr(settings, "drawing_analysis_jurisdictions", ()) or ())
        if str(value).strip()
    }
    if not allowlist or not allowlist.issubset(set(artifact.jurisdictions)):
        raise CalibrationContractError("calibration jurisdiction scope mismatch")
    if artifact.exactness_definition != EXACTNESS_DEFINITION:
        raise CalibrationContractError("calibration exactness definition mismatch")
    if artifact.domain != CALIBRATION_DOMAIN:
        raise CalibrationContractError("calibration domain mismatch")

    configured_threshold = getattr(settings, "drawing_cascade_min_resolved_conf", None)
    if (
        isinstance(configured_threshold, bool)
        or not isinstance(configured_threshold, int | float)
        or not math.isclose(
            float(configured_threshold),
            artifact.minimum_resolved_confidence,
            rel_tol=0,
            abs_tol=1e-12,
        )
    ):
        raise CalibrationContractError("calibration decision threshold mismatch")


def require_verified_calibration(
    settings: object,
    *,
    now: datetime | None = None,
) -> VerifiedCalibration:
    """Load and verify the exact calibration artifact configured for live use."""
    artifact, expected_artifact_sha = _load_pinned_artifact(settings)
    _verify_anti_replay(settings, artifact)
    _verify_artifact_signature(settings, artifact)
    _verify_artifact_lifetime_and_corpus(settings, artifact, now=now)
    roster, model_hashes = _load_calibration_runtime(settings, artifact)
    parameters = _verify_configured_tools(settings, artifact, roster, model_hashes)
    _verify_calibration_scope(settings, artifact)

    return VerifiedCalibration(
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        revocation_epoch=artifact.revocation_epoch,
        artifact_sha256=expected_artifact_sha,
        runtime_roster_sha256=artifact.runtime_roster_sha256,
        ml_bom_sha256=artifact.ml_bom_sha256,
        minimum_resolved_confidence=artifact.minimum_resolved_confidence,
        parameters=parameters,
    )


def calibration_is_verified(settings: object) -> bool:
    """Return false for any missing, stale, malformed, or mismatched artifact."""
    try:
        require_verified_calibration(settings)
    except CalibrationContractError:
        return False
    return True
