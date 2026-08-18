"""Business logic for in-app notifications and notification preferences."""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import (
    Analysis,
    AnalysisStatus,
    Comment,
    CreditCapacityRequest,
    ExportJob,
    ExportStatus,
    Monitor,
    MonitorAlert,
    Notification,
    User,
    WeeklyDigestDelivery,
)
from api.db.models import (
    NotificationType as DBNotificationType,
)
from api.deps import PERMISSION_MATRIX
from api.errors import APIError
from api.schemas.notifications import (
    NotificationPreferencesSchema,
    NotificationResponse,
    NotificationType,
)
from api.schemas.principal import PrincipalCapabilitiesResponse
from api.services.notification_unsubscribe import (
    InvalidUnsubscribeTokenError,
    digest_unsubscribe_token,
    unsubscribe_token_locator,
)
from api.services.principal_capabilities import build_principal_capabilities

logger = structlog.get_logger()

_TOMBSTONE_TITLE = "Notification unavailable"
_TOMBSTONE_BODY = "This notification no longer points to a workspace resource you can access."
_SUPPORTED_DIGEST_FREQUENCIES = frozenset({"off", "weekly"})
_LEGACY_DIGEST_FREQUENCY_NORMALIZATION = {
    "daily": "weekly",
    "immediate": "weekly",
}
_CREDIT_REQUEST_KINDS = frozenset(
    {
        "credit_capacity_request",
        "credit_capacity_request_confirmation",
        "credit_capacity_request_resolved",
        "credit_capacity_request_auto_fulfilled",
        "credit_capacity_requests_auto_fulfilled_admin",
    }
)


@dataclass(frozen=True)
class NotificationPage:
    items: list[NotificationResponse]
    unread_count: int
    total: int


@dataclass(frozen=True)
class NotificationActionResult:
    """Safe action resolution returned to the authenticated recipient."""

    notification_id: uuid.UUID
    actionable: bool
    destination: str | None
    marked_read: bool


@dataclass(frozen=True)
class _NotificationView:
    """Sanitized notification content and current action availability."""

    type: NotificationType
    title: str
    body: str
    data: dict[str, object]
    actionable: bool
    destination: str | None
    available: bool


@dataclass(frozen=True)
class _NotificationResourceSnapshot:
    """Page-local, tenant-scoped resource availability for list sanitization."""

    capabilities: PrincipalCapabilitiesResponse
    analysis_ids: frozenset[uuid.UUID]
    export_analysis_by_job: dict[uuid.UUID, uuid.UUID]
    monitor_ids: frozenset[uuid.UUID]
    alert_monitor_pairs: frozenset[tuple[uuid.UUID, uuid.UUID]]
    comment_analysis_by_id: dict[uuid.UUID, uuid.UUID]
    credit_requester_by_id: dict[uuid.UUID, uuid.UUID | None]


@dataclass
class _NotificationResourceReferences:
    """Capability-filtered resource identifiers referenced by one page."""

    analysis_ids: set[uuid.UUID]
    export_job_ids: set[uuid.UUID]
    monitor_ids: set[uuid.UUID]
    alert_ids: set[uuid.UUID]
    comment_ids: set[uuid.UUID]
    credit_request_ids: set[uuid.UUID]


def _type_value(notification: Notification) -> str:
    value = notification.type
    return str(getattr(value, "value", value))


def _data_mapping(notification: Notification) -> Mapping[str, object]:
    data = notification.data
    return data if isinstance(data, Mapping) else {}


def _uuid_value(data: Mapping[str, object], *keys: str) -> uuid.UUID | None:
    for key in keys:
        raw = data.get(key)
        if isinstance(raw, uuid.UUID):
            return raw
        if not isinstance(raw, str) or len(raw) > 64:
            continue
        try:
            return uuid.UUID(raw)
        except ValueError:
            continue
    return None


def _uuid_values(data: Mapping[str, object], key: str) -> list[uuid.UUID]:
    raw_values = data.get(key)
    if not isinstance(raw_values, list):
        return []
    resolved: list[uuid.UUID] = []
    for raw in raw_values[:100]:
        if not isinstance(raw, str) or len(raw) > 64:
            continue
        try:
            resolved.append(uuid.UUID(raw))
        except ValueError:
            continue
    return resolved


