"""Asymmetric, tenant-bound certification signatures for completed reports."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

REPORT_BINDING_FIELD = "report_certification_binding"
REPORT_BINDING_DOMAIN = "praviar:report-certification-binding:v2"
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SIGNING_KEYRING_SCHEMA = "praviar.report-certification-signing-keyring.v1"
_VERIFICATION_KEYRING_SCHEMA = "praviar.report-certification-verification-keyring.v1"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _decode_key(value: object, *, private: bool) -> bytes:
    try:
        decoded = base64.b64decode(str(value or ""), validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("report certification key is not canonical base64") from exc
    if len(decoded) != 32:
        kind = "private" if private else "public"
        raise ValueError(f"report certification {kind} key must contain 32 raw bytes")
    return decoded


def _validate_key_id(value: object) -> str:
    key_id = str(value or "")
    if _KEY_ID_RE.fullmatch(key_id) is None:
        raise ValueError("report certification key id is invalid")
    return key_id


@dataclass(frozen=True)
class ReportCertificationSigner:
    """Worker-only Ed25519 signing key ring with one active signer."""

    active_key_id: str
    private_keys: Mapping[str, Ed25519PrivateKey]

    @classmethod
    def from_secret(cls, secret: str) -> ReportCertificationSigner:
        try:
            payload = json.loads(secret)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("report certification signing key ring is invalid JSON") from exc
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version",
            "active_key_id",
            "private_keys",
        }:
            raise ValueError("report certification signing key ring schema is invalid")
        if payload.get("schema_version") != _SIGNING_KEYRING_SCHEMA:
            raise ValueError("report certification signing key ring version is invalid")
        active_key_id = _validate_key_id(payload.get("active_key_id"))
        raw_keys = payload.get("private_keys")
        if not isinstance(raw_keys, Mapping) or not raw_keys:
            raise ValueError("report certification signing key ring is empty")
        private_keys: dict[str, Ed25519PrivateKey] = {}
        for raw_key_id, raw_key in raw_keys.items():
            key_id = _validate_key_id(raw_key_id)
            private_keys[key_id] = Ed25519PrivateKey.from_private_bytes(
                _decode_key(raw_key, private=True)
            )
        if active_key_id not in private_keys:
            raise ValueError("active report certification signing key is unavailable")
        return cls(active_key_id=active_key_id, private_keys=private_keys)

    def sign(self, message: bytes) -> bytes:
        return self.private_keys[self.active_key_id].sign(message)

    def public_keyring(self) -> ReportCertificationVerificationKeyRing:
        return ReportCertificationVerificationKeyRing(
            keys={key_id: key.public_key() for key_id, key in self.private_keys.items()}
        )


@dataclass(frozen=True)
class ReportCertificationVerificationKeyRing:
    """API-safe set of public verification keys retained across rotations."""

    keys: Mapping[str, Ed25519PublicKey]

    @classmethod
    def from_json(cls, raw: str) -> ReportCertificationVerificationKeyRing:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("report certification public key ring is invalid JSON") from exc
        if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "keys"}:
            raise ValueError("report certification public key ring schema is invalid")
        if payload.get("schema_version") != _VERIFICATION_KEYRING_SCHEMA:
            raise ValueError("report certification public key ring version is invalid")
        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, Mapping) or not raw_keys:
            raise ValueError("report certification public key ring is empty")
        keys: dict[str, Ed25519PublicKey] = {}
        for raw_key_id, raw_key in raw_keys.items():
            key_id = _validate_key_id(raw_key_id)
            keys[key_id] = Ed25519PublicKey.from_public_bytes(_decode_key(raw_key, private=False))
        return cls(keys=keys)

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": _VERIFICATION_KEYRING_SCHEMA,
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


def _report_without_binding(report: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != REPORT_BINDING_FIELD}


def _report_sha256(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(_report_without_binding(report))).hexdigest()


def _signature_message(unsigned_binding: Mapping[str, Any]) -> bytes:
    return _canonical_json_bytes(
        {"domain": REPORT_BINDING_DOMAIN, "binding": dict(unsigned_binding)}
    )


def sign_report_certification_binding(
    report: Mapping[str, Any],
    *,
    signer: ReportCertificationSigner,
    analysis_id: str,
    org_id: str,
) -> dict[str, Any]:
    certification = report.get("certification_scope") or {}
    if not isinstance(certification, Mapping):
        raise ValueError("certification_scope is required for report binding")
    receipt_id = str(certification.get("evidence_receipt_id") or "").strip()
    receipt_sha256 = str(certification.get("evidence_receipt_sha256") or "").strip()
    normalized_analysis_id = str(analysis_id or "").strip()
    normalized_org_id = str(org_id or "").strip()
    lane_ids = sorted(
        {
            str(value or "").strip()
            for value in certification.get("verified_lane_ids") or []
            if str(value or "").strip()
        }
    )
    if not normalized_analysis_id or not normalized_org_id:
        raise ValueError("analysis and organization identifiers are required for report binding")
    if receipt_sha256 and len(receipt_sha256) != 64:
        raise ValueError("report certification receipt digest is invalid")
    unsigned = {
        "schema_version": "praviar.report-certification-binding.v3",
        "algorithm": "Ed25519",
        "key_id": signer.active_key_id,
        "analysis_id": normalized_analysis_id,
        "org_id": normalized_org_id,
        "report_id": str(report.get("report_id") or "").strip(),
        "report_sha256": _report_sha256(report),
        "receipt_id": receipt_id,
        "receipt_sha256": receipt_sha256,
        "verified_lane_ids": lane_ids,
        "pipeline_git_sha": str(certification.get("evidence_pipeline_git_sha") or "").strip(),
    }
    if not unsigned["report_id"]:
        raise ValueError("report_id is required for report binding")
    signature = base64.b64encode(signer.sign(_signature_message(unsigned))).decode()
    return {**unsigned, "signature_b64": signature}


def verify_report_certification_binding(
    report: Mapping[str, Any],
    *,
    keyring: ReportCertificationVerificationKeyRing,
    expected_analysis_id: str | None = None,
    expected_org_id: str | None = None,
) -> list[str]:
    binding = report.get(REPORT_BINDING_FIELD)
    expected_keys = {
        "schema_version",
        "algorithm",
        "key_id",
        "analysis_id",
        "org_id",
        "report_id",
        "report_sha256",
        "receipt_id",
        "receipt_sha256",
        "verified_lane_ids",
        "pipeline_git_sha",
        "signature_b64",
    }
    if not isinstance(binding, Mapping) or set(binding) != expected_keys:
        return ["report_certification_binding_missing_or_invalid"]
    unsigned = {key: value for key, value in binding.items() if key != "signature_b64"}
    if (
        binding.get("schema_version")
        not in {
            "praviar.report-certification-binding.v2",
            "praviar.report-certification-binding.v3",
        }
        or binding.get("algorithm") != "Ed25519"
        or binding.get("report_id") != report.get("report_id")
        or binding.get("report_sha256") != _report_sha256(report)
    ):
        return ["report_certification_binding_subject_mismatch"]
    if (
        expected_analysis_id is not None
        and binding.get("analysis_id") != str(expected_analysis_id).strip()
    ) or (expected_org_id is not None and binding.get("org_id") != str(expected_org_id).strip()):
        return ["report_certification_binding_owner_mismatch"]
    certification = report.get("certification_scope") or {}
    if not isinstance(certification, Mapping):
        return ["report_certification_binding_scope_invalid"]
    expected_lanes = sorted(
        {
            str(value or "").strip()
            for value in certification.get("verified_lane_ids") or []
            if str(value or "").strip()
        }
    )
    expected_receipt_id = str(certification.get("evidence_receipt_id") or "").strip()
    expected_receipt_sha256 = str(certification.get("evidence_receipt_sha256") or "").strip()
    expected_pipeline_git_sha = str(certification.get("evidence_pipeline_git_sha") or "").strip()
    if (
        binding.get("receipt_id") != expected_receipt_id
        or binding.get("receipt_sha256") != expected_receipt_sha256
        or binding.get("verified_lane_ids") != expected_lanes
        or binding.get("pipeline_git_sha") != expected_pipeline_git_sha
    ):
        return ["report_certification_binding_scope_mismatch"]
    verification_key = keyring.keys.get(str(binding.get("key_id") or ""))
    if verification_key is None:
        return ["report_certification_binding_key_unavailable"]
    try:
        signature = base64.b64decode(str(binding.get("signature_b64") or ""), validate=True)
    except (TypeError, ValueError):
        return ["report_certification_binding_signature_mismatch"]
    try:
        verification_key.verify(signature, _signature_message(unsigned))
    except (ValueError, InvalidSignature):
        return ["report_certification_binding_signature_mismatch"]
    return []
