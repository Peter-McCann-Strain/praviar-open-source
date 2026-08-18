from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.tools.benchmarks.monitoring_replay_benchmark import (
    MonitoringReplayValidationError,
    load_json,
    score_monitoring_replay,
    seal_dataset,
    seal_observed_results,
    seal_runtime_manifest,
    validate_dataset,
    validate_observed_results,
)

NOW = datetime(2026, 1, 30, tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _dataset(*, second_case: bool = False) -> dict:
    cases = [_case("case-1", "org-1", "report-1", 1)]
    if second_case:
        cases.append(_case("case-2", "org-2", "report-2", 2))
    return seal_dataset(
        {
            "schema_version": "monitoring-replay-dataset-v1",
            "benchmark_id": "monitoring-replay-fixture-1",
            "benchmark_scope": "fixture",
            "sealed_at": "2026-01-20T00:00:00Z",
            "replay_window_start": "2026-01-01T00:00:00Z",
            "replay_window_end": "2026-01-10T00:00:00Z",
            "curation_organization": "Independent Fixture Lab",
            "curation_protocol_sha256": _digest("curation-protocol"),
            "curation_artifact_sha256": _digest("curation-artifact"),
            "thresholds": {
                "material_recall_min": 0.95,
                "precision_min": 0.80,
                "false_alert_reduction_min": 0.30,
                "reviewer_minute_reduction_min": 0.25,
                "provenance_fidelity_min": 1.0,
            },
            "freshness_policy": {
                "max_source_lag_seconds": 7_200,
                "max_detection_lag_seconds": 7_200,
                "policy_artifact_sha256": _digest("fixture-freshness-policy"),
            },
            "independence_policy": {
                "min_distinct_organizations": 1,
                "min_distinct_adjudicators": 1,
                "min_distinct_reviewers": 1,
                "max_case_fraction_per_organization": 1.0,
            },
            "counsel_burden_approval": None,
            "cases": cases,
        }
    )


def _case(case_id: str, org_id: str, report_id: str, index: int) -> dict:
    report_sha = _digest(f"report-{index}-bytes")
    source_one = _digest(f"source-{index}-one")
    source_two = _digest(f"source-{index}-two")
    event_one = f"event-{index}-material"
    event_two = f"event-{index}-immaterial"
    return {
        "case_id": case_id,
        "org_id": org_id,
        "source_report_id": report_id,
        "source_report_sha256": report_sha,
        "source_report_generated_at": "2026-01-02T00:00:00Z",
        "replay_as_of": "2026-01-05T00:00:00Z",
        "adjudicator_identity": f"adjudicator-{index}",
        "reviewer_identity": f"reviewer-{index}",
        "adjudicated_at": "2026-01-15T00:00:00Z",
        "baseline_false_alert_count": 2,
        "baseline_reviewer_minutes": 20.0,
        "conclusion_universe": [
            {
                "conclusion_id": f"clearance:{index}",
                "dependency_fingerprint": _digest(
                    f"conclusion-{index}-dependencies"
                ),
                "conclusion_evidence_sha256": _digest(
                    f"conclusion-{index}-evidence"
                ),
            },
            {
                "conclusion_id": f"clearance:false-{case_id}",
                "dependency_fingerprint": _digest(
                    f"false-conclusion-{index}-dependencies"
                ),
                "conclusion_evidence_sha256": _digest(
                    f"false-conclusion-{index}-evidence"
                ),
            },
        ],
        "reviewer_receipt": None,
        "events": [
            {
                "event_id": event_one,
                "org_id": org_id,
                "source_report_id": report_id,
                "occurred_at": "2026-01-03T00:00:00Z",
                "available_at": "2026-01-03T01:00:00Z",
                "source_id": f"official-source-{index}-one",
                "source_sha256": source_one,
            },
            {
                "event_id": event_two,
                "org_id": org_id,
                "source_report_id": report_id,
                "occurred_at": "2026-01-04T00:00:00Z",
                "available_at": "2026-01-04T01:00:00Z",
                "source_id": f"official-source-{index}-two",
                "source_sha256": source_two,
            },
        ],
        "expected_impacts": [
            {
                "impact_id": f"impact-{index}",
                "org_id": org_id,
                "source_report_id": report_id,
                "source_report_sha256": report_sha,
                "event_id": event_one,
                "conclusion_id": f"clearance:{index}",
                "source_id": f"official-source-{index}-one",
                "source_sha256": source_one,
                "adjudication_evidence_sha256": _digest(
                    f"adjudication-evidence-{index}"
                ),
            }
        ],
    }


def _results(dataset: dict, *, include_false_alert: bool = False) -> dict:
    runtime_manifest = seal_runtime_manifest(
        {
            "runtime_id": "fixture-monitor-runtime",
            "git_sha": "1" * 40,
            "git_tree_state_sha256": _digest("fixture-tree-state"),
            "runtime_artifact_sha256": _digest("fixture-runtime"),
            "dependency_lock_sha256": _digest("fixture-lock"),
            "config_sha256": _digest("fixture-config"),
            "artifacts": [
                {
                    "path": "api/src/api/services/monitor_runtime.py",
                    "sha256": _digest("fixture-file"),
                }
            ],
        }
    )
    case_results = []
    for case in dataset["cases"]:
        impact = case["expected_impacts"][0]
        event = case["events"][0]
        predictions = [
            {
                "prediction_id": f"prediction-{case['case_id']}-correct",
                "org_id": case["org_id"],
                "source_report_id": case["source_report_id"],
                "source_report_sha256": case["source_report_sha256"],
                "event_id": event["event_id"],
                "conclusion_id": impact["conclusion_id"],
                "source_id": event["source_id"],
                "source_sha256": event["source_sha256"],
                "detected_at": "2026-01-03T02:00:00Z",
                "status": "review_required",
            }
        ]
        if include_false_alert:
            false_event = case["events"][1]
            predictions.append(
                {
                    "prediction_id": f"prediction-{case['case_id']}-false",
                    "org_id": case["org_id"],
                    "source_report_id": case["source_report_id"],
                    "source_report_sha256": case["source_report_sha256"],
                    "event_id": false_event["event_id"],
                    "conclusion_id": f"clearance:false-{case['case_id']}",
                    "source_id": false_event["source_id"],
                    "source_sha256": false_event["source_sha256"],
                    "detected_at": "2026-01-04T02:00:00Z",
                    "status": "review_required",
                }
            )
        case_results.append(
            {
                "case_id": case["case_id"],
                "org_id": case["org_id"],
                "source_report_id": case["source_report_id"],
                "source_report_sha256": case["source_report_sha256"],
                "runtime_manifest_sha256": runtime_manifest["manifest_sha256"],
                "evaluated_at": case["replay_as_of"],
                "candidate_reviewer_minutes": 10.0,
                "predictions": predictions,
            }
        )
    return seal_observed_results(
        {
            "schema_version": "monitoring-replay-results-v1",
            "benchmark_id": dataset["benchmark_id"],
            "dataset_sha256": dataset["dataset_sha256"],
            "generated_at": "2026-01-21T00:00:00Z",
            "runtime_manifest": runtime_manifest,
            "cases": case_results,
        }
    )


def _reseal_dataset(dataset: dict) -> dict:
    return seal_dataset(dataset)


def _reseal_results(results: dict, dataset: dict) -> dict:
    results["dataset_sha256"] = dataset["dataset_sha256"]
    return seal_observed_results(results)


def test_fixture_can_exercise_all_metrics_but_never_receive_evidence_credit():
    dataset = _dataset(second_case=True)
    report = score_monitoring_replay(
        dataset,
        _results(dataset),
        now=NOW,
        verify_runtime_state=False,
    )

    assert report["material_recall"] == 1.0
    assert report["precision"] == 1.0
    assert report["false_alert_reduction"] == 1.0
    assert report["reviewer_minute_reduction"] == 0.5
    assert report["provenance_fidelity"] == 1.0
    assert report["metric_gate_passed"] is True
    assert report["production_eligible"] is False
    assert report["evidence_credit"] == "none"
    assert report["passed"] is False
    assert "non-credit" in report["failures"][-1]


def test_rejects_duplicate_case_ids():
    dataset = _dataset(second_case=True)
    dataset["cases"][1]["case_id"] = dataset["cases"][0]["case_id"]
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="duplicate ID"):
        validate_dataset(dataset, now=NOW)


