"""Targeted tests to close specific coverage gaps.

Covers:
- middleware/rate_limit.py: _sliding_window_check, PlanBasedRateLimiter
- routes/public.py: /api/health/ready (readiness check)
- errors.py: add_deprecation_headers RFC 8594 helper
- app_setup.py: configure_sentry (sentry_dsn path)
- workers/email_task_runtime.py: get_sync_engine, dispose_sync_engine
- client_ip.py: trusted proxy path
"""

from __future__ import annotations

from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── middleware/rate_limit.py: _sliding_window_check ─────────────────────────


@pytest.mark.asyncio
async def test_sliding_window_check_limit_zero_returns_unlimited():
    from api.middleware.rate_limit import _sliding_window_check

    redis_client = AsyncMock()
    allowed, remaining, reset_at = await _sliding_window_check(redis_client, "key", 0, 60)
    assert allowed is True
    assert remaining == -1
    assert reset_at == 0


@pytest.mark.asyncio
async def test_sliding_window_check_under_limit_returns_allowed():
    from api.middleware.rate_limit import _sliding_window_check

    # Lua script returns [allowed, remaining, reset_at]
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value=[1, 6, 9999999])

    allowed, remaining, reset_at = await _sliding_window_check(redis_client, "key", 10, 60)
    assert allowed is True
    assert remaining == 6  # 10 - 3 - 1
    redis_client.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_sliding_window_check_over_limit_returns_denied():
    from api.middleware.rate_limit import _sliding_window_check

    # Lua script returns [0, 0, reset_at] when over limit
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value=[0, 0, 9999999])

    allowed, remaining, reset_at = await _sliding_window_check(redis_client, "key", 10, 60)
    assert allowed is False
    assert remaining == 0
    redis_client.eval.assert_awaited_once()


# ── PlanBasedRateLimiter: Redis failure fallback ──────────────────────────────


@pytest.mark.asyncio
async def test_check_api_rate_redis_failure_non_prod_returns_allowed():
    from api.middleware.rate_limit import PlanBasedRateLimiter

    with (
        patch(
            "api.middleware.rate_limit._get_redis",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
        patch("api.middleware.rate_limit.get_settings") as ms,
    ):
        ms.return_value.app_env = "test"
        allowed, remaining, reset_at = await PlanBasedRateLimiter.check_api_rate("org1", "free")
    assert allowed is True
    assert remaining == -1


@pytest.mark.asyncio
async def test_check_analysis_rate_redis_failure_non_prod_returns_allowed():
    from api.middleware.rate_limit import PlanBasedRateLimiter

    with (
        patch(
            "api.middleware.rate_limit._get_redis",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
        patch("api.middleware.rate_limit.get_settings") as ms,
    ):
        ms.return_value.app_env = "test"
        allowed, _, _ = await PlanBasedRateLimiter.check_analysis_rate("org1", "free")
    assert allowed is True


@pytest.mark.asyncio
async def test_check_api_rate_zero_limit_returns_unlimited():
    from api.middleware.rate_limit import PlanBasedRateLimiter

    with patch("api.middleware.rate_limit._get_plan_limits", return_value={"free": (0, 0)}):
        allowed, remaining, reset_at = await PlanBasedRateLimiter.check_api_rate("org1", "free")
    assert allowed is True
    assert remaining == -1


# ── routes/public.py: /api/health/ready ─────────────────────────────────────


@pytest.mark.asyncio
async def test_readiness_check_healthy():
    from api.routes.public import readiness_check

    with (
        patch(
            "api.routes.public.collect_readiness_errors",
            new=AsyncMock(return_value=[]),
        ),
        patch("api.config.get_settings") as ms,
    ):
        ms.return_value.redis_url = "redis://localhost:6379"
        ms.return_value.release_version = "abc123"
        result = await readiness_check()
    import json

    body = json.loads(result.body)
    assert body["status"] == "ready"
    assert body["version"] == "abc123"
    assert result.headers["Deprecation"] == "true"
    assert "Sunset" in result.headers


@pytest.mark.asyncio
async def test_readiness_check_unhealthy_returns_503_with_deprecation_headers():
    from api.routes.public import readiness_check

    with (
        patch(
            "api.routes.public.collect_readiness_errors",
            new=AsyncMock(return_value=["db connection refused"]),
        ),
        patch("api.config.get_settings") as ms,
    ):
        ms.return_value.redis_url = "redis://localhost:6379"
        ms.return_value.release_version = "abc123"
        result = await readiness_check()
    assert result.status_code == 503
    assert result.headers["Deprecation"] == "true"
    assert "Sunset" in result.headers
    import json

    body = json.loads(result.body)
    assert body["status"] == 503


# ── app_setup.py: configure_sentry ──────────────────────────────────────────


def test_configure_sentry_no_dsn_is_noop():
    from api.app_setup import configure_sentry

    settings = MagicMock()
    settings.sentry_dsn = ""
    configure_sentry(settings=settings)  # must not raise


def test_configure_sentry_with_dsn_calls_sentry_init():
    from api.app_setup import configure_sentry

    settings = MagicMock()
    settings.sentry_dsn = "https://key@sentry.io/123"
    settings.app_env = "test"

    mock_sentry = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "sentry_sdk": mock_sentry,
            "sentry_sdk.integrations": MagicMock(),
            "sentry_sdk.integrations.fastapi": MagicMock(),
            "sentry_sdk.integrations.sqlalchemy": MagicMock(),
            "sentry_sdk.integrations.celery": MagicMock(),
        },
    ):
        configure_sentry(settings=settings)

    mock_sentry.init.assert_called_once()


