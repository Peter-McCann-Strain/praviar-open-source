"""Plan-based rate limiting with Redis sliding window.

Enforces per-org rate limits based on the organization's subscription plan.
Uses a Redis-backed sliding window counter for distributed environments.

Usage:
    # As a FastAPI dependency on individual routes:
    @router.post("/analyses", dependencies=[Depends(rate_limit_analysis)])
    # As a router-level dependency on authenticated routers:
    app.include_router(router, dependencies=[Depends(rate_limit_api)])

Rate limit headers are injected into every response by RateLimitHeaderMiddleware.
The dependency stores limit/remaining/reset into request.state so the middleware
can read them without coupling the response model to header logic.
"""

import time
import uuid
from enum import StrEnum
from typing import cast

import structlog
from fastapi import Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from api.config import get_settings
from api.db.models import Organization
from api.deps import AuthenticatedPrincipal, CurrentPrincipal, DBSession
from api.errors import APIError

logger = structlog.get_logger()


# ── Rate-limit header middleware ─────────────────────────────────────────────


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Inject X-RateLimit-* headers into every authenticated response.

    The rate_limit_analysis dependency stores limit/remaining/reset into
    request.state after a successful check.  This middleware reads those
    values and writes them as standard response headers so clients can
    implement back-off logic without parsing error bodies.

    Header semantics:
      X-RateLimit-Limit     -- maximum requests allowed in the window
      X-RateLimit-Remaining -- requests remaining in the current window
      X-RateLimit-Reset     -- Unix timestamp (UTC) when the window resets
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = cast(Response, await call_next(request))
        rl = getattr(request.state, "rate_limit", None)
        if rl is not None:
            limit = rl.get("limit")
            remaining = rl.get("remaining")
            reset_at = rl.get("reset_at")
            if limit is not None and limit >= 0:
                response.headers["X-RateLimit-Limit"] = str(limit)
            if remaining is not None and remaining >= 0:
                response.headers["X-RateLimit-Remaining"] = str(remaining)
            if reset_at is not None and reset_at > 0:
                response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


# ── Plan limits ──────────────────────────────────────────────────────────────


class PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class RateLimitBackendUnavailableError(RuntimeError):
    """Raised when the rate-limit backend is unavailable in fail-closed mode."""


def _get_plan_limits() -> dict[str, tuple[int, int]]:
    """Load (analyses_per_hour, api_calls_per_minute) from config."""
    s = get_settings()
    return {
        PlanTier.FREE: (s.plan_free_analyses_per_hour, s.plan_free_api_calls_per_minute),
        PlanTier.STARTER: (s.plan_starter_analyses_per_hour, s.plan_starter_api_calls_per_minute),
        PlanTier.PRO: (s.plan_pro_analyses_per_hour, s.plan_pro_api_calls_per_minute),
        PlanTier.ENTERPRISE: (0, 0),  # 0 means unlimited
    }


# Window durations in seconds
ANALYSIS_WINDOW = 3600  # 1 hour
API_CALL_WINDOW = 60  # 1 minute


# ── Redis helpers ────────────────────────────────────────────────────────────


async def _get_redis():
    """Return the shared Redis connection pool (delegated to api.cache)."""
    from api.cache import get_redis as _shared_get_redis

    return await _shared_get_redis()


_SLIDING_WINDOW_SCRIPT = """
local key         = KEYS[1]
local now         = tonumber(ARGV[1])
local window_start= tonumber(ARGV[2])
local limit       = tonumber(ARGV[3])
local ttl         = tonumber(ARGV[4])
local unique_id   = ARGV[5]
redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local count = redis.call('ZCARD', key)
if count >= limit then
    -- Sliding-window reset: capacity frees when the OLDEST in-window entry
    -- ages out (oldest_score + ttl), not a full window from now. Reporting
    -- now+ttl here overstates Retry-After by up to a whole window (e.g. an
    -- hour for the analysis limiter) when room may open in seconds. Fall back
    -- to now+ttl only if the set is unexpectedly empty.
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_at = now + ttl
    if oldest[2] then
        reset_at = tonumber(oldest[2]) + ttl
    end
    -- Keep the key's TTL fresh on the reject path too so a continuously
    -- saturated key cannot retain a stale expiry set by the last allowed add.
    redis.call('EXPIRE', key, ttl + 10)
    return {0, 0, math.floor(reset_at)}
end
redis.call('ZADD', key, now, unique_id)
redis.call('EXPIRE', key, ttl + 10)
return {1, limit - count - 1, math.floor(now + ttl)}
"""


async def _sliding_window_check(
    redis_client,
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int, int]:
    """Check and increment a sliding-window counter in Redis.

    Uses a Lua script so the read-check-write sequence is atomic on the Redis
    server — no TOCTOU between concurrent requests.

    Returns:
        (allowed, remaining, reset_timestamp)
    """
    if limit == 0:
        return True, -1, 0

    now = time.time()
    window_start = now - window_seconds
    unique_id = f"{now:.6f}-{uuid.uuid4().hex}"

    result = await redis_client.eval(
        _SLIDING_WINDOW_SCRIPT,
        1,
        key,
        now,
        window_start,
        limit,
        window_seconds,
        unique_id,
    )

    allowed = bool(result[0])
    remaining = int(result[1])
    reset_at = int(result[2])
    return allowed, remaining, reset_at


