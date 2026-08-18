"""Task body helpers for one-off email worker jobs."""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from api.db.session import bind_org_to_sync_session
from api.workers.celery_app import run_async
from api.workers.email_task_payloads import (
    build_analysis_complete_send_kwargs,
    build_monitor_alert_send_kwargs,
    build_welcome_send_kwargs,
    map_email_task_result,
)
from api.workers.email_task_retry import retry_email_task
from api.workers.email_task_runtime import get_sync_engine, send_email_async

logger = structlog.get_logger()


def _same_org(left, right) -> bool:
    return str(getattr(left, "org_id", "") or "") == str(getattr(right, "org_id", "") or "")


def _matches_org(entity, org_id: str) -> bool:
    return str(getattr(entity, "org_id", "") or "") == str(org_id or "")


def send_analysis_complete_email_task(task, user_id: str, analysis_id: str) -> dict:
    """Look up user + analysis, then send the analysis-complete email."""
    logger.info(
        "email_task_analysis_complete",
        user_id=user_id,
        analysis_id=analysis_id,
    )
    engine = get_sync_engine()

    try:
        with Session(engine) as db:
            from api.db.models import Analysis, User

            # Users table is not RLS-protected; load first to get org_id for binding.
            user = db.get(User, user_id)
            if not user:
                logger.warning(
                    "email_task_missing_data",
                    user_found=False,
                    analysis_found=None,
                    user_id=user_id,
                    analysis_id=analysis_id,
                )
                return {"status": "skipped", "reason": "user or analysis not found"}

            bind_org_to_sync_session(db, getattr(user, "org_id", None))
            analysis = db.get(Analysis, analysis_id, with_for_update=True)

            if not analysis:
                logger.warning(
                    "email_task_missing_data",
                    user_found=True,
                    analysis_found=False,
                    user_id=user_id,
                    analysis_id=analysis_id,
                )
                return {"status": "skipped", "reason": "user or analysis not found"}

            if not _same_org(user, analysis):
                logger.error(
                    "email_task_analysis_tenant_mismatch",
                    user_id=user_id,
                    analysis_id=analysis_id,
                    user_org_id=str(getattr(user, "org_id", "")),
                    analysis_org_id=str(getattr(analysis, "org_id", "")),
                )
                return {"status": "skipped", "reason": "tenant mismatch"}

            if getattr(analysis, "completion_email_sent_at", None) is not None:
                logger.info(
                    "email_task_analysis_complete_already_sent",
                    analysis_id=analysis_id,
                    sent_at=str(analysis.completion_email_sent_at),
                )
                return {"status": "skipped", "reason": "already_sent"}

            payload = build_analysis_complete_send_kwargs(
                user=user,
                analysis=analysis,
                analysis_id=analysis_id,
            )

            async def _send(client):
                return await client.send_analysis_complete(**payload)

            result = run_async(send_email_async(_send))

            if result.success:
                from datetime import UTC, datetime

                analysis.completion_email_sent_at = datetime.now(UTC)
                db.commit()

            logger.info(
                "email_task_analysis_complete_done",
                success=result.success,
                message_id=result.message_id,
                error=result.error,
            )
            return map_email_task_result(result)

    except Exception as exc:
        return retry_email_task(
            task,
            exc,
            failure_event="email_task_analysis_complete_failed",
            max_retries_event="email_task_analysis_complete_max_retries",
            log_kwargs={"user_id": user_id, "analysis_id": analysis_id},
        )


