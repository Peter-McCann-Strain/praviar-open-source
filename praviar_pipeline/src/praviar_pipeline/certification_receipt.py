"""Public-key verification for release-qualified direct-clearance lanes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from praviar_pipeline.certification_policy import (
    CertificationPolicySnapshot,
    normalize_jurisdiction,
    normalize_matter_type,
    normalize_modality,
)
from praviar_pipeline.certification_subject import compute_certification_bundle_digests
from praviar_pipeline.manifest import compute_source_tree_provenance, get_pipeline_version

PAYLOAD_TYPE = "application/vnd.praviar.release-certification.v2+json"
SubjectVerificationMode = Literal["current_runtime", "signed_receipt"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENVELOPE_KEYS = {"payloadType", "payload", "signatures"}
_PAYLOAD_KEYS = {
    "schema_version",
    "receipt_id",
    "issuer",
    "subject",
    "gate",
    "certified_lanes",
    "validity",
}
_ISSUER_KEYS = {"verifier_id", "key_id"}
_SUBJECT_KEYS = {
    "git_sha",
    "source_tree_sha256",
    "api_oci_image_digest",
    "worker_oci_image_digest",
    "runtime_policy_sha256",
    "evidence_policy_sha256",
    "prompt_bundle_sha256",
    "model_bundle_sha256",
    "tool_definition_bundle_sha256",
    "collector_bundle_sha256",
}
_GATE_KEYS = {
    "result",
    "gate_schema_version",
    "threshold_policy_sha256",
    "benchmark_aggregate_sha256",
    "benchmark_manifest_sha256",
    "canonical_attempt_ledger_sha256",
    "adjudication_manifest_sha256",
    "gate_run_id",
}
_LANE_KEYS = {
    "lane_id",
    "matter_type",
    "asset_class",
    "jurisdiction",
    "execution_profile",
    "decision_kind",
    "required_record_components_sha256",
    "benchmark_population_sha256",
    "eligible_independent_case_count",
    "eligible_predicted_clear_case_count",
    "eligible_non_clear_case_count",
    "observed_false_clear_count",
    "false_clear_confidence_level",
    "false_clear_upper_bound",
}
_VALIDITY_KEYS = {
    "issued_at",
    "not_before",
    "expires_at",
    "revocation_namespace",
}


@dataclass(frozen=True)
class CertifiedLane:
    lane_id: str
    matter_type: str
    asset_class: str
    jurisdiction: str
    execution_profile: str
    required_record_components_sha256: str


@dataclass(frozen=True)
class VerifiedCertificationReceipt:
    verified: bool
    failures: tuple[str, ...]
    receipt_id: str = ""
    receipt_sha256: str = ""
    pipeline_git_sha: str = ""
    source_tree_sha256: str = ""
    expires_at: str = ""
    issuer_verifier_id: str = ""
    key_id: str = ""
    gate_run_id: str = ""
    benchmark_aggregate_sha256: str = ""
    certified_lanes: tuple[CertifiedLane, ...] = ()
    policy: CertificationPolicySnapshot | None = None


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _secret_value(value: object) -> str:
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter() or "")
    return str(value or "")


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "")
    if not text.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _decode_base64(value: object) -> bytes | None:
    try:
        return base64.b64decode(str(value or ""), validate=True)
    except (ValueError, TypeError):
        return None


def _dsse_pae(payload_type: str, payload: bytes) -> bytes:
    type_bytes = payload_type.encode()
    return (
        b"DSSEv1 "
        + str(len(type_bytes)).encode()
        + b" "
        + type_bytes
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def _strict_mapping(value: object, keys: set[str]) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) and set(value) == keys else None


def _expected_subject(settings: object | None) -> dict[str, str]:
    return {
        "api_oci_image_digest": str(
            getattr(settings, "certification_api_oci_image_digest", "") or ""
        ).strip(),
        "worker_oci_image_digest": str(
            getattr(settings, "certification_worker_oci_image_digest", "") or ""
        ).strip(),
        "runtime_policy_sha256": str(
            getattr(settings, "certification_runtime_policy_sha256", "") or ""
        ).strip(),
        "evidence_policy_sha256": str(
            getattr(settings, "certification_evidence_policy_sha256", "") or ""
        ).strip(),
        "prompt_bundle_sha256": str(
            getattr(settings, "certification_prompt_bundle_sha256", "") or ""
        ).strip(),
        "model_bundle_sha256": str(
            getattr(settings, "certification_model_bundle_sha256", "") or ""
        ).strip(),
        "tool_definition_bundle_sha256": str(
            getattr(settings, "certification_tool_definition_bundle_sha256", "") or ""
        ).strip(),
        "collector_bundle_sha256": str(
            getattr(settings, "certification_collector_bundle_sha256", "") or ""
        ).strip(),
    }


def _revoked_receipt_ids(settings: object | None) -> set[str]:
    values = getattr(settings, "certification_revoked_receipt_ids", ())
    if isinstance(values, str):
        values = values.split(",")
    return {str(value or "").strip() for value in values or () if str(value or "").strip()}


@dataclass(frozen=True)
class _ReceiptTrust:
    raw_receipt: str
    public_key_b64: str
    expected_key_id: str
    expected_verifier_id: str


@dataclass(frozen=True)
class _ParsedReceipt:
    envelope: Mapping[str, object]
    payload: Mapping[str, object]


def _invalid_receipt(*failures: str) -> VerifiedCertificationReceipt:
    return VerifiedCertificationReceipt(False, failures)


def _load_receipt_trust(
    settings: object | None,
    receipt_json: str | None,
) -> tuple[_ReceiptTrust, tuple[str, ...]]:
    raw_receipt = str(
        receipt_json
        if receipt_json is not None
        else getattr(settings, "certification_release_receipt_json", "") or ""
    ).strip()
    public_key_b64 = _secret_value(
        getattr(settings, "certification_release_public_key", "")
    ).strip()
    expected_key_id = str(getattr(settings, "certification_release_key_id", "") or "").strip()
    expected_verifier_id = str(
        getattr(settings, "certification_release_verifier_id", "") or ""
    ).strip()
    missing = []
    if not raw_receipt:
        missing.append("certification_release_receipt_missing")
    if not public_key_b64 or not expected_key_id or not expected_verifier_id:
        missing.append("certification_release_trust_root_missing")
    return (
        _ReceiptTrust(
            raw_receipt=raw_receipt,
            public_key_b64=public_key_b64,
            expected_key_id=expected_key_id,
            expected_verifier_id=expected_verifier_id,
        ),
        tuple(missing),
    )


def _parse_and_verify_envelope(
    trust: _ReceiptTrust,
) -> _ParsedReceipt | str:
    try:
        envelope_value = json.loads(trust.raw_receipt)
    except json.JSONDecodeError:
        return "certification_release_receipt_json_invalid"
    envelope = _strict_mapping(envelope_value, _ENVELOPE_KEYS)
    if envelope is None:
        return "certification_release_receipt_envelope_invalid"
    if envelope.get("payloadType") != PAYLOAD_TYPE:
        return "certification_release_receipt_payload_type_invalid"

    payload_bytes = _decode_base64(envelope.get("payload"))
    signatures = envelope.get("signatures")
    if payload_bytes is None or not isinstance(signatures, list) or len(signatures) != 1:
        return "certification_release_receipt_signature_envelope_invalid"
    signature_row = _strict_mapping(signatures[0], {"keyid", "sig"})
    if signature_row is None:
        return "certification_release_receipt_signature_envelope_invalid"
    if signature_row.get("keyid") != trust.expected_key_id:
        return "certification_release_receipt_key_id_mismatch"

    public_key_bytes = _decode_base64(trust.public_key_b64)
    signature_bytes = _decode_base64(signature_row.get("sig"))
    if public_key_bytes is None or signature_bytes is None:
        return "certification_release_receipt_key_or_signature_invalid"
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, _dsse_pae(PAYLOAD_TYPE, payload_bytes)
        )
    except (ValueError, InvalidSignature):
        return "certification_release_receipt_signature_mismatch"

    try:
        payload_value = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "certification_release_receipt_payload_invalid"
    payload = _strict_mapping(payload_value, _PAYLOAD_KEYS)
    if payload is None:
        return "certification_release_receipt_payload_invalid"
    if canonical_json_bytes(payload) != payload_bytes:
        return "certification_release_receipt_payload_not_canonical"
    return _ParsedReceipt(envelope=envelope, payload=payload)


def _receipt_sections(
    payload: Mapping[str, object],
) -> (
    tuple[
        Mapping[str, object],
        Mapping[str, object],
        Mapping[str, object],
        Mapping[str, object],
        object,
    ]
    | None
):
    issuer = _strict_mapping(payload.get("issuer"), _ISSUER_KEYS)
    subject = _strict_mapping(payload.get("subject"), _SUBJECT_KEYS)
    gate = _strict_mapping(payload.get("gate"), _GATE_KEYS)
    validity = _strict_mapping(payload.get("validity"), _VALIDITY_KEYS)
    if issuer is None or subject is None or gate is None or validity is None:
        return None
    return issuer, subject, gate, validity, payload.get("certified_lanes")


def _validate_receipt_identity(
    payload: Mapping[str, object],
    issuer: Mapping[str, object],
    settings: object | None,
    trust: _ReceiptTrust,
    failures: list[str],
) -> str:
    if payload.get("schema_version") != "praviar.release-certification.v2":
        failures.append("certification_release_receipt_schema_invalid")
    receipt_id = str(payload.get("receipt_id") or "").strip()
    if not receipt_id:
        failures.append("certification_release_receipt_id_missing")
    if receipt_id in _revoked_receipt_ids(settings):
        failures.append("certification_release_receipt_revoked")
    if issuer.get("verifier_id") != trust.expected_verifier_id:
        failures.append("certification_release_verifier_id_mismatch")
    if issuer.get("key_id") != trust.expected_key_id:
        failures.append("certification_release_issuer_key_id_mismatch")
    return receipt_id


def _validate_signed_subject(
    subject: Mapping[str, object],
    expected_subject: Mapping[str, str],
    failures: list[str],
) -> tuple[str, str]:
    signed_pipeline_sha = str(subject.get("git_sha") or "")
    signed_source_sha = str(subject.get("source_tree_sha256") or "")
    if _GIT_SHA_RE.fullmatch(signed_pipeline_sha) is None:
        failures.append("certification_release_subject_pipeline_sha_invalid")
    if _SHA256_RE.fullmatch(signed_source_sha) is None:
        failures.append("certification_release_subject_source_tree_sha_invalid")
    for key in expected_subject:
        signed_value = str(subject.get(key) or "")
        valid_digest = (
            _OCI_DIGEST_RE.fullmatch(signed_value)
            if key in {"api_oci_image_digest", "worker_oci_image_digest"}
            else _SHA256_RE.fullmatch(signed_value)
        )
        if valid_digest is None:
            failures.append(f"certification_release_subject_{key}_invalid")
    return signed_pipeline_sha, signed_source_sha


def _validate_runtime_subject(
    subject: Mapping[str, object],
    expected_subject: Mapping[str, str],
    *,
    signed_pipeline_sha: str,
    signed_source_sha: str,
    pipeline_git_sha: str | None,
    source_tree_sha256: str | None,
    failures: list[str],
) -> None:
    observed_pipeline_sha = (pipeline_git_sha or get_pipeline_version()).strip().lower()
    if signed_pipeline_sha != observed_pipeline_sha:
        failures.append("certification_release_pipeline_sha_mismatch")
    if source_tree_sha256 is None:
        _, observed_source_sha = compute_source_tree_provenance()
    else:
        observed_source_sha = source_tree_sha256.strip().lower()
    if signed_source_sha != observed_source_sha:
        failures.append("certification_release_source_tree_sha_mismatch")
    try:
        runtime_bundle_digests = compute_certification_bundle_digests()
    except (OSError, RuntimeError):
        runtime_bundle_digests = {}
        failures.append("certification_release_runtime_bundle_identity_unavailable")
    for key, expected_value in expected_subject.items():
        signed_value = str(subject.get(key) or "")
        if not expected_value or signed_value != expected_value:
            failures.append(f"certification_release_{key}_mismatch")
        if (
            key not in {"api_oci_image_digest", "worker_oci_image_digest"}
            and runtime_bundle_digests.get(key) != signed_value
        ):
            failures.append(f"certification_release_{key}_runtime_mismatch")


def _validate_gate(gate: Mapping[str, object], failures: list[str]) -> str:
    if gate.get("result") != "PASSED" or gate.get("gate_schema_version") != 2:
        failures.append("certification_release_gate_not_passed")
    for key in (
        "threshold_policy_sha256",
        "benchmark_aggregate_sha256",
        "benchmark_manifest_sha256",
        "canonical_attempt_ledger_sha256",
        "adjudication_manifest_sha256",
    ):
        if _SHA256_RE.fullmatch(str(gate.get(key) or "")) is None:
            failures.append(f"certification_release_gate_{key}_invalid")
    gate_run_id = str(gate.get("gate_run_id") or "").strip()
    if not gate_run_id:
        failures.append("certification_release_gate_run_id_missing")
    return gate_run_id


def _validate_validity(
    validity: Mapping[str, object],
    now: datetime | None,
    failures: list[str],
) -> None:
    issued_at = _parse_timestamp(validity.get("issued_at"))
    not_before = _parse_timestamp(validity.get("not_before"))
    expires_at = _parse_timestamp(validity.get("expires_at"))
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        issued_at is None
        or not_before is None
        or expires_at is None
        or not (issued_at <= not_before < expires_at)
        or expires_at - not_before > timedelta(days=31)
    ):
        failures.append("certification_release_receipt_validity_window_invalid")
    else:
        if observed_now < not_before:
            failures.append("certification_release_receipt_not_yet_valid")
        if observed_now >= expires_at:
            failures.append("certification_release_receipt_expired")
    if not str(validity.get("revocation_namespace") or "").strip():
        failures.append("certification_release_revocation_namespace_missing")


def _non_negative_counts(*values: object) -> tuple[int, ...] | None:
    counts = []
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        counts.append(value)
    return tuple(counts)


def _validate_lane_scope(
    lane: Mapping[str, object],
    *,
    lane_id: str,
    matter_type: str,
    asset_class: str,
    jurisdiction: str,
    execution_profile: str,
    failures: list[str],
) -> None:
    if (
        not matter_type
        or not asset_class
        or not jurisdiction
        or execution_profile != "adaptive"
        or lane.get("decision_kind") != "positive_clearance"
    ):
        failures.append(f"certification_release_lane_scope_invalid:{lane_id}")
    for key in ("required_record_components_sha256", "benchmark_population_sha256"):
        if _SHA256_RE.fullmatch(str(lane.get(key) or "")) is None:
            failures.append(f"certification_release_lane_{key}_invalid:{lane_id}")


def _validate_lane_statistics(
    lane: Mapping[str, object],
    lane_id: str,
    failures: list[str],
) -> None:
    counts = _non_negative_counts(
        lane.get("eligible_independent_case_count"),
        lane.get("eligible_predicted_clear_case_count"),
        lane.get("eligible_non_clear_case_count"),
        lane.get("observed_false_clear_count"),
    )
    if counts is None:
        failures.append(f"certification_release_lane_counts_invalid:{lane_id}")
    else:
        independent_count, predicted_clear_count, non_clear_count, false_clear_count = counts
        if (
            independent_count < 598
            or predicted_clear_count < 299
            or non_clear_count < 299
            or false_clear_count != 0
        ):
            failures.append(f"certification_release_lane_gate_insufficient:{lane_id}")
    if (
        lane.get("false_clear_confidence_level") != "0.95"
        or lane.get("false_clear_upper_bound") != "0.01"
    ):
        failures.append(f"certification_release_lane_statistic_invalid:{lane_id}")


def _validate_lane(
    lane_raw: object,
    lane_ids: set[str],
    failures: list[str],
) -> CertifiedLane | None:
    lane = _strict_mapping(lane_raw, _LANE_KEYS)
    if lane is None:
        failures.append("certification_release_lane_schema_invalid")
        return None

    lane_id = str(lane.get("lane_id") or "").strip()
    matter_type = normalize_matter_type(lane.get("matter_type"))
    asset_class = str(lane.get("asset_class") or "").strip().lower()
    jurisdiction = normalize_jurisdiction(lane.get("jurisdiction"))
    execution_profile = str(lane.get("execution_profile") or "").strip().lower()
    if not lane_id or lane_id in lane_ids:
        failures.append("certification_release_lane_id_invalid")
    lane_ids.add(lane_id)
    _validate_lane_scope(
        lane,
        lane_id=lane_id,
        matter_type=matter_type,
        asset_class=asset_class,
        jurisdiction=jurisdiction,
        execution_profile=execution_profile,
        failures=failures,
    )
    _validate_lane_statistics(lane, lane_id, failures)
    return CertifiedLane(
        lane_id=lane_id,
        matter_type=matter_type,
        asset_class=asset_class,
        jurisdiction=jurisdiction,
        execution_profile=execution_profile,
        required_record_components_sha256=str(lane.get("required_record_components_sha256") or ""),
    )


def _validate_lanes(lanes_raw: object, failures: list[str]) -> list[CertifiedLane]:
    certified_lanes: list[CertifiedLane] = []
    if not isinstance(lanes_raw, list) or not lanes_raw:
        failures.append("certification_release_lanes_missing")
        return certified_lanes
    lane_ids: set[str] = set()
    for lane_raw in lanes_raw:
        lane = _validate_lane(lane_raw, lane_ids, failures)
        if lane is not None:
            certified_lanes.append(lane)
    return certified_lanes


def _build_policy(
    receipt_id: str,
    certified_lanes: list[CertifiedLane],
) -> CertificationPolicySnapshot:
    modalities = tuple(
        dict.fromkeys(normalize_modality(lane.matter_type) for lane in certified_lanes)
    )
    matter_types = tuple(dict.fromkeys(lane.matter_type for lane in certified_lanes))
    jurisdictions = tuple(dict.fromkeys(lane.jurisdiction for lane in certified_lanes))
    asset_classes = tuple(dict.fromkeys(lane.asset_class for lane in certified_lanes))
    matrix = {
        modality: tuple(
            dict.fromkeys(
                lane.jurisdiction
                for lane in certified_lanes
                if normalize_modality(lane.matter_type) == modality
            )
        )
        for modality in modalities
    }
    return CertificationPolicySnapshot(
        version=receipt_id,
        certified_modalities=modalities,
        certified_matter_types=matter_types,
        certified_decision_jurisdictions=jurisdictions,
        certified_asset_classes=asset_classes,
        supported_jurisdictions=jurisdictions,
        counsel_certification_matrix=matrix,
    )


def verify_certification_receipt(
    settings: object | None,
    *,
    receipt_json: str | None = None,
    now: datetime | None = None,
    pipeline_git_sha: str | None = None,
    source_tree_sha256: str | None = None,
    subject_verification: SubjectVerificationMode = "current_runtime",
) -> VerifiedCertificationReceipt:
    """Verify a DSSE receipt against pinned trust and its required subject.

    Generation uses ``current_runtime`` so a worker can only rely on a receipt
    issued for its exact deployed inputs. Historical report access uses
    ``signed_receipt``: the signed subject remains strictly validated and bound
    to the stored report, but is not compared with the newer API deployment
    serving that immutable report.
    """
    if subject_verification not in {"current_runtime", "signed_receipt"}:
        return _invalid_receipt("certification_release_subject_verification_mode_invalid")
    trust, missing = _load_receipt_trust(settings, receipt_json)
    if missing:
        return VerifiedCertificationReceipt(False, missing)

    parsed = _parse_and_verify_envelope(trust)
    if isinstance(parsed, str):
        return _invalid_receipt(parsed)
    sections = _receipt_sections(parsed.payload)
    if sections is None:
        return _invalid_receipt("certification_release_receipt_nested_schema_invalid")
    issuer, subject, gate, validity, lanes_raw = sections

    failures: list[str] = []
    receipt_id = _validate_receipt_identity(parsed.payload, issuer, settings, trust, failures)
    expected_subject = _expected_subject(settings)
    signed_pipeline_sha, signed_source_sha = _validate_signed_subject(
        subject, expected_subject, failures
    )
    if subject_verification == "current_runtime":
        _validate_runtime_subject(
            subject,
            expected_subject,
            signed_pipeline_sha=signed_pipeline_sha,
            signed_source_sha=signed_source_sha,
            pipeline_git_sha=pipeline_git_sha,
            source_tree_sha256=source_tree_sha256,
            failures=failures,
        )
    gate_run_id = _validate_gate(gate, failures)
    _validate_validity(validity, now, failures)
    certified_lanes = _validate_lanes(lanes_raw, failures)
    policy = None if failures else _build_policy(receipt_id, certified_lanes)
    return VerifiedCertificationReceipt(
        verified=not failures,
        failures=tuple(failures),
        receipt_id=receipt_id,
        receipt_sha256=hashlib.sha256(canonical_json_bytes(parsed.envelope)).hexdigest(),
        pipeline_git_sha=str(subject.get("git_sha") or ""),
        source_tree_sha256=str(subject.get("source_tree_sha256") or ""),
        expires_at=str(validity.get("expires_at") or ""),
        issuer_verifier_id=str(issuer.get("verifier_id") or ""),
        key_id=str(issuer.get("key_id") or ""),
        gate_run_id=gate_run_id,
        benchmark_aggregate_sha256=str(gate.get("benchmark_aggregate_sha256") or ""),
        certified_lanes=tuple(certified_lanes),
        policy=policy,
    )
