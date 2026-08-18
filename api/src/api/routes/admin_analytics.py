"""Admin analytics routes for LLM cost dashboard and usage tracking."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.config import get_settings
from api.db.models import User
from api.deps import DBSession, require_permission
from api.errors import APIError
from api.schemas.admin_analytics import (
    AuditLogListExtendedResponse,
    CostBreakdownResponse,
    ModelUsageResponse,
    UsageAnalyticsResponse,
)
from api.services.admin_analytics import (
    get_audit_log_page,
    get_cost_breakdown_summary,
    get_model_usage_summary,
    get_usage_analytics_summary,
    render_audit_log_csv,
)

router = APIRouter()

AdminUser = Annotated[User, Depends(require_permission("admin.view"))]
OPTIONAL_UUID_QUERY = Query(None)


def _is_platform_superadmin(user: User) -> bool:
    platform_admin_ids = set(get_settings().platform_admin_user_ids)
    return bool(platform_admin_ids and user.id in platform_admin_ids)


def _tenant_admin_org_scope(user: User) -> uuid.UUID | None:
    return None if _is_platform_superadmin(user) else user.org_id


def _tenant_admin_requested_org_scope(
    user: User,
    requested_org_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if _is_platform_superadmin(user):
        return requested_org_id
    if requested_org_id is not None and requested_org_id != user.org_id:
        raise APIError(403, "Forbidden", "Tenant admins cannot inspect analytics outside their org")
    return user.org_id


# ── Cost Breakdown ───────────────────────────────────────────────────────────


@router.get("/admin/analytics/costs", response_model=CostBreakdownResponse)
async def get_cost_breakdown(
    user: AdminUser,
    db: DBSession,
    period: str = Query("month", pattern="^(day|week|month|quarter)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    org_id: uuid.UUID | None = OPTIONAL_UUID_QUERY,
) -> dict:
    """Cost breakdown by day, pipeline step, and LLM model.

    Aggregates from Analysis table cost tracking columns.
    """
    try:
        summary = await get_cost_breakdown_summary(
            db,
            period=period,
            start_date=start_date,
            end_date=end_date,
            org_id=_tenant_admin_requested_org_scope(user, org_id),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    return {
        "daily_costs": summary.daily_costs,
        "step_costs": summary.step_costs,
        "model_costs": summary.model_costs,
        "total_cost_usd": summary.total_cost_usd,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "period": summary.period,
        "start_date": summary.start_date,
        "end_date": summary.end_date,
    }


# ── Usage Analytics ──────────────────────────────────────────────────────────


@router.get("/admin/analytics/usage", response_model=UsageAnalyticsResponse)
async def get_usage_analytics(
    user: AdminUser,
    db: DBSession,
    period: str = Query("month", pattern="^(day|week|month|quarter)$"),
) -> dict:
    """Usage statistics: analyses by org, status, compound, and averages."""
    summary = await get_usage_analytics_summary(
        db,
        period=period,
        org_id=_tenant_admin_org_scope(user),
    )
    return {
        "org_usage": summary.org_usage,
        "status_breakdown": summary.status_breakdown,
        "top_compounds": summary.top_compounds,
        "total_analyses": summary.total_analyses,
        "avg_cost_per_analysis": summary.avg_cost_per_analysis,
        "avg_duration_seconds": summary.avg_duration_seconds,
        "period": summary.period,
    }


# ── Model Usage ──────────────────────────────────────────────────────────────


@router.get("/admin/analytics/models", response_model=ModelUsageResponse)
async def get_model_usage(
    user: AdminUser,
    db: DBSession,
    period: str = Query("month", pattern="^(day|week|month|quarter)$"),
) -> dict:
    """LLM model usage breakdown with token counts and cost estimates."""
    summary = await get_model_usage_summary(
        db,
        period=period,
        org_id=_tenant_admin_org_scope(user),
    )
    return {
        "models": summary.models,
        "total_tokens": summary.total_tokens,
        "total_cost_usd": summary.total_cost_usd,
        "overall_cache_hit_rate": summary.overall_cache_hit_rate,
        "period": summary.period,
    }


# ── Audit Log (Extended) ────────────────────────────────────────────────────


@router.get("/admin/analytics/audit-log")
async def get_audit_log(
    user: AdminUser,
    db: DBSession,
    action: str | None = Query(None),
    user_id: uuid.UUID | None = OPTIONAL_UUID_QUERY,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    accept: str | None = Header(None),
):
    """Paginated audit log with filters and CSV export.

    Send Accept: text/csv header to get CSV output.
    """
    try:
        page_result = await get_audit_log_page(
            db,
            action=action,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
            sort=sort,
            org_id=_tenant_admin_org_scope(user),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # CSV export
    if accept and "text/csv" in accept:
        return StreamingResponse(
            iter([render_audit_log_csv(page_result.items)]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
        )

    return AuditLogListExtendedResponse(
        items=page_result.items,
        total=page_result.total,
        page=page_result.page,
        per_page=page_result.per_page,
        has_next=page_result.has_next,
    )
