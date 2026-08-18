"""Service-layer tests for configuration preset/default management."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db, make_preset_mock

from api.db.models import UserRole
from api.errors import APIError
from api.schemas.analyses import AnalysisConfigSchema
from api.schemas.configs import CreatePresetRequest, SetOrgDefaultsRequest
from api.services.configs import create_preset, set_org_default_config


@pytest.mark.asyncio
async def test_create_preset_unsets_existing_default():
    db = make_mock_db()
    existing_default = make_preset_mock(is_default=True)
    default_query = MagicMock()
    default_query.scalars.return_value.all.return_value = [existing_default]
    db.execute.return_value = default_query

    body = CreatePresetRequest(
        name="Deep",
        description="Deep review",
        config=AnalysisConfigSchema(max_analysis_patents=20),
        is_default=True,
    )

    created = await create_preset(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_role=UserRole.ATTORNEY,
        body=body,
    )

    assert existing_default.is_default is False
    assert created.is_default is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_preset_rolls_back_when_audit_fails():
    db = make_mock_db()
    body = CreatePresetRequest(
        name="Deep",
        description="Deep review",
        config=AnalysisConfigSchema(max_analysis_patents=20),
        is_default=False,
    )

    with (
        patch(
            "api.services.configs.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await create_preset(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_role=UserRole.ATTORNEY,
            body=body,
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_preset_rejects_scientist():
    db = make_mock_db()
    body = CreatePresetRequest(
        name="Deep",
        description="Deep review",
        config=AnalysisConfigSchema(max_analysis_patents=20),
        is_default=False,
    )

    with pytest.raises(APIError) as exc:
        await create_preset(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_role=UserRole.SCIENTIST,
            body=body,
        )

    assert exc.value.status == 403
    assert "attorney or organization administrator" in exc.value.detail
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_org_default_config_merges_existing_settings():
    db = make_mock_db()
    org = MagicMock()
    org.settings = {"existing_key": "value"}
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db.execute.return_value = result

    body = SetOrgDefaultsRequest(search_jurisdictions=["US", "EP"], max_analysis_patents=15)
    await set_org_default_config(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_role=UserRole.ATTORNEY,
        body=body,
    )

    assert org.settings["existing_key"] == "value"
    assert org.settings["default_config"]["search_jurisdictions"] == ["US", "EP"]
    assert org.settings["default_config"]["max_analysis_patents"] == 15
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_org_default_config_stores_normalized_partial_config():
    db = make_mock_db()
    org = MagicMock()
    org.settings = {}
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db.execute.return_value = result

    body = SetOrgDefaultsRequest(
        hitl_enabled=True,
        hitl_checkpoints=["triage_review"],
        hitl_auto_skip_minutes=30,
    )
    await set_org_default_config(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_role=UserRole.ATTORNEY,
        body=body,
    )

    assert org.settings["default_config"] == {
        "hitl_enabled": True,
        "hitl_checkpoints": ["triage_review"],
        "hitl_auto_skip_minutes": 30,
    }


def test_set_org_default_config_rejects_legacy_mode_fields():
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        SetOrgDefaultsRequest(claim_analysis_depth="deep")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        SetOrgDefaultsRequest(claude_triage_model="claude-haiku")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_set_org_default_config_rolls_back_when_audit_fails():
    db = make_mock_db()
    org = MagicMock()
    org.settings = {"existing_key": "value"}
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db.execute.return_value = result

    body = SetOrgDefaultsRequest(search_jurisdictions=["US"], max_analysis_patents=15)
    with (
        patch(
            "api.services.configs.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await set_org_default_config(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_role=UserRole.ATTORNEY,
            body=body,
        )

    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_org_default_config_rejects_scientist():
    db = make_mock_db()
    body = SetOrgDefaultsRequest(search_jurisdictions=["US"])

    with pytest.raises(APIError) as exc:
        await set_org_default_config(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_role=UserRole.SCIENTIST,
            body=body,
        )

    assert exc.value.status == 403
    assert "attorney or organization administrator" in exc.value.detail
    db.commit.assert_not_awaited()