def _report_destination(
    user: User,
    analysis_id: uuid.UUID,
    *,
    capabilities: PrincipalCapabilitiesResponse | None = None,
) -> str | None:
    capabilities = capabilities or build_principal_capabilities(user)
    role = user.role
    if role in PERMISSION_MATRIX["report.view_full"] and not capabilities.risk_ratings_restricted:
        return f"/analyses/{analysis_id}/report"
    if role in PERMISSION_MATRIX["report.view_summary"]:
        return f"/analyses/{analysis_id}/report/summary"
    return None


def _tombstone(notification_type: str) -> _NotificationView:
    if notification_type in {
        DBNotificationType.SYSTEM.value,
        DBNotificationType.BILLING_EVENT.value,
    }:
        safe_type = NotificationType.SYSTEM
    else:
        try:
            safe_type = NotificationType(notification_type)
        except ValueError:
            safe_type = NotificationType.SYSTEM
    return _NotificationView(
        type=safe_type,
        title=_TOMBSTONE_TITLE,
        body=_TOMBSTONE_BODY,
        data={"tombstoned": True},
        actionable=False,
        destination=None,
        available=False,
    )


async def _analysis_complete_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    data = _data_mapping(notification)
    analysis_id = _uuid_value(data, "analysis_id")
    if analysis_id is None:
        return _tombstone(DBNotificationType.ANALYSIS_COMPLETE.value)

    if snapshot is not None:
        analysis_available = analysis_id in snapshot.analysis_ids
    else:
        result = await db.execute(
            select(Analysis.id).where(
                Analysis.id == analysis_id,
                Analysis.org_id == user.org_id,
                Analysis.status == AnalysisStatus.COMPLETED,
                Analysis.report_data.is_not(None),
            )
        )
        analysis_available = result.scalar_one_or_none() is not None
    if not analysis_available:
        return _tombstone(DBNotificationType.ANALYSIS_COMPLETE.value)

    destination = _report_destination(
        user,
        analysis_id,
        capabilities=snapshot.capabilities if snapshot is not None else None,
    )
    if destination is None:
        return _tombstone(DBNotificationType.ANALYSIS_COMPLETE.value)
    return _NotificationView(
        type=NotificationType.ANALYSIS_COMPLETE,
        title="Analysis complete",
        body="The analysis is complete. Open the authorized report view for current results.",
        data={"analysis_id": str(analysis_id)},
        actionable=True,
        destination=destination,
        available=True,
    )


async def _export_ready_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    capabilities = (
        snapshot.capabilities if snapshot is not None else build_principal_capabilities(user)
    )
    if not capabilities.can_export_report:
        return _tombstone(DBNotificationType.EXPORT_READY.value)

    data = _data_mapping(notification)
    export_job_id = _uuid_value(data, "export_job_id", "job_id", "export_id")
    if export_job_id is None:
        return _tombstone(DBNotificationType.EXPORT_READY.value)

    if snapshot is not None:
        analysis_id = snapshot.export_analysis_by_job.get(export_job_id)
    else:
        result = await db.execute(
            select(ExportJob.analysis_id)
            .join(Analysis, Analysis.id == ExportJob.analysis_id)
            .where(
                ExportJob.id == export_job_id,
                ExportJob.org_id == user.org_id,
                ExportJob.user_id == user.id,
                ExportJob.status == ExportStatus.COMPLETED,
                Analysis.org_id == user.org_id,
                Analysis.status == AnalysisStatus.COMPLETED,
                Analysis.report_data.is_not(None),
            )
        )
        analysis_id = result.scalar_one_or_none()
    if analysis_id is None:
        return _tombstone(DBNotificationType.EXPORT_READY.value)

    destination = _report_destination(user, analysis_id, capabilities=capabilities)
    if destination is None:
        return _tombstone(DBNotificationType.EXPORT_READY.value)
    return _NotificationView(
        type=NotificationType.EXPORT_READY,
        title="Export ready",
        body="Your report export is ready. Open the report workspace to download it.",
        data={
            "analysis_id": str(analysis_id),
            "export_job_id": str(export_job_id),
        },
        actionable=True,
        destination=destination,
        available=True,
    )


