"""Tests for admin dashboard service helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db, make_user

from api.db.models import ClerkAdminOperation, OrgPlan, UserRole
from api.errors import APIError
from api.schemas.admin import InviteRequest, UpdateOrgRequest, UpdateUserRoleRequest
from api.services.admin import (
    get_org_metrics,
    get_system_health,
    get_task_queue_summary,
    invite_user_to_org,
    list_audit_logs_page,
    list_organizations_page,
    list_users_page,
    update_organization_for_admin,
    update_user_role_for_admin,
)


@pytest.fixture
def stable_admin_operation(monkeypatch):
    operations: dict[uuid.UUID, ClerkAdminOperation] = {}

    async def _claim(db, **kwargs):
        operation = ClerkAdminOperation(
            id=uuid.uuid4(),
            org_id=kwargs["org_id"],
            initiated_by=kwargs["admin_id"],
            operation_type=kwargs["operation_type"],
            client_key_digest="a" * 64,
            request_hash="b" * 64,
            state="requested",
            target_user_id=kwargs["target_user_id"],
            target_email_normalized=kwargs["target_email_normalized"],
            requested_role=kwargs["requested_role"],
        )
        operations[operation.id] = operation
        await kwargs["write_audit_log_fn"](
            db,
            org_id=kwargs["org_id"],
            user_id=kwargs["admin_id"],
            action=kwargs["requested_action"],
            details={"operation_id": str(operation.id), **kwargs["requested_details"]},
            fail_closed=True,
        )
        await db.commit()
        return operation, True

    async def _load(_db, *, operation_id, for_update):
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
        operation = operations[snapshot.operation_id]
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
    monkeypatch.setattr("api.services.admin_users._load_admin_operation_by_id", _load)
    monkeypatch.setattr("api.services.admin_users._transition_invite_operation", _transition_invite)
    monkeypatch.setattr(
        "api.services.admin_users._verify_invite_operation_before_provider_read",
        _verify_invite,
    )
    monkeypatch.setattr("api.services.admin_users._lock_invite_operation_snapshot", _lock_invite)
    return operations


class TestGetOrgMetrics:
    @pytest.mark.asyncio
    async def test_get_org_metrics_builds_daily_and_totals(self, mock_db):
        org_id = uuid.uuid4()
        daily_result = SimpleNamespace(
            all=lambda: [
                SimpleNamespace(date=date(2026, 4, 1), count=3, cost=12.5, errors=1),
                SimpleNamespace(date=date(2026, 4, 2), count=1, cost=4.0, errors=0),
            ]
        )
        totals_result = SimpleNamespace(
            one=lambda: SimpleNamespace(
                total=4,
                total_cost=16.5,
                avg_duration=87.5,
                error_count=1,
            )
        )
        mock_db.execute.side_effect = [daily_result, totals_result]

        summary = await get_org_metrics(
            mock_db,
            org_id=org_id,
            now=datetime(2026, 4, 11, tzinfo=UTC),
        )

        assert [metric.date for metric in summary.daily] == ["2026-04-01", "2026-04-02"]
        assert [metric.count for metric in summary.daily] == [3, 1]
        assert summary.total_analyses == 4
        assert summary.total_cost == 16.5
        assert summary.avg_duration_seconds == 87.5
        assert summary.error_rate == 0.25

    @pytest.mark.asyncio
    async def test_get_org_metrics_zero_analyses_returns_zero_error_rate(self, mock_db):
        daily_result = SimpleNamespace(all=lambda: [])
        totals_result = SimpleNamespace(
            one=lambda: SimpleNamespace(
                total=0,
                total_cost=0.0,
                avg_duration=None,
                error_count=0,
            )
        )
        mock_db.execute.side_effect = [daily_result, totals_result]

        summary = await get_org_metrics(mock_db, org_id=uuid.uuid4())

        assert summary.daily == []
        assert summary.total_analyses == 0
        assert summary.total_cost == 0.0
        assert summary.avg_duration_seconds is None
        assert summary.error_rate == 0.0


class TestListAuditLogsPage:
    @pytest.mark.asyncio
    async def test_list_audit_logs_page_builds_items_with_user_emails(self, mock_db):
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        log_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        created_at = datetime(2026, 4, 10, tzinfo=UTC)
        total_result = SimpleNamespace(scalar_one=lambda: 1)
        logs_result = SimpleNamespace(
            scalars=lambda: SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=log_id,
                        action="analysis.deleted",
                        user_id=user_id,
                        analysis_id=analysis_id,
                        details={"source": "admin"},
                        ip_address="127.0.0.1",
                        created_at=created_at,
                    )
                ]
            )
        )
        users_result = SimpleNamespace(all=lambda: [(user_id, "admin@praviar.io")])
        mock_db.execute.side_effect = [total_result, logs_result, users_result]

        page = await list_audit_logs_page(
            mock_db,
            org_id=org_id,
            action="analysis.deleted",
            user_id=None,
            page=1,
            per_page=50,
        )

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].id == log_id
        assert page.items[0].user_email == "admin@praviar.io"
        assert page.items[0].details == {"source": "admin"}

    @pytest.mark.asyncio
    async def test_list_audit_logs_page_handles_logs_without_users(self, mock_db):
        log_id = uuid.uuid4()
        total_result = SimpleNamespace(scalar_one=lambda: 1)
        logs_result = SimpleNamespace(
            scalars=lambda: SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=log_id,
                        action="system.health",
                        user_id=None,
                        analysis_id=None,
                        details={},
                        ip_address="127.0.0.1",
                        created_at=datetime(2026, 4, 10, tzinfo=UTC),
                    )
                ]
            )
        )
        mock_db.execute.side_effect = [total_result, logs_result]

        page = await list_audit_logs_page(
            mock_db,
            org_id=uuid.uuid4(),
            action=None,
            user_id=None,
            page=1,
            per_page=50,
        )

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].user_email == ""


class TestOrganizations:
    @pytest.mark.asyncio
    async def test_list_organizations_page_maps_counts(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        org = MagicMock()
        org.id = org_id
        org.name = "Praviar Labs"
        org.slug = "praviar-labs"
        org.plan = OrgPlan.STARTER
        org.max_analyses_per_month = 25
        org.free_analyses_remaining = 2
        org.created_at = datetime(2026, 4, 11, tzinfo=UTC)

        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.all.return_value = [(org, 3, 9)]
        db.execute.side_effect = [total_result, items_result]

        page = await list_organizations_page(db, page=1, per_page=20)

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].id == org_id
        assert page.items[0].plan == "starter"
        assert page.items[0].user_count == 3
        assert page.items[0].analysis_count == 9

    @pytest.mark.asyncio
    async def test_list_organizations_page_can_scope_to_one_org(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        org = MagicMock()
        org.id = org_id
        org.name = "Praviar Labs"
        org.slug = "praviar-labs"
        org.plan = OrgPlan.STARTER
        org.max_analyses_per_month = 25
        org.free_analyses_remaining = 2
        org.created_at = datetime(2026, 4, 11, tzinfo=UTC)

        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.all.return_value = [(org, 3, 9)]
        db.execute.side_effect = [total_result, items_result]

        page = await list_organizations_page(db, org_id=org_id, page=1, per_page=20)

        count_query = str(db.execute.await_args_list[0].args[0])
        items_query = str(db.execute.await_args_list[1].args[0])
        assert "WHERE organizations.id =" in count_query
        assert "WHERE organizations.id =" in items_query
        assert page.total == 1
        assert page.items[0].id == org_id

    @pytest.mark.asyncio
    async def test_update_organization_for_admin_updates_allowed_org(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        org = MagicMock()
        org.id = org_id
        org.plan = OrgPlan.FREE
        org.max_analyses_per_month = 10
        org.free_analyses_remaining = 2

        result = MagicMock()
        result.scalar_one_or_none.return_value = org
        db.execute.return_value = result

        with patch("api.services.admin.write_audit_log", new=AsyncMock()) as audit_log:
            await update_organization_for_admin(
                db,
                org_id=org_id,
                admin_org_id=org_id,
                admin_id=uuid.uuid4(),
                body=UpdateOrgRequest(
                    plan="pro",
                    max_analyses_per_month=100,
                    free_analyses_remaining=5,
                ),
            )

        assert org.plan == OrgPlan.PRO
        assert org.max_analyses_per_month == 100
        assert org.free_analyses_remaining == 5
        audit_log.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_organization_for_admin_rejects_other_org(self):
        db = make_mock_db()
        org = MagicMock()
        org.id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = org
        db.execute.return_value = result

        with pytest.raises(APIError) as exc:
            await update_organization_for_admin(
                db,
                org_id=org.id,
                admin_org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=UpdateOrgRequest(plan="starter"),  # type: ignore[call-arg]
            )

        assert exc.value.status == 403
        db.commit.assert_not_awaited()


class TestUsers:
    @pytest.mark.asyncio
    async def test_list_users_page_maps_org_names(self):
        db = make_mock_db()
        org_id = uuid.uuid4()
        user = make_user(role=UserRole.ATTORNEY, org_id=org_id, email="attorney@praviar.io")

        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [user]
        org_result = MagicMock()
        org_result.all.return_value = [(org_id, "Praviar Labs")]
        db.execute.side_effect = [total_result, users_result, org_result]

        page = await list_users_page(db, org_id=None, page=1, per_page=20)

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].email == "attorney@praviar.io"
        assert page.items[0].role == "attorney"
        assert page.items[0].org_name == "Praviar Labs"

    @pytest.mark.asyncio
    async def test_update_user_role_for_admin_updates_allowed_user(self, stable_admin_operation):
        db = make_mock_db()
        admin_org_id = uuid.uuid4()
        user = make_user(role=UserRole.SCIENTIST, org_id=admin_org_id)

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        db.execute.return_value = result

        with patch("api.services.admin.write_audit_log", new=AsyncMock()) as audit_log:
            await update_user_role_for_admin(
                db,
                user_id=user.id,
                admin_org_id=admin_org_id,
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="attorney"),
                idempotency_key="role-service-test-123",
            )

        assert user.role == UserRole.ATTORNEY
        assert audit_log.await_count == 2
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_update_user_role_for_admin_rejects_other_org(self):
        db = make_mock_db()
        user = make_user(role=UserRole.SCIENTIST, org_id=uuid.uuid4())

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        db.execute.return_value = result

        with pytest.raises(APIError) as exc:
            await update_user_role_for_admin(
                db,
                user_id=user.id,
                admin_org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=UpdateUserRoleRequest(role="client"),
                idempotency_key="role-service-test-123",
            )

        assert exc.value.status == 403
        db.commit.assert_not_awaited()


class TestInviteUser:
    @pytest.mark.asyncio
    async def test_invite_user_to_org_creates_local_user_in_dev_mode(self, stable_admin_operation):
        db = make_mock_db()
        org_id = uuid.uuid4()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        mock_client_cm = AsyncMock()

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(
                    app_env="dev",
                    clerk_secret_key="sk_dev",
                    api_key_hmac_secret="test-private-hmac",
                ),
            ),
            patch("api.services.admin.write_audit_log", new=AsyncMock()) as audit_log,
            patch(
                "api.services.admin.httpx.AsyncClient",
                return_value=mock_client_cm,
            ) as client_cls,
        ):
            await invite_user_to_org(
                db,
                org_id=org_id,
                admin_id=uuid.uuid4(),
                body=InviteRequest(email="new.user@praviar.io", role="scientist"),
                idempotency_key="invite-service-test-123",
            )

        created_user = db.add.call_args.args[0]
        assert created_user.org_id == org_id
        assert created_user.email == "new.user@praviar.io"
        assert created_user.role == UserRole.SCIENTIST
        client_cls.assert_not_called()
        assert audit_log.await_count == 2
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_invite_user_to_org_rejects_admin_role(self):
        db = make_mock_db()

        with pytest.raises(APIError) as exc:
            await invite_user_to_org(
                db,
                org_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                body=InviteRequest(email="admin@praviar.io", role="admin"),
                idempotency_key="invite-service-test-123",
            )

        assert exc.value.status == 403
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invite_user_to_org_surfaces_clerk_failure(self, stable_admin_operation):
        import httpx

        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_clerk_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            org_id=org_id,
            clerk_user_id="user_admin_123",
            clerk_membership_role="admin",
            membership_active=True,
            role=UserRole.ADMIN,
        )
        db.execute.side_effect = [
            org_result,
            inviter_result,
            org_result,
            inviter_result,
            org_result,
        ]
        mock_client = AsyncMock()
        _mock_req = httpx.Request(
            "POST",
            "https://api.clerk.com/v1/organizations/org_clerk_123/invitations",
        )
        _mock_resp = MagicMock(status_code=502, text="clerk unavailable")

        def _raise_502():
            raise httpx.HTTPStatusError("502", request=_mock_req, response=_mock_resp)

        mock_client.post = AsyncMock(
            return_value=SimpleNamespace(
                status_code=502, text="clerk unavailable", raise_for_status=_raise_502
            )
        )
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__.return_value = mock_client
        mock_client_cm.__aexit__.return_value = False

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="sk_test_123",
                    api_key_hmac_secret="test-private-hmac",
                ),
            ),
            patch("api.services.admin.write_audit_log", new=AsyncMock()) as audit_log,
            patch("api.services.admin.httpx.AsyncClient", return_value=mock_client_cm),
            pytest.raises(APIError) as exc,
        ):
            await invite_user_to_org(
                db,
                org_id=org_id,
                admin_id=admin_id,
                body=InviteRequest(email="invitee@praviar.io", role="scientist"),
                idempotency_key="invite-service-test-123",
            )

        assert exc.value.status == 503
        assert exc.value.detail == "Clerk invitation outcome is unknown"
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_invite.requested",
            "admin.user_invite.outcome_unknown",
        ]
        db.add.assert_not_called()
        assert db.commit.await_count == 4
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invite_user_to_org_requires_clerk_in_production(self, stable_admin_operation):
        db = make_mock_db()
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=org_id,
            clerk_org_id="org_clerk_123",
        )
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=admin_id,
            org_id=org_id,
            clerk_user_id="user_admin_123",
            clerk_membership_role="admin",
            membership_active=True,
            role=UserRole.ADMIN,
        )
        db.execute.side_effect = [org_result, inviter_result]

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(
                    app_env="prod",
                    clerk_secret_key="",
                    api_key_hmac_secret="test-private-hmac",
                ),
            ),
            patch("api.services.admin.write_audit_log", new=AsyncMock()) as audit_log,
            pytest.raises(APIError) as exc,
        ):
            await invite_user_to_org(
                db,
                org_id=org_id,
                admin_id=admin_id,
                body=InviteRequest(email="invitee@praviar.io", role="scientist"),
                idempotency_key="invite-service-test-123",
            )

        assert exc.value.status == 503
        assert [item.kwargs["action"] for item in audit_log.await_args_list] == [
            "admin.user_invite.requested",
            "admin.user_invite.failed",
        ]
        db.rollback.assert_awaited_once()
        db.add.assert_not_called()
        assert db.commit.await_count == 2


class TestSystemHealth:
    @pytest.mark.asyncio
    async def test_get_system_health_builds_service_and_table_counts(self, mock_db):
        database_result = SimpleNamespace(scalar_one=lambda: 1)
        organization_count = SimpleNamespace(scalar_one=lambda: 2)
        user_count = SimpleNamespace(scalar_one=lambda: 3)
        analysis_count = SimpleNamespace(scalar_one=lambda: 4)
        mock_db.execute.side_effect = [
            database_result,
            organization_count,
            user_count,
            analysis_count,
        ]

        class FakeRedis:
            async def ping(self):
                return None

            async def aclose(self):
                return None

        def inspect(timeout):
            return SimpleNamespace(
                active=lambda: {"worker-1": []},
            )

        fake_celery = SimpleNamespace(control=SimpleNamespace(inspect=inspect))

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(redis_url="redis://localhost:6379/0"),
            ),
            patch("redis.asyncio.from_url", return_value=FakeRedis()),
            patch("api.workers.celery_app.celery_app", fake_celery),
        ):
            summary = await get_system_health(mock_db)

        assert [service.name for service in summary.services] == ["database", "redis", "celery"]
        assert summary.table_counts == {"organizations": 2, "users": 3, "analyses": 4}

    @pytest.mark.asyncio
    async def test_get_system_health_can_scope_table_counts_to_org(self, mock_db):
        org_id = uuid.uuid4()
        database_result = SimpleNamespace(scalar_one=lambda: 1)
        organization_count = SimpleNamespace(scalar_one=lambda: 1)
        user_count = SimpleNamespace(scalar_one=lambda: 2)
        analysis_count = SimpleNamespace(scalar_one=lambda: 3)
        mock_db.execute.side_effect = [
            database_result,
            organization_count,
            user_count,
            analysis_count,
        ]

        class FakeRedis:
            async def ping(self):
                return None

            async def aclose(self):
                return None

        def inspect(timeout):
            return SimpleNamespace(active=lambda: {"worker-1": []})

        fake_celery = SimpleNamespace(control=SimpleNamespace(inspect=inspect))

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(redis_url="redis://localhost:6379/0"),
            ),
            patch("redis.asyncio.from_url", return_value=FakeRedis()),
            patch("api.workers.celery_app.celery_app", fake_celery),
        ):
            summary = await get_system_health(mock_db, org_id=org_id)

        count_queries = [str(call.args[0]) for call in mock_db.execute.await_args_list[1:]]
        assert "WHERE organizations.id =" in count_queries[0]
        assert "WHERE users.org_id =" in count_queries[1]
        assert "WHERE analyses.org_id =" in count_queries[2]
        assert summary.table_counts == {"organizations": 1, "users": 2, "analyses": 3}

    @pytest.mark.asyncio
    async def test_get_system_health_uses_cloud_tasks_when_configured(self, mock_db):
        database_result = SimpleNamespace(scalar_one=lambda: 1)
        organization_count = SimpleNamespace(scalar_one=lambda: 2)
        user_count = SimpleNamespace(scalar_one=lambda: 3)
        analysis_count = SimpleNamespace(scalar_one=lambda: 4)
        mock_db.execute.side_effect = [
            database_result,
            organization_count,
            user_count,
            analysis_count,
        ]

        class FakeRedis:
            async def ping(self):
                return None

            async def aclose(self):
                return None

        settings = SimpleNamespace(
            redis_url="redis://localhost:6379/0",
            pipeline_dispatch="cloud_tasks",
            gcp_project_id="praviar-prod",
            gcp_region="us-central1",
            cloud_tasks_queue_id="analysis-jobs",
            workers_service_url="https://workers.praviar.io",
            tasks_invoker_sa_email="tasks@praviar-prod.iam.gserviceaccount.com",
        )

        with (
            patch("api.services.admin.get_settings", return_value=settings),
            patch("redis.asyncio.from_url", return_value=FakeRedis()),
        ):
            summary = await get_system_health(mock_db)

        assert [service.name for service in summary.services] == [
            "database",
            "redis",
            "cloud_tasks",
        ]
        assert summary.services[2].status == "ok"
        assert summary.table_counts == {"organizations": 2, "users": 3, "analyses": 4}

    @pytest.mark.asyncio
    async def test_get_system_health_survives_table_count_failure(self, mock_db):
        database_result = SimpleNamespace(scalar_one=lambda: 1)
        organization_count = SimpleNamespace(scalar_one=lambda: 2)
        analysis_count = SimpleNamespace(scalar_one=lambda: 4)
        mock_db.execute.side_effect = [
            database_result,
            organization_count,
            RuntimeError("users count failed"),
            analysis_count,
        ]

        class FakeRedis:
            async def ping(self):
                return None

            async def aclose(self):
                return None

        def inspect(timeout):
            return SimpleNamespace(active=lambda: {"worker-1": []})

        fake_celery = SimpleNamespace(control=SimpleNamespace(inspect=inspect))

        with (
            patch(
                "api.services.admin.get_settings",
                return_value=SimpleNamespace(redis_url="redis://localhost:6379/0"),
            ),
            patch("redis.asyncio.from_url", return_value=FakeRedis()),
            patch("api.workers.celery_app.celery_app", fake_celery),
        ):
            summary = await get_system_health(mock_db)

        assert summary.table_counts == {"organizations": 2, "analyses": 4}
        assert summary.services[-1].name == "table_counts"
        assert summary.services[-1].status == "error"
        assert "users" in summary.services[-1].detail

    @pytest.mark.asyncio
    async def test_get_task_queue_summary_normalizes_tasks_and_handles_failure(self):
        def inspect(timeout):
            return SimpleNamespace(
                active=lambda: {"worker-1": [{"id": "a1", "name": "task.active", "args": [1]}]},
                reserved=lambda: {"worker-1": [{"id": "r1", "name": "task.reserved", "args": [2]}]},
                scheduled=lambda: {"worker-1": [object(), object()]},
            )

        fake_celery = SimpleNamespace(control=SimpleNamespace(inspect=inspect))

        with patch("api.workers.celery_app.celery_app", fake_celery):
            summary = await get_task_queue_summary()

        assert [task.id for task in summary.active] == ["a1"]
        assert summary.active[0].status == "active"
        assert [task.id for task in summary.reserved] == ["r1"]
        assert summary.scheduled_count == 2

        def failing_inspect(timeout):
            raise RuntimeError("celery unavailable")

        failing_celery = SimpleNamespace(control=SimpleNamespace(inspect=failing_inspect))

        with patch("api.workers.celery_app.celery_app", failing_celery):
            summary = await get_task_queue_summary()

        assert summary.active == []
        assert summary.reserved == []
        assert summary.scheduled_count == 0

    @pytest.mark.asyncio
    async def test_get_task_queue_summary_reports_cloud_tasks_as_managed_backend(self):
        settings = SimpleNamespace(
            pipeline_dispatch="cloud_tasks",
            gcp_project_id="praviar-prod",
            gcp_region="us-central1",
            cloud_tasks_queue_id="analysis-jobs",
            workers_service_url="https://workers.praviar.io",
            tasks_invoker_sa_email="tasks@praviar-prod.iam.gserviceaccount.com",
        )

        with patch("api.services.admin.get_settings", return_value=settings):
            summary = await get_task_queue_summary()

        assert summary.backend == "cloud_tasks"
        assert summary.inspectable is False
        assert summary.active == []
        assert summary.reserved == []
        assert summary.scheduled_count == 0
        assert "analysis-jobs" in summary.detail
