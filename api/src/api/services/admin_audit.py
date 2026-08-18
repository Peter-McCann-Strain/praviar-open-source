"""Audit-log helpers for admin dashboards."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AuditLog, User
from api.schemas.admin import AuditLogEntry
from api.services.admin_health import AdminAuditLogPage
from api.services.admin_query_utils import execute_paged_query, load_id_map


async def list_audit_logs_page_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    action: str | None,
    user_id: uuid.UUID | None,
    page: int,
    per_page: int,
) -> AdminAuditLogPage:
    base_query = select(AuditLog).where(AuditLog.org_id == org_id)
    count_query = select(func.count()).select_from(AuditLog).where(AuditLog.org_id == org_id)

    if action:
        base_query = base_query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if user_id:
        base_query = base_query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)

    total, logs = await execute_paged_query(
        db,
        base_query=base_query,
        count_query=count_query,
        order_by=AuditLog.created_at.desc(),
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
        AuditLogEntry(
            id=log.id,
            action=log.action,
            user_id=log.user_id,
            user_email=user_emails.get(log.user_id, "") if log.user_id else "",
            analysis_id=log.analysis_id,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in logs
    ]
    return AdminAuditLogPage(items=items, total=total)