async def _monitor_alert_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    capabilities = (
        snapshot.capabilities if snapshot is not None else build_principal_capabilities(user)
    )
    if not capabilities.can_manage_monitors:
        return _tombstone(DBNotificationType.MONITOR_ALERT.value)

    data = _data_mapping(notification)
    monitor_id = _uuid_value(data, "monitor_id")
    alert_id = _uuid_value(data, "alert_id", "monitor_alert_id")
    if monitor_id is None:
        return _tombstone(DBNotificationType.MONITOR_ALERT.value)

    if snapshot is not None:
        monitor_available = monitor_id in snapshot.monitor_ids
    else:
        monitor_result = await db.execute(
            select(Monitor.id).where(
                Monitor.id == monitor_id,
                Monitor.org_id == user.org_id,
            )
        )
        monitor_available = monitor_result.scalar_one_or_none() is not None
    if not monitor_available:
        return _tombstone(DBNotificationType.MONITOR_ALERT.value)

    if alert_id is not None:
        if snapshot is not None:
            alert_available = (alert_id, monitor_id) in snapshot.alert_monitor_pairs
        else:
            alert_result = await db.execute(
                select(MonitorAlert.id).where(
                    MonitorAlert.id == alert_id,
                    MonitorAlert.monitor_id == monitor_id,
                    MonitorAlert.org_id == user.org_id,
                )
            )
            alert_available = alert_result.scalar_one_or_none() is not None
        if not alert_available:
            return _tombstone(DBNotificationType.MONITOR_ALERT.value)

    safe_data: dict[str, object] = {"monitor_id": str(monitor_id)}
    if alert_id is not None:
        safe_data["alert_id"] = str(alert_id)
    return _NotificationView(
        type=NotificationType.MONITOR_ALERT,
        title="Monitoring update",
        body="A monitor has new activity. Open monitoring to review authorized details.",
        data=safe_data,
        actionable=True,
        destination="/monitors",
        available=True,
    )


def _team_invite_view(
    notification: Notification,
    user: User,
    *,
    capabilities: PrincipalCapabilitiesResponse | None = None,
) -> _NotificationView:
    data = _data_mapping(notification)
    action = data.get("action")
    if action == "manage_users":
        capabilities = capabilities or build_principal_capabilities(user)
        if not capabilities.can_view_platform_admin:
            return _tombstone(DBNotificationType.TEAM_INVITE.value)
        destination = "/admin?tab=users"
        safe_data: dict[str, object] = {"action": "manage_users"}
    else:
        destination = "/dashboard"
        safe_data = {}
    return _NotificationView(
        type=NotificationType.TEAM_INVITE,
        title="Team invitation update",
        body="Open your workspace to review the current team invitation status.",
        data=safe_data,
        actionable=True,
        destination=destination,
        available=True,
    )


async def _comment_assignment_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    capabilities = (
        snapshot.capabilities if snapshot is not None else build_principal_capabilities(user)
    )
    if not capabilities.can_view_review_queue:
        return _tombstone(DBNotificationType.SYSTEM.value)

    data = _data_mapping(notification)
    comment_id = _uuid_value(data, "comment_id")
    if comment_id is None:
        return _tombstone(DBNotificationType.SYSTEM.value)

    if snapshot is not None:
        analysis_id = snapshot.comment_analysis_by_id.get(comment_id)
    else:
        result = await db.execute(
            select(Comment.analysis_id)
            .join(Analysis, Analysis.id == Comment.analysis_id)
            .where(
                Comment.id == comment_id,
                Comment.org_id == user.org_id,
                Comment.assigned_to == user.id,
                Analysis.org_id == user.org_id,
                Analysis.status != AnalysisStatus.DELETED,
            )
        )
        analysis_id = result.scalar_one_or_none()
    if analysis_id is None:
        return _tombstone(DBNotificationType.SYSTEM.value)
    return _NotificationView(
        type=NotificationType.SYSTEM,
        title="Comment assigned for review",
        body="A review thread is currently assigned to you.",
        data={
            "kind": "comment_assignment",
            "comment_id": str(comment_id),
            "analysis_id": str(analysis_id),
        },
        actionable=True,
        destination="/reviews?filter=mine&sort=priority",
        available=True,
    )


