"""Unit tests for the SSO service layer.

These tests cover:
- get_sso_status — live Clerk path, fallback to cached DB, network error
- configure_sso — enable / disable intent logging, audit event, instructions
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from conftest import make_mock_db

from api.db.models_identity import Organization
from api.errors import APIError
from api.schemas.sso import SSOConfigureRequest
from api.services.sso import (
    _clerk_dashboard_url,
    _connection_to_status,
    _parse_provider_label,
    configure_sso,
    get_sso_status,
)
from api.services.sso_freshness import SSO_STATUS_MAX_AGE, sso_status_is_fresh

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_org(
    *,
    clerk_org_id: str = "org_clerk_test",
    sso_enabled: bool = False,
    sso_provider: str | None = None,
    sso_domains: list | None = None,
    sso_required: bool = False,
    sso_status_available: bool = True,
    sso_last_synced_at: datetime | None = None,
    sso_last_refresh_started_at: datetime | None = None,
    sso_refresh_attempt_id: uuid.UUID | None = None,
) -> MagicMock:
    org = MagicMock(spec=Organization)
    org.id = uuid.uuid4()
    org.clerk_org_id = clerk_org_id
    org.sso_enabled = sso_enabled
    org.sso_provider = sso_provider
    org.sso_domains = sso_domains or []
    org.sso_required = sso_required
    org.sso_status_available = sso_status_available
    org.sso_last_synced_at = (
        sso_last_synced_at
        if sso_last_synced_at is not None
        else (datetime.now(UTC) if sso_status_available else None)
    )
    org.sso_last_refresh_started_at = sso_last_refresh_started_at
    org.sso_refresh_attempt_id = sso_refresh_attempt_id
    org.settings = {}
    return org


def make_clerk_connection(
    *,
    provider: str = "saml_okta",
    active: bool = True,
    domains: list[str] | None = None,
) -> dict:
    return {
        "id": f"ec_{uuid.uuid4().hex[:8]}",
        "provider": provider,
        "active": active,
        "domains": [{"name": d} for d in (domains or ["acme.com"])],
    }


# ---------------------------------------------------------------------------
# Freshness policy
# ---------------------------------------------------------------------------


class TestSSOStatusFreshness:
    @pytest.mark.parametrize(
        ("available", "last_synced_at"),
        [
            (False, datetime(2026, 7, 14, 10, 0, tzinfo=UTC)),
            (True, None),
            (True, datetime(2026, 7, 14, 10, 0)),
        ],
        ids=["unavailable", "missing", "naive-last-sync"],
    )
    def test_rejects_unavailable_or_untrusted_timestamps(
        self,
        available: bool,
        last_synced_at: datetime | None,
    ):
        assert not sso_status_is_fresh(
            available=available,
            last_synced_at=last_synced_at,
            now=datetime(2026, 7, 14, 10, 1, tzinfo=UTC),
        )

    def test_rejects_naive_current_time(self):
        assert not sso_status_is_fresh(
            available=True,
            last_synced_at=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
            now=datetime(2026, 7, 14, 10, 1),
        )

    def test_accepts_exact_max_age_but_rejects_older_or_future_state(self):
        now = datetime(2026, 7, 14, 10, 5, tzinfo=UTC)
        assert sso_status_is_fresh(
            available=True,
            last_synced_at=now - SSO_STATUS_MAX_AGE,
            now=now,
        )
        assert not sso_status_is_fresh(
            available=True,
            last_synced_at=now - SSO_STATUS_MAX_AGE - timedelta(microseconds=1),
            now=now,
        )
        assert not sso_status_is_fresh(
            available=True,
            last_synced_at=now + timedelta(microseconds=1),
            now=now,
        )


# ---------------------------------------------------------------------------
# _parse_provider_label
# ---------------------------------------------------------------------------


class TestParseProviderLabel:
    def test_known_providers(self):
        assert _parse_provider_label("saml_okta") == "Okta"
        assert _parse_provider_label("saml_microsoft") == "Azure AD"
        assert _parse_provider_label("saml_google") == "Google Workspace"
        assert _parse_provider_label("saml_custom") == "Custom SAML"
        assert _parse_provider_label("oidc_custom") == "Custom OIDC"

    def test_unknown_provider_returned_as_is(self):
        assert _parse_provider_label("saml_ping") == "saml_ping"

    def test_none_returns_none(self):
        assert _parse_provider_label(None) is None


def test_clerk_dashboard_url_encodes_untrusted_org_path_data():
    settings = SimpleNamespace(clerk_domain="clerk.praviar.io")

    assert _clerk_dashboard_url("org_123/../../users?x=1", settings) == (
        "https://dashboard.clerk.com/organizations/"
        "org_123%2F..%2F..%2Fusers%3Fx%3D1/sso-connections"
    )


# ---------------------------------------------------------------------------
# _connection_to_status
# ---------------------------------------------------------------------------


class TestConnectionToStatus:
    def test_active_connection(self):
        conn = make_clerk_connection(active=True, domains=["acme.com", "acme.io"])
        result = _connection_to_status([conn])
        assert result["sso_enabled"] is True
        assert result["status"] == "active"
        assert result["provider"] == "Okta"
        assert set(result["domains"]) == {"acme.com", "acme.io"}

    def test_pending_connection(self):
        conn = make_clerk_connection(active=False)
        result = _connection_to_status([conn])
        assert result["sso_enabled"] is False
        assert result["status"] == "pending"

    def test_no_connections_returns_inactive(self):
        result = _connection_to_status([])
        assert result["sso_enabled"] is False
        assert result["status"] == "inactive"
        assert result["provider"] is None
        assert result["domains"] == []

    def test_active_takes_precedence_over_pending(self):
        active_conn = make_clerk_connection(active=True, domains=["prod.com"])
        pending_conn = make_clerk_connection(active=False, domains=["staging.com"])
        result = _connection_to_status([active_conn, pending_conn])
        assert result["status"] == "active"
        assert "prod.com" in result["domains"]


# ---------------------------------------------------------------------------
# get_sso_status
# ---------------------------------------------------------------------------


class TestGetSSOStatus:
    def _make_db_with_org(self, org: MagicMock) -> AsyncMock:
        db = make_mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = org
        db.execute.return_value = result
        return db

    @pytest.mark.asyncio
    async def test_returns_active_status_from_clerk(self):
        org = make_org(clerk_org_id="org_abc")
        db = self._make_db_with_org(org)

        connection = make_clerk_connection(active=True, domains=["pharma.com"])

        class _MockClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = [connection]
                return resp

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(db, org_id=org.id, http_client_cls=_MockClient)  # type: ignore[arg-type]

        assert result.sso_enabled is True
        assert result.status == "active"
        assert "pharma.com" in result.domains
        assert result.provider == "Okta"
        assert result.clerk_dashboard_url is not None
        assert result.sso_status_available is True
        assert result.sso_status_stale is False
        assert result.sso_unavailable_reason is None
        assert org.sso_status_available is True
        assert org.sso_last_synced_at is not None
        assert org.sso_last_refresh_started_at is not None
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_authoritative_empty_response_clears_cached_active_state(self):
        previous_sync = datetime(2026, 7, 13, tzinfo=UTC)
        synced_at = datetime(2026, 7, 14, 10, 30, tzinfo=UTC)
        org = make_org(
            sso_enabled=True,
            sso_provider="Okta",
            sso_domains=["acme.com"],
            sso_last_synced_at=previous_sync,
        )
        db = self._make_db_with_org(org)

        class _EmptyClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=200)
                response.json.return_value = []
                return response

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                http_client_cls=_EmptyClient,  # type: ignore[arg-type]
                now_fn=lambda: synced_at,
            )

        assert result.status == "inactive"
        assert result.sso_enabled is False
        assert result.provider is None
        assert result.domains == []
        assert result.sso_status_available is True
        assert result.sso_last_synced_at == synced_at
        assert result.sso_status_stale is False
        assert org.sso_enabled is False
        assert org.sso_provider is None
        assert org.sso_domains == []
        assert org.sso_status_available is True
        assert org.sso_last_synced_at == synced_at
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_network_error_preserves_cached_state_but_marks_it_unavailable(self):
        previous_sync = datetime(2026, 7, 13, tzinfo=UTC)
        org = make_org(
            sso_enabled=True,
            sso_provider="Okta",
            sso_domains=["acme.com"],
            sso_last_synced_at=previous_sync,
        )
        db = self._make_db_with_org(org)

        class _FailingClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                raise httpx.RequestError("connection refused")

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(db, org_id=org.id, http_client_cls=_FailingClient)  # type: ignore[arg-type]

        assert result.sso_enabled is True
        assert result.status == "active"
        assert "acme.com" in result.domains
        assert result.sso_status_available is False
        assert result.sso_status_stale is True
        assert result.sso_unavailable_reason == "transport_error"
        assert result.sso_last_synced_at == previous_sync
        assert result.clerk_dashboard_url is None
        assert org.sso_enabled is True
        assert org.sso_domains == ["acme.com"]
        assert org.sso_status_available is False
        assert org.sso_last_synced_at == previous_sync
        assert org.sso_last_refresh_started_at is not None
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_inactive_when_no_clerk_key(self):
        org = make_org()
        db = self._make_db_with_org(org)

        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="")

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(db, org_id=org.id)

        assert result.sso_enabled is False
        assert result.status == "inactive"
        assert result.sso_status_available is False
        assert result.sso_status_stale is True
        assert result.sso_unavailable_reason == "missing_secret"
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_org(self):
        db = make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            pytest.raises(APIError) as exc_info,
        ):
            await get_sso_status(db, org_id=uuid.uuid4())

        assert exc_info.value.status == 404

    @pytest.mark.asyncio
    async def test_org_deleted_before_refresh_claim_fails_closed_without_provider_call(self):
        org = make_org()
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result]
        client = MagicMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            pytest.raises(APIError) as exc_info,
        ):
            await get_sso_status(db, org_id=org.id, http_client_cls=client)

        assert exc_info.value.status == 404
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
        client.assert_not_called()

    @pytest.mark.asyncio
    async def test_provider_error_preserves_cache_and_marks_unavailable(self):
        org = make_org(
            clerk_org_id="org_abc",
            sso_enabled=True,
            sso_provider="Okta",
            sso_domains=["acme.com"],
        )
        db = self._make_db_with_org(org)

        class _ErrorClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                resp = MagicMock()
                resp.status_code = 500
                resp.text = "internal error"
                return resp

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(db, org_id=org.id, http_client_cls=_ErrorClient)  # type: ignore[arg-type]

        assert result.status == "active"
        assert result.sso_status_available is False
        assert result.sso_unavailable_reason == "provider_error"
        assert org.sso_enabled is True
        assert org.sso_domains == ["acme.com"]
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status_code", "reason"),
        [(404, "not_found"), (200, "malformed_response")],
    )
    async def test_non_authoritative_response_preserves_cached_identity(
        self, status_code: int, reason: str
    ):
        org = make_org(
            sso_enabled=True,
            sso_provider="Azure AD",
            sso_domains=["buyer.example"],
        )
        db = self._make_db_with_org(org)

        class _Client:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=status_code)
                response.json.return_value = {"unexpected": []}
                return response

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(db, org_id=org.id, http_client_cls=_Client)  # type: ignore[arg-type]

        assert result.provider == "Azure AD"
        assert result.domains == ["buyer.example"]
        assert result.sso_status_available is False
        assert result.sso_unavailable_reason == reason
        assert org.sso_enabled is True
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_circuit_open_preserves_cache_and_marks_unavailable(self):
        from api.circuit_breaker import CircuitOpenError

        org = make_org(sso_enabled=True, sso_provider="Okta", sso_domains=["acme.com"])
        db = self._make_db_with_org(org)
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch(
                "api.circuit_breaker.clerk_breaker.call",
                new=AsyncMock(side_effect=CircuitOpenError("clerk", 30.0)),
            ),
        ):
            result = await get_sso_status(db, org_id=org.id)

        assert result.status == "active"
        assert result.sso_status_available is False
        assert result.sso_unavailable_reason == "circuit_open"
        assert org.sso_enabled is True
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_recovery_refreshes_authoritative_state_and_freshness(self):
        synced_at = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)
        org = make_org(sso_status_available=False)
        db = self._make_db_with_org(org)
        connection = make_clerk_connection(active=True, domains=["recovered.example"])

        class _Client:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=200)
                response.json.return_value = [connection]
                return response

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                http_client_cls=_Client,  # type: ignore[arg-type]
                now_fn=lambda: synced_at,
            )

        assert result.status == "active"
        assert result.sso_status_available is True
        assert result.sso_status_stale is False
        assert result.sso_last_synced_at == synced_at
        assert org.sso_domains == ["recovered.example"]

    @pytest.mark.asyncio
    async def test_status_commit_failure_fails_closed(self):
        org = make_org(sso_enabled=True, sso_provider="Okta", sso_domains=["acme.com"])
        db = self._make_db_with_org(org)
        db.commit.side_effect = RuntimeError("database unavailable")
        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            pytest.raises(APIError) as exc_info,
        ):
            await get_sso_status(db, org_id=org.id)

        assert exc_info.value.status == 503
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_org_lookup_is_tenant_scoped(self):
        org = make_org()
        db = self._make_db_with_org(org)
        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="")

        with patch("api.services.sso.get_settings", return_value=settings):
            await get_sso_status(db, org_id=org.id)

        statement = db.execute.await_args_list[0].args[0]
        assert org.id in statement.compile().params.values()

    @pytest.mark.asyncio
    async def test_older_failed_fetch_cannot_overwrite_newer_successful_refresh(self):
        fetch_started_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        newer_sync = datetime(2026, 7, 14, 10, 0, 1, tzinfo=UTC)
        org = make_org(
            sso_enabled=True,
            sso_provider="Okta",
            sso_domains=["cached.example"],
            sso_last_synced_at=datetime(2026, 7, 14, 9, 59, tzinfo=UTC),
        )
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=1)
        conditional_update_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result, conditional_update_result]

        async def _refresh_newer_success(*_args, **_kwargs):
            org.sso_enabled = False
            org.sso_provider = None
            org.sso_domains = []
            org.sso_status_available = True
            org.sso_last_synced_at = newer_sync
            org.sso_last_refresh_started_at = newer_sync
            org.sso_refresh_attempt_id = uuid.uuid4()

        db.refresh.side_effect = _refresh_newer_success
        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="clerk.praviar.io")
        times = iter([fetch_started_at, newer_sync])

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                now_fn=lambda: next(times),
            )

        assert result.status == "inactive"
        assert result.sso_status_available is True
        assert result.sso_status_stale is False
        assert result.sso_last_synced_at == newer_sync
        assert result.sso_unavailable_reason is None
        db.refresh.assert_awaited_once()
        claim_statement = db.execute.await_args_list[1].args[0]
        update_statement = db.execute.await_args_list[2].args[0]
        claim_params = claim_statement.compile().params
        compiled = update_statement.compile()
        assert org.id in compiled.params.values()
        assert fetch_started_at in claim_statement.compile().params.values()
        assert claim_params["sso_status_available"] is False
        assert claim_params["sso_refresh_attempt_id"] == compiled.params["sso_refresh_attempt_id_1"]
        where_sql = str(update_statement.whereclause)
        assert "sso_refresh_attempt_id" in where_sql
        assert "sso_last_refresh_started_at" not in where_sql
        assert "sso_last_synced_at" not in where_sql
        assert "sso_status_available" not in where_sql

    @pytest.mark.asyncio
    async def test_older_success_cannot_overwrite_newer_authoritative_refresh(self):
        fetch_started_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        newer_sync = datetime(2026, 7, 14, 10, 0, 1, tzinfo=UTC)
        older_fetch_finished_at = datetime(2026, 7, 14, 10, 0, 2, tzinfo=UTC)
        org = make_org(
            sso_enabled=False,
            sso_provider=None,
            sso_domains=[],
            sso_last_synced_at=datetime(2026, 7, 14, 9, 59, tzinfo=UTC),
        )
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=1)
        conditional_update_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result, conditional_update_result]

        async def _refresh_newer_success(*_args, **_kwargs):
            org.sso_enabled = False
            org.sso_provider = None
            org.sso_domains = []
            org.sso_status_available = True
            org.sso_last_synced_at = newer_sync
            org.sso_last_refresh_started_at = newer_sync
            org.sso_refresh_attempt_id = uuid.uuid4()

        db.refresh.side_effect = _refresh_newer_success
        older_active_connection = make_clerk_connection(
            active=True,
            domains=["superseded.example"],
        )

        class _OlderSlowClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=200)
                response.json.return_value = [older_active_connection]
                return response

        times = iter([fetch_started_at, older_fetch_finished_at])
        settings = SimpleNamespace(
            clerk_secret_key="sk_live",
            clerk_domain="clerk.praviar.io",
        )
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                http_client_cls=_OlderSlowClient,  # type: ignore[arg-type]
                now_fn=lambda: next(times),
            )

        assert result.status == "inactive"
        assert result.sso_enabled is False
        assert result.domains == []
        assert result.sso_status_available is True
        assert result.sso_status_stale is False
        assert result.sso_last_synced_at == newer_sync
        assert "superseded.example" not in result.domains
        db.refresh.assert_awaited_once()
        claim_statement = db.execute.await_args_list[1].args[0]
        update_statement = db.execute.await_args_list[2].args[0]
        claim_params = claim_statement.compile().params
        compiled = update_statement.compile()
        assert org.id in compiled.params.values()
        assert fetch_started_at in claim_statement.compile().params.values()
        assert claim_params["sso_refresh_attempt_id"] == compiled.params["sso_refresh_attempt_id_1"]
        assert "sso_enabled" in str(update_statement)
        assert "sso_domains" in str(update_statement)
        assert "sso_refresh_attempt_id" in str(update_statement.whereclause)

    @pytest.mark.asyncio
    async def test_older_success_cannot_resurrect_availability_after_newer_failure(self):
        older_start = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        newer_failure_start = datetime(2026, 7, 14, 10, 0, 1, tzinfo=UTC)
        older_finish = datetime(2026, 7, 14, 10, 0, 2, tzinfo=UTC)
        previous_sync = datetime(2026, 7, 14, 9, 59, tzinfo=UTC)
        org = make_org(
            sso_enabled=False,
            sso_provider=None,
            sso_domains=[],
            sso_last_synced_at=previous_sync,
        )
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=1)
        conditional_update_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result, conditional_update_result]

        async def _refresh_newer_failure(*_args, **_kwargs):
            org.sso_enabled = False
            org.sso_provider = None
            org.sso_domains = []
            org.sso_status_available = False
            org.sso_last_synced_at = previous_sync
            org.sso_last_refresh_started_at = newer_failure_start
            org.sso_refresh_attempt_id = uuid.uuid4()

        db.refresh.side_effect = _refresh_newer_failure
        older_active_connection = make_clerk_connection(
            active=True,
            domains=["must-not-resurrect.example"],
        )

        class _OlderSlowClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=200)
                response.json.return_value = [older_active_connection]
                return response

        times = iter([older_start, older_finish])
        settings = SimpleNamespace(
            clerk_secret_key="sk_live",
            clerk_domain="clerk.praviar.io",
        )
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                http_client_cls=_OlderSlowClient,  # type: ignore[arg-type]
                now_fn=lambda: next(times),
            )

        assert result.status == "inactive"
        assert result.sso_enabled is False
        assert result.domains == []
        assert result.sso_status_available is False
        assert result.sso_status_stale is True
        assert result.clerk_dashboard_url is None
        assert "must-not-resurrect.example" not in result.domains
        assert org.sso_last_refresh_started_at == newer_failure_start
        update_statement = db.execute.await_args_list[2].args[0]
        assert "sso_refresh_attempt_id" in str(update_statement.whereclause)

    @pytest.mark.asyncio
    async def test_equal_start_timestamps_still_use_unique_attempt_ordering(self):
        started_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        finished_at = datetime(2026, 7, 14, 10, 0, 1, tzinfo=UTC)
        previous_sync = datetime(2026, 7, 14, 9, 59, tzinfo=UTC)
        org = make_org(
            sso_status_available=False,
            sso_last_synced_at=previous_sync,
            sso_last_refresh_started_at=started_at,
        )
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=1)
        conditional_update_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result, conditional_update_result]

        async def _refresh_equal_winner(*_args, **_kwargs):
            org.sso_status_available = False
            org.sso_last_refresh_started_at = started_at
            org.sso_refresh_attempt_id = uuid.uuid4()

        db.refresh.side_effect = _refresh_equal_winner
        connection = make_clerk_connection(active=True, domains=["equal-loser.example"])

        class _Client:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def get(self, url, **kwargs):
                response = MagicMock(status_code=200)
                response.json.return_value = [connection]
                return response

        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")
        times = iter([started_at, finished_at])
        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                http_client_cls=_Client,  # type: ignore[arg-type]
                now_fn=lambda: next(times),
            )

        assert result.sso_status_available is False
        assert result.sso_status_stale is True
        assert "equal-loser.example" not in result.domains
        claim_statement = db.execute.await_args_list[1].args[0]
        completion_statement = db.execute.await_args_list[2].args[0]
        assert "sso_last_refresh_started_at" in str(claim_statement)
        where_sql = str(completion_statement.whereclause)
        assert "sso_refresh_attempt_id" in where_sql
        assert "sso_last_refresh_started_at" not in where_sql

    @pytest.mark.asyncio
    async def test_clock_rollback_cannot_overwrite_future_refresh_marker(self):
        fetch_started_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        response_time = datetime(2026, 7, 14, 10, 0, 1, tzinfo=UTC)
        future_sync = datetime(2026, 7, 14, 10, 1, tzinfo=UTC)
        org = make_org(
            sso_enabled=True,
            sso_provider="Okta",
            sso_domains=["future.example"],
            sso_last_synced_at=future_sync,
            sso_last_refresh_started_at=future_sync,
        )
        db = make_mock_db()
        load_result = MagicMock()
        load_result.scalar_one_or_none.return_value = org
        claim_result = MagicMock(rowcount=1)
        conditional_update_result = MagicMock(rowcount=0)
        db.execute.side_effect = [load_result, claim_result, conditional_update_result]

        async def _refresh_future_winner(*_args, **_kwargs):
            org.sso_status_available = True
            org.sso_last_synced_at = future_sync
            org.sso_last_refresh_started_at = future_sync
            org.sso_refresh_attempt_id = uuid.uuid4()

        db.refresh.side_effect = _refresh_future_winner
        settings = SimpleNamespace(clerk_secret_key="", clerk_domain="clerk.praviar.io")
        times = iter([fetch_started_at, response_time])

        with patch("api.services.sso.get_settings", return_value=settings):
            result = await get_sso_status(
                db,
                org_id=org.id,
                now_fn=lambda: next(times),
            )

        assert result.sso_status_available is True
        assert result.sso_status_stale is True
        assert result.clerk_dashboard_url is None
        assert result.sso_last_synced_at == future_sync
        assert org.sso_last_refresh_started_at == future_sync
        where_sql = str(db.execute.await_args_list[2].args[0].whereclause)
        assert "sso_refresh_attempt_id" in where_sql
        assert "sso_last_refresh_started_at" not in where_sql


# ---------------------------------------------------------------------------
# configure_sso
# ---------------------------------------------------------------------------


class TestConfigureSSO:
    def _make_db_with_org(self, org: MagicMock) -> AsyncMock:
        db = make_mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = org
        db.execute.return_value = result
        return db

    @pytest.mark.asyncio
    async def test_enable_returns_instructions(self):
        org = make_org(clerk_org_id="org_xyz")
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
        ):
            result = await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
            )

        assert result.status == "instructions_provided"
        assert len(result.next_steps) > 0
        assert result.clerk_dashboard_url is not None
        audit_fn.assert_awaited_once()
        assert audit_fn.await_args is not None
        call_kwargs = audit_fn.await_args.kwargs
        assert call_kwargs["action"] == "admin.sso.enable_requested"
        assert org.sso_required is True
        assert "sso_required" not in org.settings
        assert call_kwargs["fail_closed"] is True
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_configuration_serializes_freshness_check_with_status_refresh(self):
        org = make_org(clerk_org_id="org_xyz")
        db = self._make_db_with_org(org)
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", new=AsyncMock()),
        ):
            await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
            )

        load_statement = db.execute.await_args_list[0].args[0]
        assert org.id in load_statement.compile().params.values()
        assert "FOR UPDATE" in str(load_statement)

    @pytest.mark.asyncio
    async def test_unavailable_live_status_locks_configuration(self):
        org = make_org(clerk_org_id="org_xyz", sso_status_available=False)
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
            pytest.raises(APIError) as exc_info,
        ):
            await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
            )

        assert exc_info.value.status == 503
        assert "unavailable or stale" in exc_info.value.detail
        audit_fn.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "last_synced_at",
        [None, datetime(2026, 7, 14, 9, 0, tzinfo=UTC)],
        ids=["missing-timestamp", "expired-timestamp"],
    )
    async def test_available_flag_does_not_bypass_stale_timestamp(
        self, last_synced_at: datetime | None
    ):
        now = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        org = make_org(sso_status_available=True)
        org.sso_last_synced_at = last_synced_at
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
            pytest.raises(APIError) as exc_info,
        ):
            await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
                now_fn=lambda: now,
            )

        assert exc_info.value.status == 503
        audit_fn.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disable_returns_instructions(self):
        org = make_org(clerk_org_id="org_xyz", sso_enabled=True)
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="clerk.praviar.io")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
        ):
            result = await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=False),
            )

        assert result.status == "instructions_provided"
        assert audit_fn.await_args is not None
        call_kwargs = audit_fn.await_args.kwargs
        assert call_kwargs["action"] == "admin.sso.disable_requested"
        assert org.sso_required is False
        assert "sso_required" not in org.settings

    @pytest.mark.asyncio
    async def test_audit_failure_rolls_back(self):
        org = make_org()
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock(side_effect=RuntimeError("audit store unavailable"))
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
            pytest.raises(RuntimeError, match="audit store unavailable"),
        ):
            await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
            )

        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_clerk_dashboard_url_when_domain_unset(self):
        org = make_org(clerk_org_id="org_xyz")
        db = self._make_db_with_org(org)
        audit_fn = AsyncMock()
        settings = SimpleNamespace(clerk_secret_key="sk_live", clerk_domain="")

        with (
            patch("api.services.sso.get_settings", return_value=settings),
            patch("api.services.sso.write_audit_log", audit_fn),
        ):
            result = await configure_sso(
                db,
                org_id=org.id,
                user_id=uuid.uuid4(),
                body=SSOConfigureRequest(enable=True),
            )

        assert result.clerk_dashboard_url is None
