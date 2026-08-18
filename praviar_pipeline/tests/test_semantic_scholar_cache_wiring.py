"""Wiring tests: SemanticScholarClient ↔ ResponseCache.

Covers the handshake between ``SemanticScholarClient._get`` and the
module-level ``ResponseCache`` singleton. The cache key folds query params
into the body hash. The 429 retry-after handling is preserved on the
underlying ``_get_uncached`` method (cache hits bypass tenacity entirely).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.semantic_scholar import (
    SemanticScholarClient,
    _build_rate_limiter,
    _effective_requests_per_second,
    _RateLimitError,
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


@pytest.fixture
def s2_client(mock_settings) -> SemanticScholarClient:
    return SemanticScholarClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(
    payload: dict, status_code: int = 200, headers: dict | None = None
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search"),
    )


def test_effective_rate_limit_obeys_conservative_local_cap() -> None:
    assert _effective_requests_per_second(100.0) == 0.8
    assert _effective_requests_per_second(1.0) == 0.8
    assert _effective_requests_per_second(0.5) == 0.5


def test_rate_limiter_uses_single_request_bucket_with_longer_period() -> None:
    limiter = _build_rate_limiter(1.0)

    assert limiter.max_rate == 1
    assert limiter.time_period == 1.25


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"data": [{"paperId": "P1"}], "total": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "aspirin", "limit": "10"}
        with patch.object(s2_client._client, "get", mock_get):
            first = await s2_client._get("/paper/search", params=params)
            second = await s2_client._get("/paper/search", params=params)

        assert first == payload
        assert second == payload
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "semantic_scholar"' in lines[0]

        await s2_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"data": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "aspirin"}
        with patch.object(s2_client._client, "get", mock_get):
            first = await s2_client._get("/paper/search", params=params)
            second = await s2_client._get("/paper/search", params=params)

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 1

        await s2_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"data": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(s2_client._client, "get", mock_get):
            await s2_client._get("/paper/search", params={"query": "aspirin"})
            await s2_client._get("/paper/search", params={"query": "aspirin"})  # hit
            await s2_client._get("/paper/search", params={"query": "ibuprofen"})  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await s2_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"data": [{"paperId": "P1"}]}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "aspirin"}
        with patch.object(s2_client._client, "get", mock_get):
            await s2_client._get("/paper/search", params=params)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(s2_client._client, "get", explode):
            result = await s2_client._get("/paper/search", params=params)
        assert result == payload
        assert explode.call_count == 0

        await s2_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(s2_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await s2_client._get("/paper/search", params={"query": "missing"})
        expected_key = compute_request_key(
            source="semantic_scholar",
            method="GET",
            url="/paper/search",
            body=json.dumps({"query": "missing"}, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await s2_client.close()


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, s2_client: SemanticScholarClient) -> None:
        payload = {"data": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(s2_client._client, "get", mock_get):
            await s2_client._get("/paper/search", params={"query": "x"})
            await s2_client._get("/paper/search", params={"query": "x"})
        assert mock_get.call_count == 2

        await s2_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"data": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(s2_client._client, "get", mock_get):
            await s2_client._get("/paper/search", params={"query": "x"})
            await s2_client._get("/paper/search", params={"query": "x"})
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await s2_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed calls must NOT be cached, 429 retry preserved
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(s2_client._client, "get", mock_get):
            with pytest.raises(SourceUnavailableError):
                await s2_client._get("/paper/search", params={"query": "boom"})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await s2_client.close()

    async def test_authentication_error_not_cached(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        mock_get = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(s2_client._client, "get", mock_get):
            with pytest.raises(AuthenticationError):
                await s2_client._get("/paper/search", params={"query": "x"})
        assert len(cache) == 0

        await s2_client.close()

    async def test_429_retry_after_handling_preserved_on_uncached(
        self, s2_client: SemanticScholarClient, tmp_path: Path
    ) -> None:
        """The 429 retry-after handling lives on ``_get_uncached``. Verify
        that on a cache miss we still flow through tenacity: a 429 followed
        by a 200 yields the success and records exactly one cache entry."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"data": [{"paperId": "P1"}]}
        responses = [
            _fake_response({}, status_code=429, headers={"Retry-After": "0"}),
            _fake_response(payload),
        ]
        mock_get = AsyncMock(side_effect=responses)
        # Short-circuit any wait so the test runs quickly.
        with (
            patch(
                "praviar_pipeline.clients.semantic_scholar._wait_for_rate_limit",
                return_value=0,
            ),
            patch.object(s2_client._client, "get", mock_get),
        ):
            result = await s2_client._get("/paper/search", params={"query": "x"})

        assert result == payload
        assert mock_get.call_count == 2
        assert len(cache) == 1

        await s2_client.close()

    async def test_rate_limit_error_type_still_raised_directly(self) -> None:
        """Sanity: the 429 path raises ``_RateLimitError`` for tenacity."""
        # This is a unit-level pin that our refactor didn't break the
        # error type the retry decorator depends on.
        err = _RateLimitError(retry_after=1.5)
        assert err.retry_after == 1.5