async def _credit_request_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    kind: str,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    capabilities = (
        snapshot.capabilities if snapshot is not None else build_principal_capabilities(user)
    )
    admin_action = kind in {
        "credit_capacity_request",
        "credit_capacity_requests_auto_fulfilled_admin",
    }
    if admin_action and not capabilities.can_manage_billing:
        return _tombstone(DBNotificationType.SYSTEM.value)
    if not admin_action and not capabilities.can_view_billing:
        return _tombstone(DBNotificationType.SYSTEM.value)

    data = _data_mapping(notification)
    request_ids = (
        _uuid_values(data, "request_ids")
        if kind == "credit_capacity_requests_auto_fulfilled_admin"
        else []
    )
    request_id = _uuid_value(data, "request_id")
    if request_id is not None:
        request_ids = [request_id]
    if not request_ids:
        return _tombstone(DBNotificationType.SYSTEM.value)

    if snapshot is not None:
        requester_by_id = snapshot.credit_requester_by_id
        if any(request_id not in requester_by_id for request_id in request_ids):
            return _tombstone(DBNotificationType.SYSTEM.value)
        requester_ids = [requester_by_id[request_id] for request_id in request_ids]
    else:
        result = await db.execute(
            select(CreditCapacityRequest.id, CreditCapacityRequest.requester_user_id).where(
                CreditCapacityRequest.id.in_(request_ids),
                CreditCapacityRequest.org_id == user.org_id,
            )
        )
        rows = list(result.all())
        if len(rows) != len(set(request_ids)):
            return _tombstone(DBNotificationType.SYSTEM.value)
        requester_ids = [row.requester_user_id for row in rows]
    if not admin_action and any(requester_id != user.id for requester_id in requester_ids):
        return _tombstone(DBNotificationType.SYSTEM.value)

    destination = "/billing?intent=credits&source=capacity_request" if admin_action else "/billing"
    safe_data: dict[str, object] = {"kind": kind}
    if len(request_ids) == 1:
        safe_data["request_id"] = str(request_ids[0])
    else:
        safe_data["request_ids"] = [str(item) for item in request_ids]
    return _NotificationView(
        type=NotificationType.SYSTEM,
        title="Report Credit update",
        body="Open billing to review the current Report Credit request status.",
        data=safe_data,
        actionable=True,
        destination=destination,
        available=True,
    )


async def _system_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    data = _data_mapping(notification)
    raw_kind = data.get("kind")
    kind = raw_kind if isinstance(raw_kind, str) and len(raw_kind) <= 64 else ""
    if kind == "comment_assignment":
        return await _comment_assignment_view(
            db,
            notification=notification,
            user=user,
            snapshot=snapshot,
        )
    if kind in _CREDIT_REQUEST_KINDS:
        return await _credit_request_view(
            db,
            notification=notification,
            user=user,
            kind=kind,
            snapshot=snapshot,
        )

    safe_data: dict[str, object] = {"kind": kind} if kind else {}
    return _NotificationView(
        type=NotificationType.SYSTEM,
        title=notification.title,
        body=notification.body,
        data=safe_data,
        actionable=False,
        destination=None,
        available=True,
    )


async def _resolve_notification_view(
    db: AsyncSession,
    *,
    notification: Notification,
    user: User,
    snapshot: _NotificationResourceSnapshot | None = None,
) -> _NotificationView:
    notification_type = _type_value(notification)
    if notification_type == DBNotificationType.ANALYSIS_COMPLETE.value:
        return await _analysis_complete_view(
            db,
            notification=notification,
            user=user,
            snapshot=snapshot,
        )
    if notification_type == DBNotificationType.EXPORT_READY.value:
        return await _export_ready_view(
            db,
            notification=notification,
            user=user,
            snapshot=snapshot,
        )
    if notification_type == DBNotificationType.MONITOR_ALERT.value:
        return await _monitor_alert_view(
            db,
            notification=notification,
            user=user,
            snapshot=snapshot,
        )
    if notification_type == DBNotificationType.TEAM_INVITE.value:
        return _team_invite_view(
            notification,
            user,
            capabilities=snapshot.capabilities if snapshot is not None else None,
        )
    if notification_type in {
        DBNotificationType.SYSTEM.value,
        DBNotificationType.BILLING_EVENT.value,
    }:
        return await _system_view(
            db,
            notification=notification,
            user=user,
            snapshot=snapshot,
        )
    return _tombstone(notification_type)


def _empty_notification_resource_references() -> _NotificationResourceReferences:
    return _NotificationResourceReferences(
        analysis_ids=set(),
        export_job_ids=set(),
        monitor_ids=set(),
        alert_ids=set(),
        comment_ids=set(),
        credit_request_ids=set(),
    )


def _collect_credit_request_references(
    data: Mapping[str, object],
    *,
    kind: str,
    capabilities: PrincipalCapabilitiesResponse,
    references: _NotificationResourceReferences,
) -> None:
    admin_action = kind in {
        "credit_capacity_request",
        "credit_capacity_requests_auto_fulfilled_admin",
    }
    if admin_action and not capabilities.can_manage_billing:
        return
    if not admin_action and not capabilities.can_view_billing:
        return

    request_id = _uuid_value(data, "request_id")
    if request_id is not None:
        references.credit_request_ids.add(request_id)
    references.credit_request_ids.update(_uuid_values(data, "request_ids"))


