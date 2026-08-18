"""Tests for /api/v1/api-keys endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_api_key_mock(**kw) -> MagicMock:
    """Create a mock APIKey ORM object."""
    k = MagicMock()
    k.id = kw.get("id", uuid.uuid4())
    k.org_id = kw.get("org_id", uuid.uuid4())
    k.user_id = kw.get("user_id", uuid.uuid4())
    k.name = kw.get("name", "Test Key")
    k.key_hash = kw.get("key_hash", "abc123hash")
    k.key_prefix = kw.get("key_prefix", "sk_test1...")
    k.scopes = kw.get("scopes", ["analyses:read", "reports:read"])
    k.expires_at = kw.get("expires_at", datetime.now(UTC) + timedelta(days=90))
    k.last_used_at = kw.get("last_used_at")
    k.revoked = kw.get("revoked", False)
    k.created_at = kw.get("created_at", datetime.now(UTC))
    return k


def make_create_payload(**kw) -> dict:
    return {
        "name": kw.get("name", "Production Key"),
        "scopes": kw.get("scopes", ["analyses:read", "reports:read"]),
        "expires_at": kw.get(
            "expires_at",
            (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        ),
    }


# ---------------------------------------------------------------------------
# POST /api/v1/api-keys — create
# ---------------------------------------------------------------------------


class TestCreateAPIKey:
    """POST /api/v1/api-keys"""

    @pytest.mark.asyncio
    async def test_create_api_key(self, admin_client):
        c, db = admin_client
        db.refresh = AsyncMock()

        resp = await c.post(
            "/api/v1/api-keys",
            json=make_create_payload(name="Production Key"),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Production Key"
        assert "key_prefix" in data
        assert data["scopes"] == ["analyses:read", "reports:read"]
        assert "expires_at" in data
        assert "created_at" in data
        assert db.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_api_key_returns_secret_once(self, admin_client):
        """The secret_key field should be present in the creation response."""
        c, db = admin_client
        db.refresh = AsyncMock()

        resp = await c.post(
            "/api/v1/api-keys",
            json=make_create_payload(name="Secret Key"),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert "secret_key" in data
        # The secret key should be a non-empty string
        assert len(data["secret_key"]) > 0

    @pytest.mark.asyncio
    async def test_create_api_key_missing_name(self, admin_client):
        c, _db = admin_client

        resp = await c.post("/api/v1/api-keys", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_api_key_empty_name(self, admin_client):
        c, _db = admin_client

        resp = await c.post("/api/v1/api-keys", json=make_create_payload(name=""))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_api_key_requires_scope_and_future_expiry(self, admin_client):
        c, _db = admin_client

        no_scope = make_create_payload(scopes=[])
        resp = await c.post("/api/v1/api-keys", json=no_scope)
        assert resp.status_code == 422

        expired = make_create_payload(
            expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
        )
        resp = await c.post("/api/v1/api-keys", json=expired)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_api_key_rejects_export_scope_when_attorney_gate_is_enabled(
        self,
        admin_client,
    ):
        c, db = admin_client

        resp = await c.post(
            "/api/v1/api-keys",
            json=make_create_payload(scopes=["reports:export"]),
        )

        assert resp.status_code == 422
        assert "scope is unavailable" in resp.json()["detail"]
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/v1/api-keys — list
# ---------------------------------------------------------------------------


class TestListAPIKeys:
    """GET /api/v1/api-keys"""

    @pytest.mark.asyncio
    async def test_list_api_keys(self, admin_client):
        c, db = admin_client
        keys = [make_api_key_mock(), make_api_key_mock()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = keys

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_api_keys_no_secrets(self, admin_client):
        """List endpoint should NOT include secret_key in any item."""
        c, db = admin_client
        keys = [make_api_key_mock()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = keys

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert "secret_key" not in item
            assert item["scopes"] == ["analyses:read", "reports:read"]
            assert item["expires_at"]

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, admin_client):
        c, db = admin_client

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# DELETE /api/v1/api-keys/{id} — revoke
# ---------------------------------------------------------------------------


class TestRevokeAPIKey:
    """DELETE /api/v1/api-keys/{id}"""

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, admin_client):
        c, db = admin_client
        key_id = uuid.uuid4()
        api_key = make_api_key_mock(id=key_id)
        db.execute.return_value.scalar_one_or_none.return_value = api_key

        resp = await c.delete(f"/api/v1/api-keys/{key_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "revoked"
        assert api_key.revoked is True
        db.flush.assert_awaited()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self, admin_client):
        c, db = admin_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/api-keys/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "API key not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Role restrictions — admin only
# ---------------------------------------------------------------------------


class TestAPIKeyAdminOnly:
    """API key management should be restricted to admin users."""

    @pytest.mark.asyncio
    async def test_apikey_admin_only_create(self, scientist_client):
        """Non-admin (scientist) gets 403 on create."""
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/api-keys",
            json=make_create_payload(name="Forbidden Key"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_apikey_admin_only_list(self, scientist_client):
        """Non-admin (scientist) gets 403 on list."""
        c, _db = scientist_client

        resp = await c.get("/api/v1/api-keys")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_apikey_admin_only_revoke(self, scientist_client):
        """Non-admin (scientist) gets 403 on revoke."""
        c, _db = scientist_client

        resp = await c.delete(f"/api/v1/api-keys/{uuid.uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_apikey_attorney_forbidden(self, attorney_client):
        """Attorney role should also be forbidden."""
        c, _db = attorney_client

        resp = await c.post(
            "/api/v1/api-keys",
            json=make_create_payload(name="Attorney Key"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_apikey_client_forbidden(self, client_role_client):
        """Client role should be forbidden."""
        c, _db = client_role_client

        resp = await c.get("/api/v1/api-keys")
        assert resp.status_code == 403
