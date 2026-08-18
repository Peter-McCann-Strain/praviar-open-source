"""Tests for audit logging helper behavior."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.audit import write_audit_log


@pytest.mark.asyncio
async def test_write_audit_log_can_fail_closed() -> None:
    db = AsyncMock()
    db.add = MagicMock(side_effect=RuntimeError("audit insert failed"))

    with pytest.raises(RuntimeError, match="audit insert failed"):
        await write_audit_log(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            action="apikey.created",
            fail_closed=True,
        )


@pytest.mark.asyncio
async def test_write_audit_log_failure_does_not_log_raw_database_exception() -> None:
    db = AsyncMock()
    db.add = MagicMock(
        side_effect=RuntimeError(
            "postgresql://private-host/audit params recipient=counsel@example.com"
        )
    )

    with patch("api.audit.logger") as audit_logger:
        await write_audit_log(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            action="report.share.grant_created",
        )

    audit_logger.error.assert_called_once()
    _, kwargs = audit_logger.error.call_args
    assert kwargs["error_type"] == "RuntimeError"
    assert "error" not in kwargs
    assert "exc_info" not in kwargs


@pytest.mark.asyncio
async def test_write_audit_log_ignores_spoofed_forwarded_for() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    request = MagicMock()
    request.client.host = "198.51.100.10"
    request.headers = {"X-Forwarded-For": "203.0.113.20"}

    await write_audit_log(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        action="apikey.created",
        request=request,
    )

    audit_log = db.add.call_args.args[0]
    assert audit_log.ip_address == "198.51.100.10"


@pytest.mark.asyncio
async def test_write_audit_log_attributes_api_key_actor_without_secret() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    api_key_id = uuid.uuid4()
    request = MagicMock()
    request.client = None
    request.state = SimpleNamespace(
        auth_actor_type="api_key",
        auth_api_key_id=str(api_key_id),
    )

    await write_audit_log(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        action="analysis.created",
        details={"source": "api"},
        request=request,
        fail_closed=True,
    )

    audit_log = db.add.call_args.args[0]
    assert audit_log.details == {
        "source": "api",
        "actor_type": "api_key",
        "api_key_id": str(api_key_id),
    }
    assert "secret" not in str(audit_log.details).lower()
