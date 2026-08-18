"""Tests for /api/v1/configs endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from conftest import make_preset_mock

from api.db.models import ConfigPreset

# ---------------------------------------------------------------------------
# GET /api/v1/configs/presets
# ---------------------------------------------------------------------------


class TestListPresets:
    @pytest.mark.asyncio
    async def test_list_presets(self, scientist_client):
        c, db = scientist_client
        presets = [make_preset_mock(name="Standard"), make_preset_mock(name="Deep")]
        db.execute.return_value.scalars.return_value.all.return_value = presets

        resp = await c.get("/api/v1/configs/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Standard"
        assert data[1]["name"] == "Deep"

    @pytest.mark.asyncio
    async def test_list_presets_empty(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalars.return_value.all.return_value = []

        resp = await c.get("/api/v1/configs/presets")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_presets_includes_config(self, scientist_client):
        c, db = scientist_client
        preset = make_preset_mock(
            config={"max_analysis_patents": 30, "search_jurisdictions": ["EP"]},
            is_default=True,
        )
        db.execute.return_value.scalars.return_value.all.return_value = [preset]

        resp = await c.get("/api/v1/configs/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["config"]["max_analysis_patents"] == 30
        assert data[0]["is_default"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/configs/defaults
# ---------------------------------------------------------------------------


class TestGetOrgDefaults:
    @pytest.mark.asyncio
    async def test_get_defaults_returns_org_config(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = {
            "default_config": {
                "max_analysis_patents": 25,
                "search_jurisdictions": ["US", "EP"],
                "pipeline_mode": "retired",
            }
        }

        resp = await c.get("/api/v1/configs/defaults")

        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["max_analysis_patents"] == 25
        assert data["config"]["search_jurisdictions"] == ["US", "EP"]
        assert "pipeline_mode" not in data["config"]
        assert data["can_manage"] is False

    @pytest.mark.asyncio
    async def test_get_defaults_exposes_authoritative_attorney_capability(self, attorney_client):
        c, db = attorney_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get("/api/v1/configs/defaults")

        assert resp.status_code == 200
        assert resp.json()["can_manage"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/configs/presets
# ---------------------------------------------------------------------------


class TestCreatePreset:
    @pytest.mark.asyncio
    async def test_create_as_attorney(self, attorney_client):
        c, db = attorney_client
        resp = await c.post(
            "/api/v1/configs/presets",
            json={
                "name": "Quick Scan",
                "description": "Fast shallow analysis",
                "config": {"max_analysis_patents": 5},
                "is_default": False,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Quick Scan"
        assert "id" in data
        assert any(isinstance(call.args[0], ConfigPreset) for call in db.add.call_args_list)
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_default_preset_unsets_existing_default(self, attorney_client):
        c, db = attorney_client
        existing = make_preset_mock(is_default=True)
        existing_defaults = MagicMock()
        existing_defaults.scalars.return_value.all.return_value = [existing]
        db.execute.return_value = existing_defaults

        resp = await c.post(
            "/api/v1/configs/presets",
            json={
                "name": "Default Deep",
                "config": {"max_analysis_patents": 20},
                "is_default": True,
            },
        )

        assert resp.status_code == 201
        assert existing.is_default is False

    @pytest.mark.asyncio
    async def test_create_as_admin(self, admin_client):
        c, db = admin_client
        resp = await c.post(
            "/api/v1/configs/presets",
            json={
                "name": "Enterprise",
                "config": {"max_analysis_patents": 30},
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_forbidden_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.post(
            "/api/v1/configs/presets",
            json={
                "name": "My Preset",
                "config": {},
            },
        )
        assert resp.status_code == 403
        assert "config.manage" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.post(
            "/api/v1/configs/presets",
            json={"name": "X", "config": {}},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_default_concurrent_conflict_returns_409(self):
        """A partial-unique violation on the one-default-per-org index maps to 409.

        Two simultaneous is_default=True creates each clear the visible defaults
        and then both insert, so the second commit violates
        uq_config_presets_org_one_default. The service must surface a retryable
        409 rather than letting the IntegrityError become an opaque 500.
        """
        import uuid as _uuid
        from unittest.mock import AsyncMock, MagicMock

        from sqlalchemy.exc import IntegrityError

        from api.db.models import UserRole
        from api.errors import APIError
        from api.schemas.configs import CreatePresetRequest
        from api.services.configs import create_preset

        empty_defaults = MagicMock()
        empty_defaults.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_defaults)
        db.add = MagicMock()
        db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("uq violation")))

        body = CreatePresetRequest(
            name="Default Deep",
            description="",
            config={"max_analysis_patents": 20},
            is_default=True,
        )
        with pytest.raises(APIError) as exc:
            await create_preset(
                db,
                org_id=_uuid.uuid4(),
                user_id=_uuid.uuid4(),
                user_role=UserRole.ATTORNEY,
                body=body,
            )
        assert exc.value.status == 409
        db.rollback.assert_awaited()


# ---------------------------------------------------------------------------
# PUT /api/v1/configs/defaults
# ---------------------------------------------------------------------------


class TestSetOrgDefaults:
    @pytest.mark.asyncio
    async def test_set_defaults_as_attorney(self, attorney_client):
        c, db = attorney_client
        org = MagicMock()
        org.settings = {}
        db.execute.return_value.scalar_one_or_none.return_value = org

        resp = await c.put(
            "/api/v1/configs/defaults",
            json={
                "max_analysis_patents": 25,
                "search_jurisdictions": ["US", "EP"],
                "citation_traversal_enabled": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        assert "default_config" in org.settings
        assert org.settings["default_config"]["max_analysis_patents"] == 25
        assert org.settings["default_config"]["search_jurisdictions"] == ["US", "EP"]

    @pytest.mark.asyncio
    async def test_set_defaults_as_admin(self, admin_client):
        c, db = admin_client
        org = MagicMock()
        org.settings = {"existing_key": "value"}
        db.execute.return_value.scalar_one_or_none.return_value = org

        resp = await c.put(
            "/api/v1/configs/defaults",
            json={"search_jurisdictions": ["EP"]},
        )
        assert resp.status_code == 200
        # Existing settings preserved
        assert org.settings["existing_key"] == "value"
        assert "default_config" in org.settings

    @pytest.mark.asyncio
    async def test_set_defaults_forbidden_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.put(
            "/api/v1/configs/defaults",
            json={"search_jurisdictions": ["US"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_set_defaults_org_not_found(self, attorney_client):
        c, db = attorney_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.put(
            "/api/v1/configs/defaults",
            json={"search_jurisdictions": ["US"]},
        )
        assert resp.status_code == 404
        assert "Organization not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_defaults_rejects_unknown_keys(self, attorney_client):
        c, db = attorney_client
        org = MagicMock()
        org.settings = {}
        db.execute.return_value.scalar_one_or_none.return_value = org

        resp = await c.put(
            "/api/v1/configs/defaults",
            json={"jurisdiction": "US"},
        )
        assert resp.status_code == 422
