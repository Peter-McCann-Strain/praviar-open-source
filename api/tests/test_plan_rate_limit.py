"""Plan-based rate-limit dependency regressions."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from api.db.models import UserRole
from api.errors import APIError
from api.middleware import rate_limit


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, plan="free"):
        self.plan = plan

    async def execute(self, _query):
        return _ScalarResult(self.plan)


@pytest.fixture(autouse=True)
def _rate_limit_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="test",
            plan_free_analyses_per_hour=1,
            plan_free_api_calls_per_minute=10,
            plan_starter_analyses_per_hour=10,
            plan_starter_api_calls_per_minute=60,
            plan_pro_analyses_per_hour=100,
            plan_pro_api_calls_per_minute=600,
        ),
    )


@pytest.mark.asyncio
async def test_rate_limit_api_uses_authenticated_org_plan(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, str] = {}

    async def fake_check(org_id: str, plan: str):
        seen["org_id"] = org_id
        seen["plan"] = plan
        return True, 42, 123

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_api_rate", fake_check)
    org_id = uuid.uuid4()

    await rate_limit.rate_limit_api(
        user=SimpleNamespace(org_id=org_id),  # type: ignore[arg-type]
        db=_FakeDB(plan="pro"),  # type: ignore[arg-type]
        request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
    )

    assert seen == {"org_id": str(org_id), "plan": "pro"}


@pytest.mark.asyncio
async def test_rate_limit_api_sets_response_header_state(monkeypatch: pytest.MonkeyPatch):
    async def fake_check(_org_id: str, _plan: str):
        return True, 42, 123

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_api_rate", fake_check)
    request = SimpleNamespace(state=SimpleNamespace())

    await rate_limit.rate_limit_api(
        user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
        db=_FakeDB(plan="pro"),  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
    )

    assert request.state.rate_limit == {"limit": 600, "remaining": 42, "reset_at": 123}


@pytest.mark.asyncio
async def test_rate_limit_api_fails_when_org_missing():
    with pytest.raises(APIError) as exc_info:
        await rate_limit.rate_limit_api(
            user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
            db=_FakeDB(plan=None),  # type: ignore[arg-type]
            request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_rate_limit_api_fails_closed_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_check(_org_id: str, _plan: str):
        raise rate_limit.RateLimitBackendUnavailableError("redis down")

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_api_rate", fake_check)

    with pytest.raises(APIError) as exc_info:
        await rate_limit.rate_limit_api(
            user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
            db=_FakeDB(plan="free"),  # type: ignore[arg-type]
            request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 503


@pytest.mark.asyncio
async def test_rate_limit_api_rejects_over_limit(monkeypatch: pytest.MonkeyPatch):
    async def fake_check(_org_id: str, _plan: str):
        return False, 0, int(rate_limit.time.time()) + 30

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_api_rate", fake_check)

    with pytest.raises(APIError) as exc_info:
        await rate_limit.rate_limit_api(
            user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
            db=_FakeDB(plan="free"),  # type: ignore[arg-type]
            request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 429
    assert "requests/minute" in exc_info.value.detail
    assert exc_info.value.retry_after_seconds == 30


@pytest.mark.asyncio
async def test_rate_limit_analysis_uses_authenticated_org_plan(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, str] = {}

    async def fake_check(org_id: str, plan: str):
        seen["org_id"] = org_id
        seen["plan"] = plan
        return True, 4, 123

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_analysis_rate", fake_check)
    org_id = uuid.uuid4()

    await rate_limit.rate_limit_analysis(
        user=SimpleNamespace(org_id=org_id),  # type: ignore[arg-type]
        db=_FakeDB(plan="starter"),  # type: ignore[arg-type]
        request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
    )

    assert seen == {"org_id": str(org_id), "plan": "starter"}


@pytest.mark.asyncio
async def test_rate_limit_analysis_sets_response_header_state(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_check(_org_id: str, _plan: str):
        return True, 4, 123

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_analysis_rate", fake_check)
    request = SimpleNamespace(state=SimpleNamespace())

    await rate_limit.rate_limit_analysis(
        user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
        db=_FakeDB(plan="starter"),  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
    )

    assert request.state.rate_limit == {"limit": 10, "remaining": 4, "reset_at": 123}


@pytest.mark.asyncio
async def test_rate_limit_analysis_fails_when_org_missing():
    with pytest.raises(APIError) as exc_info:
        await rate_limit.rate_limit_analysis(
            user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
            db=_FakeDB(plan=None),  # type: ignore[arg-type]
            request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_rate_limit_analysis_fails_closed_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_check(_org_id: str, _plan: str):
        raise rate_limit.RateLimitBackendUnavailableError("redis down")

    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_analysis_rate", fake_check)

    with pytest.raises(APIError) as exc_info:
        await rate_limit.rate_limit_analysis(
            user=SimpleNamespace(org_id=uuid.uuid4()),  # type: ignore[arg-type]
            db=_FakeDB(plan="free"),  # type: ignore[arg-type]
            request=SimpleNamespace(state=SimpleNamespace()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 503


class _FailingPipeline:
    async def execute(self):
        raise ConnectionError("redis is down")


class _FailingRedis:
    def pipeline(self):
        return _FailingPipeline()

    async def aclose(self):
        return None


def _redis_with_pipeline() -> MagicMock:
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[None, 0, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=pipe)
    mock_redis.aclose = AsyncMock()
    mock_redis.zrem = AsyncMock()
    return mock_redis


@pytest.mark.asyncio
async def test_check_analysis_rate_raises_when_redis_pipeline_fails_in_prod(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="prod",
            plan_free_analyses_per_hour=1,
            plan_free_api_calls_per_minute=10,
            plan_starter_analyses_per_hour=10,
            plan_starter_api_calls_per_minute=60,
            plan_pro_analyses_per_hour=100,
            plan_pro_api_calls_per_minute=600,
        ),
    )

    async def failing_redis():
        return _FailingRedis()

    monkeypatch.setattr(rate_limit, "_get_redis", failing_redis)

    with pytest.raises(rate_limit.RateLimitBackendUnavailableError):
        await rate_limit.PlanBasedRateLimiter.check_analysis_rate(
            org_id=str(uuid.uuid4()),
            plan="free",
        )


@pytest.mark.asyncio
async def test_check_api_rate_raises_when_redis_pipeline_fails_in_prod(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="prod",
            plan_free_analyses_per_hour=1,
            plan_free_api_calls_per_minute=10,
            plan_starter_analyses_per_hour=10,
            plan_starter_api_calls_per_minute=60,
            plan_pro_analyses_per_hour=100,
            plan_pro_api_calls_per_minute=600,
        ),
    )

    async def failing_redis():
        return _FailingRedis()

    monkeypatch.setattr(rate_limit, "_get_redis", failing_redis)

    with pytest.raises(rate_limit.RateLimitBackendUnavailableError):
        await rate_limit.PlanBasedRateLimiter.check_api_rate(
            org_id=str(uuid.uuid4()),
            plan="free",
        )


# ---------------------------------------------------------------------------
# Integration: Retry-After header is present on a real 429 HTTP response
# ---------------------------------------------------------------------------


@contextmanager
def _disabled_rate_limiter():
    """Disable slowapi for the duration of the block."""
    from api.ratelimit import limiter

    prev = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = prev


def _build_rate_limited_app(user: MagicMock, db: AsyncMock):
    """Build the FastAPI app with auth/DB overridden but rate_limit_analysis live.

    Unlike the shared ``_build_app`` helper in conftest, this intentionally
    does NOT override ``rate_limit_analysis`` so the dependency runs for real.
    """
    from api.main import create_app

    app = create_app()

    from api.db.session import get_db
    from api.deps import get_current_user

    async def _override_user():
        return user

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    return app


@pytest.mark.asyncio
async def test_retry_after_header_present_on_429_http_response():
    """End-to-end: a rate-limited POST /analyses response carries Retry-After.

    Patches ``PlanBasedRateLimiter.check_analysis_rate`` to return *not
    allowed* so the dependency raises ``APIError(429, ...,
    retry_after_seconds=N)``.  Asserts that the HTTP response has status 429
    and a numeric ``Retry-After`` header -- verifying the full plumbing from
    the dependency through ``api_error_handler`` to the wire.
    """
    future_reset = int(time.time()) + 3600

    async def _rate_exceeded(_org_id: str, _plan: str) -> tuple[bool, int, int]:
        return False, 0, future_reset

    # DB returns plan="free" for the org lookup inside rate_limit_analysis.
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = "free"
    db.execute.return_value = result_mock

    user = MagicMock()
    user.id = uuid.uuid4()
    user.org_id = uuid.uuid4()
    user.role = UserRole.SCIENTIST
    user.clerk_user_id = "clerk_test_ratelimit"
    user.email = "ratelimit@praviar.io"
    user.full_name = "Rate Limit Test"
    user.preferences = {}

    mock_engine = AsyncMock()
    mock_startup_session = AsyncMock()
    mock_startup_session.__aenter__ = AsyncMock(return_value=mock_startup_session)
    mock_startup_session.__aexit__ = AsyncMock(return_value=False)
    mock_redis = _redis_with_pipeline()

    async def _no_cache(*_args, **_kwargs):
        return None

    app = _build_rate_limited_app(user, db)

    with (
        _disabled_rate_limiter(),
        patch("api.cache._redis_pool", None),
        patch("api.main.engine", mock_engine),
        patch("api.db.session.async_session_factory", return_value=mock_startup_session),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("api.cache.get_cached_report", side_effect=_no_cache),
        patch("api.cache.set_cached_report", side_effect=_no_cache),
        patch.object(
            rate_limit.PlanBasedRateLimiter,
            "check_analysis_rate",
            side_effect=_rate_exceeded,
        ),
    ):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/analyses",
                json={"compound_input": "aspirin"},
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 429, (
        f"Expected 429 but got {response.status_code}: {response.text}"
    )
    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None, "Retry-After header missing from 429 response"
    assert retry_after.isdigit(), f"Retry-After must be a numeric string; got {retry_after!r}"
    assert int(retry_after) >= 1, f"Retry-After must be at least 1 second; got {retry_after}"


@pytest.mark.asyncio
async def test_scoped_api_key_crosses_real_router_rate_limit_and_route_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the assembled dependency tree, not an isolated scope checker."""
    import api.deps as deps
    import api.routes.monitors as monitor_routes
    from api.db.session import get_db
    from api.main import create_app

    org_id = uuid.uuid4()
    api_key = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=uuid.uuid4(),
        scopes=["monitors:manage"],
    )
    authenticate = AsyncMock(return_value=api_key)
    monkeypatch.setattr(deps, "authenticate_api_key", authenticate)
    monkeypatch.setattr(deps, "_bind_authenticated_context", lambda *_args, **_kwargs: None)

    db = AsyncMock()
    plan_result = MagicMock()
    plan_result.scalar_one_or_none.return_value = "free"
    db.execute = AsyncMock(return_value=plan_result)

    async def _override_db():
        yield db

    check_api_rate = AsyncMock(return_value=(True, 9, int(time.time()) + 60))
    monkeypatch.setattr(rate_limit.PlanBasedRateLimiter, "check_api_rate", check_api_rate)
    list_monitors = AsyncMock(return_value=SimpleNamespace(items=[], total=0))
    monkeypatch.setattr(monitor_routes, "list_monitors_page", list_monitors)

    app = create_app()
    app.dependency_overrides[get_db] = _override_db

    with _disabled_rate_limiter():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/monitors",
                headers={"Authorization": "Bearer raw-scoped-api-key"},
            )

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0}
    authenticate.assert_awaited_once()
    assert authenticate.await_args is not None
    assert authenticate.await_args.args[0] == "raw-scoped-api-key"
    check_api_rate.assert_awaited_once_with(str(org_id), "free")
    list_monitors.assert_awaited_once()


