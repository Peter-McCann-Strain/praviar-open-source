"""Redis cache utilities for immutable data (reports, etc.)."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from api.config import get_settings

logger = structlog.get_logger()

_redis_pool: aioredis.Redis | None = None
_chat_budget_redis_pool: aioredis.Redis | None = None
DEFAULT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS = 5.0
DEFAULT_REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 30


def _report_cache_key(
    org_id: str,
    analysis_id: str,
    *,
    version: str | None = None,
) -> str:
    if version is None:
        return f"report:{org_id}:{analysis_id}"
    if len(version) != 64 or any(character not in "0123456789abcdef" for character in version):
        raise ValueError("report cache version must be a lowercase SHA-256 digest")
    return f"report:{org_id}:{analysis_id}:{version}"


def redis_connection_kwargs(settings: Any) -> dict[str, float | int]:
    """Return bounded Redis connection kwargs shared by runtime clients."""
    return {
        "socket_connect_timeout": getattr(
            settings,
            "redis_socket_connect_timeout_seconds",
            DEFAULT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
        ),
        "socket_timeout": getattr(
            settings,
            "redis_socket_timeout_seconds",
            DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS,
        ),
        "health_check_interval": getattr(
            settings,
            "redis_health_check_interval_seconds",
            DEFAULT_REDIS_HEALTH_CHECK_INTERVAL_SECONDS,
        ),
    }


async def get_redis() -> aioredis.Redis:
    """Return a shared async Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
            **redis_connection_kwargs(settings),
        )
    return _redis_pool


async def get_chat_budget_redis() -> aioredis.Redis:
    """Return the dedicated, no-eviction monetary-ledger Redis pool."""
    global _chat_budget_redis_pool  # noqa: PLW0603
    if _chat_budget_redis_pool is None:
        settings = get_settings()
        if not settings.chat_budget_redis_url:
            raise RuntimeError("CHAT_BUDGET_REDIS_URL is not configured")
        _chat_budget_redis_pool = aioredis.from_url(
            settings.chat_budget_redis_url,
            decode_responses=True,
            max_connections=20,
            **redis_connection_kwargs(settings),
        )
    return _chat_budget_redis_pool


async def close_redis_pool() -> None:
    """Close the shared cache and monetary-ledger pools."""
    global _chat_budget_redis_pool, _redis_pool  # noqa: PLW0603
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
    if _chat_budget_redis_pool is not None:
        await _chat_budget_redis_pool.aclose()
        _chat_budget_redis_pool = None


async def get_cached_report(
    org_id: str,
    analysis_id: str,
    *,
    version: str | None = None,
) -> dict[Any, Any] | None:
    """Fetch a cached report from Redis.

    Returns None on a true cache miss (key not found).
    Raises on Redis/deserialization errors so callers see failures loudly.
    """
    key = _report_cache_key(org_id, analysis_id, version=version)
    try:
        r = await get_redis()
        data = await r.get(key)
    except aioredis.RedisError as exc:
        logger.error(
            "cache_read_error",
            key=key,
            error=str(exc),
            exc_info=True,
        )
        # Re-raise: the caller MUST know cache is broken, not silently fall through to DB
        raise
    if data is None:
        logger.debug("cache_miss", key=key)
        return None

    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "cache_deserialization_error",
            key=key,
            error=str(exc),
            data_preview=str(data)[:200],
            exc_info=True,
        )
        raise

    logger.debug("cache_hit", key=key)
    if not isinstance(parsed, dict):
        raise TypeError("cached report payload must be a JSON object")
    return parsed


async def set_cached_report(
    org_id: str,
    analysis_id: str,
    report_data: dict[Any, Any],
    ttl: int | None = None,
    *,
    version: str | None = None,
) -> None:
    """Cache a report in Redis with a TTL (default from settings)."""
    ttl = ttl if ttl is not None else get_settings().report_cache_ttl
    key = _report_cache_key(org_id, analysis_id, version=version)
    try:
        r = await get_redis()
        await r.set(
            key,
            json.dumps(report_data, default=str),
            ex=ttl,
        )
        logger.debug("cache_set", key=key, ttl=ttl)
    except aioredis.RedisError as exc:
        logger.error(
            "cache_write_error",
            key=key,
            error=str(exc),
            exc_info=True,
        )
        raise
