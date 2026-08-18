"""Service-layer tests for monitor management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import bind_report_data, make_mock_db, valid_report_data

from api.db.models import AnalysisStatus, MonitorSchedule
from api.errors import APIError
from api.schemas.monitors import CreateMonitorRequest, UpdateMonitorRequest
from api.services.monitor_alert_factory import build_monitor_alert
from api.services.monitor_delta_computation import MonitorRunDelta
from api.services.monitor_runtime import (
    _execute_queries,
    build_monitor_seed_from_report,
    build_monitor_watch_targets,
    execute_monitor_run,
    hydrate_monitor_from_source_analysis,
)
from api.services.monitors import (
    create_monitor,
    delete_monitor,
    dismiss_monitor_alert,
    update_monitor,
)


def make_alert_mock(**kw) -> MagicMock:
    alert = MagicMock()
    alert.id = kw.get("id", uuid.uuid4())
    alert.org_id = kw.get("org_id", uuid.uuid4())
    alert.monitor_id = kw.get("monitor_id", uuid.uuid4())
    alert.dismissed = kw.get("dismissed", False)
    alert.dismissed_by = kw.get("dismissed_by")
    alert.created_at = kw.get("created_at", datetime.now(UTC))
    return alert


def complete_monitor_provider_receipts(result_count: int = 1) -> list[dict]:
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


def test_build_monitor_alert_copies_monitor_org_id() -> None:
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    delta = MonitorRunDelta(
        new_patent_ids=["US12345678A1"],
        new_event_ids=[],
        jurisdiction_deltas={"US": {"patent_count": 1}},
    )

    alert = build_monitor_alert(
        monitor,  # type: ignore[arg-type]
        delta=delta,
        summary="Detected one new patent.",
        run_mode="diff_only",
        run_at=datetime.now(UTC),
    )

    assert alert.org_id == org_id


@pytest.mark.asyncio
async def test_monitor_query_requires_explicit_success_receipt_for_every_provider():
    query = {
        "jurisdiction": "US",
        "query": "US123",
        "reason": "exact",
        "required_provider_names": ["uspto_odp", "patentsview"],
        "coverage_keys": ["US|patent|US123"],
    }

    async def incomplete(_report, _query, *, org_id=None):
        return {
            "provider_executions": [
                complete_monitor_provider_receipts(0)[0],
            ],
            "results": [],
        }

    with pytest.raises(APIError) as exc_info:
        await _execute_queries(
            {},
            queries=[query],
            org_id=uuid.uuid4(),
            external_search_fn=incomplete,
        )

    assert exc_info.value.status == 503
    assert "missing=['patentsview']" in exc_info.value.detail


@pytest.mark.asyncio
async def test_monitor_query_accepts_explicit_successful_zero_result_receipts():
    query = {
        "jurisdiction": "US",
        "query": "US123",
        "reason": "exact",
        "required_provider_names": ["uspto_odp"],
        "coverage_keys": ["US|patent|US123"],
    }

    async def zero_complete(_report, _query, *, org_id=None):
        return {
            "provider_executions": [
                complete_monitor_provider_receipts(0)[0],
            ],
            "results": [],
        }

    results, providers, receipts = await _execute_queries(
        {},
        queries=[query],
        org_id=uuid.uuid4(),
        external_search_fn=zero_complete,
    )

    assert providers == ["uspto_odp"]
    assert len(receipts) == 1
    assert receipts[0]["explicit_zero_results"] is True
    assert results[0]["response"]["results"] == []


@pytest.mark.asyncio
async def test_create_monitor_commits_and_writes_audit_log():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    body = CreateMonitorRequest(
        compound_smiles="CC(=O)Oc1ccccc1C(=O)O",
        compound_name="Aspirin",
        schedule="weekly",
    )
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        monitor = await create_monitor(
            db,
            org_id=org_id,
            user_id=user_id,
            body=body,
            request=request,
        )

    assert str(monitor.schedule) == "weekly"
    assert monitor.compound_name == "Aspirin"
    db.commit.assert_awaited_once()
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True


@pytest.mark.asyncio
async def test_create_monitor_rolls_back_when_audit_fails():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    body = CreateMonitorRequest(
        compound_smiles="CC(=O)Oc1ccccc1C(=O)O",
        compound_name="Aspirin",
        schedule="weekly",
    )

    with (
        patch(
            "api.services.monitors.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await create_monitor(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=body,
            request=request,
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_monitor_can_seed_from_analysis_report():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()
    analysis_id = uuid.uuid4()
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = uuid.uuid4()
    analysis.status = AnalysisStatus.COMPLETED
    analysis.compound_name = "Seeded Compound"
    analysis.compound_smiles = "CCO"
    analysis.report_data = valid_report_data(
        trust_mode="counsel",
        compound={
            "name": "Seeded Compound",
            "canonical_smiles": "CCN",
        },
    )
    bind_report_data(
        analysis.report_data,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    no_monitor_result = MagicMock()
    no_monitor_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, no_monitor_result])
    body = CreateMonitorRequest(
        analysis_id=analysis_id,
        compound_smiles="",
        compound_name="",
        schedule="weekly",
    )
    user_id = uuid.uuid4()
    org_id = analysis.org_id

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        monitor = await create_monitor(
            db,
            org_id=org_id,
            user_id=user_id,
            body=body,
            request=request,
        )

    assert monitor.compound_smiles == "CCN"
    assert monitor.compound_name == "Seeded Compound"
    assert monitor.jurisdiction_bundle == "custom"
    assert monitor.monitoring_strategy["execution_model"] == "conclusion_aware_event_first"
    assert monitor.monitoring_strategy["auto_bigquery_enabled"] is False
    assert any(target["target_type"] == "compound" for target in monitor.watch_targets)
    assert audit_log.await_args is not None
    audit_details = audit_log.await_args.kwargs["details"]
    assert audit_details["source_analysis_id"] == str(analysis_id)
    assert audit_details["source_trust_mode"] == "counsel"


@pytest.mark.asyncio
async def test_create_monitor_normalizes_missing_source_trust_mode_to_explorer():
    db = make_mock_db()
    db.refresh = AsyncMock()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data(
        report_id="report-without-public-mode",
        compound={"name": "Adaptive Compound", "canonical_smiles": "CCN"},
    )
    report.pop("trust_mode", None)
    bind_report_data(report, analysis_id=analysis_id, org_id=org_id)
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        compound_name="Adaptive Compound",
        compound_smiles="CCN",
        report_data=report,
    )
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    no_monitor_result = MagicMock()
    no_monitor_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, no_monitor_result])

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()):
        monitor = await create_monitor(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=CreateMonitorRequest(analysis_id=analysis_id, schedule="weekly"),
            request=MagicMock(),
        )

    assert monitor.source_report_id == "report-without-public-mode"
    assert monitor.source_trust_mode == "explorer"


@pytest.mark.asyncio
async def test_create_monitor_exactly_replays_existing_analysis_monitor():
    db = make_mock_db()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = org_id
    analysis.status = AnalysisStatus.COMPLETED
    analysis.compound_name = "Seeded Compound"
    analysis.compound_smiles = "CCN"
    analysis.report_data = valid_report_data(
        trust_mode="counsel",
        compound={"name": "Seeded Compound", "canonical_smiles": "CCN"},
    )
    bind_report_data(
        analysis.report_data,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.org_id = org_id
    existing.source_analysis_id = analysis_id
    existing.compound_smiles = "CCN"
    existing.compound_name = "Seeded Compound"
    existing.schedule = MonitorSchedule.WEEKLY
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(side_effect=[analysis_result, existing_result])

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        result = await create_monitor(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=CreateMonitorRequest(analysis_id=analysis_id, schedule="weekly"),
            request=MagicMock(),
        )

    assert result is existing
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])
    db.add.assert_not_called()
    db.commit.assert_awaited_once()
    audit_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_monitor_conflicts_when_analysis_monitor_settings_differ():
    db = make_mock_db()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = org_id
    analysis.status = AnalysisStatus.COMPLETED
    analysis.compound_name = "Seeded Compound"
    analysis.compound_smiles = "CCN"
    analysis.report_data = valid_report_data(
        compound={"name": "Seeded Compound", "canonical_smiles": "CCN"},
    )
    bind_report_data(
        analysis.report_data,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    existing = MagicMock()
    existing.compound_smiles = "CCN"
    existing.compound_name = "Seeded Compound"
    existing.schedule = MonitorSchedule.WEEKLY
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(side_effect=[analysis_result, existing_result])

    with pytest.raises(APIError) as exc_info:
        await create_monitor(
            db,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=CreateMonitorRequest(analysis_id=analysis_id, schedule="daily"),
            request=MagicMock(),
        )

    assert exc_info.value.status == 409
    assert "Update the existing monitor" in exc_info.value.detail
    db.rollback.assert_awaited_once()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_monitor_recovers_concurrent_unique_insert_as_replay():
    from sqlalchemy.exc import IntegrityError

    db = make_mock_db()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = org_id
    analysis.status = AnalysisStatus.COMPLETED
    analysis.compound_name = "Seeded Compound"
    analysis.compound_smiles = "CCN"
    analysis.report_data = valid_report_data(
        compound={"name": "Seeded Compound", "canonical_smiles": "CCN"},
    )
    bind_report_data(
        analysis.report_data,
        analysis_id=analysis.id,
        org_id=analysis.org_id,
    )
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.compound_smiles = "CCN"
    existing.compound_name = "Seeded Compound"
    existing.schedule = MonitorSchedule.WEEKLY
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    no_monitor_result = MagicMock()
    no_monitor_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(side_effect=[analysis_result, no_monitor_result, existing_result])
    db.flush = AsyncMock(
        side_effect=IntegrityError(
            "insert",
            {},
            SimpleNamespace(
                diag=SimpleNamespace(constraint_name="uq_monitors_org_source_analysis_id")
            ),
        )
    )

    result = await create_monitor(
        db,
        org_id=org_id,
        user_id=uuid.uuid4(),
        body=CreateMonitorRequest(analysis_id=analysis_id, schedule="weekly"),
        request=MagicMock(),
    )

    assert result is existing
    db.rollback.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_monitor_rejects_running_analysis_seed():
    db = make_mock_db()
    request = MagicMock()
    analysis_id = uuid.uuid4()
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = uuid.uuid4()
    analysis.status = AnalysisStatus.RUNNING
    analysis.report_data = valid_report_data()
    db.execute.return_value.scalar_one_or_none.return_value = analysis
    body = CreateMonitorRequest(
        analysis_id=analysis_id,
        compound_smiles="",
        compound_name="",
        schedule="weekly",
    )

    with pytest.raises(APIError) as exc_info:
        await create_monitor(
            db,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            body=body,
            request=request,
        )

    assert exc_info.value.status == 409
    assert "source-span provenance" in exc_info.value.detail
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_monitor_rejects_completed_analysis_seed_without_source_span_map():
    db = make_mock_db()
    request = MagicMock()
    analysis_id = uuid.uuid4()
    report = valid_report_data()
    report.pop("claim_source_span_map")
    analysis = MagicMock()
    analysis.id = analysis_id
    analysis.org_id = uuid.uuid4()
    analysis.status = AnalysisStatus.COMPLETED
    analysis.report_data = report
    db.execute.return_value.scalar_one_or_none.return_value = analysis
    body = CreateMonitorRequest(
        analysis_id=analysis_id,
        compound_smiles="",
        compound_name="",
        schedule="weekly",
    )

    with pytest.raises(APIError) as exc_info:
        await create_monitor(
            db,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            body=body,
            request=request,
        )

    assert exc_info.value.status == 409
    assert "source-span provenance" in exc_info.value.detail
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_monitor_writes_fail_closed_audit_log():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    no_open_reassessment = MagicMock()
    no_open_reassessment.scalar_one_or_none.return_value = None
    delete_alerts_result = MagicMock()
    db.execute = AsyncMock(side_effect=[monitor_result, no_open_reassessment, delete_alerts_result])
    user_id = uuid.uuid4()

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        await delete_monitor(
            db,
            monitor_id=monitor.id,
            org_id=monitor.org_id,
            user_id=user_id,
            request=MagicMock(),
        )

    db.delete.assert_awaited_once_with(monitor)
    db.commit.assert_awaited_once()
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["user_id"] == user_id


@pytest.mark.asyncio
async def test_delete_monitor_rolls_back_when_audit_fails():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    no_open_reassessment = MagicMock()
    no_open_reassessment.scalar_one_or_none.return_value = None
    delete_alerts_result = MagicMock()
    db.execute = AsyncMock(side_effect=[monitor_result, no_open_reassessment, delete_alerts_result])

    with (
        patch(
            "api.services.monitors.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await delete_monitor(
            db,
            monitor_id=monitor.id,
            org_id=monitor.org_id,
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_dismiss_monitor_alert_updates_state():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    alert = make_alert_mock(monitor_id=monitor.id)
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    alert_result = MagicMock()
    alert_result.scalar_one_or_none.return_value = alert
    db.execute = AsyncMock(side_effect=[monitor_result, alert_result])

    user_id = uuid.uuid4()
    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        await dismiss_monitor_alert(
            db,
            monitor_id=monitor.id,
            alert_id=alert.id,
            org_id=uuid.uuid4(),
            user_id=user_id,
            request=MagicMock(),
        )

    assert alert.dismissed is True
    assert alert.dismissed_by == user_id
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_monitor_writes_fail_closed_audit_log():
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.monitoring_strategy = {}
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=monitor_result)
    user_id = uuid.uuid4()

    with patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log:
        result = await update_monitor(
            db,
            monitor_id=monitor.id,
            org_id=monitor.org_id,
            user_id=user_id,
            body=UpdateMonitorRequest(schedule="daily", is_active=False),  # type: ignore[call-arg]
            request=MagicMock(),
        )

    assert result is monitor
    assert monitor.schedule.value == "daily"
    assert monitor.is_active is False
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["user_id"] == user_id
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["details"]["changed_fields"] == [
        "schedule",
        "is_active",
    ]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(monitor)


@pytest.mark.asyncio
async def test_update_monitor_reseeds_report_derived_watch_targets() -> None:
    db = make_mock_db()
    db.refresh = AsyncMock()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = org_id
    monitor.source_analysis_id = analysis_id
    monitor.compound_smiles = "CCO"
    monitor.compound_name = "Sofosbuvir"
    monitor.schedule = MonitorSchedule.WEEKLY
    monitor.monitoring_strategy = {"search_terms": {}}
    monitor.watch_targets = []
    report_data = valid_report_data()
    report_data.update(
        {
            "report_id": "report-5011",
            "target_jurisdictions": ["US", "EP"],
            "matter_evidence_index": {"patent_records": []},
            "patent_analyses": [
                {
                    "patent_id": "WO0000000002A1",
                    "title": "Nucleoside phosphoramidate prodrugs",
                    "assignee": "Fictional Helix Therapeutics",
                    "risk_level": "high",
                }
            ],
        }
    )
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=monitor_result)

    with (
        patch(
            "api.services.monitors._resolve_monitor_seed",
            new=AsyncMock(
                return_value=(
                    "CCO",
                    "Sofosbuvir",
                    {"source_trust_mode": "counsel"},
                    report_data,
                )
            ),
        ),
        patch("api.services.monitors.write_audit_log", new=AsyncMock()) as audit_log,
    ):
        result = await update_monitor(
            db,
            monitor_id=monitor.id,
            org_id=org_id,
            user_id=uuid.uuid4(),
            body=UpdateMonitorRequest(schedule="daily", is_active=True),
            request=MagicMock(),
        )

    assert result is monitor
    assert monitor.source_report_id == "report-5011"
    assert monitor.target_jurisdictions == ["US", "EP"]
    assert monitor.monitoring_strategy["search_terms"]["key_assignees"] == (
        "Fictional Helix Therapeutics"
    )
    assert [
        target["target_id"] for target in monitor.watch_targets if target["target_type"] == "patent"
    ] == ["WO0000000002A1"]
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["details"]["changed_fields"] == [
        "schedule",
        "is_active",
        "report_seed",
    ]


@pytest.mark.asyncio
async def test_update_monitor_rolls_back_when_audit_fails():
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.monitoring_strategy = {}
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    db.execute = AsyncMock(return_value=monitor_result)

    with (
        patch(
            "api.services.monitors.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await update_monitor(
            db,
            monitor_id=monitor.id,
            org_id=monitor.org_id,
            user_id=uuid.uuid4(),
            body=UpdateMonitorRequest(is_active=False),  # type: ignore[call-arg]
            request=MagicMock(),
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_dismiss_monitor_alert_rolls_back_when_audit_fails():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    alert = make_alert_mock(monitor_id=monitor.id)
    monitor_result = MagicMock()
    monitor_result.scalar_one_or_none.return_value = monitor
    alert_result = MagicMock()
    alert_result.scalar_one_or_none.return_value = alert
    db.execute = AsyncMock(side_effect=[monitor_result, alert_result])

    with (
        patch(
            "api.services.monitors.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await dismiss_monitor_alert(
            db,
            monitor_id=monitor.id,
            alert_id=alert.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_monitor_run_bootstraps_snapshot_without_alert():
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
    monitor.target_jurisdictions = ["US", "EP"]
    monitor.jurisdiction_bundle = "us_europe"
    monitor.monitoring_strategy = {
        "version": "2026-04-monitor-v1",
        "search_terms": {"key_assignees": "Example Pharma"},
    }
    monitor.watch_targets = [
        {"jurisdiction": "US", "target_type": "patent", "target_id": "US12345678A1"},
        {"jurisdiction": "EP", "target_type": "patent", "target_id": "EP1234567A1"},
    ]
    monitor.last_snapshot = {}
    monitor.last_full_refresh_at = None
    monitor.last_run_at = None
    monitor.cached_patent_ids = []

    async def fake_external_search(_report, query, *, org_id=None):
        return {
            "scope": {
                "provider_capabilities": [
                    {"provider_name": "uspto_odp"},
                    {"provider_name": "epo_ops"},
                ]
            },
            "provider_executions": complete_monitor_provider_receipts(),
            "results": [
                {
                    "result_id": f"result:{query}",
                    "patent_id": "US12345678A1" if "US" in query else "EP1234567A1",
                }
            ],
        }

    result = await execute_monitor_run(
        db,
        monitor=monitor,
        external_search_fn=fake_external_search,
    )

    assert result.status == "ok"
    assert result.run_mode == "bootstrap"
    assert result.alert_created is False
    assert monitor.last_snapshot["completed_snapshot"]["observed_patent_ids"] == [
        "US12345678A1",
        "EP1234567A1",
    ]
    assert monitor.last_snapshot["coverage_progress"]["complete"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_cursor_preserves_completed_snapshot_until_full_manifest_finishes():
    report = valid_report_data(target_jurisdictions=["US"])
    report["matter_evidence_index"]["patent_records"] = [
        {
            "patent_id": f"US20260000{index}A1",
            "jurisdiction": "US",
            "title": f"Critical patent {index}",
            "family_id": f"family-{index}",
        }
        for index in range(12)
    ]
    strategy, targets, jurisdictions, bundle = build_monitor_seed_from_report(
        report,
        schedule="daily",
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
    monitor.compound_smiles = "CCO"
    monitor.schedule = "daily"
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
            "provider_executions": complete_monitor_provider_receipts(0),
            "results": [],
        }

    first = await execute_monitor_run(
        db,
        monitor=monitor,
        external_search_fn=fake_external_search,
    )

    assert first.status == "partial"
    assert first.coverage_complete is False
    assert first.coverage_cursor == 10
    assert first.coverage_total > first.coverage_cursor
    assert monitor.last_run_at is None
    assert monitor.last_run_status == "coverage_incomplete"
    assert monitor.conclusion_status == "coverage_incomplete"
    assert monitor.last_snapshot["completed_snapshot"] == {}
    assert monitor.last_snapshot["coverage_progress"]["accumulator"]["completed_coverage_keys"]
    assert monitor.cached_patent_ids == []
    assert not any(
        getattr(call.args[0], "monitor_id", None) == monitor.id for call in db.add.call_args_list
    )

    result = first
    for _ in range(10):
        if result.coverage_complete:
            break
        result = await execute_monitor_run(
            db,
            monitor=monitor,
            external_search_fn=fake_external_search,
        )

    assert result.status == "ok"
    assert result.coverage_complete is True
    assert monitor.last_snapshot["coverage_progress"]["complete"] is True
    completed_keys = set(monitor.last_snapshot["completed_snapshot"]["completed_coverage_keys"])
    assert {row["coverage_key"] for row in strategy["coverage_manifest"]} <= completed_keys


@pytest.mark.asyncio
async def test_execute_monitor_run_creates_alert_for_new_patent_delta():
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
    monitor.target_jurisdictions = ["US"]
    monitor.jurisdiction_bundle = "custom"
    monitor.monitoring_strategy = {"version": "2026-04-monitor-v1", "search_terms": {}}
    monitor.watch_targets = [
        {"jurisdiction": "US", "target_type": "patent", "target_id": "US12345678A1"}
    ]
    monitor.last_snapshot = {"observed_patent_ids": ["US12345678A1"], "observed_event_ids": []}
    monitor.last_full_refresh_at = datetime.now(UTC)
    monitor.last_run_at = datetime.now(UTC)
    monitor.cached_patent_ids = ["US12345678A1"]

    async def fake_external_search(_report, _query, *, org_id=None):
        return {
            "scope": {"provider_capabilities": [{"provider_name": "uspto_odp"}]},
            "provider_executions": complete_monitor_provider_receipts(),
            "results": [
                {"result_id": "result:1", "patent_id": "US12345678A1"},
                {"result_id": "result:2", "patent_id": "US99999999A1"},
            ],
        }

    dispatcher = SimpleNamespace(dispatch_monitor_alert_email=AsyncMock(return_value="task-1"))
    with patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher):
        result = await execute_monitor_run(
            db,
            monitor=monitor,
            external_search_fn=fake_external_search,
        )

    assert result.status == "ok"
    assert result.alert_created is True
    assert result.new_patent_ids == ["US99999999A1"]
    assert db.add.call_count >= 1
    dispatcher.dispatch_monitor_alert_email.assert_awaited_once_with(
        user_id=str(monitor.user_id),
        monitor_id=str(monitor.id),
        alert_id=str(result.alert_id),
        org_id=str(monitor.org_id),
    )


@pytest.mark.asyncio
async def test_execute_monitor_run_skips_alert_email_when_creator_removed():
    """A monitor whose user_id was SET NULL must not dispatch a doomed email task."""
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    # Creator user was removed: ondelete=SET NULL leaves user_id None.
    monitor.user_id = None
    monitor.source_analysis_id = None
    monitor.compound_name = "Aspirin"
    monitor.compound_smiles = "CC(=O)Oc1ccccc1C(=O)O"
    monitor.schedule = "weekly"
    monitor.target_jurisdictions = ["US"]
    monitor.jurisdiction_bundle = "custom"
    monitor.monitoring_strategy = {"version": "2026-04-monitor-v1", "search_terms": {}}
    monitor.watch_targets = [
        {"jurisdiction": "US", "target_type": "patent", "target_id": "US12345678A1"}
    ]
    monitor.last_snapshot = {"observed_patent_ids": ["US12345678A1"], "observed_event_ids": []}
    monitor.last_full_refresh_at = datetime.now(UTC)
    monitor.last_run_at = datetime.now(UTC)
    monitor.cached_patent_ids = ["US12345678A1"]

    async def fake_external_search(_report, _query, *, org_id=None):
        return {
            "scope": {"provider_capabilities": [{"provider_name": "uspto_odp"}]},
            "provider_executions": complete_monitor_provider_receipts(),
            "results": [
                {"result_id": "result:1", "patent_id": "US12345678A1"},
                {"result_id": "result:2", "patent_id": "US99999999A1"},
            ],
        }

    dispatcher = SimpleNamespace(dispatch_monitor_alert_email=AsyncMock(return_value="task-1"))
    with patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher):
        result = await execute_monitor_run(
            db,
            monitor=monitor,
            external_search_fn=fake_external_search,
        )

    # The alert row is still created and persisted; only the email is skipped.
    assert result.alert_created is True
    dispatcher.dispatch_monitor_alert_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_hydrate_monitor_fails_closed_without_source_span_provenance():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.source_analysis_id = uuid.uuid4()
    monitor.compound_name = "Persisted Monitor Compound"
    monitor.compound_smiles = "CCO"
    monitor.schedule = "weekly"
    monitor.target_jurisdictions = ["US"]
    monitor.jurisdiction_bundle = "custom"
    monitor.monitoring_strategy = {"modality": "small_molecule", "search_terms": {}}
    monitor.watch_targets = [
        {"jurisdiction": "US", "target_type": "patent", "target_id": "US91000011A1"}
    ]
    monitor.source_report_id = "old-report"
    monitor.source_trust_mode = "counsel"

    report = valid_report_data(
        report_id="unsafe-source-report",
        compound={"name": "Unsafe Source", "canonical_smiles": "CCC"},
    )
    report.pop("claim_source_span_map")
    analysis = MagicMock(
        id=monitor.source_analysis_id,
        org_id=monitor.org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    with pytest.raises(APIError) as exc_info:
        await hydrate_monitor_from_source_analysis(db, monitor=monitor)

    assert exc_info.value.status == 409
    assert "run was refused" in exc_info.value.detail
    assert monitor.source_report_id == "old-report"
    assert monitor.source_trust_mode == "counsel"


@pytest.mark.asyncio
async def test_hydrate_monitor_normalizes_missing_source_trust_mode_to_explorer():
    db = make_mock_db()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.source_analysis_id = uuid.uuid4()
    monitor.compound_name = "Adaptive Compound"
    monitor.compound_smiles = "CCN"
    monitor.schedule = "weekly"
    report = valid_report_data(
        report_id="adaptive-report",
        compound={"name": "Adaptive Compound", "canonical_smiles": "CCN"},
    )
    report.pop("trust_mode", None)
    bind_report_data(
        report,
        analysis_id=monitor.source_analysis_id,
        org_id=monitor.org_id,
    )
    analysis = MagicMock(
        id=monitor.source_analysis_id,
        org_id=monitor.org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    hydrated = await hydrate_monitor_from_source_analysis(db, monitor=monitor)

    assert hydrated["trust_mode"] == "monitor"
    assert monitor.source_report_id == "adaptive-report"
    assert monitor.source_trust_mode == "explorer"


@pytest.mark.asyncio
async def test_execute_monitor_run_refuses_source_report_without_provenance():
    db = make_mock_db()
    db.refresh = AsyncMock()
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.user_id = uuid.uuid4()
    monitor.source_analysis_id = uuid.uuid4()
    monitor.compound_name = "Persisted Monitor Compound"
    monitor.compound_smiles = "CCO"
    monitor.schedule = "weekly"
    monitor.target_jurisdictions = ["US"]
    monitor.jurisdiction_bundle = "custom"
    monitor.monitoring_strategy = {"modality": "small_molecule", "search_terms": {}}
    monitor.watch_targets = [
        {"jurisdiction": "US", "target_type": "patent", "target_id": "US91000011A1"}
    ]
    monitor.source_report_id = "old-report"
    monitor.source_trust_mode = "counsel"
    monitor.last_snapshot = {}
    monitor.last_full_refresh_at = None
    monitor.last_run_at = None
    monitor.cached_patent_ids = []

    report = valid_report_data(
        report_id="unsafe-source-report",
        compound={"name": "Unsafe Source", "canonical_smiles": "CCC"},
    )
    report["matter_evidence_index"] = {
        "patent_records": [
            {
                "patent_id": "US91000015A1",
                "jurisdiction": "US",
                "title": "Unsafe source patent",
            }
        ]
    }
    report.pop("claim_source_span_map")
    analysis = MagicMock(
        id=monitor.source_analysis_id,
        org_id=monitor.org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    db.execute.return_value.scalar_one_or_none.return_value = analysis

    async def fake_external_search(report_data, query, *, org_id=None):
        return {
            "scope": {"provider_capabilities": [{"provider_name": "uspto_odp"}]},
            "provider_executions": complete_monitor_provider_receipts(),
            "results": [{"result_id": "persisted", "patent_id": "US91000011A1"}],
        }

    with pytest.raises(APIError) as exc_info:
        await execute_monitor_run(
            db,
            monitor=monitor,
            external_search_fn=fake_external_search,
        )

    assert exc_info.value.status == 409
    assert "run was refused" in exc_info.value.detail
    assert monitor.cached_patent_ids == []
    assert monitor.source_report_id == "old-report"
    assert monitor.source_trust_mode == "counsel"


@pytest.mark.asyncio
async def test_hydrate_report_linked_monitor_fails_closed_when_source_analysis_is_missing():
    db = make_mock_db()
    db.execute.return_value.scalar_one_or_none.return_value = None
    monitor = MagicMock()
    monitor.id = uuid.uuid4()
    monitor.org_id = uuid.uuid4()
    monitor.source_analysis_id = uuid.uuid4()

    with pytest.raises(APIError) as exc_info:
        await hydrate_monitor_from_source_analysis(db, monitor=monitor)

    assert exc_info.value.status == 409
    assert "source analysis is unavailable" in exc_info.value.detail.lower()


def test_build_monitor_watch_targets_adds_ep_and_uk_post_grant_targets() -> None:
    report_data = {
        "jurisdiction_matrix": [
            {"jurisdiction": "EP", "lane_status": "counsel_certified"},
            {"jurisdiction": "UK", "lane_status": "screening_only"},
        ],
        "matter_evidence_index": {
            "patent_records": [
                {
                    "patent_id": "EP1234567B1",
                    "jurisdiction": "EP",
                    "title": "EP launch patent",
                    "ep_register_status": "Granted",
                    "has_opposition_events": True,
                    "ep_unitary_effect_status": "registered",
                    "ep_upc_opt_out_status": "opted_out",
                    "ep_validation_states": ["DE", "FR", "UK"],
                }
            ]
        },
    }

    targets = build_monitor_watch_targets(report_data, compound_name="Aspirin")
    target_ids = {target["target_id"] for target in targets}

    assert "EP1234567B1:ep_register_status:Granted" in target_ids
    assert "EP1234567B1:ep_opposition" in target_ids
    assert "EP1234567B1:ep_unitary_effect:registered" in target_ids
    assert "EP1234567B1:ep_upc_opt_out:opted_out" in target_ids
    assert "EP1234567B1:uk_validation_state" in target_ids


def test_monitor_seed_preserves_patent_analyses_when_evidence_index_is_empty() -> None:
    report_data = {
        "compound": {"name": "Sofosbuvir"},
        "target_jurisdictions": ["US", "EP"],
        "matter_evidence_index": {"patent_records": []},
        "patent_analyses": [
            {
                "patent_id": "WO0000000002A1",
                "title": "Nucleoside phosphoramidate prodrugs",
                "assignee": "Fictional Helix Therapeutics",
                "risk_level": "high",
            },
            {
                "patent_id": "WO0000000004A1",
                "title": "Solid forms of an antiviral compound",
                "assignee": "Fictional Helix Therapeutics",
                "risk_level": "high",
            },
        ],
    }

    strategy, targets, jurisdictions, _ = build_monitor_seed_from_report(
        report_data,
        schedule="daily",
        compound_name="Sofosbuvir",
    )

    patent_targets = [target for target in targets if target["target_type"] == "patent"]
    assert [target["target_id"] for target in patent_targets] == [
        "WO0000000002A1",
        "WO0000000004A1",
    ]
    assert {target["jurisdiction"] for target in patent_targets} == {"GLOBAL"}
    assert strategy["search_terms"]["key_assignees"] == "Fictional Helix Therapeutics"
    assert jurisdictions == ["US", "EP"]