# ---------------------------------------------------------------------------
# Redis pool singleton -- _get_redis() must create the pool only once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_pool_is_created_once_not_per_call(monkeypatch: pytest.MonkeyPatch):
    """Calling _get_redis() twice must invoke aioredis.from_url exactly once.

    The singleton now lives in api.cache.  We reset it there and patch
    from_url to count invocations.  Two sequential calls to rate_limit._get_redis()
    (which delegates to api.cache.get_redis) must result in a single from_url
    call -- the second call must return the cached pool object.
    """
    import redis.asyncio as aioredis

    import api.cache as cache_module

    fake_pool = AsyncMock()
    call_count = 0

    def _counting_from_url(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return fake_pool

    # Reset the module-level singleton in api.cache so we start from a clean slate.
    monkeypatch.setattr(cache_module, "_redis_pool", None)
    monkeypatch.setattr(aioredis, "from_url", _counting_from_url)
    monkeypatch.setattr(
        cache_module,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="test",
            redis_url="redis://localhost:6379/0",
        ),
    )

    first = await rate_limit._get_redis()
    second = await rate_limit._get_redis()

    assert call_count == 1, (
        f"aioredis.from_url must be called exactly once; was called {call_count} time(s)"
    )
    assert first is second, "Both calls must return the same pool object"


