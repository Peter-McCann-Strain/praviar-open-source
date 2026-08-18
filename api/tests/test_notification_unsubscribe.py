from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing
from api.ratelimit import digest_unsubscribe_rate_limit_key
from api.services.notification_unsubscribe import (
    InvalidUnsubscribeTokenError,
    create_digest_unsubscribe_capability,
    digest_unsubscribe_token,
    unsubscribe_token_locator,
)
from api.services.notifications import unsubscribe_weekly_digest


def _test_keyring() -> ExternalReportDeliveryKeyRing:
    return ExternalReportDeliveryKeyRing(
        active_key_id="test-v1",
        encryption_keys={"test-v1": b"e" * 32},
        operation_hmac_key=b"h" * 32,
    )


def test_digest_unsubscribe_capability_is_opaque_and_db_bound():
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    with patch(
        "api.services.notification_unsubscribe._token_keyring",
        return_value=_test_keyring(),
    ):
        capability = create_digest_unsubscribe_capability(now=now)

    assert capability.token.startswith("du1.")
    assert len(capability.token) >= 80
    assert len(capability.token_digest) == 64
    assert capability.expires_at == now + timedelta(days=90)
    assert "@" not in capability.token
    assert str(uuid.uuid4()) not in capability.token


def test_digest_unsubscribe_capability_rejects_tamper_and_noncanonical_shape():
    with patch(
        "api.services.notification_unsubscribe._token_keyring",
        return_value=_test_keyring(),
    ):
        capability = create_digest_unsubscribe_capability()
        assert digest_unsubscribe_token(capability.token) == capability.token_digest
        assert len(unsubscribe_token_locator(capability.token)) == 64
        with pytest.raises(InvalidUnsubscribeTokenError):
            digest_unsubscribe_token(f"{capability.token[:-1]}!")
        with pytest.raises(InvalidUnsubscribeTokenError):
            digest_unsubscribe_token("du1.short")


def test_unsubscribe_throttle_is_token_wide_and_never_uses_raw_capability():
    locator = "a" * 64

    def _request(client: tuple[str, int]) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/notifications/unsubscribe/digest/{locator}",
                "path_params": {"token_locator": locator},
                "headers": [],
                "client": client,
                "server": ("api.praviar.io", 443),
                "scheme": "https",
                "query_string": b"",
            }
        )

    first = digest_unsubscribe_rate_limit_key(_request(("192.0.2.1", 1234)))
    second = digest_unsubscribe_rate_limit_key(_request(("198.51.100.2", 4321)))

    assert first == second == f"weekly-digest-unsubscribe:{locator}"
    assert "du1." not in first


