from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praviar_pipeline.vision_execution_contract import (
    VisionExecutionContext,
    VisionExecutionContractError,
    VisionExecutionSigner,
    VisionExecutionVerificationKeyRing,
    VisionModelIdentity,
    VisionOCSROutput,
    VisionRuntimeBinding,
    build_vision_output,
    ingest_vision_output,
    prepare_vision_dispatch,
    sign_vision_execution_receipt,
    verify_vision_dispatch,
)

_NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
_INPUT = b"synthetic-private-patent-crop"


class _ReplayGuard:
    def __init__(self) -> None:
        self.consumed: set[UUID] = set()

    def consume_once(self, receipt_id: UUID) -> bool:
        if receipt_id in self.consumed:
            return False
        self.consumed.add(receipt_id)
        return True


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _context() -> VisionExecutionContext:
    return VisionExecutionContext(
        org_id=uuid4(),
        analysis_id=uuid4(),
        execution_id=uuid4(),
        execution_attempt=3,
        execution_fence_token=_digest("execution-fence-3"),
    )


def _runtime() -> VisionRuntimeBinding:
    return VisionRuntimeBinding(
        roster_sha256=_digest("roster"),
        ml_bom_sha256=_digest("ml-bom"),
        calibration_artifact_id="calibration-v7",
        calibration_artifact_revision=7,
        calibration_artifact_sha256=_digest("calibration-artifact-v7"),
        tool_id="molscribe",
        models=(
            VisionModelIdentity(
                model_id="molscribe/swin_base_char_aux_1m680k",
                sha256=_digest("molscribe-model"),
            ),
        ),
        container_image_digest=f"sha256:{_digest('molscribe-container')}",
    )


def _signer_and_keyring() -> tuple[
    VisionExecutionSigner,
    VisionExecutionVerificationKeyRing,
]:
    private_key = Ed25519PrivateKey.generate()
    signer = VisionExecutionSigner(key_id="vision-worker-test-v1", private_key=private_key)
    keyring = VisionExecutionVerificationKeyRing(keys={signer.key_id: private_key.public_key()})
    return signer, keyring


def _request():
    context = _context()
    runtime = _runtime()
    request = prepare_vision_dispatch(
        context=context,
        input_bytes=_INPUT,
        patent_id="US1234567A1",
        page_number=4,
        structure_index=2,
        content_type="image/png",
        runtime=runtime,
        now=_NOW,
    )
    return request, context, runtime


def test_dispatch_is_shadow_only_and_rejects_tenant_fence_or_input_mismatch() -> None:
    request, context, runtime = _request()

    assert request.rollout_state == "shadow"
    assert request.influence_permitted is False
    verify_vision_dispatch(
        request,
        input_bytes=_INPUT,
        expected_context=context,
        current_runtime=runtime,
        now=_NOW + timedelta(seconds=1),
    )

    wrong_tenant = context.model_copy(update={"org_id": uuid4()})
    with pytest.raises(VisionExecutionContractError, match="tenant or execution fence"):
        verify_vision_dispatch(
            request,
            input_bytes=_INPUT,
            expected_context=wrong_tenant,
            current_runtime=runtime,
            now=_NOW + timedelta(seconds=1),
        )

    stale_fence = context.model_copy(update={"execution_fence_token": _digest("execution-fence-2")})
    with pytest.raises(VisionExecutionContractError, match="tenant or execution fence"):
        verify_vision_dispatch(
            request,
            input_bytes=_INPUT,
            expected_context=stale_fence,
            current_runtime=runtime,
            now=_NOW + timedelta(seconds=1),
        )

    with pytest.raises(VisionExecutionContractError, match="input digest mismatch"):
        verify_vision_dispatch(
            request,
            input_bytes=b"substituted-tenant-image",
            expected_context=context,
            current_runtime=runtime,
            now=_NOW + timedelta(seconds=1),
        )


def test_dispatch_rejects_stale_window_or_runtime_calibration_rollback() -> None:
    request, context, runtime = _request()
    rolled_back_runtime = runtime.model_copy(
        update={
            "calibration_artifact_id": "calibration-v6",
            "calibration_artifact_revision": 6,
            "calibration_artifact_sha256": _digest("calibration-artifact-v6"),
        }
    )

    with pytest.raises(VisionExecutionContractError, match="runtime binding mismatch"):
        verify_vision_dispatch(
            request,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=rolled_back_runtime,
            now=_NOW + timedelta(seconds=1),
        )

    with pytest.raises(VisionExecutionContractError, match="validity window"):
        verify_vision_dispatch(
            request,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            now=request.expires_at,
        )


