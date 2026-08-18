"""Celery application factory with persistent async event loop."""

from __future__ import annotations

import asyncio
import atexit
import threading
from collections.abc import Coroutine
from typing import Any

import structlog
from celery import Celery

from api.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

celery_app = Celery(
    "praviar",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="praviar_json",
    accept_content=["praviar_json", "json"],
    result_serializer="praviar_json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_soft_time_limit,
    task_time_limit=settings.celery_hard_time_limit,
)

celery_app.autodiscover_tasks(["api.workers"])

# ---------------------------------------------------------------------------
# Kombu JSON encoder — T1-03
#
# Audit (2026-05-20): all current task signatures pass `str` IDs only; no task
# argument is typed as a Pydantic model, uuid.UUID, or datetime. This encoder is
# registered defensively so future tasks can safely pass those types without
# hitting Python's default json.JSONEncoder TypeError at dispatch time.
# Verify: grep -r "def .*(.*UUID\|datetime\|BaseModel" api/src/api/workers/
# ---------------------------------------------------------------------------

import json  # noqa: E402
import uuid  # noqa: E402
from datetime import date, datetime  # noqa: E402


class _PraviarJSONEncoder(json.JSONEncoder):
    """Extend the default encoder with uuid, datetime, and date support."""

    def default(self, o: object) -> object:
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        try:
            from pydantic import BaseModel

            if isinstance(o, BaseModel):
                return o.model_dump(mode="json")
        except ImportError:
            pass
        return super().default(o)


from kombu.serialization import register as _kombu_register  # noqa: E402

_kombu_register(
    "praviar_json",
    encoder=lambda v: json.dumps(v, cls=_PraviarJSONEncoder),
    decoder=json.loads,
    content_type="application/json",
    content_encoding="utf-8",
)

# ---------------------------------------------------------------------------
# OTel worker initialisation — T1-05
#
# CeleryInstrumentor must be called inside worker_process_init, not at module
# import. Celery forks worker processes; OTel state initialised before the fork
# is duplicated incorrectly, breaking span context propagation across children.
# ---------------------------------------------------------------------------
from celery.signals import worker_process_init  # noqa: E402


@worker_process_init.connect
def _init_otel_in_worker(**_kwargs: object) -> None:
    try:
        from api.observability import configure_otel

        configure_otel(None, settings)
    except Exception:
        logger.warning("otel_celery_worker_init_failed", exc_info=True)
        return

    try:
        import opentelemetry.instrumentation.celery as _otel_celery

        celery_instrumentor = _otel_celery.CeleryInstrumentor

        celery_instrumentor().instrument()
        logger.info("otel_celery_instrumented")
    except ImportError:
        logger.warning(
            "otel_celery_instrumentor_unavailable",
            hint="install opentelemetry-instrumentation-celery",
        )


# ---------------------------------------------------------------------------
# Persistent event loop for async pipeline execution
# ---------------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop running in a daemon thread.

    Thread-safe: uses a module-level lock to prevent race conditions
    when multiple Celery worker threads request the loop concurrently.
    """
    global _loop, _thread  # noqa: PLW0603
    with _lock:
        if _loop is None or _loop.is_closed():
            logger.debug("event_loop_creating", reason="loop is None or closed")
            _loop = asyncio.new_event_loop()
            _thread = threading.Thread(
                target=_loop.run_forever,
                daemon=True,
                name="celery-asyncio-loop",
            )
            _thread.start()
            logger.info(
                "event_loop_started",
                thread_name=_thread.name,
                thread_id=_thread.ident,
            )
    return _loop


def _shutdown_event_loop() -> None:
    """Gracefully stop the persistent event loop on process exit."""
    global _loop, _thread  # noqa: PLW0603
    with _lock:
        if _loop is not None and not _loop.is_closed():
            logger.info("event_loop_shutting_down")
            _loop.call_soon_threadsafe(_loop.stop)
            if _thread is not None:
                _thread.join(timeout=10)
                if _thread.is_alive():
                    logger.error(
                        "event_loop_thread_join_timeout",
                        msg="Event loop thread did not stop within 10s",
                    )
            _loop.close()
            _loop = None
            _thread = None
            logger.info("event_loop_shut_down")


atexit.register(_shutdown_event_loop)


# Default timeout for run_async: use celery hard time limit minus 30s buffer,
# or 3600s if not configured.
_RUN_ASYNC_TIMEOUT = max(60, settings.celery_soft_time_limit - 30)


def run_async(coro: Coroutine[Any, Any, Any], timeout: float | None = None) -> Any:
    """Submit an async coroutine to the persistent event loop and block until done.

    This avoids the overhead of asyncio.run() creating/destroying an event loop
    per task, and allows httpx connection pools to be reused across tasks.

    Args:
        coro: The coroutine to execute.
        timeout: Maximum seconds to wait. Defaults to celery_hard_time_limit - 30s.
                 Raises TimeoutError if exceeded.
    """
    if timeout is None:
        timeout = _RUN_ASYNC_TIMEOUT

    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        logger.error(
            "run_async_timeout",
            timeout_s=timeout,
            msg="Async coroutine exceeded timeout — cancelled",
        )
        raise
