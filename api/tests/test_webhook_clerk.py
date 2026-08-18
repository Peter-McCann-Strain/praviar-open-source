"""Tests for the Clerk webhook handler (api/src/api/routes/webhooks.py).

Calls the handler coroutine directly — no HTTP layer — so pytest-cov tracks
the route code in the same thread without needing thread-coverage workarounds.
"""

from __future__ import annotations

import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError


def _make_request(
    body: bytes = b"{}",
    svix_id: str = "msg_test",
    svix_ts: str = "1234567890",
    svix_sig: str = "v1,abc",
) -> MagicMock:
    req = MagicMock()
    req.body = AsyncMock(return_value=body)
    req.headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_ts,
        "svix-signature": svix_sig,
    }
    return req


def _make_svix_mod(payload=None, raise_exc=None):
    wh = MagicMock()
    if raise_exc is not None:
        wh.verify.side_effect = raise_exc
    else:
        wh.verify.return_value = payload or {}
    mod = MagicMock()
    mod.Webhook = MagicMock(return_value=wh)
    return mod


# ── Import the handler once ───────────────────────────────────────────────────


def _handler():
    from api.routes.webhooks import clerk_webhook

    return clerk_webhook


@pytest.mark.asyncio
async def test_receipt_duplicate_requires_same_payload_hash_and_type():
    from api.routes.webhooks import _claim_clerk_webhook_receipt

    existing = MagicMock(
        event_type="organizationMembership.updated",
        payload_sha256="a" * 64,
    )
    lookup = MagicMock()
    lookup.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError(None, None, RuntimeError("duplicate")))
    db.execute = AsyncMock(return_value=lookup)

    claimed = await _claim_clerk_webhook_receipt(
        db,
        svix_id="msg_same",
        event_type="organizationMembership.updated",
        payload_sha256="a" * 64,
    )

    assert claimed is False
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_receipt_rejects_same_svix_id_with_different_payload_hash():
    from api.errors import APIError
    from api.routes.webhooks import _claim_clerk_webhook_receipt

    existing = MagicMock(
        event_type="organizationMembership.updated",
        payload_sha256="a" * 64,
    )
    lookup = MagicMock()
    lookup.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError(None, None, RuntimeError("duplicate")))
    db.execute = AsyncMock(return_value=lookup)

    with pytest.raises(APIError) as exc_info:
        await _claim_clerk_webhook_receipt(
            db,
            svix_id="msg_collision",
            event_type="organizationMembership.updated",
            payload_sha256="b" * 64,
        )

    assert exc_info.value.status == 409


# ── Missing secret ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_secret_raises_500():
    from api.errors import APIError

    with patch("api.routes.webhooks.get_settings") as ms:
        ms.return_value.clerk_webhook_secret = ""
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request())
    assert exc_info.value.status == 500


@pytest.mark.asyncio
async def test_none_secret_raises_500():
    from api.errors import APIError

    with patch("api.routes.webhooks.get_settings") as ms:
        ms.return_value.clerk_webhook_secret = None
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request())
    assert exc_info.value.status == 500


# ── Missing svix headers ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_svix_id_raises_401():
    from api.errors import APIError

    with patch("api.routes.webhooks.get_settings") as ms:
        ms.return_value.clerk_webhook_secret = "whsec_test"
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request(svix_id=""))
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_missing_svix_timestamp_raises_401():
    from api.errors import APIError

    with patch("api.routes.webhooks.get_settings") as ms:
        ms.return_value.clerk_webhook_secret = "whsec_test"
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request(svix_ts=""))
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_missing_svix_signature_raises_401():
    from api.errors import APIError

    with patch("api.routes.webhooks.get_settings") as ms:
        ms.return_value.clerk_webhook_secret = "whsec_test"
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request(svix_sig=""))
    assert exc_info.value.status == 401


# ── Verification failure ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_signature_raises_401():
    from api.errors import APIError

    mock_svix = _make_svix_mod(raise_exc=ValueError("bad sig"))
    with (
        patch("api.routes.webhooks.get_settings") as ms,
        patch.dict("sys.modules", {"svix.webhooks": mock_svix}),
    ):
        ms.return_value.clerk_webhook_secret = "whsec_test"
        with pytest.raises(APIError) as exc_info:
            await _handler()(_make_request())
    assert exc_info.value.status == 401


