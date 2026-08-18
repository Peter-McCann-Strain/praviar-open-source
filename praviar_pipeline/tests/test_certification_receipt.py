from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from praviar_pipeline.certification_receipt import (
    PAYLOAD_TYPE,
    canonical_json_bytes,
    verify_certification_receipt,
)
from praviar_pipeline.certification_subject import (
    build_runtime_certification_bundle,
    compute_certification_bundle_digests,
)
from praviar_pipeline.certification_subject import (
    main as emit_certification_subject,
)

PIPELINE_SHA = "a" * 40
SOURCE_TREE_SHA = "b" * 64
KEY_ID = "release-key-2026-q3"
VERIFIER_ID = "praviar-release-gate/prod/v1"
PRIVATE_KEY = Ed25519PrivateKey.generate()
PUBLIC_KEY_B64 = base64.b64encode(
    PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode()
BUNDLE_DIGESTS = compute_certification_bundle_digests()


def test_runtime_bundle_subject_is_closed_and_derived_from_image_files() -> None:
    assert build_runtime_certification_bundle(PIPELINE_SHA) == {
        "schema_version": "praviar.runtime-certification-bundle.v1",
        "git_sha": PIPELINE_SHA,
        **BUNDLE_DIGESTS,
    }


def test_runtime_bundle_emitter_writes_canonical_new_file(tmp_path) -> None:
    output = tmp_path / "runtime-subject.json"

    assert emit_certification_subject(["--git-sha", PIPELINE_SHA, "--output", str(output)]) == 0
    raw = output.read_bytes()
    assert raw == canonical_json_bytes(json.loads(raw))

    try:
        emit_certification_subject(["--git-sha", PIPELINE_SHA, "--output", str(output)])
    except FileExistsError:
        pass
    else:
        raise AssertionError("runtime subject emitter overwrote an existing artifact")


def _payload() -> dict:
    return {
        "schema_version": "praviar.release-certification.v2",
        "receipt_id": "release-2026-07-13",
        "issuer": {"verifier_id": VERIFIER_ID, "key_id": KEY_ID},
        "subject": {
            "git_sha": PIPELINE_SHA,
            "source_tree_sha256": SOURCE_TREE_SHA,
            "api_oci_image_digest": "sha256:" + "c" * 64,
            "worker_oci_image_digest": "sha256:" + "d" * 64,
            **BUNDLE_DIGESTS,
        },
        "gate": {
            "result": "PASSED",
            "gate_schema_version": 2,
            "threshold_policy_sha256": "4" * 64,
            "benchmark_aggregate_sha256": "5" * 64,
            "benchmark_manifest_sha256": "6" * 64,
            "canonical_attempt_ledger_sha256": "7" * 64,
            "adjudication_manifest_sha256": "8" * 64,
            "gate_run_id": "benchmark-run-2026-07-13",
        },
        "certified_lanes": [
            {
                "lane_id": "us-small-molecule-compound-adaptive-v1",
                "matter_type": "small_molecule",
                "asset_class": "compound",
                "jurisdiction": "US",
                "execution_profile": "adaptive",
                "decision_kind": "positive_clearance",
                "required_record_components_sha256": "9" * 64,
                "benchmark_population_sha256": "a" * 64,
                "eligible_independent_case_count": 598,
                "eligible_predicted_clear_case_count": 299,
                "eligible_non_clear_case_count": 299,
                "observed_false_clear_count": 0,
                "false_clear_confidence_level": "0.95",
                "false_clear_upper_bound": "0.01",
            }
        ],
        "validity": {
            "issued_at": "2026-07-13T00:00:00Z",
            "not_before": "2026-07-13T00:00:00Z",
            "expires_at": "2026-08-12T00:00:00Z",
            "revocation_namespace": "praviar-release-certification-prod",
        },
    }


def _pae(payload: bytes) -> bytes:
    payload_type = PAYLOAD_TYPE.encode()
    return (
        b"DSSEv1 "
        + str(len(payload_type)).encode()
        + b" "
        + payload_type
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def _settings(payload: dict | None = None) -> SimpleNamespace:
    signed_payload = canonical_json_bytes(payload or _payload())
    signature = PRIVATE_KEY.sign(_pae(signed_payload))
    envelope = {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(signed_payload).decode(),
        "signatures": [{"keyid": KEY_ID, "sig": base64.b64encode(signature).decode()}],
    }
    subject = (payload or _payload())["subject"]
    return SimpleNamespace(
        certification_release_receipt_json=json.dumps(envelope),
        certification_release_public_key=SecretStr(PUBLIC_KEY_B64),
        certification_release_key_id=KEY_ID,
        certification_release_verifier_id=VERIFIER_ID,
        certification_api_oci_image_digest=subject["api_oci_image_digest"],
        certification_worker_oci_image_digest=subject["worker_oci_image_digest"],
        certification_runtime_policy_sha256=subject["runtime_policy_sha256"],
        certification_evidence_policy_sha256=subject["evidence_policy_sha256"],
        certification_prompt_bundle_sha256=subject["prompt_bundle_sha256"],
        certification_model_bundle_sha256=subject["model_bundle_sha256"],
        certification_tool_definition_bundle_sha256=subject["tool_definition_bundle_sha256"],
        certification_collector_bundle_sha256=subject["collector_bundle_sha256"],
        certification_revoked_receipt_ids=[],
    )


def _verify(settings: object):
    return verify_certification_receipt(
        settings,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        pipeline_git_sha=PIPELINE_SHA,
        source_tree_sha256=SOURCE_TREE_SHA,
    )


def test_valid_receipt_binds_atomic_lane_to_exact_runtime_source() -> None:
    result = _verify(_settings())

    assert result.verified is True
    assert result.failures == ()
    assert result.receipt_id == "release-2026-07-13"
    assert result.issuer_verifier_id == VERIFIER_ID
    assert result.policy is not None
    assert result.certified_lanes[0].lane_id == ("us-small-molecule-compound-adaptive-v1")


def test_missing_receipt_and_public_trust_root_fail_closed() -> None:
    result = _verify(SimpleNamespace())

    assert result.verified is False
    assert result.failures == (
        "certification_release_receipt_missing",
        "certification_release_trust_root_missing",
    )


def test_payload_tampering_breaks_the_dsse_signature() -> None:
    settings = _settings()
    envelope = json.loads(settings.certification_release_receipt_json)
    payload = json.loads(base64.b64decode(envelope["payload"]))
    payload["certified_lanes"][0]["jurisdiction"] = "JP"
    envelope["payload"] = base64.b64encode(canonical_json_bytes(payload)).decode()
    settings.certification_release_receipt_json = json.dumps(envelope)

    result = _verify(settings)

    assert result.verified is False
    assert result.failures == ("certification_release_receipt_signature_mismatch",)


def test_receipt_for_another_revision_or_source_tree_fails_closed() -> None:
    revision_result = verify_certification_receipt(
        _settings(),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        pipeline_git_sha="e" * 40,
        source_tree_sha256=SOURCE_TREE_SHA,
    )
    source_result = verify_certification_receipt(
        _settings(),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        pipeline_git_sha=PIPELINE_SHA,
        source_tree_sha256="f" * 64,
    )

    assert "certification_release_pipeline_sha_mismatch" in revision_result.failures
    assert "certification_release_source_tree_sha_mismatch" in source_result.failures


def test_signed_historical_receipt_survives_runtime_rollover() -> None:
    result = verify_certification_receipt(
        _settings(),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        pipeline_git_sha="e" * 40,
        source_tree_sha256="f" * 64,
        subject_verification="signed_receipt",
    )

    assert result.verified is True
    assert result.pipeline_git_sha == PIPELINE_SHA
    assert result.source_tree_sha256 == SOURCE_TREE_SHA


def test_generation_rejects_receipt_from_previous_runtime() -> None:
    settings = _settings()
    settings.certification_api_oci_image_digest = "sha256:" + "0" * 64
    settings.certification_worker_oci_image_digest = "sha256:" + "1" * 64
    result = verify_certification_receipt(
        settings,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        pipeline_git_sha="e" * 40,
        source_tree_sha256="f" * 64,
    )

    assert result.verified is False
    assert "certification_release_pipeline_sha_mismatch" in result.failures
    assert "certification_release_source_tree_sha_mismatch" in result.failures
    assert "certification_release_api_oci_image_digest_mismatch" in result.failures
    assert "certification_release_worker_oci_image_digest_mismatch" in result.failures


def test_signed_historical_mode_still_rejects_malformed_subject() -> None:
    payload = _payload()
    payload["subject"]["git_sha"] = "not-a-git-sha"
    result = verify_certification_receipt(
        _settings(payload),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
        subject_verification="signed_receipt",
    )

    assert result.verified is False
    assert "certification_release_subject_pipeline_sha_invalid" in result.failures


def test_receipt_cannot_replace_runtime_bundle_identity_with_matching_config_claim() -> None:
    payload = _payload()
    payload["subject"]["prompt_bundle_sha256"] = "0" * 64

    result = _verify(_settings(payload))

    assert "certification_release_prompt_bundle_sha256_runtime_mismatch" in result.failures


def test_expired_or_revoked_receipt_fails_closed() -> None:
    expired = verify_certification_receipt(
        _settings(),
        now=datetime(2026, 8, 12, tzinfo=UTC),
        pipeline_git_sha=PIPELINE_SHA,
        source_tree_sha256=SOURCE_TREE_SHA,
    )
    revoked_settings = _settings()
    revoked_settings.certification_revoked_receipt_ids = ["release-2026-07-13"]
    revoked = _verify(revoked_settings)

    assert "certification_release_receipt_expired" in expired.failures
    assert "certification_release_receipt_revoked" in revoked.failures