def test_rejects_duplicate_event_ids_across_cases():
    dataset = _dataset(second_case=True)
    dataset["cases"][1]["events"][0]["event_id"] = dataset["cases"][0]["events"][0][
        "event_id"
    ]
    dataset["cases"][1]["expected_impacts"][0]["event_id"] = dataset["cases"][0][
        "events"
    ][0]["event_id"]
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="dataset events"):
        validate_dataset(dataset, now=NOW)


def test_rejects_duplicate_prediction_ids():
    dataset = _dataset(second_case=True)
    results = _results(dataset)
    duplicate_id = results["cases"][0]["predictions"][0]["prediction_id"]
    results["cases"][1]["predictions"][0]["prediction_id"] = duplicate_id
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="results predictions"):
        validate_observed_results(results, dataset=dataset, now=NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at", "2026-01-06T00:00:00Z"),
        ("available_at", "2026-01-06T00:00:00Z"),
    ],
)
def test_rejects_future_or_leaky_events(field: str, value: str):
    dataset = _dataset()
    dataset["cases"][0]["events"][0][field] = value
    dataset = _reseal_dataset(dataset)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="future, leaky, or non-causal",
    ):
        validate_dataset(dataset, now=NOW)


def test_rejects_future_fixture_dates_relative_to_clock():
    dataset = _dataset()
    dataset["sealed_at"] = "2027-01-20T00:00:00Z"
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="cannot be in the future"):
        validate_dataset(dataset, now=NOW)


