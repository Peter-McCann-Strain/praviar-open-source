"""Shared retry helpers for email worker tasks."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def retry_email_task(
    task,
    exc: Exception,
    *,
    failure_event: str,
    max_retries_event: str,
    log_kwargs: dict,
) -> dict:
    """Log a task failure and retry through Celery.

    Celery's ``task.retry()`` raises a ``Retry`` exception that the worker
    MUST see in order to requeue the task. The previous implementation
    caught that signal and returned a "failed" dict, which silently
    suppressed retries. We now let the ``Retry`` exception propagate.

    The only branch that returns a structured failure record is
    ``MaxRetriesExceededError`` — at that point the task is terminally
    failed and the caller needs a result, not another retry.
    """
    logger.error(failure_event, **log_kwargs, error=str(exc), exc_info=True)
    try:
        task.retry(exc=exc)
    except task.MaxRetriesExceededError:
        logger.error(max_retries_event, **log_kwargs)
        return {"status": "failed", "error": str(exc)}
    # If task.retry() did not raise (e.g. a misconfigured task or a test
    # double), force a fail-fast surface rather than silently swallowing.
    raise RuntimeError("task.retry() did not raise; Celery retry visibility is broken") from exc
