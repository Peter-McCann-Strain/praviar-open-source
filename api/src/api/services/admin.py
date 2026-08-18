"""Business logic for admin dashboard queries and mutations."""

from __future__ import annotations

import uuid

import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.schemas.admin import InviteRequest, UpdateOrgRequest, UpdateUserRoleRequest
from api.services import (
    admin_audit,
    admin_health,
    admin_orgs,
    admin_users,
)
from api.services.admin_health import (
    AdminAuditLogPage,
    AdminMetricsSummary,
    AdminOrgPage,
    AdminSystemHealthSummary,
    AdminTaskQueueSummary,
    AdminUserPage,
)


async def get_org_metrics(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    now=None,
    window_days: int = 30,
) -> AdminMetricsSummary:
    return await admin_health.get_org_metrics_impl(
        db,
        org_id=org_id,
        now=now,
        window_days=window_days,
    )


async def get_system_health(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    include_topology: bool = False,
) -> AdminSystemHealthSummary:
    return await admin_health.get_system_health_impl(
        db,
        settings=get_settings(),
        redis_from_url=aioredis.from_url,
        org_id=org_id,
        include_topology=include_topology,
    )


async def list_audit_logs_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    action: str | None,
    user_id: uuid.UUID | None,
    page: int,
    per_page: int,
) -> AdminAuditLogPage:
    return await admin_audit.list_audit_logs_page_impl(
        db,
        org_id=org_id,
        action=action,
        user_id=user_id,
        page=page,
        per_page=per_page,
    )


async def get_task_queue_summary() -> AdminTaskQueueSummary:
    return admin_health.get_task_queue_summary_impl(settings=get_settings())


async def list_organizations_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    page: int,
    per_page: int,
) -> AdminOrgPage:
    return await admin_orgs.list_organizations_page_impl(
        db,
        org_id=org_id,
        page=page,
        per_page=per_page,
    )


async def update_organization_for_admin(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: UpdateOrgRequest,
    allow_cross_org: bool = False,
) -> None:
    await admin_orgs.update_organization_for_admin_impl(
        db,
        org_id=org_id,
        admin_org_id=admin_org_id,
        admin_id=admin_id,
        body=body,
        write_audit_log_fn=write_audit_log,
        allow_cross_org=allow_cross_org,
    )


async def list_users_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None,
    page: int,
    per_page: int,
) -> AdminUserPage:
    return await admin_users.list_users_page_impl(
        db,
        org_id=org_id,
        page=page,
        per_page=per_page,
    )


async def update_user_role_for_admin(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: UpdateUserRoleRequest,
    idempotency_key: str | None = None,
) -> None:
    await admin_users.update_user_role_for_admin_impl(
        db,
        user_id=user_id,
        admin_org_id=admin_org_id,
        admin_id=admin_id,
        body=body,
        write_audit_log_fn=write_audit_log,
        settings=get_settings(),
        http_client_cls=httpx.AsyncClient,
        idempotency_key=idempotency_key,
    )


async def invite_user_to_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: InviteRequest,
    idempotency_key: str | None = None,
) -> None:
    await admin_users.invite_user_to_org_impl(
        db,
        org_id=org_id,
        admin_id=admin_id,
        body=body,
        settings=get_settings(),
        http_client_cls=httpx.AsyncClient,
        write_audit_log_fn=write_audit_log,
        idempotency_key=idempotency_key,
    )


async def reconcile_admin_operation(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    operation_id: uuid.UUID,
    recovery_action: str | None = None,
) -> dict[str, object]:
    return await admin_users.reconcile_admin_operation_impl(
        db,
        org_id=org_id,
        admin_id=admin_id,
        operation_id=operation_id,
        recovery_action=recovery_action,
        settings=get_settings(),
        http_client_cls=httpx.AsyncClient,
        write_audit_log_fn=write_audit_log,
    )


async def list_admin_operations(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int = 50,
) -> dict[str, object]:
    return await admin_users.list_admin_operations_impl(
        db,
        org_id=org_id,
        limit=limit,
    )
