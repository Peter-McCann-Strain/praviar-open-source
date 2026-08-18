"""Hostile tests for RequestLoggingMiddleware request_id entropy and echo behaviour.

The app under test is a minimal FastAPI instance with only
RequestLoggingMiddleware attached.  No database, no Clerk auth, no startup
checks -- so these tests are fully self-contained and fast.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api import app_lifecycle
from api.app_lifecycle import (
    RequestLoggingMiddleware,
    _verify_production_database_privilege_boundary,
    _verify_production_epo_provenance,
    build_lifespan,
)
from api.db import claimed_use_privileged

# ---------------------------------------------------------------------------
# Minimal app fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Return an async client wired to a bare app with only the middleware."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    async def ping() -> JSONResponse:
        return JSONResponse({"ok": True})

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Hostile tests: request_id entropy
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^[0-9a-f]+$")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_role", "api_calls", "worker_calls"),
    [
        ("api", 1, 0),
        ("worker", 0, 1),
    ],
)
async def test_prod_startup_verifies_the_active_database_role(
    monkeypatch: pytest.MonkeyPatch,
    service_role: str,
    api_calls: int,
    worker_calls: int,
) -> None:
    api_verifier = AsyncMock()
    worker_verifier = AsyncMock()
    monkeypatch.setattr(
        claimed_use_privileged,
        "verify_claimed_use_privilege_boundary",
        api_verifier,
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "verify_claimed_use_worker_privilege_boundary",
        worker_verifier,
    )

    await _verify_production_database_privilege_boundary(
        app_env="prod",
        service_role=service_role,
    )

    assert api_verifier.await_count == api_calls
    assert worker_verifier.await_count == worker_calls


@pytest.mark.asyncio
async def test_non_prod_startup_does_not_open_privileged_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_verifier = AsyncMock()
    worker_verifier = AsyncMock()
    monkeypatch.setattr(
        claimed_use_privileged,
        "verify_claimed_use_privilege_boundary",
        api_verifier,
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "verify_claimed_use_worker_privilege_boundary",
        worker_verifier,
    )

    await _verify_production_database_privilege_boundary(
        app_env="test",
        service_role="worker",
    )

    api_verifier.assert_not_awaited()
    worker_verifier.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("app_env", "service_role", "expected_calls"),
    [
        ("prod", "worker", 1),
        ("prod", "api", 0),
        ("test", "worker", 0),
    ],
)
async def test_epo_provenance_startup_is_worker_only_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    service_role: str,
    expected_calls: int,
) -> None:
    from api import epo_provenance_runtime

    verifier = AsyncMock()
    monkeypatch.setattr(
        epo_provenance_runtime,
        "verify_epo_provenance_runtime",
        verifier,
    )

    await _verify_production_epo_provenance(
        app_env=app_env,
        service_role=service_role,
    )

    assert verifier.await_count == expected_calls


@pytest.mark.asyncio
async def test_request_id_is_32_hex_chars(client: httpx.AsyncClient) -> None:
    """Generated request_id must be exactly 32 lowercase hex characters.

    secrets.token_hex(16) produces 32 hex chars.  If the implementation
    switches to a shorter or differently-encoded token this assertion fires.
    """
    response = await client.get("/ping")
    request_id = response.headers.get("X-Request-ID", "")
    assert len(request_id) == 32, (
        f"Expected X-Request-ID to be 32 chars, got {len(request_id)!r}: {request_id!r}"
    )


@pytest.mark.asyncio
async def test_request_id_is_all_hex(client: httpx.AsyncClient) -> None:
    """Generated request_id must contain only lowercase hex digits [0-9a-f].

    A UUID or base64 token would fail this assertion, catching accidental
    format drift without relying on the length check alone.
    """
    response = await client.get("/ping")
    request_id = response.headers.get("X-Request-ID", "")
    assert _HEX_RE.match(request_id), f"X-Request-ID contains non-hex characters: {request_id!r}"


# ---------------------------------------------------------------------------
# Hostile tests: request_id header echo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_is_echoed_in_response_header(client: httpx.AsyncClient) -> None:
    """The generated request_id must appear in the X-Request-ID response header."""
    response = await client.get("/ping")
    assert "X-Request-ID" in response.headers, "X-Request-ID header missing from response"
    # Confirm the value is non-empty -- a blank echo would be a silent failure.
    assert response.headers["X-Request-ID"], "X-Request-ID response header is present but empty"


@pytest.mark.asyncio
async def test_client_supplied_request_id_is_respected(
    client: httpx.AsyncClient,
) -> None:
    """A caller-supplied X-Request-ID must be echoed verbatim in the response.

    This ensures the middleware honours client-generated correlation IDs
    (e.g. from an upstream API gateway) rather than replacing them.
    """
    custom_id = "custom-correlation-id-abc123"
    response = await client.get("/ping", headers={"X-Request-ID": custom_id})
    echoed = response.headers.get("X-Request-ID", "")
    assert echoed == custom_id, f"Expected X-Request-ID echo {custom_id!r}, got {echoed!r}"


# ---------------------------------------------------------------------------
# Hostile tests: uniqueness across requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_requests_get_different_request_ids(
    client: httpx.AsyncClient,
) -> None:
    """Each request without a caller-supplied ID must receive a distinct request_id.

    A collision here would indicate that the token is being cached or seeded
    with a fixed value -- both serious entropy failures.
    """
    resp_a = await client.get("/ping")
    resp_b = await client.get("/ping")
    id_a = resp_a.headers.get("X-Request-ID", "")
    id_b = resp_b.headers.get("X-Request-ID", "")
    assert id_a and id_b, "One or both responses missing X-Request-ID header"
    assert id_a != id_b, f"Two consecutive requests produced the same request_id: {id_a!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("service_role", ["api", "worker"])
async def test_lifespan_runs_fail_closed_startup_and_complete_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    service_role: str,
) -> None:
    """A healthy lifecycle verifies dependencies before yield and disposes every pool."""
    from api import cache, epo_provenance_runtime, metrics, observability
    from api.db import session

    settings = SimpleNamespace(
        app_env="test",
        service_role=service_role,
        debug=False,
        api_prefix="/api",
        cors_origins=["https://app.example"],
        database_url="postgresql+asyncpg://example/db",
        redis_url="redis://example/0",
        db_pool_size=5,
        db_max_overflow=2,
        release_version="test-release",
        deployment_env="test",
        sentry_dsn="",
        gcs_bucket_name="",
        clerk_secret_key="",
    )
    startup_checks = AsyncMock()
    verify_database = AsyncMock()
    verify_epo = AsyncMock()
    shutdown_otel = AsyncMock()
    close_redis = AsyncMock()
    dispose_claimed_use = AsyncMock()
    dispose_epo = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())
    metric = MagicMock()

    monkeypatch.setattr(app_lifecycle, "configure_structlog", MagicMock())
    monkeypatch.setattr(app_lifecycle, "get_settings", lambda: settings)
    monkeypatch.setattr(app_lifecycle, "run_startup_checks", startup_checks)
    monkeypatch.setattr(
        app_lifecycle,
        "_verify_production_database_privilege_boundary",
        verify_database,
    )
    monkeypatch.setattr(app_lifecycle, "_verify_production_epo_provenance", verify_epo)
    monkeypatch.setattr(
        cache, "redis_connection_kwargs", lambda _settings: {"decode_responses": True}
    )
    monkeypatch.setattr(cache, "close_redis_pool", close_redis)
    monkeypatch.setattr(observability, "shutdown_otel", shutdown_otel)
    monkeypatch.setattr(session, "async_session_factory", object())
    monkeypatch.setattr(
        metrics, "build_info", SimpleNamespace(labels=MagicMock(return_value=metric))
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "dispose_claimed_use_privileged_engines",
        dispose_claimed_use,
    )
    monkeypatch.setattr(epo_provenance_runtime, "dispose_epo_provenance_runtime", dispose_epo)

    async with build_lifespan(engine=engine)(FastAPI()):
        startup_checks.assert_awaited_once()
        verify_database.assert_awaited_once_with(app_env="test", service_role=service_role)
        verify_epo.assert_awaited_once_with(app_env="test", service_role=service_role)
        metric.set.assert_called_once_with(1)

    shutdown_otel.assert_awaited_once()
    close_redis.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    dispose_claimed_use.assert_awaited_once()
    assert dispose_epo.await_count == (1 if service_role == "worker" else 0)


@pytest.mark.asyncio
async def test_lifespan_shutdown_continues_when_optional_flushes_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry and Redis teardown failures must not leak the database engine."""
    from api import cache, metrics, observability
    from api.db import session

    settings = SimpleNamespace(
        app_env="test",
        service_role="api",
        debug=False,
        api_prefix="/api",
        cors_origins=[],
        database_url="",
        redis_url="",
        db_pool_size=1,
        db_max_overflow=0,
        release_version="test-release",
        deployment_env="test",
        sentry_dsn="",
        gcs_bucket_name="",
        clerk_secret_key="",
    )
    engine = SimpleNamespace(dispose=AsyncMock())
    dispose_claimed_use = AsyncMock()

    monkeypatch.setattr(app_lifecycle, "configure_structlog", MagicMock())
    monkeypatch.setattr(app_lifecycle, "get_settings", lambda: settings)
    monkeypatch.setattr(app_lifecycle, "run_startup_checks", AsyncMock())
    monkeypatch.setattr(
        app_lifecycle,
        "_verify_production_database_privilege_boundary",
        AsyncMock(),
    )
    monkeypatch.setattr(app_lifecycle, "_verify_production_epo_provenance", AsyncMock())
    monkeypatch.setattr(cache, "redis_connection_kwargs", lambda _settings: {})
    monkeypatch.setattr(cache, "close_redis_pool", AsyncMock(side_effect=RuntimeError("redis")))
    monkeypatch.setattr(observability, "shutdown_otel", AsyncMock(side_effect=RuntimeError("otel")))
    monkeypatch.setattr(session, "async_session_factory", object())
    monkeypatch.setattr(
        metrics,
        "build_info",
        SimpleNamespace(labels=MagicMock(return_value=MagicMock())),
    )
    monkeypatch.setattr(
        claimed_use_privileged,
        "dispose_claimed_use_privileged_engines",
        dispose_claimed_use,
    )

    async with build_lifespan(engine=engine)(FastAPI()):
        pass

    engine.dispose.assert_awaited_once()
    dispose_claimed_use.assert_awaited_once()
