"""Sealed offline benchmark for structure and Markush patent retrieval.

The runner consumes an adjudicated dataset and separately sealed observed
results. It performs no network calls and does not generate ground truth.
Passing fixture data is not a production recall claim; a production claim
requires a sufficiently large, independently curated sealed dataset.

Usage:
    python research/tools/benchmarks/markush_retrieval_benchmark.py \
        --dataset path/to/sealed-dataset.json \
        --results path/to/sealed-observed-results.json \
        --output path/to/score.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PositiveCategory = Literal[
    "exact",
    "scaffold",
    "developed_example",
    "markush_only",
]

_CATEGORIES: tuple[PositiveCategory, ...] = (
    "exact",
    "scaffold",
    "developed_example",
    "markush_only",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLICATION_ID = re.compile(r"^[A-Z]{2}[A-Z0-9]{5,24}$")
_MINIMUM_CASES_FOR_SCORING = 20
_MINIMUM_POSITIVES_PER_CATEGORY_FOR_SCORING = 10
# With zero observed failures, 299 independent observations are the smallest
# integer sample whose exact one-sided 95% upper error bound
# ``1 - 0.05 ** (1 / n)`` is below 1%.
_MINIMUM_CASES_FOR_PRODUCTION_CLAIM = 299
_MINIMUM_POSITIVES_PER_CATEGORY_FOR_PRODUCTION_CLAIM = 299
_PRODUCTION_POINT_THRESHOLD_FLOOR = 0.99
_PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR = 0.99
_PRODUCTION_MINIMUM_NEGATIVE_TO_POSITIVE_RATIO = 1.0
_ONE_SIDED_95_Z = 1.6448536269514722
_SIGNATURE_FIELD = "benchmark_signature"
_SIGNATURE_SCHEMA_VERSION = 1
_SIGNATURE_ALGORITHM = "Ed25519"
_RETRIEVAL_LANES = {
    "exact_structure",
    "scaffold_structure",
    "developed_example_structure",
    "patentscope_markush",
    "licensed_markush",
}
_MARKUSH_RETRIEVAL_LANES = {
    "patentscope_markush",
    "licensed_markush",
}
_MARKUSH_PRODUCTION_EVIDENCE_FIELDS = {
    "full_exact_structure_evidence_sha256",
    "stereo_aware_evidence_sha256",
    "variable_table_evidence_sha256",
}


class BenchmarkValidationError(ValueError):
    """A sealed benchmark artifact violates its contract."""


class CategoryMetric(TypedDict):
    true_positives: int
    positives: int
    recall: float
    recall_lower_bound_95: float
    threshold: float
    passed: bool


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


def _signature_material(purpose: str, payload: dict[str, Any]) -> bytes:
    return f"praviar:markush-retrieval:{purpose}:v1\0".encode() + _canonical_json_bytes(
        payload
    )


def sign_benchmark_artifact(
    payload: dict[str, Any],
    *,
    purpose: Literal["dataset", "observed-results"],
    private_key: Ed25519PrivateKey,
    key_id: str,
) -> dict[str, Any]:
    """Issue an independent Ed25519 signature over a sealed artifact."""
    normalized_key_id = key_id.strip()
    if not normalized_key_id:
        raise ValueError("benchmark signature key_id is required")
    unsigned = {key: value for key, value in payload.items() if key != _SIGNATURE_FIELD}
    signature = private_key.sign(_signature_material(purpose, unsigned))
    return {
        **unsigned,
        _SIGNATURE_FIELD: {
            "schema_version": _SIGNATURE_SCHEMA_VERSION,
            "algorithm": _SIGNATURE_ALGORITHM,
            "key_id": normalized_key_id,
            "purpose": purpose,
            "signature_base64": base64.b64encode(signature).decode(),
        },
    }


def _verify_production_signature(
    payload: dict[str, Any],
    *,
    purpose: Literal["dataset", "observed-results"],
    label: str,
) -> None:
    signature = _require_mapping(payload.get(_SIGNATURE_FIELD), f"{label}.signature")
    if set(signature) != {
        "schema_version",
        "algorithm",
        "key_id",
        "purpose",
        "signature_base64",
    }:
        raise BenchmarkValidationError(f"{label} signature schema is invalid")
    if (
        signature.get("schema_version") != _SIGNATURE_SCHEMA_VERSION
        or signature.get("algorithm") != _SIGNATURE_ALGORITHM
        or signature.get("purpose") != purpose
    ):
        raise BenchmarkValidationError(f"{label} signature contract is invalid")
    env_prefix = (
        "MARKUSH_BENCHMARK_DATASET"
        if purpose == "dataset"
        else "MARKUSH_BENCHMARK_RESULTS"
    )
    expected_key_id = os.environ.get(f"{env_prefix}_KEY_ID", "").strip()
    public_key_base64 = os.environ.get(f"{env_prefix}_PUBLIC_KEY", "").strip()
    if not expected_key_id or not public_key_base64:
        raise BenchmarkValidationError(
            "production benchmark verification key is not configured"
        )
    if signature.get("key_id") != expected_key_id:
        raise BenchmarkValidationError(f"{label} signature key is not trusted")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_base64, validate=True)
        )
        signature_bytes = base64.b64decode(
            str(signature.get("signature_base64") or ""),
            validate=True,
        )
    except (TypeError, ValueError):
        raise BenchmarkValidationError(f"{label} signature is malformed") from None
    unsigned = {key: value for key, value in payload.items() if key != _SIGNATURE_FIELD}
    try:
        public_key.verify(
            signature_bytes,
            _signature_material(purpose, unsigned),
        )
    except (InvalidSignature, TypeError, ValueError):
        raise BenchmarkValidationError(f"{label} signature mismatch") from None


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkValidationError(f"{label} must be an object")
    return cast("dict[str, Any]", value)


def _require_exact_keys(
    value: dict[str, Any],
    *,
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        unexpected = sorted(set(value) - expected)
        missing = sorted(expected - set(value))
        raise BenchmarkValidationError(
            f"{label} fields mismatch; missing={missing}, unexpected={unexpected}"
        )


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BenchmarkValidationError(f"{label} must be an array")
    return value


def _require_nonempty_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise BenchmarkValidationError(f"{label} must be non-empty")
    return text


def _require_sha256(value: object, label: str) -> str:
    digest = _require_nonempty_text(value, label).lower()
    if not _SHA256.fullmatch(digest):
        raise BenchmarkValidationError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _require_aware_datetime(value: object, label: str) -> datetime:
    text = _require_nonempty_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BenchmarkValidationError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BenchmarkValidationError(f"{label} must include a UTC offset")
    return parsed


def _wilson_lower_bound(successes: int, observations: int) -> float:
    """Return the one-sided 95% Wilson lower confidence bound."""
    if observations <= 0:
        return 0.0
    proportion = successes / observations
    z_squared = _ONE_SIDED_95_Z**2
    denominator = 1.0 + z_squared / observations
    centre = proportion + z_squared / (2.0 * observations)
    spread = _ONE_SIDED_95_Z * math.sqrt(
        (proportion * (1.0 - proportion) + z_squared / (4.0 * observations))
        / observations
    )
    return max(0.0, (centre - spread) / denominator)


def _require_allowlisted_production_value(
    value: object,
    *,
    env_name: str,
    label: str,
) -> str:
    normalized = _require_nonempty_text(value, label)
    allowed = {
        item.strip() for item in os.environ.get(env_name, "").split(",") if item.strip()
    }
    if not allowed:
        raise BenchmarkValidationError(
            f"{label} production allowlist is not configured"
        )
    if normalized not in allowed:
        raise BenchmarkValidationError(f"{label} is not production-allowlisted")
    return normalized


def _publication_id(value: object, label: str) -> str:
    publication_id = re.sub(r"[\s,./-]", "", str(value or "").upper())
    if not _PUBLICATION_ID.fullmatch(publication_id):
        raise BenchmarkValidationError(f"{label} is not a normalized publication ID")
    return publication_id


def _verify_seal(payload: dict[str, Any], seal_field: str, label: str) -> str:
    seal = _require_sha256(payload.get(seal_field), f"{label}.{seal_field}")
    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {seal_field, _SIGNATURE_FIELD}
    }
    if _sha256(unsealed) != seal:
        raise BenchmarkValidationError(f"{label} seal mismatch")
    return seal


def seal_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a derived dataset seal; intended for curation tooling."""
    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {"dataset_sha256", _SIGNATURE_FIELD}
    }
    return {**unsealed, "dataset_sha256": _sha256(unsealed)}


