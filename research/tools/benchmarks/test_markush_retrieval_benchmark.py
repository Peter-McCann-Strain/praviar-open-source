from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from research.tools.benchmarks.markush_retrieval_benchmark import (
    BenchmarkValidationError,
    score_retrieval_benchmark,
    seal_dataset,
    seal_observed_results,
    sign_benchmark_artifact,
)

_CATEGORIES = ("exact", "scaffold", "developed_example", "markush_only")
_SYNTHETIC_DATASET_KEY_ID = "fixture"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _dataset(
    *,
    case_count: int = 20,
    benchmark_scope: str = "fixture",
    signing_key: Ed25519PrivateKey | None = None,  # gitleaks:allow - generated test key
) -> dict:
    cases = []
    for case_index in range(case_count):
        positives = [
            {
                "publication_id": f"US2026{case_index:04d}{category_index:02d}A1",
                "family_id": f"family-{case_index}-{category_index}",
                "category": category,
                "adjudication_evidence_sha256": _digest(
                    f"evidence-{case_index}-{category}"
                ),
                **(
                    {
                        "full_exact_structure_evidence_sha256": _digest(
                            f"full-exact-{case_index}"
                        ),
                        "stereo_aware_evidence_sha256": _digest(
                            f"stereo-aware-{case_index}"
                        ),
                        "variable_table_evidence_sha256": _digest(
                            f"variable-table-{case_index}"
                        ),
                    }
                    if benchmark_scope == "production" and category == "markush_only"
                    else {}
                ),
            }
            for category_index, category in enumerate(_CATEGORIES)
        ]
        negatives = [
            {
                "publication_id": (f"US2025{case_index:04d}{negative_index:02d}A1"),
                "family_id": f"negative-family-{case_index}-{negative_index}",
                "judgment": "not_relevant",
                "adjudication_evidence_sha256": _digest(
                    f"negative-evidence-{case_index}-{negative_index}"
                ),
            }
            for negative_index in range(len(positives))
        ]
        cases.append(
            {
                "case_id": f"case-{case_index:02d}",
                "query_structure_sha256": _digest(f"query-{case_index}"),
                "adjudicator_identity": f"adjudicator-{case_index}",
                "reviewer_identity": f"reviewer-{case_index}",
                "positives": positives,
                "adjudicated_candidates": [
                    *[
                        {
                            "publication_id": positive["publication_id"],
                            "family_id": positive["family_id"],
                            "judgment": "relevant",
                            "adjudication_evidence_sha256": positive[
                                "adjudication_evidence_sha256"
                            ],
                        }
                        for positive in positives
                    ],
                    *negatives,
                ],
            }
        )
    dataset = seal_dataset(
        {
            "schema_version": "markush-retrieval-benchmark-v2",
            "benchmark_id": (
                "praviar-markush-production-2026q3"
                if benchmark_scope == "production"
                else "sealed-fixture-v1"
            ),
            "benchmark_scope": benchmark_scope,
            "sealed_at": "2026-07-25T10:00:00Z",
            "curation_methodology": (
                "Independent blinded dual adjudication under the signed production "
                "candidate-pooling protocol."
                if benchmark_scope == "production"
                else "Independent fixture adjudication used only to test "
                "deterministic scoring."
            ),
            "curation_organization": (
                "Independent Patent Retrieval Consortium"
                if benchmark_scope == "production"
                else "Praviar benchmark test fixture"
            ),
            "curation_protocol_sha256": _digest("fixture-curation-protocol"),
            "curation_artifact_sha256": _digest("fixture-curation-artifact"),
            "candidate_pool_protocol_sha256": _digest(
                "fixture-candidate-pool-protocol"
            ),
            "retrieval_cutoff": 100,
            "thresholds": {
                "category_recall_min": {
                    category: (0.99 if benchmark_scope == "production" else 0.95)
                    for category in _CATEGORIES
                },
                "family_recall_min": (
                    0.99 if benchmark_scope == "production" else 0.95
                ),
                "family_precision_min": (
                    0.99 if benchmark_scope == "production" else 0.95
                ),
            },
            "cases": cases,
        }
    )
    if benchmark_scope == "production" and signing_key is not None:
        return sign_benchmark_artifact(
            dataset,
            purpose="dataset",
            private_key=signing_key,
            key_id=_SYNTHETIC_DATASET_KEY_ID,
        )
    return dataset


