"""Tests for /api/v1/admin/analytics routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.admin_analytics import (
    AuditLogEntryExtended,
    DailyCost,
    ModelCost,
    ModelUsageDetail,
    OrgUsage,
    StatusBreakdown,
    StepCost,
    TopCompound,
)
from api.services.admin_analytics import (
    AuditLogPage,
    CostBreakdownSummary,
    ModelUsageSummary,
    UsageAnalyticsSummary,
)


class TestAdminAnalyticsUsageRoute:
    @pytest.mark.asyncio
    async def test_usage_admin_only(self, scientist_client):
        c, _db = scientist_client

        resp = await c.get("/api/v1/admin/analytics/usage")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_usage_returns_service_payload(self, admin_client):
        c, _db = admin_client
        org_id = uuid.uuid4()
        summary = UsageAnalyticsSummary(
            org_usage=[
                OrgUsage(
                    org_id=org_id,
                    org_name="Praviar Labs",
                    analysis_count=4,
                    total_cost_usd=20.0,
                    avg_cost_usd=5.0,
                )
            ],
            status_breakdown=[StatusBreakdown(status="completed", count=3)],
            top_compounds=[
                TopCompound(
                    compound_name="aspirin",
                    compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
                    analysis_count=2,
                )
            ],
            total_analyses=4,
            avg_cost_per_analysis=5.0,
            avg_duration_seconds=55.5,
            period="month",
        )

        with patch(
            "api.routes.admin_analytics.get_usage_analytics_summary",
            new=AsyncMock(return_value=summary),
        ) as get_usage_mock:
            resp = await c.get("/api/v1/admin/analytics/usage")

        assert resp.status_code == 200
        assert resp.json() == {
            "org_usage": [
                {
                    "org_id": str(org_id),
                    "org_name": "Praviar Labs",
                    "analysis_count": 4,
                    "total_cost_usd": 20.0,
                    "avg_cost_usd": 5.0,
                }
            ],
            "status_breakdown": [{"status": "completed", "count": 3}],
            "top_compounds": [
                {
                    "compound_name": "aspirin",
                    "compound_smiles": "CC(=O)Oc1ccccc1C(O)=O",
                    "analysis_count": 2,
                }
            ],
            "total_analyses": 4,
            "avg_cost_per_analysis": 5.0,
            "avg_duration_seconds": 55.5,
            "period": "month",
        }
        assert get_usage_mock.await_count == 1
        assert get_usage_mock.await_args is not None
        assert get_usage_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_usage_platform_superadmin_can_view_global_usage(self, admin_client):
        c, _db = admin_client
        summary = UsageAnalyticsSummary(
            org_usage=[],
            status_breakdown=[],
            top_compounds=[],
            total_analyses=0,
            avg_cost_per_analysis=0.0,
            avg_duration_seconds=None,
            period="month",
        )

        with (
            patch("api.routes.admin_analytics._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin_analytics.get_usage_analytics_summary",
                new=AsyncMock(return_value=summary),
            ) as get_usage_mock,
        ):
            resp = await c.get("/api/v1/admin/analytics/usage")

        assert resp.status_code == 200
        assert get_usage_mock.await_args is not None
        assert get_usage_mock.await_args.kwargs["org_id"] is None


class TestAdminAnalyticsCostBreakdownRoute:
    @pytest.mark.asyncio
    async def test_costs_admin_only(self, scientist_client):
        c, _db = scientist_client

        resp = await c.get("/api/v1/admin/analytics/costs")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_costs_returns_service_payload(self, admin_client):
        c, _db = admin_client
        summary = CostBreakdownSummary(
            daily_costs=[
                DailyCost(
                    date="2026-04-11",
                    total_cost_usd=12.3,
                    analysis_count=2,
                    total_input_tokens=1000,
                    total_output_tokens=500,
                )
            ],
            step_costs=[
                StepCost(
                    step_name="step4_analyze",
                    total_cost_usd=12.3,
                    analysis_count=2,
                    avg_cost_usd=6.15,
                )
            ],
            model_costs=[
                ModelCost(
                    model_name="claude-opus-4-6",
                    total_cost_usd=12.3,
                    total_input_tokens=1000,
                    total_output_tokens=500,
                    request_count=2,
                )
            ],
            total_cost_usd=12.3,
            total_input_tokens=1000,
            total_output_tokens=500,
            period="month",
            start_date="2026-04-01",
            end_date="2026-04-11",
        )

        with patch(
            "api.routes.admin_analytics.get_cost_breakdown_summary",
            new=AsyncMock(return_value=summary),
        ) as get_costs_mock:
            resp = await c.get("/api/v1/admin/analytics/costs")

        assert resp.status_code == 200
        assert resp.json()["total_cost_usd"] == 12.3
        assert resp.json()["step_costs"][0]["step_name"] == "step4_analyze"
        assert get_costs_mock.await_count == 1
        assert get_costs_mock.await_args is not None
        assert get_costs_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_costs_rejects_other_org_for_tenant_admin(self, admin_client):
        c, _db = admin_client

        with patch(
            "api.routes.admin_analytics.get_cost_breakdown_summary",
            new=AsyncMock(),
        ) as get_costs_mock:
            resp = await c.get(f"/api/v1/admin/analytics/costs?org_id={uuid.uuid4()}")

        assert resp.status_code == 403
        get_costs_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_costs_platform_superadmin_can_request_global_costs(self, admin_client):
        c, _db = admin_client
        summary = CostBreakdownSummary(
            daily_costs=[],
            step_costs=[],
            model_costs=[],
            total_cost_usd=0.0,
            total_input_tokens=0,
            total_output_tokens=0,
            period="month",
            start_date="2026-04-01",
            end_date="2026-04-11",
        )

        with (
            patch("api.routes.admin_analytics._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin_analytics.get_cost_breakdown_summary",
                new=AsyncMock(return_value=summary),
            ) as get_costs_mock,
        ):
            resp = await c.get("/api/v1/admin/analytics/costs")

        assert resp.status_code == 200
        assert get_costs_mock.await_args is not None
        assert get_costs_mock.await_args.kwargs["org_id"] is None

    @pytest.mark.asyncio
    async def test_costs_rejects_invalid_explicit_date_range(self, admin_client):
        c, _db = admin_client

        resp = await c.get(
            "/api/v1/admin/analytics/costs?start_date=not-a-date&end_date=2026-04-11"
        )

        assert resp.status_code == 422
        assert "start_date must be an ISO-8601" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_costs_rejects_partial_explicit_date_range(self, admin_client):
        c, _db = admin_client

        resp = await c.get("/api/v1/admin/analytics/costs?start_date=2026-04-01")

        assert resp.status_code == 422
        assert "start_date and end_date" in resp.json()["detail"]


class TestAdminAnalyticsModelUsageRoute:
    @pytest.mark.asyncio
    async def test_models_admin_only(self, scientist_client):
        c, _db = scientist_client

        resp = await c.get("/api/v1/admin/analytics/models")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_models_returns_service_payload(self, admin_client):
        c, _db = admin_client
        summary = ModelUsageSummary(
            models=[
                ModelUsageDetail(
                    model_name="claude-opus-4-6",
                    total_input_tokens=1200,
                    total_output_tokens=300,
                    total_tokens=1500,
                    estimated_cost_usd=12.3456,
                    request_count=4,
                    cache_hit_rate=None,
                )
            ],
            total_tokens=1500,
            total_cost_usd=12.3456,
            overall_cache_hit_rate=25.0,
            period="month",
        )

        with patch(
            "api.routes.admin_analytics.get_model_usage_summary",
            new=AsyncMock(return_value=summary),
        ) as get_models_mock:
            resp = await c.get("/api/v1/admin/analytics/models")

        assert resp.status_code == 200
        assert resp.json() == {
            "models": [
                {
                    "model_name": "claude-opus-4-6",
                    "total_input_tokens": 1200,
                    "total_output_tokens": 300,
                    "total_tokens": 1500,
                    "estimated_cost_usd": 12.3456,
                    "request_count": 4,
                    "cache_hit_rate": None,
                }
            ],
            "total_tokens": 1500,
            "total_cost_usd": 12.3456,
            "overall_cache_hit_rate": 25.0,
            "period": "month",
        }
        assert get_models_mock.await_count == 1
        assert get_models_mock.await_args is not None
        assert get_models_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_models_platform_superadmin_can_view_global_usage(self, admin_client):
        c, _db = admin_client
        summary = ModelUsageSummary(
            models=[],
            total_tokens=0,
            total_cost_usd=0.0,
            overall_cache_hit_rate=None,
            period="month",
        )

        with (
            patch("api.routes.admin_analytics._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin_analytics.get_model_usage_summary",
                new=AsyncMock(return_value=summary),
            ) as get_models_mock,
        ):
            resp = await c.get("/api/v1/admin/analytics/models")

        assert resp.status_code == 200
        assert get_models_mock.await_args is not None
        assert get_models_mock.await_args.kwargs["org_id"] is None


class TestAdminAnalyticsAuditLogRoute:
    @pytest.mark.asyncio
    async def test_audit_log_returns_paginated_payload(self, admin_client):
        c, _db = admin_client
        entry = AuditLogEntryExtended(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            action="analysis.created",
            user_id=uuid.uuid4(),
            user_email="attorney@praviar.io",
            analysis_id=uuid.uuid4(),
            details={"compound": "aspirin"},
            ip_address="127.0.0.1",
            created_at=datetime(2026, 4, 11, tzinfo=UTC),
        )
        page = AuditLogPage(items=[entry], total=1, page=1, per_page=50, has_next=False)

        with patch(
            "api.routes.admin_analytics.get_audit_log_page",
            new=AsyncMock(return_value=page),
        ) as get_page_mock:
            resp = await c.get("/api/v1/admin/analytics/audit-log")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["action"] == "analysis.created"
        assert get_page_mock.await_count == 1
        assert get_page_mock.await_args is not None
        assert get_page_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_audit_log_platform_superadmin_can_view_global_log(self, admin_client):
        c, _db = admin_client
        page = AuditLogPage(items=[], total=0, page=1, per_page=50, has_next=False)

        with (
            patch("api.routes.admin_analytics._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin_analytics.get_audit_log_page",
                new=AsyncMock(return_value=page),
            ) as get_page_mock,
        ):
            resp = await c.get("/api/v1/admin/analytics/audit-log")

        assert resp.status_code == 200
        assert get_page_mock.await_args is not None
        assert get_page_mock.await_args.kwargs["org_id"] is None

    @pytest.mark.asyncio
    async def test_audit_log_csv_uses_renderer(self, admin_client):
        c, _db = admin_client
        page = AuditLogPage(items=[], total=0, page=1, per_page=50, has_next=False)

        with (
            patch(
                "api.routes.admin_analytics.get_audit_log_page",
                new=AsyncMock(return_value=page),
            ) as get_page_mock,
            patch(
                "api.routes.admin_analytics.render_audit_log_csv",
                return_value="id,action\n",
            ) as render_csv,
        ):
            resp = await c.get(
                "/api/v1/admin/analytics/audit-log",
                headers={"Accept": "text/csv"},
            )

        assert resp.status_code == 200
        assert resp.text == "id,action\n"
        assert resp.headers["content-disposition"] == "attachment; filename=audit-log.csv"
        assert get_page_mock.await_count == 1
        render_csv.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_audit_log_rejects_invalid_date_filter(self, admin_client):
        c, _db = admin_client

        resp = await c.get("/api/v1/admin/analytics/audit-log?start_date=not-a-date")

        assert resp.status_code == 422
        assert "date filter must be an ISO-8601" in resp.json()["detail"]