def _collect_system_resource_reference(
    data: Mapping[str, object],
    *,
    capabilities: PrincipalCapabilitiesResponse,
    references: _NotificationResourceReferences,
) -> None:
    raw_kind = data.get("kind")
    kind = raw_kind if isinstance(raw_kind, str) and len(raw_kind) <= 64 else ""
    if kind == "comment_assignment":
        if capabilities.can_view_review_queue:
            comment_id = _uuid_value(data, "comment_id")
            if comment_id is not None:
                references.comment_ids.add(comment_id)
        return
    if kind not in _CREDIT_REQUEST_KINDS:
        return
    _collect_credit_request_references(
        data,
        kind=kind,
        capabilities=capabilities,
        references=references,
    )


def _collect_notification_resource_reference(
    notification: Notification,
    *,
    capabilities: PrincipalCapabilitiesResponse,
    references: _NotificationResourceReferences,
) -> None:
    notification_type = _type_value(notification)
    data = _data_mapping(notification)

    if notification_type == DBNotificationType.ANALYSIS_COMPLETE.value:
        analysis_id = _uuid_value(data, "analysis_id")
        if analysis_id is not None:
            references.analysis_ids.add(analysis_id)
        return

    if notification_type == DBNotificationType.EXPORT_READY.value:
        if capabilities.can_export_report:
            export_job_id = _uuid_value(data, "export_job_id", "job_id", "export_id")
            if export_job_id is not None:
                references.export_job_ids.add(export_job_id)
        return

    if notification_type == DBNotificationType.MONITOR_ALERT.value:
        if capabilities.can_manage_monitors:
            monitor_id = _uuid_value(data, "monitor_id")
            if monitor_id is not None:
                references.monitor_ids.add(monitor_id)
                alert_id = _uuid_value(data, "alert_id", "monitor_alert_id")
                if alert_id is not None:
                    references.alert_ids.add(alert_id)
        return

    if notification_type in {
        DBNotificationType.SYSTEM.value,
        DBNotificationType.BILLING_EVENT.value,
    }:
        _collect_system_resource_reference(
            data,
            capabilities=capabilities,
            references=references,
        )


def _collect_notification_resource_references(
    notifications: list[Notification],
    *,
    capabilities: PrincipalCapabilitiesResponse,
) -> _NotificationResourceReferences:
    references = _empty_notification_resource_references()
    for notification in notifications:
        _collect_notification_resource_reference(
            notification,
            capabilities=capabilities,
            references=references,
        )
    return references


