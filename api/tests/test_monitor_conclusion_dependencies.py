"""Conclusion-aware monitor invalidation contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db, valid_report_data

from api.services.monitor_conclusion_dependencies import (
    CONCLUSION_DEPENDENCY_VERSION,
    build_conclusion_dependencies,
    merge_stale_conclusions,
)
from api.services.monitor_delta_computation import build_snapshot, diff_snapshot
from api.services.monitor_query_strategy import (
    MONITOR_STRATEGY_VERSION,
    build_monitor_queries,
    build_monitor_seed_from_report,
)
from api.services.monitor_runtime import execute_monitor_run


def _complete_provider_receipts(result_count: int = 1) -> list[dict]:
    return [
        {
            "provider_id": provider,
            "provider_name": provider,
            "status": "succeeded",
            "result_count": result_count,
            "explicit_zero_results": result_count == 0,
            "completed_at": "2026-07-27T10:00:00Z",
            "error_type": "",
        }
        for provider in (
            "uspto_odp",
            "patentsview",
            "ptab",
            "orange_book",
            "purple_book",
            "epo_ops",
            "patentscope",
        )
    ]


def _seed_report() -> dict:
    report = valid_report_data(
        report_id="report-conclusion-ledger",
        generated_at="2026-07-01T10:00:00Z",
        target_jurisdictions=["US"],
    )
    report["patent_analyses"] = [
        {
            "patent_id": "US12345678A1",
            "title": "Existing blocking candidate",
            "risk_level": "medium",
            "assignee": "Example Pharma",
        }
    ]
    report["matter_evidence_index"]["patent_records"] = [
        {
            "patent_id": "US12345678A1",
            "jurisdiction": "US",
            "title": "Existing blocking candidate",
            "family_id": "fam-123",
        }
    ]
    return report


def test_seed_builds_versioned_conclusion_dependency_ledger() -> None:
    report = _seed_report()

    strategy, targets, jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )

    assert strategy["version"] == MONITOR_STRATEGY_VERSION
    assert strategy["conclusion_dependency_version"] == CONCLUSION_DEPENDENCY_VERSION
    dependencies = strategy["conclusion_dependencies"]
    assert [item["conclusion_id"] for item in dependencies] == [
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    ]
    assert all(len(item["dependency_fingerprint"]) == 64 for item in dependencies)
    assert jurisdictions == ["US"]

    patent_target = next(
        target
        for target in targets
        if target["target_type"] == "patent" and target["target_id"] == "US12345678A1"
    )
    assert patent_target["affected_conclusion_ids"] == [
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    ]
    compound_target = next(target for target in targets if target["target_type"] == "compound")
    assert compound_target["affected_conclusion_ids"] == [
        "clearance:global",
        "clearance:US",
    ]


def test_manual_monitor_does_not_invent_a_legal_conclusion() -> None:
    dependencies = build_conclusion_dependencies(
        {
            "compound": {"name": "Aspirin"},
            "target_jurisdictions": ["US"],
        }
    )

    assert dependencies == []


def test_query_plan_carries_dependency_edges_into_provider_work() -> None:
    report = _seed_report()
    strategy, targets, jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    monitor = SimpleNamespace(
        watch_targets=targets,
        monitoring_strategy=strategy,
        target_jurisdictions=jurisdictions,
        compound_name="Aspirin",
    )

    queries = build_monitor_queries(
        monitor,  # type: ignore[arg-type]
        report_data=report,
        run_mode="full_refresh",
    )

    exact = next(query for query in queries if query["query"] == "US12345678A1")
    assert exact["affected_conclusion_ids"] == [
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    ]
    sweep = next(query for query in queries if query["query"] == "aspirin US patent")
    assert sweep["affected_conclusion_ids"] == [
        "clearance:global",
        "clearance:US",
    ]


def test_global_patent_target_is_bound_to_the_lane_where_it_is_queried() -> None:
    report = _seed_report()
    report["matter_evidence_index"]["patent_records"] = []
    strategy, targets, jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    monitor = SimpleNamespace(
        watch_targets=targets,
        monitoring_strategy=strategy,
        target_jurisdictions=jurisdictions,
        compound_name="Aspirin",
    )

    queries = build_monitor_queries(
        monitor,  # type: ignore[arg-type]
        report_data=report,
        run_mode="diff_only",
    )

    exact = next(query for query in queries if query["query"] == "US12345678A1")
    assert exact["affected_conclusion_ids"] == [
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    ]


def test_query_plan_covers_every_target_and_prioritizes_patents_before_families() -> None:
    report = _seed_report()
    report["matter_evidence_index"]["patent_records"].extend(
        {
            "patent_id": f"US20260000{index}A1",
            "jurisdiction": "US",
            "title": f"Critical patent {index}",
            "family_id": f"family-{index}",
        }
        for index in range(12)
    )
    strategy, targets, jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="daily",
        compound_name="Aspirin",
    )
    monitor = SimpleNamespace(
        watch_targets=targets,
        monitoring_strategy=strategy,
        target_jurisdictions=jurisdictions,
        compound_name="Aspirin",
    )

    queries = build_monitor_queries(
        monitor,  # type: ignore[arg-type]
        report_data=report,
        run_mode="diff_only",
    )

    manifest_keys = {row["coverage_key"] for row in strategy["coverage_manifest"]}
    planned_keys = {coverage_key for query in queries for coverage_key in query["coverage_keys"]}
    assert manifest_keys <= planned_keys
    assert len(queries) > 4
    first_family_index = next(
        index
        for index, query in enumerate(queries)
        if any("|family|" in key for key in query["coverage_keys"])
    )
    last_patent_index = max(
        index
        for index, query in enumerate(queries)
        if any("|patent|" in key for key in query["coverage_keys"])
    )
    assert last_patent_index < first_family_index


def test_new_patent_marks_only_bound_conclusions_review_required() -> None:
    report = _seed_report()
    strategy, targets, _jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    dependencies = strategy["conclusion_dependencies"]
    before = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    after = before + timedelta(days=7)
    previous = build_snapshot(
        run_mode="bootstrap",
        query_results=[
            {
                "jurisdiction": "US",
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                ],
                "response": {
                    "results": [
                        {
                            "result_id": "result:existing",
                            "patent_id": "US12345678A1",
                        }
                    ]
                },
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=before,
    )
    current = build_snapshot(
        run_mode="diff_only",
        query_results=[
            {
                "jurisdiction": "US",
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                ],
                "response": {
                    "results": [
                        {
                            "result_id": "result:existing",
                            "patent_id": "US12345678A1",
                        },
                        {
                            "result_id": "result:new",
                            "patent_id": "US99999999A1",
                        },
                    ]
                },
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=after,
    )

    delta = diff_snapshot(
        previous,
        current,
        conclusion_dependencies=dependencies,
    )

    assert delta.new_patent_ids == ["US99999999A1"]
    assert [item["conclusion_id"] for item in delta.affected_conclusions] == [
        "clearance:global",
        "clearance:US",
    ]
    assert all(
        item["status"] == "review_required"
        and item["reason_codes"] == ["new_patent_candidate"]
        and item["trigger_patent_ids"] == ["US99999999A1"]
        for item in delta.affected_conclusions
    )
    assert "patent-risk:US12345678A1" not in {
        item["conclusion_id"] for item in delta.affected_conclusions
    }


def test_exact_record_event_marks_patent_risk_and_aggregate_conclusions() -> None:
    report = _seed_report()
    strategy, _targets, _jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    current = {
        "generated_at": "2026-07-26T10:00:00+00:00",
        "observed_patent_ids": [],
        "observed_event_ids": ["event:office-action:new"],
        "observed_event_signals": [
            {
                "signal_id": "event:office-action:new",
                "jurisdictions": ["US"],
                "conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                    "patent-risk:US12345678A1",
                ],
            }
        ],
        "jurisdiction_deltas": {},
    }

    delta = diff_snapshot(
        {"observed_patent_ids": [], "observed_event_ids": []},
        current,
        conclusion_dependencies=strategy["conclusion_dependencies"],
    )

    assert {item["conclusion_id"] for item in delta.affected_conclusions} == {
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    }
    assert all(
        item["reason_codes"] == ["monitored_record_event"]
        and item["trigger_event_ids"] == ["event:office-action:new"]
        for item in delta.affected_conclusions
    )


def test_same_patent_changed_provider_record_invalidates_bound_conclusions() -> None:
    report = _seed_report()
    strategy, targets, _jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    before = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    after = before + timedelta(days=1)
    base_result = {
        "result_id": "uspto_odp:16123456",
        "patent_id": "US12345678A1",
        "source_name": "uspto_odp",
        "provenance": [
            {"label": "Application status", "value": "Patented Case"},
        ],
    }
    previous = build_snapshot(
        run_mode="bootstrap",
        query_results=[
            {
                "jurisdiction": "US",
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                    "patent-risk:US12345678A1",
                ],
                "response": {"results": [base_result]},
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=before,
    )
    current = build_snapshot(
        run_mode="diff_only",
        query_results=[
            {
                "jurisdiction": "US",
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                    "patent-risk:US12345678A1",
                ],
                "response": {
                    "results": [
                        {
                            **base_result,
                            "provenance": [
                                {
                                    "label": "Application status",
                                    "value": "Abandoned",
                                },
                            ],
                        }
                    ]
                },
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=after,
    )

    delta = diff_snapshot(
        previous,
        current,
        conclusion_dependencies=strategy["conclusion_dependencies"],
    )

    assert delta.new_patent_ids == []
    assert len(delta.new_event_ids) == 1
    assert delta.new_event_ids[0].startswith(
        "uspto_odp:16123456@sha256:",
    )
    assert {impact["conclusion_id"] for impact in delta.affected_conclusions} == {
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    }
    assert all(
        impact["reason_codes"] == ["monitored_record_event"]
        and impact["trigger_event_ids"] == delta.new_event_ids
        for impact in delta.affected_conclusions
    )


def test_unchanged_provider_record_does_not_create_content_event() -> None:
    now = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    query_result = {
        "jurisdiction": "US",
        "affected_conclusion_ids": ["clearance:US"],
        "response": {
            "results": [
                {
                    "result_id": "uspto_odp:16123456",
                    "patent_id": "US12345678A1",
                    "source_name": "uspto_odp",
                    "provenance": [
                        {
                            "label": "Application status",
                            "value": "Patented Case",
                        }
                    ],
                }
            ]
        },
    }
    previous = build_snapshot(
        run_mode="bootstrap",
        query_results=[query_result],
        provider_names=["uspto_odp"],
        watch_targets=[],
        now=now,
    )
    current = build_snapshot(
        run_mode="diff_only",
        query_results=[query_result],
        provider_names=["uspto_odp"],
        watch_targets=[],
        now=now + timedelta(days=1),
    )

    delta = diff_snapshot(previous, current, conclusion_dependencies=[])

    assert delta.new_patent_ids == []
    assert delta.new_event_ids == []


def test_provider_notices_never_enter_evidence_snapshot_or_advance_freshness() -> None:
    snapshot = build_snapshot(
        run_mode="diff_only",
        query_results=[
            {
                "jurisdiction": "US",
                "coverage_keys": ["US|patent|US123"],
                "affected_conclusion_ids": ["clearance:US"],
                "execution_receipts": [
                    {
                        "provider_name": "uspto_odp",
                        "status": "failed",
                        "result_count": 0,
                        "explicit_zero_results": False,
                    }
                ],
                "response": {
                    "results": [
                        {
                            "result_id": "provider_notice:uspto_odp",
                            "artifact_type": "provider_notice",
                            "section": "external_provider_notice",
                            "authority_tier": "governance",
                            "summary": "provider failed",
                        }
                    ]
                },
            }
        ],
        provider_names=[],
        watch_targets=[],
        now=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert snapshot["observed_patent_ids"] == []
    assert snapshot["observed_event_ids"] == []
    assert snapshot["observed_record_fingerprints"] == {}


def test_disappeared_record_and_patent_invalidate_prior_bound_conclusions() -> None:
    report = _seed_report()
    strategy, targets, _jurisdictions, _bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    previous = build_snapshot(
        run_mode="bootstrap",
        query_results=[
            {
                "jurisdiction": "US",
                "coverage_keys": ["US|patent|US12345678A1"],
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                    "patent-risk:US12345678A1",
                ],
                "response": {
                    "results": [
                        {
                            "result_id": "uspto_odp:16123456",
                            "patent_id": "US12345678A1",
                            "source_name": "uspto_odp",
                        }
                    ]
                },
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )
    current = build_snapshot(
        run_mode="diff_only",
        query_results=[
            {
                "jurisdiction": "US",
                "coverage_keys": ["US|patent|US12345678A1"],
                "affected_conclusion_ids": [
                    "clearance:global",
                    "clearance:US",
                    "patent-risk:US12345678A1",
                ],
                "response": {"results": []},
            }
        ],
        provider_names=["uspto_odp"],
        watch_targets=targets,
        now=datetime(2026, 7, 27, tzinfo=UTC),
    )

    delta = diff_snapshot(
        previous,
        current,
        conclusion_dependencies=strategy["conclusion_dependencies"],
    )

    assert "uspto_odp:16123456@disappeared" in delta.new_event_ids
    assert "patent:US12345678A1@disappeared" in delta.new_event_ids
    assert {impact["conclusion_id"] for impact in delta.affected_conclusions} == {
        "clearance:global",
        "clearance:US",
        "patent-risk:US12345678A1",
    }


def test_unresolved_impacts_survive_later_no_change_runs_and_accumulate_evidence() -> None:
    initial = [
        {
            "conclusion_id": "clearance:US",
            "invalidated_at": "2026-07-20T10:00:00Z",
            "latest_observed_at": "2026-07-20T10:00:00Z",
            "reason_codes": ["new_patent_candidate"],
            "trigger_patent_ids": ["US90000001A1"],
            "trigger_event_ids": [],
            "jurisdictions": ["US"],
        }
    ]
    later = [
        {
            "conclusion_id": "clearance:US",
            "invalidated_at": "2026-07-26T10:00:00Z",
            "latest_observed_at": "2026-07-26T10:00:00Z",
            "reason_codes": ["monitored_record_event"],
            "trigger_patent_ids": [],
            "trigger_event_ids": ["event:grant"],
            "jurisdictions": ["US"],
        }
    ]

    merged = merge_stale_conclusions(initial, later)
    unchanged = merge_stale_conclusions(merged, [])

    assert unchanged == merged
    assert merged[0]["invalidated_at"] == "2026-07-20T10:00:00Z"
    assert merged[0]["latest_observed_at"] == "2026-07-26T10:00:00Z"
    assert merged[0]["reason_codes"] == [
        "new_patent_candidate",
        "monitored_record_event",
    ]
    assert merged[0]["trigger_patent_ids"] == ["US90000001A1"]
    assert merged[0]["trigger_event_ids"] == ["event:grant"]


@pytest.mark.asyncio
async def test_monitor_run_persists_review_required_posture_and_alert_evidence() -> None:
    report = _seed_report()
    strategy, targets, jurisdictions, bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.user_id = uuid.uuid4()
    monitor.source_analysis_id = None
    monitor.compound_name = "Aspirin"
    monitor.compound_smiles = "CC(=O)Oc1ccccc1C(=O)O"
    monitor.schedule = "weekly"
    monitor.target_jurisdictions = jurisdictions
    monitor.jurisdiction_bundle = bundle
    monitor.monitoring_strategy = strategy
    monitor.watch_targets = targets
    monitor.last_snapshot = {
        "observed_patent_ids": ["US12345678A1"],
        "observed_event_ids": [],
    }
    monitor.last_full_refresh_at = None
    monitor.last_run_at = datetime.now(UTC)
    monitor.cached_patent_ids = ["US12345678A1"]
    monitor.stale_conclusions = []
    monitor.conclusion_status = "fresh"

    async def fake_external_search(_report, query, *, org_id=None):
        results = [{"result_id": "result:existing", "patent_id": "US12345678A1"}]
        if query == "Aspirin US patent":
            results.append({"result_id": "result:new", "patent_id": "US99999999A1"})
        return {
            "scope": {"provider_capabilities": [{"provider_name": "uspto_odp"}]},
            "provider_executions": _complete_provider_receipts(),
            "results": results,
        }

    dispatcher = SimpleNamespace(dispatch_monitor_alert_email=AsyncMock(return_value="task-1"))
    locked_result = MagicMock()
    locked_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=locked_result)
    with (
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.monitor_runtime.record_monitor_conclusion_invalidations",
            new=AsyncMock(return_value=[]),
        ) as record_invalidations,
    ):
        result = await execute_monitor_run(
            db,
            monitor=monitor,
            external_search_fn=fake_external_search,
        )

    assert result.status == "ok"
    assert result.conclusion_status == "review_required"
    assert result.stale_conclusion_count == 2
    assert {item.conclusion_id for item in result.affected_conclusions} == {
        "clearance:global",
        "clearance:US",
    }
    assert monitor.conclusion_status == "review_required"
    assert len(monitor.stale_conclusions) == 2
    alert = next(
        call.args[0]
        for call in db.add.call_args_list
        if getattr(call.args[0], "monitor_id", None) == monitor.id
    )
    assert alert.alert_type == "conclusion_review_required"
    assert len(alert.affected_conclusions) == 2
    assert "attorney reassessment" in alert.summary
    record_invalidations.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_establishes_baseline_without_staling_the_source_report() -> None:
    report = _seed_report()
    strategy, targets, jurisdictions, bundle = build_monitor_seed_from_report(
        report,
        schedule="weekly",
        compound_name="Aspirin",
    )
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.user_id = uuid.uuid4()
    monitor.source_analysis_id = None
    monitor.compound_name = "Aspirin"
    monitor.compound_smiles = "CC(=O)Oc1ccccc1C(=O)O"
    monitor.schedule = "weekly"
    monitor.target_jurisdictions = jurisdictions
    monitor.jurisdiction_bundle = bundle
    monitor.monitoring_strategy = strategy
    monitor.watch_targets = targets
    monitor.last_snapshot = {}
    monitor.last_full_refresh_at = None
    monitor.last_run_at = None
    monitor.cached_patent_ids = []
    monitor.stale_conclusions = []
    monitor.conclusion_status = "fresh"

    async def fake_external_search(_report, _query, *, org_id=None):
        return {
            "scope": {"provider_capabilities": [{"provider_name": "uspto_odp"}]},
            "provider_executions": _complete_provider_receipts(),
            "results": [{"result_id": "result:existing", "patent_id": "US12345678A1"}],
        }

    result = await execute_monitor_run(
        db,
        monitor=monitor,
        external_search_fn=fake_external_search,
    )

    assert result.run_mode == "bootstrap"
    assert result.alert_created is False
    assert result.conclusion_status == "fresh"
    assert result.stale_conclusion_count == 0
    assert result.affected_conclusions == []
    assert monitor.stale_conclusions == []