# ── Rate limiter class ───────────────────────────────────────────────────────


class PlanBasedRateLimiter:
    """Checks rate limits based on the organisation's plan tier.

    Tracks analysis submissions per hour.
    """

    @staticmethod
    def _get_plan_limits(plan: str) -> tuple[int, int]:
        """Return (analyses_per_hour, api_calls_per_minute) for a plan."""
        limits = _get_plan_limits()
        return limits.get(plan, limits[PlanTier.FREE])

    @staticmethod
    async def check_api_rate(
        org_id: str,
        plan: str,
    ) -> tuple[bool, int, int]:
        """Check the per-minute API call limit.

        Returns:
            (allowed, remaining, reset_timestamp)
        """
        _, api_limit = PlanBasedRateLimiter._get_plan_limits(plan)
        if api_limit == 0:
            return True, -1, 0

        try:
            redis_client = await _get_redis()
            key = f"ratelimit:api:{org_id}"
            return await _sliding_window_check(redis_client, key, api_limit, API_CALL_WINDOW)
        except Exception as exc:
            logger.warning("rate_limit_redis_error", org_id=org_id, exc_info=True)
            if get_settings().app_env == "prod":
                raise RateLimitBackendUnavailableError(
                    "Redis rate-limit backend unavailable"
                ) from exc
            return True, -1, 0

    @staticmethod
    async def check_analysis_rate(
        org_id: str,
        plan: str,
    ) -> tuple[bool, int, int]:
        """Check the per-hour analysis submission limit.

        Returns:
            (allowed, remaining, reset_timestamp)
        """
        analysis_limit, _ = PlanBasedRateLimiter._get_plan_limits(plan)
        if analysis_limit == 0:
            return True, -1, 0

        try:
            redis_client = await _get_redis()
            key = f"ratelimit:analysis:{org_id}"
            return await _sliding_window_check(redis_client, key, analysis_limit, ANALYSIS_WINDOW)
        except Exception as exc:
            logger.warning("rate_limit_redis_error", org_id=org_id, exc_info=True)
            if get_settings().app_env == "prod":
                raise RateLimitBackendUnavailableError(
                    "Redis rate-limit backend unavailable"
                ) from exc
            return True, -1, 0


# ── Per-route dependencies ───────────────────────────────────────────────────


async def _load_org_plan(user: AuthenticatedPrincipal, db: DBSession) -> str:
    result = await db.execute(select(Organization.plan).where(Organization.id == user.org_id))
    plan_value = result.scalar_one_or_none()
    if plan_value is None:
        raise APIError(
            403,
            "Forbidden",
            "Authenticated user is not associated with a valid organization.",
        )
    return str(getattr(plan_value, "value", plan_value))


def _store_rate_limit_state(
    request: Request,
    *,
    limit: int,
    remaining: int,
    reset_at: int,
) -> None:
    request.state.rate_limit = {
        "limit": -1 if limit == 0 else limit,
        "remaining": remaining,
        "reset_at": reset_at,
    }


async def rate_limit_api(user: CurrentPrincipal, db: DBSession, request: Request) -> None:
    """FastAPI dependency that checks the per-minute org API-call rate limit."""

    org_id = str(user.org_id)
    plan = await _load_org_plan(user, db)
    _, api_limit = PlanBasedRateLimiter._get_plan_limits(plan)
    try:
        allowed, remaining, reset_at = await PlanBasedRateLimiter.check_api_rate(org_id, plan)
    except RateLimitBackendUnavailableError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Rate limit backend is unavailable; refusing API request.",
        ) from exc

    if not allowed:
        retry_after = max(1, reset_at - int(time.time()))
        raise APIError(
            429,
            "Too Many Requests",
            f"API rate limit exceeded. Limit: {api_limit} requests/minute. "
            f"Retry after {retry_after} seconds.",
            retry_after_seconds=retry_after,
        )
    _store_rate_limit_state(
        request,
        limit=api_limit,
        remaining=remaining,
        reset_at=reset_at,
    )


async def rate_limit_analysis(user: CurrentPrincipal, db: DBSession, request: Request) -> None:
    """FastAPI dependency that checks the per-hour analysis submission limit.

    Apply to analysis creation endpoints:
        @router.post("/analyses", dependencies=[Depends(rate_limit_analysis)])
    """

    org_id = str(user.org_id)
    plan = await _load_org_plan(user, db)

    analysis_limit, _ = PlanBasedRateLimiter._get_plan_limits(plan)
    try:
        allowed, remaining, reset_at = await PlanBasedRateLimiter.check_analysis_rate(org_id, plan)
    except RateLimitBackendUnavailableError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Rate limit backend is unavailable; refusing analysis submission.",
        ) from exc

    if not allowed:
        retry_after = max(1, reset_at - int(time.time()))
        raise APIError(
            429,
            "Too Many Requests",
            f"Analysis rate limit exceeded. Limit: {analysis_limit} analyses/hour. "
            f"Retry after {retry_after} seconds.",
            retry_after_seconds=retry_after,
        )
    _store_rate_limit_state(
        request,
        limit=analysis_limit,
        remaining=remaining,
        reset_at=reset_at,
    )
