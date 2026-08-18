"""Monitor and alert CRUD routes."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response, status

from api.db.models import Monitor, User
from api.deps import (
    AuthenticatedPrincipal,
    DBSession,
    require_permission,
    require_permission_or_api_key_scope,
)
from api.ratelimit import limiter
from api.schemas.common import StatusResponse
from api.schemas.monitors import (
    CreateMonitorRequest,
    MonitorAlertListResponse,
    MonitorConclusionReassessmentListResponse,
    MonitorConclusionReassessmentResponse,
    MonitorListResponse,
    MonitorResponse,
    MonitorRunResponse,
    ResolveMonitorConclusionRequest,
    RunMonitorRequest,
    UpdateMonitorRequest,
)
from api.services.monitor_reassessment_lifecycle import (
    list_monitor_conclusion_reassessments,
    resolve_monitor_conclusion,
)
from api.services.monitor_runtime import execute_monitor_run, get_monitor_for_run
from api.services.monitors import (
    create_monitor as create_monitor_record,
)
from api.services.monitors import (
    delete_monitor as delete_monitor_record,
)
from api.services.monitors import (
    dismiss_monitor_alert as dismiss_monitor_alert_record,
)
from api.services.monitors import (
    find_monitor_for_analysis,
    get_monitor_for_org,
    list_monitor_alerts_page,
    list_monitors_page,
)
from api.services.monitors import (
    update_monitor as update_monitor_record,
)

logger = structlog.get_logger()

router = APIRouter()

MonitorUser = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("monitor.manage", "monitors:manage")),
]
MonitorCounsel = Annotated[
    User,
    Depends(require_permission("reviewer_decision.view")),
]


# ── Monitors ─────────────────────────────────────────────────────────────────


@router.post("/monitors", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_monitor(
    body: CreateMonitorRequest,
    user: MonitorUser,
    db: DBSession,
    request: Request,
) -> Monitor:
    """Create a new compound monitor."""
    logger.info(
        "create_monitor",
        user_id=str(user.id),
        org_id=str(user.org_id),
        compound_smiles=body.compound_smiles[:100],
        analysis_id=str(body.analysis_id) if body.analysis_id else None,
    )

    return await create_monitor_record(
        db,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
    )


@router.get("/monitors", response_model=MonitorListResponse)
async def list_monitors(
    user: MonitorUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> dict:
    """List monitors for the current org."""
    result = await list_monitors_page(
        db,
        org_id=user.org_id,
        page=page,
        per_page=per_page,
        is_active=is_active,
    )
    return {"items": result.items, "total": result.total}


@router.get("/monitors/by-analysis/{analysis_id}", response_model=MonitorResponse | None)
async def get_monitor_by_analysis(
    analysis_id: uuid.UUID,
    user: MonitorUser,
    db: DBSession,
) -> Monitor | None:
    """Get the org's report-seeded monitor for an analysis, if one exists."""
    return await find_monitor_for_analysis(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: uuid.UUID,
    user: MonitorUser,
    db: DBSession,
) -> Monitor:
    """Get a single monitor."""
    return await get_monitor_for_org(db, monitor_id=monitor_id, org_id=user.org_id)


@router.get(
    "/monitors/{monitor_id}/conclusion-reassessments",
    response_model=MonitorConclusionReassessmentListResponse,
)
async def list_conclusion_reassessments(
    monitor_id: uuid.UUID,
    user: MonitorCounsel,
    db: DBSession,
) -> dict:
    """List the durable legal lifecycle for this watch's conclusions."""
    await get_monitor_for_org(db, monitor_id=monitor_id, org_id=user.org_id)
    rows = await list_monitor_conclusion_reassessments(
        db,
        monitor_id=monitor_id,
        org_id=user.org_id,
    )
    return {"items": rows, "total": len(rows)}


@router.post(
    "/monitors/{monitor_id}/conclusions/{conclusion_id}/reassess",
    response_model=MonitorConclusionReassessmentResponse,
)
async def reassess_conclusion(
    monitor_id: uuid.UUID,
    conclusion_id: str,
    body: ResolveMonitorConclusionRequest,
    user: MonitorCounsel,
    db: DBSession,
    request: Request,
) -> object:
    """Record an attorney-attested disposition for one stale conclusion."""
    return await resolve_monitor_conclusion(
        db,
        monitor_id=monitor_id,
        conclusion_id=conclusion_id,
        org_id=user.org_id,
        user=user,
        body=body,
        request=request,
    )


@router.patch("/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: uuid.UUID,
    body: UpdateMonitorRequest,
    user: MonitorUser,
    db: DBSession,
    request: Request,
) -> Monitor:
    """Update a monitor's schedule, active status, or compound name."""
    return await update_monitor_record(
        db,
        monitor_id=monitor_id,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
    )


@router.delete(
    "/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_monitor(
    monitor_id: uuid.UUID,
    user: MonitorUser,
    db: DBSession,
    request: Request,
) -> Response:
    """Hard-delete a monitor and its associated alerts."""
    await delete_monitor_record(
        db,
        monitor_id=monitor_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Monitor Alerts ───────────────────────────────────────────────────────────


@router.get("/monitors/{monitor_id}/alerts", response_model=MonitorAlertListResponse)
async def list_monitor_alerts(
    monitor_id: uuid.UUID,
    user: MonitorUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    dismissed: bool | None = Query(default=None),
) -> dict:
    """List alerts for a monitor."""
    result = await list_monitor_alerts_page(
        db,
        monitor_id=monitor_id,
        org_id=user.org_id,
        page=page,
        per_page=per_page,
        dismissed=dismissed,
    )
    return {"items": result.items, "total": result.total}


@router.post(
    "/monitors/{monitor_id}/alerts/{alert_id}/dismiss",
    response_model=StatusResponse,
)
async def dismiss_alert(
    monitor_id: uuid.UUID,
    alert_id: uuid.UUID,
    user: MonitorUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Dismiss an alert."""
    await dismiss_monitor_alert_record(
        db,
        monitor_id=monitor_id,
        alert_id=alert_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )
    return {"status": "dismissed"}


@router.post("/monitors/{monitor_id}/run", response_model=MonitorRunResponse)
@limiter.limit("5/minute")
async def run_monitor(
    monitor_id: uuid.UUID,
    body: RunMonitorRequest,
    user: MonitorUser,
    db: DBSession,
    request: Request,
) -> MonitorRunResponse:
    """Run a bounded low-cost monitoring pass for one monitor."""
    from fastapi import HTTPException

    from api.db.session import pinned_advisory_lock

    monitor = await get_monitor_for_run(
        db,
        monitor_id=monitor_id,
        org_id=user.org_id,
    )
    lock_key = monitor_id.int & ((1 << 63) - 1)
    async with pinned_advisory_lock(lock_key) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409, detail="A scan is already running for this monitor."
            )
        return await execute_monitor_run(
            db,
            monitor=monitor,
            force_full_refresh=body.force_full_refresh,
        )
