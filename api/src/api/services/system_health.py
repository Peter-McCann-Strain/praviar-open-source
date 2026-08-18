"""Infrastructure health checks shared by startup and readiness endpoints."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Literal

# Maximum time allowed per individual dependency probe in the health check.
# We never let a slow dependency stall the health endpoint — the probe returns
# "degraded" rather than blocking the load-balancer health poll.
HEALTH_CHECK_TIMEOUT_SECONDS = 0.1

CheckStatus = Literal["ok", "degraded", "error"]


async def check_database_health(*, async_session_factory_fn) -> None:
    """Raise if the database is not reachable."""
    from sqlalchemy import text

    async with async_session_factory_fn() as session:
        await session.execute(text("SELECT 1"))


async def check_migration_head(*, async_session_factory_fn, alembic_cfg_path: str) -> None:
    """Raise if the DB schema is behind the expected Alembic head.

    Prevents the API from serving traffic on a stale schema when migrations
    were skipped or ran out of order.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    cfg = Config(alembic_cfg_path)
    script = ScriptDirectory.from_config(cfg)
    expected = set(script.get_heads())

    async with async_session_factory_fn() as session:
        try:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            current = {row[0] for row in result.fetchall()}
        except Exception:
            current = set()

    if current != expected:
        missing = expected - current
        extra = current - expected
        raise RuntimeError(
            f"Database schema is not at migration head. "
            f"Expected: {sorted(expected)}, current: {sorted(current)}, "
            f"missing: {sorted(missing)}, extra: {sorted(extra)}. "
            "Run 'alembic upgrade head' before starting the API."
        )


async def check_redis_health(
    *,
    redis_url: str,
    redis_from_url_fn,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
) -> None:
    """Raise if Redis is not reachable."""
    redis_client = redis_from_url_fn(redis_url, **dict(redis_connection_kwargs or {}))
    try:
        await redis_client.ping()
    finally:
        await redis_client.aclose()


async def _timed_check(coro) -> tuple[CheckStatus, float, str | None]:
    """Run *coro* with a 100 ms timeout.

    Returns (status, latency_ms, error_detail).

    - "ok"       — completed within the timeout window without raising.
    - "degraded" — timed out; the dependency may be slow but is not confirmed down.
    - "error"    — raised an exception within the timeout window.

    The health endpoint must NEVER fail (5xx) just because a dependency is slow
    or temporarily unreachable.  Callers interpret the returned status.
    """
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(coro, timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
        latency_ms = (time.monotonic() - t0) * 1000
        return "ok", latency_ms, None
    except TimeoutError:
        latency_ms = (time.monotonic() - t0) * 1000
        return "degraded", latency_ms, "timeout"
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return "error", latency_ms, str(exc)


async def collect_health_detail(
    *,
    redis_url: str,
    async_session_factory_fn,
    redis_from_url_fn,
    logger,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured health detail dict for the /api/health endpoint.

    The overall status is "ok" only when all checks pass.  Individual dependency
    degradation is surfaced in the "checks" sub-object so operators can diagnose
    without inspecting logs.  Latency figures help identify slow-but-alive deps.

    This function does NOT raise — the caller decides whether to 200 or 503.
    """
    db_status, db_latency_ms, db_error = await _timed_check(
        check_database_health(async_session_factory_fn=async_session_factory_fn)
    )
    if db_status != "ok":
        logger.error(
            "health_db_check_failed",
            status=db_status,
            error=db_error,
        )

    redis_status, redis_latency_ms, redis_error = await _timed_check(
        check_redis_health(
            redis_url=redis_url,
            redis_from_url_fn=redis_from_url_fn,
            redis_connection_kwargs=redis_connection_kwargs,
        )
    )
    if redis_status != "ok":
        logger.error(
            "health_redis_check_failed",
            status=redis_status,
            error=redis_error,
        )

    checks: dict[str, str] = {
        "database": db_status,
        "redis": redis_status,
    }
    latency_ms: dict[str, float] = {
        "database": round(db_latency_ms, 1),
        "redis": round(redis_latency_ms, 1),
    }

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "latency_ms": latency_ms,
    }


_READINESS_TIMEOUT_SECONDS = 2.0


async def _probe(coro, label: str, logger) -> str | None:
    """Run a readiness probe with a hard timeout. Returns an error string or None."""
    try:
        await asyncio.wait_for(coro, timeout=_READINESS_TIMEOUT_SECONDS)
        return None
    except TimeoutError:
        logger.error("readiness_probe_timeout", check=label, timeout_s=_READINESS_TIMEOUT_SECONDS)
        return f"{label}: timed out"
    except Exception as exc:
        logger.error("readiness_probe_failed", check=label, error=str(exc), exc_info=True)
        return f"{label}: unavailable"


async def collect_readiness_errors(
    *,
    redis_url: str,
    async_session_factory_fn,
    redis_from_url_fn,
    logger,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return readiness failures for the current runtime.

    Used by /api/health/ready — this endpoint IS allowed to return 503 when
    dependencies are down, unlike /api/health which only reports status.
    Probes run concurrently so a slow DB cannot hide a Redis failure.
    """
    db_error, redis_error = await asyncio.gather(
        _probe(
            check_database_health(async_session_factory_fn=async_session_factory_fn),
            "database",
            logger,
        ),
        _probe(
            check_redis_health(
                redis_url=redis_url,
                redis_from_url_fn=redis_from_url_fn,
                redis_connection_kwargs=redis_connection_kwargs,
            ),
            "redis",
            logger,
        ),
    )
    return [e for e in (db_error, redis_error) if e is not None]


async def run_startup_checks(
    *,
    app_env: str,
    database_url: str,
    redis_url: str,
    db_pool_size: int,
    db_max_overflow: int,
    async_session_factory_fn,
    redis_from_url_fn,
    logger,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
    alembic_cfg_path: str = "alembic.ini",
) -> None:
    """Verify external infrastructure before the app starts serving traffic."""
    if app_env == "test":
        logger.info("startup_checks_skipped", reason="APP_ENV=test")
        return

    try:
        await check_database_health(async_session_factory_fn=async_session_factory_fn)
        logger.debug(
            "startup_db_ok",
            database_url=database_url.split("@")[-1] if "@" in database_url else "***",
            pool_size=db_pool_size,
            max_overflow=db_max_overflow,
        )
    except Exception as exc:
        logger.error("startup_db_failed", error=str(exc), exc_info=True)
        raise RuntimeError(f"Database not reachable at startup: {exc}") from exc

    try:
        await check_migration_head(
            async_session_factory_fn=async_session_factory_fn,
            alembic_cfg_path=alembic_cfg_path,
        )
        logger.info("startup_migration_head_ok")
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("startup_migration_check_failed", error=str(exc), exc_info=True)
        raise RuntimeError(f"Migration head check failed at startup: {exc}") from exc

    try:
        await check_redis_health(
            redis_url=redis_url,
            redis_from_url_fn=redis_from_url_fn,
            redis_connection_kwargs=redis_connection_kwargs,
        )
        redis_host = redis_url.split("@")[-1] if "@" in redis_url else redis_url
        logger.debug("startup_redis_ok", redis_host=redis_host)
    except Exception as exc:
        logger.error("startup_redis_failed", error=str(exc), exc_info=True)
        raise RuntimeError(f"Redis not reachable at startup: {exc}") from exc