def _observed(
    dataset: dict,
    *,
    signing_key: Ed25519PrivateKey | None = None,  # gitleaks:allow - generated test key
) -> dict:
    observed = seal_observed_results(
        {
            "schema_version": "markush-retrieval-observed-v2",
            "benchmark_id": dataset["benchmark_id"],
            "benchmark_scope": dataset["benchmark_scope"],
            "dataset_sha256": dataset["dataset_sha256"],
            "executed_at": "2026-07-25T11:00:00Z",
            "system_identity": (
                "praviar-production-retrieval"
                if dataset["benchmark_scope"] == "production"
                else "fixture-backend"
            ),
            "system_version": (
                "2026.07.25"
                if dataset["benchmark_scope"] == "production"
                else "fixture-only"
            ),
            "source_tree_sha256": _digest("fixture-source-tree"),
            "retrieval_configuration_sha256": _digest("fixture-config"),
            "execution_receipt_sha256": _digest("fixture-execution-receipt"),
            "cases": [
                {
                    "case_id": case["case_id"],
                    "case_execution_receipt_sha256": _digest(
                        f"case-execution-{case['case_id']}"
                    ),
                    "retrieved": [
                        {
                            "publication_id": positive["publication_id"],
                            "rank": rank,
                            "retrieval_lanes": [
                                {
                                    "exact": "exact_structure",
                                    "scaffold": "scaffold_structure",
                                    "developed_example": (
                                        "developed_example_structure"
                                    ),
                                    "markush_only": "patentscope_markush",
                                }[positive["category"]]
                            ],
                            "retrieval_receipt_sha256": _digest(
                                f"retrieval-{case['case_id']}-{rank}"
                            ),
                            **(
                                {
                                    field: _digest(
                                        f"observed-{field}-{case['case_id']}-{rank}"
                                    )
                                    for field in (
                                        "full_exact_structure_evidence_sha256",
                                        "stereo_aware_evidence_sha256",
                                        "variable_table_evidence_sha256",
                                    )
                                }
                                if (
                                    dataset["benchmark_scope"] == "production"
                                    and positive["category"] == "markush_only"
                                )
                                else {}
                            ),
                        }
                        for rank, positive in enumerate(
                            case["positives"],
                            start=1,
                        )
                    ],
                }
                for case in dataset["cases"]
            ],
        }
    )
    if dataset["benchmark_scope"] == "production" and signing_key is not None:
        return sign_benchmark_artifact(
            observed,
            purpose="observed-results",
            private_key=signing_key,
            key_id="retrieval-runtime-2026",
        )
    return observed


def _trust_signing_keys(
    monkeypatch: pytest.MonkeyPatch,
    dataset_key: Ed25519PrivateKey,
    results_key: Ed25519PrivateKey,
) -> None:
    for purpose, private_key, key_id in (
        ("DATASET", dataset_key, _SYNTHETIC_DATASET_KEY_ID),
        ("RESULTS", results_key, "retrieval-runtime-2026"),
    ):
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        monkeypatch.setenv(f"MARKUSH_BENCHMARK_{purpose}_KEY_ID", key_id)
        monkeypatch.setenv(
            f"MARKUSH_BENCHMARK_{purpose}_PUBLIC_KEY",
            base64.b64encode(public_key).decode(),
        )
    monkeypatch.setenv(
        "MARKUSH_BENCHMARK_ALLOWED_DATASET_IDS",
        "praviar-markush-production-2026q3",
    )
    monkeypatch.setenv(
        "MARKUSH_BENCHMARK_ALLOWED_CURATOR_ORGANIZATIONS",
        "Independent Patent Retrieval Consortium",
    )
    monkeypatch.setenv(
        "MARKUSH_BENCHMARK_ALLOWED_SYSTEM_IDENTITIES",
        "praviar-production-retrieval",
    )
    monkeypatch.setenv("MARKUSH_BENCHMARK_EXPECTED_CUTOFF", "100")


