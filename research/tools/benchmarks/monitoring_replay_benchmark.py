"""Sealed offline benchmark for conclusion-linked patent monitoring.

This evaluator scores dated monitoring events against independently
adjudicated conclusion impacts. It makes no network calls and never generates
ground truth. Fixture benchmarks are always non-credit, even when every metric
passes; only a sufficiently large, independently curated, signed production
benchmark can satisfy the release gate.

Usage:
    python research/tools/benchmarks/monitoring_replay_benchmark.py \
        --dataset path/to/sealed-dataset.json \
        --results path/to/sealed-observed-results.json \
        --output path/to/score.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

DATASET_SCHEMA_VERSION = "monitoring-replay-dataset-v1"
RESULTS_SCHEMA_VERSION = "monitoring-replay-results-v1"
REPORT_SCHEMA_VERSION = "monitoring-replay-score-v1"

MATERIAL_RECALL_MIN = 0.95
PRECISION_MIN = 0.80
FALSE_ALERT_REDUCTION_MIN = 0.30
REVIEWER_MINUTE_REDUCTION_MIN = 0.25
PROVENANCE_FIDELITY_MIN = 1.0
MIN_PRODUCTION_CASES = 50
MIN_PRODUCTION_EVENTS = 250
MIN_PRODUCTION_ORGANIZATIONS = 5
MIN_PRODUCTION_ADJUDICATORS = 3
MIN_PRODUCTION_REVIEWERS = 3
MAX_PRODUCTION_CASE_FRACTION_PER_ORGANIZATION = 0.40
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 250_000

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SIGNATURE_FIELD = "benchmark_signature"
_SIGNATURE_ALGORITHM = "Ed25519"
_SIGNATURE_SCHEMA_VERSION = 1


class MonitoringReplayValidationError(ValueError):
    """A replay artifact violates the sealed benchmark contract."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MonitoringReplayValidationError(f"{label} must be an object")
    return cast("dict[str, Any]", value)


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MonitoringReplayValidationError(f"{label} must be an array")
    return value