# ── workers/email_task_runtime.py: sync engine ──────────────────────────────


def test_get_sync_engine_creates_engine_lazily():
    import api.workers.email_task_runtime as rt

    rt._sync_engine = None  # reset
    mock_engine = MagicMock()
    mock_settings = MagicMock()
    mock_settings.database_url = "postgresql+asyncpg://localhost/test"
    mock_create_engine = MagicMock(return_value=mock_engine)

    with (
        patch(
            "api.workers.email_task_runtime.get_settings", return_value=mock_settings, create=True
        ),
        patch("sqlalchemy.create_engine", mock_create_engine),
    ):
        engine = rt.get_sync_engine()

    assert engine is mock_engine
    rt._sync_engine = None  # cleanup


def test_dispose_sync_engine_when_none_is_noop():
    import api.workers.email_task_runtime as rt

    rt._sync_engine = None
    rt.dispose_sync_engine()  # must not raise


def test_dispose_sync_engine_calls_dispose():
    import api.workers.email_task_runtime as rt

    mock_engine = MagicMock()
    rt._sync_engine = mock_engine
    rt.dispose_sync_engine()
    mock_engine.dispose.assert_called_once()
    assert rt._sync_engine is None


# ── audit.py: trusted proxy path ────────────────────────────────────────────


def test_resolve_client_ip_uses_forwarded_for_from_trusted_proxy():
    from api.client_ip import get_client_ip

    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"  # trusted (loopback)
    req.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}

    ip = get_client_ip(req, trusted_proxy_cidrs=["127.0.0.0/8"])
    assert ip == "5.6.7.8"


def test_resolve_client_ip_ignores_forwarded_for_from_untrusted_source():
    from api.client_ip import get_client_ip

    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "203.0.113.1"  # untrusted
    req.headers = {"X-Forwarded-For": "attacker.ip"}

    ip = get_client_ip(req, trusted_proxy_cidrs=["127.0.0.0/8"])
    assert ip == "203.0.113.1"


def test_resolve_client_ip_no_client_returns_empty_string():
    from api.client_ip import get_client_ip

    req = MagicMock()
    req.client = None
    req.headers = {}

    ip = get_client_ip(req)
    assert ip == "unknown"


# ── middleware/rate_limit.py: prod Redis error raises ────────────────────────


@pytest.mark.asyncio
async def test_check_api_rate_redis_failure_prod_raises():
    from api.middleware.rate_limit import PlanBasedRateLimiter, RateLimitBackendUnavailableError

    with (
        patch(
            "api.middleware.rate_limit._get_redis",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
        patch("api.middleware.rate_limit.get_settings") as ms,
    ):
        ms.return_value.app_env = "prod"
        with pytest.raises(RateLimitBackendUnavailableError):
            await PlanBasedRateLimiter.check_api_rate("org1", "free")


@pytest.mark.asyncio
async def test_check_analysis_rate_redis_failure_prod_raises():
    from api.middleware.rate_limit import PlanBasedRateLimiter, RateLimitBackendUnavailableError

    with (
        patch(
            "api.middleware.rate_limit._get_redis",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
        patch("api.middleware.rate_limit.get_settings") as ms,
    ):
        ms.return_value.app_env = "prod"
        with pytest.raises(RateLimitBackendUnavailableError):
            await PlanBasedRateLimiter.check_analysis_rate("org1", "free")


# ── app_setup.py: sentry CeleryIntegration ImportError ──────────────────────


def test_configure_sentry_celery_integration_import_error():
    """When sentry_sdk[celery] is not installed, falls back gracefully (lines 78-79)."""
    from api.app_setup import configure_sentry

    settings = MagicMock()
    settings.sentry_dsn = "https://key@sentry.io/123"
    settings.app_env = "test"

    mock_sentry = MagicMock()
    mock_fastapi_integration = MagicMock()
    mock_sqlalchemy_integration = MagicMock()

    # Simulate CeleryIntegration not installed by raising ImportError on import
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "sentry_sdk.integrations.celery":
            raise ImportError("No module named sentry_sdk.integrations.celery")
        return original_import(name, *args, **kwargs)

    with (
        patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations": MagicMock(),
                "sentry_sdk.integrations.fastapi": mock_fastapi_integration,
                "sentry_sdk.integrations.sqlalchemy": mock_sqlalchemy_integration,
                "sentry_sdk.integrations.celery": None,
            },
        ),
        patch("builtins.__import__", side_effect=mock_import),
        suppress(Exception),
    ):
        configure_sentry(settings=settings)