def test_sealed_runner_scores_all_categories_and_family_metrics() -> None:
    dataset = _dataset()
    score = score_retrieval_benchmark(dataset, _observed(dataset))

    assert score["passed"] is True
    assert score["case_count"] == 20
    assert all(metric["recall"] == 1.0 for metric in score["category_metrics"].values())
    assert score["family_metrics"]["recall"] == 1.0
    assert score["family_metrics"]["precision"] == 1.0
    assert score["production_claim_eligible"] is False
    assert (
        "Fixture results do not establish production corpus recall"
        in score["claim_boundary"]
    )
    assert len(score["score_sha256"]) == 64


def test_runner_fails_markush_only_and_family_thresholds_without_fabrication() -> None:
    dataset = _dataset()
    observed = _observed(dataset)
    for row in observed["cases"]:
        row["retrieved"] = row["retrieved"][:-1]
    observed = seal_observed_results(observed)

    score = score_retrieval_benchmark(dataset, observed)

    assert score["passed"] is False
    assert score["category_metrics"]["markush_only"]["recall"] == 0.0
    assert any("markush_only recall" in failure for failure in score["failures"])
    assert any("family recall" in failure for failure in score["failures"])


def test_markush_only_recall_requires_attested_markush_retrieval_lane() -> None:
    dataset = _dataset()
    observed = _observed(dataset)
    for row in observed["cases"]:
        row["retrieved"][-1]["retrieval_lanes"] = ["exact_structure"]
    observed = seal_observed_results(observed)

    score = score_retrieval_benchmark(dataset, observed)

    assert score["category_metrics"]["markush_only"]["recall"] == 0.0
    assert (
        score["markush_lane_ablation"]["markush_only_hits_also_found_by_ordinary_lanes"]
        == 20
    )
    assert (
        score["markush_lane_ablation"]["markush_only_true_positives_from_markush_lanes"]
        == 0
    )


def test_observed_results_cannot_self_report_family_or_submit_unjudged_output() -> None:
    dataset = _dataset()
    observed = _observed(dataset)
    observed["cases"][0]["retrieved"][0]["family_id"] = dataset["cases"][0][
        "positives"
    ][0]["family_id"]
    observed = seal_observed_results(observed)
    with pytest.raises(BenchmarkValidationError, match="unexpected=.*family_id"):
        score_retrieval_benchmark(dataset, observed)

    unjudged = _observed(dataset)
    unjudged["cases"][0]["retrieved"][0] = {
        "publication_id": "US2099999999A1",
        "rank": 1,
        "retrieval_lanes": ["exact_structure"],
        "retrieval_receipt_sha256": _digest("unjudged-retrieval"),
    }
    unjudged = seal_observed_results(unjudged)
    with pytest.raises(BenchmarkValidationError, match="unjudged or outside"):
        score_retrieval_benchmark(dataset, unjudged)


def test_family_precision_uses_curator_signed_candidate_mapping() -> None:
    dataset = _dataset()
    observed = _observed(dataset)
    for case, row in zip(dataset["cases"], observed["cases"], strict=True):
        row["retrieved"].append(
            {
                "publication_id": case["adjudicated_candidates"][-1]["publication_id"],
                "rank": len(row["retrieved"]) + 1,
                "retrieval_lanes": ["exact_structure"],
                "retrieval_receipt_sha256": _digest(
                    f"negative-retrieval-{case['case_id']}"
                ),
            }
        )
    observed = seal_observed_results(observed)

    score = score_retrieval_benchmark(dataset, observed)

    assert score["family_metrics"]["precision"] == 0.8
    assert score["family_metrics"]["passed"] is False
    assert any("family precision" in failure for failure in score["failures"])


