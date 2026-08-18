"""Tests for /api/v1/admin routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from conftest import make_user

from api.db.models import UserRole
from api.errors import APIError
from api.routes.admin import _tenant_admin_user_scope
from api.schemas.admin import AuditLogEntry, OrgSummary, ServiceHealth, TaskInfo, UserSummary
from api.services.admin import (
    AdminAuditLogPage,
    AdminMetricsSummary,
    AdminOrgPage,
    AdminSystemHealthSummary,
    AdminTaskQueueSummary,
    AdminUserPage,
)


@pytest.mark.parametrize(
    ("method", "endpoint"),
    [
        ("GET", "/api/v1/admin/metrics"),
        ("GET", "/api/v1/admin/health"),
        ("GET", "/api/v1/admin/audit-logs"),
        ("GET", "/api/v1/admin/organizations"),
        ("GET", "/api/v1/admin/tasks"),
    ],
)
@pytest.mark.asyncio
async def test_admin_endpoint_requires_admin(scientist_client, method, endpoint):
    """Admin routes must reject non-admin callers with 403.

    Replaces the per-route ``test_*_admin_only`` boilerplate that previously
    repeated the same assertion across five separate test classes.
    """
    c, _db = scientist_client
    resp = await c.request(method, endpoint)
    assert resp.status_code == 403, f"{method} {endpoint} should be admin-only"


class TestAdminMetricsRoute:
    @pytest.mark.asyncio
    async def test_get_metrics_returns_service_payload(self, admin_client):
        c, _db = admin_client
        summary = AdminMetricsSummary(
            daily=[],
            total_analyses=7,
            total_cost=12.5,
            avg_duration_seconds=44.0,
            error_rate=0.1429,
        )

        with patch(
            "api.routes.admin.get_org_metrics",
            new=AsyncMock(return_value=summary),
        ) as get_metrics_mock:
            resp = await c.get("/api/v1/admin/metrics")

        assert resp.status_code == 200
        assert resp.json() == {
            "daily": [],
            "total_analyses": 7,
            "total_cost": 12.5,
            "avg_duration_seconds": 44.0,
            "error_rate": 0.1429,
        }
        assert get_metrics_mock.await_count == 1


class TestAdminHealthRoute:
    @pytest.mark.asyncio
    async def test_admin_health_returns_service_payload(self, admin_client):
        c, _db = admin_client
        summary = AdminSystemHealthSummary(
            services=[
                ServiceHealth(name="database", status="ok"),
                ServiceHealth(name="redis", status="ok"),
            ],
            table_counts={"organizations": 2, "users": 5, "analyses": 9},
        )

        with patch(
            "api.routes.admin.get_system_health",
            new=AsyncMock(return_value=summary),
        ) as get_health_mock:
            resp = await c.get("/api/v1/admin/health")

        assert resp.status_code == 200
        assert resp.json() == {
            "services": [
                {"name": "database", "status": "ok", "detail": ""},
                {"name": "redis", "status": "ok", "detail": ""},
            ],
            "table_counts": {"organizations": 2, "users": 5, "analyses": 9},
        }
        assert get_health_mock.await_count == 1
        assert get_health_mock.await_args is not None
        assert get_health_mock.await_args.kwargs["org_id"] is not None
        assert get_health_mock.await_args.kwargs["include_topology"] is False

    @pytest.mark.asyncio
    async def test_platform_superadmin_health_can_use_global_counts(self, admin_client):
        c, _db = admin_client
        summary = AdminSystemHealthSummary(services=[], table_counts={})

        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.get_system_health",
                new=AsyncMock(return_value=summary),
            ) as get_health_mock,
        ):
            resp = await c.get("/api/v1/admin/health")

        assert resp.status_code == 200
        assert get_health_mock.await_args is not None
        assert get_health_mock.await_args.kwargs["org_id"] is None
        assert get_health_mock.await_args.kwargs["include_topology"] is True


class TestAdminAuditLogsRoute:
    @pytest.mark.asyncio
    async def test_list_audit_logs_returns_service_payload(self, admin_client):
        c, _db = admin_client
        log_id = uuid.uuid4()
        entry = AuditLogEntry(
            id=log_id,
            action="analysis.deleted",
            user_id=None,
            user_email="",
            analysis_id=None,
            details={"source": "admin"},
            ip_address="127.0.0.1",
            created_at=datetime(2026, 4, 11, tzinfo=UTC),
        )
        page = AdminAuditLogPage(items=[entry], total=1)

        with patch(
            "api.routes.admin.list_admin_audit_logs_page",
            new=AsyncMock(return_value=page),
        ) as list_logs_mock:
            resp = await c.get("/api/v1/admin/audit-logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(log_id)
        assert data["items"][0]["action"] == "analysis.deleted"
        assert data["items"][0]["details"] == {"source": "admin"}
        assert list_logs_mock.await_count == 1


class TestAdminOrganizationsRoute:
    @pytest.mark.asyncio
    async def test_list_organizations_returns_service_payload(self, admin_client):
        c, _db = admin_client
        org_id = uuid.uuid4()
        page = AdminOrgPage(
            items=[
                OrgSummary(
                    id=org_id,
                    name="Praviar Labs",
                    slug="praviar-labs",
                    plan="starter",
                    user_count=3,
                    analysis_count=9,
                    max_analyses_per_month=25,
                    free_analyses_remaining=2,
                    created_at=datetime(2026, 4, 11, tzinfo=UTC),
                )
            ],
            total=1,
        )

        with patch(
            "api.routes.admin.list_admin_organizations_page",
            new=AsyncMock(return_value=page),
        ) as list_orgs_mock:
            resp = await c.get("/api/v1/admin/organizations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(org_id)
        assert data["items"][0]["plan"] == "starter"
        assert data["items"][0]["user_count"] == 3
        assert data["capabilities"]["is_platform_superadmin"] is False
        assert data["capabilities"]["can_manage_org_billing"] is False
        assert data["capabilities"]["can_inspect_task_queue"] is False
        assert list_orgs_mock.await_count == 1
        assert list_orgs_mock.await_args is not None
        assert list_orgs_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_platform_superadmin_can_list_all_organizations(self, admin_client):
        c, _db = admin_client
        page = AdminOrgPage(items=[], total=0)

        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.list_admin_organizations_page",
                new=AsyncMock(return_value=page),
            ) as list_orgs_mock,
        ):
            resp = await c.get("/api/v1/admin/organizations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["capabilities"]["is_platform_superadmin"] is True
        assert data["capabilities"]["can_manage_org_billing"] is True
        assert data["capabilities"]["can_inspect_task_queue"] is True
        assert list_orgs_mock.await_args is not None
        assert list_orgs_mock.await_args.kwargs["org_id"] is None

    @pytest.mark.asyncio
    async def test_update_organization_returns_status(self, admin_client):
        c, _db = admin_client
        org_id = uuid.uuid4()

        # plan/quota changes require platform superadmin — patch the gate so the
        # test exercises the service layer, not the auth check.
        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.update_organization_for_admin",
                new=AsyncMock(),
            ) as update_org_mock,
        ):
            resp = await c.patch(
                f"/api/v1/admin/organizations/{org_id}",
                json={"plan": "pro", "max_analyses_per_month": 100},
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "updated"}
        assert update_org_mock.await_count == 1
        assert update_org_mock.await_args is not None
        assert update_org_mock.await_args.kwargs["org_id"] == org_id

    @pytest.mark.asyncio
    async def test_update_organization_plan_forbidden_for_tenant_admin(self, admin_client):
        c, _db = admin_client
        org_id = uuid.uuid4()

        with patch("api.routes.admin._is_platform_superadmin", return_value=False):
            resp = await c.patch(
                f"/api/v1/admin/organizations/{org_id}",
                json={"plan": "enterprise"},
            )

        assert resp.status_code == 403


class TestAdminUsersRoute:
    @pytest.mark.asyncio
    async def test_list_users_returns_service_payload(self, admin_client):
        c, _db = admin_client
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        page = AdminUserPage(
            items=[
                UserSummary(
                    id=user_id,
                    email="attorney@praviar.io",
                    full_name="Lead Counsel",
                    role="attorney",
                    org_id=org_id,
                    org_name="Praviar Labs",
                    last_active_at=None,
                    created_at=datetime(2026, 4, 11, tzinfo=UTC),
                )
            ],
            total=1,
        )

        with patch(
            "api.routes.admin.list_admin_users_page",
            new=AsyncMock(return_value=page),
        ) as list_users_mock:
            resp = await c.get("/api/v1/admin/users")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(user_id)
        assert data["items"][0]["org_name"] == "Praviar Labs"
        assert data["items"][0]["role"] == "attorney"
        assert data["capabilities"]["admin_org_id"]
        assert data["capabilities"]["can_list_cross_org_users"] is False
        assert data["capabilities"]["can_manage_cross_org_user_roles"] is False
        assert list_users_mock.await_count == 1
        assert list_users_mock.await_args is not None
        assert list_users_mock.await_args.kwargs["org_id"] is not None

    @pytest.mark.asyncio
    async def test_platform_superadmin_can_list_users_across_orgs(self, admin_client):
        c, _db = admin_client
        page = AdminUserPage(items=[], total=0)

        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.list_admin_users_page",
                new=AsyncMock(return_value=page),
            ) as list_users_mock,
        ):
            resp = await c.get("/api/v1/admin/users")

        assert resp.status_code == 200
        data = resp.json()
        assert data["capabilities"]["is_platform_superadmin"] is True
        assert data["capabilities"]["can_list_cross_org_users"] is True
        assert data["capabilities"]["can_manage_cross_org_user_roles"] is False
        assert list_users_mock.await_args is not None
        assert list_users_mock.await_args.kwargs["org_id"] is None

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_list_users_for_other_org(self, admin_client):
        c, _db = admin_client

        with patch("api.routes.admin.list_admin_users_page", new=AsyncMock()) as list_users_mock:
            resp = await c.get(f"/api/v1/admin/users?org_id={uuid.uuid4()}")

        assert resp.status_code == 403
        list_users_mock.assert_not_awaited()

    def test_tenant_admin_user_scope_defaults_to_own_org(self):
        user = make_user(role=UserRole.ADMIN)

        assert _tenant_admin_user_scope(user, None) == user.org_id

    def test_tenant_admin_user_scope_rejects_other_org(self):
        user = make_user(role=UserRole.ADMIN)

        with pytest.raises(APIError):
            _tenant_admin_user_scope(user, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_user_role_returns_status(self, admin_client):
        c, _db = admin_client
        user_id = uuid.uuid4()

        with patch(
            "api.routes.admin.update_user_role_for_admin",
            new=AsyncMock(),
        ) as update_role_mock:
            resp = await c.patch(
                f"/api/v1/admin/users/{user_id}/role",
                headers={"Idempotency-Key": "buyer-role-retry-123"},
                json={"role": "client"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "updated"}
        assert update_role_mock.await_count == 1
        assert update_role_mock.await_args is not None
        assert update_role_mock.await_args.kwargs["user_id"] == user_id
        assert update_role_mock.await_args.kwargs["idempotency_key"] == ("buyer-role-retry-123")


class TestAdminInviteRoute:
    @pytest.mark.asyncio
    async def test_invite_user_returns_status(self, admin_client):
        c, _db = admin_client

        with patch(
            "api.routes.admin.invite_user_to_org",
            new=AsyncMock(),
        ) as invite_user_mock:
            resp = await c.post(
                "/api/v1/admin/invite",
                headers={"Idempotency-Key": "invite-buyer-retry-123"},
                json={"email": "invitee@praviar.io", "role": "scientist"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "invited"}
        assert invite_user_mock.await_count == 1
        assert invite_user_mock.await_args is not None
        assert invite_user_mock.await_args.kwargs["body"].email == "invitee@praviar.io"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("path", "method", "json"),
        [
            (
                "/api/v1/admin/invite",
                "post",
                {"email": "invitee@praviar.io", "role": "scientist"},
            ),
            (
                f"/api/v1/admin/users/{uuid.uuid4()}/role",
                "patch",
                {"role": "client"},
            ),
        ],
    )
    async def test_buyer_mutations_require_valid_idempotency_key(
        self, admin_client, path: str, method: str, json: dict
    ):
        c, _db = admin_client
        request = getattr(c, method)

        missing = await request(path, json=json)
        short = await request(path, headers={"Idempotency-Key": "short"}, json=json)
        whitespace = await request(
            path,
            headers={"Idempotency-Key": "invalid key with spaces"},
            json=json,
        )

        assert missing.status_code == 422
        assert short.status_code == 422
        assert whitespace.status_code == 422

    @pytest.mark.asyncio
    async def test_reconcile_admin_operation_returns_authoritative_status(self, admin_client):
        c, _db = admin_client
        operation_id = uuid.uuid4()
        with patch(
            "api.routes.admin.reconcile_admin_operation",
            new=AsyncMock(
                return_value={
                    "operation_id": operation_id,
                    "operation_type": "invite",
                    "state": "completed",
                    "outcome_confirmed": True,
                    "reconciliation_required": False,
                    "provider_resource_id": "orginv_123",
                    "target_user_id": None,
                    "target_email_normalized": "buyer@example.com",
                    "requested_role": "client",
                    "updated_at": datetime.now(UTC),
                }
            ),
        ) as reconcile:
            response = await c.post(
                f"/api/v1/admin/operations/{operation_id}/reconcile",
            )

        assert response.status_code == 200
        assert response.json()["outcome_confirmed"] is True
        assert reconcile.await_args.kwargs["operation_id"] == operation_id

    @pytest.mark.asyncio
    async def test_list_admin_operations_is_org_scoped_and_refresh_safe(self, admin_client):
        c, _db = admin_client
        operation_id = uuid.uuid4()
        updated_at = datetime.now(UTC)
        with patch(
            "api.routes.admin.list_admin_operations",
            new=AsyncMock(
                return_value={
                    "items": [
                        {
                            "operation_id": operation_id,
                            "operation_type": "role_update",
                            "state": "role_call_started",
                            "outcome_confirmed": False,
                            "reconciliation_required": True,
                            "provider_resource_id": None,
                            "target_user_id": uuid.uuid4(),
                            "target_email_normalized": None,
                            "requested_role": "attorney",
                            "updated_at": updated_at,
                        }
                    ],
                    "open_total": 1,
                    "has_more": False,
                }
            ),
        ) as list_operations:
            response = await c.get("/api/v1/admin/operations")

        assert response.status_code == 200
        assert response.json()["items"][0]["operation_id"] == str(operation_id)
        assert response.json()["items"][0]["reconciliation_required"] is True
        assert list_operations.await_args.kwargs["org_id"] is not None


class TestAdminTaskQueueRoute:
    @pytest.mark.asyncio
    async def test_get_task_queue_returns_service_payload(self, admin_client):
        c, _db = admin_client
        summary = AdminTaskQueueSummary(
            active=[
                TaskInfo(
                    id="active-1",
                    name="api.tasks.run",
                    args=["org-1"],
                    status="active",
                )
            ],
            reserved=[
                TaskInfo(
                    id="reserved-1",
                    name="api.tasks.enqueue",
                    args=["org-2"],
                    status="reserved",
                )
            ],
            scheduled_count=3,
        )

        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.get_task_queue_summary",
                new=AsyncMock(return_value=summary),
            ) as get_queue_mock,
        ):
            resp = await c.get("/api/v1/admin/tasks")

        assert resp.status_code == 200
        assert resp.json() == {
            "backend": "celery",
            "detail": "",
            "inspectable": True,
            "active": [
                {
                    "id": "active-1",
                    "name": "api.tasks.run",
                    "args": ["org-1"],
                    "status": "active",
                }
            ],
            "reserved": [
                {
                    "id": "reserved-1",
                    "name": "api.tasks.enqueue",
                    "args": ["org-2"],
                    "status": "reserved",
                }
            ],
            "scheduled_count": 3,
        }
        assert get_queue_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_tenant_admin_task_queue_is_not_inspected(self, admin_client):
        c, _db = admin_client

        with patch("api.routes.admin.get_task_queue_summary", new=AsyncMock()) as get_queue_mock:
            resp = await c.get("/api/v1/admin/tasks")

        assert resp.status_code == 200
        assert resp.json() == {
            "backend": "restricted",
            "detail": "Task queue inspection is platform-admin only.",
            "inspectable": False,
            "active": [],
            "reserved": [],
            "scheduled_count": 0,
        }
        get_queue_mock.assert_not_awaited()


class TestAdminOffboardingRoutes:
    """Tests for GDPR tenant offboarding / data erasure endpoints."""

    ORG_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-000000000001")

    @pytest.mark.asyncio
    async def test_get_offboard_status_non_superadmin_returns_403(self, admin_client):
        c, _db = admin_client
        with patch("api.routes.admin._is_platform_superadmin", return_value=False):
            resp = await c.get(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_offboard_status_superadmin_returns_200(self, admin_client):
        c, _db = admin_client
        payload = {
            "org_id": str(self.ORG_ID),
            "org_name": "Acme Bio",
            "deletion_status": None,
            "deletion_scheduled_at": None,
            "deletion_requested_by": None,
        }
        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.get_org_offboarding_status",
                new=AsyncMock(return_value=payload),
            ),
        ):
            resp = await c.get(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 200
        assert resp.json()["org_name"] == "Acme Bio"

    @pytest.mark.asyncio
    async def test_schedule_offboarding_non_superadmin_returns_403(self, admin_client):
        c, _db = admin_client
        with patch("api.routes.admin._is_platform_superadmin", return_value=False):
            resp = await c.post(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_schedule_offboarding_superadmin_returns_202(self, admin_client):
        c, _db = admin_client
        payload = {
            "org_id": str(self.ORG_ID),
            "deletion_status": "pending",
            "deletion_scheduled_at": "2026-07-08T18:00:00+00:00",
            "message": "Organization data will be erased on 2026-07-08.",
        }
        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.schedule_org_deletion",
                new=AsyncMock(return_value=payload),
            ),
        ):
            resp = await c.post(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 202
        assert resp.json()["deletion_status"] == "pending"

    @pytest.mark.asyncio
    async def test_cancel_offboarding_non_superadmin_returns_403(self, admin_client):
        c, _db = admin_client
        with patch("api.routes.admin._is_platform_superadmin", return_value=False):
            resp = await c.delete(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cancel_offboarding_superadmin_returns_200(self, admin_client):
        c, _db = admin_client
        payload = {
            "org_id": str(self.ORG_ID),
            "deletion_status": None,
            "message": "Deletion cancelled",
        }
        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.cancel_org_deletion",
                new=AsyncMock(return_value=payload),
            ),
        ):
            resp = await c.delete(f"/api/v1/admin/organizations/{self.ORG_ID}/offboard")
        assert resp.status_code == 200
        assert resp.json()["deletion_status"] is None

    @pytest.mark.asyncio
    async def test_execute_erasure_non_superadmin_returns_403(self, admin_client):
        c, _db = admin_client
        with patch("api.routes.admin._is_platform_superadmin", return_value=False):
            resp = await c.post(f"/api/v1/admin/organizations/{self.ORG_ID}/erase")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_execute_erasure_superadmin_returns_200(self, admin_client):
        c, _db = admin_client
        payload = {
            "org_id": str(self.ORG_ID),
            "deletion_status": "erased",
            "message": "Organization data has been erased.",
        }
        with (
            patch("api.routes.admin._is_platform_superadmin", return_value=True),
            patch(
                "api.routes.admin.execute_org_erasure",
                new=AsyncMock(return_value=payload),
            ),
        ):
            resp = await c.post(f"/api/v1/admin/organizations/{self.ORG_ID}/erase")
        assert resp.status_code == 200
        assert resp.json()["deletion_status"] == "erased"