def send_monitor_alert_email_task(
    task,
    user_id: str,
    monitor_id: str,
    alert_id: str,
    org_id: str,
) -> dict:
    """Look up user + monitor + alert, then send the alert email."""
    logger.info(
        "email_task_monitor_alert",
        user_id=user_id,
        monitor_id=monitor_id,
        alert_id=alert_id,
        org_id=org_id,
    )
    engine = get_sync_engine()

    try:
        with Session(engine) as db:
            bind_org_to_sync_session(db, org_id)
            from api.db.models import Monitor, MonitorAlert, User

            user = db.get(User, user_id)
            monitor = db.get(Monitor, monitor_id)
            alert = db.get(MonitorAlert, alert_id, with_for_update=True)

            if not user or not monitor or not alert:
                logger.warning(
                    "email_task_monitor_missing_data",
                    user_found=user is not None,
                    monitor_found=monitor is not None,
                    alert_found=alert is not None,
                )
                return {"status": "skipped", "reason": "data not found"}

            # Ownership/tenant checks run first so the idempotency short-circuit
            # cannot mask a cross-tenant payload (mirrors send_analysis_complete_email_task).
            if not _same_org(user, monitor):
                logger.error(
                    "email_task_monitor_tenant_mismatch",
                    user_id=user_id,
                    monitor_id=monitor_id,
                    alert_id=alert_id,
                    user_org_id=str(getattr(user, "org_id", "")),
                    monitor_org_id=str(getattr(monitor, "org_id", "")),
                )
                return {"status": "skipped", "reason": "tenant mismatch"}

            if not _matches_org(user, org_id) or not _matches_org(monitor, org_id):
                logger.error(
                    "email_task_monitor_payload_org_mismatch",
                    user_id=user_id,
                    monitor_id=monitor_id,
                    alert_id=alert_id,
                    payload_org_id=org_id,
                    user_org_id=str(getattr(user, "org_id", "")),
                    monitor_org_id=str(getattr(monitor, "org_id", "")),
                )
                return {"status": "skipped", "reason": "tenant mismatch"}

            if str(getattr(alert, "monitor_id", "") or "") != str(getattr(monitor, "id", "") or ""):
                logger.error(
                    "email_task_monitor_alert_mismatch",
                    user_id=user_id,
                    monitor_id=monitor_id,
                    alert_id=alert_id,
                    alert_monitor_id=str(getattr(alert, "monitor_id", "")),
                )
                return {"status": "skipped", "reason": "monitor alert mismatch"}

            if getattr(alert, "email_sent_at", None) is not None:
                logger.info(
                    "email_task_monitor_alert_already_sent",
                    alert_id=alert_id,
                    sent_at=str(alert.email_sent_at),
                )
                return {"status": "skipped", "reason": "already_sent"}

            payload = build_monitor_alert_send_kwargs(
                user=user,
                monitor=monitor,
                alert=alert,
            )

            async def _send(client):
                return await client.send_monitor_alert(**payload)

            result = run_async(send_email_async(_send))

            if result.success:
                from datetime import UTC, datetime

                alert.email_sent_at = datetime.now(UTC)
                db.commit()

            logger.info(
                "email_task_monitor_alert_done",
                success=result.success,
                message_id=result.message_id,
            )
            return map_email_task_result(result)

    except Exception as exc:
        return retry_email_task(
            task,
            exc,
            failure_event="email_task_monitor_alert_failed",
            max_retries_event="email_task_monitor_alert_max_retries",
            log_kwargs={"user_id": user_id, "alert_id": alert_id, "org_id": org_id},
        )


def send_welcome_email_task(task, user_id: str) -> dict:
    """Send welcome email to a new user."""
    logger.info("email_task_welcome", user_id=user_id)
    engine = get_sync_engine()

    try:
        with Session(engine) as db:
            from api.db.models import User

            user = db.get(User, user_id, with_for_update=True)
            if not user:
                logger.warning("email_task_welcome_user_not_found", user_id=user_id)
                return {"status": "skipped", "reason": "user not found"}

            if getattr(user, "welcome_email_sent_at", None) is not None:
                logger.info(
                    "email_task_welcome_already_sent",
                    user_id=user_id,
                    sent_at=str(user.welcome_email_sent_at),
                )
                return {"status": "skipped", "reason": "already_sent"}

            payload = build_welcome_send_kwargs(user=user)

            async def _send(client):
                return await client.send_welcome(**payload)

            result = run_async(send_email_async(_send))

            if result.success:
                from datetime import UTC, datetime

                user.welcome_email_sent_at = datetime.now(UTC)
                db.commit()

            logger.info(
                "email_task_welcome_done",
                success=result.success,
                message_id=result.message_id,
            )
            return map_email_task_result(result)

    except Exception as exc:
        return retry_email_task(
            task,
            exc,
            failure_event="email_task_welcome_failed",
            max_retries_event="email_task_welcome_max_retries",
            log_kwargs={"user_id": user_id},
        )