@pytest.mark.asyncio
async def test_close_redis_pool_calls_aclose_on_pool(monkeypatch: pytest.MonkeyPatch):
    """close_redis_pool() must call aclose() on the existing pool and clear the ref.

    The pool and close_redis_pool() now live in api.cache.  After calling
    cache.close_redis_pool():
      - pool.aclose() has been awaited exactly once
      - the module-level _redis_pool in api.cache is reset to None so the next
        get_redis() call will allocate a fresh connection pool
    """
    import api.cache as cache_module
    from api.cache import close_redis_pool

    fake_pool = AsyncMock()
    fake_pool.aclose = AsyncMock()

    monkeypatch.setattr(cache_module, "_redis_pool", fake_pool)
    monkeypatch.setattr(cache_module, "_chat_budget_redis_pool", None)

    await close_redis_pool()

    fake_pool.aclose.assert_awaited_once()
    assert cache_module._redis_pool is None, (
        "_redis_pool must be reset to None after close_redis_pool() so the next "
        "call to get_redis() creates a fresh pool"
    )


@pytest.mark.asyncio
async def test_close_redis_pool_closes_dedicated_chat_budget_pool(
    monkeypatch: pytest.MonkeyPatch,
):
    import api.cache as cache_module
    from api.cache import close_redis_pool

    budget_pool = AsyncMock()
    budget_pool.aclose = AsyncMock()
    monkeypatch.setattr(cache_module, "_redis_pool", None)
    monkeypatch.setattr(cache_module, "_chat_budget_redis_pool", budget_pool)

    await close_redis_pool()

    budget_pool.aclose.assert_awaited_once()
    assert cache_module._chat_budget_redis_pool is None