def test_signed_output_ingests_exactly_once() -> None:
    request, context, runtime = _request()
    signer, keyring = _signer_and_keyring()
    output = build_vision_output(
        request,
        payload=VisionOCSROutput(
            status="succeeded",
            canonical_smiles="CCO",
            confidence=0.98,
            valid=True,
        ),
        completed_at=_NOW + timedelta(seconds=2),
    )
    receipt = sign_vision_execution_receipt(
        request,
        output,
        signer=signer,
        issued_at=_NOW + timedelta(seconds=3),
    )
    replay_guard = _ReplayGuard()

    payload = ingest_vision_output(
        request,
        output,
        receipt,
        input_bytes=_INPUT,
        expected_context=context,
        current_runtime=runtime,
        keyring=keyring,
        replay_guard=replay_guard,
        now=_NOW + timedelta(seconds=4),
    )

    assert payload.canonical_smiles == "CCO"
    assert payload.valid is True
    with pytest.raises(VisionExecutionContractError, match="replay detected"):
        ingest_vision_output(
            request,
            output,
            receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=replay_guard,
            now=_NOW + timedelta(seconds=5),
        )


def test_ingestion_rejects_cross_tenant_output_and_signature_tampering() -> None:
    request, context, runtime = _request()
    signer, keyring = _signer_and_keyring()
    output = build_vision_output(
        request,
        payload=VisionOCSROutput(
            status="abstained",
            error_code="below_verified_threshold",
        ),
        completed_at=_NOW + timedelta(seconds=2),
    )
    receipt = sign_vision_execution_receipt(
        request,
        output,
        signer=signer,
        issued_at=_NOW + timedelta(seconds=3),
    )

    cross_tenant_output = output.model_copy(
        update={
            "context": context.model_copy(update={"org_id": uuid4()}),
        }
    )
    with pytest.raises(VisionExecutionContractError, match="signer refused"):
        sign_vision_execution_receipt(
            request,
            cross_tenant_output,
            signer=signer,
            issued_at=_NOW + timedelta(seconds=3),
        )
    with pytest.raises(VisionExecutionContractError, match="output identity binding"):
        ingest_vision_output(
            request,
            cross_tenant_output,
            receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=_ReplayGuard(),
            now=_NOW + timedelta(seconds=4),
        )

    tampered_receipt = receipt.model_copy(
        update={"signature_b64": base64.b64encode(b"\x00" * 64).decode()}
    )
    with pytest.raises(VisionExecutionContractError, match="signature mismatch"):
        ingest_vision_output(
            request,
            output,
            tampered_receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=_ReplayGuard(),
            now=_NOW + timedelta(seconds=4),
        )


def test_ingestion_rejects_revoked_receipt_before_consumption() -> None:
    request, context, runtime = _request()
    signer, keyring = _signer_and_keyring()
    output = build_vision_output(
        request,
        payload=VisionOCSROutput(
            status="failed",
            error_code="worker_failure",
        ),
        completed_at=_NOW + timedelta(seconds=2),
    )
    receipt = sign_vision_execution_receipt(
        request,
        output,
        signer=signer,
        issued_at=_NOW + timedelta(seconds=3),
    )
    replay_guard = _ReplayGuard()

    with pytest.raises(VisionExecutionContractError, match="receipt is revoked"):
        ingest_vision_output(
            request,
            output,
            receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=replay_guard,
            revoked_receipt_ids=frozenset({receipt.receipt_id}),
            now=_NOW + timedelta(seconds=4),
        )
    assert replay_guard.consumed == set()


def test_ingestion_rejects_future_dated_output_and_receipt() -> None:
    request, context, runtime = _request()
    signer, keyring = _signer_and_keyring()
    output = build_vision_output(
        request,
        payload=VisionOCSROutput(
            status="abstained",
            error_code="below_verified_threshold",
        ),
        completed_at=_NOW + timedelta(minutes=1),
    )
    receipt = sign_vision_execution_receipt(
        request,
        output,
        signer=signer,
        issued_at=_NOW + timedelta(minutes=1, seconds=1),
    )

    with pytest.raises(VisionExecutionContractError, match="output timestamp"):
        ingest_vision_output(
            request,
            output,
            receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=_ReplayGuard(),
            now=_NOW,
        )

    completed = output.model_copy(update={"completed_at": _NOW})
    future_receipt = sign_vision_execution_receipt(
        request,
        completed,
        signer=signer,
        issued_at=_NOW + timedelta(minutes=1),
    )
    with pytest.raises(VisionExecutionContractError, match="receipt timestamp"):
        ingest_vision_output(
            request,
            completed,
            future_receipt,
            input_bytes=_INPUT,
            expected_context=context,
            current_runtime=runtime,
            keyring=keyring,
            replay_guard=_ReplayGuard(),
            now=_NOW,
        )
