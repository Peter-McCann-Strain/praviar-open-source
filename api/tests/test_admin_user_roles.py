from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from conftest import make_mock_db, make_user

from api.db.models import ClerkAdminOperation, UserRole
from api.errors import APIError
from api.schemas.admin import UpdateUserRoleRequest
from api.services import admin_users as admin_users_service
from api.services.admin_users import (
    _clear_operation_owned_denial,
    _guard_last_admin_demotion,
    _update_user_role_in_clerk,
    update_user_role_for_admin_impl,
)


@pytest.fixture(autouse=True)
def _stable_durable_operation_claim(monkeypatch):
    original_load_target = admin_users_service._load_target_user
    targets: dict[uuid.UUID, object] = {}
    operations: dict[uuid.UUID, ClerkAdminOperation] = {}

    async def _load_target(db, *, user_id, for_update=False):
        if user_id not in targets:
            targets[user_id] = await original_load_target(
                db, user_id=user_id, for_update=for_update
            )
        return targets[user_id]

    async def _claim(db, **kwargs):
        operation = ClerkAdminOperation(
            id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
            org_id=kwargs["org_id"],
            initiated_by=kwargs["admin_id"],
            operation_type=kwargs["operation_type"],
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="requested",
            target_user_id=kwargs["target_user_id"],
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

    async def _reserve(
        db,
        *,
        target_user_id,
        admin_org_id,
        new_role,
        operation_id=None,
    ):
        target = targets[target_user_id]
        await admin_users_service._guard_last_admin_demotion(
            db,
            target_user=target,
            admin_org_id=admin_org_id,
            new_role=new_role,
            for_update=True,
            require_synchronized_authority=True,
        )
        if target.role != new_role:
            target.membership_permission_denied_at = datetime.now(UTC)
            target.membership_permission_denied_by_operation_id = operation_id
        await db.commit()
        return (
            SimpleNamespace(id=admin_org_id, clerk_org_id="org_123"),
            target,
            operations.get(operation_id),
        )

    async def _lock_org(_db, *, org_id):
        return SimpleNamespace(id=org_id, clerk_org_id="org_123")

    async def _load_operation(_db, *, operation_id, for_update):
        del for_update
        return operations[operation_id]

    async def _direct_breaker_call(fn):
        return await fn()

    monkeypatch.setattr("api.services.admin_users._claim_admin_operation", _claim)
    monkeypatch.setattr("api.services.admin_users._load_target_user", _load_target)
    monkeypatch.setattr("api.services.admin_users._reserve_role_change", _reserve)
    monkeypatch.setattr("api.services.admin_users._lock_org", _lock_org)
    monkeypatch.setattr("api.services.admin_users._load_admin_operation_by_id", _load_operation)
    monkeypatch.setattr("api.circuit_breaker.clerk_breaker.call", _direct_breaker_call)
    return operations, targets


class TestAdminUserRoles:
    def test_only_exact_operation_can_release_owned_denial(self):
        org_id = uuid.uuid4()
        target = make_user(role=UserRole.ADMIN, org_id=org_id)
        owner = ClerkAdminOperation(
            id=uuid.uuid4(),
            org_id=org_id,
            initiated_by=uuid.uuid4(),
            operation_type="role_update",
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="role_call_started",
            target_user_id=target.id,
            requested_role="client",
        )
        interloper = ClerkAdminOperation(
            id=uuid.uuid4(),
            org_id=org_id,
            initiated_by=uuid.uuid4(),
            operation_type="role_update",
            client_key_digest="c" * 64,
            request_hash="d" * 64,
            state="failed",
            target_user_id=target.id,
            requested_role="attorney",
        )
        target.membership_permission_denied_at = datetime.now(UTC)
        target.membership_permission_denied_by_operation_id = owner.id

        _clear_operation_owned_denial(target, operation=interloper)

        assert target.membership_permission_denied_at is not None
        assert target.membership_permission_denied_by_operation_id == owner.id

        _clear_operation_owned_denial(target, operation=owner)

        assert target.membership_permission_denied_at is None
        assert target.membership_permission_denied_by_operation_id is None

    @pytest.mark.asyncio
    async def test_last_admin_guard_counts_only_active_unreserved_synchronized_admins(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        target = make_user(role=UserRole.ADMIN, org_id=org_id)
        target.membership_active = True
        target.clerk_membership_id = "mem_active"
        target.clerk_membership_role = "admin"
        target.membership_permission_denied_at = None
        result = MagicMock()
        result.scalars.return_value.all.return_value = [target.id]
        db.execute.return_value = result

        with pytest.raises(APIError, match="Cannot demote the last admin"):
            await _guard_last_admin_demotion(
                db,
                target_user=target,
                admin_org_id=org_id,
                new_role=UserRole.CLIENT,
                for_update=True,
                require_synchronized_authority=True,
            )

        sql = str(db.execute.await_args.args[0])
        assert "membership_active" in sql
        assert "membership_permission_denied_at" in sql
        assert "clerk_membership_role" in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["timeout", "503"])
    async def test_durable_membership_mutation_is_submitted_at_most_once(self, failure: str):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        org = SimpleNamespace(id=org_id, clerk_org_id="org_123")
        operation = ClerkAdminOperation(
            id=uuid.uuid4(),
            org_id=org_id,
            initiated_by=uuid.uuid4(),
            operation_type="role_update",
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="requested",
            target_user_id=user.id,
            requested_role="attorney",
        )
        current = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata={
                "unrelated_provider_key": "preserve-me",
                "praviar_role_version": 1,
                "praviar_role": "scientist",
            },
        )
        client = AsyncMock()
        client.get.return_value = current
        if failure == "timeout":
            client.patch.side_effect = httpx.ReadTimeout("ambiguous")
        else:
            client.patch.return_value = httpx.Response(503, json={"error": "busy"})
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        async def _transition(_db, *, new_state, provider_updated_at=None, **_kwargs):
            operation.state = new_state
            if provider_updated_at is not None:
                operation.provider_updated_at = provider_updated_at
            await _db.commit()
            return org, user, operation

        async def _verify_provider_snapshot(_db, **_kwargs):
            await _db.commit()

        with (
            patch(
                "api.services.admin_users._transition_role_operation",
                new=_transition,
            ),
            patch(
                "api.services.admin_users._verify_role_provider_snapshot",
                new=_verify_provider_snapshot,
            ),
            pytest.raises(APIError, match="outcome is unknown"),
        ):
            await _update_user_role_in_clerk(
                target_user=user,
                org=org,
                new_role=UserRole.ATTORNEY,
                settings=SimpleNamespace(clerk_secret_key="sk_live"),
                http_client_cls=MagicMock(return_value=client_cm),
                db=db,
                operation=operation,
            )

        assert client.patch.await_count == 1
        assert operation.state == "metadata_call_started"
        assert client.patch.await_args.kwargs["json"]["public_metadata"] == {
            "unrelated_provider_key": "preserve-me",
            "praviar_role_version": 1,
            "praviar_role": "attorney",
        }

    @pytest.mark.asyncio
    async def test_update_user_role_for_admin_impl_updates_user_and_audits(self):
        db = make_mock_db()
        admin_org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=admin_org_id)

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        db.execute.return_value = result
        audit_log = AsyncMock()

        await update_user_role_for_admin_impl(
            db,
            user_id=user.id,
            admin_org_id=admin_org_id,
            admin_id=uuid.uuid4(),
            body=UpdateUserRoleRequest(role="attorney"),
            write_audit_log_fn=audit_log,
            settings=SimpleNamespace(app_env="dev", clerk_secret_key="sk_dev"),
            http_client_cls=AsyncMock(),
            idempotency_key="role-operation-123",
        )

        assert user.role == UserRole.ATTORNEY
        assert audit_log.await_count == 2
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_update_user_role_for_admin_impl_rolls_back_when_audit_fails(self):
        db = make_mock_db()
        admin_org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=admin_org_id)

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        db.execute.return_value = result
        audit_log = AsyncMock(side_effect=RuntimeError("audit unavailable"))

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=admin_org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="attorney"),
                write_audit_log_fn=audit_log,
                settings=SimpleNamespace(app_env="dev", clerk_secret_key="sk_dev"),
                http_client_cls=AsyncMock(),
                idempotency_key="role-operation-123",
            )

        assert user.role == UserRole.SCIENTIST
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_user_role_for_admin_impl_rejects_invalid_role(self):
        db = make_mock_db()
        admin_org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=admin_org_id)

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        db.execute.return_value = result

        with pytest.raises(APIError) as exc:
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=admin_org_id,
                admin_id=uuid.uuid4(),
                body=SimpleNamespace(role="not-a-role"),  # type: ignore[arg-type]
                write_audit_log_fn=AsyncMock(),
                settings=SimpleNamespace(app_env="dev", clerk_secret_key="sk_dev"),
                http_client_cls=AsyncMock(),
                idempotency_key="role-operation-123",
            )

        assert exc.value.status == 400
        db.commit.assert_not_awaited()

    @staticmethod
    def _membership_response(
        user,
        *,
        clerk_org_id: str,
        clerk_role: str,
        public_metadata: dict[str, object],
        updated_at: int = 1_790_000_000_000,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": user.clerk_membership_id,
                "organization": {"id": clerk_org_id},
                "public_user_data": {"user_id": user.clerk_user_id},
                "role": clerk_role,
                "public_metadata": public_metadata,
                "updated_at": updated_at,
            },
        )

    @pytest.mark.asyncio
    async def test_prod_member_role_update_patches_versioned_metadata(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        org = SimpleNamespace(id=org_id, clerk_org_id="org_123")
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = org
        db.execute.side_effect = [target_result, org_result, target_result]
        expected_metadata = {
            "praviar_role_version": 1,
            "praviar_role": "attorney",
        }
        order: list[str] = []
        response = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata=expected_metadata,
        )
        client = AsyncMock()
        client.get.return_value = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata={
                "praviar_role_version": 1,
                "praviar_role": "scientist",
            },
        )
        client.patch.side_effect = lambda *_args, **_kwargs: (
            order.append("provider"),
            response,
        )[1]
        db.commit.side_effect = lambda: order.append("commit")
        audit_log = AsyncMock(
            side_effect=lambda *_args, **kwargs: order.append(f"audit:{kwargs['action']}")
        )
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        await update_user_role_for_admin_impl(
            db,
            user_id=user.id,
            admin_org_id=org_id,
            admin_id=uuid.uuid4(),
            body=UpdateUserRoleRequest(role="attorney"),
            write_audit_log_fn=audit_log,
            settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
            http_client_cls=MagicMock(return_value=client_cm),
            idempotency_key="role-operation-123",
        )

        assert user.role == UserRole.ATTORNEY
        assert user.clerk_membership_role == "member"
        assert user.membership_updated_at == datetime.fromtimestamp(1_790_000_000, tz=UTC)
        client.patch.assert_awaited_once()
        call = client.patch.await_args
        assert call.args[0] == (
            "https://api.clerk.com/v1/organizations/org_123/memberships/clerk_test_user/metadata"
        )
        assert call.kwargs["json"] == {"public_metadata": expected_metadata}
        assert call.kwargs["headers"]["Clerk-API-Version"] == "2026-05-12"
        assert call.kwargs["headers"]["Authorization"] == "Bearer sk_live_123"
        assert "Idempotency-Key" not in call.kwargs["headers"]
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_role.update_requested",
            "admin.user_role.updated",
        ]
        assert audit_log.await_args_list[0].kwargs["details"]["operation_id"] == (
            "11111111-1111-4111-8111-111111111111"
        )
        assert db.commit.await_count >= 5

    @pytest.mark.asyncio
    async def test_prod_promotion_updates_coarse_clerk_role_before_local_admin(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.CLIENT, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        db.execute.side_effect = [target_result, org_result, target_result]
        client = AsyncMock()
        client.get.return_value = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata={
                "praviar_role_version": 1,
                "praviar_role": "client",
            },
        )
        client.patch.return_value = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:admin",
            public_metadata={},
        )
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        await update_user_role_for_admin_impl(
            db,
            user_id=user.id,
            admin_org_id=org_id,
            admin_id=uuid.uuid4(),
            body=UpdateUserRoleRequest(role="admin"),
            write_audit_log_fn=AsyncMock(),
            settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
            http_client_cls=MagicMock(return_value=client_cm),
            idempotency_key="role-operation-123",
        )

        assert user.role == UserRole.ADMIN
        assert user.clerk_membership_role == "admin"
        client.patch.assert_awaited_once()
        call = client.patch.await_args
        assert call.args[0].endswith("/organizations/org_123/memberships/clerk_test_user")
        assert call.kwargs["json"] == {"role": "org:admin"}
        assert db.commit.await_count >= 5

    @pytest.mark.asyncio
    async def test_prod_demotion_sets_least_privilege_metadata_before_coarse_role(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.ADMIN, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "admin"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        admins_result = MagicMock()
        admins_result.scalars.return_value.all.return_value = [user.id, uuid.uuid4()]
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        db.execute.side_effect = [
            target_result,
            admins_result,
            org_result,
            admins_result,
            admins_result,
        ]
        expected_metadata = {
            "praviar_role_version": 1,
            "praviar_role": "client",
        }
        client = AsyncMock()
        client.get.side_effect = [
            self._membership_response(
                user,
                clerk_org_id="org_123",
                clerk_role="org:admin",
                public_metadata={},
            ),
            self._membership_response(
                user,
                clerk_org_id="org_123",
                clerk_role="org:admin",
                public_metadata=expected_metadata,
            ),
        ]
        client.patch.side_effect = [
            self._membership_response(
                user,
                clerk_org_id="org_123",
                clerk_role="org:admin",
                public_metadata=expected_metadata,
            ),
            self._membership_response(
                user,
                clerk_org_id="org_123",
                clerk_role="org:member",
                public_metadata=expected_metadata,
                updated_at=1_791_000_000_000,
            ),
        ]
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        await update_user_role_for_admin_impl(
            db,
            user_id=user.id,
            admin_org_id=org_id,
            admin_id=uuid.uuid4(),
            body=UpdateUserRoleRequest(role="client"),
            write_audit_log_fn=AsyncMock(),
            settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
            http_client_cls=MagicMock(return_value=client_cm),
            idempotency_key="role-operation-123",
        )

        assert user.role == UserRole.CLIENT
        assert user.clerk_membership_role == "member"
        assert user.membership_updated_at == datetime.fromtimestamp(1_791_000_000, tz=UTC)
        assert client.patch.await_count == 2
        metadata_call, role_call = client.patch.await_args_list
        assert metadata_call.args[0].endswith("/memberships/clerk_test_user/metadata")
        assert metadata_call.kwargs["json"] == {"public_metadata": expected_metadata}
        assert role_call.args[0].endswith("/memberships/clerk_test_user")
        assert role_call.kwargs["json"] == {"role": "org:member"}
        assert db.commit.await_count >= 7

    @pytest.mark.asyncio
    async def test_prod_role_update_unknown_outcome_rolls_back_without_local_mutation(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        db.execute.side_effect = [target_result, org_result, target_result]
        request = httpx.Request(
            "PATCH",
            "https://api.clerk.com/v1/organizations/org_123/memberships/clerk_test_user/metadata",
        )
        client = AsyncMock()
        client.get.return_value = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata={
                "praviar_role_version": 1,
                "praviar_role": "scientist",
            },
        )
        client.patch.side_effect = httpx.ReadTimeout("unknown outcome", request=request)
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        audit_log = AsyncMock()

        with (
            patch("api.http_utils.asyncio.sleep", new=AsyncMock()),
            pytest.raises(APIError) as exc,
        ):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="attorney"),
                write_audit_log_fn=audit_log,
                settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
                http_client_cls=MagicMock(return_value=client_cm),
                idempotency_key="role-operation-123",
            )

        assert exc.value.status == 503
        assert exc.value.detail == "Clerk membership update outcome is unknown"
        assert client.patch.await_count == 1
        assert user.role == UserRole.SCIENTIST
        assert user.clerk_membership_role == "member"
        assert user.membership_permission_denied_at is not None
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_role.update_requested",
            "admin.user_role.update.outcome_unknown",
        ]
        assert db.commit.await_count >= 4
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_known_clerk_rejection_restores_authority_and_is_terminal(
        self,
        _stable_durable_operation_claim,
    ):
        operations, _targets = _stable_durable_operation_claim
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        db.execute.side_effect = [target_result, org_result]
        client = AsyncMock()
        client.get.return_value = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:member",
            public_metadata={
                "praviar_role_version": 1,
                "praviar_role": "scientist",
            },
        )
        client.patch.return_value = httpx.Response(422, json={"error": "rejected"})
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        audit = AsyncMock()

        with pytest.raises(APIError, match="Clerk rejected the request"):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="attorney"),
                write_audit_log_fn=audit,
                settings=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_live_123",
                ),
                http_client_cls=MagicMock(return_value=client_cm),
                idempotency_key="known-rejection-key-123",
            )

        operation = next(iter(operations.values()))
        assert operation.state == "failed"
        assert operation.last_error_code == "clerk_422"
        assert user.role == UserRole.SCIENTIST
        assert user.clerk_membership_role == "member"
        assert user.membership_permission_denied_at is None
        assert client.patch.await_count == 1
        assert [call.kwargs["action"] for call in audit.await_args_list] == [
            "admin.user_role.update_requested",
            "admin.user_role.update.failed",
        ]

    @pytest.mark.asyncio
    async def test_demotion_role_rejection_terminalizes_partial_metadata_without_replay(
        self,
        _stable_durable_operation_claim,
    ):
        operations, _targets = _stable_durable_operation_claim
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.ADMIN, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "admin"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        other_admin_id = uuid.uuid4()
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        initial_admins = MagicMock()
        initial_admins.scalars.return_value.all.return_value = [user.id, other_admin_id]
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        locked_admins = MagicMock()
        locked_admins.scalars.return_value.all.return_value = [user.id, other_admin_id]
        db.execute.side_effect = [
            target_result,
            initial_admins,
            org_result,
            locked_admins,
        ]
        metadata = {
            "praviar_role_version": 1,
            "praviar_role": "client",
        }
        current_admin = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:admin",
            public_metadata={},
        )
        metadata_accepted = self._membership_response(
            user,
            clerk_org_id="org_123",
            clerk_role="org:admin",
            public_metadata=metadata,
            updated_at=1_790_000_001_000,
        )
        client = AsyncMock()
        client.get.side_effect = [current_admin, metadata_accepted]
        client.patch.side_effect = [
            metadata_accepted,
            httpx.Response(422, json={"error": "role rejected"}),
        ]
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False
        audit = AsyncMock()

        with pytest.raises(APIError, match="Clerk rejected the request"):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="client"),
                write_audit_log_fn=audit,
                settings=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_live_123",
                ),
                http_client_cls=MagicMock(return_value=client_cm),
                idempotency_key="partial-role-rejection-123",
            )

        operation = next(iter(operations.values()))
        assert operation.state == "failed"
        assert operation.last_error_code == "clerk_role_rejected_after_metadata_422"
        assert operation.provider_updated_at is not None
        assert user.role == UserRole.CLIENT
        assert user.clerk_membership_role == "admin"
        assert user.membership_permission_denied_at is not None
        assert user.membership_permission_denied_by_operation_id is None
        assert user.membership_permission_convergence_operation_id == operation.id
        assert user.membership_updated_at == operation.provider_updated_at
        assert client.patch.await_count == 2
        failed_audit = audit.await_args_list[-1].kwargs
        assert failed_audit["action"] == "admin.user_role.update.failed"
        assert failed_audit["details"]["provider_accepted"] is True
        assert failed_audit["details"]["partial_metadata_accepted"] is True
        assert failed_audit["details"]["authority_denied_pending_convergence"] is True
        assert failed_audit["details"]["terminal_reason"] == operation.last_error_code

        # Terminal failure removes this operation from reconciliation/open work;
        # only the two original provider calls were made.
        assert client.patch.await_count == 2

    @pytest.mark.asyncio
    async def test_prod_preflight_audit_failure_prevents_clerk_role_call(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "member"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        db.execute.side_effect = [target_result, org_result]
        client_cls = MagicMock()

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="attorney"),
                write_audit_log_fn=AsyncMock(side_effect=RuntimeError("audit unavailable")),
                settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
                http_client_cls=client_cls,
                idempotency_key="role-operation-123",
            )

        client_cls.assert_not_called()
        assert user.role == UserRole.SCIENTIST
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prod_demotion_relocks_and_rechecks_last_admin_after_preflight(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.ADMIN, org_id=org_id)
        user.clerk_membership_id = "mem_123"
        user.clerk_membership_role = "admin"
        user.membership_active = True
        user.membership_updated_at = datetime.fromtimestamp(1_788_000_000, tz=UTC)
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = user
        initial_admins = MagicMock()
        initial_admins.scalars.return_value.all.return_value = [user.id, uuid.uuid4()]
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_123",
        )
        remaining_admin = MagicMock()
        remaining_admin.scalars.return_value.all.return_value = [user.id]
        db.execute.side_effect = [
            target_result,
            initial_admins,
            org_result,
            remaining_admin,
        ]
        client_cls = MagicMock()
        audit_log = AsyncMock()

        with pytest.raises(APIError, match="Cannot demote the last admin"):
            await update_user_role_for_admin_impl(
                db,
                user_id=user.id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="client"),
                write_audit_log_fn=audit_log,
                settings=SimpleNamespace(app_env="prod", clerk_secret_key="sk_live_123"),
                http_client_cls=client_cls,
                idempotency_key="role-operation-123",
            )

        assert "membership_permission_denied_at" in str(db.execute.await_args_list[3].args[0])
        client_cls.assert_not_called()
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_role.update_requested",
            "admin.user_role.update.failed",
        ]
        assert db.commit.await_count == 2
        db.rollback.assert_awaited_once()
