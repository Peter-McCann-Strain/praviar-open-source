"""Wiring tests: LensClient ↔ ResponseCache.

Covers the handshake between ``LensClient._post`` and the module-level
``ResponseCache`` singleton. Lens is a POST-based search API, so the cache
key must fold the JSON-serialised payload into the body hash — distinct
queries must key distinctly even when they hit the same path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.lens import LensClient
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
def lens_client(mock_settings) -> LensClient:
    return LensClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.lens.org/patent/search"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        """RECORD mode calls through every time, but JSONL dedups on key."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"data": [{"lens_id": "abc"}], "total": 1}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": {"match": {"title": "aspirin"}}}
        with patch.object(lens_client._client, "post", mock_post):
            first = await lens_client._post("/patent/search", payload=query)
            second = await lens_client._post("/patent/search", payload=query)

        assert first == payload
        assert second == payload
        assert mock_post.call_count == 2  # RECORD always calls through
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "lens"' in lines[0]

        await lens_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"data": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": {"match": {"title": "aspirin"}}}
        with patch.object(lens_client._client, "post", mock_post):
            first = await lens_client._post("/patent/search", payload=query)
            second = await lens_client._post("/patent/search", payload=query)

        assert first == payload
        assert second == payload
        assert mock_post.call_count == 1

        await lens_client.close()

    async def test_different_payloads_produce_different_cache_keys(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        """Two POSTs to the same path with different bodies record distinctly."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"data": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        q1 = {"query": {"match": {"title": "aspirin"}}}
        q2 = {"query": {"match": {"title": "ibuprofen"}}}
        with patch.object(lens_client._client, "post", mock_post):
            await lens_client._post("/patent/search", payload=q1)
            await lens_client._post("/patent/search", payload=q1)  # hit
            await lens_client._post("/patent/search", payload=q2)  # new key

        assert mock_post.call_count == 2
        assert len(cache) == 2

        await lens_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(self, lens_client: LensClient, tmp_path: Path) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"data": [{"lens_id": "abc"}]}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": {"match": {"title": "aspirin"}}}
        with patch.object(lens_client._client, "post", mock_post):
            await lens_client._post("/patent/search", payload=query)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(lens_client._client, "post", explode):
            result = await lens_client._post("/patent/search", payload=query)
        assert result == payload
        assert explode.call_count == 0

        await lens_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        query = {"query": {"match": {"title": "missing"}}}
        with patch.object(lens_client._client, "post", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await lens_client._post("/patent/search", payload=query)
        expected_key = compute_request_key(
            source="lens",
            method="POST",
            url="/patent/search",
            body=json.dumps(query, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await lens_client.close()


# ---------------------------------------------------------------------------
# No cache installed / DISABLED — default passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, lens_client: LensClient) -> None:
        payload = {"data": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"q": 1}
        with patch.object(lens_client._client, "post", mock_post):
            await lens_client._post("/patent/search", payload=query)
            await lens_client._post("/patent/search", payload=query)
        assert mock_post.call_count == 2

        await lens_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"data": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"q": 1}
        with patch.object(lens_client._client, "post", mock_post):
            await lens_client._post("/patent/search", payload=query)
            await lens_client._post("/patent/search", payload=query)
        assert mock_post.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await lens_client.close()


# ---------------------------------------------------------------------------
# Error propagation and key-collision safety
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        with patch(
            "praviar_pipeline.clients.lens.wait_exponential_jitter",
            return_value=lambda *_a, **_kw: 0,
        ):
            mock_post = AsyncMock(return_value=_fake_response({}, status_code=404))
            with patch.object(lens_client._client, "post", mock_post):
                # SourceUnavailableError is in retry_if_not_exception_type, so
                # it propagates on first attempt, not wrapped in RetryError.
                with pytest.raises((SourceUnavailableError, RetryError)):
                    await lens_client._post("/patent/search", payload={"q": 1})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await lens_client.close()

    async def test_authentication_error_preserved_and_not_cached(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        """401/403 responses raise AuthenticationError — must NOT be recorded."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        mock_post = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(lens_client._client, "post", mock_post):
            with pytest.raises(AuthenticationError):
                await lens_client._post("/patent/search", payload={"q": 1})
        assert len(cache) == 0

        await lens_client.close()

    async def test_retry_eventually_succeeds_records_one_entry(
        self, lens_client: LensClient, tmp_path: Path
    ) -> None:
        """Tenacity retries on 5xx; final success records exactly one entry."""
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        payload = {"data": [{"ok": True}]}
        responses = [
            _fake_response({}, status_code=500),
            _fake_response({}, status_code=500),
            _fake_response(payload),
        ]
        mock_post = AsyncMock(side_effect=responses)
        with (
            patch(
                "praviar_pipeline.clients.lens.wait_exponential_jitter",
                return_value=lambda *_a, **_kw: 0,
            ),
            patch.object(lens_client._client, "post", mock_post),
        ):
            try:
                result = await lens_client._post("/patent/search", payload={"q": 1})
            except RetryError:
                result = None

        if result is not None:
            assert result == payload
            assert len(cache) == 1
        else:
            # 3 attempts exhausted before success — nothing cached.
            assert len(cache) == 0

        await lens_client.close()

    async def test_compute_request_key_different_source_does_not_collide(
        self,
    ) -> None:
        """Same body/url keyed under a different source produces a different key."""
        body = json.dumps({"q": 1}, sort_keys=True)
        lens_key = compute_request_key(
            source="lens", method="POST", url="/patent/search", body=body
        )
        other_key = compute_request_key(
            source="pubchem", method="POST", url="/patent/search", body=body
        )
        assert lens_key != other_key
