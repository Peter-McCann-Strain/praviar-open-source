"""Hostile tests for the Retry-After header on 429 responses.

Three scenarios:
1. Plan-based rate limit raises APIError(429, retry_after_seconds=N) -- header
   must be present and a positive integer string on the wire.
2. The header value must parse as int > 0 (numeric sanity check).
3. A generic APIError(429) raised *without* retry_after_seconds must NOT carry
   a Retry-After header -- the handler must not fabricate one.
"""

from __future__ import annotations

import time
import uuid
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from api.db.models import UserRole
from api.errors import APIError
from api.middleware import rate_limit


@contextmanager
def _disabled_rate_limiter():
    """Suppress slowapi for the duration of the block."""
    from api.ratelimit import limiter

    prev = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = prev


def _build_app_with_live_rate_limit(user: MagicMock, db: AsyncMock):
    """Build the full app with auth/DB overridden but rate_limit_analysis *live*.

    The shared conftest helper stubs out rate_limit_analysis.  This builder
    deliberately leaves it wired so we can exercise the full path from the
    FastAPI dependency through api_error_handler to the HTTP response headers.
    """
    from api.db.session import get_db
    from api.deps import get_current_user
    from api.main import create_app

    app = create_app()

    async def _user_override():
        return user

    async def _db_override():
        yield db

    app.dependency_overrides[get_current_user] = _user_override
    app.dependency_overrides[get_db] = _db_override
    return app


def _standard_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.org_id = uuid.uuid4()
    user.role = UserRole.SCIENTIST
    user.clerk_user_id = "clerk_retry_after_test"
    user.email = "retry@praviar.io"
    user.full_name = "Retry After Test"
    user.preferences = {}
    return user


def _db_returning_plan(plan: str) -> AsyncMock:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = plan
    db.execute.return_value = result_mock
    return db


def _redis_with_pipeline() -> MagicMock:
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[None, 0, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=pipe)
    mock_redis.ping = AsyncMock()
    mock_redis.aclose = AsyncMock()
    mock_redis.zrem = AsyncMock()
    return mock_redis


def _infra_patches(mock_redis: MagicMock):
    """Return the set of patches needed to suppress real I/O during app startup."""
    mock_engine = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def _no_cache(*_a, **_kw):
        return None

    return (
        patch("api.cache._redis_pool", None),
        patch("api.main.engine", mock_engine),
        patch("api.db.session.async_session_factory", return_value=mock_session),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("api.cache.get_cached_report", side_effect=_no_cache),
        patch("api.cache.set_cached_report", side_effect=_no_cache),
    )


# ---------------------------------------------------------------------------
# Test 1 + 2 -- plan-based 429 carries Retry-After; value is a positive int
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_based_429_sets_retry_after_header():
    """A rate-limited analysis submission must carry a Retry-After header.

    We make PlanBasedRateLimiter.check_analysis_rate return (False, 0, future)
    so the dependency raises APIError(429, ..., retry_after_seconds=N).
    The api_error_handler must forward that value as the Retry-After header.
    """
    future_reset = int(time.time()) + 3600

    async def _rate_exceeded(_org_id: str, _plan: str) -> tuple[bool, int, int]:
        return False, 0, future_reset

    user = _standard_user()
    db = _db_returning_plan("free")
    mock_redis = _redis_with_pipeline()

    app = _build_app_with_live_rate_limit(user, db)

    with ExitStack() as stack:
        stack.enter_context(_disabled_rate_limiter())
        for cm in _infra_patches(mock_redis):
            stack.enter_context(cm)
        stack.enter_context(
            patch.object(
                rate_limit.PlanBasedRateLimiter,
                "check_analysis_rate",
                side_effect=_rate_exceeded,
            )
        )
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/analyses",
                json={"compound_input": "aspirin"},
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 429, f"Expected 429, got {response.status_code}: {response.text}"
    assert "Retry-After" in response.headers, (
        "Retry-After header must be present on a plan-based 429 response"
    )


@pytest.mark.asyncio
async def test_retry_after_value_is_positive_integer():
    """The Retry-After value must be a string encoding a positive integer.

    RFC 7231 section 7.1.3 requires a delta-seconds value (non-negative integer).
    We enforce > 0 because the rate_limit dependency clamps to max(1, ...).
    """
    future_reset = int(time.time()) + 3600

    async def _rate_exceeded(_org_id: str, _plan: str) -> tuple[bool, int, int]:
        return False, 0, future_reset

    user = _standard_user()
    db = _db_returning_plan("free")
    mock_redis = _redis_with_pipeline()

    app = _build_app_with_live_rate_limit(user, db)

    with ExitStack() as stack:
        stack.enter_context(_disabled_rate_limiter())
        for cm in _infra_patches(mock_redis):
            stack.enter_context(cm)
        stack.enter_context(
            patch.object(
                rate_limit.PlanBasedRateLimiter,
                "check_analysis_rate",
                side_effect=_rate_exceeded,
            )
        )
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/analyses",
                json={"compound_input": "aspirin"},
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 429
    retry_after = response.headers.get("Retry-After", "")
    assert retry_after.isdigit(), f"Retry-After must be a numeric string; got {retry_after!r}"
    assert int(retry_after) > 0, (
        f"Retry-After must be > 0 (rate_limit clamps to max(1, ...)); got {retry_after}"
    )


# ---------------------------------------------------------------------------
# Test 3 -- a generic 429 raised without retry_after_seconds has no header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_429_without_retry_after_seconds_omits_header():
    """A 429 raised via APIError without retry_after_seconds must NOT carry Retry-After.

    The api_error_handler is gated on ``exc.retry_after_seconds is not None``.
    This test manufactures a 429 from an arbitrary route that uses APIError
    directly (no retry_after_seconds kwarg) and verifies the handler does not
    fabricate a header value.
    """
    # Build a minimal FastAPI app that always raises a bare 429.
    from fastapi import FastAPI

    from api.errors import api_error_handler

    mini_app = FastAPI()
    mini_app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]

    @mini_app.get("/probe")
    async def _probe():
        raise APIError(429, "Too Many Requests", "Slow down -- no retry hint available.")

    async with httpx.AsyncClient(
        transport=ASGITransport(app=mini_app), base_url="http://test"
    ) as client:
        response = await client.get("/probe")

    assert response.status_code == 429
    assert "Retry-After" not in response.headers, (
        "Retry-After header must be absent when retry_after_seconds is not set on APIError"
    )