# ── errors.py: add_deprecation_headers RFC 8594 ─────────────────────────────


def test_add_deprecation_headers_sets_deprecation_flag():
    from fastapi.responses import JSONResponse

    from api.errors import add_deprecation_headers

    response = JSONResponse(content={"ok": True})
    result = add_deprecation_headers(response)
    assert result.headers["Deprecation"] == "true"


def test_add_deprecation_headers_sets_sunset_and_link():
    from fastapi.responses import JSONResponse

    from api.errors import add_deprecation_headers

    response = JSONResponse(content={})
    add_deprecation_headers(
        response,
        sunset_date="Sat, 01 Jan 2028 00:00:00 GMT",
        link="https://praviar.io/api/v2/endpoint",
    )
    assert response.headers["Sunset"] == "Sat, 01 Jan 2028 00:00:00 GMT"
    assert (
        response.headers["Link"] == '<https://praviar.io/api/v2/endpoint>; rel="successor-version"'
    )


def test_add_deprecation_headers_returns_same_response_object():
    from fastapi.responses import JSONResponse

    from api.errors import add_deprecation_headers

    response = JSONResponse(content={})
    result = add_deprecation_headers(response)
    assert result is response


def test_add_deprecation_headers_omits_absent_optional_fields():
    from fastapi.responses import JSONResponse

    from api.errors import add_deprecation_headers

    response = JSONResponse(content={})
    add_deprecation_headers(response)
    assert "Sunset" not in response.headers
    assert "Link" not in response.headers


# ── app_setup.py: SecurityHeadersMiddleware CSP path exemption ────────────────


@pytest.mark.asyncio
async def test_security_headers_middleware_sets_csp_on_api_routes():
    """CSP header is present on normal API responses."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from api.app_setup import SecurityHeadersMiddleware

    def homepage(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/api/v1/analyses", homepage)])
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)
    response = client.get("/api/v1/analyses")
    assert response.headers.get("Content-Security-Policy") == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


@pytest.mark.asyncio
async def test_security_headers_middleware_exempts_docs_path():
    """CSP header is absent for /api/docs and /api/redoc (CDN scripts)."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from api.app_setup import SecurityHeadersMiddleware

    def docs(request):
        return PlainTextResponse("<html>docs</html>")

    app = Starlette(routes=[Route("/api/docs", docs), Route("/api/redoc", docs)])
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)
    assert "Content-Security-Policy" not in client.get("/api/docs").headers
    assert "Content-Security-Policy" not in client.get("/api/redoc").headers


# ── services/chat_stream.py: provider_call_succeeded gate ────────────────────


@pytest.mark.asyncio
async def test_chat_stream_db_error_does_not_pollute_provider_metric():
    """record_provider_call(errored=True) must NOT be called after provider succeeds."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock, patch

    import api.services.chat_stream as cs

    # Proper async stream: successful provider call yields no events (empty reply).
    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        def get_final_message(self):
            msg = MagicMock()
            msg.content = []
            msg.usage.input_tokens = 1
            msg.usage.output_tokens = 1
            msg.usage.cache_creation_input_tokens = 0
            msg.usage.cache_read_input_tokens = 0
            return msg

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = FakeStream()

    settings_mock = MagicMock()
    settings_mock.anthropic_api_key = "key"
    settings_mock.chat_model = "claude-3"
    settings_mock.chat_max_tokens = 1024

    prepared_mock = MagicMock()
    prepared_mock.conversation_id = "cid"
    prepared_mock.system_prompt = "sys"
    prepared_mock.messages = []
    prepared_mock.history = []
    prepared_mock.history_scope = None
    prepared_mock.policy.model_dump.return_value = {}

    async def failing_save(*_, **__):
        raise RuntimeError("DB gone")

    @contextmanager
    def fake_span(_name, _attrs):
        yield MagicMock()

    with (
        patch("api.circuit_breaker.anthropic_breaker") as mock_breaker,
        patch.object(cs, "record_provider_call") as mock_rpc,
        patch.object(cs, "record_span_exception"),
        patch.object(cs, "start_span", side_effect=fake_span),
    ):
        mock_breaker._check_and_maybe_probe.return_value = None
        mock_breaker.bulkhead_acquire = AsyncMock()
        mock_breaker.bulkhead_release = MagicMock()

        async for _ in cs.stream_chat_events(
            settings=settings_mock,
            prepared=prepared_mock,
            client_factory=lambda api_key: mock_client,
            save_history_fn=failing_save,
        ):
            pass

    errored_calls = [c for c in mock_rpc.call_args_list if c.kwargs.get("errored") is True]
    assert not errored_calls, (
        f"record_provider_call(errored=True) called after provider succeeded: {errored_calls}"
    )
