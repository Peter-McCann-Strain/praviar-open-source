"""System health, metrics, and shared admin result models.

Consolidates the former admin health/metrics family:
  admin_runtime_status   -- low-level DB, Redis, Celery and Cloud Tasks checks
  admin_task_queue       -- worker task queue summary
  admin_metrics_helpers  -- pure aggregation helpers for org metrics
  admin_metrics          -- DB-backed org metrics queries
  admin_models           -- shared result dataclasses used across admin services
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Date as SqlDate
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.cache import redis_connection_kwargs
from api.db.models import Analysis, AnalysisStatus, Organization, User
from api.schemas.admin import (
    AuditLogEntry,
    DailyMetric,
    OrgSummary,
    ServiceHealth,
    TaskInfo,
    UserSummary,
)

logger = structlog.get_logger()

_DATABASE_HEALTH_ERROR_DETAIL = "Database health check failed"
_REDIS_HEALTH_ERROR_DETAIL = "Redis health check failed"
_CELERY_HEALTH_ERROR_DETAIL = "Worker health check failed"
_TASK_QUEUE_ERROR_DETAIL = "Task queue inspection failed"


# ---------------------------------------------------------------------------
# Shared result dataclasses  (formerly admin_models)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdminMetricsSummary:
    daily: list[DailyMetric]
    total_analyses: int
    total_cost: float
    avg_duration_seconds: float | None
    error_rate: float


@dataclass(frozen=True)
class AdminAuditLogPage:
    items: list[AuditLogEntry]
    total: int


@dataclass(frozen=True)
class AdminOrgPage:
    items: list[OrgSummary]
    total: int


@dataclass(frozen=True)
class AdminUserPage:
    items: list[UserSummary]
    total: int


@dataclass(frozen=True)
class AdminTaskQueueSummary:
    active: list[TaskInfo]
    reserved: list[TaskInfo]
    scheduled_count: int
    backend: str = "celery"
    detail: str = ""
    inspectable: bool = True


@dataclass(frozen=True)
class AdminSystemHealthSummary:
    services: list[ServiceHealth]
    table_counts: dict[str, int]


# ---------------------------------------------------------------------------
# Pure metrics helpers  (formerly admin_metrics_helpers)
# ---------------------------------------------------------------------------


def build_metrics_window_start(
    *,
    now: datetime | None,
    window_days: int,
) -> datetime:
    reference_time = now or datetime.now(UTC)
    return reference_time - timedelta(days=window_days)


def serialize_daily_metric_row(row) -> DailyMetric:
    return DailyMetric(
        date=str(row.date),
        count=row.count,
        cost=float(row.cost),
        errors=row.errors or 0,
    )


def build_admin_metrics_summary(
    *,
    daily: list[DailyMetric],
    total_analyses: int,
    total_cost: float | None,
    avg_duration_seconds: float | None,
    error_count: int | None,
) -> AdminMetricsSummary:
    resolved_total_cost = float(total_cost or 0.0)
    return AdminMetricsSummary(
        daily=daily,
        total_analyses=total_analyses,
        total_cost=resolved_total_cost,
        avg_duration_seconds=avg_duration_seconds,
        error_rate=round((error_count or 0) / max(total_analyses, 1), 4),
    )


# ---------------------------------------------------------------------------
# Low-level runtime-status checks  (formerly admin_runtime_status)
# ---------------------------------------------------------------------------


async def _check_database_health(db: AsyncSession) -> ServiceHealth:
    try:
        await db.execute(select(1))
        return ServiceHealth(name="database", status="ok")
    except Exception as exc:
        logger.warning(
            "admin_database_health_check_failed",
            error_type=type(exc).__name__,
        )
        return ServiceHealth(
            name="database",
            status="error",
            detail=_DATABASE_HEALTH_ERROR_DETAIL,
        )


async def _check_redis_health(
    *,
    redis_url: str,
    redis_from_url,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
) -> ServiceHealth:
    try:
        redis = redis_from_url(redis_url, **dict(redis_connection_kwargs or {}))
        try:
            await redis.ping()
            return ServiceHealth(name="redis", status="ok")
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.warning(
            "admin_redis_health_check_failed",
            error_type=type(exc).__name__,
        )
        return ServiceHealth(
            name="redis",
            status="error",
            detail=_REDIS_HEALTH_ERROR_DETAIL,
        )


def _check_celery_health() -> ServiceHealth:
    try:
        from api.workers.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=2)
        active_queues = inspect.active_queues()
        if active_queues is None:
            return ServiceHealth(
                name="celery",
                status="error",
                detail="No workers responding",
            )

        expected_queue = str(getattr(celery_app.conf, "task_default_queue", "celery"))
        eligible_workers = {
            worker
            for worker, queues in active_queues.items()
            if isinstance(queues, list)
            and any(
                isinstance(queue, dict) and queue.get("name") == expected_queue for queue in queues
            )
        }
        if eligible_workers:
            return ServiceHealth(
                name="celery",
                status="ok",
                detail=f"{len(eligible_workers)} worker(s) on required queue",
            )
        return ServiceHealth(
            name="celery",
            status="error",
            detail="No workers subscribed to required queue",
        )
    except Exception as exc:
        logger.warning(
            "admin_celery_health_check_failed",
            error_type=type(exc).__name__,
        )
        return ServiceHealth(
            name="celery",
            status="error",
            detail=_CELERY_HEALTH_ERROR_DETAIL,
        )


def _check_cloud_tasks_health(
    settings,
    *,
    include_topology: bool = False,
) -> ServiceHealth:
    required_fields = {
        "GCP_PROJECT_ID": getattr(settings, "gcp_project_id", ""),
        "GCP_REGION": getattr(settings, "gcp_region", ""),
        "CLOUD_TASKS_QUEUE_ID": getattr(settings, "cloud_tasks_queue_id", ""),
        "WORKERS_SERVICE_URL": getattr(settings, "workers_service_url", ""),
        "TASKS_INVOKER_SA_EMAIL": getattr(settings, "tasks_invoker_sa_email", ""),
    }
    missing = [name for name, value in required_fields.items() if not str(value or "").strip()]
    if missing:
        return ServiceHealth(
            name="cloud_tasks",
            status="error",
            detail=(
                f"Missing config: {', '.join(missing)}"
                if include_topology
                else "Cloud Tasks configuration incomplete"
            ),
        )

    return ServiceHealth(
        name="cloud_tasks",
        status="ok",
        detail=(
            (f"{settings.cloud_tasks_queue_id} in {settings.gcp_project_id}/{settings.gcp_region}")
            if include_topology
            else "Cloud Tasks configured"
        ),
    )


def _check_dispatcher_health(
    settings,
    *,
    include_topology: bool = False,
) -> ServiceHealth:
    dispatch_backend = getattr(settings, "pipeline_dispatch", "celery")
    if dispatch_backend == "cloud_tasks":
        return _check_cloud_tasks_health(settings, include_topology=include_topology)
    if dispatch_backend == "celery":
        return _check_celery_health()
    return ServiceHealth(
        name="task_dispatcher",
        status="error",
        detail=f"Unsupported PIPELINE_DISPATCH={dispatch_backend!r}",
    )


async def _collect_table_counts(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
) -> tuple[dict[str, int], list[str]]:
    table_counts: dict[str, int] = {}
    failed_tables: list[str] = []

    count_specs = [
        ("organizations", Organization, Organization.id),
        ("users", User, User.org_id),
        ("analyses", Analysis, Analysis.org_id),
    ]
    for table_name, model, scope_column in count_specs:
        try:
            query = select(func.count()).select_from(model)
            if org_id is not None:
                query = query.where(scope_column == org_id)
            result = await db.execute(query)
            table_counts[table_name] = result.scalar_one()
        except Exception as exc:
            failed_tables.append(table_name)
            logger.warning(
                "admin_health_table_count_failed",
                table=table_name,
                error_type=type(exc).__name__,
            )

    return table_counts, failed_tables


def task_from_celery_payload(payload: dict, *, status: str) -> TaskInfo:
    return TaskInfo(
        id=payload.get("id", ""),
        name=payload.get("name", ""),
        args=payload.get("args", []),
        status=status,
    )


def _inspect_celery_queue(*, inspect) -> AdminTaskQueueSummary:
    active_tasks = [
        task_from_celery_payload(task, status="active")
        for tasks in (inspect.active() or {}).values()
        for task in tasks
    ]
    reserved_tasks = [
        task_from_celery_payload(task, status="reserved")
        for tasks in (inspect.reserved() or {}).values()
        for task in tasks
    ]
    scheduled = inspect.scheduled() or {}
    scheduled_count = sum(len(tasks) for tasks in scheduled.values())

    return AdminTaskQueueSummary(
        active=active_tasks,
        reserved=reserved_tasks,
        scheduled_count=scheduled_count,
    )


# ---------------------------------------------------------------------------
# Task queue summary  (formerly admin_task_queue)
# ---------------------------------------------------------------------------


def _cloud_tasks_queue_summary(settings) -> AdminTaskQueueSummary:
    # The route that exposes task queue summaries explicitly requires platform
    # superadmin access, so operational topology is appropriate on this surface.
    health = _check_cloud_tasks_health(settings, include_topology=True)
    return AdminTaskQueueSummary(
        active=[],
        reserved=[],
        scheduled_count=0,
        backend="cloud_tasks",
        detail=(
            health.detail
            if health.status == "ok"
            else f"Cloud Tasks config is incomplete: {health.detail}"
        ),
        inspectable=False,
    )


def get_task_queue_summary_impl(*, settings) -> AdminTaskQueueSummary:
    """Return a summary of the current task queue state."""
    if getattr(settings, "pipeline_dispatch", "celery") == "cloud_tasks":
        return _cloud_tasks_queue_summary(settings)

    try:
        from api.workers.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=3)
        return _inspect_celery_queue(inspect=inspect)
    except Exception as exc:
        logger.warning(
            "admin_task_queue_error",
            error_type=type(exc).__name__,
        )
        return AdminTaskQueueSummary(
            active=[],
            reserved=[],
            scheduled_count=0,
            detail=_TASK_QUEUE_ERROR_DETAIL,
        )


# ---------------------------------------------------------------------------
# System health facade
# ---------------------------------------------------------------------------


async def get_system_health_impl(
    db: AsyncSession,
    *,
    settings,
    redis_from_url,
    org_id: uuid.UUID | None = None,
    include_topology: bool = False,
) -> AdminSystemHealthSummary:
    """Build a full system health summary from DB, Redis, and dispatcher checks."""
    services: list[ServiceHealth] = [
        await _check_database_health(db),
        await _check_redis_health(
            redis_url=settings.redis_url,
            redis_from_url=redis_from_url,
            redis_connection_kwargs=redis_connection_kwargs(settings),
        ),
        _check_dispatcher_health(settings, include_topology=include_topology),
    ]
    table_counts, failed_tables = await _collect_table_counts(db, org_id=org_id)

    if failed_tables:
        services.append(
            ServiceHealth(
                name="table_counts",
                status="error",
                detail=f"Failed tables: {', '.join(sorted(failed_tables))}",
            )
        )

    return AdminSystemHealthSummary(services=services, table_counts=table_counts)


# ---------------------------------------------------------------------------
# Org metrics facade  (formerly admin_metrics)
# ---------------------------------------------------------------------------


async def get_org_metrics_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    now: datetime | None = None,
    window_days: int = 30,
) -> AdminMetricsSummary:
    """Return daily and aggregate metrics for a single organisation."""
    window_start = build_metrics_window_start(now=now, window_days=window_days)

    daily_result = await db.execute(
        select(
            cast(Analysis.created_at, SqlDate).label("date"),
            func.count().label("count"),
            func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("cost"),
            func.sum(func.cast(Analysis.status == AnalysisStatus.FAILED, Integer)).label("errors"),
        )
        .where(Analysis.created_at >= window_start)
        .where(Analysis.org_id == org_id)
        .group_by(cast(Analysis.created_at, SqlDate))
        .order_by(cast(Analysis.created_at, SqlDate))
    )

    daily = [serialize_daily_metric_row(row) for row in daily_result.all()]

    totals_result = await db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("total_cost"),
            func.avg(Analysis.pipeline_duration_seconds).label("avg_duration"),
            func.sum(func.cast(Analysis.status == AnalysisStatus.FAILED, Integer)).label(
                "error_count"
            ),
        )
        .where(Analysis.created_at >= window_start)
        .where(Analysis.org_id == org_id)
    )
    totals = totals_result.one()
    total_analyses = totals.total or 0
    avg_duration_seconds = float(totals.avg_duration) if totals.avg_duration is not None else None
    return build_admin_metrics_summary(
        daily=daily,
        total_analyses=total_analyses,
        total_cost=totals.total_cost,
        avg_duration_seconds=avg_duration_seconds,
        error_count=totals.error_count,
    )
