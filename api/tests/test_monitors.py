"""Tests for /api/v1/monitors endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import bind_report_data, make_paginated_result, valid_report_data

from api.db.models import AnalysisStatus, MonitorSchedule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_monitor_mock(**kw) -> MagicMock:
    """Create a mock Monitor ORM object."""
    m = MagicMock()
    m.id = kw.get("id", uuid.uuid4())
    m.org_id = kw.get("org_id", uuid.uuid4())
    m.user_id = kw.get("user_id", uuid.uuid4())
    m.source_analysis_id = kw.get("source_analysis_id")
    m.compound_smiles = kw.get("compound_smiles", "CC(=O)Oc1ccccc1C(=O)O")
    m.compound_name = kw.get("compound_name", "Aspirin")
    m.source_report_id = kw.get("source_report_id", "")
    m.source_trust_mode = kw.get("source_trust_mode", "counsel")
    m.schedule = kw.get("schedule", MonitorSchedule.WEEKLY)
    m.is_active = kw.get("is_active", True)
    m.jurisdiction_bundle = kw.get("jurisdiction_bundle", "us_europe")
    m.target_jurisdictions = kw.get("target_jurisdictions", ["US", "EP"])
    m.strategy_version = kw.get("strategy_version", "2026-07-monitor-v2")
    m.monitoring_strategy = kw.get(
        "monitoring_strategy",
        {
            "execution_model": "conclusion_aware_event_first",
            "default_run_mode": "diff_only",
            "auto_bigquery_enabled": False,
        },
    )
    m.watch_targets = kw.get(
        "watch_targets",
        [{"jurisdiction": "US", "target_type": "patent", "target_id": "US12345678A1"}],
    )
    m.last_run_at = kw.get("last_run_at")
    m.last_full_refresh_at = kw.get("last_full_refresh_at")
    m.last_run_mode = kw.get("last_run_mode", "")
    m.last_run_status = kw.get("last_run_status", "pending")
    m.last_run_summary = kw.get("last_run_summary", "")
    m.last_patent_count = kw.get("last_patent_count", 0)
    m.cached_patent_ids = kw.get("cached_patent_ids", [])
    m.last_snapshot = kw.get("last_snapshot", {})
    m.conclusion_status = kw.get("conclusion_status", "fresh")
    m.stale_conclusions = kw.get("stale_conclusions", [])
    m.stale_conclusion_count = len(m.stale_conclusions)
    m.created_at = kw.get("created_at", datetime.now(UTC))
    return m


def make_alert_mock(**kw) -> MagicMock:
    """Create a mock MonitorAlert ORM object."""
    a = MagicMock()
    a.id = kw.get("id", uuid.uuid4())
    a.org_id = kw.get("org_id", uuid.uuid4())
    a.monitor_id = kw.get("monitor_id", uuid.uuid4())
    a.alert_type = kw.get("alert_type", "new_patent_delta")
    a.severity = kw.get("severity", "medium")
    a.summary = kw.get("summary", "Detected a new patent delta.")
    a.strategy_mode = kw.get("strategy_mode", "diff_only")
    a.new_patent_ids = kw.get("new_patent_ids", ["US12345678A1"])
    a.new_event_ids = kw.get("new_event_ids", [])
    a.jurisdiction_deltas = kw.get("jurisdiction_deltas", {"US": {"patent_count": 1}})
    a.affected_conclusions = kw.get("affected_conclusions", [])
    a.stale_conclusion_count = len(a.affected_conclusions)
    a.new_patent_count = kw.get("new_patent_count", 1)
    a.run_at = kw.get("run_at", datetime.now(UTC))
    a.dismissed = kw.get("dismissed", False)
    a.dismissed_by = kw.get("dismissed_by")
    a.created_at = kw.get("created_at", datetime.now(UTC))
    return a


# ---------------------------------------------------------------------------
# POST /api/v1/monitors — create
# ---------------------------------------------------------------------------


class TestCreateMonitor:
    """POST /api/v1/monitors"""

    @pytest.mark.asyncio
    async def test_create_monitor(self, scientist_client):
        c, db = scientist_client

        # db.refresh needs to be a no-op for the mock
        db.refresh = AsyncMock()

        resp = await c.post(
            "/api/v1/monitors",
            json={
                "compound_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "compound_name": "Aspirin",
                "schedule": "weekly",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["compound_smiles"] == "CC(=O)Oc1ccccc1C(=O)O"
        assert data["compound_name"] == "Aspirin"
        assert data["schedule"] == "weekly"
        assert data["is_active"] is True
        assert db.add.call_count >= 1
        assert db.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_create_monitor_missing_smiles(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/monitors",
            json={"compound_name": "Aspirin", "schedule": "weekly"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_monitor_from_analysis_seed(self, scientist_client):
        c, db = scientist_client
        db.refresh = AsyncMock()
        analysis_id = uuid.uuid4()
        analysis = MagicMock()
        analysis.id = analysis_id
        analysis.org_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
        analysis.status = AnalysisStatus.COMPLETED
        analysis.compound_name = "Aspirin"
        analysis.compound_smiles = "CCO"
        analysis.report_data = valid_report_data(
            trust_mode="explorer",
            compound={
                "name": "Aspirin",
                "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
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

        resp = await c.post(
            "/api/v1/monitors",
            json={
                "analysis_id": str(analysis_id),
                "schedule": "weekly",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["compound_smiles"] == "CC(=O)Oc1ccccc1C(=O)O"
        assert data["compound_name"] == "Aspirin"
        assert data["monitoring_strategy"]["execution_model"] == "conclusion_aware_event_first"
        assert data["monitoring_strategy"]["auto_bigquery_enabled"] is False
        assert data["source_analysis_id"] == str(analysis_id)

    @pytest.mark.asyncio
    async def test_create_monitor_rejects_analysis_seed_without_source_span_map(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        report = valid_report_data()
        report.pop("claim_source_span_map")
        analysis = MagicMock()
        analysis.id = analysis_id
        analysis.org_id = uuid.uuid4()
        analysis.status = AnalysisStatus.COMPLETED
        analysis.compound_name = "Aspirin"
        analysis.compound_smiles = "CCO"
        analysis.report_data = report
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        db.execute = AsyncMock(return_value=analysis_result)

        resp = await c.post(
            "/api/v1/monitors",
            json={
                "analysis_id": str(analysis_id),
                "schedule": "weekly",
            },
        )

        assert resp.status_code == 409
        assert "source-span provenance" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_monitor_empty_smiles(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/monitors",
            json={"compound_smiles": "", "schedule": "weekly"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_monitor_invalid_schedule(self, scientist_client):
        c, db = scientist_client
        db.refresh = AsyncMock()

        resp = await c.post(
            "/api/v1/monitors",
            json={
                "compound_smiles": "CCO",
                "schedule": "hourly",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_monitor_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client

        resp = await c.post(
            "/api/v1/monitors",
            json={
                "compound_smiles": "CCO",
                "schedule": "weekly",
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/monitors — list
# ---------------------------------------------------------------------------


class TestListMonitors:
    """GET /api/v1/monitors"""

    @pytest.mark.asyncio
    async def test_list_monitors(self, scientist_client):
        c, db = scientist_client
        monitors = [make_monitor_mock(), make_monitor_mock()]
        count_result, items_result = make_paginated_result(2, monitors)
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/monitors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_monitors_empty(self, scientist_client):
        c, db = scientist_client
        count_result, items_result = make_paginated_result(0, [])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/monitors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_monitors_filter_active(self, scientist_client):
        c, db = scientist_client
        active_monitor = make_monitor_mock(is_active=True)
        count_result, items_result = make_paginated_result(1, [active_monitor])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/monitors?is_active=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_monitors_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.get("/api/v1/monitors")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/monitors/{id} — detail
# ---------------------------------------------------------------------------


class TestGetMonitor:
    """GET /api/v1/monitors/{id}"""

    @pytest.mark.asyncio
    async def test_get_monitor(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        db.execute.return_value.scalar_one_or_none.return_value = monitor

        resp = await c.get(f"/api/v1/monitors/{monitor_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(monitor_id)

    @pytest.mark.asyncio
    async def test_get_monitor_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/monitors/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Monitor not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_monitor_by_analysis(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        monitor = make_monitor_mock(source_analysis_id=analysis_id)
        db.execute.return_value.scalar_one_or_none.return_value = monitor

        resp = await c.get(f"/api/v1/monitors/by-analysis/{analysis_id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(monitor.id)
        assert resp.json()["source_analysis_id"] == str(analysis_id)

    @pytest.mark.asyncio
    async def test_get_monitor_by_analysis_returns_null_when_absent(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/monitors/by-analysis/{uuid.uuid4()}")

        assert resp.status_code == 200
        assert resp.json() is None


# ---------------------------------------------------------------------------
# PATCH /api/v1/monitors/{id} — update
# ---------------------------------------------------------------------------


class TestUpdateMonitor:
    """PATCH /api/v1/monitors/{id}"""

    @pytest.mark.asyncio
    async def test_update_monitor(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        db.execute.return_value.scalar_one_or_none.return_value = monitor
        db.refresh = AsyncMock()

        resp = await c.patch(
            f"/api/v1/monitors/{monitor_id}",
            json={"is_active": False, "compound_name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert monitor.is_active is False
        assert monitor.compound_name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_monitor_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.patch(
            f"/api/v1/monitors/{uuid.uuid4()}",
            json={"is_active": False},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_monitor_schedule(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        db.execute.return_value.scalar_one_or_none.return_value = monitor
        db.refresh = AsyncMock()

        resp = await c.patch(
            f"/api/v1/monitors/{monitor_id}",
            json={"schedule": "daily"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/v1/monitors/{id}
# ---------------------------------------------------------------------------


class TestDeleteMonitor:
    """DELETE /api/v1/monitors/{id}"""

    @pytest.mark.asyncio
    async def test_delete_monitor(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)

        # Lookup, durable reassessment check, then bulk alert deletion.
        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        no_open_reassessment = MagicMock()
        no_open_reassessment.scalar_one_or_none.return_value = None
        delete_alerts_result = MagicMock()

        db.execute = AsyncMock(
            side_effect=[monitor_result, no_open_reassessment, delete_alerts_result]
        )

        resp = await c.delete(f"/api/v1/monitors/{monitor_id}")
        assert resp.status_code == 204
        db.delete.assert_awaited()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_monitor_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/monitors/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_monitor_with_alerts(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)

        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        no_open_reassessment = MagicMock()
        no_open_reassessment.scalar_one_or_none.return_value = None
        delete_alerts_result = MagicMock()
        db.execute = AsyncMock(
            side_effect=[monitor_result, no_open_reassessment, delete_alerts_result]
        )

        resp = await c.delete(f"/api/v1/monitors/{monitor_id}")
        assert resp.status_code == 204
        # Bulk DELETE for alerts via execute + monitor via delete
        assert db.execute.await_count >= 3  # lookup + reassessment guard + alert delete
        assert db.delete.await_count == 1  # monitor itself


# ---------------------------------------------------------------------------
# GET /api/v1/monitors/{id}/alerts — list alerts
# ---------------------------------------------------------------------------


class TestListAlerts:
    """GET /api/v1/monitors/{id}/alerts"""

    @pytest.mark.asyncio
    async def test_list_alerts(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        alerts = [make_alert_mock(monitor_id=monitor_id), make_alert_mock(monitor_id=monitor_id)]

        # First call: verify monitor exists, then count, then items
        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = alerts

        db.execute = AsyncMock(side_effect=[monitor_result, count_result, items_result])

        resp = await c.get(f"/api/v1/monitors/{monitor_id}/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_alerts_monitor_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/monitors/{uuid.uuid4()}/alerts")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)

        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[monitor_result, count_result, items_result])

        resp = await c.get(f"/api/v1/monitors/{monitor_id}/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# POST /api/v1/monitors/{id}/alerts/{alert_id}/dismiss
# ---------------------------------------------------------------------------


class TestDismissAlert:
    """POST /api/v1/monitors/{id}/alerts/{alert_id}/dismiss"""

    @pytest.mark.asyncio
    async def test_dismiss_alert(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        alert_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        alert = make_alert_mock(id=alert_id, monitor_id=monitor_id)

        # First call: verify monitor, second call: find alert
        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        alert_result = MagicMock()
        alert_result.scalar_one_or_none.return_value = alert

        db.execute = AsyncMock(side_effect=[monitor_result, alert_result])

        resp = await c.post(f"/api/v1/monitors/{monitor_id}/alerts/{alert_id}/dismiss")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dismissed"
        assert alert.dismissed is True
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dismiss_alert_monitor_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.post(f"/api/v1/monitors/{uuid.uuid4()}/alerts/{uuid.uuid4()}/dismiss")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_dismiss_alert_not_found(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)

        # Monitor exists but alert does not
        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor

        alert_result = MagicMock()
        alert_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[monitor_result, alert_result])

        resp = await c.post(f"/api/v1/monitors/{monitor_id}/alerts/{uuid.uuid4()}/dismiss")
        assert resp.status_code == 404
        assert "Alert not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/v1/monitors/{id}/run
# ---------------------------------------------------------------------------


class TestRunMonitor:
    @pytest.mark.asyncio
    async def test_run_monitor_returns_execution_summary(self, scientist_client):
        c, db = scientist_client
        monitor_id = uuid.uuid4()
        monitor = make_monitor_mock(id=monitor_id)
        monitor_result = MagicMock()
        monitor_result.scalar_one_or_none.return_value = monitor
        db.execute = AsyncMock(return_value=monitor_result)

        lock_cm = AsyncMock()
        lock_cm.__aenter__.return_value = True  # lock acquired
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.monitors.execute_monitor_run", new=AsyncMock()) as run_monitor,
            patch("api.db.session.pinned_advisory_lock", return_value=lock_cm),
        ):
            run_monitor.return_value = {
                "monitor_id": str(monitor_id),
                "run_mode": "diff_only",
                "status": "ok",
                "summary": "Executed diff only monitoring pass.",
                "query_count": 2,
                "alert_created": False,
                "alert_id": None,
                "new_patent_count": 0,
                "new_patent_ids": [],
                "new_event_ids": [],
                "next_recommended_mode": "targeted_refresh",
                "provider_names": ["uspto_odp", "epo_ops"],
            }
            resp = await c.post(
                f"/api/v1/monitors/{monitor_id}/run",
                json={"force_full_refresh": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["monitor_id"] == str(monitor_id)
        assert data["status"] == "ok"
        assert data["run_mode"] in {
            "bootstrap",
            "diff_only",
            "targeted_refresh",
            "full_refresh",
        }
        assert isinstance(data["provider_names"], list)


# ---------------------------------------------------------------------------
# Org isolation
# ---------------------------------------------------------------------------


class TestMonitorOrgIsolation:
    """Monitors from other orgs should not be accessible."""

    @pytest.mark.asyncio
    async def test_monitor_org_isolation(self, scientist_client):
        """Cannot access a monitor that belongs to a different org.

        The route filters by org_id, so a non-matching monitor returns 404.
        """
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        other_org_monitor_id = uuid.uuid4()
        resp = await c.get(f"/api/v1/monitors/{other_org_monitor_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_other_org_monitor_404(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.patch(
            f"/api/v1/monitors/{uuid.uuid4()}",
            json={"is_active": False},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_org_monitor_404(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/monitors/{uuid.uuid4()}")
        assert resp.status_code == 404
