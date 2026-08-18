from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from api.db.models import ClerkAdminOperation, UserRole
from api.errors import APIError
from api.schemas.admin import InviteRequest
from api.services.admin_users import (
    _admin_operation_digests,
    _begin_partial_role_recovery,
    _claim_admin_operation,
    _invite_user_in_prod,
    _transition_role_operation,
    _update_user_role_in_clerk,
    list_admin_operations_impl,
    reconcile_admin_operation_impl,
)


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _count(value: int):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _rows(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _operation(
    *,
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    request_hash: str,
    key_digest: str,
) -> ClerkAdminOperation:
    return ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=uuid.uuid4(),
        operation_type="role_update",
        client_key_digest=key_digest,
        request_hash=request_hash,
        state="metadata_call_started",
        target_user_id=target_user_id,
        requested_role="attorney",
    )


@pytest.mark.asyncio
async def test_partial_role_recovery_reopens_only_exact_correlated_rejected_step(monkeypatch):
    db = AsyncMock()
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    operation = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash="a" * 64,
        key_digest="b" * 64,
    )
    operation.state = "failed"
    operation.requested_role = "attorney"
    operation.last_error_code = "clerk_role_rejected_after_metadata_422"
    target = SimpleNamespace(
        id=target_id,
        org_id=org_id,
        role=UserRole.ATTORNEY,
        membership_active=True,
        membership_permission_denied_at=datetime.now(UTC),
        membership_permission_denied_by_operation_id=None,
        membership_permission_convergence_operation_id=operation.id,
    )
    lock_order: list[str] = []

    async def _lock_org(*_args, **_kwargs):
        lock_order.append("org")
        return SimpleNamespace(id=org_id)

    async def _load_target(*_args, **_kwargs):
        lock_order.append("user")
        return target

    async def _load_operation(*_args, **_kwargs):
        lock_order.append("operation")
        return operation

    monkeypatch.setattr("api.services.admin_users._lock_org", _lock_org)
    monkeypatch.setattr("api.services.admin_users._load_target_user", _load_target)
    monkeypatch.setattr(
        "api.services.admin_users._load_admin_operation_by_id",
        _load_operation,
    )
    audit = AsyncMock()

    recovered = await _begin_partial_role_recovery(
        db,
        org_id=org_id,
        admin_id=uuid.uuid4(),
        operation_id=operation.id,
        target_user_id=target_id,
        write_audit_log_fn=audit,
    )

    assert recovered is operation
    assert lock_order == ["org", "user", "operation"]
    assert operation.state == "metadata_accepted"
    assert operation.last_error_code is None
    assert target.membership_permission_denied_at is not None
    assert target.membership_permission_denied_by_operation_id == operation.id
    assert target.membership_permission_convergence_operation_id is None
    assert audit.await_args.kwargs["fail_closed"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_role_recovery_rejects_malformed_suffix_without_state_transfer(monkeypatch):
    db = AsyncMock()
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    operation = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash="c" * 64,
        key_digest="d" * 64,
    )
    operation.state = "failed"
    operation.last_error_code = "clerk_role_rejected_after_metadata_422_trailing"
    target = SimpleNamespace(
        id=target_id,
        org_id=org_id,
        role=UserRole.ATTORNEY,
        membership_active=True,
        membership_permission_denied_at=datetime.now(UTC),
        membership_permission_denied_by_operation_id=None,
        membership_permission_convergence_operation_id=operation.id,
    )
    monkeypatch.setattr(
        "api.services.admin_users._lock_org",
        AsyncMock(return_value=SimpleNamespace(id=org_id)),
    )
    monkeypatch.setattr(
        "api.services.admin_users._load_target_user",
        AsyncMock(return_value=target),
    )
    monkeypatch.setattr(
        "api.services.admin_users._load_admin_operation_by_id",
        AsyncMock(return_value=operation),
    )

    with pytest.raises(APIError, match="authority changed"):
        await _begin_partial_role_recovery(
            db,
            org_id=org_id,
            admin_id=uuid.uuid4(),
            operation_id=operation.id,
            target_user_id=target_id,
            write_audit_log_fn=AsyncMock(),
        )

    assert operation.state == "failed"
    assert target.membership_permission_convergence_operation_id == operation.id
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_offset", [-1, 301])
async def test_role_provider_timestamp_must_clear_locked_watermark_and_future_ceiling(
    monkeypatch,
    provider_offset: int,
):
    db = AsyncMock()
    database_now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    db.scalar.return_value = database_now
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    operation = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash="e" * 64,
        key_digest="f" * 64,
    )
    operation.state = "role_call_started"
    target = SimpleNamespace(membership_updated_at=database_now)
    monkeypatch.setattr(
        "api.services.admin_users._lock_role_operation_snapshot",
        AsyncMock(return_value=(SimpleNamespace(id=org_id), target, operation)),
    )
    provider_updated_at = database_now + timedelta(seconds=provider_offset)

    with pytest.raises(APIError, match="stale|future-dated"):
        await _transition_role_operation(
            db,
            snapshot=MagicMock(),
            expected_states=frozenset({"role_call_started"}),
            new_state="role_accepted",
            provider_updated_at=provider_updated_at,
        )

    assert operation.state == "role_call_started"
    db.commit.assert_not_awaited()
    assert "clock_timestamp" in str(db.scalar.await_args.args[0]).lower()


