"""Organization admin helpers."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, Organization, User
from api.errors import APIError
from api.schemas.admin import OrgSummary, UpdateOrgRequest
from api.services.admin_health import AdminOrgPage

logger = structlog.get_logger()


def _build_organization_counts_subqueries():
    user_count_sq = select(User.org_id, func.count().label("cnt")).group_by(User.org_id).subquery()
    analysis_count_sq = (
        select(Analysis.org_id, func.count().label("cnt")).group_by(Analysis.org_id).subquery()
    )
    return user_count_sq, analysis_count_sq


async def _fetch_organizations_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None,
    page: int,
    per_page: int,
):
    offset = (page - 1) * per_page
    count_query = select(func.count()).select_from(Organization)
    if org_id is not None:
        count_query = count_query.where(Organization.id == org_id)
    total = (await db.execute(count_query)).scalar_one()
    user_count_sq, analysis_count_sq = _build_organization_counts_subqueries()
    items_query = (
        select(
            Organization,
            func.coalesce(user_count_sq.c.cnt, 0).label("user_count"),
            func.coalesce(analysis_count_sq.c.cnt, 0).label("analysis_count"),
        )
        .outerjoin(user_count_sq, Organization.id == user_count_sq.c.org_id)
        .outerjoin(analysis_count_sq, Organization.id == analysis_count_sq.c.org_id)
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    if org_id is not None:
        items_query = items_query.where(Organization.id == org_id)
    result = await db.execute(items_query)
    return total, result.all()


def _map_organization_row(row) -> OrgSummary:
    org, user_count, analysis_count = row
    return OrgSummary(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan.value,
        user_count=user_count,
        analysis_count=analysis_count,
        max_analyses_per_month=org.max_analyses_per_month,
        free_analyses_remaining=org.free_analyses_remaining,
        created_at=org.created_at,
    )


async def list_organizations_page_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    page: int,
    per_page: int,
) -> AdminOrgPage:
    total, rows = await _fetch_organizations_page(
        db,
        org_id=org_id,
        page=page,
        per_page=per_page,
    )
    items = [_map_organization_row(row) for row in rows]
    return AdminOrgPage(items=items, total=total)


async def _load_organization_for_admin(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    allow_cross_org: bool = False,
) -> Organization:
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if not org:
        raise APIError(404, "Not Found", "Organization not found")
    if not allow_cross_org and org.id != admin_org_id:
        raise APIError(403, "Forbidden", "Cannot modify other organizations")
    return org


def _apply_organization_updates(
    org: Organization,
    *,
    body: UpdateOrgRequest,
) -> None:
    if body.plan is not None:
        org.plan = body.plan
    if body.max_analyses_per_month is not None:
        org.max_analyses_per_month = body.max_analyses_per_month
    if body.free_analyses_remaining is not None:
        org.free_analyses_remaining = body.free_analyses_remaining


async def _write_org_update_audit(
    db: AsyncSession,
    *,
    org: Organization,
    admin_id: uuid.UUID,
    write_audit_log_fn,
) -> None:
    await write_audit_log_fn(
        db,
        org_id=org.id,
        user_id=admin_id,
        action="admin.organization.updated",
        details={
            "organization_id": str(org.id),
            "plan": org.plan.value,
            "max_analyses_per_month": org.max_analyses_per_month,
            "free_analyses_remaining": org.free_analyses_remaining,
        },
        fail_closed=True,
    )


async def update_organization_for_admin_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: UpdateOrgRequest,
    write_audit_log_fn,
    allow_cross_org: bool = False,
) -> None:
    org = await _load_organization_for_admin(
        db,
        org_id=org_id,
        admin_org_id=admin_org_id,
        allow_cross_org=allow_cross_org,
    )
    _apply_organization_updates(org, body=body)
    # When a superadmin modifies a different org, the FastAPI middleware has
    # bound app.current_org_id to the admin's own org.  The audit_logs table
    # has FORCE ROW LEVEL SECURITY with a WITH CHECK on app.current_org_id, so
    # an INSERT with org_id=target_org.id would violate the policy and roll
    # back the whole transaction.  Rebind to the target org before the audit
    # write, mirroring the pattern in offboarding.execute_org_erasure.
    if allow_cross_org and org.id != admin_org_id:
        await db.execute(select(func.set_config("app.current_org_id", str(org.id), True)))
    try:
        await _write_org_update_audit(
            db,
            org=org,
            admin_id=admin_id,
            write_audit_log_fn=write_audit_log_fn,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("admin_org_updated", org_id=str(org_id), admin_id=str(admin_id))