# ── Event routing ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_created_event():
    payload = {"type": "user.created", "data": {"id": "usr_1"}}
    mock_svix = _make_svix_mod(payload=payload)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.webhooks.get_settings") as ms,
        patch.dict("sys.modules", {"svix.webhooks": mock_svix}),
        patch("api.routes.webhooks.async_session_factory", return_value=mock_db),
        patch(
            "api.routes.webhooks._handle_user_created",
            new=AsyncMock(return_value={"status": "ok"}),
        ),
    ):
        ms.return_value.clerk_webhook_secret = "whsec_test"
        result = await _handler()(_make_request(body=json.dumps(payload).encode()))
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_org_created_event():
    payload = {"type": "organization.created", "data": {"id": "org_1"}}
    mock_svix = _make_svix_mod(payload=payload)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.webhooks.get_settings") as ms,
        patch.dict("sys.modules", {"svix.webhooks": mock_svix}),
        patch("api.routes.webhooks.async_session_factory", return_value=mock_db),
        patch(
            "api.routes.webhooks._handle_org_created",
            new=AsyncMock(return_value={"status": "ok"}),
        ),
    ):
        ms.return_value.clerk_webhook_secret = "whsec_test"
        result = await _handler()(_make_request(body=json.dumps(payload).encode()))
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_exact_membership_event_is_receipted_and_routed_with_event_type():
    payload = {
        "type": "organizationMembership.updated",
        "data": {
            "id": "mem_1",
            "organization": {"id": "org_1", "name": "Example"},
            "public_user_data": {
                "user_id": "user_1",
                "identifier": "chemist@praviar.io",
            },
            "role": "org:member",
            "updated_at": 1_789_000_000_000,
        },
    }
    mock_svix = _make_svix_mod(payload=payload)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    handler = AsyncMock(return_value={"status": "updated"})

    with (
        patch("api.routes.webhooks.get_settings") as ms,
        patch.dict("sys.modules", {"svix.webhooks": mock_svix}),
        patch("api.routes.webhooks.async_session_factory", return_value=mock_db),
        patch("api.routes.webhooks._handle_membership_event", new=handler),
    ):
        ms.return_value.clerk_webhook_secret = "whsec_test"
        result = await _handler()(_make_request(body=json.dumps(payload).encode()))

    assert result == {"status": "updated"}
    handler.assert_awaited_once_with(
        mock_db,
        payload["data"],
        event_type="organizationMembership.updated",
        event_id="msg_test",
        source="clerk_webhook",
        write_audit_log_fn=ANY,
    )
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_membership_audit_failure_rolls_back_receipt_and_authority_mutation():
    payload = {
        "type": "organizationMembership.deleted",
        "data": {
            "id": "mem_1",
            "organization": {"id": "org_1", "name": "Example"},
            "role": "org:member",
            "updated_at": 1_789_000_000_000,
        },
    }
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    handler = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    with (
        patch("api.routes.webhooks.get_settings") as settings,
        patch.dict("sys.modules", {"svix.webhooks": _make_svix_mod(payload=payload)}),
        patch("api.routes.webhooks.async_session_factory", return_value=mock_db),
        patch("api.routes.webhooks._handle_membership_event", new=handler),
    ):
        settings.return_value.clerk_webhook_secret = "whsec_test"
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await _handler()(_make_request(body=json.dumps(payload).encode()))

    mock_db.commit.assert_not_awaited()
    mock_db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_unhandled_event_returns_ok():
    payload = {"type": "user.deleted", "data": {}}
    mock_svix = _make_svix_mod(payload=payload)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.webhooks.get_settings") as ms,
        patch.dict("sys.modules", {"svix.webhooks": mock_svix}),
        patch("api.routes.webhooks.async_session_factory", return_value=mock_db),
    ):
        ms.return_value.clerk_webhook_secret = "whsec_test"
        result = await _handler()(_make_request(body=json.dumps(payload).encode()))
    assert result["status"] == "ok"
