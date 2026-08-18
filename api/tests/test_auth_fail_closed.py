"""Auth fail-closed regressions for dev bypass and Clerk JWT verification."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy.exc import IntegrityError

from api import deps
from api.auth import clerk
from api.circuit_breaker import CircuitOpenError
from api.db.models import UserRole
from api.errors import APIError


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, user=None):
        self.user = user
        self.execute_calls = 0

    async def execute(self, *_args, **_kwargs):
        self.execute_calls += 1
        return _ScalarResult(self.user)


class _RowResult:
    """Result whose .first() returns the joined user and organization row."""

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeJwtDB:
    """DB stub for the real Clerk-JWT path."""

    def __init__(self, *, user, deletion_status, clerk_org_id="org_active"):
        if user is not None:
            if not hasattr(user, "membership_active"):
                user.membership_active = True
            if not hasattr(user, "role"):
                user.role = UserRole.SCIENTIST
            if not hasattr(user, "clerk_membership_id"):
                user.clerk_membership_id = (
                    None if clerk_org_id.startswith("personal_") else "mem_active"
                )
            if not hasattr(user, "clerk_membership_role"):
                user.clerk_membership_role = (
                    None if clerk_org_id.startswith("personal_") else "member"
                )
        self._row = None if user is None else (user, deletion_status, clerk_org_id)
        self.execute_calls = 0
        self.bound_org_id = None
        self.commit_calls = 0
        self.rollback_calls = 0

    async def execute(self, *_args, **_kwargs):
        self.execute_calls += 1
        return _RowResult(self._row)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


def _request_with_bearer(token: str):
    return SimpleNamespace(
        headers={"Authorization": f"Bearer {token}"},
        url=SimpleNamespace(path="/api/v1/analyses"),
        state=SimpleNamespace(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("allow_dev_auth_bypass", "app_env"),
    [
        (False, "dev"),
        (True, "prod"),
        (False, "prod"),
        (True, "test"),
    ],
)
async def test_dev_token_rejected_unless_bypass_enabled_in_dev(
    monkeypatch: pytest.MonkeyPatch,
    allow_dev_auth_bypass: bool,
    app_env: str,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(
            allow_dev_auth_bypass=allow_dev_auth_bypass,
            app_env=app_env,
        ),
    )
    monkeypatch.setattr(
        deps,
        "verify_clerk_token",
        MagicMock(side_effect=jwt.InvalidTokenError("dev-token is not a JWT")),
    )
    db = _FakeDB()

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer(deps.DEV_TOKEN), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 401
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_dev_token_accepted_only_with_bypass_enabled_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mock user must include org_id because get_current_user() now binds it
    # to the RLS context (api/db/session.py set_current_org_id).
    user = SimpleNamespace(
        clerk_user_id=deps.DEV_CLERK_USER_ID,
        org_id="00000000-0000-0000-0000-000000000001",
    )
    db = _FakeDB(user=user)
    verify_clerk_token = MagicMock(side_effect=AssertionError("dev bypass must not verify JWT"))
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=True, app_env="dev"),
    )
    monkeypatch.setattr(deps, "verify_clerk_token", verify_clerk_token)

    resolved = await deps.get_current_user(_request_with_bearer(deps.DEV_TOKEN), db)  # type: ignore[arg-type]

    assert resolved is user
    verify_clerk_token.assert_not_called()
    assert db.execute_calls == 2


def test_clerk_token_verification_requires_authorized_party_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        clerk,
        "get_settings",
        lambda: SimpleNamespace(
            clerk_publishable_key="",
            clerk_jwks_url="https://clerk.example.test/.well-known/jwks.json",
            clerk_domain="clerk.example.test",
            app_url="",
            cors_origins=[],
        ),
    )
    get_jwks_client = MagicMock(side_effect=AssertionError("JWKS must not be fetched"))
    monkeypatch.setattr(clerk, "_get_jwks_client", get_jwks_client)

    with pytest.raises(ValueError, match="APP_URL or CORS_ORIGINS"):
        clerk.verify_clerk_token("not-a-dev-token")

    get_jwks_client.assert_not_called()


def test_clerk_token_verification_requires_issuer_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        clerk,
        "get_settings",
        lambda: SimpleNamespace(
            clerk_publishable_key="pk_test_x",
            clerk_jwks_url="https://clerk.example.test/.well-known/jwks.json",
            clerk_domain="",
            app_url="https://app.example.test",
            cors_origins=["https://app.example.test"],
        ),
    )
    get_jwks_client = MagicMock(side_effect=AssertionError("JWKS must not be fetched"))
    monkeypatch.setattr(clerk, "_get_jwks_client", get_jwks_client)

    with pytest.raises(ValueError, match="CLERK_DOMAIN must be set"):
        clerk.verify_clerk_token("not-a-dev-token")

    get_jwks_client.assert_not_called()


@pytest.mark.asyncio
async def test_current_user_fails_closed_when_clerk_authorized_parties_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=False, app_env="prod"),
    )
    monkeypatch.setattr(
        clerk,
        "get_settings",
        lambda: SimpleNamespace(
            clerk_publishable_key="",
            clerk_jwks_url="https://clerk.example.test/.well-known/jwks.json",
            clerk_domain="clerk.example.test",
            app_url="",
            cors_origins=[],
        ),
    )
    get_jwks_client = MagicMock(side_effect=AssertionError("JWKS must not be fetched"))
    monkeypatch.setattr(clerk, "_get_jwks_client", get_jwks_client)
    db = _FakeDB()

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 401
    assert db.execute_calls == 0
    get_jwks_client.assert_not_called()


@pytest.mark.asyncio
async def test_clerk_jwks_connection_failure_maps_to_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "verify_clerk_token",
        MagicMock(side_effect=PyJWKClientConnectionError("provider unavailable")),
    )

    with pytest.raises(APIError) as exc_info:
        await deps._verify_clerk_principal("signed-token")

    assert exc_info.value.status == 503
    assert exc_info.value.detail == "Authentication provider is temporarily unavailable"
    assert exc_info.value.retry_after_seconds == 5


@pytest.mark.asyncio
async def test_clerk_jwks_open_circuit_maps_to_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "verify_clerk_token",
        MagicMock(side_effect=CircuitOpenError("clerk_jwks", 12.1)),
    )

    with pytest.raises(APIError) as exc_info:
        await deps._verify_clerk_principal("signed-token")

    assert exc_info.value.status == 503
    assert exc_info.value.detail == "Authentication provider is temporarily unavailable"
    assert exc_info.value.retry_after_seconds == 13


@pytest.mark.asyncio
async def test_clerk_verification_runs_off_the_async_request_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_thread_id = threading.get_ident()
    verification_thread_ids: list[int] = []

    def verify(_token: str) -> dict[str, object]:
        verification_thread_ids.append(threading.get_ident())
        return {
            "sub": "user_threaded",
            "v": 2,
            "o": {"id": "org_threaded", "rol": "member"},
        }

    monkeypatch.setattr(deps, "verify_clerk_token", verify)

    principal = await deps._verify_clerk_principal("signed-token")

    assert principal.user_id == "user_threaded"
    assert verification_thread_ids
    assert verification_thread_ids[0] != request_thread_id


def _enable_real_jwt_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sub: str,
    org_id: object = "org_active",
    org_role: str = "member",
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=False, app_env="prod"),
    )
    payload: dict[str, object] = {"sub": sub, "v": 2}
    if org_id is not None:
        payload["o"] = {"id": org_id, "rol": org_role}
    monkeypatch.setattr(deps, "verify_clerk_token", MagicMock(return_value=payload))


def test_membership_authority_rejects_deleted_membership() -> None:
    user = SimpleNamespace(
        clerk_membership_id="mem_deleted",
        clerk_membership_role="member",
        membership_active=True,
        membership_deleted_at=datetime.now(UTC),
        membership_permission_denied_at=None,
        role=UserRole.SCIENTIST,
    )

    assert (
        deps._membership_authority_is_consistent(
            user,  # type: ignore[arg-type]
            token_org_role="member",
        )
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deletion_status",
    ["billing_cancellation_pending", "archive_deletion_pending", "erased"],
)
async def test_current_user_rejected_when_org_erasure_blocks_new_writes(
    monkeypatch: pytest.MonkeyPatch,
    deletion_status: str,
) -> None:
    """A valid Clerk JWT is rejected once irreversible erasure work starts.

    The erasure path keeps the user row (PII redacted) for FK integrity, so the
    user still resolves by clerk_user_id. Authentication must fail before a
    request can create data behind the billing/archive erasure fence.
    """
    user = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        clerk_user_id="user_erased",
        org_id="00000000-0000-0000-0000-000000000009",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_erased")
    bind_mock = MagicMock(side_effect=AssertionError("must not bind RLS during erasure"))
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    db = _FakeJwtDB(user=user, deletion_status=deletion_status)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "local_role",
    [UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT],
)
async def test_current_user_allowed_when_org_active(
    monkeypatch: pytest.MonkeyPatch,
    local_role: UserRole,
) -> None:
    """A valid Clerk JWT for an org with no deletion_status resolves normally."""
    user = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        clerk_user_id="user_active",
        clerk_membership_id="mem_active",
        clerk_membership_role="member",
        membership_active=True,
        role=local_role,
        org_id="00000000-0000-0000-0000-00000000000a",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_active")

    async def _fake_bind(_db, org_id):
        return org_id

    monkeypatch.setattr(deps, "bind_current_org_to_session", _fake_bind)
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *a, **k: None)
    db = _FakeJwtDB(user=user, deletion_status=None)

    resolved = await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert resolved is user


@pytest.mark.asyncio
async def test_first_login_reconciliation_commits_before_read_only_auth_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="99999999-9999-4999-8999-999999999999",
        clerk_user_id="user_first_login",
        clerk_membership_id=None,
        clerk_membership_role=None,
        membership_active=True,
        role=UserRole.SCIENTIST,
        org_id="00000000-0000-0000-0000-000000000011",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_first_login")

    async def _reconcile(*_args, **_kwargs):
        user.clerk_membership_id = "mem_first_login"
        user.clerk_membership_role = "member"
        return {"status": "updated"}

    monkeypatch.setattr(deps, "bootstrap_clerk_membership", AsyncMock(side_effect=_reconcile))
    monkeypatch.setattr(deps, "bind_current_org_to_session", AsyncMock())
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *a, **k: None)
    db = _FakeJwtDB(user=user, deletion_status=None)

    resolved = await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert resolved is user
    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.execute_calls == 2


@pytest.mark.asyncio
async def test_failed_first_login_reconciliation_rolls_back_without_authenticating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        clerk_user_id="user_bootstrap_failed",
        clerk_membership_id=None,
        clerk_membership_role=None,
        membership_active=True,
        role=UserRole.SCIENTIST,
        org_id="00000000-0000-0000-0000-000000000012",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_bootstrap_failed")
    monkeypatch.setattr(
        deps,
        "bootstrap_clerk_membership",
        AsyncMock(side_effect=APIError(503, "Service Unavailable", "Clerk unavailable")),
    )
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    db = _FakeJwtDB(user=user, deletion_status=None)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 503
    assert db.commit_calls == 0
    assert db.rollback_calls == 2
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "constraint_name",
    [
        "uq_users_clerk_user_org",
        "uq_users_clerk_membership_id",
    ],
)
async def test_concurrent_first_login_unique_loser_rereads_committed_winner(
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
) -> None:
    winner = SimpleNamespace(
        id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        clerk_user_id="user_race",
        clerk_membership_id="mem_race",
        clerk_membership_role="member",
        membership_active=True,
        role=UserRole.SCIENTIST,
        org_id="00000000-0000-0000-0000-000000000013",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_race")

    class _ConstraintError(Exception):
        pass

    constraint_error = _ConstraintError()
    constraint_error.constraint_name = constraint_name

    race_error = IntegrityError("insert principal", {}, constraint_error)
    monkeypatch.setattr(
        deps,
        "bootstrap_clerk_membership",
        AsyncMock(side_effect=race_error),
    )
    monkeypatch.setattr(deps, "bind_current_org_to_session", AsyncMock())
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *a, **k: None)
    db = _FakeJwtDB(user=winner, deletion_status=None)
    db._row = None
    rows = [None, (winner, None, "org_active")]

    async def _sequence_execute(*_args, **_kwargs):
        db.execute_calls += 1
        return _RowResult(rows.pop(0))

    db.execute = _sequence_execute  # type: ignore[method-assign]

    resolved = await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert resolved is winner
    assert db.rollback_calls == 2
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_org_create_race_retries_membership_upsert_before_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    winner = SimpleNamespace(
        id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        clerk_user_id="user_org_race",
        clerk_membership_id="mem_org_race",
        clerk_membership_role="member",
        membership_active=True,
        role=UserRole.SCIENTIST,
        org_id="00000000-0000-0000-0000-000000000014",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_org_race")

    class _ConstraintError(Exception):
        constraint_name = "organizations_clerk_org_id_key"

    org_race = IntegrityError("insert org", {}, _ConstraintError())
    bootstrap = AsyncMock(side_effect=[org_race, {"status": "created"}])
    monkeypatch.setattr(deps, "bootstrap_clerk_membership", bootstrap)
    monkeypatch.setattr(deps, "bind_current_org_to_session", AsyncMock())
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *a, **k: None)
    db = _FakeJwtDB(user=winner, deletion_status=None)
    rows = [None, (winner, None, "org_active")]

    async def _sequence_execute(*_args, **_kwargs):
        db.execute_calls += 1
        return _RowResult(rows.pop(0))

    db.execute = _sequence_execute  # type: ignore[method-assign]

    resolved = await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert resolved is winner
    assert bootstrap.await_count == 2
    assert db.rollback_calls == 2
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_first_login_does_not_swallow_unrelated_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_real_jwt_path(monkeypatch, sub="user_unrelated_race")

    class _ConstraintError(Exception):
        constraint_name = "organizations_slug_key"

    integrity_error = IntegrityError("insert org", {}, _ConstraintError())
    monkeypatch.setattr(
        deps,
        "bootstrap_clerk_membership",
        AsyncMock(side_effect=integrity_error),
    )
    db = _FakeJwtDB(user=None, deletion_status=None)

    with pytest.raises(IntegrityError):
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert db.rollback_calls == 2


@pytest.mark.asyncio
async def test_current_user_rejects_stale_local_admin_after_signed_demotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="77777777-7777-4777-8777-777777777777",
        clerk_user_id="user_demoted",
        clerk_membership_id="mem_demoted",
        clerk_membership_role="admin",
        membership_active=True,
        role=UserRole.ADMIN,
        org_id="00000000-0000-0000-0000-00000000000f",
    )
    _enable_real_jwt_path(
        monkeypatch,
        sub="user_demoted",
        org_role="member",
    )
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    monkeypatch.setattr(deps, "bootstrap_clerk_membership", AsyncMock())
    db = _FakeJwtDB(user=user, deletion_status=None)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_rejects_signed_admin_until_promotion_webhook_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="88888888-8888-4888-8888-888888888888",
        clerk_user_id="user_promoted",
        clerk_membership_id="mem_promoted",
        clerk_membership_role="member",
        membership_active=True,
        role=UserRole.SCIENTIST,
        org_id="00000000-0000-0000-0000-000000000010",
    )
    _enable_real_jwt_path(
        monkeypatch,
        sub="user_promoted",
        org_role="admin",
    )
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    monkeypatch.setattr(deps, "bootstrap_clerk_membership", AsyncMock())
    db = _FakeJwtDB(user=user, deletion_status=None)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_rejects_enterprise_workspace_without_org_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="33333333-3333-4333-8333-333333333333",
        clerk_user_id="user_missing_org",
        org_id="00000000-0000-0000-0000-00000000000b",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_missing_org", org_id=None)
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    db = _FakeJwtDB(user=user, deletion_status=None, clerk_org_id="org_persisted")

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_rejects_legacy_top_level_org_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=False, app_env="prod"),
    )
    monkeypatch.setattr(
        deps,
        "verify_clerk_token",
        MagicMock(
            return_value={
                "sub": "user_legacy_token",
                "v": 1,
                "org_id": "org_persisted",
            }
        ),
    )
    db = _FakeJwtDB(user=None, deletion_status=None)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 401
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_current_user_rejects_malformed_v2_org_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(allow_dev_auth_bypass=False, app_env="prod"),
    )
    monkeypatch.setattr(
        deps,
        "verify_clerk_token",
        MagicMock(return_value={"sub": "user_malformed_org", "v": 2, "o": {}}),
    )
    db = _FakeJwtDB(user=None, deletion_status=None)

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 401
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_current_user_rejects_clerk_org_switch_until_membership_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="44444444-4444-4444-8444-444444444444",
        clerk_user_id="user_switching_org",
        org_id="00000000-0000-0000-0000-00000000000c",
    )
    _enable_real_jwt_path(
        monkeypatch,
        sub="user_switching_org",
        org_id="org_newly_selected",
    )
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    db = _FakeJwtDB(user=user, deletion_status=None, clerk_org_id="org_persisted")

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_requires_org_selection_without_org_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="55555555-5555-4555-8555-555555555555",
        clerk_user_id="user_personal",
        org_id="00000000-0000-0000-0000-00000000000d",
    )
    _enable_real_jwt_path(monkeypatch, sub="user_personal", org_id=None)

    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    db = _FakeJwtDB(
        user=user,
        deletion_status=None,
        clerk_org_id="personal_user_personal",
    )

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    assert exc_info.value.title == "Organization Required"
    assert exc_info.value.detail == "Select an organization before continuing."
    assert db.execute_calls == 0
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_rejects_enterprise_org_claim_for_personal_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="66666666-6666-4666-8666-666666666666",
        clerk_user_id="user_personal_with_org",
        org_id="00000000-0000-0000-0000-00000000000e",
    )
    _enable_real_jwt_path(
        monkeypatch,
        sub="user_personal_with_org",
        org_id="org_enterprise",
    )
    bind_mock = AsyncMock()
    monkeypatch.setattr(deps, "bind_current_org_to_session", bind_mock)
    monkeypatch.setattr(
        deps,
        "bootstrap_clerk_membership",
        AsyncMock(side_effect=APIError(403, "Forbidden", "No active membership")),
    )
    db = _FakeJwtDB(
        user=user,
        deletion_status=None,
        clerk_org_id="personal_user_personal_with_org",
    )

    with pytest.raises(APIError) as exc_info:
        await deps.get_current_user(_request_with_bearer("real-jwt-path"), db)  # type: ignore[arg-type]

    assert exc_info.value.status == 403
    bind_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_key_scope_dependency_returns_non_admin_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scopes=["analyses:write"],
    )
    auth_mock = AsyncMock(return_value=api_key)
    monkeypatch.setattr(deps, "authenticate_api_key", auth_mock)
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *a, **k: None)

    checker = deps.require_permission_or_api_key_scope("analysis.create", "analyses:write")
    db = _FakeDB()
    request = _request_with_bearer("raw-api-key")
    principal = await deps.get_authenticated_principal(
        request,
        db,  # type: ignore[arg-type]
    )
    authorized = await checker(principal)

    assert isinstance(principal, deps.APIKeyPrincipal)
    assert authorized is principal
    assert principal.org_id == api_key.org_id
    assert principal.id == api_key.user_id
    assert principal.role == UserRole.SCIENTIST
    assert principal.api_key_scopes == ("analyses:write",)
    assert principal.api_key_id == api_key.id
    assert request.state.auth_actor_type == "api_key"
    assert request.state.auth_api_key_id == str(api_key.id)
    auth_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_key_scope_dependency_falls_back_to_clerk_rbac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    monkeypatch.setattr(deps, "authenticate_api_key", AsyncMock(return_value=None))
    get_user_mock = AsyncMock(return_value=user)
    monkeypatch.setattr(deps, "get_current_user", get_user_mock)

    checker = deps.require_permission_or_api_key_scope("analysis.create", "analyses:write")
    principal = await deps.get_authenticated_principal(
        _request_with_bearer("clerk-jwt"),
        _FakeDB(),  # type: ignore[arg-type]
    )
    authorized = await checker(principal)

    assert principal is user
    assert authorized is user
    get_user_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_key_scope_dependency_keeps_clerk_rbac_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.CLIENT,
    )
    monkeypatch.setattr(deps, "authenticate_api_key", AsyncMock(return_value=None))
    monkeypatch.setattr(deps, "get_current_user", AsyncMock(return_value=user))

    checker = deps.require_permission_or_api_key_scope("analysis.create", "analyses:write")
    principal = await deps.get_authenticated_principal(
        _request_with_bearer("client-jwt"),
        _FakeDB(),  # type: ignore[arg-type]
    )

    with pytest.raises(APIError) as exc_info:
        await checker(principal)

    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_api_key_scope_dependency_rejects_authenticated_key_without_route_scope() -> None:
    principal = deps.APIKeyPrincipal(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
        api_key_id=uuid.uuid4(),
        api_key_scopes=("analyses:read",),
    )
    checker = deps.require_permission_or_api_key_scope("analysis.create", "analyses:write")

    with pytest.raises(APIError) as exc_info:
        await checker(principal)

    assert exc_info.value.status == 403
    assert "analyses:write" in exc_info.value.detail
