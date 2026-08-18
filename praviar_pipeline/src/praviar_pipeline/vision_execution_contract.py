"""Tenant- and execution-fenced contracts for shadow vision workers.

This module is a production scaffold, not a rollout switch. Every request is
explicitly shadow-only and non-influential. A future remote worker boundary
must verify dispatch bytes before execution and must return an Ed25519-signed
receipt that is atomically consumed once before result ingestion.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping

VISION_EXECUTION_DOMAIN = "praviar:vision-execution-receipt:v1"
MAX_DISPATCH_VALIDITY = timedelta(minutes=15)
MAX_INGEST_CLOCK_SKEW = timedelta(seconds=5)
MAX_INPUT_BYTES = 100 * 1024 * 1024
SHA256_PATTERN = r"^[0-9a-f]{64}$"
OCI_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
KEY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class VisionExecutionContractError(RuntimeError):
    """Raised when a vision dispatch or result crosses a trust boundary."""


class VisionExecutionContext(BaseModel):
    """Tenant and optimistic-concurrency fence for one execution attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    org_id: UUID
    analysis_id: UUID
    execution_id: UUID
    execution_attempt: int = Field(ge=1)
    execution_fence_token: str = Field(pattern=SHA256_PATTERN)


class VisionModelIdentity(BaseModel):
    """One exact model artifact used by the selected worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=SHA256_PATTERN)


class VisionRuntimeBinding(BaseModel):
    """Immutable release identities that the worker must actually execute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roster_sha256: str = Field(pattern=SHA256_PATTERN)
    ml_bom_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_artifact_id: str = Field(min_length=1, max_length=256)
    calibration_artifact_revision: int = Field(ge=1)
    calibration_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    tool_id: str = Field(min_length=1, max_length=128)
    models: tuple[VisionModelIdentity, ...] = Field(min_length=1)
    container_image_digest: str = Field(pattern=OCI_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_models(self) -> VisionRuntimeBinding:
        model_ids = [model.model_id for model in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("vision runtime model IDs must be unique")
        return self


class VisionDispatchRequest(BaseModel):
    """Content-addressed request sent to an isolated shadow worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.vision-dispatch.v1"] = "praviar.vision-dispatch.v1"
    request_id: UUID
    dispatch_nonce: str = Field(pattern=SHA256_PATTERN)
    context: VisionExecutionContext
    rollout_state: Literal["shadow"] = "shadow"
    influence_permitted: Literal[False] = False
    created_at: datetime
    expires_at: datetime
    patent_id: str = Field(min_length=1, max_length=128)
    page_number: int = Field(ge=1)
    structure_index: int = Field(ge=0)
    content_type: Literal["image/png", "image/tiff", "image/jpeg"]
    input_sha256: str = Field(pattern=SHA256_PATTERN)
    input_size_bytes: int = Field(ge=1, le=MAX_INPUT_BYTES)
    runtime: VisionRuntimeBinding

    @model_validator(mode="after")
    def validate_window(self) -> VisionDispatchRequest:
        _require_aware(self.created_at, label="dispatch created_at")
        _require_aware(self.expires_at, label="dispatch expires_at")
        validity = self.expires_at.astimezone(UTC) - self.created_at.astimezone(UTC)
        if validity <= timedelta(0) or validity > MAX_DISPATCH_VALIDITY:
            raise ValueError("vision dispatch validity window is invalid")
        return self


class VisionOCSROutput(BaseModel):
    """Strict result payload; failures and abstentions cannot look successful."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["succeeded", "abstained", "failed"]
    canonical_smiles: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    valid: bool = False
    error_code: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_status(self) -> VisionOCSROutput:
        if not math.isfinite(self.confidence):
            raise ValueError("vision output confidence must be finite")
        if self.status == "succeeded":
            if not self.valid or not self.canonical_smiles or self.error_code:
                raise ValueError("successful vision output must be valid and error-free")
        elif self.valid or self.canonical_smiles or not self.error_code:
            raise ValueError("non-success vision output must abstain without a structure")
        return self


class VisionExecutionOutput(BaseModel):
    """Worker result with every confused-deputy boundary repeated explicitly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.vision-output.v1"] = "praviar.vision-output.v1"
    request_id: UUID
    dispatch_nonce: str = Field(pattern=SHA256_PATTERN)
    context: VisionExecutionContext
    influence_permitted: Literal[False] = False
    input_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_at: datetime
    payload: VisionOCSROutput

    @model_validator(mode="after")
    def validate_completed_at(self) -> VisionExecutionOutput:
        _require_aware(self.completed_at, label="vision output completed_at")
        return self


class VisionExecutionReceipt(BaseModel):
    """Ed25519 receipt binding exact request and output envelopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.vision-execution-receipt.v1"] = (
        "praviar.vision-execution-receipt.v1"
    )
    receipt_id: UUID
    algorithm: Literal["Ed25519"] = "Ed25519"
    key_id: str = Field(pattern=KEY_ID_PATTERN)
    org_id: UUID
    analysis_id: UUID
    execution_id: UUID
    execution_attempt: int = Field(ge=1)
    execution_fence_token: str = Field(pattern=SHA256_PATTERN)
    request_id: UUID
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    output_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_artifact_id: str
    calibration_artifact_revision: int = Field(ge=1)
    calibration_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    issued_at: datetime
    signature_b64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_issued_at(self) -> VisionExecutionReceipt:
        _require_aware(self.issued_at, label="vision receipt issued_at")
        return self


class VisionReceiptReplayGuard(Protocol):
    """Atomic durable replay ledger required by result ingestion."""

    def consume_once(self, receipt_id: UUID) -> bool:
        """Return true exactly once for a previously unseen receipt ID."""


@dataclass(frozen=True)
class VisionExecutionSigner:
    """Worker-only Ed25519 signing identity."""

    key_id: str
    private_key: Ed25519PrivateKey  # gitleaks:allow -- type annotation, never key material

    def __post_init__(self) -> None:
        if not _valid_key_id(self.key_id):
            raise ValueError("vision execution signing key ID is invalid")

    @classmethod
    def from_base64(cls, *, key_id: str, private_key_b64: str) -> VisionExecutionSigner:
        key_bytes = _decode_base64(private_key_b64, expected_bytes=32, label="private key")
        return cls(
            key_id=key_id,
            private_key=Ed25519PrivateKey.from_private_bytes(key_bytes),
        )


@dataclass(frozen=True)
class VisionExecutionVerificationKeyRing:
    """Ingestion-side public keys retained across controlled rotation."""

    keys: Mapping[str, Ed25519PublicKey]

    def __post_init__(self) -> None:
        if not self.keys or any(not _valid_key_id(key_id) for key_id in self.keys):
            raise ValueError("vision execution verification key ring is invalid")

    @classmethod
    def from_json(cls, raw: str) -> VisionExecutionVerificationKeyRing:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("vision execution verification key ring is invalid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "keys"}:
            raise ValueError("vision execution verification key ring schema is invalid")
        if payload["schema_version"] != "praviar.vision-execution-keyring.v1":
            raise ValueError("vision execution verification key ring version is invalid")
        raw_keys = payload["keys"]
        if not isinstance(raw_keys, dict):
            raise ValueError("vision execution verification keys are invalid")
        return cls(
            keys={
                str(key_id): Ed25519PublicKey.from_public_bytes(
                    _decode_base64(value, expected_bytes=32, label="public key")
                )
                for key_id, value in raw_keys.items()
            }
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": "praviar.vision-execution-keyring.v1",
                "keys": {
                    key_id: base64.b64encode(
                        key.public_bytes(
                            encoding=serialization.Encoding.Raw,
                            format=serialization.PublicFormat.Raw,
                        )
                    ).decode()
                    for key_id, key in self.keys.items()
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def _require_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _canonical_json_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _runtime_sha256(runtime: VisionRuntimeBinding) -> str:
    return _sha256(runtime)


def _valid_key_id(value: object) -> bool:
    return re.fullmatch(KEY_ID_PATTERN, str(value or "")) is not None


def _decode_base64(value: object, *, expected_bytes: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(str(value or ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"vision execution {label} is not canonical base64") from exc
    if len(decoded) != expected_bytes:
        raise ValueError(f"vision execution {label} has an invalid length")
    return decoded


def prepare_vision_dispatch(
    *,
    context: VisionExecutionContext,
    input_bytes: bytes,
    patent_id: str,
    page_number: int,
    structure_index: int,
    content_type: Literal["image/png", "image/tiff", "image/jpeg"],
    runtime: VisionRuntimeBinding,
    now: datetime | None = None,
    validity: timedelta = timedelta(minutes=5),
) -> VisionDispatchRequest:
    """Create a shadow-only, content-addressed request envelope."""
    if not input_bytes or len(input_bytes) > MAX_INPUT_BYTES:
        raise VisionExecutionContractError("vision dispatch input size is invalid")
    created_at = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        return VisionDispatchRequest(
            request_id=uuid4(),
            dispatch_nonce=secrets.token_hex(32),
            context=context,
            created_at=created_at,
            expires_at=created_at + validity,
            patent_id=patent_id,
            page_number=page_number,
            structure_index=structure_index,
            content_type=content_type,
            input_sha256=hashlib.sha256(input_bytes).hexdigest(),
            input_size_bytes=len(input_bytes),
            runtime=runtime,
        )
    except ValueError as exc:
        raise VisionExecutionContractError("vision dispatch contract is invalid") from exc


def verify_vision_dispatch(
    request: VisionDispatchRequest,
    *,
    input_bytes: bytes,
    expected_context: VisionExecutionContext,
    current_runtime: VisionRuntimeBinding,
    now: datetime | None = None,
) -> None:
    """Fail closed before a worker sees tenant-bound image bytes."""
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if request.context != expected_context:
        raise VisionExecutionContractError("vision dispatch tenant or execution fence mismatch")
    if request.runtime != current_runtime:
        raise VisionExecutionContractError("vision dispatch runtime binding mismatch")
    if checked_at < request.created_at.astimezone(
        UTC
    ) or checked_at >= request.expires_at.astimezone(UTC):
        raise VisionExecutionContractError("vision dispatch is outside its validity window")
    if (
        request.input_size_bytes != len(input_bytes)
        or request.input_sha256 != hashlib.sha256(input_bytes).hexdigest()
    ):
        raise VisionExecutionContractError("vision dispatch input digest mismatch")


def build_vision_output(
    request: VisionDispatchRequest,
    *,
    payload: VisionOCSROutput,
    completed_at: datetime | None = None,
) -> VisionExecutionOutput:
    """Build a result envelope repeating every dispatch security boundary."""
    timestamp = (completed_at or datetime.now(UTC)).astimezone(UTC)
    if timestamp < request.created_at.astimezone(UTC) or timestamp >= request.expires_at.astimezone(
        UTC
    ):
        raise VisionExecutionContractError("vision output is outside the dispatch window")
    return VisionExecutionOutput(
        request_id=request.request_id,
        dispatch_nonce=request.dispatch_nonce,
        context=request.context,
        input_sha256=request.input_sha256,
        runtime_sha256=_runtime_sha256(request.runtime),
        completed_at=timestamp,
        payload=payload,
    )


def _unsigned_receipt(receipt: VisionExecutionReceipt) -> dict[str, object]:
    return receipt.model_dump(mode="json", exclude={"signature_b64"})


def _receipt_message(receipt: VisionExecutionReceipt) -> bytes:
    return _canonical_json_bytes(
        {
            "domain": VISION_EXECUTION_DOMAIN,
            "receipt": _unsigned_receipt(receipt),
        }
    )


def sign_vision_execution_receipt(
    request: VisionDispatchRequest,
    output: VisionExecutionOutput,
    *,
    signer: VisionExecutionSigner,
    issued_at: datetime | None = None,
) -> VisionExecutionReceipt:
    """Sign exact tenant, fence, request, output, and calibration identities."""
    timestamp = (issued_at or datetime.now(UTC)).astimezone(UTC)
    expected_output_identity = (
        request.request_id,
        request.dispatch_nonce,
        request.context,
        request.input_sha256,
        _runtime_sha256(request.runtime),
    )
    actual_output_identity = (
        output.request_id,
        output.dispatch_nonce,
        output.context,
        output.input_sha256,
        output.runtime_sha256,
    )
    if actual_output_identity != expected_output_identity:
        raise VisionExecutionContractError("vision signer refused an output identity mismatch")
    if timestamp < output.completed_at.astimezone(
        UTC
    ) or timestamp >= request.expires_at.astimezone(UTC):
        raise VisionExecutionContractError("vision signer refused an invalid receipt timestamp")
    unsigned = VisionExecutionReceipt(
        receipt_id=uuid4(),
        key_id=signer.key_id,
        org_id=request.context.org_id,
        analysis_id=request.context.analysis_id,
        execution_id=request.context.execution_id,
        execution_attempt=request.context.execution_attempt,
        execution_fence_token=request.context.execution_fence_token,
        request_id=request.request_id,
        request_sha256=_sha256(request),
        output_sha256=_sha256(output),
        calibration_artifact_id=request.runtime.calibration_artifact_id,
        calibration_artifact_revision=request.runtime.calibration_artifact_revision,
        calibration_artifact_sha256=request.runtime.calibration_artifact_sha256,
        issued_at=timestamp,
        signature_b64=base64.b64encode(b"\x00" * 64).decode(),
    )
    signature = signer.private_key.sign(_receipt_message(unsigned))
    return unsigned.model_copy(update={"signature_b64": base64.b64encode(signature).decode()})


def ingest_vision_output(
    request: VisionDispatchRequest,
    output: VisionExecutionOutput,
    receipt: VisionExecutionReceipt,
    *,
    input_bytes: bytes,
    expected_context: VisionExecutionContext,
    current_runtime: VisionRuntimeBinding,
    keyring: VisionExecutionVerificationKeyRing,
    replay_guard: VisionReceiptReplayGuard,
    revoked_receipt_ids: frozenset[UUID] = frozenset(),
    now: datetime | None = None,
) -> VisionOCSROutput:
    """Verify and atomically consume one result receipt before ingestion."""
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    verify_vision_dispatch(
        request,
        input_bytes=input_bytes,
        expected_context=expected_context,
        current_runtime=current_runtime,
        now=checked_at,
    )
    expected_output_identity = (
        request.request_id,
        request.dispatch_nonce,
        request.context,
        request.input_sha256,
        _runtime_sha256(request.runtime),
    )
    actual_output_identity = (
        output.request_id,
        output.dispatch_nonce,
        output.context,
        output.input_sha256,
        output.runtime_sha256,
    )
    if actual_output_identity != expected_output_identity:
        raise VisionExecutionContractError("vision output identity binding mismatch")
    if (
        output.completed_at.astimezone(UTC) < request.created_at.astimezone(UTC)
        or output.completed_at.astimezone(UTC) >= request.expires_at.astimezone(UTC)
        or output.completed_at.astimezone(UTC) > checked_at + MAX_INGEST_CLOCK_SKEW
    ):
        raise VisionExecutionContractError("vision output timestamp is invalid")

    expected_receipt_identity = (
        request.context.org_id,
        request.context.analysis_id,
        request.context.execution_id,
        request.context.execution_attempt,
        request.context.execution_fence_token,
        request.request_id,
        _sha256(request),
        _sha256(output),
        request.runtime.calibration_artifact_id,
        request.runtime.calibration_artifact_revision,
        request.runtime.calibration_artifact_sha256,
    )
    actual_receipt_identity = (
        receipt.org_id,
        receipt.analysis_id,
        receipt.execution_id,
        receipt.execution_attempt,
        receipt.execution_fence_token,
        receipt.request_id,
        receipt.request_sha256,
        receipt.output_sha256,
        receipt.calibration_artifact_id,
        receipt.calibration_artifact_revision,
        receipt.calibration_artifact_sha256,
    )
    if actual_receipt_identity != expected_receipt_identity:
        raise VisionExecutionContractError("vision receipt identity binding mismatch")
    if (
        receipt.issued_at.astimezone(UTC) < output.completed_at.astimezone(UTC)
        or receipt.issued_at.astimezone(UTC) >= request.expires_at.astimezone(UTC)
        or receipt.issued_at.astimezone(UTC) > checked_at + MAX_INGEST_CLOCK_SKEW
    ):
        raise VisionExecutionContractError("vision receipt timestamp is invalid")
    if receipt.receipt_id in revoked_receipt_ids:
        raise VisionExecutionContractError("vision execution receipt is revoked")
    verification_key = keyring.keys.get(receipt.key_id)
    if verification_key is None:
        raise VisionExecutionContractError("vision execution receipt key is untrusted")
    try:
        signature = _decode_base64(
            receipt.signature_b64,
            expected_bytes=64,
            label="receipt signature",
        )
        verification_key.verify(signature, _receipt_message(receipt))
    except (InvalidSignature, ValueError):
        raise VisionExecutionContractError("vision execution receipt signature mismatch") from None
    if not replay_guard.consume_once(receipt.receipt_id):
        raise VisionExecutionContractError("vision execution receipt replay detected")
    return output.payload