def test_runner_rejects_tampered_or_undersized_ground_truth() -> None:
    dataset = _dataset()
    dataset["cases"][0]["positives"][0]["family_id"] = "tampered"
    with pytest.raises(BenchmarkValidationError, match="seal mismatch"):
        score_retrieval_benchmark(dataset, _observed(_dataset()))

    undersized = _dataset()
    undersized["cases"] = undersized["cases"][:1]
    undersized = seal_dataset(undersized)
    with pytest.raises(BenchmarkValidationError, match="at least 20"):
        score_retrieval_benchmark(undersized, _observed(undersized))

    extra_field = _dataset()
    extra_field["ignored_claim_override"] = True
    extra_field = seal_dataset(extra_field)
    with pytest.raises(BenchmarkValidationError, match="unexpected=.*claim_override"):
        score_retrieval_benchmark(extra_field, _observed(extra_field))


def test_production_metrics_require_large_sample_but_blind_claim_stays_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_key = Ed25519PrivateKey.generate()
    results_key = Ed25519PrivateKey.generate()
    _trust_signing_keys(monkeypatch, dataset_key, results_key)
    dataset = _dataset(
        case_count=299,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    score = score_retrieval_benchmark(
        dataset,
        _observed(dataset, signing_key=results_key),
    )

    assert score["passed"] is False
    assert score["production_claim_eligible"] is False
    assert all(
        metric["passed"] is True for metric in score["category_metrics"].values()
    )
    assert any(
        "black-box execution harness" in failure for failure in score["failures"]
    )
    assert all(
        metric["recall_lower_bound_95"] > 0.99
        for metric in score["category_metrics"].values()
    )

    undersized = _dataset(
        case_count=298,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    with pytest.raises(BenchmarkValidationError, match="at least 299"):
        score_retrieval_benchmark(
            undersized,
            _observed(undersized, signing_key=results_key),
        )


def test_runner_rejects_pre_seal_execution_and_weak_production_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_key = Ed25519PrivateKey.generate()
    results_key = Ed25519PrivateKey.generate()
    _trust_signing_keys(monkeypatch, dataset_key, results_key)
    dataset = _dataset(
        case_count=299,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    observed = _observed(dataset, signing_key=results_key)
    observed["executed_at"] = "2026-07-25T09:59:59Z"
    observed = seal_observed_results(observed)
    with pytest.raises(BenchmarkValidationError, match="after the benchmark is sealed"):
        score_retrieval_benchmark(dataset, observed)

    dataset["thresholds"]["family_recall_min"] = 0.989
    dataset = seal_dataset(dataset)
    with pytest.raises(BenchmarkValidationError, match="must be at least 0.99"):
        score_retrieval_benchmark(
            dataset,
            _observed(dataset, signing_key=results_key),
        )


def test_production_rejects_duplicate_queries_and_unregistered_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_key = Ed25519PrivateKey.generate()
    results_key = Ed25519PrivateKey.generate()
    _trust_signing_keys(monkeypatch, dataset_key, results_key)

    duplicate_queries = _dataset(
        case_count=299,
        benchmark_scope="production",
    )
    duplicate_queries["cases"][1]["query_structure_sha256"] = duplicate_queries[
        "cases"
    ][0]["query_structure_sha256"]
    duplicate_queries = sign_benchmark_artifact(
        seal_dataset(duplicate_queries),
        purpose="dataset",
        private_key=dataset_key,
        key_id=_SYNTHETIC_DATASET_KEY_ID,
    )
    with pytest.raises(BenchmarkValidationError, match="unique query structure"):
        score_retrieval_benchmark(
            duplicate_queries,
            _observed(duplicate_queries, signing_key=results_key),
        )

    synthetic_provenance = _dataset(
        case_count=299,
        benchmark_scope="production",
    )
    synthetic_provenance["curation_organization"] = "Synthetic Fixture Factory"
    synthetic_provenance = sign_benchmark_artifact(
        seal_dataset(synthetic_provenance),
        purpose="dataset",
        private_key=dataset_key,
        key_id=_SYNTHETIC_DATASET_KEY_ID,
    )
    with pytest.raises(BenchmarkValidationError, match="not production-allowlisted"):
        score_retrieval_benchmark(
            synthetic_provenance,
            _observed(synthetic_provenance, signing_key=results_key),
        )


def test_production_markush_hits_require_exact_stereo_and_variable_table_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_key = Ed25519PrivateKey.generate()
    results_key = Ed25519PrivateKey.generate()
    _trust_signing_keys(monkeypatch, dataset_key, results_key)

    incomplete_qrels = _dataset(case_count=299, benchmark_scope="production")
    del incomplete_qrels["cases"][0]["positives"][-1]["stereo_aware_evidence_sha256"]
    incomplete_qrels = sign_benchmark_artifact(
        seal_dataset(incomplete_qrels),
        purpose="dataset",
        private_key=dataset_key,
        key_id=_SYNTHETIC_DATASET_KEY_ID,
    )
    with pytest.raises(
        BenchmarkValidationError,
        match="missing=.*stereo_aware_evidence_sha256",
    ):
        score_retrieval_benchmark(
            incomplete_qrels,
            _observed(incomplete_qrels, signing_key=results_key),
        )

    dataset = _dataset(
        case_count=299,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    observed = _observed(dataset)
    markush_result = observed["cases"][0]["retrieved"][-1]
    publication_id = markush_result["publication_id"]
    markush_result["publication_id"] = f"{publication_id[:2]}-{publication_id[2:]}"
    del markush_result["variable_table_evidence_sha256"]
    observed = sign_benchmark_artifact(
        seal_observed_results(observed),
        purpose="observed-results",
        private_key=results_key,
        key_id="retrieval-runtime-2026",
    )
    with pytest.raises(
        BenchmarkValidationError,
        match="missing=.*variable_table_evidence_sha256",
    ):
        score_retrieval_benchmark(dataset, observed)


def test_production_claim_rejects_unsigned_or_untrusted_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_key = Ed25519PrivateKey.generate()
    results_key = Ed25519PrivateKey.generate()
    _trust_signing_keys(monkeypatch, dataset_key, results_key)
    unsigned = _dataset(case_count=299, benchmark_scope="production")
    with pytest.raises(BenchmarkValidationError, match="signature must be an object"):
        score_retrieval_benchmark(unsigned, _observed(unsigned))

    _trust_signing_keys(monkeypatch, dataset_key, dataset_key)
    same_key_dataset = _dataset(
        case_count=299,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    with pytest.raises(BenchmarkValidationError, match="distinct public keys"):
        score_retrieval_benchmark(
            same_key_dataset,
            _observed(same_key_dataset, signing_key=dataset_key),
        )

    _trust_signing_keys(monkeypatch, dataset_key, results_key)
    signed = _dataset(
        case_count=299,
        benchmark_scope="production",
        signing_key=dataset_key,
    )
    observed = _observed(signed, signing_key=Ed25519PrivateKey.generate())
    with pytest.raises(BenchmarkValidationError, match="signature mismatch"):
        score_retrieval_benchmark(signed, observed)


def test_json_schemas_are_valid_json_documents() -> None:
    directory = Path(__file__).resolve().parent
    for filename in (
        "markush_retrieval_benchmark.schema.json",
        "markush_retrieval_observed.schema.json",
    ):
        schema = json.loads((directory / filename).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