async def _load_available_analysis_ids(
    db: AsyncSession,
    *,
    analysis_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> frozenset[uuid.UUID]:
    if not analysis_ids:
        return frozenset()
    result = await db.execute(
        select(Analysis.id).where(
            Analysis.id.in_(analysis_ids),
            Analysis.org_id == org_id,
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.report_data.is_not(None),
        )
    )
    return frozenset(result.scalars().all())


async def _load_export_analysis_by_job(
    db: AsyncSession,
    *,
    export_job_ids: set[uuid.UUID],
    user: User,
) -> dict[uuid.UUID, uuid.UUID]:
    if not export_job_ids:
        return {}
    result = await db.execute(
        select(ExportJob.id, ExportJob.analysis_id)
        .join(Analysis, Analysis.id == ExportJob.analysis_id)
        .where(
            ExportJob.id.in_(export_job_ids),
            ExportJob.org_id == user.org_id,
            ExportJob.user_id == user.id,
            ExportJob.status == ExportStatus.COMPLETED,
            Analysis.org_id == user.org_id,
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.report_data.is_not(None),
        )
    )
    return {job_id: analysis_id for job_id, analysis_id in result.all()}


async def _load_available_monitor_ids(
    db: AsyncSession,
    *,
    monitor_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> frozenset[uuid.UUID]:
    if not monitor_ids:
        return frozenset()
    result = await db.execute(
        select(Monitor.id).where(
            Monitor.id.in_(monitor_ids),
            Monitor.org_id == org_id,
        )
    )
    return frozenset(result.scalars().all())


async def _load_alert_monitor_pairs(
    db: AsyncSession,
    *,
    alert_ids: set[uuid.UUID],
    monitor_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> frozenset[tuple[uuid.UUID, uuid.UUID]]:
    if not alert_ids:
        return frozenset()
    result = await db.execute(
        select(MonitorAlert.id, MonitorAlert.monitor_id).where(
            MonitorAlert.id.in_(alert_ids),
            MonitorAlert.monitor_id.in_(monitor_ids),
            MonitorAlert.org_id == org_id,
        )
    )
    return frozenset((alert_id, monitor_id) for alert_id, monitor_id in result.all())


async def _load_comment_analysis_by_id(
    db: AsyncSession,
    *,
    comment_ids: set[uuid.UUID],
    user: User,
) -> dict[uuid.UUID, uuid.UUID]:
    if not comment_ids:
        return {}
    result = await db.execute(
        select(Comment.id, Comment.analysis_id)
        .join(Analysis, Analysis.id == Comment.analysis_id)
        .where(
            Comment.id.in_(comment_ids),
            Comment.org_id == user.org_id,
            Comment.assigned_to == user.id,
            Analysis.org_id == user.org_id,
            Analysis.status != AnalysisStatus.DELETED,
        )
    )
    return {comment_id: analysis_id for comment_id, analysis_id in result.all()}


async def _load_credit_requester_by_id(
    db: AsyncSession,
    *,
    request_ids: set[uuid.UUID],
    org_id: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID | None]:
    if not request_ids:
        return {}
    result = await db.execute(
        select(CreditCapacityRequest.id, CreditCapacityRequest.requester_user_id).where(
            CreditCapacityRequest.id.in_(request_ids),
            CreditCapacityRequest.org_id == org_id,
        )
    )
    return {request_id: requester_user_id for request_id, requester_user_id in result.all()}


async def _build_notification_resource_snapshot(
    db: AsyncSession,
    *,
    notifications: list[Notification],
    user: User,
) -> _NotificationResourceSnapshot:
    """Batch-load current resource availability for one notification page."""
    capabilities = build_principal_capabilities(user)
    references = _collect_notification_resource_references(
        notifications,
        capabilities=capabilities,
    )

    # Keep the scoped loads sequential: their order is part of the deterministic
    # page-snapshot contract and each failure must stop subsequent database work.
    available_analysis_ids = await _load_available_analysis_ids(
        db,
        analysis_ids=references.analysis_ids,
        org_id=user.org_id,
    )
    export_analysis_by_job = await _load_export_analysis_by_job(
        db,
        export_job_ids=references.export_job_ids,
        user=user,
    )
    available_monitor_ids = await _load_available_monitor_ids(
        db,
        monitor_ids=references.monitor_ids,
        org_id=user.org_id,
    )
    alert_monitor_pairs = await _load_alert_monitor_pairs(
        db,
        alert_ids=references.alert_ids,
        monitor_ids=references.monitor_ids,
        org_id=user.org_id,
    )
    comment_analysis_by_id = await _load_comment_analysis_by_id(
        db,
        comment_ids=references.comment_ids,
        user=user,
    )
    credit_requester_by_id = await _load_credit_requester_by_id(
        db,
        request_ids=references.credit_request_ids,
        org_id=user.org_id,
    )

    return _NotificationResourceSnapshot(
        capabilities=capabilities,
        analysis_ids=available_analysis_ids,
        export_analysis_by_job=export_analysis_by_job,
        monitor_ids=available_monitor_ids,
        alert_monitor_pairs=alert_monitor_pairs,
        comment_analysis_by_id=comment_analysis_by_id,
        credit_requester_by_id=credit_requester_by_id,
    )


def _serialize_notification(
    notification: Notification,
    view: _NotificationView,
) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        type=view.type,
        title=view.title,
        body=view.body,
        read=notification.read,
        data=view.data,
        actionable=view.actionable,
        tombstoned=not view.available,
        created_at=notification.created_at,
    )


async def list_notifications_page(
    db: AsyncSession,
    *,
    user: User,
    page: int,
    per_page: int,
) -> NotificationPage:
    """Return paginated notifications plus unread counts for a user/org."""
    base_query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.org_id == user.org_id,
    )
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar_one()
    unread_count = (
        await db.execute(
            select(func.count()).select_from(
                base_query.where(Notification.read == False).subquery()  # noqa: E712
            )
        )
    ).scalar_one()
    items = list(
        (
            await db.execute(
                base_query.order_by(Notification.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        )
        .scalars()
        .all()
    )
    snapshot = await _build_notification_resource_snapshot(
        db,
        notifications=items,
        user=user,
    )
    safe_items = [
        _serialize_notification(
            notification,
            await _resolve_notification_view(
                db,
                notification=notification,
                user=user,
                snapshot=snapshot,
            ),
        )
        for notification in items
    ]
    return NotificationPage(
        items=safe_items,
        unread_count=int(unread_count),
        total=int(total),
    )


async def resolve_notification_action(
    db: AsyncSession,
    *,
    user: User,
    notification_id: uuid.UUID,
) -> NotificationActionResult:
    """Resolve a safe destination and mark read only after successful resolution."""
    result = await db.execute(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.org_id == user.org_id,
        )
        .with_for_update()
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise APIError(404, "Not Found", "Notification action unavailable")

    view = await _resolve_notification_view(db, notification=notification, user=user)
    if not view.available:
        raise APIError(404, "Not Found", "Notification action unavailable")
    if not view.actionable or view.destination is None:
        return NotificationActionResult(
            notification_id=notification.id,
            actionable=False,
            destination=None,
            marked_read=False,
        )

    marked_read = not notification.read
    if marked_read:
        notification.read = True
        try:
            await db.flush()
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        logger.info(
            "notification_action_resolved",
            notification_id=str(notification.id),
            org_id=str(user.org_id),
            user_id=str(user.id),
        )
    return NotificationActionResult(
        notification_id=notification.id,
        actionable=True,
        destination=view.destination,
        marked_read=marked_read,
    )


async def get_unread_notification_count(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> int:
    """Return unread notification count for a user/org pair."""
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read == False,  # noqa: E712
        )
    )
    return int(result.scalar_one())


async def mark_notifications_read(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    notification_ids: list[uuid.UUID],
) -> int:
    """Mark specific notifications as read and return the count updated."""
    if not notification_ids:
        return 0

    result = await db.execute(
        update(Notification)
        .where(
            Notification.id.in_(notification_ids),
            Notification.user_id == user_id,
            Notification.org_id == org_id,
        )
        .values(read=True)
    )
    marked = max(int(getattr(result, "rowcount", 0) or 0), 0)
    if marked == 0:
        return 0
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "notifications_marked_read",
        user_id=str(user_id),
        count=marked,
        ids=[str(notification_id) for notification_id in notification_ids],
    )
    return marked


async def dismiss_all_notifications(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> int:
    """Mark all unread notifications as read and return the count updated."""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read == False,  # noqa: E712
        )
        .values(read=True)
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    marked = max(int(getattr(result, "rowcount", 0) or 0), 0)
    logger.info(
        "notifications_all_dismissed",
        user_id=str(user_id),
        count=marked,
    )
    return marked


def get_notification_preferences(user: User) -> dict:
    """Read notification preferences from the user JSONB preferences blob."""
    prefs = user.preferences or {}
    stored_frequency = prefs.get("email_digest_frequency", "weekly")
    normalized_frequency = _LEGACY_DIGEST_FREQUENCY_NORMALIZATION.get(
        stored_frequency,
        stored_frequency,
    )
    if normalized_frequency != stored_frequency:
        logger.warning(
            "notification_digest_frequency_normalized",
            user_id=str(user.id),
            stored_frequency=stored_frequency,
            normalized_frequency=normalized_frequency,
        )
    if normalized_frequency not in _SUPPORTED_DIGEST_FREQUENCIES:
        raise ValueError("Stored email digest frequency is unsupported")
    return {
        "email_on_analysis_complete": prefs.get("email_on_analysis_complete", True),
        "email_on_monitor_alert": prefs.get("email_on_monitor_alert", True),
        "email_digest_frequency": normalized_frequency,
    }


async def update_notification_preferences(
    db: AsyncSession,
    *,
    user: User,
    body: NotificationPreferencesSchema,
) -> dict:
    """Update notification preferences without overwriting unrelated user prefs."""
    # Refetch with a row lock to prevent lost-update race with the weekly-digest worker.
    result = await db.execute(select(User).where(User.id == user.id).with_for_update())
    locked_user = result.scalar_one_or_none()
    if locked_user is None:
        raise RuntimeError(f"User {user.id} disappeared between auth and preference update")
    current_prefs = dict(locked_user.preferences or {})
    current_prefs["email_on_analysis_complete"] = body.email_on_analysis_complete
    current_prefs["email_on_monitor_alert"] = body.email_on_monitor_alert
    current_prefs["email_digest_frequency"] = body.email_digest_frequency.value
    locked_user.preferences = current_prefs
    try:
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "notification_preferences_updated",
        user_id=str(user.id),
        prefs={
            "email_on_analysis_complete": body.email_on_analysis_complete,
            "email_on_monitor_alert": body.email_on_monitor_alert,
            "email_digest_frequency": body.email_digest_frequency.value,
        },
    )
    return {
        "email_on_analysis_complete": body.email_on_analysis_complete,
        "email_on_monitor_alert": body.email_on_monitor_alert,
        "email_digest_frequency": body.email_digest_frequency.value,
    }


