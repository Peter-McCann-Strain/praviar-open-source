"""Audit log helper — records user actions for compliance and debugging."""

from __future__ import annotations

import uuid

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.client_ip import get_client_ip
from api.db.models import AuditLog

logger = structlog.get_logger()


async def write_audit_log(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    analysis_id: uuid.UUID | None = None,
    action: str,
    details: dict | None = None,
    request: Request | None = None,
    fail_closed: bool = False,
) -> None:
    """Write an audit log entry.

    By default audit failures are logged but do not crash the request. Sensitive
    flows can set ``fail_closed`` so the caller can roll back the enclosing
    transaction instead of creating an unaudited artifact.
    """
    ip = ""
    if request and request.client:
        ip = get_client_ip(request)

    audit_details = dict(details or {})
    actor_type = None
    api_key_id = None
    if request is not None:
        state = getattr(request, "state", None)
        candidate_actor_type = getattr(state, "auth_actor_type", None)
        candidate_api_key_id = getattr(state, "auth_api_key_id", None)
        if candidate_actor_type in {"clerk_user", "api_key"}:
            actor_type = candidate_actor_type
        if actor_type == "api_key" and isinstance(candidate_api_key_id, str):
            try:
                api_key_id = str(uuid.UUID(candidate_api_key_id))
            except ValueError:
                logger.warning("audit_invalid_api_key_actor_id", action=action)
                if fail_closed:
                    raise
    if actor_type:
        audit_details["actor_type"] = actor_type
    if api_key_id:
        audit_details["api_key_id"] = api_key_id

    try:
        log = AuditLog(
            org_id=org_id,
            user_id=user_id,
            analysis_id=analysis_id,
            action=action,
            details=audit_details,
            ip_address=ip[:45],
        )
        db.add(log)
        await db.flush()
        logger.info(
            "audit_log",
            action=action,
            user_id=str(user_id) if user_id else None,
            analysis_id=str(analysis_id) if analysis_id else None,
            ip_address=ip[:45] if ip else None,
            actor_type=actor_type,
            api_key_id=api_key_id,
        )
    except Exception as exc:
        # Broad catch intentional for the default best-effort mode.
        # Database exceptions can render SQL parameters in both ``str(exc)``
        # and traceback output. Audit details may contain recipient identity or
        # other customer metadata, so keep this failure signal deliberately
        # closed and let the request's normal error boundary own diagnostics.
        logger.error(
            "audit_log_failed",
            action=action,
            user_id=str(user_id) if user_id else None,
            analysis_id=str(analysis_id) if analysis_id else None,
            error_type=type(exc).__name__,
        )
        if fail_closed:
            raise
