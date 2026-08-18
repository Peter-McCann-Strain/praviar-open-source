import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request

from api.config import get_settings
from api.db.models import User
from api.deps import DBSession, require_permission
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.admin import (
    AdminOperationListResponse,
    AdminOperationRecoveryRequest,
    AdminOperationStatus,
    AuditLogListResponse,
    InviteRequest,
    MetricsResponse,
    OrgListResponse,
    SystemHealthResponse,
    TaskQueueResponse,
    UpdateOrgRequest,
    UpdateUserRoleRequest,
    UserListResponse,
)
from api.schemas.common import StatusResponse
from api.services.admin import (
    get_org_metrics,
    get_system_health,
    get_task_queue_summary,
    invite_user_to_org,
    list_admin_operations,
    reconcile_admin_operation,
    update_organization_for_admin,
    update_user_role_for_admin,
)
from api.services.admin import (
    list_audit_logs_page as list_admin_audit_logs_page,
)
from api.services.admin import (
    list_organizations_page as list_admin_organizations_page,
)
from api.services.admin import (
    list_users_page as list_admin_users_page,
)
from api.services.claimed_use_ledger_client import call_claimed_use_ledger
from api.services.offboarding import (
    authorize_platform_org_erasure,
    cancel_org_deletion,
    execute_org_erasure,
    get_org_offboarding_status,
    persist_claimed_use_erasure_authorization,
    schedule_org_deletion,
)

logger = structlog.get_logger()

router = APIRouter()

AdminUser = Annotated[User, Depends(require_permission("admin.view"))]
AdminManager = Annotated[User, Depends(require_permission("admin.manage_users"))]

