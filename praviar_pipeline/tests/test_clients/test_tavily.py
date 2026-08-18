from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from praviar_pipeline.clients.tavily import TavilyClient
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.no_paid_api import PaidApiBlockedError


def test_tavily_client_required_missing_key_raises() -> None:
    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key=""),
    ):
        with pytest.raises(ConfigurationError) as excinfo:
            TavilyClient(required=True)

    assert excinfo.value.source == "tavily"


@pytest.mark.asyncio
async def test_tavily_search_blocks_live_request_in_no_paid_mode(monkeypatch) -> None:
    class _UnexpectedHTTPClient:
        async def post(self, *_args, **_kwargs):
            raise AssertionError("Tavily transport should not be reached")

    monkeypatch.setenv("NO_PAID_API", "true")
    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key="key", tavily_requests_per_minute=10.0),
    ):
        client = TavilyClient()
    client._client = _UnexpectedHTTPClient()

    with pytest.raises(PaidApiBlockedError, match="NO_PAID_API=true"):
        await client.search("succinic acid cpc", required=True)


@pytest.mark.asyncio
async def test_tavily_search_required_transport_error_raises() -> None:
    sentinel = "tavily-transport-api-key-sentinel"

    class _FailingHTTPClient:
        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError(f"offline request?api_key={sentinel}")

    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key="key", tavily_requests_per_minute=10.0),
    ):
        client = TavilyClient()
    client._client = _FailingHTTPClient()

    with (
        patch("praviar_pipeline.clients.tavily.assert_paid_api_allowed"),
        pytest.raises(SourceUnavailableError) as excinfo,
    ):
        await client.search("succinic acid cpc", required=True)

    assert excinfo.value.source == "tavily"
    assert str(excinfo.value) == "tavily unavailable: grounding search failed"
    assert sentinel not in repr(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


@pytest.mark.asyncio
async def test_tavily_search_optional_transport_error_returns_empty() -> None:
    class _FailingHTTPClient:
        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")

    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key="key", tavily_requests_per_minute=10.0),
    ):
        client = TavilyClient()
    client._client = _FailingHTTPClient()

    with patch("praviar_pipeline.clients.tavily.assert_paid_api_allowed"):
        assert await client.search("succinic acid cpc") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [402, 432])
async def test_tavily_search_billing_or_rate_limit_fails_closed_when_required(
    status_code: int,
) -> None:
    """HTTP 402/432 are terminal evidence gaps in required grounding mode."""

    class _ExhaustedClient:
        async def post(self, *_args, **_kwargs):
            response = httpx.Response(
                status_code, request=httpx.Request("POST", "https://api.tavily.com/search")
            )
            raise httpx.HTTPStatusError(
                f"Client error '{status_code}'",
                request=response.request,
                response=response,
            )

    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key="key", tavily_requests_per_minute=10.0),
    ):
        client = TavilyClient(required=True)
    client._client = _ExhaustedClient()

    with (
        patch("praviar_pipeline.clients.tavily.assert_paid_api_allowed"),
        patch("praviar_pipeline.clients.tavily.asyncio.sleep"),
    ):
        with pytest.raises(SourceUnavailableError) as exc_info:
            await client.search("aspirin CPC codes", required=True)

    assert exc_info.value.source == "tavily"
    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_tavily_search_server_error_with_required_raises_source_unavailable() -> None:
    """Non-billing HTTP errors (e.g. 500) still raise SourceUnavailableError in required mode."""

    class _ServerErrorClient:
        async def post(self, *_args, **_kwargs):
            response = httpx.Response(
                500, request=httpx.Request("POST", "https://api.tavily.com/search")
            )
            raise httpx.HTTPStatusError(
                "Server error '500'",
                request=response.request,
                response=response,
            )

    with patch(
        "praviar_pipeline.clients.tavily.get_settings",
        return_value=SimpleNamespace(tavily_api_key="key", tavily_requests_per_minute=10.0),
    ):
        client = TavilyClient()
    client._client = _ServerErrorClient()

    with (
        patch("praviar_pipeline.clients.tavily.assert_paid_api_allowed"),
        pytest.raises(SourceUnavailableError) as excinfo,
    ):
        await client.search("aspirin CPC codes", required=True)

    assert excinfo.value.source == "tavily"