async def unsubscribe_weekly_digest(
    db: AsyncSession,
    *,
    token: str,
    token_locator: str,
    request: Request,
) -> dict[str, str]:
    """Disable digests through an opaque DB-bound capability.

    Every invalid, expired, consumed, deleted, and successful capability returns
    the same response. The raw token is accepted only in the request body and
    never appears in the API path or structured logs.
    """
    try:
        expected_locator = unsubscribe_token_locator(token)
        token_digest = digest_unsubscribe_token(token)
    except InvalidUnsubscribeTokenError:
        return {"status": "unsubscribed"}
    if not hmac.compare_digest(expected_locator, token_locator):
        return {"status": "unsubscribed"}

    await db.execute(
        select(
            func.set_config(
                "app.digest_unsubscribe_token_digest",
                token_digest,
                True,
            )
        )
    )
    result = await db.execute(
        select(
            WeeklyDigestDelivery.id,
            WeeklyDigestDelivery.org_id,
            WeeklyDigestDelivery.user_id,
            WeeklyDigestDelivery.unsubscribe_expires_at,
            WeeklyDigestDelivery.unsubscribe_used_at,
        ).where(
            WeeklyDigestDelivery.unsubscribe_token_digest == token_digest,
        )
    )
    capability = result.one_or_none()
    now = datetime.now(UTC)
    if (
        capability is None
        or capability.unsubscribe_expires_at is None
        or capability.unsubscribe_expires_at < now
        or capability.unsubscribe_used_at is not None
    ):
        return {"status": "unsubscribed"}

    await db.execute(select(func.set_config("app.current_org_id", str(capability.org_id), True)))
    result = await db.execute(
        select(User)
        .where(
            User.id == capability.user_id,
            User.org_id == capability.org_id,
        )
        .with_for_update()
    )
    locked_user = result.scalar_one_or_none()
    if locked_user is None:
        return {"status": "unsubscribed"}

    # The weekly sender locks user -> delivery. Match that order here to avoid
    # deadlocks while still revalidating the capability after both locks are
    # held. A consumed link cannot disable a later explicit re-subscription.
    result = await db.execute(
        select(WeeklyDigestDelivery)
        .where(
            WeeklyDigestDelivery.id == capability.id,
            WeeklyDigestDelivery.org_id == capability.org_id,
            WeeklyDigestDelivery.user_id == capability.user_id,
            WeeklyDigestDelivery.unsubscribe_token_digest == token_digest,
        )
        .with_for_update()
    )
    delivery = result.scalar_one_or_none()
    if (
        delivery is None
        or delivery.unsubscribe_expires_at is None
        or delivery.unsubscribe_expires_at < now
        or delivery.unsubscribe_used_at is not None
    ):
        return {"status": "unsubscribed"}

    delivery.unsubscribe_used_at = now
    current_prefs = dict(locked_user.preferences or {})
    if current_prefs.get("email_digest_frequency") == "off":
        await db.commit()
        return {"status": "unsubscribed"}

    current_prefs["email_digest_frequency"] = "off"
    current_prefs["digest_unsubscribed_at"] = now.isoformat()
    current_prefs.pop("last_weekly_digest_reserved_at", None)
    locked_user.preferences = current_prefs
    try:
        await write_audit_log(
            db,
            org_id=delivery.org_id,
            user_id=delivery.user_id,
            action="notifications.weekly_digest_unsubscribed",
            details={
                "channel": "email",
                "digest_frequency": "off",
                "source": "one_click",
                "unsubscribed_at": now.isoformat(),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "weekly_digest_unsubscribed",
        org_id=str(delivery.org_id),
        user_id=str(delivery.user_id),
    )
    return {"status": "unsubscribed"}
