"""Tests for notification routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.notifications import DigestFrequency
from api.services.notifications import NotificationActionResult, NotificationPage


class TestNotificationRoutes:
    @pytest.mark.asyncio
    async def test_digest_unsubscribe_delegates_without_identity_dependency(
        self,
        public_client,
    ):
        with patch(
            "api.routes.notifications.unsubscribe_weekly_digest",
            new=AsyncMock(return_value={"status": "unsubscribed"}),
        ) as unsubscribe:
            response = await public_client.post(
                f"/api/v1/notifications/unsubscribe/digest/{'a' * 64}",
                json={"token": "t" * 80},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "unsubscribed"}
        assert unsubscribe.await_args.kwargs["token"] == "t" * 80
        assert unsubscribe.await_args.kwargs["token_locator"] == "a" * 64

    @pytest.mark.asyncio
    async def test_list_notifications_delegates_to_service(self, scientist_client):
        client, _db = scientist_client
        item = SimpleNamespace(
            id=uuid.uuid4(),
            type="analysis_complete",
            title="Analysis complete",
            body="Done",
            read=False,
            data={},
            created_at=datetime(2026, 4, 11, tzinfo=UTC),
        )
        page = NotificationPage(items=[item], unread_count=1, total=1)  # type: ignore[arg-type]

        with patch(
            "api.routes.notifications.list_notifications_page",
            new=AsyncMock(return_value=page),
        ) as list_page:
            response = await client.get("/api/v1/notifications")

        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["unread_count"] == 1
        assert list_page.await_count == 1
        assert list_page.await_args.kwargs["user"].role.value == "scientist"

    @pytest.mark.asyncio
    async def test_unread_count_delegates_to_service(self, scientist_client):
        client, _db = scientist_client

        with patch(
            "api.routes.notifications.get_unread_notification_count",
            new=AsyncMock(return_value=3),
        ) as get_count:
            response = await client.get("/api/v1/notifications/unread-count")

        assert response.status_code == 200
        assert response.json() == {"unread_count": 3}
        assert get_count.await_count == 1

    @pytest.mark.asyncio
    async def test_mark_read_delegates_to_service(self, scientist_client):
        client, _db = scientist_client
        notification_id = uuid.uuid4()

        with patch(
            "api.routes.notifications.mark_notifications_read",
            new=AsyncMock(return_value=1),
        ) as mark_read:
            response = await client.post(
                "/api/v1/notifications/mark-read",
                json={"notification_ids": [str(notification_id)]},
            )

        assert response.status_code == 200
        assert response.json() == {"marked": 1}
        assert mark_read.await_count == 1

    @pytest.mark.asyncio
    async def test_resolve_action_delegates_to_server_authoritative_service(
        self,
        scientist_client,
    ):
        client, _db = scientist_client
        notification_id = uuid.uuid4()
        result = NotificationActionResult(
            notification_id=notification_id,
            actionable=True,
            destination=f"/analyses/{uuid.uuid4()}/report",
            marked_read=True,
        )

        with patch(
            "api.routes.notifications.resolve_notification_action",
            new=AsyncMock(return_value=result),
        ) as resolve_action:
            response = await client.post(f"/api/v1/notifications/{notification_id}/resolve-action")

        assert response.status_code == 200
        assert response.json() == {
            "notification_id": str(notification_id),
            "actionable": True,
            "destination": result.destination,
            "marked_read": True,
        }
        assert resolve_action.await_count == 1
        assert resolve_action.await_args.kwargs["notification_id"] == notification_id
        assert resolve_action.await_args.kwargs["user"].role.value == "scientist"

    @pytest.mark.asyncio
    async def test_resolve_action_validates_notification_uuid(self, scientist_client):
        client, _db = scientist_client

        response = await client.post("/api/v1/notifications/not-a-uuid/resolve-action")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_dismiss_all_delegates_to_service(self, scientist_client):
        client, _db = scientist_client

        with patch(
            "api.routes.notifications.dismiss_all_notifications",
            new=AsyncMock(return_value=4),
        ) as dismiss_all:
            response = await client.post("/api/v1/notifications/dismiss-all")

        assert response.status_code == 200
        assert response.json() == {"marked": 4}
        assert dismiss_all.await_count == 1

    @pytest.mark.asyncio
    async def test_get_preferences_uses_service(self, scientist_client):
        client, _db = scientist_client
        payload = {
            "email_on_analysis_complete": False,
            "email_on_monitor_alert": True,
            "email_digest_frequency": "weekly",
        }

        with patch(
            "api.routes.notifications.get_notification_preferences",
            return_value=payload,
        ) as get_prefs:
            response = await client.get("/api/v1/notifications/preferences")

        assert response.status_code == 200
        assert response.json() == payload
        get_prefs.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_preferences_delegates_to_service(self, scientist_client):
        client, _db = scientist_client
        payload = {
            "email_on_analysis_complete": False,
            "email_on_monitor_alert": False,
            "email_digest_frequency": DigestFrequency.WEEKLY.value,
        }

        with patch(
            "api.routes.notifications.update_notification_preferences",
            new=AsyncMock(return_value=payload),
        ) as update_prefs:
            response = await client.put(
                "/api/v1/notifications/preferences",
                json=payload,
            )

        assert response.status_code == 200
        assert response.json() == payload
        assert update_prefs.await_count == 1