@pytest.mark.asyncio
async def test_new_key_same_canonical_target_reuses_unresolved_operation():
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    settings = SimpleNamespace(api_key_hmac_secret="hmac-private")
    payload = {
        "operation_type": "role_update",
        "target_user_id": str(target_id),
        "requested_role": "attorney",
    }
    _, request_hash = _admin_operation_digests(
        settings=settings,
        org_id=org_id,
        idempotency_key="first-client-key-123",
        request_payload=payload,
    )
    existing = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash=request_hash,
        key_digest="a" * 64,
    )
    db.execute.side_effect = [
        _scalar(SimpleNamespace(id=org_id)),
        _scalar(None),
        _scalar(existing),
    ]

    operation, created = await _claim_admin_operation(
        db,
        settings=settings,
        org_id=org_id,
        admin_id=uuid.uuid4(),
        operation_type="role_update",
        idempotency_key="second-client-key-456",
        request_payload=payload,
        target_user_id=target_id,
        target_email_normalized=None,
        requested_role="attorney",
        write_audit_log_fn=AsyncMock(),
        requested_action="admin.user_role.update_requested",
        requested_details={},
    )

    assert operation is existing
    assert created is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_new_key_different_role_is_blocked_while_target_unresolved():
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    settings = SimpleNamespace(api_key_hmac_secret="hmac-private")
    old_payload = {
        "operation_type": "role_update",
        "target_user_id": str(target_id),
        "requested_role": "attorney",
    }
    _, old_hash = _admin_operation_digests(
        settings=settings,
        org_id=org_id,
        idempotency_key="first-client-key-123",
        request_payload=old_payload,
    )
    existing = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash=old_hash,
        key_digest="a" * 64,
    )
    db.execute.side_effect = [
        _scalar(SimpleNamespace(id=org_id)),
        _scalar(None),
        _scalar(existing),
    ]

    with pytest.raises(APIError, match="requires reconciliation") as exc:
        await _claim_admin_operation(
            db,
            settings=settings,
            org_id=org_id,
            admin_id=uuid.uuid4(),
            operation_type="role_update",
            idempotency_key="second-client-key-456",
            request_payload={**old_payload, "requested_role": "client"},
            target_user_id=target_id,
            target_email_normalized=None,
            requested_role="client",
            write_audit_log_fn=AsyncMock(),
            requested_action="admin.user_role.update_requested",
            requested_details={},
        )

    assert exc.value.status == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_same_key_different_body_is_rejected_before_scope_or_provider_work():
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()
    target_id = uuid.uuid4()
    settings = SimpleNamespace(api_key_hmac_secret="hmac-private")
    key = "same-client-key-12345"
    old_payload = {
        "operation_type": "role_update",
        "target_user_id": str(target_id),
        "requested_role": "attorney",
    }
    key_digest, old_hash = _admin_operation_digests(
        settings=settings,
        org_id=org_id,
        idempotency_key=key,
        request_payload=old_payload,
    )
    existing = _operation(
        org_id=org_id,
        target_user_id=target_id,
        request_hash=old_hash,
        key_digest=key_digest,
    )
    db.execute.side_effect = [
        _scalar(SimpleNamespace(id=org_id)),
        _scalar(existing),
    ]

    with pytest.raises(APIError, match="different admin request") as exc:
        await _claim_admin_operation(
            db,
            settings=settings,
            org_id=org_id,
            admin_id=uuid.uuid4(),
            operation_type="role_update",
            idempotency_key=key,
            request_payload={**old_payload, "requested_role": "client"},
            target_user_id=target_id,
            target_email_normalized=None,
            requested_role="client",
            write_audit_log_fn=AsyncMock(),
            requested_action="admin.user_role.update_requested",
            requested_details={},
        )

    assert exc.value.status == 409
    assert db.execute.await_count == 2
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_new_key_same_invite_email_reuses_unresolved_invitation():
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()
    settings = SimpleNamespace(api_key_hmac_secret="hmac-private")
    payload = {
        "operation_type": "invite",
        "email": "buyer@example.com",
        "requested_role": "client",
    }
    _, request_hash = _admin_operation_digests(
        settings=settings,
        org_id=org_id,
        idempotency_key="first-invite-key-123",
        request_payload=payload,
    )
    existing = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=uuid.uuid4(),
        operation_type="invite",
        client_key_digest="c" * 64,
        request_hash=request_hash,
        state="invite_call_started",
        target_email_normalized="buyer@example.com",
        requested_role="client",
    )
    db.execute.side_effect = [
        _scalar(SimpleNamespace(id=org_id)),
        _scalar(None),
        _scalar(existing),
    ]

    operation, created = await _claim_admin_operation(
        db,
        settings=settings,
        org_id=org_id,
        admin_id=uuid.uuid4(),
        operation_type="invite",
        idempotency_key="second-invite-key-456",  # gitleaks:allow
        request_payload=payload,
        target_user_id=None,
        target_email_normalized="buyer@example.com",
        requested_role="client",
        write_audit_log_fn=AsyncMock(),
        requested_action="admin.user_invite.requested",
        requested_details={},
    )

    assert operation is existing
    assert created is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_requested_invite_reconcile_reloads_authoritative_inviter_before_post(
    monkeypatch,
):
    db = AsyncMock()
    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    settings = SimpleNamespace(
        app_env="prod",
        clerk_secret_key="sk_live",
        api_key_hmac_secret="hmac-private",
    )
    operation = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=admin_id,
        operation_type="invite",
        client_key_digest="a" * 64,
        request_hash="b" * 64,
        state="requested",
        target_email_normalized="buyer@example.com",
        requested_role="client",
    )
    db.execute.return_value = _scalar(operation)
    org = SimpleNamespace(id=org_id, clerk_org_id="org_authoritative")
    inviter = SimpleNamespace(
        id=admin_id,
        clerk_user_id="user_authoritative_admin",
    )
    lock_org = AsyncMock(return_value=org)
    load_authority = AsyncMock(return_value=(org, inviter))

    async def _invite(**kwargs):
        assert kwargs["clerk_org_id"] == "org_authoritative"
        assert kwargs["inviter_clerk_user_id"] == "user_authoritative_admin"
        operation.state = "provider_accepted"
        operation.provider_resource_id = "orginv_exact"
        return "orginv_exact"

    monkeypatch.setattr("api.services.admin_users._lock_org", lock_org)
    monkeypatch.setattr("api.services.admin_users._load_clerk_invite_authority", load_authority)
    monkeypatch.setattr("api.services.admin_users._invite_user_in_prod", _invite)

    async def _lock_invite_snapshot(_db, **_kwargs):
        return org, inviter, operation

    monkeypatch.setattr(
        "api.services.admin_users._lock_invite_operation_snapshot",
        _lock_invite_snapshot,
    )
    audit = AsyncMock()

    status = await reconcile_admin_operation_impl(
        db,
        org_id=org_id,
        admin_id=admin_id,
        operation_id=operation.id,
        settings=settings,
        http_client_cls=MagicMock(),
        write_audit_log_fn=audit,
    )

    assert status["state"] == "completed"
    load_authority.assert_awaited_once_with(
        db,
        org_id=org_id,
        admin_id=admin_id,
        for_update=True,
    )
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_operation_listing_prioritizes_older_open_work_over_100_newer_terminals():
    db = AsyncMock()
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    open_operation = _operation(
        org_id=org_id,
        target_user_id=uuid.uuid4(),
        request_hash="a" * 64,
        key_digest="b" * 64,
    )
    open_operation.updated_at = now - timedelta(days=7)
    terminals = []
    for index in range(100):
        terminal = _operation(
            org_id=org_id,
            target_user_id=uuid.uuid4(),
            request_hash=f"{index:064x}",
            key_digest=f"{index + 100:064x}",
        )
        terminal.state = "completed"
        terminal.updated_at = now - timedelta(seconds=index)
        terminals.append(terminal)
    db.execute.side_effect = [_count(1), _rows([open_operation, *terminals])]

    result = await list_admin_operations_impl(db, org_id=org_id, limit=100)

    assert result["open_total"] == 1
    assert result["has_more"] is True
    assert result["items"][0]["operation_id"] == open_operation.id
    listing_sql = str(db.execute.await_args_list[1].args[0])
    assert "CASE WHEN" in listing_sql
    assert "LIMIT" in listing_sql


