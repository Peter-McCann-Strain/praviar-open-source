"""Hostile tests for Clerk organization-membership synchronization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.db.models import (
    ClerkAdminOperation,
    ClerkMembershipTombstone,
    Organization,
    User,
    UserRole,
)
from api.errors import APIError
from api.services.clerk_webhooks import (
    MEMBERSHIP_CREATED,
    MEMBERSHIP_DELETED,
    MEMBERSHIP_UPDATED,
    _is_exact_partial_role_failure,
    bootstrap_clerk_membership,
    get_or_create_org,
    handle_membership_event,
    handle_org_created,
    handle_user_created,
)


def _scalar(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _rows(values: list[User]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _first(value) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _membership_payload(
    *,
    membership_id: str = "mem_123",
    org_id: str = "org_123",
    user_id: str | None = "user_123",
    role: str = "org:member",
    praviar_role: str | None = "scientist",
    updated_at: int = 1_789_000_000_000,
) -> dict:
    public_user_data = None
    if user_id is not None:
        public_user_data = {
            "user_id": user_id,
            "identifier": "chemist@praviar.io",
            "first_name": "Casey",
            "last_name": "Chemist",
        }
    payload = {
        "id": membership_id,
        "organization": {"id": org_id, "name": "Example Pharma"},
        "public_user_data": public_user_data,
        "role": role,
        "updated_at": updated_at,
    }
    if praviar_role is not None:
        payload["public_metadata"] = {
            "praviar_role_version": 1,
            "praviar_role": praviar_role,
        }
    return payload


class _BootstrapClient:
    def __init__(self, responses: list[httpx.Response], calls: list[dict], **_kwargs):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url: str, *, headers: dict, params: dict) -> httpx.Response:
        self._calls.append({"url": url, "headers": headers, "params": params})
        return self._responses.pop(0)


def _bootstrap_client_factory(responses: list[httpx.Response], calls: list[dict]):
    return lambda **kwargs: _BootstrapClient(responses, calls, **kwargs)


@pytest.mark.asyncio
async def test_user_created_waits_for_authoritative_membership_without_db_fallback(mock_db):
    result = await handle_user_created(
        mock_db,
        {
            "id": "user_123",
            # This field is not part of Clerk's user.created contract and must
            # never be used to invent a tenant or first-user admin.
            "organization_memberships": [{"organization": {"id": "org_untrusted"}}],
        },
    )

    assert result == {"status": "awaiting_membership"}
    mock_db.execute.assert_not_awaited()
    assert all(not isinstance(call.args[0], User) for call in mock_db.add.call_args_list)


@pytest.mark.asyncio
async def test_user_created_requires_durable_user_id(mock_db):
    with pytest.raises(APIError, match="Missing user ID"):
        await handle_user_created(mock_db, {"id": ""})


@pytest.mark.asyncio
async def test_get_or_create_org_requires_exact_id_and_uses_credit_defaults(mock_db):
    with pytest.raises(APIError, match="Missing organization ID"):
        await get_or_create_org(mock_db, clerk_org_id="", name="Example")

    mock_db.execute.return_value = _scalar(None)
    org = await get_or_create_org(mock_db, clerk_org_id="org_123", name="Example")
    assert isinstance(org, Organization)
    assert org.free_analyses_remaining == 2
    assert org.max_analyses_per_month == 2
    assert "FOR UPDATE" in str(mock_db.execute.await_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_local_role", "expected_token_role"),
    [
        ("org:member", UserRole.SCIENTIST, "member"),
        ("org:admin", UserRole.ADMIN, "admin"),
    ],
)
async def test_membership_created_maps_only_explicit_clerk_roles(
    mock_db,
    role: str,
    expected_local_role: UserRole,
    expected_token_role: str,
):
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ) as bind:
        result = await handle_membership_event(
            mock_db,
            _membership_payload(role=role),
            event_type=MEMBERSHIP_CREATED,
        )

    assert result == {"status": "created"}
    bind.assert_awaited_once_with(mock_db, org.id)
    created = mock_db.add.call_args.args[0]
    assert isinstance(created, User)
    assert created.org_id == org.id
    assert created.clerk_membership_id == "mem_123"
    assert created.clerk_membership_role == expected_token_role
    assert created.role == expected_local_role
    assert created.membership_active is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("praviar_role", "expected_role"),
    [
        ("attorney", UserRole.ATTORNEY),
        ("scientist", UserRole.SCIENTIST),
        ("client", UserRole.CLIENT),
    ],
)
async def test_member_metadata_maps_only_non_admin_app_roles(
    mock_db,
    praviar_role: str,
    expected_role: UserRole,
):
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        await handle_membership_event(
            mock_db,
            _membership_payload(praviar_role=praviar_role),
            event_type=MEMBERSHIP_CREATED,
        )

    created = mock_db.add.call_args.args[0]
    assert created.role == expected_role
    assert created.clerk_membership_role == "member"


@pytest.mark.asyncio
async def test_new_member_without_role_metadata_fails_closed(mock_db):
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]

    with (
        patch(
            "api.services.clerk_webhooks.bind_current_org_to_session",
            new=AsyncMock(),
        ),
        pytest.raises(APIError, match="Versioned Praviar membership role metadata is required"),
    ):
        await handle_membership_event(
            mock_db,
            _membership_payload(praviar_role=None),
            event_type=MEMBERSHIP_CREATED,
        )

    mock_db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_role", [UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT])
async def test_existing_member_without_metadata_revokes_authority(
    mock_db,
    existing_role: UserRole,
):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=existing_role,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(praviar_role=None),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "deactivated_missing_role_authority"}
    assert current.role == existing_role
    assert current.clerk_membership_role == "member"
    assert current.membership_active is False
    assert current.membership_permission_denied_at is not None


@pytest.mark.asyncio
async def test_membership_mutation_emits_prior_and_new_authority_audit_atomically(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.ATTORNEY,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [
        _scalar(org),
        _first(current),
        _scalar(None),
        _rows([current]),
        _first(current),
    ]
    audit = AsyncMock()

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(praviar_role="scientist"),
            event_type=MEMBERSHIP_UPDATED,
            event_id="msg_authority_1",
            write_audit_log_fn=audit,
        )

    assert result == {"status": "updated"}
    details = audit.await_args.kwargs["details"]
    assert details["delivery_event_id"] == "msg_authority_1"
    assert details["membership_id"] == "mem_123"
    assert details["prior_authority"]["local_role"] == "attorney"
    assert details["new_authority"]["local_role"] == "scientist"
    assert audit.await_args.kwargs["fail_closed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "public_metadata",
    [
        {"praviar_role_version": 2, "praviar_role": "scientist"},
        {"praviar_role_version": 1, "praviar_role": "admin"},
        {"praviar_role_version": 1, "praviar_role": "owner"},
        {"praviar_role_version": True, "praviar_role": "client"},
    ],
)
async def test_member_rejects_invalid_or_privilege_escalating_metadata(
    mock_db,
    public_metadata: dict[str, object],
):
    payload = _membership_payload()
    payload["public_metadata"] = public_metadata

    with pytest.raises(APIError, match="Versioned Praviar membership role metadata is required"):
        await handle_membership_event(
            mock_db,
            payload,
            event_type=MEMBERSHIP_CREATED,
        )

    assert all(not isinstance(call.args[0], User) for call in mock_db.add.call_args_list)


@pytest.mark.asyncio
async def test_membership_rejects_unknown_role_before_org_or_user_mutation(mock_db):
    with pytest.raises(APIError, match="Unsupported organization membership role"):
        await handle_membership_event(
            mock_db,
            _membership_payload(role="org:owner"),
            event_type=MEMBERSHIP_CREATED,
        )

    mock_db.execute.assert_not_awaited()
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_membership_update_before_create_requires_durable_user_id(mock_db):
    with pytest.raises(APIError, match="Missing user ID"):
        await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None),
            event_type=MEMBERSHIP_UPDATED,
        )

    mock_db.execute.assert_not_awaited()
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_membership_rejects_non_email_identifier_without_creating_principal(mock_db):
    org = MagicMock(id=uuid.uuid4())
    payload = _membership_payload()
    payload["public_user_data"]["identifier"] = "+15555550123"
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]

    with (
        patch(
            "api.services.clerk_webhooks.bind_current_org_to_session",
            new=AsyncMock(),
        ),
        pytest.raises(APIError, match="must be an email address"),
    ):
        await handle_membership_event(
            mock_db,
            payload,
            event_type=MEMBERSHIP_CREATED,
        )

    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_org_is_bound_before_membership_user_mutation(mock_db):
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]
    order: list[str] = []
    mock_db.add.side_effect = lambda _obj: order.append("add-user")
    bind = AsyncMock(side_effect=lambda *_args: order.append("bind-org"))

    with patch("api.services.clerk_webhooks.bind_current_org_to_session", new=bind):
        await handle_membership_event(
            mock_db,
            _membership_payload(),
            event_type=MEMBERSHIP_CREATED,
        )

    assert order == ["bind-org", "add-user"]
    statements = [str(call.args[0]) for call in mock_db.execute.await_args_list]
    assert "organizations" in statements[0]
    assert "FOR UPDATE" in statements[0]
    assert "clerk_membership_tombstones" in statements[1]
    assert "users" in statements[2]


@pytest.mark.asyncio
async def test_delete_with_nullable_public_user_creates_terminal_tombstone(mock_db):
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _scalar(None)]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None),
            event_type=MEMBERSHIP_DELETED,
        )

    assert result == {"status": "tombstoned"}
    tombstone = mock_db.add.call_args.args[0]
    assert isinstance(tombstone, ClerkMembershipTombstone)
    assert tombstone.clerk_membership_id == "mem_123"
    assert tombstone.clerk_user_id is None
    assert tombstone.org_id == org.id


@pytest.mark.asyncio
async def test_delete_before_create_tombstone_blocks_late_resurrection(mock_db):
    org = MagicMock(id=uuid.uuid4())
    tombstone = MagicMock(spec=ClerkMembershipTombstone)
    tombstone.clerk_membership_id = "mem_123"
    mock_db.execute.side_effect = [_scalar(org), _scalar(tombstone)]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_CREATED,
        )

    assert result == {"status": "ignored_deleted"}
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_stale_membership_update_cannot_change_role(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_790_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(role="org:admin", updated_at=1_789_000_000_000),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "ignored_stale"}
    assert current.role == UserRole.SCIENTIST
    assert current.clerk_membership_role == "member"


@pytest.mark.asyncio
async def test_stale_role_metadata_cannot_overwrite_newer_local_role(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.ATTORNEY,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_790_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(praviar_role="client", updated_at=1_789_000_000_000),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "ignored_stale"}
    assert current.role == UserRole.ATTORNEY
    assert current.clerk_membership_role == "member"


@pytest.mark.asyncio
async def test_delete_ignores_malformed_role_metadata_and_still_revokes(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        role=UserRole.SCIENTIST,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    payload = _membership_payload(user_id=None)
    payload["role"] = "org:custom_reviewer"
    payload["public_metadata"] = {"praviar_role_version": 999, "praviar_role": "admin"}
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _scalar(current),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            payload,
            event_type=MEMBERSHIP_DELETED,
        )

    assert result == {"status": "deleted"}
    assert current.membership_active is False


@pytest.mark.asyncio
async def test_current_membership_update_applies_role_demotion_monotonically(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.ADMIN,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(role="org:member"),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.SCIENTIST
    assert current.clerk_membership_role == "member"


@pytest.mark.asyncio
async def test_delete_deactivates_only_exact_membership_principal(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _scalar(current),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None),
            event_type=MEMBERSHIP_DELETED,
        )

    assert result == {"status": "deleted"}
    assert current.membership_active is False
    assert current.membership_deleted_at is not None


@pytest.mark.asyncio
async def test_newer_distinct_membership_can_reactivate_same_org_principal(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_old",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=False,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
        membership_deleted_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(membership_id="mem_new"),
            event_type=MEMBERSHIP_CREATED,
        )

    assert result == {"status": "updated"}
    assert current.membership_active is True
    assert current.clerk_membership_id == "mem_new"
    assert current.membership_deleted_at is None


@pytest.mark.asyncio
async def test_newer_valid_metadata_reactivates_same_metadata_deactivated_membership(
    mock_db,
):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=False,
        membership_permission_denied_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
        membership_deleted_at=None,
    )
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.membership_active is True
    assert current.membership_permission_denied_at is None


@pytest.mark.asyncio
async def test_true_deletion_marker_blocks_same_membership_even_without_tombstone_row(
    mock_db,
):
    org = MagicMock(id=uuid.uuid4())
    deleted_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=False,
        membership_permission_denied_at=deleted_at,
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=deleted_at,
        membership_deleted_at=deleted_at,
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "ignored_deleted"}
    assert current.membership_active is False
    assert current.membership_deleted_at == deleted_at


@pytest.mark.asyncio
async def test_webhook_interleaving_cannot_clear_operation_owned_denial(mock_db):
    org = MagicMock(id=uuid.uuid4())
    operation_id = uuid.uuid4()
    denied_at = datetime.fromtimestamp(1_789_000_000, tz=UTC)
    current = User(
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="member",
        org_id=org.id,
        email="chemist@praviar.io",
        full_name="Casey Chemist",
        role=UserRole.SCIENTIST,
        membership_active=True,
        membership_permission_denied_at=denied_at,
        membership_permission_denied_by_operation_id=operation_id,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
        membership_deleted_at=None,
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                praviar_role="attorney",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.ATTORNEY
    assert current.membership_permission_denied_at == denied_at
    assert current.membership_permission_denied_by_operation_id == operation_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation_state",
    [
        "requested",
        "metadata_call_started",
        "metadata_accepted",
        "role_call_started",
        "role_accepted",
    ],
)
async def test_membership_delete_terminalizes_every_open_role_state_and_releases_owner(
    mock_db,
    operation_state: str,
):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.ADMIN,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    operation = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org.id,
        initiated_by=uuid.uuid4(),
        operation_type="role_update",
        client_key_digest="a" * 64,
        request_hash="b" * 64,
        state=operation_state,
        target_user_id=current.id,
        requested_role="client",
    )
    denied_at = datetime.fromtimestamp(1_788_500_000, tz=UTC)
    current.membership_permission_denied_at = denied_at
    current.membership_permission_denied_by_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _scalar(current),
        _scalar(operation),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None, updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_DELETED,
        )

    assert result == {"status": "deleted"}
    assert operation.state == "failed"
    assert operation.last_error_code == "membership_deleted"
    assert current.membership_active is False
    assert current.membership_permission_denied_at > denied_at
    assert current.membership_permission_denied_by_operation_id is None
    statements = [str(call.args[0]) for call in mock_db.execute.await_args_list]
    assert "organizations" in statements[0]
    assert "FOR UPDATE" in statements[0]
    assert "users" in statements[2]
    assert "clerk_admin_operations" in statements[3]


@pytest.mark.asyncio
async def test_membership_delete_audits_terminalized_operation_in_same_transaction(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.ADMIN,
        membership_active=True,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
    )
    operation = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org.id,
        initiated_by=uuid.uuid4(),
        operation_type="role_update",
        client_key_digest="e" * 64,
        request_hash="f" * 64,
        state="role_call_started",
        target_user_id=current.id,
        requested_role="client",
    )
    current.membership_permission_denied_at = datetime.fromtimestamp(1_788_500_000, tz=UTC)
    current.membership_permission_denied_by_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _first(current),
        _scalar(None),
        _scalar(current),
        _scalar(operation),
        _first(current),
    ]
    audit = AsyncMock()

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None, updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_DELETED,
            event_id="msg_delete_open_operation",
            write_audit_log_fn=audit,
        )

    assert result == {"status": "deleted"}
    details = audit.await_args.kwargs["details"]
    assert details["terminalized_operation_id"] == str(operation.id)
    assert details["new_authority"]["membership_active"] is False
    assert details["new_authority"]["membership_permission_denied_by_operation_id"] is None
    assert audit.await_args.kwargs["fail_closed"] is True


def _partial_demotion_operation(*, org_id: uuid.UUID, user_id: uuid.UUID) -> ClerkAdminOperation:
    return ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=uuid.uuid4(),
        operation_type="role_update",
        client_key_digest="c" * 64,
        request_hash="d" * 64,
        state="failed",
        target_user_id=user_id,
        requested_role="client",
        provider_updated_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
        last_error_code="clerk_role_rejected_after_metadata_422",
    )


@pytest.mark.asyncio
async def test_partial_demotion_admin_echo_cannot_reopen_authority(mock_db):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    current.membership_permission_convergence_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(operation),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                role="org:admin",
                praviar_role="client",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.CLIENT
    assert current.clerk_membership_role == "admin"
    assert current.membership_permission_denied_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recovery",
    ["requested_member", "clean_admin", "explicit_admin"],
)
async def test_partial_demotion_exact_provider_convergence_releases_generic_denial(
    mock_db,
    recovery: str,
):
    org = MagicMock(id=uuid.uuid4())
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=datetime.fromtimestamp(1_789_000_000, tz=UTC),
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    current.membership_permission_convergence_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(operation),
    ]
    if recovery == "requested_member":
        payload = _membership_payload(
            role="org:member",
            praviar_role="client",
            updated_at=1_790_000_000_000,
        )
    elif recovery == "clean_admin":
        payload = _membership_payload(
            role="org:admin",
            praviar_role=None,
            updated_at=1_790_000_000_000,
        )
    else:
        payload = _membership_payload(
            role="org:admin",
            praviar_role="admin",
            updated_at=1_790_000_000_000,
        )

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            payload,
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.membership_permission_denied_at is None
    assert current.membership_permission_denied_by_operation_id is None
    assert current.membership_permission_convergence_operation_id is None
    assert current.role == (UserRole.CLIENT if recovery == "requested_member" else UserRole.ADMIN)
    assert current.clerk_membership_role == (
        "member" if recovery == "requested_member" else "admin"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_clock_offset_seconds", [-30, -1])
async def test_partial_demotion_exact_correlation_ignores_app_and_db_clock_order(
    mock_db,
    operation_clock_offset_seconds: int,
):
    org = MagicMock(id=uuid.uuid4())
    denied_at = datetime.fromtimestamp(1_789_000_000, tz=UTC)
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=denied_at,
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=denied_at,
    )
    exact_operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    exact_operation.updated_at = datetime.fromtimestamp(
        1_789_000_000 + operation_clock_offset_seconds,
        tz=UTC,
    )
    historical_operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    historical_operation.updated_at = datetime.fromtimestamp(1_789_100_000, tz=UTC)
    current.membership_permission_convergence_operation_id = exact_operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(exact_operation),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                role="org:admin",
                praviar_role="client",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.CLIENT
    assert current.membership_permission_denied_at == denied_at
    assert current.membership_permission_convergence_operation_id == exact_operation.id
    convergence_query = str(mock_db.execute.await_args_list[3].args[0])
    assert "WHERE clerk_admin_operations.id =" in convergence_query
    assert "ORDER BY" not in convergence_query
    assert historical_operation.id != exact_operation.id


@pytest.mark.asyncio
@pytest.mark.parametrize("reference_failure", ["missing", "wrong_target"])
async def test_partial_demotion_invalid_exact_reference_remains_fail_closed(
    mock_db,
    reference_failure: str,
):
    org = MagicMock(id=uuid.uuid4())
    denied_at = datetime.fromtimestamp(1_789_000_000, tz=UTC)
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=denied_at,
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=denied_at,
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    current.membership_permission_convergence_operation_id = operation.id
    if reference_failure == "missing":
        referenced_operation = None
    else:
        operation.target_user_id = uuid.uuid4()
        referenced_operation = operation
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(referenced_operation),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                role="org:admin",
                praviar_role="client",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.CLIENT
    assert current.membership_permission_denied_at == denied_at
    assert current.membership_permission_convergence_operation_id == operation.id


@pytest.mark.asyncio
async def test_bootstrap_conflicting_partial_demotion_echo_cannot_restore_admin(mock_db):
    org = MagicMock(id=uuid.uuid4())
    denied_at = datetime.fromtimestamp(1_789_000_000, tz=UTC)
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=denied_at,
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=denied_at,
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    current.membership_permission_convergence_operation_id = operation.id
    membership = _membership_payload(
        role="org:admin",
        praviar_role="client",
        updated_at=1_790_000_000_000,
    )
    responses = [httpx.Response(200, json={"total_count": 1, "data": [membership]})]
    calls: list[dict] = []
    mock_db.execute.side_effect = [
        _scalar(org),
        _first(current),
        _scalar(None),
        _rows([current]),
        _scalar(operation),
        _first(current),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="admin",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=AsyncMock(),
            http_client_cls=_bootstrap_client_factory(responses, calls),
        )

    assert result == {"status": "updated"}
    assert current.role == UserRole.CLIENT
    assert current.membership_permission_denied_at == denied_at
    assert current.membership_permission_convergence_operation_id == operation.id
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_membership_delete_clears_terminal_convergence_reference(mock_db):
    org = MagicMock(id=uuid.uuid4())
    denied_at = datetime.fromtimestamp(1_789_000_000, tz=UTC)
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=denied_at,
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=denied_at,
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    current.membership_permission_convergence_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _scalar(current),
        _scalar(None),
    ]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(user_id=None, updated_at=1_790_000_000_000),
            event_type=MEMBERSHIP_DELETED,
        )

    assert result == {"status": "deleted"}
    assert current.membership_active is False
    assert current.membership_permission_denied_at > denied_at
    assert current.membership_permission_denied_by_operation_id is None
    assert current.membership_permission_convergence_operation_id is None


def test_user_denial_constraints_require_deny_and_exclusive_operation_references():
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in User.__table__.constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }

    assert (
        "membership_permission_denied_at IS NOT NULL"
        in constraints["ck_users_membership_permission_denial_convergence"]
    )
    exclusive = constraints["ck_users_membership_permission_denial_reference_exclusive"]
    assert "membership_permission_denied_by_operation_id IS NULL" in exclusive
    assert "membership_permission_convergence_operation_id IS NULL" in exclusive
    assert (
        "membership_deleted_at IS NULL OR NOT membership_active"
        in constraints["ck_users_deleted_membership_inactive"]
    )


@pytest.mark.asyncio
async def test_future_membership_snapshot_is_rejected_against_locked_database_clock(mock_db):
    org = MagicMock(id=uuid.uuid4())
    mock_db.scalar.return_value = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([])]

    with (
        patch("api.services.clerk_webhooks.bind_current_org_to_session", new=AsyncMock()),
        pytest.raises(APIError, match="future-dated membership snapshot"),
    ):
        await handle_membership_event(
            mock_db,
            _membership_payload(updated_at=1_800_000_000_000),
            event_type=MEMBERSHIP_UPDATED,
        )

    mock_db.add.assert_not_called()
    assert "clock_timestamp" in str(mock_db.scalar.await_args.args[0]).lower()


@pytest.mark.asyncio
async def test_equal_timestamp_demotion_deactivates_instead_of_preserving_admin(mock_db):
    org = MagicMock(id=uuid.uuid4())
    provider_time = datetime.fromtimestamp(1_790_000_000, tz=UTC)
    database_now = datetime(2100, 1, 1, tzinfo=UTC)
    mock_db.scalar.return_value = database_now
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.ADMIN,
        membership_active=True,
        membership_updated_at=provider_time,
    )
    mock_db.execute.side_effect = [_scalar(org), _scalar(None), _rows([current])]

    with patch("api.services.clerk_webhooks.bind_current_org_to_session", new=AsyncMock()):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                role="org:member",
                praviar_role="client",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "deactivated_timestamp_collision"}
    assert current.membership_active is False
    assert current.role == UserRole.CLIENT
    assert current.membership_permission_denied_at == database_now


@pytest.mark.asyncio
async def test_exact_partial_convergence_is_allowed_at_same_provider_millisecond(mock_db):
    org = MagicMock(id=uuid.uuid4())
    provider_time = datetime.fromtimestamp(1_790_000_000, tz=UTC)
    current = User(
        id=uuid.uuid4(),
        clerk_user_id="user_123",
        clerk_membership_id="mem_123",
        clerk_membership_role="admin",
        org_id=org.id,
        email="admin@praviar.io",
        role=UserRole.CLIENT,
        membership_active=True,
        membership_permission_denied_at=provider_time,
        membership_updated_at=provider_time,
    )
    operation = _partial_demotion_operation(org_id=org.id, user_id=current.id)
    operation.provider_updated_at = provider_time
    current.membership_permission_convergence_operation_id = operation.id
    mock_db.execute.side_effect = [
        _scalar(org),
        _scalar(None),
        _rows([current]),
        _scalar(operation),
    ]

    with patch("api.services.clerk_webhooks.bind_current_org_to_session", new=AsyncMock()):
        result = await handle_membership_event(
            mock_db,
            _membership_payload(
                role="org:member",
                praviar_role="client",
                updated_at=1_790_000_000_000,
            ),
            event_type=MEMBERSHIP_UPDATED,
        )

    assert result == {"status": "updated"}
    assert current.membership_active is True
    assert current.clerk_membership_role == "member"
    assert current.membership_permission_denied_at is None
    assert current.membership_permission_convergence_operation_id is None


@pytest.mark.parametrize(
    "error_code",
    [
        "clerk_role_rejected_after_metadata_",
        "clerk_role_rejected_after_metadata_nope",
        "clerk_role_rejected_after_metadata_422_trailing",
        "clerk_role_rejected_after_metadata_429",
        "clerk_role_rejected_after_metadata_500",
        "clerk_role_rejected_after_metadata_999",
    ],
)
def test_partial_failure_requires_full_nonretryable_4xx_suffix(error_code: str):
    operation = _partial_demotion_operation(org_id=uuid.uuid4(), user_id=uuid.uuid4())
    operation.last_error_code = error_code

    assert not _is_exact_partial_role_failure(
        operation,
        operation_id=operation.id,
        org_id=operation.org_id,
        user_id=operation.target_user_id,
    )


@pytest.mark.asyncio
async def test_handle_org_created_never_grants_a_user_role(mock_db):
    mock_db.execute.return_value = _scalar(None)
    result = await handle_org_created(
        mock_db,
        {"id": "org_123", "name": "Example", "slug": "example"},
    )

    assert result == {"status": "ok"}
    added = mock_db.add.call_args.args[0]
    assert isinstance(added, Organization)
    assert not isinstance(added, User)


@pytest.mark.asyncio
async def test_bootstrap_uses_exact_versioned_token_bound_clerk_lookup(mock_db):
    membership = _membership_payload()
    calls: list[dict] = []
    responses = [httpx.Response(200, json={"total_count": 1, "data": [membership]})]
    upsert = AsyncMock(return_value={"status": "created"})
    audit = AsyncMock()

    with patch("api.services.clerk_webhooks.handle_membership_event", new=upsert):
        result = await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=audit,
            http_client_cls=_bootstrap_client_factory(responses, calls),
        )

    assert result == {"status": "created"}
    assert calls == [
        {
            "url": "https://api.clerk.com/v1/organizations/org_123/memberships",
            "headers": {
                "Authorization": "Bearer sk_live_test",
                "Accept": "application/json",
                "Clerk-API-Version": "2026-05-12",
            },
            "params": {"user_id": "user_123", "limit": 2, "offset": 0},
        }
    ]
    upsert.assert_awaited_once_with(
        mock_db,
        membership,
        event_type=MEMBERSHIP_UPDATED,
        source="clerk_bootstrap",
        write_audit_log_fn=audit,
    )


@pytest.mark.asyncio
async def test_bootstrap_enters_same_org_first_lock_order_before_local_upsert(mock_db):
    membership = _membership_payload()
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [
        _scalar(org),
        _first(None),
        _scalar(None),
        _rows([]),
        _first(None),
    ]
    responses = [httpx.Response(200, json={"total_count": 1, "data": [membership]})]

    with patch(
        "api.services.clerk_webhooks.bind_current_org_to_session",
        new=AsyncMock(),
    ):
        result = await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=AsyncMock(),
            http_client_cls=_bootstrap_client_factory(responses, []),
        )

    assert result == {"status": "created"}
    statements = [str(call.args[0]) for call in mock_db.execute.await_args_list]
    assert "organizations" in statements[0]
    assert "FOR UPDATE" in statements[0]
    assert "users" in statements[1]
    assert "FOR UPDATE" in statements[1]
    assert "clerk_membership_tombstones" in statements[2]
    assert "users" in statements[3]


@pytest.mark.asyncio
async def test_bootstrap_audit_failure_rolls_back_principal_and_denies_auth(mock_db):
    membership = _membership_payload()
    org = MagicMock(id=uuid.uuid4())
    mock_db.execute.side_effect = [
        _scalar(org),
        _first(None),
        _scalar(None),
        _rows([]),
        _first(None),
    ]
    responses = [httpx.Response(200, json={"total_count": 1, "data": [membership]})]
    audit = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    with (
        patch("api.services.clerk_webhooks.bind_current_org_to_session", new=AsyncMock()),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=audit,
            http_client_cls=_bootstrap_client_factory(responses, []),
        )

    audit.assert_awaited_once()
    details = audit.await_args.kwargs["details"]
    assert details["source"] == "clerk_bootstrap"
    assert audit.await_args.kwargs["fail_closed"] is True
    mock_db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_zero_membership_fails_403_without_local_fallback(mock_db):
    responses = [httpx.Response(200, json={"total_count": 0, "data": []})]

    with pytest.raises(APIError) as exc_info:
        await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=AsyncMock(),
            http_client_cls=_bootstrap_client_factory(responses, []),
        )

    assert exc_info.value.status == 403
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_provider_role_mismatch_fails_409_as_stale_auth_context(mock_db):
    membership = _membership_payload(role="org:admin")
    responses = [httpx.Response(200, json={"total_count": 1, "data": [membership]})]

    with pytest.raises(APIError) as exc_info:
        await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=AsyncMock(),
            http_client_cls=_bootstrap_client_factory(responses, []),
        )

    assert exc_info.value.status == 409
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_retries_429_with_retry_after_inside_bounded_budget(mock_db):
    membership = _membership_payload()
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"total_count": 1, "data": [membership]}),
    ]
    calls: list[dict] = []
    upsert = AsyncMock(return_value={"status": "created"})

    with patch("api.services.clerk_webhooks.handle_membership_event", new=upsert):
        await bootstrap_clerk_membership(
            mock_db,
            clerk_user_id="user_123",
            clerk_org_id="org_123",
            token_org_role="member",
            settings=SimpleNamespace(clerk_secret_key="sk_live_test"),
            write_audit_log_fn=AsyncMock(),
            http_client_cls=_bootstrap_client_factory(responses, calls),
        )

    assert len(calls) == 2
