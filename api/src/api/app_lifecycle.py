"""Application lifecycle and request middleware."""

from __future__ import annotations

import logging
import re
import secrets
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.config import get_settings
from api.observability.spans import set_current_span_attributes
from api.security import redact_sensitive_log_data
from api.services.system_health import run_startup_checks

logger = structlog.get_logger()


async def _verify_production_database_privilege_boundary(
    *,
    app_env: str,
    service_role: str,
) -> None:
    if app_env != "prod":
        return
    if service_role == "api":
        from api.db.claimed_use_privileged import (
            verify_claimed_use_privilege_boundary,
        )

        await verify_claimed_use_privilege_boundary()
        return
    if service_role == "worker":
        from api.db.claimed_use_privileged import (
            verify_claimed_use_worker_privilege_boundary,
        )

        await verify_claimed_use_worker_privilege_boundary()


async def _verify_production_epo_provenance(
    *,
    app_env: str,
    service_role: str,
) -> None:
    if app_env != "prod" or service_role != "worker":
        return
    from api.epo_provenance_runtime import verify_epo_provenance_runtime

    await verify_epo_provenance_runtime()


def configure_structlog() -> None:
    """Wire structlog ProcessorFormatter so uvicorn and third-party logs share the same chain.

    Must be called once before the first log event. Safe to call multiple times (idempotent via
    root logger handler check).
    """
    if any(
        isinstance(h, logging.StreamHandler)
        and isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
        for h in logging.getLogger().handlers
    ):
        return

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive_log_data,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False


#: Inbound X-Request-ID is client-controlled. Only echo it back / use it as a
#: log + trace correlation key when it is a bounded, charset-restricted token.
#: Anything else is replaced with a fresh server-generated id so a caller cannot
#: inject oversized values (log/header amplification) or control characters that
#: poison structured-log and trace correlation.
_REQUEST_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")


def _resolve_request_id(raw: str | None) -> str:
    if raw is not None and _REQUEST_ID_RE.match(raw):
        return raw
    return secrets.token_hex(16)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach request_id to every request and log entry/exit with timing."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id

        start = time.monotonic()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        set_current_span_attributes(
            {
                "praviar.request_id": request_id,
                "http.request.method": request.method,
            }
        )

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.exception(
                "request_error",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise
        else:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-API-Version"] = "1"
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def build_lifespan(*, engine):
    """Create the FastAPI lifespan manager using the provided engine."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        """Startup/shutdown lifecycle — verifies infrastructure before accepting traffic."""
        import redis.asyncio as aioredis

        from api.cache import redis_connection_kwargs
        from api.db.session import async_session_factory

        configure_structlog()

        settings = get_settings()
        assert settings.app_env is not None
        logger.info(
            "api_starting",
            app_env=settings.app_env,
            debug=settings.debug,
            api_prefix=settings.api_prefix,
            cors_origins_count=len(settings.cors_origins),
        )

        await run_startup_checks(
            app_env=settings.app_env,
            database_url=settings.database_url,
            redis_url=settings.redis_url,
            db_pool_size=settings.db_pool_size,
            db_max_overflow=settings.db_max_overflow,
            async_session_factory_fn=async_session_factory,
            redis_from_url_fn=aioredis.from_url,
            logger=logger,
            redis_connection_kwargs=redis_connection_kwargs(settings),
        )
        await _verify_production_database_privilege_boundary(
            app_env=settings.app_env,
            service_role=settings.service_role,
        )
        await _verify_production_epo_provenance(
            app_env=settings.app_env,
            service_role=settings.service_role,
        )

        from api.metrics import build_info

        build_info.labels(
            version=settings.release_version,
            environment=settings.deployment_env,
        ).set(1)

        logger.info(
            "api_ready",
            sentry_enabled=bool(settings.sentry_dsn),
            gcs_enabled=bool(settings.gcs_bucket_name),
            clerk_configured=bool(settings.clerk_secret_key),
        )

        yield

        # Shutdown sequence: flush OTel spans, then release DB pool.
        # Uvicorn owns SIGTERM/SIGINT handling; we do not override its signal handlers.
        try:
            from api.observability import shutdown_otel

            await shutdown_otel()
        except Exception:
            logger.warning("otel_shutdown_error", exc_info=True)

        try:
            from api.cache import close_redis_pool

            await close_redis_pool()
        except Exception:
            logger.warning("redis_pool_shutdown_error", exc_info=True)

        await engine.dispose()
        from api.db.claimed_use_privileged import (
            dispose_claimed_use_privileged_engines,
        )

        await dispose_claimed_use_privileged_engines()
        if settings.service_role == "worker":
            from api.epo_provenance_runtime import dispose_epo_provenance_runtime

            await dispose_epo_provenance_runtime()
        logger.info("api_shutdown")

    return lifespan