def _require_exact_keys(
    value: dict[str, Any],
    *,
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unexpected = sorted(set(value) - expected)
        raise MonitoringReplayValidationError(
            f"{label} fields mismatch; missing={missing}, unexpected={unexpected}"
        )


def _require_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MonitoringReplayValidationError(f"{label} must be non-empty")
    return normalized


def _require_sha256(value: object, label: str) -> str:
    digest = _require_text(value, label).lower()
    if not _SHA256.fullmatch(digest):
        raise MonitoringReplayValidationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return digest


def _require_git_sha(value: object, label: str) -> str:
    sha = _require_text(value, label).lower()
    if not _GIT_SHA.fullmatch(sha):
        raise MonitoringReplayValidationError(
            f"{label} must be a lowercase 40-character Git SHA"
        )
    return sha


def _require_number(
    value: object,
    label: str,
    *,
    minimum: float = 0.0,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MonitoringReplayValidationError(f"{label} must be a number")
    number = float(value)
    if number < minimum:
        raise MonitoringReplayValidationError(
            f"{label} must be at least {minimum:g}"
        )
    return number


def _require_integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MonitoringReplayValidationError(f"{label} must be an integer")
    if value < minimum:
        raise MonitoringReplayValidationError(
            f"{label} must be at least {minimum}"
        )
    return value


def _require_datetime(
    value: object,
    label: str,
    *,
    now: datetime,
) -> datetime:
    text = _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MonitoringReplayValidationError(
            f"{label} must be an ISO 8601 datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MonitoringReplayValidationError(f"{label} must include a UTC offset")
    if parsed > now:
        raise MonitoringReplayValidationError(f"{label} cannot be in the future")
    return parsed


def _require_uuid_like(value: object, label: str) -> str:
    normalized = _require_text(value, label)
    # Tenant IDs need stable opaque identity, not necessarily Python UUIDs in
    # imported enterprise ledgers. Whitespace and path-like values are denied.
    if any(character.isspace() for character in normalized) or "/" in normalized:
        raise MonitoringReplayValidationError(f"{label} is not a stable tenant ID")
    return normalized


def _require_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MonitoringReplayValidationError(
                f"{label} contains duplicate ID {value!r}"
            )
        seen.add(value)


def _validate_freshness_policy(value: object) -> dict[str, Any]:
    policy = _require_mapping(value, "dataset.freshness_policy")
    _require_exact_keys(
        policy,
        expected={
            "max_source_lag_seconds",
            "max_detection_lag_seconds",
            "policy_artifact_sha256",
        },
        label="dataset.freshness_policy",
    )
    _require_integer(
        policy.get("max_source_lag_seconds"),
        "dataset.freshness_policy.max_source_lag_seconds",
    )
    _require_integer(
        policy.get("max_detection_lag_seconds"),
        "dataset.freshness_policy.max_detection_lag_seconds",
    )
    _require_sha256(
        policy.get("policy_artifact_sha256"),
        "dataset.freshness_policy.policy_artifact_sha256",
    )
    return policy


def _validate_independence_policy(value: object) -> dict[str, Any]:
    policy = _require_mapping(value, "dataset.independence_policy")
    _require_exact_keys(
        policy,
        expected={
            "min_distinct_organizations",
            "min_distinct_adjudicators",
            "min_distinct_reviewers",
            "max_case_fraction_per_organization",
        },
        label="dataset.independence_policy",
    )
    for field in (
        "min_distinct_organizations",
        "min_distinct_adjudicators",
        "min_distinct_reviewers",
    ):
        _require_integer(policy.get(field), f"dataset.independence_policy.{field}", minimum=1)
    fraction = _require_number(
        policy.get("max_case_fraction_per_organization"),
        "dataset.independence_policy.max_case_fraction_per_organization",
    )
    if fraction <= 0 or fraction > 1:
        raise MonitoringReplayValidationError(
            "dataset.independence_policy.max_case_fraction_per_organization "
            "must be greater than 0 and at most 1"
        )
    return policy


def _require_relative_repo_path(value: object, label: str) -> str:
    normalized = _require_text(value, label)
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith(".git/"):
        raise MonitoringReplayValidationError(
            f"{label} must be a safe repository-relative path"
        )
    return path.as_posix()


def _verify_seal(
    payload: dict[str, Any],
    *,
    seal_field: str,
    label: str,
) -> str:
    expected = _require_sha256(payload.get(seal_field), f"{label}.{seal_field}")
    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {seal_field, _SIGNATURE_FIELD}
    }
    if _sha256(unsealed) != expected:
        raise MonitoringReplayValidationError(f"{label} seal mismatch")
    return expected


def seal_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a dataset copy with its canonical SHA-256 seal."""

    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {"dataset_sha256", _SIGNATURE_FIELD}
    }
    return {**unsealed, "dataset_sha256": _sha256(unsealed)}


def seal_observed_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an observed-results copy with its canonical SHA-256 seal."""

    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {"results_sha256", _SIGNATURE_FIELD}
    }
    return {**unsealed, "results_sha256": _sha256(unsealed)}


def seal_runtime_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a runtime manifest copy with its canonical SHA-256 seal."""

    unsealed = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    return {**unsealed, "manifest_sha256": _sha256(unsealed)}


def _signature_material(purpose: str, payload: dict[str, Any]) -> bytes:
    return (
        f"praviar:monitoring-replay:{purpose}:v1\0".encode()
        + _canonical_json_bytes(payload)
    )


def sign_benchmark_artifact(
    payload: dict[str, Any],
    *,
    purpose: Literal["dataset", "observed-results"],
    private_key: Ed25519PrivateKey,
    key_id: str,
) -> dict[str, Any]:
    """Sign a sealed benchmark artifact using a purpose-bound Ed25519 envelope."""

    normalized_key_id = _require_text(key_id, "signature key_id")
    unsigned = {
        key: value for key, value in payload.items() if key != _SIGNATURE_FIELD
    }
    signature = private_key.sign(_signature_material(purpose, unsigned))
    return {
        **unsigned,
        _SIGNATURE_FIELD: {
            "schema_version": _SIGNATURE_SCHEMA_VERSION,
            "algorithm": _SIGNATURE_ALGORITHM,
            "key_id": normalized_key_id,
            "purpose": purpose,
            "signature_base64": base64.b64encode(signature).decode("ascii"),
        },
    }


def _verify_production_signature(
    payload: dict[str, Any],
    *,
    purpose: Literal["dataset", "observed-results"],
    label: str,
) -> None:
    signature = _require_mapping(payload.get(_SIGNATURE_FIELD), f"{label}.signature")
    _require_exact_keys(
        signature,
        expected={
            "schema_version",
            "algorithm",
            "key_id",
            "purpose",
            "signature_base64",
        },
        label=f"{label}.signature",
    )
    if (
        signature.get("schema_version") != _SIGNATURE_SCHEMA_VERSION
        or signature.get("algorithm") != _SIGNATURE_ALGORITHM
        or signature.get("purpose") != purpose
    ):
        raise MonitoringReplayValidationError(
            f"{label} signature contract is invalid"
        )
    env_prefix = (
        "MONITOR_REPLAY_DATASET"
        if purpose == "dataset"
        else "MONITOR_REPLAY_RESULTS"
    )
    expected_key_id = os.environ.get(f"{env_prefix}_KEY_ID", "").strip()
    public_key_base64 = os.environ.get(f"{env_prefix}_PUBLIC_KEY", "").strip()
    if not expected_key_id or not public_key_base64:
        raise MonitoringReplayValidationError(
            f"{label} production verification key is not configured"
        )
    if signature.get("key_id") != expected_key_id:
        raise MonitoringReplayValidationError(
            f"{label} signature key is not trusted"
        )
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_base64, validate=True)
        )
        signature_bytes = base64.b64decode(
            str(signature.get("signature_base64") or ""),
            validate=True,
        )
    except (TypeError, ValueError):
        raise MonitoringReplayValidationError(
            f"{label} signature is malformed"
        ) from None
    unsigned = {
        key: value for key, value in payload.items() if key != _SIGNATURE_FIELD
    }
    try:
        public_key.verify(signature_bytes, _signature_material(purpose, unsigned))
    except (InvalidSignature, TypeError, ValueError):
        raise MonitoringReplayValidationError(
            f"{label} signature mismatch"
        ) from None


def _require_allowlisted_identity(
    value: object,
    *,
    label: str,
    env_name: str,
) -> str:
    identity = _require_text(value, label)
    allowlist = {
        item.strip()
        for item in os.environ.get(env_name, "").split(",")
        if item.strip()
    }
    if not allowlist:
        raise MonitoringReplayValidationError(
            f"{label} production allowlist is not configured"
        )
    if identity not in allowlist:
        raise MonitoringReplayValidationError(
            f"{label} is not production-allowlisted"
        )
    return identity


def _verify_reviewer_receipt(
    value: object,
    *,
    case: dict[str, Any],
    reviewer_identity: str,
    sealed_at: datetime,
    now: datetime,
) -> None:
    label = f"dataset case {case['case_id']}.reviewer_receipt"
    receipt = _require_mapping(value, label)
    _require_exact_keys(
        receipt,
        expected={
            "schema_version",
            "reviewer_identity",
            "case_id",
            "source_report_sha256",
            "adjudication_evidence_manifest_sha256",
            "signed_at",
            "key_id",
            "signature_base64",
        },
        label=label,
    )
    if receipt.get("schema_version") != "monitoring-reviewer-receipt-v1":
        raise MonitoringReplayValidationError(
            f"{label}.schema_version is unsupported"
        )
    if (
        receipt.get("reviewer_identity") != reviewer_identity
        or receipt.get("case_id") != case["case_id"]
        or receipt.get("source_report_sha256") != case["source_report_sha256"]
    ):
        raise MonitoringReplayValidationError(
            f"{label} is not bound to the exact reviewer, case, and report"
        )
    expected_manifest = _sha256(
        sorted(
            (
                {
                    "impact_id": impact["impact_id"],
                    "adjudication_evidence_sha256": impact[
                        "adjudication_evidence_sha256"
                    ],
                }
                for impact in cast(
                    "list[dict[str, Any]]",
                    case["expected_impacts"],
                )
            ),
            key=lambda item: str(item["impact_id"]),
        )
    )
    if (
        _require_sha256(
            receipt.get("adjudication_evidence_manifest_sha256"),
            f"{label}.adjudication_evidence_manifest_sha256",
        )
        != expected_manifest
    ):
        raise MonitoringReplayValidationError(
            f"{label} adjudication evidence manifest mismatch"
        )
    signed_at = _require_datetime(
        receipt.get("signed_at"),
        f"{label}.signed_at",
        now=now,
    )
    if signed_at > sealed_at:
        raise MonitoringReplayValidationError(
            f"{label} must be signed before the dataset seal"
        )
    key_id = _require_text(receipt.get("key_id"), f"{label}.key_id")
    try:
        trusted_keys = json.loads(
            os.environ.get("MONITOR_REPLAY_REVIEWER_PUBLIC_KEYS_JSON", "")
        )
    except json.JSONDecodeError:
        raise MonitoringReplayValidationError(
            "reviewer receipt trust store is malformed"
        ) from None
    if not isinstance(trusted_keys, dict) or key_id not in trusted_keys:
        raise MonitoringReplayValidationError(
            f"{label} signing key is not trusted"
        )
    unsigned = {
        key: item for key, item in receipt.items() if key != "signature_base64"
    }
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(str(trusted_keys[key_id]), validate=True)
        )
        signature = base64.b64decode(
            str(receipt.get("signature_base64") or ""),
            validate=True,
        )
        public_key.verify(
            signature,
            _signature_material("reviewer-receipt", unsigned),
        )
    except (InvalidSignature, TypeError, ValueError):
        raise MonitoringReplayValidationError(
            f"{label} signature mismatch"
        ) from None


def _validate_thresholds(value: object) -> dict[str, Any]:
    thresholds = _require_mapping(value, "dataset.thresholds")
    expected = {
        "material_recall_min": MATERIAL_RECALL_MIN,
        "precision_min": PRECISION_MIN,
        "false_alert_reduction_min": FALSE_ALERT_REDUCTION_MIN,
        "reviewer_minute_reduction_min": REVIEWER_MINUTE_REDUCTION_MIN,
        "provenance_fidelity_min": PROVENANCE_FIDELITY_MIN,
    }
    _require_exact_keys(
        thresholds,
        expected=set(expected),
        label="dataset.thresholds",
    )
    for key, required_value in expected.items():
        observed = _require_number(thresholds.get(key), f"dataset.thresholds.{key}")
        if observed != required_value:
            raise MonitoringReplayValidationError(
                f"dataset.thresholds.{key} must be {required_value}"
            )
    return thresholds


def _validate_counsel_burden_approval(
    value: object,
    *,
    sealed_at: datetime,
    scope: str,
    now: datetime,
) -> dict[str, Any] | None:
    if value is None:
        return None
    approval = _require_mapping(value, "dataset.counsel_burden_approval")
    _require_exact_keys(
        approval,
        expected={
            "approved_by",
            "approved_at",
            "approval_evidence_sha256",
            "max_false_alerts_total",
            "max_false_alerts_per_case",
        },
        label="dataset.counsel_burden_approval",
    )
    approved_by = _require_text(
        approval.get("approved_by"),
        "dataset.counsel_burden_approval.approved_by",
    )
    approved_at = _require_datetime(
        approval.get("approved_at"),
        "dataset.counsel_burden_approval.approved_at",
        now=now,
    )
    if approved_at > sealed_at:
        raise MonitoringReplayValidationError(
            "counsel burden approval must predate the dataset seal"
        )
    _require_sha256(
        approval.get("approval_evidence_sha256"),
        "dataset.counsel_burden_approval.approval_evidence_sha256",
    )
    _require_integer(
        approval.get("max_false_alerts_total"),
        "dataset.counsel_burden_approval.max_false_alerts_total",
    )
    _require_number(
        approval.get("max_false_alerts_per_case"),
        "dataset.counsel_burden_approval.max_false_alerts_per_case",
    )
    if scope == "production":
        _require_allowlisted_identity(
            approved_by,
            label="dataset.counsel_burden_approval.approved_by",
            env_name="MONITOR_REPLAY_COUNSEL_ALLOWLIST",
        )
    return approval


def validate_dataset(
    payload: object,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate curation, chronology, tenant boundaries, and the dataset seal."""

    current_time = now or datetime.now(UTC)
    dataset = _require_mapping(payload, "dataset")
    if dataset.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise MonitoringReplayValidationError(
            "dataset.schema_version is unsupported"
        )
    fields = {
        "schema_version",
        "benchmark_id",
        "benchmark_scope",
        "sealed_at",
        "replay_window_start",
        "replay_window_end",
        "curation_organization",
        "curation_protocol_sha256",
        "curation_artifact_sha256",
        "thresholds",
        "freshness_policy",
        "independence_policy",
        "counsel_burden_approval",
        "cases",
        "dataset_sha256",
    }
    if _SIGNATURE_FIELD in dataset:
        fields.add(_SIGNATURE_FIELD)
    _require_exact_keys(dataset, expected=fields, label="dataset")
    _verify_seal(dataset, seal_field="dataset_sha256", label="dataset")
    benchmark_id = _require_text(dataset.get("benchmark_id"), "dataset.benchmark_id")
    scope = dataset.get("benchmark_scope")
    if scope not in {"fixture", "production"}:
        raise MonitoringReplayValidationError(
            "dataset.benchmark_scope must be fixture or production"
        )
    sealed_at = _require_datetime(dataset.get("sealed_at"), "dataset.sealed_at", now=current_time)
    window_start = _require_datetime(
        dataset.get("replay_window_start"),
        "dataset.replay_window_start",
        now=current_time,
    )
    window_end = _require_datetime(
        dataset.get("replay_window_end"),
        "dataset.replay_window_end",
        now=current_time,
    )
    if window_start >= window_end or window_end > sealed_at:
        raise MonitoringReplayValidationError(
            "dataset replay window must be ordered and end by the seal time"
        )
    curation_organization = _require_text(
        dataset.get("curation_organization"),
        "dataset.curation_organization",
    )
    _require_sha256(
        dataset.get("curation_protocol_sha256"),
        "dataset.curation_protocol_sha256",
    )
    _require_sha256(
        dataset.get("curation_artifact_sha256"),
        "dataset.curation_artifact_sha256",
    )
    _validate_thresholds(dataset.get("thresholds"))
    freshness_policy = _validate_freshness_policy(dataset.get("freshness_policy"))
    independence_policy = _validate_independence_policy(
        dataset.get("independence_policy")
    )
    approval = _validate_counsel_burden_approval(
        dataset.get("counsel_burden_approval"),
        sealed_at=sealed_at,
        scope=str(scope),
        now=current_time,
    )

    cases = _require_list(dataset.get("cases"), "dataset.cases")
    if not cases:
        raise MonitoringReplayValidationError("dataset.cases must not be empty")

    case_ids: list[str] = []
    event_ids: list[str] = []
    impact_ids: list[str] = []
    organizations: list[str] = []
    adjudicators: list[str] = []
    reviewers: list[str] = []
    total_events = 0
    for case_index, raw_case in enumerate(cases):
        label = f"dataset.cases[{case_index}]"
        case = _require_mapping(raw_case, label)
        _require_exact_keys(
            case,
            expected={
                "case_id",
                "org_id",
                "source_report_id",
                "source_report_sha256",
                "source_report_generated_at",
                "replay_as_of",
                "adjudicator_identity",
                "reviewer_identity",
                "adjudicated_at",
                "baseline_false_alert_count",
                "baseline_reviewer_minutes",
                "conclusion_universe",
                "reviewer_receipt",
                "events",
                "expected_impacts",
            },
            label=label,
        )
        case_id = _require_text(case.get("case_id"), f"{label}.case_id")
        org_id = _require_uuid_like(case.get("org_id"), f"{label}.org_id")
        report_id = _require_text(
            case.get("source_report_id"),
            f"{label}.source_report_id",
        )
        report_sha = _require_sha256(
            case.get("source_report_sha256"),
            f"{label}.source_report_sha256",
        )
        report_generated_at = _require_datetime(
            case.get("source_report_generated_at"),
            f"{label}.source_report_generated_at",
            now=current_time,
        )
        replay_as_of = _require_datetime(
            case.get("replay_as_of"),
            f"{label}.replay_as_of",
            now=current_time,
        )
        adjudicated_at = _require_datetime(
            case.get("adjudicated_at"),
            f"{label}.adjudicated_at",
            now=current_time,
        )
        if not (
            window_start
            <= report_generated_at
            <= replay_as_of
            <= window_end
            <= adjudicated_at
            <= sealed_at
        ):
            raise MonitoringReplayValidationError(
                f"{label} has non-causal report/replay/adjudication timestamps"
            )
        adjudicator = _require_text(
            case.get("adjudicator_identity"),
            f"{label}.adjudicator_identity",
        )
        reviewer = _require_text(
            case.get("reviewer_identity"),
            f"{label}.reviewer_identity",
        )
        if adjudicator == reviewer:
            raise MonitoringReplayValidationError(
                f"{label} adjudicator and reviewer must be independent identities"
            )
        organizations.append(org_id)
        adjudicators.append(adjudicator)
        reviewers.append(reviewer)
        if scope == "production":
            _require_allowlisted_identity(
                curation_organization,
                label="dataset.curation_organization",
                env_name="MONITOR_REPLAY_CURATION_ORG_ALLOWLIST",
            )
            _require_allowlisted_identity(
                adjudicator,
                label=f"{label}.adjudicator_identity",
                env_name="MONITOR_REPLAY_ADJUDICATOR_ALLOWLIST",
            )
            _require_allowlisted_identity(
                reviewer,
                label=f"{label}.reviewer_identity",
                env_name="MONITOR_REPLAY_REVIEWER_ALLOWLIST",
            )
        _require_integer(
            case.get("baseline_false_alert_count"),
            f"{label}.baseline_false_alert_count",
        )
        _require_number(
            case.get("baseline_reviewer_minutes"),
            f"{label}.baseline_reviewer_minutes",
        )

        conclusion_ids: list[str] = []
        for conclusion_index, raw_conclusion in enumerate(
            _require_list(
                case.get("conclusion_universe"),
                f"{label}.conclusion_universe",
            )
        ):
            conclusion_label = (
                f"{label}.conclusion_universe[{conclusion_index}]"
            )
            conclusion = _require_mapping(raw_conclusion, conclusion_label)
            _require_exact_keys(
                conclusion,
                expected={
                    "conclusion_id",
                    "dependency_fingerprint",
                    "conclusion_evidence_sha256",
                },
                label=conclusion_label,
            )
            conclusion_ids.append(
                _require_text(
                    conclusion.get("conclusion_id"),
                    f"{conclusion_label}.conclusion_id",
                )
            )
            _require_sha256(
                conclusion.get("dependency_fingerprint"),
                f"{conclusion_label}.dependency_fingerprint",
            )
            _require_sha256(
                conclusion.get("conclusion_evidence_sha256"),
                f"{conclusion_label}.conclusion_evidence_sha256",
            )
        if not conclusion_ids:
            raise MonitoringReplayValidationError(
                f"{label}.conclusion_universe must not be empty"
            )
        _require_unique(conclusion_ids, f"{label}.conclusion_universe")
        conclusion_id_set = set(conclusion_ids)

        raw_events = _require_list(case.get("events"), f"{label}.events")
        if not raw_events:
            raise MonitoringReplayValidationError(f"{label}.events must not be empty")
        case_event_ids: set[str] = set()
        event_by_id: dict[str, dict[str, Any]] = {}
        for event_index, raw_event in enumerate(raw_events):
            event_label = f"{label}.events[{event_index}]"
            event = _require_mapping(raw_event, event_label)
            _require_exact_keys(
                event,
                expected={
                    "event_id",
                    "org_id",
                    "source_report_id",
                    "occurred_at",
                    "available_at",
                    "source_id",
                    "source_sha256",
                },
                label=event_label,
            )
            event_id = _require_text(event.get("event_id"), f"{event_label}.event_id")
            event_org = _require_uuid_like(event.get("org_id"), f"{event_label}.org_id")
            event_report = _require_text(
                event.get("source_report_id"),
                f"{event_label}.source_report_id",
            )
            if event_org != org_id or event_report != report_id:
                raise MonitoringReplayValidationError(
                    f"{event_label} crosses the case tenant/report boundary"
                )
            occurred_at = _require_datetime(
                event.get("occurred_at"),
                f"{event_label}.occurred_at",
                now=current_time,
            )
            available_at = _require_datetime(
                event.get("available_at"),
                f"{event_label}.available_at",
                now=current_time,
            )
            if not (
                report_generated_at <= occurred_at <= available_at <= replay_as_of
            ):
                raise MonitoringReplayValidationError(
                    f"{event_label} is future, leaky, or non-causal"
                )
            if (
                available_at - occurred_at
            ).total_seconds() > int(freshness_policy["max_source_lag_seconds"]):
                raise MonitoringReplayValidationError(
                    f"{event_label} exceeds the sealed source freshness policy"
                )
            _require_text(event.get("source_id"), f"{event_label}.source_id")
            _require_sha256(
                event.get("source_sha256"),
                f"{event_label}.source_sha256",
            )
            case_event_ids.add(event_id)
            event_ids.append(event_id)
            event_by_id[event_id] = event
            total_events += 1

        raw_impacts = _require_list(
            case.get("expected_impacts"),
            f"{label}.expected_impacts",
        )
        semantic_impacts: list[tuple[str, str, str]] = []
        for impact_index, raw_impact in enumerate(raw_impacts):
            impact_label = f"{label}.expected_impacts[{impact_index}]"
            impact = _require_mapping(raw_impact, impact_label)
            _require_exact_keys(
                impact,
                expected={
                    "impact_id",
                    "org_id",
                    "source_report_id",
                    "source_report_sha256",
                    "event_id",
                    "conclusion_id",
                    "source_id",
                    "source_sha256",
                    "adjudication_evidence_sha256",
                },
                label=impact_label,
            )
            impact_id = _require_text(
                impact.get("impact_id"),
                f"{impact_label}.impact_id",
            )
            impact_org = _require_uuid_like(
                impact.get("org_id"),
                f"{impact_label}.org_id",
            )
            impact_report = _require_text(
                impact.get("source_report_id"),
                f"{impact_label}.source_report_id",
            )
            impact_report_sha = _require_sha256(
                impact.get("source_report_sha256"),
                f"{impact_label}.source_report_sha256",
            )
            if (
                impact_org != org_id
                or impact_report != report_id
                or impact_report_sha != report_sha
            ):
                raise MonitoringReplayValidationError(
                    f"{impact_label} crosses the case tenant/report boundary"
                )
            impact_event_id = _require_text(
                impact.get("event_id"),
                f"{impact_label}.event_id",
            )
            if impact_event_id not in case_event_ids:
                raise MonitoringReplayValidationError(
                    f"{impact_label} references an event outside its case"
                )
            conclusion_id = _require_text(
                impact.get("conclusion_id"),
                f"{impact_label}.conclusion_id",
            )
            if conclusion_id not in conclusion_id_set:
                raise MonitoringReplayValidationError(
                    f"{impact_label} references a conclusion outside the "
                    "sealed conclusion universe"
                )
            source_id = _require_text(
                impact.get("source_id"),
                f"{impact_label}.source_id",
            )
            source_sha = _require_sha256(
                impact.get("source_sha256"),
                f"{impact_label}.source_sha256",
            )
            event = event_by_id[impact_event_id]
            if (
                source_id != event.get("source_id")
                or source_sha != event.get("source_sha256")
            ):
                raise MonitoringReplayValidationError(
                    f"{impact_label} provenance does not match its source event"
                )
            _require_sha256(
                impact.get("adjudication_evidence_sha256"),
                f"{impact_label}.adjudication_evidence_sha256",
            )
            impact_ids.append(impact_id)
            semantic_impacts.append((impact_event_id, conclusion_id, source_sha))
        _require_unique(
            (":".join(item) for item in semantic_impacts),
            f"{label}.expected_impacts semantic keys",
        )
        case_ids.append(case_id)

    _require_unique(case_ids, "dataset.cases")
    _require_unique(event_ids, "dataset events")
    _require_unique(impact_ids, "dataset expected impacts")

    organization_counts = {
        organization: organizations.count(organization)
        for organization in set(organizations)
    }
    observed_max_org_fraction = max(organization_counts.values()) / len(cases)
    if (
        len(organization_counts)
        < int(independence_policy["min_distinct_organizations"])
        or len(set(adjudicators))
        < int(independence_policy["min_distinct_adjudicators"])
        or len(set(reviewers))
        < int(independence_policy["min_distinct_reviewers"])
        or observed_max_org_fraction
        > float(independence_policy["max_case_fraction_per_organization"])
    ):
        raise MonitoringReplayValidationError(
            "dataset does not satisfy its sealed independence policy"
        )

    if scope == "production":
        if len(cases) < MIN_PRODUCTION_CASES or total_events < MIN_PRODUCTION_EVENTS:
            raise MonitoringReplayValidationError(
                "production dataset requires at least "
                f"{MIN_PRODUCTION_CASES} cases and {MIN_PRODUCTION_EVENTS} events"
            )
        if not any(
            int(case["baseline_false_alert_count"]) > 0 for case in cases
        ) or not any(float(case["baseline_reviewer_minutes"]) > 0 for case in cases):
            raise MonitoringReplayValidationError(
                "production dataset requires non-zero baseline burden observations"
            )
        if (
            int(independence_policy["min_distinct_organizations"])
            < MIN_PRODUCTION_ORGANIZATIONS
            or int(independence_policy["min_distinct_adjudicators"])
            < MIN_PRODUCTION_ADJUDICATORS
            or int(independence_policy["min_distinct_reviewers"])
            < MIN_PRODUCTION_REVIEWERS
            or float(
                independence_policy["max_case_fraction_per_organization"]
            )
            > MAX_PRODUCTION_CASE_FRACTION_PER_ORGANIZATION
        ):
            raise MonitoringReplayValidationError(
                "production independence policy is below the release floor"
            )
        if set(adjudicators) & set(reviewers):
            raise MonitoringReplayValidationError(
                "production adjudicator and reviewer cohorts must be disjoint"
            )
        for case in cast("list[dict[str, Any]]", cases):
            _verify_reviewer_receipt(
                case.get("reviewer_receipt"),
                case=case,
                reviewer_identity=str(case["reviewer_identity"]),
                sealed_at=sealed_at,
                now=current_time,
            )
        _verify_production_signature(dataset, purpose="dataset", label="dataset")
    elif approval is not None:
        # Fixture approvals are retained for schema tests but never grant the
        # precision alternative or production evidence credit.
        pass

    # benchmark_id is intentionally read during validation so an empty value
    # cannot be hidden by a valid seal.
    assert benchmark_id
    return dataset


def _validate_runtime_manifest(
    value: object,
    *,
    scope: str,
    repo_root: Path,
    verify_runtime_state: bool,
) -> dict[str, Any]:
    manifest = _require_mapping(value, "results.runtime_manifest")
    _require_exact_keys(
        manifest,
        expected={
            "runtime_id",
            "git_sha",
            "git_tree_state_sha256",
            "runtime_artifact_sha256",
            "dependency_lock_sha256",
            "config_sha256",
            "artifacts",
            "manifest_sha256",
        },
        label="results.runtime_manifest",
    )
    expected_manifest_sha = _require_sha256(
        manifest.get("manifest_sha256"),
        "results.runtime_manifest.manifest_sha256",
    )
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if _sha256(unsigned) != expected_manifest_sha:
        raise MonitoringReplayValidationError("runtime manifest seal mismatch")
    _require_text(manifest.get("runtime_id"), "results.runtime_manifest.runtime_id")
    git_sha = _require_git_sha(
        manifest.get("git_sha"),
        "results.runtime_manifest.git_sha",
    )
    tree_sha = _require_sha256(
        manifest.get("git_tree_state_sha256"),
        "results.runtime_manifest.git_tree_state_sha256",
    )
    _require_sha256(
        manifest.get("runtime_artifact_sha256"),
        "results.runtime_manifest.runtime_artifact_sha256",
    )
    _require_sha256(
        manifest.get("dependency_lock_sha256"),
        "results.runtime_manifest.dependency_lock_sha256",
    )
    _require_sha256(
        manifest.get("config_sha256"),
        "results.runtime_manifest.config_sha256",
    )
    artifacts = _require_list(
        manifest.get("artifacts"),
        "results.runtime_manifest.artifacts",
    )
    if not artifacts:
        raise MonitoringReplayValidationError(
            "results.runtime_manifest.artifacts must not be empty"
        )
    artifact_paths: list[str] = []
    for index, raw_artifact in enumerate(artifacts):
        label = f"results.runtime_manifest.artifacts[{index}]"
        artifact = _require_mapping(raw_artifact, label)
        _require_exact_keys(
            artifact,
            expected={"path", "sha256"},
            label=label,
        )
        relative_path = _require_relative_repo_path(
            artifact.get("path"),
            f"{label}.path",
        )
        expected_sha = _require_sha256(
            artifact.get("sha256"),
            f"{label}.sha256",
        )
        artifact_paths.append(relative_path)
        if verify_runtime_state:
            path = (repo_root / relative_path).resolve()
            if (
                not path.is_relative_to(repo_root.resolve())
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha
            ):
                raise MonitoringReplayValidationError(
                    f"{label} does not match the current repository artifact"
                )
    _require_unique(artifact_paths, "results.runtime_manifest.artifacts")
    if verify_runtime_state:
        current_git_sha, current_tree_sha = current_git_state(repo_root)
        if git_sha != current_git_sha or tree_sha != current_tree_sha:
            raise MonitoringReplayValidationError(
                "observed results are not bound to the current exact Git state"
            )
    elif scope == "production":
        raise MonitoringReplayValidationError(
            "production results require exact runtime-state verification"
        )
    return manifest


def current_git_state(repo_root: Path = REPO_ROOT) -> tuple[str, str]:
    """Return HEAD and a content-sensitive digest of the exact worktree state."""

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
        untracked_output = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise MonitoringReplayValidationError(
            "could not inspect the exact Git worktree state"
        ) from exc
    _require_git_sha(head, "current Git SHA")
    untracked: list[dict[str, str]] = []
    for raw_path in untracked_output.split(b"\0"):
        if not raw_path:
            continue
        relative_path = raw_path.decode("utf-8")
        path = (repo_root / relative_path).resolve()
        if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
            raise MonitoringReplayValidationError(
                "untracked Git state contains an invalid path"
            )
        untracked.append(
            {
                "path": relative_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    tree_state = {
        "git_sha": head,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "untracked": sorted(untracked, key=lambda item: item["path"]),
    }
    return head, _sha256(tree_state)


def validate_observed_results(
    payload: object,
    *,
    dataset: dict[str, Any],
    now: datetime | None = None,
    repo_root: Path = REPO_ROOT,
    verify_runtime_state: bool = False,
) -> dict[str, Any]:
    """Validate result binding, chronology, source provenance, and isolation."""

    current_time = now or datetime.now(UTC)
    results = _require_mapping(payload, "results")
    if results.get("schema_version") != RESULTS_SCHEMA_VERSION:
        raise MonitoringReplayValidationError(
            "results.schema_version is unsupported"
        )
    fields = {
        "schema_version",
        "benchmark_id",
        "dataset_sha256",
        "generated_at",
        "runtime_manifest",
        "cases",
        "results_sha256",
    }
    if _SIGNATURE_FIELD in results:
        fields.add(_SIGNATURE_FIELD)
    _require_exact_keys(results, expected=fields, label="results")
    _verify_seal(results, seal_field="results_sha256", label="results")
    if results.get("benchmark_id") != dataset.get("benchmark_id"):
        raise MonitoringReplayValidationError(
            "results benchmark_id does not match the dataset"
        )
    if results.get("dataset_sha256") != dataset.get("dataset_sha256"):
        raise MonitoringReplayValidationError(
            "results are not bound to the exact dataset seal"
        )
    generated_at = _require_datetime(
        results.get("generated_at"),
        "results.generated_at",
        now=current_time,
    )
    dataset_sealed_at = _require_datetime(
        dataset.get("sealed_at"),
        "dataset.sealed_at",
        now=current_time,
    )
    if generated_at < dataset_sealed_at:
        raise MonitoringReplayValidationError(
            "results cannot predate the sealed adjudicated dataset"
        )
    scope = str(dataset.get("benchmark_scope"))
    runtime_manifest = _validate_runtime_manifest(
        results.get("runtime_manifest"),
        scope=scope,
        repo_root=repo_root,
        verify_runtime_state=verify_runtime_state,
    )

    dataset_cases = {
        str(case["case_id"]): case
        for case in cast("list[dict[str, Any]]", dataset["cases"])
    }
    raw_cases = _require_list(results.get("cases"), "results.cases")
    case_ids: list[str] = []
    prediction_ids: list[str] = []
    for case_index, raw_case in enumerate(raw_cases):
        label = f"results.cases[{case_index}]"
        case_result = _require_mapping(raw_case, label)
        _require_exact_keys(
            case_result,
            expected={
                "case_id",
                "org_id",
                "source_report_id",
                "source_report_sha256",
                "runtime_manifest_sha256",
                "evaluated_at",
                "candidate_reviewer_minutes",
                "predictions",
            },
            label=label,
        )
        case_id = _require_text(case_result.get("case_id"), f"{label}.case_id")
        if case_id not in dataset_cases:
            raise MonitoringReplayValidationError(
                f"{label} is not bound to a dataset case"
            )
        expected_case = dataset_cases[case_id]
        org_id = _require_uuid_like(case_result.get("org_id"), f"{label}.org_id")
        report_id = _require_text(
            case_result.get("source_report_id"),
            f"{label}.source_report_id",
        )
        report_sha = _require_sha256(
            case_result.get("source_report_sha256"),
            f"{label}.source_report_sha256",
        )
        if (
            _require_sha256(
                case_result.get("runtime_manifest_sha256"),
                f"{label}.runtime_manifest_sha256",
            )
            != runtime_manifest["manifest_sha256"]
        ):
            raise MonitoringReplayValidationError(
                f"{label} is not bound to the exact runtime manifest"
            )
        if (
            org_id != expected_case["org_id"]
            or report_id != expected_case["source_report_id"]
            or report_sha != expected_case["source_report_sha256"]
        ):
            raise MonitoringReplayValidationError(
                f"{label} crosses the dataset tenant/report boundary"
            )
        evaluated_at = _require_datetime(
            case_result.get("evaluated_at"),
            f"{label}.evaluated_at",
            now=current_time,
        )
        expected_as_of = _require_datetime(
            expected_case["replay_as_of"],
            f"dataset case {case_id}.replay_as_of",
            now=current_time,
        )
        if evaluated_at != expected_as_of:
            raise MonitoringReplayValidationError(
                f"{label} is stale or evaluated beyond its exact replay cutoff"
            )
        if generated_at < evaluated_at:
            raise MonitoringReplayValidationError(
                f"{label} cannot be generated before its replay evaluation"
            )
        _require_number(
            case_result.get("candidate_reviewer_minutes"),
            f"{label}.candidate_reviewer_minutes",
        )
        events = {
            str(event["event_id"]): event
            for event in cast("list[dict[str, Any]]", expected_case["events"])
        }
        conclusion_ids = {
            str(conclusion["conclusion_id"])
            for conclusion in cast(
                "list[dict[str, Any]]",
                expected_case["conclusion_universe"],
            )
        }
        semantic_predictions: list[tuple[str, str, str]] = []
        for prediction_index, raw_prediction in enumerate(
            _require_list(case_result.get("predictions"), f"{label}.predictions")
        ):
            prediction_label = f"{label}.predictions[{prediction_index}]"
            prediction = _require_mapping(raw_prediction, prediction_label)
            _require_exact_keys(
                prediction,
                expected={
                    "prediction_id",
                    "org_id",
                    "source_report_id",
                    "source_report_sha256",
                    "event_id",
                    "conclusion_id",
                    "source_id",
                    "source_sha256",
                    "detected_at",
                    "status",
                },
                label=prediction_label,
            )
            prediction_id = _require_text(
                prediction.get("prediction_id"),
                f"{prediction_label}.prediction_id",
            )
            prediction_org = _require_uuid_like(
                prediction.get("org_id"),
                f"{prediction_label}.org_id",
            )
            prediction_report = _require_text(
                prediction.get("source_report_id"),
                f"{prediction_label}.source_report_id",
            )
            prediction_report_sha = _require_sha256(
                prediction.get("source_report_sha256"),
                f"{prediction_label}.source_report_sha256",
            )
            if (
                prediction_org != org_id
                or prediction_report != report_id
                or prediction_report_sha != report_sha
            ):
                raise MonitoringReplayValidationError(
                    f"{prediction_label} crosses the case tenant/report boundary"
                )
            event_id = _require_text(
                prediction.get("event_id"),
                f"{prediction_label}.event_id",
            )
            if event_id not in events:
                raise MonitoringReplayValidationError(
                    f"{prediction_label} references an unsealed or cross-case event"
                )
            conclusion_id = _require_text(
                prediction.get("conclusion_id"),
                f"{prediction_label}.conclusion_id",
            )
            if conclusion_id not in conclusion_ids:
                raise MonitoringReplayValidationError(
                    f"{prediction_label} references a conclusion outside the "
                    "sealed conclusion universe"
                )
            source_id = _require_text(
                prediction.get("source_id"),
                f"{prediction_label}.source_id",
            )
            source_sha = _require_sha256(
                prediction.get("source_sha256"),
                f"{prediction_label}.source_sha256",
            )
            source_event = events[event_id]
            if (
                source_id != source_event["source_id"]
                or source_sha != source_event["source_sha256"]
            ):
                raise MonitoringReplayValidationError(
                    f"{prediction_label} is not bound to the exact event source"
                )
            detected_at = _require_datetime(
                prediction.get("detected_at"),
                f"{prediction_label}.detected_at",
                now=current_time,
            )
            available_at = _require_datetime(
                source_event["available_at"],
                f"dataset event {event_id}.available_at",
                now=current_time,
            )
            if not available_at <= detected_at <= evaluated_at:
                raise MonitoringReplayValidationError(
                    f"{prediction_label} has a non-causal detection timestamp"
                )
            freshness_policy = cast(
                "dict[str, Any]",
                dataset["freshness_policy"],
            )
            if (
                detected_at - available_at
            ).total_seconds() > int(
                freshness_policy["max_detection_lag_seconds"]
            ):
                raise MonitoringReplayValidationError(
                    f"{prediction_label} exceeds the sealed detection "
                    "freshness policy"
                )
            if prediction.get("status") != "review_required":
                raise MonitoringReplayValidationError(
                    f"{prediction_label}.status must be review_required"
                )
            prediction_ids.append(prediction_id)
            semantic_predictions.append((event_id, conclusion_id, source_sha))
        _require_unique(
            (":".join(item) for item in semantic_predictions),
            f"{label}.predictions semantic keys",
        )
        case_ids.append(case_id)

    _require_unique(case_ids, "results.cases")
    _require_unique(prediction_ids, "results predictions")
    if set(case_ids) != set(dataset_cases):
        missing = sorted(set(dataset_cases) - set(case_ids))
        unexpected = sorted(set(case_ids) - set(dataset_cases))
        raise MonitoringReplayValidationError(
            "results must contain every dataset case exactly once; "
            f"missing={missing}, unexpected={unexpected}"
        )
    if scope == "production":
        _verify_production_signature(
            results,
            purpose="observed-results",
            label="results",
        )
    return results


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _reduction(candidate: int | float, baseline: int | float) -> float | None:
    if baseline <= 0:
        return None
    return 1.0 - (float(candidate) / float(baseline))


def score_monitoring_replay(
    dataset_payload: object,
    results_payload: object,
    *,
    now: datetime | None = None,
    repo_root: Path = REPO_ROOT,
    verify_runtime_state: bool = False,
) -> dict[str, Any]:
    """Validate and score an exact dataset/results pair."""

    dataset = validate_dataset(dataset_payload, now=now)
    results = validate_observed_results(
        results_payload,
        dataset=dataset,
        now=now,
        repo_root=repo_root,
        verify_runtime_state=verify_runtime_state,
    )
    dataset_cases = {
        str(case["case_id"]): cast("dict[str, Any]", case)
        for case in cast("list[dict[str, Any]]", dataset["cases"])
    }
    result_cases = {
        str(case["case_id"]): cast("dict[str, Any]", case)
        for case in cast("list[dict[str, Any]]", results["cases"])
    }

    expected_keys: set[tuple[str, str, str, str]] = set()
    predicted_keys: set[tuple[str, str, str, str]] = set()
    expected_pair_sources: dict[tuple[str, str, str], str] = {}
    predicted_pair_sources: dict[tuple[str, str, str], str] = {}
    baseline_false_alerts = 0
    baseline_reviewer_minutes = 0.0
    candidate_reviewer_minutes = 0.0
    total_events = 0
    case_metrics: list[dict[str, Any]] = []

    for case_id, case in dataset_cases.items():
        result_case = result_cases[case_id]
        expected_case_keys: set[tuple[str, str, str, str]] = set()
        for impact in cast("list[dict[str, Any]]", case["expected_impacts"]):
            key = (
                case_id,
                str(impact["event_id"]),
                str(impact["conclusion_id"]),
                str(impact["source_sha256"]),
            )
            expected_keys.add(key)
            expected_case_keys.add(key)
            expected_pair_sources[key[:3]] = key[3]
        predicted_case_keys: set[tuple[str, str, str, str]] = set()
        for prediction in cast("list[dict[str, Any]]", result_case["predictions"]):
            key = (
                case_id,
                str(prediction["event_id"]),
                str(prediction["conclusion_id"]),
                str(prediction["source_sha256"]),
            )
            predicted_keys.add(key)
            predicted_case_keys.add(key)
            predicted_pair_sources[key[:3]] = key[3]
        case_true_positives = len(expected_case_keys & predicted_case_keys)
        case_false_positives = len(predicted_case_keys - expected_case_keys)
        case_false_negatives = len(expected_case_keys - predicted_case_keys)
        case_metrics.append(
            {
                "case_id": case_id,
                "expected_material_impacts": len(expected_case_keys),
                "predicted_impacts": len(predicted_case_keys),
                "true_positives": case_true_positives,
                "false_positives": case_false_positives,
                "false_negatives": case_false_negatives,
                "material_recall": _rate(
                    case_true_positives,
                    len(expected_case_keys),
                ),
                "precision": (
                    _rate(case_true_positives, len(predicted_case_keys))
                    if predicted_case_keys
                    else (1.0 if not expected_case_keys else 0.0)
                ),
                "baseline_false_alert_count": int(
                    case["baseline_false_alert_count"]
                ),
                "candidate_false_alert_count": case_false_positives,
                "baseline_reviewer_minutes": float(
                    case["baseline_reviewer_minutes"]
                ),
                "candidate_reviewer_minutes": float(
                    result_case["candidate_reviewer_minutes"]
                ),
            }
        )
        baseline_false_alerts += int(case["baseline_false_alert_count"])
        baseline_reviewer_minutes += float(case["baseline_reviewer_minutes"])
        candidate_reviewer_minutes += float(
            result_case["candidate_reviewer_minutes"]
        )
        total_events += len(cast("list[Any]", case["events"]))

    true_positives = len(expected_keys & predicted_keys)
    false_positives = len(predicted_keys - expected_keys)
    false_negatives = len(expected_keys - predicted_keys)
    material_recall = _rate(true_positives, len(expected_keys))
    precision = (
        _rate(true_positives, len(predicted_keys))
        if predicted_keys
        else (1.0 if not expected_keys else 0.0)
    )
    comparable_pairs = set(expected_pair_sources) & set(predicted_pair_sources)
    provenance_mismatches = sorted(
        {
            "/".join(pair)
            for pair in comparable_pairs
            if expected_pair_sources[pair] != predicted_pair_sources[pair]
        }
    )
    provenance_fidelity = (
        _rate(
            len(comparable_pairs) - len(provenance_mismatches),
            len(comparable_pairs),
        )
        if comparable_pairs
        else (1.0 if not expected_keys else 0.0)
    )
    false_alert_reduction = _reduction(false_positives, baseline_false_alerts)
    reviewer_minute_reduction = _reduction(
        candidate_reviewer_minutes,
        baseline_reviewer_minutes,
    )
    scope = str(dataset["benchmark_scope"])
    approval = cast(
        "dict[str, Any] | None",
        dataset.get("counsel_burden_approval"),
    )
    counsel_approved_burden_pass = bool(
        scope == "production"
        and approval is not None
        and false_positives <= int(approval["max_false_alerts_total"])
        and _rate(false_positives, len(dataset_cases))
        <= float(approval["max_false_alerts_per_case"])
    )
    metric_checks = {
        "material_recall": material_recall >= MATERIAL_RECALL_MIN,
        "precision_or_counsel_approved_burden": (
            precision >= PRECISION_MIN or counsel_approved_burden_pass
        ),
        "false_alert_or_reviewer_minute_reduction": (
            (
                false_alert_reduction is not None
                and false_alert_reduction >= FALSE_ALERT_REDUCTION_MIN
            )
            or (
                reviewer_minute_reduction is not None
                and reviewer_minute_reduction >= REVIEWER_MINUTE_REDUCTION_MIN
            )
        ),
        "exact_changed_conclusion_source_provenance": (
            provenance_fidelity >= PROVENANCE_FIDELITY_MIN
            and not provenance_mismatches
        ),
        "fresh_complete_tenant_bound_replay": True,
    }
    metric_gate_passed = all(metric_checks.values())
    production_eligible = bool(
        scope == "production"
        and len(dataset_cases) >= MIN_PRODUCTION_CASES
        and total_events >= MIN_PRODUCTION_EVENTS
    )
    passed = bool(production_eligible and metric_gate_passed)
    failures = [name for name, value in metric_checks.items() if not value]
    if not production_eligible:
        failures.append(
            "fixture/non-production benchmark is non-credit and cannot satisfy release thresholds"
        )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark_id": dataset["benchmark_id"],
        "benchmark_scope": scope,
        "dataset_sha256": dataset["dataset_sha256"],
        "results_sha256": results["results_sha256"],
        "runtime_manifest_sha256": results["runtime_manifest"]["manifest_sha256"],
        "git_sha": results["runtime_manifest"]["git_sha"],
        "evidence_credit": "production" if production_eligible else "none",
        "production_eligible": production_eligible,
        "case_count": len(dataset_cases),
        "event_count": total_events,
        "expected_material_impact_count": len(expected_keys),
        "predicted_impact_count": len(predicted_keys),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "material_recall": material_recall,
        "precision": precision,
        "provenance_fidelity": provenance_fidelity,
        "provenance_mismatches": provenance_mismatches,
        "baseline_false_alert_count": baseline_false_alerts,
        "candidate_false_alert_count": false_positives,
        "false_alert_reduction": false_alert_reduction,
        "baseline_reviewer_minutes": baseline_reviewer_minutes,
        "candidate_reviewer_minutes": candidate_reviewer_minutes,
        "reviewer_minute_reduction": reviewer_minute_reduction,
        "counsel_approved_burden_pass": counsel_approved_burden_pass,
        "thresholds": {
            "material_recall_min": MATERIAL_RECALL_MIN,
            "precision_min": PRECISION_MIN,
            "false_alert_reduction_min": FALSE_ALERT_REDUCTION_MIN,
            "reviewer_minute_reduction_min": REVIEWER_MINUTE_REDUCTION_MIN,
            "provenance_fidelity_min": PROVENANCE_FIDELITY_MIN,
            "minimum_production_cases": MIN_PRODUCTION_CASES,
            "minimum_production_events": MIN_PRODUCTION_EVENTS,
        },
        "metric_checks": metric_checks,
        "metric_gate_passed": metric_gate_passed,
        "passed": passed,
        "failures": failures,
        "case_metrics": case_metrics,
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MonitoringReplayValidationError(
                f"JSON object contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def load_json(path: Path) -> object:
    """Load JSON while rejecting duplicate object keys and non-finite numbers."""

    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise MonitoringReplayValidationError(
                f"JSON artifact exceeds {MAX_JSON_BYTES} bytes"
            )
        raw = path.read_bytes()
        if len(raw) > MAX_JSON_BYTES:
            raise MonitoringReplayValidationError(
                f"JSON artifact exceeds {MAX_JSON_BYTES} bytes"
            )
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                MonitoringReplayValidationError(
                    f"JSON contains non-finite number {value}"
                )
            ),
        )
        stack: list[tuple[object, int]] = [(parsed, 1)]
        nodes = 0
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if nodes > MAX_JSON_NODES:
                raise MonitoringReplayValidationError(
                    f"JSON artifact exceeds {MAX_JSON_NODES} nodes"
                )
            if depth > MAX_JSON_DEPTH:
                raise MonitoringReplayValidationError(
                    f"JSON artifact exceeds nesting depth {MAX_JSON_DEPTH}"
                )
            if isinstance(value, dict):
                stack.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                stack.extend((item, depth + 1) for item in value)
        return parsed
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MonitoringReplayValidationError(
            f"could not load valid JSON from {path}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-fixture-runtime",
        action="store_true",
        help=(
            "Skip current-worktree verification for fixture development only. "
            "Production benchmarks always reject this mode."
        ),
    )
    args = parser.parse_args(argv)
    try:
        report = score_monitoring_replay(
            load_json(args.dataset),
            load_json(args.results),
            verify_runtime_state=not args.allow_fixture_runtime,
        )
    except MonitoringReplayValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report["passed"]:
        print(
            "[PASS] production monitoring replay: "
            f"recall={report['material_recall']:.3f}, "
            f"precision={report['precision']:.3f}"
        )
        return 0
    print(
        "[NO CREDIT] monitoring replay did not satisfy the production gate: "
        + "; ".join(report["failures"])
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
