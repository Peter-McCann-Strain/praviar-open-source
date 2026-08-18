"""Business logic for monitor and alert management."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    Monitor,
    MonitorAlert,
    MonitorSchedule,
)
from api.errors import APIError
from api.schemas.monitors import CreateMonitorRequest, UpdateMonitorRequest
from api.services.monitor_reassessment_lifecycle import (
    has_open_monitor_reassessments,
)
from api.services.monitor_runtime import build_monitor_seed_from_report
from api.services.report_access import (
    normalize_report_trust_mode,
    require_completed_report_payload,
)

logger = structlog.get_logger()

_MONITOR_SOURCE_ANALYSIS_UNIQUE_INDEX = "uq_monitors_org_source_analysis_id"


@dataclass(frozen=True)
class MonitorPage:
    items: Sequence[Monitor]
    total: int


@dataclass(frozen=True)
class MonitorAlertPage:
    items: Sequence[MonitorAlert]
    total: int


def _text(value: object) -> str:
    return str(value or "").strip()


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    return getattr(diagnostic, "constraint_name", None) or getattr(
        original, "constraint_name", None
    )


async def _resolve_monitor_seed(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    body: CreateMonitorRequest,
) -> tuple[str, str, dict, dict]:
    compound_smiles = body.compound_smiles.strip()
    compound_name = body.compound_name.strip()
    details: dict[str, str] = {}
    report_data: dict = {}

    if body.analysis_id is None:
        return compound_smiles, compound_name, details, report_data

    result = await db.execute(
        select(Analysis)
        .where(
            Analysis.id == body.analysis_id,
            Analysis.org_id == org_id,
        )
        .with_for_update()
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise APIError(404, "Not Found", "Analysis not found")

    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Only completed reports with source-span provenance can seed monitors",
    )
    report_compound = report_data.get("compound", {}) if isinstance(report_data, dict) else {}
    report_name = str(report_compound.get("name", "") or "").strip()
    report_smiles = str(
        report_compound.get("canonical_smiles", "") or report_compound.get("smiles", "") or ""
    ).strip()
    compound_name = compound_name or report_name or str(analysis.compound_name or "").strip()
    compound_smiles = (
        compound_smiles or report_smiles or str(analysis.compound_smiles or "").strip()
    )

    if not compound_smiles:
        raise APIError(
            422,
            "Unprocessable Entity",
            "Analysis does not contain a reusable compound structure for monitoring",
        )

    details["source_analysis_id"] = str(analysis.id)
    details["source_trust_mode"] = normalize_report_trust_mode(report_data)
    return compound_smiles, compound_name, details, report_data


async def find_monitor_for_analysis(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    with_for_update: bool = False,
) -> Monitor | None:
    """Return the one org-scoped monitor seeded by an analysis, if present."""
    statement = select(Monitor).where(
        Monitor.source_analysis_id == analysis_id,
        Monitor.org_id == org_id,
    )
    if with_for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def _monitor_seed_matches(
    monitor: Monitor,
    *,
    compound_smiles: str,
    compound_name: str,
    schedule: str,
) -> bool:
    return (
        monitor.compound_smiles == compound_smiles
        and monitor.compound_name == compound_name
        and _text(monitor.schedule) == schedule
    )


async def _resolve_existing_seeded_monitor(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    analysis_id: uuid.UUID,
    compound_smiles: str,
    compound_name: str,
    schedule: str,
    with_for_update: bool,
) -> Monitor | None:
    existing = await find_monitor_for_analysis(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        with_for_update=with_for_update,
    )
    if existing is None:
        return None
    if not _monitor_seed_matches(
        existing,
        compound_smiles=compound_smiles,
        compound_name=compound_name,
        schedule=schedule,
    ):
        raise APIError(
            409,
            "Conflict",
            "A monitor already exists for this analysis with different settings. "
            "Update the existing monitor instead.",
        )
    return existing


async def get_monitor_for_org(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Monitor:
    statement = select(Monitor).where(
        Monitor.id == monitor_id,
        Monitor.org_id == org_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    monitor = result.scalar_one_or_none()
    if not monitor:
        logger.warning("monitor_not_found", monitor_id=str(monitor_id), org_id=str(org_id))
        raise APIError(404, "Not Found", "Monitor not found")
    return monitor


async def create_monitor(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: CreateMonitorRequest,
    request: Request,
) -> Monitor:
    compound_smiles, compound_name, source_details, report_data = await _resolve_monitor_seed(
        db,
        org_id=org_id,
        body=body,
    )
    if body.analysis_id is not None:
        try:
            existing = await _resolve_existing_seeded_monitor(
                db,
                org_id=org_id,
                analysis_id=body.analysis_id,
                compound_smiles=compound_smiles,
                compound_name=compound_name,
                schedule=body.schedule,
                with_for_update=True,
            )
        except APIError:
            await db.rollback()
            raise
        if existing is not None:
            await db.commit()
            logger.info(
                "monitor_create_replayed",
                monitor_id=str(existing.id),
                analysis_id=str(body.analysis_id),
                org_id=str(org_id),
            )
            return existing
    strategy_report = (
        report_data
        if report_data
        else {
            "trust_mode": "monitor",
            "compound": {
                "name": compound_name,
                "canonical_smiles": compound_smiles,
            },
            "target_jurisdictions": [],
            "jurisdiction_bundle": "custom",
        }
    )
    monitoring_strategy, watch_targets, target_jurisdictions, jurisdiction_bundle = (
        build_monitor_seed_from_report(
            strategy_report,
            schedule=body.schedule,
            compound_name=compound_name,
        )
    )
    monitor = Monitor(
        org_id=org_id,
        user_id=user_id,
        source_analysis_id=body.analysis_id,
        compound_smiles=compound_smiles,
        compound_name=compound_name,
        source_report_id=_text(report_data.get("report_id")) if report_data else "",
        source_trust_mode=_text(source_details.get("source_trust_mode")),
        schedule=MonitorSchedule(body.schedule),
        jurisdiction_bundle=jurisdiction_bundle,
        target_jurisdictions=target_jurisdictions,
        strategy_version=monitoring_strategy["version"],
        monitoring_strategy=monitoring_strategy,
        watch_targets=watch_targets,
        conclusion_status=(
            "fresh" if monitoring_strategy.get("conclusion_dependencies") else "unbound"
        ),
        stale_conclusions=[],
        last_run_status="pending",
        last_run_summary="Monitor created — awaiting first low-cost diff pass.",
    )
    db.add(monitor)
    try:
        await db.flush()
        await db.refresh(monitor)

        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="monitor.created",
            details={
                "monitor_id": str(monitor.id),
                "compound_smiles": compound_smiles[:200],
                "compound_name": compound_name[:200],
                "schedule": body.schedule,
                **source_details,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if (
            body.analysis_id is not None
            and _integrity_constraint_name(exc) == _MONITOR_SOURCE_ANALYSIS_UNIQUE_INDEX
        ):
            existing = await _resolve_existing_seeded_monitor(
                db,
                org_id=org_id,
                analysis_id=body.analysis_id,
                compound_smiles=compound_smiles,
                compound_name=compound_name,
                schedule=body.schedule,
                with_for_update=False,
            )
            if existing is not None:
                await db.commit()
                logger.info(
                    "monitor_create_concurrent_replay",
                    monitor_id=str(existing.id),
                    analysis_id=str(body.analysis_id),
                    org_id=str(org_id),
                )
                return existing
        raise
    except Exception:
        await db.rollback()
        raise
    logger.info("monitor_created", monitor_id=str(monitor.id), user_id=str(user_id))
    return monitor


async def list_monitors_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
    is_active: bool | None,
) -> MonitorPage:
    query = select(Monitor).where(Monitor.org_id == org_id)
    if is_active is not None:
        query = query.where(Monitor.is_active == is_active)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(
        query.order_by(Monitor.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return MonitorPage(items=result.scalars().all(), total=total)


async def update_monitor(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMonitorRequest,
    request: Request | None = None,
) -> Monitor:
    # Serialize report-seed and schedule changes with scan persistence and
    # counsel reassessment, which also mutate this monitor row.
    monitor = await get_monitor_for_org(
        db,
        monitor_id=monitor_id,
        org_id=org_id,
        for_update=True,
    )
    changed_fields: list[str] = []

    if body.schedule is not None:
        monitor.schedule = MonitorSchedule(body.schedule)
        strategy = dict(monitor.monitoring_strategy or {})
        strategy["schedule"] = body.schedule
        monitor.monitoring_strategy = strategy
        changed_fields.append("schedule")
    if body.is_active is not None:
        monitor.is_active = body.is_active
        changed_fields.append("is_active")
    if body.compound_name is not None:
        monitor.compound_name = body.compound_name
        strategy = dict(monitor.monitoring_strategy or {})
        strategy["compound_name"] = body.compound_name
        monitor.monitoring_strategy = strategy
        changed_fields.append("compound_name")

    if isinstance(monitor.source_analysis_id, uuid.UUID):
        final_schedule = _text(monitor.schedule) or "weekly"
        seed_body = CreateMonitorRequest(
            compound_smiles=monitor.compound_smiles,
            compound_name=monitor.compound_name,
            analysis_id=monitor.source_analysis_id,
            schedule=final_schedule,
        )
        compound_smiles, compound_name, source_details, report_data = await _resolve_monitor_seed(
            db, org_id=org_id, body=seed_body
        )
        strategy, watch_targets, target_jurisdictions, jurisdiction_bundle = (
            build_monitor_seed_from_report(
                report_data,
                schedule=final_schedule,
                compound_name=compound_name,
            )
        )
        monitor.compound_smiles = compound_smiles
        monitor.compound_name = compound_name
        monitor.source_report_id = _text(report_data.get("report_id"))
        monitor.source_trust_mode = _text(source_details.get("source_trust_mode"))
        monitor.jurisdiction_bundle = jurisdiction_bundle
        monitor.target_jurisdictions = target_jurisdictions
        monitor.strategy_version = strategy["version"]
        monitor.monitoring_strategy = strategy
        monitor.watch_targets = watch_targets
        if not list(getattr(monitor, "stale_conclusions", None) or []):
            monitor.conclusion_status = (
                "fresh" if strategy.get("conclusion_dependencies") else "unbound"
            )
        changed_fields.append("report_seed")

    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="monitor.updated",
            details={
                "monitor_id": str(monitor_id),
                "changed_fields": changed_fields,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
        await db.refresh(monitor)
    except Exception:
        await db.rollback()
        raise
    logger.info("monitor_updated", monitor_id=str(monitor_id), org_id=str(org_id))
    return monitor


async def delete_monitor(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> None:
    # Serialize deletion with scan persistence and counsel reassessment, which
    # both lock this row before mutating lifecycle state.
    monitor = await get_monitor_for_org(
        db,
        monitor_id=monitor_id,
        org_id=org_id,
        for_update=True,
    )
    unresolved_impacts = (
        list(monitor.stale_conclusions)
        if isinstance(getattr(monitor, "stale_conclusions", None), list)
        else []
    )
    durable_open_episode = await has_open_monitor_reassessments(
        db,
        monitor_id=monitor_id,
        org_id=org_id,
    )
    if unresolved_impacts or durable_open_episode:
        raise APIError(
            409,
            "Conflict",
            "Resolve every monitoring-invalidated conclusion before deleting this watch. "
            "Acknowledging alerts is not a legal reassessment.",
        )
    try:
        await db.execute(
            delete(MonitorAlert).where(
                MonitorAlert.monitor_id == monitor_id,
                MonitorAlert.org_id == org_id,
            )
        )
        await db.delete(monitor)
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="monitor.deleted",
            details={"monitor_id": str(monitor_id)},
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("monitor_deleted", monitor_id=str(monitor_id), org_id=str(org_id))


async def list_monitor_alerts_page(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
    dismissed: bool | None,
) -> MonitorAlertPage:
    await get_monitor_for_org(db, monitor_id=monitor_id, org_id=org_id)

    query = select(MonitorAlert).where(
        MonitorAlert.monitor_id == monitor_id,
        MonitorAlert.org_id == org_id,
    )
    if dismissed is not None:
        query = query.where(MonitorAlert.dismissed == dismissed)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(
        query.order_by(MonitorAlert.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return MonitorAlertPage(items=result.scalars().all(), total=total)


async def dismiss_monitor_alert(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    alert_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> None:
    await get_monitor_for_org(db, monitor_id=monitor_id, org_id=org_id)

    result = await db.execute(
        select(MonitorAlert).where(
            MonitorAlert.id == alert_id,
            MonitorAlert.monitor_id == monitor_id,
            MonitorAlert.org_id == org_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise APIError(404, "Not Found", "Alert not found")

    alert.dismissed = True
    alert.dismissed_by = user_id
    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="monitor.alert.dismissed",
            details={
                "monitor_id": str(monitor_id),
                "alert_id": str(alert_id),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "alert_dismissed",
        alert_id=str(alert_id),
        monitor_id=str(monitor_id),
        user_id=str(user_id),
    )
