"""Route-level tests for /api/v1/admin/sso/status and /api/v1/admin/sso/configure.

These tests verify:
- Admin-only access (403 for scientist role)
- Successful delegation to service layer
- Correct HTTP status codes and response shapes
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.sso import SSOConfigureResponse, SSOStatusResponse

# ---------------------------------------------------------------------------
# GET /api/v1/admin/sso/status
# ---------------------------------------------------------------------------


class TestSSOStatusRoute:
    """GET /api/v1/admin/sso/status"""

    @pytest.mark.asyncio
    async def test_get_sso_status_returns_200_for_admin(self, admin_client):
        c, _db = admin_client
        status_payload = SSOStatusResponse(
            sso_enabled=True,
            provider="Okta",
            domains=["pharma.com"],
            status="active",
            clerk_dashboard_url="https://dashboard.clerk.com/org/org_abc",
            sso_status_available=True,
            sso_last_synced_at=datetime(2026, 7, 14, tzinfo=UTC),
            sso_status_stale=False,
            sso_unavailable_reason=None,
        )

        with patch(
            "api.routes.sso.get_sso_status",
            new=AsyncMock(return_value=status_payload),
        ) as svc:
            resp = await c.get("/api/v1/admin/sso/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sso_enabled"] is True
        assert data["provider"] == "Okta"
        assert data["status"] == "active"
        assert data["sso_status_available"] is True
        assert data["sso_status_stale"] is False
        assert "pharma.com" in data["domains"]
        svc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_sso_status_returns_403_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.get("/api/v1/admin/sso/status")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_sso_status_inactive_when_no_connection(self, admin_client):
        c, _db = admin_client
        status_payload = SSOStatusResponse(
            sso_enabled=False,
            provider=None,
            domains=[],
            status="inactive",
            clerk_dashboard_url=None,
            sso_status_available=True,
            sso_last_synced_at=datetime(2026, 7, 14, tzinfo=UTC),
            sso_status_stale=False,
            sso_unavailable_reason=None,
        )

        with patch(
            "api.routes.sso.get_sso_status",
            new=AsyncMock(return_value=status_payload),
        ):
            resp = await c.get("/api/v1/admin/sso/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sso_enabled"] is False
        assert data["status"] == "inactive"
        assert data["provider"] is None
        assert data["domains"] == []


# ---------------------------------------------------------------------------
# POST /api/v1/admin/sso/configure
# ---------------------------------------------------------------------------


class TestSSOConfigureRoute:
    """POST /api/v1/admin/sso/configure"""

    @pytest.mark.asyncio
    async def test_configure_sso_enable_returns_200_for_admin(self, admin_client):
        c, _db = admin_client
        configure_payload = SSOConfigureResponse(
            status="instructions_provided",
            message="SSO enable requested. Follow the steps in your Clerk dashboard.",
            next_steps=[
                "Log in to the Clerk dashboard.",
                "Navigate to your organization's SSO settings.",
                "Upload your IdP metadata or configure OIDC credentials.",
            ],
            clerk_dashboard_url="https://dashboard.clerk.com/org/org_abc/sso",
        )

        with patch(
            "api.routes.sso.configure_sso",
            new=AsyncMock(return_value=configure_payload),
        ) as svc:
            resp = await c.post(
                "/api/v1/admin/sso/configure",
                json={"enable": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "instructions_provided"
        assert len(data["next_steps"]) > 0
        assert data["clerk_dashboard_url"] is not None
        svc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_configure_sso_disable_returns_200_for_admin(self, admin_client):
        c, _db = admin_client
        configure_payload = SSOConfigureResponse(
            status="instructions_provided",
            message="SSO disable requested. Follow the steps in your Clerk dashboard.",
            next_steps=["Log in to the Clerk dashboard.", "Remove the enterprise connection."],
            clerk_dashboard_url=None,
        )

        with patch(
            "api.routes.sso.configure_sso",
            new=AsyncMock(return_value=configure_payload),
        ) as svc:
            resp = await c.post(
                "/api/v1/admin/sso/configure",
                json={"enable": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "instructions_provided"
        svc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_configure_sso_returns_403_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.post("/api/v1/admin/sso/configure", json={"enable": True})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_configure_sso_requires_body(self, admin_client):
        c, _db = admin_client
        resp = await c.post("/api/v1/admin/sso/configure", json={})
        assert resp.status_code == 422