@pytest.mark.asyncio
async def test_one_click_unsubscribe_preserves_other_preferences_and_audits():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    delivery = MagicMock(
        id=uuid.uuid4(),
        user_id=user_id,
        org_id=org_id,
        unsubscribe_expires_at=now + timedelta(days=1),
        unsubscribe_used_at=None,
    )
    user = MagicMock(
        id=user_id,
        org_id=org_id,
        preferences={
            "email_on_analysis_complete": True,
            "email_on_monitor_alert": False,
            "email_digest_frequency": "weekly",
            "last_weekly_digest_reserved_at": "legacy-marker",
            "theme": "light",
        },
    )
    capability_result = MagicMock()
    capability_result.one_or_none.return_value = delivery
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    delivery_result = MagicMock()
    delivery_result.scalar_one_or_none.return_value = delivery
    db = AsyncMock()
    db.execute.side_effect = [
        MagicMock(),
        capability_result,
        MagicMock(),
        user_result,
        delivery_result,
    ]

    with (
        patch(
            "api.services.notifications.unsubscribe_token_locator",
            return_value="a" * 64,
        ),
        patch(
            "api.services.notifications.digest_unsubscribe_token",
            return_value="b" * 64,
        ),
        patch(
            "api.services.notifications.write_audit_log",
            new=AsyncMock(),
        ) as write_audit,
    ):
        result = await unsubscribe_weekly_digest(
            db,
            token="opaque-token",
            token_locator="a" * 64,
            request=MagicMock(),
        )

    assert result == {"status": "unsubscribed"}
    assert user.preferences["email_digest_frequency"] == "off"
    assert user.preferences["email_on_analysis_complete"] is True
    assert user.preferences["email_on_monitor_alert"] is False
    assert user.preferences["theme"] == "light"
    assert "last_weekly_digest_reserved_at" not in user.preferences
    assert "digest_unsubscribed_at" in user.preferences
    assert delivery.unsubscribe_used_at is not None
    first_params = db.execute.await_args_list[0].args[0].compile().params
    assert "app.digest_unsubscribe_token_digest" in first_params.values()
    assert "weekly_digest_deliveries.unsubscribe_token_digest" in str(
        db.execute.await_args_list[1].args[0]
    )
    org_params = db.execute.await_args_list[2].args[0].compile().params
    assert "app.current_org_id" in org_params.values()
    write_audit.assert_awaited_once()
    assert write_audit.await_args.kwargs["details"]["source"] == "one_click"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_click_unsubscribe_is_idempotent_and_consumes_valid_capability():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    delivery = MagicMock(
        id=uuid.uuid4(),
        user_id=user_id,
        org_id=org_id,
        unsubscribe_expires_at=datetime.now(UTC) + timedelta(days=1),
        unsubscribe_used_at=None,
    )
    user = MagicMock(
        id=user_id,
        org_id=org_id,
        preferences={"email_digest_frequency": "off"},
    )
    capability_result = MagicMock()
    capability_result.one_or_none.return_value = delivery
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    delivery_result = MagicMock()
    delivery_result.scalar_one_or_none.return_value = delivery
    db = AsyncMock()
    db.execute.side_effect = [
        MagicMock(),
        capability_result,
        MagicMock(),
        user_result,
        delivery_result,
    ]

    with (
        patch("api.services.notifications.unsubscribe_token_locator", return_value="a" * 64),
        patch("api.services.notifications.digest_unsubscribe_token", return_value="b" * 64),
        patch(
            "api.services.notifications.write_audit_log",
            new=AsyncMock(),
        ) as write_audit,
    ):
        result = await unsubscribe_weekly_digest(
            db,
            token="opaque-token",
            token_locator="a" * 64,
            request=MagicMock(),
        )

    assert result == {"status": "unsubscribed"}
    assert delivery.unsubscribe_used_at is not None
    write_audit.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumed_unsubscribe_capability_cannot_disable_later_resubscription():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    consumed_at = datetime.now(UTC) - timedelta(minutes=5)
    capability = MagicMock(
        id=uuid.uuid4(),
        user_id=user_id,
        org_id=org_id,
        unsubscribe_expires_at=datetime.now(UTC) + timedelta(days=1),
        unsubscribe_used_at=consumed_at,
    )
    capability_result = MagicMock()
    capability_result.one_or_none.return_value = capability
    db = AsyncMock()
    db.execute.side_effect = [MagicMock(), capability_result]

    with (
        patch("api.services.notifications.unsubscribe_token_locator", return_value="a" * 64),
        patch("api.services.notifications.digest_unsubscribe_token", return_value="b" * 64),
        patch(
            "api.services.notifications.write_audit_log",
            new=AsyncMock(),
        ) as write_audit,
    ):
        result = await unsubscribe_weekly_digest(
            db,
            token="opaque-token",
            token_locator="a" * 64,
            request=MagicMock(),
        )

    assert result == {"status": "unsubscribed"}
    assert db.execute.await_count == 2
    db.commit.assert_not_awaited()
    write_audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["invalid", "locator_mismatch", "missing", "expired"])
async def test_unsubscribe_failures_are_response_indistinguishable(case: str):
    db = AsyncMock()
    token_locator = "a" * 64
    patches = [
        patch("api.services.notifications.unsubscribe_token_locator", return_value=token_locator),
        patch("api.services.notifications.digest_unsubscribe_token", return_value="b" * 64),
    ]
    if case == "invalid":
        patches[0] = patch(
            "api.services.notifications.unsubscribe_token_locator",
            side_effect=InvalidUnsubscribeTokenError("bad"),
        )
    elif case == "locator_mismatch":
        token_locator = "c" * 64
    else:
        capability_result = MagicMock()
        if case == "missing":
            capability_result.one_or_none.return_value = None
        else:
            capability_result.one_or_none.return_value = MagicMock(
                unsubscribe_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                unsubscribe_used_at=None,
            )
        db.execute.side_effect = [MagicMock(), capability_result]

    with patches[0], patches[1]:
        result = await unsubscribe_weekly_digest(
            db,
            token="opaque-token",
            token_locator=token_locator,
            request=MagicMock(),
        )

    assert result == {"status": "unsubscribed"}
    db.commit.assert_not_awaited()
