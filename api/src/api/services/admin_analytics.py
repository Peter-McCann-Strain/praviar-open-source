"""Business logic helpers for admin analytics endpoints.

Consolidates the former admin_analytics_* family:
  admin_analytics_window       -- time-window helpers and filter builders
  admin_analytics_time         -- thin re-export of window helpers (preserved)
  admin_analytics_models       -- shared result dataclasses
  admin_analytics_pricing      -- LLM cost-rate lookup
  admin_analytics_cost_helpers -- pure aggregation helpers
  admin_analytics_costs        -- DB-backed cost and model-usage queries
  admin_analytics_usage        -- DB-backed usage aggregation
  admin_analytics_audit        -- DB-backed audit-log queries
  admin_analytics_csv          -- CSV rendering helpers
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from praviar_pipeline.rendering.spreadsheet_safety import neutralize_spreadsheet_row
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, AnalysisStatus, AuditLog, Organization, PipelineEvent, User
from api.schemas.admin_analytics import (
    AuditLogEntryExtended,
    DailyCost,
    ModelCost,
    ModelUsageDetail,
    OrgUsage,
    StatusBreakdown,
    StepCost,
    TopCompound,
)
from api.services.admin_query_utils import execute_paged_query, load_id_map

_SENSITIVE_DETAIL_KEY_RE = re.compile(
    r"(authorization|bearer|cookie|credential|secret|password|passwd|token|api[_-]?key|client[_-]?secret|session|private[_-]?key)",
    re.IGNORECASE,
)
_SENSITIVE_DETAIL_VALUE_RE = re.compile(
    r"(\b(?:postgres(?:ql)?|mysql|mariadb|redis|amqp|mongodb|snowflake)://|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+|"
    r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9_]+|"
    r"\bprv_live_[A-Za-z0-9_-]{43})",
    re.IGNORECASE,
)
_REDACTED_AUDIT_VALUE = "[redacted]"

# ---------------------------------------------------------------------------
# Shared result dataclasses  (formerly admin_analytics_models)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageAnalyticsSummary:
    org_usage: list[OrgUsage]
    status_breakdown: list[StatusBreakdown]
    top_compounds: list[TopCompound]
    total_analyses: int
    avg_cost_per_analysis: float
    avg_duration_seconds: float | None
    period: str


@dataclass(frozen=True)
class ModelUsageSummary:
    models: list[ModelUsageDetail]
    total_tokens: int
    total_cost_usd: float
    overall_cache_hit_rate: float | None
    period: str


@dataclass(frozen=True)
class CostBreakdownSummary:
    daily_costs: list[DailyCost]
    step_costs: list[StepCost]
    model_costs: list[ModelCost]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    period: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class AuditLogPage:
    items: list[AuditLogEntryExtended]
    total: int
    page: int
    per_page: int
    has_next: bool


def _redact_audit_detail_value(key: str | None, value: Any) -> Any:
    """Return a safe-to-display audit detail value for UI/API/CSV consumers."""

    if key == "api_key_id":
        try:
            return str(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            return _REDACTED_AUDIT_VALUE

    if key and _SENSITIVE_DETAIL_KEY_RE.search(key):
        return _REDACTED_AUDIT_VALUE

    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_audit_detail_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }

    if isinstance(value, list):
        return [_redact_audit_detail_value(None, item) for item in value]

    if isinstance(value, tuple):
        return [_redact_audit_detail_value(None, item) for item in value]

    if isinstance(value, str) and _SENSITIVE_DETAIL_VALUE_RE.search(value):
        return _REDACTED_AUDIT_VALUE

    return value


def sanitize_audit_details(details: Any) -> dict[str, Any]:
    """Normalize audit details so alternate clients cannot receive raw secrets."""

    if not isinstance(details, Mapping):
        return {}

    return {str(key): _redact_audit_detail_value(str(key), value) for key, value in details.items()}


# ---------------------------------------------------------------------------
# Time-window helpers  (formerly admin_analytics_window / admin_analytics_time)
# ---------------------------------------------------------------------------


def parse_period(period: str) -> timedelta:
    """Convert a period token into a date range delta."""
    periods = {
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30),
        "quarter": timedelta(days=90),
    }
    return periods.get(period, timedelta(days=30))


def _parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 date or datetime") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_date_range(
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime, datetime]:
    """Parse a requested date range or fall back to a period-based window."""
    now = datetime.now(UTC)

    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("start_date and end_date must be provided together")
        start = _parse_iso_datetime(start_date, field_name="start_date")
        end = _parse_iso_datetime(end_date, field_name="end_date")
        if start > end:
            raise ValueError("start_date must be before or equal to end_date")
        return start, end

    delta = parse_period(period)
    return now - delta, now


def build_analytics_window_filter(range_start: datetime, range_end: datetime):
    """Build the shared created-at window predicate for analytics queries."""
    return Analysis.created_at.between(range_start, range_end)


def model_name_from_config(config: Mapping[str, object] | None) -> str:
    """Resolve analytics grouping from internal adaptive execution metadata."""
    if not isinstance(config, Mapping):
        return "world_class_adaptive"
    for key in ("analysis_execution_profile", "execution_profile"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    plan = config.get("analysis_execution_plan")
    if isinstance(plan, Mapping):
        for key in ("method", "pipeline", "execution_profile"):
            value = plan.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "world_class_adaptive"


# ---------------------------------------------------------------------------
# LLM pricing helpers  (formerly admin_analytics_pricing)
# ---------------------------------------------------------------------------


def get_model_pricing() -> dict[str, tuple[float, float]]:
    """Build model pricing lookup from praviar_pipeline config."""
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    return {
        settings.claude_triage_model: (
            settings.cost_per_million_input_haiku,
            settings.cost_per_million_output_haiku,
        ),
        settings.claude_analysis_model: (
            settings.cost_per_million_input_sonnet,
            settings.cost_per_million_output_sonnet,
        ),
        settings.claude_deep_model: (
            settings.cost_per_million_input_opus,
            settings.cost_per_million_output_opus,
        ),
        "default": (
            settings.cost_per_million_input_sonnet,
            settings.cost_per_million_output_sonnet,
        ),
    }


def estimate_model_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    get_model_pricing_fn: Callable[[], dict[str, tuple[float, float]]] | None = None,
) -> float:
    """Estimate LLM cost for a specific model and token counts."""
    if get_model_pricing_fn is None:
        get_model_pricing_fn = get_model_pricing
    pricing = get_model_pricing_fn()
    input_rate, output_rate = pricing.get(model, pricing["default"])
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


# ---------------------------------------------------------------------------
# Pure aggregation helpers  (formerly admin_analytics_cost_helpers)
# ---------------------------------------------------------------------------


def build_step_costs(
    *,
    step_rows: Iterable[Any],
    total_cost: float,
) -> list[StepCost]:
    """Distribute total cost across pipeline steps by analysis share."""
    step_rows = list(step_rows)
    total_step_analyses = sum(row.analysis_count for row in step_rows) or 1
    return [
        StepCost(
            step_name=row.step_name,
            total_cost_usd=round(total_cost * (row.analysis_count / total_step_analyses), 4),
            analysis_count=row.analysis_count,
            avg_cost_usd=round(
                (total_cost * (row.analysis_count / total_step_analyses))
                / max(row.analysis_count, 1),
                4,
            ),
        )
        for row in step_rows
    ]


def build_model_costs(
    *,
    rows: Iterable[Any],
    model_name_from_config,
) -> list[ModelCost]:
    """Aggregate cost rows into per-model cost summaries."""
    model_costs_map: dict[str, ModelCost] = {}
    for row in rows:
        config = row.config or {}
        model_name = model_name_from_config(config)
        if model_name not in model_costs_map:
            model_costs_map[model_name] = ModelCost(
                model_name=model_name,
                total_cost_usd=0.0,
                total_input_tokens=0,
                total_output_tokens=0,
                request_count=0,
            )
        entry = model_costs_map[model_name]
        entry.total_input_tokens += row.input_tokens or 0
        entry.total_output_tokens += row.output_tokens or 0
        entry.total_cost_usd += float(row.total_cost or 0)
        entry.request_count += row.count or 0

    return sorted(
        model_costs_map.values(),
        key=lambda model: model.total_cost_usd,
        reverse=True,
    )


def build_model_usage_details(
    *,
    rows: Iterable[Any],
    model_name_from_config,
) -> tuple[list[ModelUsageDetail], int, float]:
    """Aggregate usage rows into per-model detail objects plus totals."""
    models_map: dict[str, ModelUsageDetail] = {}
    total_tokens = 0
    total_cost = 0.0

    for row in rows:
        config = row.config or {}
        model_name = model_name_from_config(config)
        input_tokens = row.input_tokens or 0
        output_tokens = row.output_tokens or 0
        cost = float(row.total_cost or 0)
        tokens = input_tokens + output_tokens

        if model_name not in models_map:
            models_map[model_name] = ModelUsageDetail(
                model_name=model_name,
                total_input_tokens=0,
                total_output_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
                request_count=0,
                cache_hit_rate=None,
            )

        entry = models_map[model_name]
        entry.total_input_tokens += input_tokens
        entry.total_output_tokens += output_tokens
        entry.total_tokens += tokens
        entry.estimated_cost_usd += cost
        entry.request_count += row.count or 0

        total_tokens += tokens
        total_cost += cost

    models = sorted(models_map.values(), key=lambda model: model.estimated_cost_usd, reverse=True)
    return models, total_tokens, total_cost


def calculate_cache_hit_rate(report_data_rows: Iterable[Mapping[str, object]]) -> float | None:
    """Compute the fraction of pipeline calls that had a cache hit."""
    cache_hits = 0
    cache_total = 0
    for row in report_data_rows:
        if isinstance(row, dict):
            cost_data = row.get("cost", {})
            if isinstance(cost_data, dict):
                cached = cost_data.get("cache_creation_input_tokens", 0)
                cache_read = cost_data.get("cache_read_input_tokens", 0)
                if cached or cache_read:
                    cache_total += 1
                    if cache_read > 0:
                        cache_hits += 1
    if cache_total == 0:
        return None
    return cache_hits / cache_total * 100


# ---------------------------------------------------------------------------
# DB-backed cost and model-usage queries  (formerly admin_analytics_costs)
# ---------------------------------------------------------------------------


async def get_cost_breakdown_summary_impl(
    db: AsyncSession,
    *,
    period: str,
    range_start,
    range_end,
    org_id: uuid.UUID | None = None,
) -> CostBreakdownSummary:
    """Aggregate cost usage by day, pipeline step, and configured model."""
    base_filter = build_analytics_window_filter(range_start, range_end)
    if org_id:
        base_filter = base_filter & (Analysis.org_id == org_id)

    daily_result = await db.execute(
        select(
            func.date(Analysis.created_at).label("date"),
            func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("total_cost"),
            func.count().label("count"),
            func.coalesce(func.sum(Analysis.total_input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Analysis.total_output_tokens), 0).label("output_tokens"),
        )
        .where(base_filter)
        .group_by(func.date(Analysis.created_at))
        .order_by(func.date(Analysis.created_at))
    )
    daily_costs = []
    for row in daily_result.all():
        count = row._mapping["count"]
        daily_costs.append(
            DailyCost(
                date=str(row.date),
                total_cost_usd=float(row.total_cost),
                analysis_count=int(count),
                total_input_tokens=int(row.input_tokens),
                total_output_tokens=int(row.output_tokens),
            )
        )

    step_rows = (
        await db.execute(
            select(
                PipelineEvent.step_name,
                func.count(func.distinct(PipelineEvent.analysis_id)).label("analysis_count"),
            )
            .join(Analysis, PipelineEvent.analysis_id == Analysis.id)
            .where(base_filter)
            .where(PipelineEvent.event_type == "completed")
            .group_by(PipelineEvent.step_name)
            .order_by(desc("analysis_count"))
        )
    ).all()

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("total_cost"),
                func.count().label("total_count"),
            ).where(base_filter)
        )
    ).one()
    total_cost = float(totals.total_cost or 0)
    computed_step_costs = build_step_costs(step_rows=step_rows, total_cost=total_cost)

    model_result = await db.execute(
        select(
            Analysis.config,
            func.sum(Analysis.total_input_tokens).label("input_tokens"),
            func.sum(Analysis.total_output_tokens).label("output_tokens"),
            func.sum(Analysis.estimated_cost_usd).label("total_cost"),
            func.count().label("count"),
        )
        .where(base_filter)
        .where(Analysis.status == AnalysisStatus.COMPLETED)
        .group_by(Analysis.config)
        .limit(20)
    )

    computed_model_costs = build_model_costs(
        rows=model_result.all(),
        model_name_from_config=model_name_from_config,
    )

    return CostBreakdownSummary(
        daily_costs=daily_costs,
        step_costs=computed_step_costs,
        model_costs=computed_model_costs,
        total_cost_usd=total_cost,
        total_input_tokens=sum(day.total_input_tokens for day in daily_costs),
        total_output_tokens=sum(day.total_output_tokens for day in daily_costs),
        period=period,
        start_date=str(range_start.date()),
        end_date=str(range_end.date()),
    )


async def get_model_usage_summary_impl(
    db: AsyncSession,
    *,
    period: str,
    range_start,
    range_end,
    org_id: uuid.UUID | None,
) -> ModelUsageSummary:
    """Aggregate token and cost usage by configured model."""
    base_filter = build_analytics_window_filter(range_start, range_end)
    if org_id:
        base_filter = base_filter & (Analysis.org_id == org_id)

    result = await db.execute(
        select(
            Analysis.config,
            func.sum(Analysis.total_input_tokens).label("input_tokens"),
            func.sum(Analysis.total_output_tokens).label("output_tokens"),
            func.sum(Analysis.estimated_cost_usd).label("total_cost"),
            func.count().label("count"),
        )
        .where(base_filter)
        .where(Analysis.status == AnalysisStatus.COMPLETED)
        .group_by(Analysis.config)
    )

    models, total_tokens, total_cost = build_model_usage_details(
        rows=result.all(),
        model_name_from_config=model_name_from_config,
    )

    cache_result = await db.execute(
        select(Analysis.report_data)
        .where(base_filter)
        .where(Analysis.status == AnalysisStatus.COMPLETED)
        .where(Analysis.report_data.isnot(None))
        .limit(100)
    )

    overall_cache_rate = calculate_cache_hit_rate(
        [r for r in cache_result.scalars().all() if r is not None]
    )

    return ModelUsageSummary(
        models=models,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 4),
        overall_cache_hit_rate=round(overall_cache_rate, 1)
        if overall_cache_rate is not None
        else None,
        period=period,
    )


# ---------------------------------------------------------------------------
# DB-backed usage aggregation  (formerly admin_analytics_usage)
# ---------------------------------------------------------------------------


async def get_usage_analytics_summary_impl(
    db: AsyncSession,
    *,
    period: str,
    range_start,
    range_end,
    org_id: uuid.UUID | None,
) -> UsageAnalyticsSummary:
    """Aggregate usage statistics by org, status, and compound."""
    base_filter = build_analytics_window_filter(range_start, range_end)
    if org_id:
        base_filter = base_filter & (Analysis.org_id == org_id)

    org_result = await db.execute(
        select(
            Analysis.org_id,
            Organization.name.label("org_name"),
            func.count().label("analysis_count"),
            func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("total_cost"),
        )
        .join(Organization, Analysis.org_id == Organization.id)
        .where(base_filter)
        .group_by(Analysis.org_id, Organization.name)
        .order_by(desc("total_cost"))
        .limit(20)
    )
    org_usage = [
        OrgUsage(
            org_id=row.org_id,
            org_name=row.org_name,
            analysis_count=row.analysis_count,
            total_cost_usd=float(row.total_cost),
            avg_cost_usd=round(float(row.total_cost) / max(row.analysis_count, 1), 4),
        )
        for row in org_result.all()
    ]

    status_result = await db.execute(
        select(
            Analysis.status,
            func.count().label("count"),
        )
        .where(base_filter)
        .group_by(Analysis.status)
    )
    status_breakdown = [
        StatusBreakdown(status=row.status.value, count=int(row._mapping["count"]))
        for row in status_result.all()
    ]

    compound_result = await db.execute(
        select(
            Analysis.compound_name,
            Analysis.compound_smiles,
            func.count().label("analysis_count"),
        )
        .where(base_filter)
        .where(Analysis.compound_name != "")
        .group_by(Analysis.compound_name, Analysis.compound_smiles)
        .order_by(desc("analysis_count"))
        .limit(10)
    )
    top_compounds = [
        TopCompound(
            compound_name=row.compound_name,
            compound_smiles=row.compound_smiles or "",
            analysis_count=row.analysis_count,
        )
        for row in compound_result.all()
    ]

    aggregate = (
        await db.execute(
            select(
                func.count().label("total"),
                func.coalesce(func.sum(Analysis.estimated_cost_usd), 0.0).label("total_cost"),
                func.avg(Analysis.pipeline_duration_seconds).label("avg_duration"),
            ).where(base_filter)
        )
    ).one()
    total_analyses = aggregate.total or 0
    total_cost = float(aggregate.total_cost or 0)

    return UsageAnalyticsSummary(
        org_usage=org_usage,
        status_breakdown=status_breakdown,
        top_compounds=top_compounds,
        total_analyses=total_analyses,
        avg_cost_per_analysis=round(total_cost / max(total_analyses, 1), 4),
        avg_duration_seconds=float(aggregate.avg_duration) if aggregate.avg_duration else None,
        period=period,
    )


# ---------------------------------------------------------------------------
# DB-backed audit-log queries  (formerly admin_analytics_audit)
# ---------------------------------------------------------------------------


def _parse_optional_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO date string into a UTC datetime when valid."""
    if not value:
        return None
    return _parse_iso_datetime(value, field_name="date filter")


