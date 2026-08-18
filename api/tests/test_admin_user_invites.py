from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from conftest import make_mock_db

from api.db.models import ClerkAdminOperation, UserRole
from api.errors import APIError
from api.schemas.admin import InviteRequest
from api.services.admin_users import _invite_user_in_prod, invite_user_to_org_impl


@pytest.fixture(autouse=True)
def _stable_durable_operation_claim(monkeypatch):
    operations: dict[uuid.UUID, ClerkAdminOperation] = {}

    async def _claim(db, **kwargs):
        operation = ClerkAdminOperation(
            id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
            org_id=kwargs["org_id"],
            initiated_by=kwargs["admin_id"],
            operation_type=kwargs["operation_type"],
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="requested",
            target_email_normalized=kwargs["target_email_normalized"],
            requested_role=kwargs["requested_role"],
        )
        operations[operation.id] = operation
        try:
            await kwargs["write_audit_log_fn"](
                db,
                org_id=kwargs["org_id"],
                user_id=kwargs["admin_id"],
                action=kwargs["requested_action"],
                details={"operation_id": str(operation.id), **kwargs["requested_details"]},
                fail_closed=True,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return operation, True

    async def _direct_breaker_call(fn):
        return await fn()

    async def _load_operation(_db, *, operation_id, for_update):
        del for_update
        return operations[operation_id]

    async def _transition_invite(
        db,
        *,
        snapshot,
        new_state,
        provider_resource_id=None,
        **_kwargs,
    ):
        operation = operations.get(snapshot.operation_id)
        if operation is not None:
            operation.state = new_state
            if provider_resource_id is not None:
                operation.provider_resource_id = provider_resource_id
        await db.commit()
        return operation

    async def _verify_invite(db, **_kwargs):
        await db.commit()

    async def _lock_invite(_db, *, snapshot, **_kwargs):
        operation = operations[snapshot.operation_id]
        return (
            SimpleNamespace(id=snapshot.org_id, clerk_org_id=snapshot.clerk_org_id),
            SimpleNamespace(
                id=snapshot.inviter_user_id,
                org_id=snapshot.org_id,
                clerk_user_id=snapshot.inviter_clerk_user_id,
                membership_active=True,
                membership_permission_denied_at=None,
                clerk_membership_role="admin",
                role=UserRole.ADMIN,
            ),
            operation,
        )

    monkeypatch.setattr("api.services.admin_users._claim_admin_operation", _claim)
    monkeypatch.setattr("api.circuit_breaker.clerk_breaker.call", _direct_breaker_call)
    monkeypatch.setattr("api.services.admin_users._load_admin_operation_by_id", _load_operation)
    monkeypatch.setattr("api.services.admin_users._transition_invite_operation", _transition_invite)
    monkeypatch.setattr(
        "api.services.admin_users._verify_invite_operation_before_provider_read",
        _verify_invite,
    )
    monkeypatch.setattr("api.services.admin_users._lock_invite_operation_snapshot", _lock_invite)
    return operations


class TestAdminUserInvites:
    @staticmethod
    def _durable_invite_operation(org_id: uuid.UUID) -> ClerkAdminOperation:
        return ClerkAdminOperation(
            id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
            org_id=org_id,
            initiated_by=uuid.uuid4(),
            operation_type="invite",
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="invite_call_started",
            target_email_normalized="buyer@example.com",
            requested_role="client",
        )

    @pytest.mark.asyncio
    async def test_invite_reconciliation_paginates_and_ignores_identical_unmarked_invite(self):
        db = make_mock_db()
        operation = self._durable_invite_operation(uuid.uuid4())
        unmarked = {
            "id": "old_invite",
            "organization_id": "org_123",
            "email_address": "buyer@example.com",
            "role": "org:member",
            "status": "pending",
            "public_metadata": {
                "praviar_role_version": 1,
                "praviar_role": "client",
            },
        }
        filler = [
            {**unmarked, "id": f"old_{index}", "email_address": f"old{index}@example.com"}
            for index in range(99)
        ]
        marked = {
            **unmarked,
            "id": "exact_invite",
            "status": "accepted",
            "public_metadata": {
                **unmarked["public_metadata"],
                "praviar_invitation_operation_id": str(operation.id),
            },
        }
        client = AsyncMock()
        client.get.side_effect = [
            httpx.Response(200, json={"data": [unmarked, *filler], "total_count": 101}),
            httpx.Response(200, json={"data": [marked], "total_count": 101}),
        ]
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        invitation_id = await _invite_user_in_prod(
            body=InviteRequest(email="buyer@example.com", role="client"),
            clerk_org_id="org_123",
            inviter_clerk_user_id="admin_123",
            settings=SimpleNamespace(clerk_secret_key="sk_live"),
            http_client_cls=MagicMock(return_value=client_cm),
            db=db,
            operation=operation,
        )

        assert invitation_id == "exact_invite"
        assert client.get.await_count == 2
        client.post.assert_not_awaited()
        assert operation.state == "provider_accepted"

    @pytest.mark.asyncio
    async def test_invite_reconciliation_finds_fast_accepted_membership_by_marker(self):
        db = make_mock_db()
        operation = self._durable_invite_operation(uuid.uuid4())
        membership = {
            "id": "mem_accepted",
            "organization": {"id": "org_123"},
            "public_user_data": {
                "user_id": "buyer_123",
                "identifier": "buyer@example.com",
            },
            "role": "org:member",
            "public_metadata": {
                "praviar_role_version": 1,
                "praviar_role": "client",
                "praviar_invitation_operation_id": str(operation.id),
            },
        }
        client = AsyncMock()
        client.get.side_effect = [
            httpx.Response(200, json={"data": [], "total_count": 0}),
            httpx.Response(200, json={"data": [membership], "total_count": 1}),
        ]
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        invitation_id = await _invite_user_in_prod(
            body=InviteRequest(email="buyer@example.com", role="client"),
            clerk_org_id="org_123",
            inviter_clerk_user_id="admin_123",
            settings=SimpleNamespace(clerk_secret_key="sk_live"),
            http_client_cls=MagicMock(return_value=client_cm),
            db=db,
            operation=operation,
        )

        assert invitation_id == "mem_accepted"
        client.post.assert_not_awaited()
        assert operation.state == "provider_accepted"

    @pytest.mark.asyncio
    async def test_invite_application_log_uses_keyed_digest_not_raw_email(self):
        db = make_mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        settings = SimpleNamespace(
            app_env="dev",
            clerk_secret_key="sk_dev_private",
            api_key_hmac_secret="audit-hmac-private",
        )

        with patch("api.services.admin_users.logger.info") as info:
            await invite_user_to_org_impl(
                db,
                org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=InviteRequest(email="private.buyer@example.com", role="client"),
                settings=settings,
                http_client_cls=AsyncMock(),
                write_audit_log_fn=AsyncMock(),
                idempotency_key="invite-request-123",
            )

        call = info.call_args_list[-1]
        assert "private.buyer@example.com" not in repr(call)
        assert call.kwargs["email_digest"]
        assert "email" not in call.kwargs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["timeout", "503"])
    async def test_durable_invite_is_submitted_at_most_once(self, failure: str):
        db = make_mock_db()
        org_id = uuid.uuid4()
        operation = ClerkAdminOperation(
            id=uuid.uuid4(),
            org_id=org_id,
            initiated_by=uuid.uuid4(),
            operation_type="invite",
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="requested",
            target_email_normalized="buyer@example.com",
            requested_role="client",
        )
        client = AsyncMock()
        if failure == "timeout":
            client.post.side_effect = httpx.ReadTimeout("ambiguous")
        else:
            client.post.return_value = httpx.Response(503, json={"error": "busy"})
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        with pytest.raises(APIError, match="outcome is unknown"):
            await _invite_user_in_prod(
                body=InviteRequest(email="buyer@example.com", role="client"),
                clerk_org_id="org_123",
                inviter_clerk_user_id="user_admin",
                settings=SimpleNamespace(clerk_secret_key="sk_live"),
                http_client_cls=MagicMock(return_value=client_cm),
                db=db,
                operation=operation,
            )

        assert client.post.await_count == 1
        assert operation.state == "invite_call_started"

    @pytest.mark.asyncio
    async def test_known_clerk_rejection_is_terminal_and_releases_invite_scope(
        self,
        _stable_durable_operation_claim,
    ):
        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            clerk_user_id="user_admin",
        )
        db.execute.side_effect = [
            org_result,
            inviter_result,
            org_result,
            inviter_result,
            org_result,
        ]
        client = AsyncMock()
        client.post.return_value = httpx.Response(422, json={"error": "rejected"})
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        audit = AsyncMock()

        with pytest.raises(APIError, match="Clerk rejected the request"):
            await invite_user_to_org_impl(
                db,
                org_id=org_id,
                admin_id=admin_id,
                body=InviteRequest(email="buyer@example.com", role="client"),
                settings=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_live",
                    api_key_hmac_secret="test-private-hmac",
                ),
                http_client_cls=MagicMock(return_value=client_cm),
                write_audit_log_fn=audit,
                idempotency_key="known-rejection-key-123",
            )

        operation = next(iter(_stable_durable_operation_claim.values()))
        assert operation.state == "failed"
        assert operation.last_error_code == "clerk_422"
        assert client.post.await_count == 1
        assert [call.kwargs["action"] for call in audit.await_args_list] == [
            "admin.user_invite.requested",
            "admin.user_invite.failed",
        ]

    @pytest.mark.asyncio
    async def test_invite_user_to_org_impl_creates_local_user_in_dev(self):
        db = make_mock_db()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        audit_log = AsyncMock()

        await invite_user_to_org_impl(
            db,
            org_id=uuid.uuid4(),
            admin_id=uuid.uuid4(),
            body=InviteRequest(email="new.user@praviar.io", role="scientist"),
            settings=SimpleNamespace(
                app_env="dev",
                clerk_secret_key="sk_dev",
                api_key_hmac_secret="test-private-hmac",
            ),
            http_client_cls=AsyncMock(),
            write_audit_log_fn=audit_log,
            idempotency_key="invite-request-123",
        )

        created_user = db.add.call_args.args[0]
        assert created_user.email == "new.user@praviar.io"
        assert created_user.role == UserRole.SCIENTIST
        assert audit_log.await_count == 2
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_invite_user_to_org_impl_rolls_back_when_audit_fails(self):
        db = make_mock_db()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        audit_log = AsyncMock(side_effect=RuntimeError("audit unavailable"))

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await invite_user_to_org_impl(
                db,
                org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=InviteRequest(email="new.user@praviar.io", role="scientist"),
                settings=SimpleNamespace(
                    app_env="dev",
                    clerk_secret_key="sk_dev",
                    api_key_hmac_secret="test-private-hmac",
                ),
                http_client_cls=AsyncMock(),
                write_audit_log_fn=audit_log,
                idempotency_key="invite-request-123",
            )

        db.add.assert_not_called()
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invite_user_to_org_impl_rejects_duplicate_dev_user(self):
        db = make_mock_db()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = object()
        db.execute.return_value = existing_result

        with pytest.raises(APIError) as exc:
            await invite_user_to_org_impl(
                db,
                org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=InviteRequest(email="new.user@praviar.io", role="scientist"),
                settings=SimpleNamespace(
                    app_env="dev",
                    clerk_secret_key="sk_dev",
                    api_key_hmac_secret="test-private-hmac",
                ),
                http_client_cls=AsyncMock(),
                write_audit_log_fn=AsyncMock(),
                idempotency_key="invite-request-123",
            )

        assert exc.value.status == 409
        db.add.assert_not_called()
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["attorney", "scientist", "client"])
    async def test_prod_invite_uses_exact_clerk_org_contract(self, role: str):
        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_pharma_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            org_id=org_id,
            clerk_user_id="user_inviter_123",
            membership_active=True,
            clerk_membership_role="admin",
            role=UserRole.ADMIN,
        )
        db.execute.side_effect = [
            org_result,
            inviter_result,
            org_result,
            inviter_result,
            org_result,
        ]
        expected_metadata = {
            "praviar_role_version": 1,
            "praviar_role": role,
            "praviar_invitation_operation_id": ("11111111-1111-4111-8111-111111111111"),
        }
        response = httpx.Response(
            201,
            json={
                "id": "orginv_123",
                "organization_id": "org_pharma_123",
                "email_address": "new.user@praviar.io",
                "role": "org:member",
                "status": "pending",
                "public_metadata": {
                    **expected_metadata,
                    "provider_owned": "preserved",
                },
            },
        )
        order: list[str] = []
        client = AsyncMock()
        client.post.side_effect = lambda *_args, **_kwargs: (
            order.append("provider"),
            response,
        )[1]
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        client_cls = MagicMock(return_value=client_cm)
        audit_log = AsyncMock(
            side_effect=lambda *_args, **kwargs: order.append(f"audit:{kwargs['action']}")
        )
        db.commit.side_effect = lambda: order.append("commit")

        await invite_user_to_org_impl(
            db,
            org_id=org_id,
            admin_id=admin_id,
            body=InviteRequest(email="new.user@praviar.io", role=role),
            settings=SimpleNamespace(
                app_env="prod",
                clerk_secret_key="sk_live_123",
                api_key_hmac_secret="test-private-hmac",
            ),
            http_client_cls=client_cls,
            write_audit_log_fn=audit_log,
            idempotency_key="invite-request-123",
        )

        client.post.assert_awaited_once_with(
            "https://api.clerk.com/v1/organizations/org_pharma_123/invitations",
            headers={
                "Authorization": "Bearer sk_live_123",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Clerk-API-Version": "2026-05-12",
            },
            json={
                "inviter_user_id": "user_inviter_123",
                "email_address": "new.user@praviar.io",
                "role": "org:member",
                "public_metadata": expected_metadata,
            },
        )
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_invite.requested",
            "admin.user_invited",
        ]
        assert audit_log.await_args_list[0].kwargs["details"]["operation_id"] == (
            "11111111-1111-4111-8111-111111111111"
        )
        assert db.commit.await_count == 5
        db.rollback.assert_not_awaited()
        assert order == [
            "audit:admin.user_invite.requested",
            "commit",
            "commit",
            "commit",
            "provider",
            "commit",
            "audit:admin.user_invited",
            "commit",
        ]

    @pytest.mark.asyncio
    async def test_prod_invite_rejects_mismatched_clerk_response_and_rolls_back(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_pharma_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            clerk_user_id="user_inviter_123",
        )
        db.execute.side_effect = [
            org_result,
            inviter_result,
            org_result,
            inviter_result,
            org_result,
        ]
        response = httpx.Response(
            201,
            json={
                "id": "orginv_123",
                "organization_id": "org_other",
                "email_address": "new.user@praviar.io",
                "role": "org:member",
                "status": "pending",
                "public_metadata": {
                    "praviar_role_version": 1,
                    "praviar_role": "scientist",
                },
            },
        )
        client = AsyncMock()
        client.post.return_value = response
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        audit_log = AsyncMock()

        with pytest.raises(APIError) as exc:
            await invite_user_to_org_impl(
                db,
                org_id=org_id,
                admin_id=admin_id,
                body=InviteRequest(email="new.user@praviar.io", role="scientist"),
                settings=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_live_123",
                    api_key_hmac_secret="test-private-hmac",
                ),
                http_client_cls=MagicMock(return_value=client_cm),
                write_audit_log_fn=audit_log,
                idempotency_key="invite-request-123",
            )

        assert exc.value.status == 502
        assert "mismatched invitation" in exc.value.detail
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_invite.requested",
            "admin.user_invite.outcome_unknown",
        ]
        assert db.commit.await_count == 4
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prod_invite_preflight_audit_failure_prevents_clerk_call(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_pharma_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            clerk_user_id="user_inviter_123",
        )
        db.execute.side_effect = [org_result, inviter_result]
        client_cls = MagicMock()

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await invite_user_to_org_impl(
                db,
                org_id=org_id,
                admin_id=admin_id,
                body=InviteRequest(email="new.user@praviar.io", role="scientist"),
                settings=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_live_123",
                    api_key_hmac_secret="test-private-hmac",
                ),
                http_client_cls=client_cls,
                write_audit_log_fn=AsyncMock(side_effect=RuntimeError("audit unavailable")),
                idempotency_key="invite-request-123",
            )

        client_cls.assert_not_called()
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()