def test_rejects_adjudication_without_independent_review():
    dataset = _dataset()
    dataset["cases"][0]["reviewer_identity"] = dataset["cases"][0][
        "adjudicator_identity"
    ]
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="independent identities"):
        validate_dataset(dataset, now=NOW)


def test_rejects_adjudication_before_replay_window_closes():
    dataset = _dataset()
    dataset["cases"][0]["adjudicated_at"] = "2026-01-08T00:00:00Z"
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="non-causal"):
        validate_dataset(dataset, now=NOW)


def test_rejects_missing_source_hash():
    dataset = _dataset()
    dataset["cases"][0]["events"][0]["source_sha256"] = ""
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="must be non-empty"):
        validate_dataset(dataset, now=NOW)


def test_rejects_expected_impact_source_mismatch():
    dataset = _dataset()
    dataset["cases"][0]["expected_impacts"][0]["source_sha256"] = _digest(
        "wrong-source"
    )
    dataset = _reseal_dataset(dataset)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="provenance does not match",
    ):
        validate_dataset(dataset, now=NOW)


def test_rejects_cross_tenant_dataset_event():
    dataset = _dataset()
    dataset["cases"][0]["events"][0]["org_id"] = "another-org"
    dataset = _reseal_dataset(dataset)

    with pytest.raises(MonitoringReplayValidationError, match="tenant/report boundary"):
        validate_dataset(dataset, now=NOW)


def test_rejects_cross_report_result_prediction():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["predictions"][0]["source_report_id"] = "other-report"
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="tenant/report boundary"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_non_causal_detection_before_source_availability():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["predictions"][0]["detected_at"] = (
        "2026-01-03T00:30:00Z"
    )
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="non-causal"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_stale_or_lookahead_result_cutoff():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["evaluated_at"] = "2026-01-06T00:00:00Z"
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="stale or evaluated beyond"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_result_not_bound_to_exact_dataset_seal():
    dataset = _dataset()
    results = _results(dataset)
    results["dataset_sha256"] = _digest("another-dataset")
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="exact dataset seal"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_runtime_manifest_seal_mismatch():
    dataset = _dataset()
    results = _results(dataset)
    results["runtime_manifest"]["config_sha256"] = _digest("changed-config")
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="manifest seal mismatch"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_result_source_not_bound_to_exact_event_bytes():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["predictions"][0]["source_sha256"] = _digest(
        "different-source-bytes"
    )
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="exact event source"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_expected_impact_outside_complete_conclusion_universe():
    dataset = _dataset()
    dataset["cases"][0]["expected_impacts"][0]["conclusion_id"] = (
        "clearance:unsealed"
    )
    dataset = _reseal_dataset(dataset)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="sealed conclusion universe",
    ):
        validate_dataset(dataset, now=NOW)


def test_rejects_prediction_outside_complete_conclusion_universe():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["predictions"][0]["conclusion_id"] = (
        "clearance:unsealed"
    )
    results = seal_observed_results(results)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="sealed conclusion universe",
    ):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_source_lag_beyond_sealed_freshness_policy():
    dataset = _dataset()
    dataset["freshness_policy"]["max_source_lag_seconds"] = 30
    dataset = _reseal_dataset(dataset)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="source freshness policy",
    ):
        validate_dataset(dataset, now=NOW)


def test_rejects_detection_lag_beyond_sealed_freshness_policy():
    dataset = _dataset()
    dataset["freshness_policy"]["max_detection_lag_seconds"] = 30
    dataset = _reseal_dataset(dataset)
    results = _results(dataset)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="detection freshness policy",
    ):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_rejects_case_not_bound_to_exact_runtime_manifest():
    dataset = _dataset()
    results = _results(dataset)
    results["cases"][0]["runtime_manifest_sha256"] = _digest("other-runtime")
    results = seal_observed_results(results)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="exact runtime manifest",
    ):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_false_alerts_count_against_precision_and_burden():
    dataset = _dataset()
    report = score_monitoring_replay(
        dataset,
        _results(dataset, include_false_alert=True),
        now=NOW,
    )

    assert report["true_positives"] == 1
    assert report["false_positives"] == 1
    assert report["precision"] == 0.5
    assert report["candidate_false_alert_count"] == 1
    assert report["false_alert_reduction"] == 0.5
    assert report["metric_checks"]["precision_or_counsel_approved_burden"] is False
    assert report["metric_gate_passed"] is False


