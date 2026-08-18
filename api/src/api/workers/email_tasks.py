"""Celery-compatible task wrappers for async email delivery."""

from api.workers.celery_app import celery_app
from api.workers.email_task_actions import (
    send_analysis_complete_email_task,
    send_monitor_alert_email_task,
    send_welcome_email_task,
)
from api.workers.email_task_weekly import send_weekly_digest_task


class _TerminalEmailTask:
    """Task adapter for non-Celery execution paths.

    The shared email task helpers call ``task.retry`` when a send fails.
    Cloud Tasks execution reaches this module after the HTTP task has already
    been accepted, so there is no Celery retry signal to propagate. Treat those
    failures as terminal structured failures instead of pretending a retry was
    scheduled.
    """

    MaxRetriesExceededError = RuntimeError

    def retry(self, *, exc: Exception) -> None:
        raise self.MaxRetriesExceededError(str(exc))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_analysis_complete_email(self, user_id: str, analysis_id: str) -> dict:
    return send_analysis_complete_email_task(self, user_id, analysis_id)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_monitor_alert_email(
    self,
    user_id: str,
    monitor_id: str,
    alert_id: str,
    org_id: str,
) -> dict:
    return execute_monitor_alert_email(
        user_id=user_id,
        monitor_id=monitor_id,
        alert_id=alert_id,
        org_id=org_id,
        task=self,
    )


def execute_monitor_alert_email(
    *,
    user_id: str,
    monitor_id: str,
    alert_id: str,
    org_id: str,
    task=None,
) -> dict:
    """Execute one monitor alert email outside Celery."""
    return send_monitor_alert_email_task(
        task or _TerminalEmailTask(),
        user_id,
        monitor_id,
        alert_id,
        org_id,
    )


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def send_welcome_email(self, user_id: str) -> dict:
    return send_welcome_email_task(self, user_id)


@celery_app.task(bind=True, max_retries=2)
def send_weekly_digest(self) -> dict:
    result = execute_weekly_digest(task=self)
    if result.get("status") == "retry_later":
        raise self.retry(
            countdown=int(
                result.get(
                    "retry_after_seconds",
                    60,
                )
            )
        )
    return result


def execute_weekly_digest(*, task=None) -> dict:
    """Execute the weekly digest sweep outside Celery."""
    return send_weekly_digest_task(task or _TerminalEmailTask())
