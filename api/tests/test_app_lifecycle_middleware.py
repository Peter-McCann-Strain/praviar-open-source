"""Targeted tests for RequestLoggingMiddleware and RateLimitHeaderMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.testclient import TestClient

from api.app_lifecycle import RequestLoggingMiddleware
from api.middleware.rate_limit import RateLimitHeaderMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    method: str = "GET",
    path: str = "/ping",
    request_id: str | None = None,
) -> MagicMock:
    """Build a minimal mock Request object."""
    request = MagicMock()
    request.method = method
    request.url = MagicMock()
    request.url.path = path
    request.state = MagicMock()

    headers: dict[str, str] = {}
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    request.headers = headers
    return request


def _make_response(status_code: int = 200) -> Response:
    """Return a real Starlette Response so headers can be set."""
    return Response(content=b"ok", status_code=status_code)


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------


class TestRequestLoggingMiddleware:
    """Unit tests for RequestLoggingMiddleware.dispatch."""

    async def test_normal_request_sets_x_request_id_header(self) -> None:
        """A successful request must have X-Request-ID on the response."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/ping")
        async def ping():
            return JSONResponse({"ok": True})

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_x_request_id_header_echoed_when_provided(self) -> None:
        """If X-Request-ID is provided, the same value is echoed on the response."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/echo")
        async def echo():
            return JSONResponse({"ok": True})

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/echo", headers={"X-Request-ID": "my-trace-id-42"})
        assert resp.headers["x-request-id"] == "my-trace-id-42"

    def test_generated_request_id_is_32_hex_chars(self) -> None:
        """Auto-generated request_id (secrets.token_hex(16)) is 32 lowercase hex chars."""
        import re

        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/gen")
        async def gen():
            return JSONResponse({"ok": True})

        client = TestClient(app)
        resp = client.get("/gen")
        rid = resp.headers.get("x-request-id", "")
        assert re.fullmatch(r"[0-9a-f]{32}", rid), f"Unexpected request_id: {rid!r}"

    def test_exception_in_call_next_propagates(self) -> None:
        """An exception raised by the route handler must propagate out of dispatch."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/boom")
        async def boom():
            raise RuntimeError("deliberate boom")

        client = TestClient(app, raise_server_exceptions=True)
        with pytest.raises(RuntimeError, match="deliberate boom"):
            client.get("/boom")

    def test_x_api_version_header_is_set(self) -> None:
        """The middleware must set X-API-Version: 1 on every successful response."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/version")
        async def version():
            return JSONResponse({"ok": True})

        client = TestClient(app)
        resp = client.get("/version")
        assert resp.headers.get("x-api-version") == "1"

    async def test_dispatch_direct_call_sets_state_request_id(self) -> None:
        """dispatch() sets request.state.request_id from the header."""
        middleware = RequestLoggingMiddleware(app=MagicMock())

        response = _make_response()
        call_next = AsyncMock(return_value=response)

        request = _make_request(request_id="test-req-id-999")
        request.state = MagicMock()

        with (
            patch("api.app_lifecycle.structlog.contextvars.bind_contextvars"),
            patch("api.app_lifecycle.structlog.contextvars.clear_contextvars"),
        ):
            result = await middleware.dispatch(request, call_next)

        assert request.state.request_id == "test-req-id-999"
        assert result.headers.get("X-Request-ID") == "test-req-id-999"

    async def test_dispatch_generates_request_id_when_header_absent(self) -> None:
        """When X-Request-ID header is absent, a new token_hex is generated."""
        middleware = RequestLoggingMiddleware(app=MagicMock())

        response = _make_response()
        call_next = AsyncMock(return_value=response)

        request = _make_request()  # no request_id in headers
        request.state = MagicMock()

        with (
            patch("api.app_lifecycle.structlog.contextvars.bind_contextvars"),
            patch("api.app_lifecycle.structlog.contextvars.clear_contextvars"),
            patch("api.app_lifecycle.secrets.token_hex", return_value="deadbeef" * 4) as mock_tok,
        ):
            await middleware.dispatch(request, call_next)

        mock_tok.assert_called_once_with(16)
        assert request.state.request_id == "deadbeef" * 4

    async def test_dispatch_exception_logs_and_reraises(self) -> None:
        """When call_next raises, dispatch logs the error and re-raises."""
        middleware = RequestLoggingMiddleware(app=MagicMock())

        call_next = AsyncMock(side_effect=ValueError("broken"))
        request = _make_request(request_id="req-ex-01")
        request.state = MagicMock()

        with (
            patch("api.app_lifecycle.structlog.contextvars.bind_contextvars"),
            patch("api.app_lifecycle.structlog.contextvars.clear_contextvars"),
            patch("api.app_lifecycle.logger") as mock_logger,
            pytest.raises(ValueError, match="broken"),
        ):
            await middleware.dispatch(request, call_next)

        mock_logger.exception.assert_called_once()
        call_kwargs = mock_logger.exception.call_args
        assert call_kwargs.args[0] == "request_error"


# ---------------------------------------------------------------------------
# RateLimitHeaderMiddleware
# ---------------------------------------------------------------------------


class TestRateLimitHeaderMiddleware:
    """Unit tests for RateLimitHeaderMiddleware.dispatch."""

    async def _call_dispatch(self, request: MagicMock) -> Response:
        """Run the middleware dispatch with the given request, return the response."""
        middleware = RateLimitHeaderMiddleware(app=MagicMock())
        response = _make_response()
        call_next = AsyncMock(return_value=response)
        return await middleware.dispatch(request, call_next)

    async def test_sets_rate_limit_headers_when_state_present(self) -> None:
        """All three X-RateLimit-* headers are set when request.state.rate_limit is populated."""
        request = MagicMock()
        request.state.rate_limit = {"limit": 100, "remaining": 42, "reset_at": 1700000000}

        response = await self._call_dispatch(request)

        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "42"
        assert response.headers["X-RateLimit-Reset"] == "1700000000"

    async def test_no_headers_when_rate_limit_is_none(self) -> None:
        """When request.state.rate_limit is None, no X-RateLimit-* headers are added."""
        request = MagicMock()
        # getattr(request.state, "rate_limit", None) == None
        del request.state.rate_limit  # remove attribute to trigger getattr default
        request.state = MagicMock(spec=[])  # spec=[] means no attributes → getattr returns default

        response = await self._call_dispatch(request)

        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers

    async def test_partial_values_only_set_present_headers(self) -> None:
        """When only some values are set in the rate_limit dict, only those headers appear."""
        request = MagicMock()
        request.state.rate_limit = {"limit": 50, "remaining": None, "reset_at": None}

        response = await self._call_dispatch(request)

        assert response.headers["X-RateLimit-Limit"] == "50"
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers

    async def test_zero_remaining_is_still_set(self) -> None:
        """remaining=0 is a valid value (>= 0) and should appear in the header."""
        request = MagicMock()
        request.state.rate_limit = {"limit": 10, "remaining": 0, "reset_at": 9999999999}

        response = await self._call_dispatch(request)

        assert response.headers["X-RateLimit-Remaining"] == "0"

    async def test_negative_limit_omits_header(self) -> None:
        """limit=-1 (unlimited sentinel) must NOT produce an X-RateLimit-Limit header."""
        request = MagicMock()
        request.state.rate_limit = {"limit": -1, "remaining": -1, "reset_at": 0}

        response = await self._call_dispatch(request)

        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers

    async def test_rate_limit_attribute_missing_from_state(self) -> None:
        """getattr returning None when attribute absent — no headers, no crash."""
        request = MagicMock()
        # Simulate absence via spec
        type(request.state).rate_limit = property(lambda self: None)

        response = await self._call_dispatch(request)

        assert "X-RateLimit-Limit" not in response.headers