def test_fixture_counsel_approval_cannot_override_precision_failure():
    dataset = _dataset()
    dataset["counsel_burden_approval"] = {
        "approved_by": "fixture-counsel",
        "approved_at": "2026-01-19T00:00:00Z",
        "approval_evidence_sha256": _digest("fixture-approval"),
        "max_false_alerts_total": 10,
        "max_false_alerts_per_case": 10.0,
    }
    dataset = _reseal_dataset(dataset)
    report = score_monitoring_replay(
        dataset,
        _results(dataset, include_false_alert=True),
        now=NOW,
    )

    assert report["counsel_approved_burden_pass"] is False
    assert report["metric_checks"]["precision_or_counsel_approved_burden"] is False


def test_production_label_cannot_bypass_minimum_evidence_size(
    monkeypatch: pytest.MonkeyPatch,
):
    dataset = _dataset()
    dataset["benchmark_scope"] = "production"
    dataset = _reseal_dataset(dataset)
    monkeypatch.setenv(
        "MONITOR_REPLAY_CURATION_ORG_ALLOWLIST",
        "Independent Fixture Lab",
    )
    monkeypatch.setenv("MONITOR_REPLAY_ADJUDICATOR_ALLOWLIST", "adjudicator-1")
    monkeypatch.setenv("MONITOR_REPLAY_REVIEWER_ALLOWLIST", "reviewer-1")

    with pytest.raises(
        MonitoringReplayValidationError,
        match="at least 50 cases and 250 events",
    ):
        validate_dataset(dataset, now=NOW)


def test_runtime_file_verification_rejects_mismatch(tmp_path: Path):
    dataset = _dataset()
    results = _results(dataset)
    runtime_path = tmp_path / "runtime.py"
    runtime_path.write_text("print('actual')\n", encoding="utf-8")
    results["runtime_manifest"] = seal_runtime_manifest(
        {
            **results["runtime_manifest"],
            "artifacts": [
                {
                    "path": "runtime.py",
                    "sha256": _digest("not-the-file"),
                }
            ],
        }
    )
    results = seal_observed_results(results)

    with pytest.raises(
        MonitoringReplayValidationError,
        match="current repository artifact",
    ):
        validate_observed_results(
            results,
            dataset=dataset,
            now=NOW,
            repo_root=tmp_path,
            verify_runtime_state=True,
        )


def test_results_must_cover_every_case_exactly_once():
    dataset = _dataset(second_case=True)
    results = _results(dataset)
    results["cases"].pop()
    results = seal_observed_results(results)

    with pytest.raises(MonitoringReplayValidationError, match="every dataset case"):
        validate_observed_results(results, dataset=dataset, now=NOW)


def test_json_loader_rejects_duplicate_keys(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version": "one", "schema_version": "two"}')

    with pytest.raises(MonitoringReplayValidationError, match="duplicate key"):
        load_json(path)


def test_json_loader_rejects_oversized_artifact_before_parsing(tmp_path: Path):
    path = tmp_path / "oversized.json"
    with path.open("wb") as artifact:
        artifact.truncate(16 * 1024 * 1024 + 1)

    with pytest.raises(MonitoringReplayValidationError, match="exceeds"):
        load_json(path)


def test_json_loader_rejects_excessive_nesting(tmp_path: Path):
    path = tmp_path / "nested.json"
    path.write_text("[" * 65 + "0" + "]" * 65, encoding="utf-8")

    with pytest.raises(MonitoringReplayValidationError, match="nesting depth"):
        load_json(path)


def test_seals_reject_tampering():
    dataset = _dataset()
    tampered_dataset = deepcopy(dataset)
    tampered_dataset["cases"][0]["baseline_reviewer_minutes"] = 999
    with pytest.raises(MonitoringReplayValidationError, match="dataset seal mismatch"):
        validate_dataset(tampered_dataset, now=NOW)

    results = _results(dataset)
    tampered_results = deepcopy(results)
    tampered_results["cases"][0]["candidate_reviewer_minutes"] = 0
    with pytest.raises(MonitoringReplayValidationError, match="results seal mismatch"):
        validate_observed_results(tampered_results, dataset=dataset, now=NOW)


def test_output_is_json_serializable_and_bound_to_all_seals():
    dataset = _dataset()
    results = _results(dataset)
    report = score_monitoring_replay(dataset, results, now=NOW)

    encoded = json.dumps(report, sort_keys=True)
    assert dataset["dataset_sha256"] in encoded
    assert results["results_sha256"] in encoded
    assert results["runtime_manifest"]["manifest_sha256"] in encoded