async def get_audit_log_page_impl(
    db: AsyncSession,
    *,
    action: str | None,
    user_id: uuid.UUID | None,
    start_date: str | None,
    end_date: str | None,
    page: int,
    per_page: int,
    sort: str,
    org_id: uuid.UUID | None = None,
) -> AuditLogPage:
    """Return filtered audit log entries with pagination metadata."""
    base_query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if org_id:
        base_query = base_query.where(AuditLog.org_id == org_id)
        count_query = count_query.where(AuditLog.org_id == org_id)
    if action:
        base_query = base_query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if user_id:
        base_query = base_query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)

    start = _parse_optional_iso_datetime(start_date)
    if start is not None:
        base_query = base_query.where(AuditLog.created_at >= start)
        count_query = count_query.where(AuditLog.created_at >= start)

    end = _parse_optional_iso_datetime(end_date)
    if end is not None:
        base_query = base_query.where(AuditLog.created_at <= end)
        count_query = count_query.where(AuditLog.created_at <= end)

    order = AuditLog.created_at.desc() if sort == "desc" else AuditLog.created_at.asc()
    total, logs = await execute_paged_query(
        db,
        base_query=base_query,
        count_query=count_query,
        order_by=order,
        page=page,
        per_page=per_page,
    )
    log_user_ids = {log.user_id for log in logs if log.user_id}
    user_emails = await load_id_map(
        db,
        model=User,
        id_column=User.id,
        value_column=User.email,
        ids=log_user_ids,
    )

    items = [
        AuditLogEntryExtended(
            id=log.id,
            org_id=log.org_id,
            action=log.action,
            user_id=log.user_id,
            user_email=user_emails.get(log.user_id, "") if log.user_id else "",
            analysis_id=log.analysis_id,
            details=sanitize_audit_details(log.details),
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in logs
    ]
    return AuditLogPage(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_next=(page * per_page) < total,
    )


# ---------------------------------------------------------------------------
# CSV rendering  (formerly admin_analytics_csv)
# ---------------------------------------------------------------------------


def render_audit_log_csv(items: list) -> str:
    """Render audit log items as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        neutralize_spreadsheet_row(
            [
                "id",
                "org_id",
                "action",
                "user_id",
                "user_email",
                "analysis_id",
                "details",
                "ip_address",
                "created_at",
            ]
        )
    )
    for item in items:
        writer.writerow(
            neutralize_spreadsheet_row(
                [
                    str(item.id),
                    str(item.org_id),
                    item.action,
                    str(item.user_id) if item.user_id else "",
                    item.user_email,
                    str(item.analysis_id) if item.analysis_id else "",
                    json.dumps(sanitize_audit_details(item.details), sort_keys=True),
                    item.ip_address,
                    item.created_at.isoformat(),
                ]
            )
        )
    return output.getvalue()


# ---------------------------------------------------------------------------
# Public facade  (mirrors the former admin_analytics.py interface exactly)
# ---------------------------------------------------------------------------


async def get_usage_analytics_summary(
    db: AsyncSession,
    *,
    period: str,
    org_id: uuid.UUID | None = None,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> UsageAnalyticsSummary:
    """Aggregate usage statistics by org, status, and compound."""
    if range_start is None or range_end is None:
        range_start, range_end = parse_date_range(period, None, None)
    return await get_usage_analytics_summary_impl(
        db,
        period=period,
        range_start=range_start,
        range_end=range_end,
        org_id=org_id,
    )


async def get_cost_breakdown_summary(
    db: AsyncSession,
    *,
    period: str,
    start_date: str | None,
    end_date: str | None,
    org_id: uuid.UUID | None,
) -> CostBreakdownSummary:
    """Aggregate cost usage by day, pipeline step, and configured model."""
    range_start, range_end = parse_date_range(period, start_date, end_date)
    return await get_cost_breakdown_summary_impl(
        db,
        period=period,
        range_start=range_start,
        range_end=range_end,
        org_id=org_id,
    )


async def get_model_usage_summary(
    db: AsyncSession,
    *,
    period: str,
    org_id: uuid.UUID | None = None,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> ModelUsageSummary:
    """Aggregate token and cost usage by configured model."""
    if range_start is None or range_end is None:
        range_start, range_end = parse_date_range(period, None, None)
    return await get_model_usage_summary_impl(
        db,
        period=period,
        range_start=range_start,
        range_end=range_end,
        org_id=org_id,
    )


async def get_audit_log_page(
    db: AsyncSession,
    *,
    action: str | None,
    user_id: uuid.UUID | None,
    start_date: str | None,
    end_date: str | None,
    page: int,
    per_page: int,
    sort: str,
    org_id: uuid.UUID | None = None,
) -> AuditLogPage:
    """Return filtered audit log entries with pagination metadata."""
    return await get_audit_log_page_impl(
        db,
        action=action,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
        sort=sort,
        org_id=org_id,
    )
