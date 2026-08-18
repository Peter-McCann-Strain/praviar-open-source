"""Wiring tests: EPO OPS transport helpers ↔ ResponseCache.

Covers the handshake between ``authenticated_json_get`` /
``authenticated_binary_get`` and the module-level ``ResponseCache``
singleton. These are freestanding functions (unlike PubChem's methods),
but the cache semantics are identical: RECORD captures first observation,
REPLAY hits skip HTTP, misses in REPLAY raise ``CacheMissError``, and
OAuth token refresh is deliberately NOT wrapped.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from aiolimiter import AsyncLimiter
from httpx import AsyncByteStream, AsyncClient, MockTransport, Request, Response

import praviar_pipeline.clients.epo_ops_transport as epo_transport
from praviar_pipeline.clients.epo_ops_transport import (
    authenticated_binary_get,
    authenticated_json_get,
    request_access_token,
)
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.response_cache import (
    CacheMissError,
    CacheMode,
    ResponseCache,
    compute_request_key,
    set_current_cache,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _make_client(handler) -> tuple[AsyncClient, AsyncLimiter]:
    transport = MockTransport(handler)
    client = AsyncClient(base_url="https://ops.epo.org/3.2/rest-services", transport=transport)
    limiter = AsyncLimiter(max_rate=1000, time_period=1)
    return client, limiter


class _Counter:
    """Counts invocations of a MockTransport handler."""

    def __init__(self, handler):
        self._handler = handler
        self.count = 0

    def __call__(self, request: Request) -> Response:
        self.count += 1
        return self._handler(request)


class _ChunkStream(AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


# ---------------------------------------------------------------------------
# JSON GET: RECORD / REPLAY / REPLAY_THEN_RECORD / DISABLED
# ---------------------------------------------------------------------------


class TestJsonGet:
    async def test_record_captures_first_observation_only(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"world-patent-data": {"exchange-documents": {}}}
        counter = _Counter(lambda r: Response(200, json=payload))
        client, limiter = _make_client(counter)
        try:
            first = await authenticated_json_get(
                client=client,
                limiter=limiter,
                path="/published-data/publication/docdb/US.7851188.B2/biblio",
                token="t1",
            )
            second = await authenticated_json_get(
                client=client,
                limiter=limiter,
                path="/published-data/publication/docdb/US.7851188.B2/biblio",
                token="t1",
            )
        finally:
            await client.aclose()

        assert first == payload
        assert second == payload
        assert counter.count == 2  # RECORD always calls through
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "epo_ops"' in lines[0]

    async def test_replay_then_record_serves_second_call_from_cache(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"ok": True}
        counter = _Counter(lambda r: Response(200, json=payload))
        client, limiter = _make_client(counter)
        try:
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
        finally:
            await client.aclose()

        assert counter.count == 1  # second call served from cache

    async def test_replay_hit_skips_http(self, tmp_path: Path) -> None:
        # First, record
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        payload = {"ok": True}
        counter = _Counter(lambda r: Response(200, json=payload))
        client, limiter = _make_client(counter)
        try:
            await authenticated_json_get(client=client, limiter=limiter, path="/biblio", token="t1")
        finally:
            await client.aclose()

        # Now replay
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = _Counter(lambda r: (_ for _ in ()).throw(AssertionError("live call")))
        client2, limiter2 = _make_client(explode)
        try:
            result = await authenticated_json_get(
                client=client2, limiter=limiter2, path="/biblio", token="t2"
            )
        finally:
            await client2.aclose()
        assert result == payload
        assert explode.count == 0

    async def test_replay_miss_raises_cache_miss_error(self, tmp_path: Path) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = _Counter(lambda r: (_ for _ in ()).throw(AssertionError("live call")))
        client, limiter = _make_client(explode)
        try:
            with pytest.raises(CacheMissError) as excinfo:
                await authenticated_json_get(
                    client=client, limiter=limiter, path="/missing", token="t"
                )
        finally:
            await client.aclose()

        expected_body = json.dumps({"params": None, "ok_on_404": False}, sort_keys=True)
        expected_key = compute_request_key(
            source="epo_ops", method="GET", url="/missing", body=expected_body
        )
        assert excinfo.value.key == expected_key
        assert explode.count == 0

    async def test_disabled_mode_passthrough_no_disk(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(200, json={"ok": True}))
        client, limiter = _make_client(counter)
        try:
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
        finally:
            await client.aclose()
        assert counter.count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

    async def test_no_cache_installed_passthrough(self, tmp_path: Path) -> None:
        counter = _Counter(lambda r: Response(200, json={"ok": True}))
        client, limiter = _make_client(counter)
        try:
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
            await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
        finally:
            await client.aclose()
        assert counter.count == 2

    async def test_different_params_produce_different_keys(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(200, json={"ok": True}))
        client, limiter = _make_client(counter)
        try:
            await authenticated_json_get(
                client=client,
                limiter=limiter,
                path="/search",
                token="t",
                params={"q": "aspirin"},
            )
            await authenticated_json_get(
                client=client,
                limiter=limiter,
                path="/search",
                token="t",
                params={"q": "aspirin"},
            )  # hit
            await authenticated_json_get(
                client=client,
                limiter=limiter,
                path="/search",
                token="t",
                params={"q": "ibuprofen"},
            )  # new key
        finally:
            await client.aclose()
        assert counter.count == 2
        assert len(cache) == 2

    async def test_ok_on_404_semantic_empty_is_recorded(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(404))
        client, limiter = _make_client(counter)
        try:
            result = await authenticated_json_get(
                client=client, limiter=limiter, path="/x", token="t", ok_on_404=True
            )
        finally:
            await client.aclose()
        assert result == {}
        assert len(cache) == 1

    async def test_source_unavailable_error_not_recorded(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(500))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(SourceUnavailableError):
                await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
        finally:
            await client.aclose()
        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

    async def test_authentication_error_not_recorded(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(401))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(AuthenticationError):
                await authenticated_json_get(client=client, limiter=limiter, path="/x", token="t")
        finally:
            await client.aclose()
        assert len(cache) == 0


# ---------------------------------------------------------------------------
# Binary GET
# ---------------------------------------------------------------------------


class TestBinaryGet:
    async def test_record_and_replay_binary_roundtrip(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        raw = b"\x89PNG\r\n\x1a\nfake-bytes"
        counter = _Counter(lambda r: Response(200, content=raw))
        client, limiter = _make_client(counter)
        try:
            result = await authenticated_binary_get(
                client=client, limiter=limiter, path="/drawing.png", token="t"
            )
        finally:
            await client.aclose()
        assert result == raw
        assert len(cache) == 1

        # Replay round-trips via base64
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = _Counter(lambda r: (_ for _ in ()).throw(AssertionError("live call")))
        client2, limiter2 = _make_client(explode)
        try:
            replayed = await authenticated_binary_get(
                client=client2, limiter=limiter2, path="/drawing.png", token="t2"
            )
        finally:
            await client2.aclose()
        assert replayed == raw
        assert explode.count == 0

    async def test_binary_404_semantic_empty_replayed_as_none(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(404))
        client, limiter = _make_client(counter)
        try:
            result = await authenticated_binary_get(
                client=client, limiter=limiter, path="/missing.png", token="t"
            )
        finally:
            await client.aclose()
        assert result is None
        assert len(cache) == 1

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = _Counter(lambda r: (_ for _ in ()).throw(AssertionError("live call")))
        client2, limiter2 = _make_client(explode)
        try:
            replayed = await authenticated_binary_get(
                client=client2, limiter=limiter2, path="/missing.png", token="t2"
            )
        finally:
            await client2.aclose()
        assert replayed is None

    async def test_binary_disabled_passthrough(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        raw = b"bytes"
        counter = _Counter(lambda r: Response(200, content=raw))
        client, limiter = _make_client(counter)
        try:
            result = await authenticated_binary_get(
                client=client, limiter=limiter, path="/x.png", token="t"
            )
        finally:
            await client.aclose()
        assert result == raw
        assert len(cache) == 0

    async def test_binary_401_raises_authentication_error(self, tmp_path: Path) -> None:
        counter = _Counter(lambda r: Response(401))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(AuthenticationError) as excinfo:
                await authenticated_binary_get(
                    client=client, limiter=limiter, path="/drawing.png", token="t"
                )
        finally:
            await client.aclose()
        assert excinfo.value.source == "epo_ops"
        assert counter.count == 1

    async def test_binary_5xx_raises_source_unavailable(self, tmp_path: Path) -> None:
        counter = _Counter(lambda r: Response(503))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(SourceUnavailableError) as excinfo:
                await authenticated_binary_get(
                    client=client, limiter=limiter, path="/drawing.png", token="t"
                )
        finally:
            await client.aclose()
        assert excinfo.value.status_code == 503
        assert excinfo.value.source == "epo_ops"
        assert counter.count == 1

    async def test_binary_accepts_exact_byte_cap(self, tmp_path: Path) -> None:
        counter = _Counter(lambda r: Response(200, content=b"12345"))
        client, limiter = _make_client(counter)
        try:
            result = await authenticated_binary_get(
                client=client,
                limiter=limiter,
                path="/drawing.png",
                token="t",
                max_bytes=5,
            )
        finally:
            await client.aclose()

        assert result == b"12345"

    async def test_binary_rejects_chunked_body_one_byte_over_cap(self, tmp_path: Path) -> None:
        counter = _Counter(lambda r: Response(200, stream=_ChunkStream([b"123", b"456"])))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(SourceUnavailableError, match="byte limit"):
                await authenticated_binary_get(
                    client=client,
                    limiter=limiter,
                    path="/drawing.png",
                    token="t",
                    max_bytes=5,
                )
        finally:
            await client.aclose()

    async def test_binary_requested_limit_cannot_exceed_transport_hard_cap(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(epo_transport, "EPO_BINARY_MAX_BYTES", 5)
        counter = _Counter(lambda r: Response(200, content=b"123456"))
        client, limiter = _make_client(counter)
        try:
            with pytest.raises(SourceUnavailableError, match="byte limit"):
                await authenticated_binary_get(
                    client=client,
                    limiter=limiter,
                    path="/drawing.png",
                    token="t",
                    max_bytes=100,
                )
        finally:
            await client.aclose()

    async def test_binary_cache_key_binds_body_cap(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        counter = _Counter(lambda r: Response(200, content=b"12345"))
        client, limiter = _make_client(counter)
        try:
            assert (
                await authenticated_binary_get(
                    client=client,
                    limiter=limiter,
                    path="/drawing.png",
                    token="t",
                    max_bytes=5,
                )
                == b"12345"
            )
        finally:
            await client.aclose()

        set_current_cache(ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY))
        client2, limiter2 = _make_client(
            lambda r: (_ for _ in ()).throw(AssertionError("live call"))
        )
        try:
            with pytest.raises(CacheMissError):
                await authenticated_binary_get(
                    client=client2,
                    limiter=limiter2,
                    path="/drawing.png",
                    token="rotated",
                    max_bytes=4,
                )
        finally:
            await client2.aclose()


# ---------------------------------------------------------------------------
# OAuth token — must NOT be cached
# ---------------------------------------------------------------------------


class TestOAuthNotCached:
    async def test_token_refresh_is_not_wrapped(self, tmp_path: Path) -> None:
        """Token endpoint must always hit the live network — tokens expire."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        counter = _Counter(
            lambda r: Response(
                200, json={"access_token": "abc", "token_type": "Bearer", "expires_in": 1200}
            )
        )
        transport = MockTransport(counter)
        auth = AsyncClient(base_url="https://ops.epo.org", transport=transport)
        try:
            await request_access_token(
                auth_client=auth,
                auth_url="/auth/accesstoken",
                consumer_key="ck",
                consumer_secret="cs",
            )
            await request_access_token(
                auth_client=auth,
                auth_url="/auth/accesstoken",
                consumer_key="ck",
                consumer_secret="cs",
            )
        finally:
            await auth.aclose()
        # Called live every time, nothing recorded.
        assert counter.count == 2
        assert len(cache) == 0
        assert cache.cache_path.exists()
        assert cache.cache_path.read_text(encoding="utf-8") == ""