def seal_observed_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a derived results seal; intended for runner adapters."""
    unsealed = {
        key: value
        for key, value in payload.items()
        if key not in {"results_sha256", _SIGNATURE_FIELD}
    }
    return {**unsealed, "results_sha256": _sha256(unsealed)}


def validate_dataset(payload: object) -> dict[str, Any]:
    """Validate structure, curation provenance, minimum size, and dataset seal."""
    dataset = _require_mapping(payload, "dataset")
    if dataset.get("schema_version") != "markush-retrieval-benchmark-v2":
        raise BenchmarkValidationError("dataset schema_version is unsupported")
    dataset_fields = {
        "schema_version",
        "benchmark_id",
        "benchmark_scope",
        "sealed_at",
        "curation_methodology",
        "curation_organization",
        "curation_protocol_sha256",
        "curation_artifact_sha256",
        "candidate_pool_protocol_sha256",
        "retrieval_cutoff",
        "thresholds",
        "cases",
        "dataset_sha256",
    }
    if _SIGNATURE_FIELD in dataset:
        dataset_fields.add(_SIGNATURE_FIELD)
    _require_exact_keys(dataset, expected=dataset_fields, label="dataset")
    _verify_seal(dataset, "dataset_sha256", "dataset")
    benchmark_id = _require_nonempty_text(
        dataset.get("benchmark_id"),
        "dataset.benchmark_id",
    )
    scope = dataset.get("benchmark_scope")
    if scope not in {"fixture", "production"}:
        raise BenchmarkValidationError(
            "dataset.benchmark_scope must be fixture or production"
        )
    _require_aware_datetime(dataset.get("sealed_at"), "dataset.sealed_at")
    _require_nonempty_text(
        dataset.get("curation_methodology"), "dataset.curation_methodology"
    )
    curation_organization = _require_nonempty_text(
        dataset.get("curation_organization"),
        "dataset.curation_organization",
    )
    if scope == "production":
        _require_allowlisted_production_value(
            benchmark_id,
            env_name="MARKUSH_BENCHMARK_ALLOWED_DATASET_IDS",
            label="dataset.benchmark_id",
        )
        _require_allowlisted_production_value(
            curation_organization,
            env_name="MARKUSH_BENCHMARK_ALLOWED_CURATOR_ORGANIZATIONS",
            label="dataset.curation_organization",
        )
    _require_sha256(
        dataset.get("curation_protocol_sha256"),
        "dataset.curation_protocol_sha256",
    )
    _require_sha256(
        dataset.get("curation_artifact_sha256"),
        "dataset.curation_artifact_sha256",
    )
    _require_sha256(
        dataset.get("candidate_pool_protocol_sha256"),
        "dataset.candidate_pool_protocol_sha256",
    )
    thresholds = _require_mapping(dataset.get("thresholds"), "dataset.thresholds")
    _require_exact_keys(
        thresholds,
        expected={
            "category_recall_min",
            "family_recall_min",
            "family_precision_min",
        },
        label="dataset.thresholds",
    )
    category_thresholds = _require_mapping(
        thresholds.get("category_recall_min"),
        "dataset.thresholds.category_recall_min",
    )
    _require_exact_keys(
        category_thresholds,
        expected=set(_CATEGORIES),
        label="dataset.thresholds.category_recall_min",
    )
    for category in _CATEGORIES:
        threshold = category_thresholds.get(category)
        if (
            not isinstance(threshold, (int, float))
            or not 0.0 <= float(threshold) <= 1.0
        ):
            raise BenchmarkValidationError(f"invalid {category} recall threshold")
        if (
            scope == "production"
            and float(threshold) < _PRODUCTION_POINT_THRESHOLD_FLOOR
        ):
            raise BenchmarkValidationError(
                f"production {category} recall threshold must be at least "
                f"{_PRODUCTION_POINT_THRESHOLD_FLOOR:.2f}"
            )
    for key in ("family_recall_min", "family_precision_min"):
        threshold = thresholds.get(key)
        if (
            not isinstance(threshold, (int, float))
            or not 0.0 <= float(threshold) <= 1.0
        ):
            raise BenchmarkValidationError(f"invalid {key} threshold")
        if (
            scope == "production"
            and float(threshold) < _PRODUCTION_POINT_THRESHOLD_FLOOR
        ):
            raise BenchmarkValidationError(
                f"production {key} threshold must be at least "
                f"{_PRODUCTION_POINT_THRESHOLD_FLOOR:.2f}"
            )
    cutoff = dataset.get("retrieval_cutoff")
    if not isinstance(cutoff, int) or isinstance(cutoff, bool) or cutoff < 1:
        raise BenchmarkValidationError(
            "dataset.retrieval_cutoff must be a positive integer"
        )
    if scope == "production":
        expected_cutoff = os.environ.get(
            "MARKUSH_BENCHMARK_EXPECTED_CUTOFF",
            "",
        ).strip()
        if not expected_cutoff or not expected_cutoff.isdigit():
            raise BenchmarkValidationError(
                "production retrieval cutoff policy is not configured"
            )
        if cutoff != int(expected_cutoff):
            raise BenchmarkValidationError(
                "production retrieval_cutoff does not match frozen policy"
            )

    cases = _require_list(dataset.get("cases"), "dataset.cases")
    if len(cases) < _MINIMUM_CASES_FOR_SCORING:
        raise BenchmarkValidationError(
            "sealed benchmark requires at least "
            f"{_MINIMUM_CASES_FOR_SCORING} independently curated cases"
        )
    if scope == "production" and len(cases) < _MINIMUM_CASES_FOR_PRODUCTION_CLAIM:
        raise BenchmarkValidationError(
            "production benchmark requires at least "
            f"{_MINIMUM_CASES_FOR_PRODUCTION_CLAIM} independently curated cases"
        )
    case_ids: set[str] = set()
    query_hashes: set[str] = set()
    category_counts: dict[PositiveCategory, int] = defaultdict(int)
    category_query_family_units: dict[
        PositiveCategory,
        set[tuple[str, str]],
    ] = defaultdict(set)
    for case_index, raw_case in enumerate(cases):
        case = _require_mapping(raw_case, f"dataset.cases[{case_index}]")
        _require_exact_keys(
            case,
            expected={
                "case_id",
                "query_structure_sha256",
                "adjudicator_identity",
                "reviewer_identity",
                "positives",
                "adjudicated_candidates",
            },
            label=f"dataset case {case_index}",
        )
        case_id = _require_nonempty_text(
            case.get("case_id"), f"case {case_index}.case_id"
        )
        if case_id in case_ids:
            raise BenchmarkValidationError(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        query_structure_sha256 = _require_sha256(
            case.get("query_structure_sha256"),
            f"case {case_id}.query_structure_sha256",
        )
        if scope == "production" and query_structure_sha256 in query_hashes:
            raise BenchmarkValidationError(
                "production benchmark cases require unique query structure digests"
            )
        query_hashes.add(query_structure_sha256)
        _require_nonempty_text(
            case.get("adjudicator_identity"),
            f"case {case_id}.adjudicator_identity",
        )
        reviewer = _require_nonempty_text(
            case.get("reviewer_identity"),
            f"case {case_id}.reviewer_identity",
        )
        if reviewer == case.get("adjudicator_identity"):
            raise BenchmarkValidationError(
                f"case {case_id} adjudicator and reviewer must be distinct"
            )
        positives = _require_list(case.get("positives"), f"case {case_id}.positives")
        if not positives:
            raise BenchmarkValidationError(
                f"case {case_id} has no positive publications"
            )
        publication_ids: set[str] = set()
        positive_families_by_publication: dict[str, str] = {}
        case_categories: set[PositiveCategory] = set()
        for positive_index, raw_positive in enumerate(positives):
            positive = _require_mapping(
                raw_positive,
                f"case {case_id}.positives[{positive_index}]",
            )
            raw_category = positive.get("category")
            positive_fields = {
                "publication_id",
                "family_id",
                "category",
                "adjudication_evidence_sha256",
            }
            if scope == "production" and raw_category == "markush_only":
                positive_fields.update(_MARKUSH_PRODUCTION_EVIDENCE_FIELDS)
            _require_exact_keys(
                positive,
                expected=positive_fields,
                label=f"case {case_id} positive",
            )
            publication_id = _publication_id(
                positive.get("publication_id"),
                f"case {case_id} positive publication_id",
            )
            if publication_id in publication_ids:
                raise BenchmarkValidationError(
                    f"case {case_id} contains duplicate publication {publication_id}"
                )
            publication_ids.add(publication_id)
            family_id = _require_nonempty_text(
                positive.get("family_id"),
                f"case {case_id} positive family_id",
            )
            positive_families_by_publication[publication_id] = family_id
            if raw_category not in _CATEGORIES:
                raise BenchmarkValidationError(
                    f"case {case_id} positive category is unsupported"
                )
            category_counts[cast("PositiveCategory", raw_category)] += 1
            typed_category = cast("PositiveCategory", raw_category)
            case_categories.add(typed_category)
            category_query_family_units[typed_category].add(
                (query_structure_sha256, family_id)
            )
            _require_sha256(
                positive.get("adjudication_evidence_sha256"),
                f"case {case_id} positive evidence",
            )
            if scope == "production" and raw_category == "markush_only":
                for evidence_field in sorted(_MARKUSH_PRODUCTION_EVIDENCE_FIELDS):
                    _require_sha256(
                        positive.get(evidence_field),
                        f"case {case_id} markush_only {evidence_field}",
                    )

        candidates = _require_list(
            case.get("adjudicated_candidates"),
            f"case {case_id}.adjudicated_candidates",
        )
        if not candidates:
            raise BenchmarkValidationError(
                f"case {case_id} has no adjudicated candidate pool"
            )
        candidate_judgments: dict[str, tuple[str, str]] = {}
        for candidate_index, raw_candidate in enumerate(candidates):
            candidate = _require_mapping(
                raw_candidate,
                f"case {case_id}.adjudicated_candidates[{candidate_index}]",
            )
            _require_exact_keys(
                candidate,
                expected={
                    "publication_id",
                    "family_id",
                    "judgment",
                    "adjudication_evidence_sha256",
                },
                label=f"case {case_id} adjudicated candidate",
            )
            candidate_publication_id = _publication_id(
                candidate.get("publication_id"),
                f"case {case_id} candidate publication_id",
            )
            if candidate_publication_id in candidate_judgments:
                raise BenchmarkValidationError(
                    f"case {case_id} contains duplicate adjudicated candidate "
                    f"{candidate_publication_id}"
                )
            candidate_family_id = _require_nonempty_text(
                candidate.get("family_id"),
                f"case {case_id} candidate family_id",
            )
            judgment = candidate.get("judgment")
            if judgment not in {"relevant", "not_relevant"}:
                raise BenchmarkValidationError(
                    f"case {case_id} candidate judgment is unsupported"
                )
            _require_sha256(
                candidate.get("adjudication_evidence_sha256"),
                f"case {case_id} candidate evidence",
            )
            candidate_judgments[candidate_publication_id] = (
                candidate_family_id,
                str(judgment),
            )

        relevant_candidates = {
            publication_id: family_and_judgment[0]
            for publication_id, family_and_judgment in candidate_judgments.items()
            if family_and_judgment[1] == "relevant"
        }
        if relevant_candidates != positive_families_by_publication:
            raise BenchmarkValidationError(
                f"case {case_id} positives do not exactly match relevant "
                "adjudicated candidates"
            )
        negative_count = sum(
            judgment == "not_relevant" for _, judgment in candidate_judgments.values()
        )
        if (
            scope == "production"
            and negative_count
            < len(positive_families_by_publication)
            * _PRODUCTION_MINIMUM_NEGATIVE_TO_POSITIVE_RATIO
        ):
            raise BenchmarkValidationError(
                f"case {case_id} production candidate pool requires at least "
                "one adjudicated negative per positive"
            )
        if scope == "production" and case_categories != set(_CATEGORIES):
            raise BenchmarkValidationError(
                f"case {case_id} production qrels require at least one "
                "positive in every retrieval category"
            )

    for category in _CATEGORIES:
        if category_counts[category] < _MINIMUM_POSITIVES_PER_CATEGORY_FOR_SCORING:
            raise BenchmarkValidationError(
                f"sealed benchmark requires at least "
                f"{_MINIMUM_POSITIVES_PER_CATEGORY_FOR_SCORING} "
                f"{category} positives"
            )
        if (
            scope == "production"
            and category_counts[category]
            < _MINIMUM_POSITIVES_PER_CATEGORY_FOR_PRODUCTION_CLAIM
        ):
            raise BenchmarkValidationError(
                "production benchmark requires at least "
                f"{_MINIMUM_POSITIVES_PER_CATEGORY_FOR_PRODUCTION_CLAIM} "
                f"{category} positives"
            )
        if (
            scope == "production"
            and len(category_query_family_units[category])
            < _MINIMUM_POSITIVES_PER_CATEGORY_FOR_PRODUCTION_CLAIM
        ):
            raise BenchmarkValidationError(
                "production benchmark requires at least "
                f"{_MINIMUM_POSITIVES_PER_CATEGORY_FOR_PRODUCTION_CLAIM} "
                f"distinct query-family units for {category}"
            )
    if scope == "production":
        _verify_production_signature(
            dataset,
            purpose="dataset",
            label="dataset",
        )
    return dataset


def validate_observed_results(
    payload: object,
    *,
    dataset: dict[str, Any],
) -> dict[str, Any]:
    """Validate independently produced top-k results and their seal."""
    observed = _require_mapping(payload, "observed_results")
    if observed.get("schema_version") != "markush-retrieval-observed-v2":
        raise BenchmarkValidationError("observed results schema_version is unsupported")
    observed_fields = {
        "schema_version",
        "benchmark_id",
        "benchmark_scope",
        "dataset_sha256",
        "executed_at",
        "system_identity",
        "system_version",
        "source_tree_sha256",
        "retrieval_configuration_sha256",
        "execution_receipt_sha256",
        "cases",
        "results_sha256",
    }
    if _SIGNATURE_FIELD in observed:
        observed_fields.add(_SIGNATURE_FIELD)
    _require_exact_keys(
        observed,
        expected=observed_fields,
        label="observed results",
    )
    _verify_seal(observed, "results_sha256", "observed_results")
    if observed.get("benchmark_id") != dataset.get("benchmark_id"):
        raise BenchmarkValidationError("observed benchmark_id does not match dataset")
    if observed.get("benchmark_scope") != dataset.get("benchmark_scope"):
        raise BenchmarkValidationError(
            "observed benchmark_scope does not match dataset"
        )
    if observed.get("dataset_sha256") != dataset.get("dataset_sha256"):
        raise BenchmarkValidationError(
            "observed results are bound to a different dataset"
        )
    executed_at = _require_aware_datetime(
        observed.get("executed_at"),
        "observed.executed_at",
    )
    sealed_at = _require_aware_datetime(dataset.get("sealed_at"), "dataset.sealed_at")
    if executed_at < sealed_at:
        raise BenchmarkValidationError(
            "observed retrieval must execute after the benchmark is sealed"
        )
    _require_nonempty_text(observed.get("system_identity"), "observed.system_identity")
    if dataset["benchmark_scope"] == "production":
        _require_allowlisted_production_value(
            observed.get("system_identity"),
            env_name="MARKUSH_BENCHMARK_ALLOWED_SYSTEM_IDENTITIES",
            label="observed.system_identity",
        )
    _require_nonempty_text(observed.get("system_version"), "observed.system_version")
    _require_sha256(observed.get("source_tree_sha256"), "observed.source_tree_sha256")
    _require_sha256(
        observed.get("retrieval_configuration_sha256"),
        "observed.retrieval_configuration_sha256",
    )
    _require_sha256(
        observed.get("execution_receipt_sha256"),
        "observed.execution_receipt_sha256",
    )

    rows = _require_list(observed.get("cases"), "observed.cases")
    dataset_case_ids = {str(case["case_id"]) for case in dataset["cases"]}
    if len(rows) != len(dataset_case_ids):
        raise BenchmarkValidationError(
            "observed results must contain every dataset case once"
        )
    observed_case_ids: set[str] = set()
    cutoff = int(dataset["retrieval_cutoff"])
    candidate_publications_by_case = {
        str(case["case_id"]): {
            _publication_id(
                candidate["publication_id"],
                "adjudicated candidate publication",
            )
            for candidate in case["adjudicated_candidates"]
        }
        for case in dataset["cases"]
    }
    markush_publications_by_case = {
        str(case["case_id"]): {
            _publication_id(
                positive["publication_id"],
                "Markush positive publication",
            )
            for positive in case["positives"]
            if positive["category"] == "markush_only"
        }
        for case in dataset["cases"]
    }
    for row_index, raw_row in enumerate(rows):
        row = _require_mapping(raw_row, f"observed.cases[{row_index}]")
        _require_exact_keys(
            row,
            expected={"case_id", "case_execution_receipt_sha256", "retrieved"},
            label=f"observed case row {row_index}",
        )
        case_id = _require_nonempty_text(row.get("case_id"), "observed case_id")
        if case_id not in dataset_case_ids or case_id in observed_case_ids:
            raise BenchmarkValidationError(
                f"unknown or duplicate observed case: {case_id}"
            )
        observed_case_ids.add(case_id)
        _require_sha256(
            row.get("case_execution_receipt_sha256"),
            f"observed case {case_id} execution receipt",
        )
        retrieved = _require_list(
            row.get("retrieved"), f"observed case {case_id}.retrieved"
        )
        if len(retrieved) > cutoff:
            raise BenchmarkValidationError(
                f"observed case {case_id} exceeds retrieval_cutoff={cutoff}"
            )
        publication_ids: set[str] = set()
        for result_index, raw_result in enumerate(retrieved):
            result = _require_mapping(
                raw_result,
                f"observed case {case_id}.retrieved[{result_index}]",
            )
            publication_id = _publication_id(
                result.get("publication_id"),
                f"observed case {case_id} publication_id",
            )
            result_fields = {
                "publication_id",
                "rank",
                "retrieval_lanes",
                "retrieval_receipt_sha256",
            }
            if (
                dataset["benchmark_scope"] == "production"
                and publication_id in markush_publications_by_case[case_id]
            ):
                result_fields.update(_MARKUSH_PRODUCTION_EVIDENCE_FIELDS)
            _require_exact_keys(
                result,
                expected=result_fields,
                label=f"observed case {case_id} retrieved result",
            )
            if publication_id in publication_ids:
                raise BenchmarkValidationError(
                    f"observed case {case_id} has duplicate publication {publication_id}"
                )
            publication_ids.add(publication_id)
            rank = result.get("rank")
            if (
                not isinstance(rank, int)
                or isinstance(rank, bool)
                or rank != result_index + 1
            ):
                raise BenchmarkValidationError(
                    f"observed case {case_id} ranks must be contiguous and "
                    "match result order"
                )
            retrieval_lanes = _require_list(
                result.get("retrieval_lanes"),
                f"observed case {case_id} retrieval_lanes",
            )
            if (
                not retrieval_lanes
                or any(lane not in _RETRIEVAL_LANES for lane in retrieval_lanes)
                or len(retrieval_lanes) != len(set(retrieval_lanes))
            ):
                raise BenchmarkValidationError(
                    f"observed case {case_id} retrieval lanes are invalid"
                )
            _require_sha256(
                result.get("retrieval_receipt_sha256"),
                f"observed case {case_id} retrieval receipt",
            )
            if (
                dataset["benchmark_scope"] == "production"
                and publication_id in markush_publications_by_case[case_id]
            ):
                for evidence_field in sorted(_MARKUSH_PRODUCTION_EVIDENCE_FIELDS):
                    _require_sha256(
                        result.get(evidence_field),
                        f"observed case {case_id} Markush result {evidence_field}",
                    )
            if publication_id not in candidate_publications_by_case[case_id]:
                raise BenchmarkValidationError(
                    f"observed case {case_id} publication {publication_id} "
                    "is unjudged or outside the sealed candidate pool"
                )
    if dataset["benchmark_scope"] == "production":
        dataset_signature = _require_mapping(
            dataset.get(_SIGNATURE_FIELD),
            "dataset.signature",
        )
        observed_signature = _require_mapping(
            observed.get(_SIGNATURE_FIELD),
            "observed results.signature",
        )
        if dataset_signature.get("key_id") == observed_signature.get("key_id"):
            raise BenchmarkValidationError(
                "production dataset and observed results require distinct signing keys"
            )
        if (
            os.environ.get(
                "MARKUSH_BENCHMARK_DATASET_PUBLIC_KEY",
                "",
            ).strip()
            == os.environ.get(
                "MARKUSH_BENCHMARK_RESULTS_PUBLIC_KEY",
                "",
            ).strip()
        ):
            raise BenchmarkValidationError(
                "production dataset and observed results require distinct public keys"
            )
        _verify_production_signature(
            observed,
            purpose="observed-results",
            label="observed results",
        )
    return observed


def score_retrieval_benchmark(
    dataset_payload: object,
    observed_payload: object,
) -> dict[str, Any]:
    """Score exact/scaffold/example/Markush recall and family metrics."""
    dataset = validate_dataset(dataset_payload)
    observed = validate_observed_results(observed_payload, dataset=dataset)
    observed_by_case = {str(row["case_id"]): row for row in observed["cases"]}
    category_true_positives: dict[PositiveCategory, int] = defaultdict(int)
    category_positives: dict[PositiveCategory, int] = defaultdict(int)
    family_true_positives = 0
    family_positives = 0
    family_retrieved = 0
    markush_only_ordinary_lane_hits = 0
    markush_only_markush_lane_hits = 0

    for case in dataset["cases"]:
        case_id = str(case["case_id"])
        retrieved = observed_by_case[case_id]["retrieved"]
        retrieved_publications = {
            _publication_id(row["publication_id"], "retrieved publication")
            for row in retrieved
        }
        retrieved_by_publication = {
            _publication_id(
                row["publication_id"],
                "retrieved publication",
            ): row
            for row in retrieved
        }
        candidate_by_publication = {
            _publication_id(
                candidate["publication_id"],
                "adjudicated candidate publication",
            ): candidate
            for candidate in case["adjudicated_candidates"]
        }
        retrieved_families = {
            str(candidate_by_publication[publication_id]["family_id"]).strip()
            for publication_id in retrieved_publications
        }
        positive_families = {
            str(positive["family_id"]).strip() for positive in case["positives"]
        }
        family_true_positives += len(retrieved_families & positive_families)
        family_positives += len(positive_families)
        family_retrieved += len(retrieved_families)
        for positive in case["positives"]:
            category = cast("PositiveCategory", positive["category"])
            category_positives[category] += 1
            publication_id = _publication_id(
                positive["publication_id"],
                "positive publication",
            )
            retrieved_result = retrieved_by_publication.get(publication_id)
            retrieval_lanes = (
                set(retrieved_result["retrieval_lanes"])
                if retrieved_result is not None
                else set()
            )
            if category == "markush_only":
                if retrieval_lanes & _MARKUSH_RETRIEVAL_LANES:
                    markush_only_markush_lane_hits += 1
                if retrieval_lanes - _MARKUSH_RETRIEVAL_LANES:
                    markush_only_ordinary_lane_hits += 1
            if retrieved_result is not None and (
                category != "markush_only"
                or bool(retrieval_lanes & _MARKUSH_RETRIEVAL_LANES)
            ):
                category_true_positives[category] += 1

    category_metrics: dict[PositiveCategory, CategoryMetric] = {}
    failures: list[str] = []
    thresholds = dataset["thresholds"]
    for category in _CATEGORIES:
        positives = category_positives[category]
        recall = category_true_positives[category] / positives
        recall_lower_bound = _wilson_lower_bound(
            category_true_positives[category],
            positives,
        )
        threshold = float(thresholds["category_recall_min"][category])
        confidence_passed = (
            dataset["benchmark_scope"] != "production"
            or recall_lower_bound >= _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR
        )
        passed = recall >= threshold and confidence_passed
        category_metrics[category] = {
            "true_positives": category_true_positives[category],
            "positives": positives,
            "recall": recall,
            "recall_lower_bound_95": recall_lower_bound,
            "threshold": threshold,
            "passed": passed,
        }
        if not passed:
            failures.append(
                f"{category} recall {recall:.4f} is below threshold {threshold:.4f}"
            )
        if (
            dataset["benchmark_scope"] == "production"
            and recall_lower_bound < _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR
        ):
            failures.append(
                f"{category} recall one-sided 95% lower bound "
                f"{recall_lower_bound:.4f} is below "
                f"{_PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR:.4f}"
            )

    family_recall = family_true_positives / family_positives
    family_precision = (
        family_true_positives / family_retrieved if family_retrieved else 0.0
    )
    family_recall_lower_bound = _wilson_lower_bound(
        family_true_positives,
        family_positives,
    )
    family_precision_lower_bound = _wilson_lower_bound(
        family_true_positives,
        family_retrieved,
    )
    family_recall_threshold = float(thresholds["family_recall_min"])
    family_precision_threshold = float(thresholds["family_precision_min"])
    if family_recall < family_recall_threshold:
        failures.append(
            f"family recall {family_recall:.4f} is below "
            f"threshold {family_recall_threshold:.4f}"
        )
    if family_precision < family_precision_threshold:
        failures.append(
            f"family precision {family_precision:.4f} is below "
            f"threshold {family_precision_threshold:.4f}"
        )
    if dataset["benchmark_scope"] == "production":
        if family_recall_lower_bound < _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR:
            failures.append(
                "family recall one-sided 95% lower bound "
                f"{family_recall_lower_bound:.4f} is below "
                f"{_PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR:.4f}"
            )
        if family_precision_lower_bound < _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR:
            failures.append(
                "family precision one-sided 95% lower bound "
                f"{family_precision_lower_bound:.4f} is below "
                f"{_PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR:.4f}"
            )
        failures.append(
            "production claim is blocked until a separately trusted black-box "
            "execution harness proves the results signer could not access hidden qrels"
        )

    score_payload = {
        "schema_version": "markush-retrieval-score-v2",
        "benchmark_id": dataset["benchmark_id"],
        "benchmark_scope": dataset["benchmark_scope"],
        "dataset_sha256": dataset["dataset_sha256"],
        "results_sha256": observed["results_sha256"],
        "case_count": len(dataset["cases"]),
        "retrieval_cutoff": dataset["retrieval_cutoff"],
        "category_metrics": category_metrics,
        "family_metrics": {
            "true_positive_families": family_true_positives,
            "positive_families": family_positives,
            "retrieved_families": family_retrieved,
            "recall": family_recall,
            "recall_lower_bound_95": family_recall_lower_bound,
            "recall_threshold": family_recall_threshold,
            "precision": family_precision,
            "precision_lower_bound_95": family_precision_lower_bound,
            "precision_threshold": family_precision_threshold,
            "passed": (
                family_recall >= family_recall_threshold
                and family_precision >= family_precision_threshold
                and (
                    dataset["benchmark_scope"] != "production"
                    or (
                        family_recall_lower_bound
                        >= _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR
                        and family_precision_lower_bound
                        >= _PRODUCTION_ONE_SIDED_CONFIDENCE_FLOOR
                    )
                )
            ),
        },
        "markush_lane_ablation": {
            "markush_only_true_positives_from_markush_lanes": (
                markush_only_markush_lane_hits
            ),
            "markush_only_hits_also_found_by_ordinary_lanes": (
                markush_only_ordinary_lane_hits
            ),
            "markush_only_positive_count": category_positives["markush_only"],
        },
        "passed": not failures,
        "production_claim_eligible": False,
        "failures": failures,
        "claim_boundary": (
            "This score is valid only for the sealed dataset and observed top-k "
            "artifact. Fixture results do not establish production corpus recall."
        ),
    }
    return {**score_payload, "score_sha256": _sha256(score_payload)}


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkValidationError(
            f"cannot load {path}: {type(exc).__name__}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        score = score_retrieval_benchmark(
            _load_json(args.dataset),
            _load_json(args.results),
        )
    except BenchmarkValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(score, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if score["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
