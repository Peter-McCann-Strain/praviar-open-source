from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from api.services import licensed_family_overlay


def _settings(search_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        licensed_family_overlay_provider_name="Acme Family Overlay",
        licensed_family_overlay_search_url=search_url,
        licensed_family_overlay_api_key="secret",
        licensed_family_overlay_allowed_org_ids=["org-1"],
        licensed_family_overlay_timeout_seconds=12.0,
    )


class _FakeStreamingResponse:
    """Models the subset of the httpx streaming response the overlay reads."""

    def __init__(self, body: bytes, *, chunk_size: int = 8) -> None:
        self._body = body
        self._chunk_size = chunk_size

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        for start in range(0, len(self._body), self._chunk_size):
            yield self._body[start : start + self._chunk_size]

    async def __aenter__(self) -> _FakeStreamingResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _FakeStreamingClient:
    """Records constructor kwargs and serves a fixed streamed body."""

    def __init__(self, captured: dict[str, Any], *, body: bytes) -> None:
        self._captured = captured
        self._body = body

    def factory(self, **kwargs: Any) -> _FakeStreamingClient:
        self._captured.update(kwargs)
        return self

    async def __aenter__(self) -> _FakeStreamingClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def stream(self, method: str, url: str, *, json: dict[str, Any]) -> _FakeStreamingResponse:
        self._captured["method"] = method
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakeStreamingResponse(self._body)


def test_runtime_config_is_not_configured_for_unsafe_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://127.0.0.1/search"),
    )

    runtime_config = licensed_family_overlay.get_licensed_family_overlay_runtime_config()

    assert runtime_config.search_url_safe is False
    assert runtime_config.configured is False


@pytest.mark.asyncio
async def test_public_endpoint_network_backend_rejects_private_connected_peer() -> None:
    class FakeStream:
        closed = False

        def get_extra_info(self, info: str) -> object:
            if info == "server_addr":
                return ("10.0.0.1", 443)
            return None

        async def aclose(self) -> None:
            self.closed = True

    class FakeBackend:
        stream = FakeStream()

        async def connect_tcp(self, *args: Any, **kwargs: Any) -> FakeStream:
            return self.stream

        async def sleep(self, seconds: float) -> None:
            return None

    backend = FakeBackend()
    guarded = licensed_family_overlay._PublicEndpointNetworkBackend(backend)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must resolve only to public IP ranges"):
        await guarded.connect_tcp("licensed.example", 443)

    assert backend.stream.closed is True


@pytest.mark.asyncio
async def test_public_endpoint_network_backend_allows_public_connected_peer() -> None:
    class FakeStream:
        def get_extra_info(self, info: str) -> object:
            if info == "server_addr":
                return ("8.8.8.8", 443)
            return None

        async def aclose(self) -> None:
            raise AssertionError("public peer should not be closed")

    class FakeBackend:
        stream = FakeStream()

        async def connect_tcp(self, *args: Any, **kwargs: Any) -> FakeStream:
            return self.stream

        async def sleep(self, seconds: float) -> None:
            return None

    guarded = licensed_family_overlay._PublicEndpointNetworkBackend(FakeBackend())  # type: ignore[arg-type]

    assert await guarded.connect_tcp("licensed.example", 443) is FakeBackend.stream


@pytest.mark.asyncio
async def test_search_licensed_family_overlay_rejects_unsafe_url_without_http_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> object:
        raise AssertionError("unsafe overlay URL opened an HTTP client")

    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://169.254.169.254/computeMetadata/v1/"),
    )
    monkeypatch.setattr(licensed_family_overlay.httpx, "AsyncClient", fail_if_called)

    with pytest.raises(ValueError, match="LICENSED_FAMILY_OVERLAY_SEARCH_URL"):
        await licensed_family_overlay.search_licensed_family_overlay({"query": "aspirin"})


@pytest.mark.asyncio
async def test_search_licensed_family_overlay_uses_no_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    client_instance = _FakeStreamingClient(
        captured,
        body=b'{"results": [{"id": "licensed-1"}]}',
    )

    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://licensed.example/search"),
    )
    monkeypatch.setattr(
        licensed_family_overlay.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, "", ("8.8.8.8", 443))],
    )
    monkeypatch.setattr(
        licensed_family_overlay.httpx,
        "AsyncClient",
        client_instance.factory,
    )

    results = await licensed_family_overlay.search_licensed_family_overlay({"query": "aspirin"})

    assert results == [{"id": "licensed-1"}]
    assert captured["follow_redirects"] is False
    assert isinstance(
        captured["transport"],
        licensed_family_overlay.httpx.AsyncHTTPTransport,
    )
    assert captured["url"] == "https://licensed.example/search"


@pytest.mark.asyncio
@pytest.mark.parametrize("resolved_ip", ["10.0.0.1", "169.254.169.254"])
async def test_search_licensed_family_overlay_rejects_private_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
    resolved_ip: str,
) -> None:
    def fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[tuple]:
        return [(None, None, None, "", (resolved_ip, 443))]

    def fail_if_called(*args: Any, **kwargs: Any) -> object:
        raise AssertionError("unsafe overlay URL opened an HTTP client")

    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://licensed.example/search"),
    )
    monkeypatch.setattr(licensed_family_overlay.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(licensed_family_overlay.httpx, "AsyncClient", fail_if_called)

    with pytest.raises(ValueError, match="must resolve only to public IP ranges"):
        await licensed_family_overlay.search_licensed_family_overlay({"query": "aspirin"})


@pytest.mark.asyncio
async def test_search_licensed_family_overlay_allows_public_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    client_instance = _FakeStreamingClient(
        captured,
        body=b'{"results": [{"id": "licensed-1"}]}',
    )

    def fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[tuple]:
        return [(None, None, None, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://licensed.example/search"),
    )
    monkeypatch.setattr(licensed_family_overlay.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        licensed_family_overlay.httpx,
        "AsyncClient",
        client_instance.factory,
    )

    result = await licensed_family_overlay.search_licensed_family_overlay({"query": "aspirin"})

    assert result == [{"id": "licensed-1"}]
    assert captured["url"] == "https://licensed.example/search"


@pytest.mark.asyncio
async def test_search_licensed_family_overlay_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    oversized = b"x" * (licensed_family_overlay._MAX_OVERLAY_RESPONSE_BYTES + 1)
    client_instance = _FakeStreamingClient(captured, body=oversized)

    def fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[tuple]:
        return [(None, None, None, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(
        licensed_family_overlay,
        "get_settings",
        lambda: _settings("https://licensed.example/search"),
    )
    monkeypatch.setattr(licensed_family_overlay.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        licensed_family_overlay.httpx,
        "AsyncClient",
        client_instance.factory,
    )

    with pytest.raises(ValueError, match="exceeded"):
        await licensed_family_overlay.search_licensed_family_overlay({"query": "aspirin"})
