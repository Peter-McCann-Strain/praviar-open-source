"""Tests for /api/webhooks/clerk endpoint.

The webhook handler uses its own DB session (async_session_factory) and
svix verification, so we mock at the module level.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

# ---------------------------------------------------------------------------
# Fixtures — webhook tests need a different setup since the endpoint does
# not use get_current_user / get_db deps. It accesses settings directly
# and creates its own sessions.
# ---------------------------------------------------------------------------


@pytest.fixture
async def webhook_client():
    """Client that only patches engine.dispose for lifespan, plus settings."""
    from api.main import create_app

    app = create_app()

    mock_engine = AsyncMock()
    with patch("api.main.engine", mock_engine):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


SVIX_HEADERS = {
    "svix-id": "msg_test123",
    "svix-timestamp": "1700000000",
    "svix-signature": "v1,test_signature",
}


# ---------------------------------------------------------------------------
# POST /api/webhooks/clerk
# ---------------------------------------------------------------------------


class TestClerkWebhook:
    @pytest.mark.asyncio
    async def test_missing_signature_headers(self, webhook_client):
        with patch("api.routes.webhooks.get_settings") as mock_settings:
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=b"{}",
                headers={"Content-Type": "application/json"},
            )
        # Missing svix headers => 401
        assert resp.status_code == 401
        assert "Missing webhook signature" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_webhook_secret(self, webhook_client):
        """When CLERK_WEBHOOK_SECRET is empty, should return 500."""
        with patch("api.routes.webhooks.get_settings") as mock_settings:
            settings = MagicMock()
            settings.clerk_webhook_secret = ""
            mock_settings.return_value = settings

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=b"{}",
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )
        assert resp.status_code == 500
        assert "CLERK_WEBHOOK_SECRET not configured" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_user_created_event(self, webhook_client):
        """user.created is receipted but waits for membership authority."""
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_user_new",
                "email_addresses": [{"email_address": "new@praviar.io"}],
                "first_name": "Jane",
                "last_name": "Doe",
                "public_metadata": {"role": "scientist"},
                "organization_memberships": [
                    {
                        "organization": {
                            "id": "org_clerk_123",
                            "name": "Pharma Inc",
                        }
                    }
                ],
            },
        }

        mock_db = AsyncMock()
        # User lookup => not found
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        # Org lookup => not found
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = None
        # First user in a newly-created organization receives the admin role.
        org_users_result = MagicMock()
        org_users_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[user_result, org_result, org_users_result])
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        # Create a proper async context manager for the session
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_membership"
        # Only the transactional Svix receipt is written. No org/user fallback.
        assert mock_db.add.call_count == 1
        assert mock_db.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_user_created_already_exists(self, webhook_client):
        """If user already exists, return already_exists."""
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_existing",
                "email_addresses": [{"email_address": "existing@bio.io"}],
                "first_name": "Existing",
                "last_name": "User",
                "public_metadata": {},
                "organization_memberships": [],
            },
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        existing_user = MagicMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute = AsyncMock(return_value=user_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_membership"

    @pytest.mark.asyncio
    async def test_user_created_invalid_role_fails_closed(self, webhook_client):
        """user metadata cannot grant a role; membership events are authoritative."""
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_bad_role",
                "email_addresses": [{"email_address": "bad-role@bio.io"}],
                "first_name": "Bad",
                "last_name": "Role",
                "public_metadata": {"role": "owner"},
                "organization_memberships": [],
            },
        }

        mock_db = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=user_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_membership"
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_created_membership_without_org_id_fails_closed(self, webhook_client):
        """Non-contract membership arrays on user.created are never consumed."""
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_missing_org",
                "email_addresses": [{"email_address": "missing-org@bio.io"}],
                "first_name": "Missing",
                "last_name": "Org",
                "public_metadata": {"role": "scientist"},
                "organization_memberships": [{"organization": {"name": "No Id Inc"}}],
            },
        }

        mock_db = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=user_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_membership"
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_created_handler_failure_rolls_back(self, webhook_client):
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_rollback",
                "email_addresses": [{"email_address": "rollback@bio.io"}],
            },
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.rollback = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
            patch(
                "api.routes.webhooks._handle_user_created",
                new=AsyncMock(side_effect=RuntimeError("user sync failed")),
            ),
            pytest.raises(RuntimeError, match="user sync failed"),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        mock_db.rollback.assert_awaited_once()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_event_type_fails_closed_before_session(self, webhook_client):
        payload = {"data": {"id": "clerk_missing_type"}}

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory") as session_factory_mock,
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 400
        assert "Missing webhook event type" in resp.json()["detail"]
        session_factory_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_created_non_object_data_fails_closed_before_session(
        self,
        webhook_client,
    ):
        payload = {"type": "user.created", "data": []}

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory") as session_factory_mock,
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 400
        assert "Webhook data must be an object" in resp.json()["detail"]
        session_factory_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_org_created_event(self, webhook_client):
        """Valid organization.created webhook creates org."""
        payload = {
            "type": "organization.created",
            "data": {
                "id": "org_new_123",
                "name": "New Org",
                "slug": "new-org",
            },
        }

        mock_db = AsyncMock()
        # Org lookup => not found
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=org_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert mock_db.add.call_count == 2  # receipt + organization
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_org_created_handler_failure_rolls_back(self, webhook_client):
        payload = {
            "type": "organization.created",
            "data": {
                "id": "org_rollback",
                "name": "Rollback Org",
                "slug": "rollback-org",
            },
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.rollback = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
            patch(
                "api.routes.webhooks._handle_org_created",
                new=AsyncMock(side_effect=RuntimeError("org sync failed")),
            ),
            pytest.raises(RuntimeError, match="org sync failed"),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        mock_db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_org_created_already_exists(self, webhook_client):
        """If org already exists, do nothing."""
        payload = {
            "type": "organization.created",
            "data": {
                "id": "org_existing",
                "name": "Existing Org",
                "slug": "existing-org",
            },
        }

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        existing_org = MagicMock()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = existing_org
        mock_db.execute = AsyncMock(return_value=org_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "already_exists"
        assert mock_db.add.call_count == 1  # receipt only

    @pytest.mark.asyncio
    async def test_verification_failure(self, webhook_client):
        """Webhook signature verification failure returns 401."""
        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.side_effect = ValueError("Invalid signature")
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=b'{"type":"user.created"}',
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 401
        assert "Webhook verification failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unknown_event_type(self, webhook_client):
        """Unknown event types should still return 200 (acknowledge receipt)."""
        payload = {"type": "session.ended", "data": {}}

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory") as session_factory_mock,
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        session_factory_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_created_personal_org(self, webhook_client):
        """User without membership remains pending; no personal org is invented."""
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_solo_user",
                "email_addresses": [{"email_address": "solo@bio.io"}],
                "first_name": "Solo",
                "last_name": "User",
                "public_metadata": {},
                "organization_memberships": [],
            },
        }

        mock_db = AsyncMock()
        # User lookup => not found
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=user_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.routes.webhooks.get_settings") as mock_settings,
            patch("svix.webhooks.Webhook") as mock_webhook,
            patch("api.routes.webhooks.async_session_factory", return_value=mock_session_ctx),
        ):
            settings = MagicMock()
            settings.clerk_webhook_secret = "whsec_test_secret"
            mock_settings.return_value = settings

            wh_instance = MagicMock()
            wh_instance.verify.return_value = payload
            mock_webhook.return_value = wh_instance

            resp = await webhook_client.post(
                "/api/webhooks/clerk",
                content=json.dumps(payload).encode(),
                headers={**SVIX_HEADERS, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_membership"
        assert mock_db.add.call_count == 1  # receipt only