@pytest.mark.asyncio
async def test_terminal_role_failure_releases_global_open_operation_lock():
    db = AsyncMock()
    org_id = uuid.uuid4()
    operation = _operation(
        org_id=org_id,
        target_user_id=uuid.uuid4(),
        request_hash="9" * 64,
        key_digest="8" * 64,
    )
    operation.state = "failed"
    operation.last_error_code = "membership_deleted"
    operation.updated_at = datetime.now(UTC)
    db.execute.side_effect = [_count(0), _rows([operation])]

    result = await list_admin_operations_impl(db, org_id=org_id, limit=50)

    assert result["open_total"] == 0
    assert result["items"][0]["state"] == "failed"
    assert result["items"][0]["reconciliation_required"] is False


@pytest.mark.asyncio
async def test_role_provider_io_runs_only_after_canonical_locks_are_released(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = datetime(2100, 1, 1, tzinfo=UTC)
    lock_state = {"held": False}
    org_id = uuid.uuid4()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        clerk_user_id="user_target",
        clerk_membership_id="mem_target",
        clerk_membership_role="member",
        membership_active=True,
        membership_permission_denied_at=datetime.now(UTC),
        membership_permission_denied_by_operation_id=None,
        membership_updated_at=datetime.fromtimestamp(1_788_000_000, tz=UTC),
        role=UserRole.SCIENTIST,
    )
    org = SimpleNamespace(id=org_id, clerk_org_id="org_exact")
    operation = _operation(
        org_id=org_id,
        target_user_id=user.id,
        request_hash="c" * 64,
        key_digest="d" * 64,
    )
    operation.state = "requested"
    operation.requested_role = "attorney"
    user.membership_permission_denied_by_operation_id = operation.id

    async def _lock_org(_db, *, org_id):
        assert org_id == org.id
        assert lock_state["held"] is False
        lock_state["held"] = True
        return org

    async def _load_target(_db, *, user_id, for_update):
        assert lock_state["held"] is True
        assert user_id == user.id and for_update is True
        return user

    async def _load_operation(_db, *, operation_id, for_update):
        assert lock_state["held"] is True
        assert operation_id == operation.id and for_update is True
        return operation

    async def _commit():
        lock_state["held"] = False

    async def _direct_breaker_call(fn):
        return await fn()

    db.commit.side_effect = _commit
    monkeypatch.setattr("api.services.admin_users._lock_org", _lock_org)
    monkeypatch.setattr("api.services.admin_users._load_target_user", _load_target)
    monkeypatch.setattr("api.services.admin_users._load_admin_operation_by_id", _load_operation)
    monkeypatch.setattr("api.circuit_breaker.clerk_breaker.call", _direct_breaker_call)

    def _membership(metadata):
        return httpx.Response(
            200,
            json={
                "id": user.clerk_membership_id,
                "organization": {"id": org.clerk_org_id},
                "public_user_data": {"user_id": user.clerk_user_id},
                "role": "org:member",
                "public_metadata": metadata,
                "updated_at": 1_790_000_000_000,
            },
        )

    client = AsyncMock()

    async def _get(*_args, **_kwargs):
        assert lock_state["held"] is False
        return _membership({"praviar_role_version": 1, "praviar_role": "scientist"})

    async def _patch(*_args, **_kwargs):
        assert lock_state["held"] is False
        return _membership({"praviar_role_version": 1, "praviar_role": "attorney"})

    client.get.side_effect = _get
    client.patch.side_effect = _patch
    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client
    client_cm.__aexit__.return_value = False

    await _update_user_role_in_clerk(
        target_user=user,
        org=org,
        new_role=UserRole.ATTORNEY,
        settings=SimpleNamespace(clerk_secret_key="sk_live"),
        http_client_cls=MagicMock(return_value=client_cm),
        db=db,
        operation=operation,
    )

    assert operation.state == "metadata_accepted"
    assert lock_state["held"] is False
    client.get.assert_awaited_once()
    client.patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_paginated_invite_reconciliation_never_reads_clerk_under_locks(monkeypatch):
    db = AsyncMock()
    lock_state = {"held": False}
    org_id = uuid.uuid4()
    inviter = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        clerk_user_id="user_admin",
        membership_active=True,
        membership_permission_denied_at=None,
        clerk_membership_role="admin",
        role=UserRole.ADMIN,
    )
    org = SimpleNamespace(id=org_id, clerk_org_id="org_exact")
    operation = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=inviter.id,
        operation_type="invite",
        client_key_digest="e" * 64,
        request_hash="f" * 64,
        state="invite_call_started",
        target_email_normalized="buyer@example.com",
        requested_role="client",
    )

    async def _lock_org(_db, *, org_id):
        assert org_id == org.id
        assert lock_state["held"] is False
        lock_state["held"] = True
        return org

    async def _load_target(_db, *, user_id, for_update):
        assert lock_state["held"] is True
        assert user_id == inviter.id and for_update is True
        return inviter

    async def _load_operation(_db, *, operation_id, for_update):
        assert lock_state["held"] is True
        assert operation_id == operation.id and for_update is True
        return operation

    async def _commit():
        lock_state["held"] = False

    async def _direct_breaker_call(fn):
        return await fn()

    db.commit.side_effect = _commit
    monkeypatch.setattr("api.services.admin_users._lock_org", _lock_org)
    monkeypatch.setattr("api.services.admin_users._load_target_user", _load_target)
    monkeypatch.setattr("api.services.admin_users._load_admin_operation_by_id", _load_operation)
    monkeypatch.setattr("api.circuit_breaker.clerk_breaker.call", _direct_breaker_call)

    client = AsyncMock()

    async def _get(*_args, **_kwargs):
        assert lock_state["held"] is False
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "orginv_exact",
                        "organization_id": org.clerk_org_id,
                        "email_address": "buyer@example.com",
                        "role": "org:member",
                        "status": "pending",
                        "public_metadata": {
                            "praviar_role_version": 1,
                            "praviar_role": "client",
                            "praviar_invitation_operation_id": str(operation.id),
                        },
                    }
                ],
                "total_count": 1,
            },
        )

    client.get.side_effect = _get
    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client
    client_cm.__aexit__.return_value = False

    invitation_id = await _invite_user_in_prod(
        body=InviteRequest(email="buyer@example.com", role="client"),
        clerk_org_id=org.clerk_org_id,
        inviter_user_id=inviter.id,
        inviter_clerk_user_id=inviter.clerk_user_id,
        settings=SimpleNamespace(clerk_secret_key="sk_live"),
        http_client_cls=MagicMock(return_value=client_cm),
        db=db,
        operation=operation,
    )

    assert invitation_id == "orginv_exact"
    assert operation.state == "provider_accepted"
    assert lock_state["held"] is False
    client.post.assert_not_awaited()


def test_admin_operation_digests_fail_closed_without_dedicated_hmac_secret():
    with pytest.raises(APIError, match="privacy HMAC is not configured") as exc:
        _admin_operation_digests(
            settings=SimpleNamespace(clerk_secret_key="must-not-be-used"),
            org_id=uuid.uuid4(),
            idempotency_key="admin-operation-key-123",
            request_payload={"operation_type": "invite"},
        )

    assert exc.value.status == 503