_PROBLEM_4XX = {
    "401": {
        "description": "Authentication required",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "403": {
        "description": "Forbidden -- admin role required",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "404": {
        "description": "Not found",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "422": {
        "description": "Validation error",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "429": {
        "description": "Rate limit exceeded",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
}


def _is_platform_superadmin(user: User) -> bool:
    platform_admin_ids = set(get_settings().platform_admin_user_ids)
    return bool(platform_admin_ids and user.id in platform_admin_ids)


def _tenant_admin_org_scope(user: User) -> uuid.UUID | None:
    return None if _is_platform_superadmin(user) else user.org_id


def _tenant_admin_user_scope(
    user: User,
    requested_org_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if _is_platform_superadmin(user):
        return requested_org_id
    if requested_org_id is not None and requested_org_id != user.org_id:
        raise APIError(403, "Forbidden", "Tenant admins cannot list users outside their org")
    return user.org_id


def _admin_capabilities(user: User) -> dict:
    is_platform_superadmin = _is_platform_superadmin(user)
    return {
        "admin_org_id": user.org_id,
        "is_platform_superadmin": is_platform_superadmin,
        "can_manage_org_billing": is_platform_superadmin,
        "can_list_cross_org_users": is_platform_superadmin,
        # Cross-org role mutation is intentionally not enabled by the current
        # service contract; expose that truth so the UI can stay read-only.
        "can_manage_cross_org_user_roles": False,
        "can_inspect_task_queue": is_platform_superadmin,
    }


# ── System Health ─────────────────────────────────────────────────────────────


@router.get(
    "/admin/health",
    response_model=SystemHealthResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def admin_health(request: Request, user: AdminUser, db: DBSession) -> dict:
    """System health: DB, Redis, table counts."""
    org_scope = _tenant_admin_org_scope(user)
    if org_scope is None:
        logger.warning(
            "superadmin_cross_tenant_access",
            user_id=str(user.id),
            endpoint=request.url.path,
        )
    summary = await get_system_health(
        db,
        org_id=org_scope,
        include_topology=org_scope is None,
    )
    return {"services": summary.services, "table_counts": summary.table_counts}


# ── Organizations ─────────────────────────────────────────────────────────────


@router.get(
    "/admin/organizations",
    response_model=OrgListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_organizations(
    request: Request,
    user: AdminUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    """List organizations with usage stats, scoped to tenant admins by default."""
    org_scope = _tenant_admin_org_scope(user)
    if org_scope is None:
        logger.warning(
            "superadmin_cross_tenant_access",
            user_id=str(user.id),
            endpoint=request.url.path,
        )
    page_result = await list_admin_organizations_page(
        db,
        org_id=org_scope,
        page=page,
        per_page=per_page,
    )
    return {
        "items": page_result.items,
        "total": page_result.total,
        "capabilities": _admin_capabilities(user),
    }


@router.patch(
    "/admin/organizations/{org_id}",
    response_model=StatusResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def update_organization(
    org_id: uuid.UUID,
    body: UpdateOrgRequest,
    user: AdminManager,
    db: DBSession,
) -> dict:
    """Update org plan or limits."""
    billing_fields_requested = (
        body.plan is not None
        or body.max_analyses_per_month is not None
        or body.free_analyses_remaining is not None
    )
    if billing_fields_requested and not _is_platform_superadmin(user):
        raise APIError(
            403,
            "Forbidden",
            "Changing plan or quota requires platform superadmin access",
        )
    await update_organization_for_admin(
        db,
        org_id=org_id,
        admin_org_id=user.org_id,
        admin_id=user.id,
        body=body,
        allow_cross_org=_is_platform_superadmin(user),
    )
    return {"status": "updated"}


# ── Users ─────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/users",
    response_model=UserListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_users(
    request: Request,
    user: AdminUser,
    db: DBSession,
    org_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    """List users, scoped to the caller's org unless they are a platform superadmin."""
    scoped_org_id = _tenant_admin_user_scope(user, org_id)
    if _is_platform_superadmin(user):
        logger.warning(
            "superadmin_cross_tenant_access",
            user_id=str(user.id),
            endpoint=request.url.path,
        )
    page_result = await list_admin_users_page(
        db,
        org_id=scoped_org_id,
        page=page,
        per_page=per_page,
    )
    return {
        "items": page_result.items,
        "total": page_result.total,
        "capabilities": _admin_capabilities(user),
    }


@router.patch(
    "/admin/users/{user_id}/role",
    response_model=StatusResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def update_user_role(
    user_id: uuid.UUID,
    body: UpdateUserRoleRequest,
    admin: AdminManager,
    db: DBSession,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[!-~]+$",
        ),
    ],
) -> dict:
    """Change a user's role."""
    await update_user_role_for_admin(
        db,
        user_id=user_id,
        admin_org_id=admin.org_id,
        admin_id=admin.id,
        body=body,
        idempotency_key=idempotency_key,
    )
    return {"status": "updated"}


@router.post(
    "/admin/invite",
    response_model=StatusResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
@limiter.limit("5/minute")
async def invite_user(
    body: InviteRequest,
    admin: AdminManager,
    db: DBSession,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[!-~]+$",
        ),
    ],
) -> dict:
    """Send an invitation to join the platform.

    When Clerk is configured, uses the Clerk Backend API to create an invitation.
    In dev mode, creates a local user directly.

    Supply an ``Idempotency-Key`` header in every environment (16–128 visible
    ASCII characters; a UUID is suitable). Praviar durably records the call
    boundary and reconciles exact Clerk state; it does not rely on undocumented
    provider idempotency behavior.
    """
    await invite_user_to_org(
        db,
        org_id=admin.org_id,
        admin_id=admin.id,
        body=body,
        idempotency_key=idempotency_key,
    )
    return {"status": "invited"}


@router.get(
    "/admin/operations",
    response_model=AdminOperationListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_admin_mutations(
    admin: AdminManager,
    db: DBSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    """List recent durable mutation states for refresh-safe admin recovery."""
    return await list_admin_operations(db, org_id=admin.org_id, limit=limit)


@router.post(
    "/admin/operations/{operation_id}/reconcile",
    response_model=AdminOperationStatus,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def reconcile_admin_mutation(
    operation_id: uuid.UUID,
    admin: AdminManager,
    db: DBSession,
    body: AdminOperationRecoveryRequest | None = None,
) -> dict[str, object]:
    """Fetch exact Clerk state and converge one ambiguous durable mutation."""
    return await reconcile_admin_operation(
        db,
        org_id=admin.org_id,
        admin_id=admin.id,
        operation_id=operation_id,
        recovery_action=body.recovery_action if body is not None else None,
    )


# ── Metrics ───────────────────────────────────────────────────────────────────


@router.get(
    "/admin/metrics",
    response_model=MetricsResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def get_metrics(user: AdminUser, db: DBSession) -> dict:
    """Aggregated metrics for the last 30 days."""
    summary = await get_org_metrics(db, org_id=user.org_id)
    return {
        "daily": summary.daily,
        "total_analyses": summary.total_analyses,
        "total_cost": summary.total_cost,
        "avg_duration_seconds": summary.avg_duration_seconds,
        "error_rate": summary.error_rate,
    }


# ── Audit Logs ────────────────────────────────────────────────────────────────


@router.get(
    "/admin/audit-logs",
    response_model=AuditLogListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_audit_logs(
    user: AdminUser,
    db: DBSession,
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    """Searchable, filterable audit log viewer."""
    audit_page = await list_admin_audit_logs_page(
        db,
        org_id=user.org_id,
        action=action,
        user_id=user_id,
        page=page,
        per_page=per_page,
    )
    return {"items": audit_page.items, "total": audit_page.total}


# ── Worker Task Queue ─────────────────────────────────────────────────────────


@router.get(
    "/admin/tasks",
    response_model=TaskQueueResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def get_task_queue(user: AdminUser) -> dict:
    """Worker task queue status."""
    if not _is_platform_superadmin(user):
        return {
            "backend": "restricted",
            "detail": "Task queue inspection is platform-admin only.",
            "inspectable": False,
            "active": [],
            "reserved": [],
            "scheduled_count": 0,
        }

    summary = await get_task_queue_summary()
    return {
        "backend": summary.backend,
        "detail": summary.detail,
        "inspectable": summary.inspectable,
        "active": summary.active,
        "reserved": summary.reserved,
        "scheduled_count": summary.scheduled_count,
    }


# ── Tenant Offboarding (GDPR / data erasure) ─────────────────────────────────


@router.get(
    "/admin/organizations/{org_id}/offboard",
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Get org offboarding/deletion status",
)
async def get_offboarding_status(
    org_id: uuid.UUID,
    user: AdminUser,
    db: DBSession,
) -> dict:
    """Return the current deletion/erasure status for an organisation."""
    if not _is_platform_superadmin(user):
        raise APIError(403, "Forbidden", "Tenant offboarding requires platform admin access")
    return await get_org_offboarding_status(db, org_id=org_id)


@router.post(
    "/admin/organizations/{org_id}/offboard",
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Schedule org deletion (30-day erasure grace period)",
    status_code=202,
)
async def schedule_offboarding(
    org_id: uuid.UUID,
    user: AdminUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Schedule org data erasure with a 30-day grace period (GDPR Art. 17).

    The org's data will be soft-deleted after the grace period unless cancelled.
    """
    if not _is_platform_superadmin(user):
        raise APIError(403, "Forbidden", "Tenant offboarding requires platform admin access")
    logger.warning(
        "superadmin_cross_tenant_access",
        user_id=str(user.id),
        endpoint=request.url.path,
        action="schedule_offboarding",
    )
    return await schedule_org_deletion(
        db,
        org_id=org_id,
        requested_by_user_id=user.id,
        requested_by_email=user.email,
        request=request,
    )


@router.delete(
    "/admin/organizations/{org_id}/offboard",
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Cancel a pending org deletion",
)
async def cancel_offboarding(
    org_id: uuid.UUID,
    user: AdminUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Cancel a scheduled deletion during the 30-day grace period."""
    if not _is_platform_superadmin(user):
        raise APIError(403, "Forbidden", "Tenant offboarding requires platform admin access")
    return await cancel_org_deletion(
        db,
        org_id=org_id,
        cancelled_by_user_id=user.id,
        cancelled_by_email=user.email,
        request=request,
    )


@router.post(
    "/admin/organizations/{org_id}/erase",
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Execute immediate data erasure (platform superadmin only)",
    status_code=200,
)
async def execute_erasure(
    org_id: uuid.UUID,
    user: AdminUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Immediately erase all org data (bypasses grace period).

    Use only for explicit customer erasure requests or regulatory orders.
    """
    if not _is_platform_superadmin(user):
        raise APIError(403, "Forbidden", "Data erasure requires platform admin access")
    logger.warning(
        "superadmin_cross_tenant_access",
        user_id=str(user.id),
        endpoint=request.url.path,
        action="execute_erasure",
        org_id=str(org_id),
    )
    if get_settings().app_env == "prod":
        authorization = authorize_platform_org_erasure(
            org_id=org_id,
            actor_user_id=user.id,
            actor_email=user.email,
        )
        authorization = await persist_claimed_use_erasure_authorization(
            db,
            authorization=authorization,
        )
        return await call_claimed_use_ledger(
            operation="erase-org",
            payload={
                "authorization_id": str(authorization.authorization_id),
                "request_id": str(authorization.request_id),
                "org_id": str(authorization.org_id),
                "actor_user_id": str(user.id),
                "authorized_at": authorization.authorized_at.isoformat(),
                "capability_secret": authorization.capability_secret,
            },
        )
    return await execute_org_erasure(
        db,
        org_id=org_id,
        executed_by_user_id=user.id,
        executed_by_email=user.email,
        request=request,
    )
