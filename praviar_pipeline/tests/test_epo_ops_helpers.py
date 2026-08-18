"""Focused tests for EPO OPS helper modules."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from aiolimiter import AsyncLimiter
from httpx import AsyncClient, MockTransport, Request, Response

from praviar_pipeline.clients.epo_ops_helpers import (
    build_cql_query,
    build_drawing_page_path,
    build_drawing_range_header,
    build_ops_auth_client,
    build_ops_client,
    build_ops_limiter,
    collect_drawings,
    refresh_access_token,
    to_docdb_format,
    to_epodoc_publication_format,
)
from praviar_pipeline.clients.epo_ops_transport import authenticated_json_get
from praviar_pipeline.errors import AuthenticationError


def test_to_docdb_format_converts_compact_and_hyphenated_ids() -> None:
    assert to_docdb_format("US7851188B2") == "US.7851188.B2"
    assert to_docdb_format("US-2024294466-A1") == "US.2024294466.A1"
    assert to_docdb_format("unknown") == "unknown"


def test_to_epodoc_publication_format_rejects_non_ep_and_strips_kind() -> None:
    assert to_epodoc_publication_format("EP1234567B1") == "EP1234567"
    assert to_epodoc_publication_format("EP-1234567-A1") == "EP1234567"
    with pytest.raises(ValueError, match="requires an EP publication"):
        to_epodoc_publication_format("US7851188B2")


def test_build_cql_query_combines_supported_filters() -> None:
    assert (
        build_cql_query(
            cpc_codes=["A01", "B02", "C03", "D04", "E05", "F06"],
            claim_keywords=["alpha", "beta"],
            applicants=["Acme", "Globex"],
        )
        == '(cpc="A01" OR cpc="B02" OR cpc="C03" OR cpc="D04" OR cpc="E05") AND (cl="alpha" OR cl="beta") AND (pa="Acme" OR pa="Globex")'
    )


def test_build_drawing_page_path_uses_page_range() -> None:
    assert (
        build_drawing_page_path("US.7851188.B2", 3, "image/png")
        == "/published-data/publication/docdb/US.7851188.B2/images"
    )


def test_build_drawing_range_header() -> None:
    assert build_drawing_range_header(3) == "3-3"
    assert build_drawing_range_header(1) == "1-1"


def test_build_ops_limiter_uses_requests_per_minute() -> None:
    limiter = build_ops_limiter(requests_per_minute=7)
    assert limiter.max_rate == 7
    assert limiter.time_period == 60


def test_build_ops_client_uses_settings_timeout_and_limits() -> None:
    settings = SimpleNamespace(
        http_timeout_default=12.5,
        http_connect_timeout=3.25,
        http_max_connections=11,
        http_max_keepalive=7,
    )

    client = build_ops_client(base_url="https://ops.epo.org/3.2/rest-services", settings=settings)
    try:
        assert str(client.base_url).endswith("/3.2/rest-services/")
        assert client.timeout.connect == 3.25
        assert client.timeout.read == 12.5
    finally:
        # Keep the test isolated from transport/resource lifetime.
        import asyncio

        asyncio.run(client.aclose())


def test_build_ops_auth_client_uses_settings_timeout() -> None:
    settings = SimpleNamespace(
        http_timeout_default=9.5,
        http_connect_timeout=2.0,
    )

    client = build_ops_auth_client(settings=settings)
    try:
        assert client.timeout.connect == 2.0
        assert client.timeout.read == 9.5
    finally:
        import asyncio

        asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_refresh_access_token_returns_token_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_access_token_fn(**kwargs):
        assert kwargs["auth_url"] == "https://ops.epo.org/3.2/auth/accesstoken"
        assert kwargs["consumer_key"] == "key"
        assert kwargs["consumer_secret"] == "secret"
        return {"access_token": "token-123", "expires_in": 1200}

    monkeypatch.setattr("praviar_pipeline.clients.epo_ops_helpers.time.monotonic", lambda: 100.0)

    token, expires_at = await refresh_access_token(
        auth_client=SimpleNamespace(),
        auth_url="https://ops.epo.org/3.2/auth/accesstoken",
        consumer_key="key",
        consumer_secret="secret",
        request_access_token_fn=fake_request_access_token_fn,
        logger=SimpleNamespace(
            debug=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None
        ),
    )

    assert token == "token-123"
    assert expires_at == 1240.0


@pytest.mark.asyncio
async def test_refresh_access_token_raises_without_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_access_token_fn(**kwargs):
        return {"expires_in": 1200}

    monkeypatch.setattr("praviar_pipeline.clients.epo_ops_helpers.time.monotonic", lambda: 100.0)

    with pytest.raises(AuthenticationError) as excinfo:
        await refresh_access_token(
            auth_client=SimpleNamespace(),
            auth_url="https://ops.epo.org/3.2/auth/accesstoken",
            consumer_key="key",
            consumer_secret="secret",
            request_access_token_fn=fake_request_access_token_fn,
            logger=SimpleNamespace(
                debug=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None
            ),
        )

    message = str(excinfo.value)
    assert message == "EPO OPS token response missing access token"
    assert "secret" not in message
    assert "https://" not in message


@pytest.mark.asyncio
async def test_authenticated_json_get_returns_empty_dict_on_404_when_ok() -> None:
    """With ok_on_404=True, 404 is a semantic empty (e.g., no family data)."""

    async def handler(request: Request) -> Response:
        assert request.headers["authorization"] == "Bearer token-123"
        return Response(404, request=request)

    transport = MockTransport(handler)
    async with AsyncClient(base_url="https://ops.epo.org", transport=transport) as client:
        data = await authenticated_json_get(
            client=client,
            limiter=AsyncLimiter(1, 1),
            path="/published-data/search",
            token="token-123",
            ok_on_404=True,
        )

    assert data == {}


@pytest.mark.asyncio
async def test_authenticated_json_get_raises_source_unavailable_on_404_by_default() -> None:
    """Without ok_on_404, 404 is a source failure (SourceUnavailableError)."""
    from praviar_pipeline.errors import SourceUnavailableError

    async def handler(request: Request) -> Response:
        return Response(404, request=request)

    transport = MockTransport(handler)
    async with AsyncClient(base_url="https://ops.epo.org", transport=transport) as client:
        with pytest.raises(SourceUnavailableError) as excinfo:
            await authenticated_json_get(
                client=client,
                limiter=AsyncLimiter(1, 1),
                path="/published-data/search",
                token="token-123",
            )

    assert excinfo.value.status_code == 404
    assert excinfo.value.source == "epo_ops"


@pytest.mark.asyncio
async def test_authenticated_json_get_raises_source_unavailable_on_5xx() -> None:
    from praviar_pipeline.errors import SourceUnavailableError

    async def handler(request: Request) -> Response:
        return Response(503, request=request)

    transport = MockTransport(handler)
    async with AsyncClient(base_url="https://ops.epo.org", transport=transport) as client:
        with pytest.raises(SourceUnavailableError) as excinfo:
            await authenticated_json_get(
                client=client,
                limiter=AsyncLimiter(1, 1),
                path="/published-data/publication/docdb/US.7851188.B2/biblio",
                token="token-123",
            )

    assert excinfo.value.status_code == 503


@pytest.mark.asyncio
async def test_collect_drawings_logs_failures_and_keeps_successes() -> None:
    async def fetch_drawing_page(patent_id: str, page: int, image_format: str):
        assert patent_id == "US7851188B2"
        assert image_format == "image/png"
        if page == 2:
            raise httpx.ReadError("boom", request=Request("GET", "https://ops.epo.org"))
        return b"page-bytes" if page == 1 else None

    logger = SimpleNamespace(
        warning=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
    )

    drawings = await collect_drawings(
        patent_id="US7851188B2",
        pages_to_fetch=3,
        image_format="image/png",
        fetch_drawing_page=fetch_drawing_page,
        logger=logger,
    )

    assert drawings == [(1, b"page-bytes")]
