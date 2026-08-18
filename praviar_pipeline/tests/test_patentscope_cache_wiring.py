"""Wiring tests: PatentScopeClient ↔ ResponseCache.

Covers the handshake between ``PatentScopeClient._get`` and the module-level
``ResponseCache`` singleton. PatentScope is a GET-based search API where the
query parameters carry the search semantics, so the cache key folds the
JSON-serialised params into the body hash — distinct queries must key
distinctly even when they hit the same path (``/search``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.patentscope import PatentScopeClient
from praviar_pipeline.errors import AuthenticationError
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
def patentscope_client(monkeypatch, mock_settings) -> PatentScopeClient:
    """A configured PatentScopeClient (real settings have no creds in test env)."""
    # Make sure the client believes credentials are configured so _get is reachable.
    client = PatentScopeClient()
    client._username = "test-user"
    client._password = "test-pass"
    return client


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://patentscope.wipo.int/search/en/api/search"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"response": {"numFound": 0, "docs": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "succinic", "rows": "10"}
        with patch.object(patentscope_client._client, "get", mock_get):
            first = await patentscope_client._get("/search", params=params)
            second = await patentscope_client._get("/search", params=params)

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 2  # RECORD always calls through
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "patentscope"' in lines[0]

        await patentscope_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"response": {"numFound": 0, "docs": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "succinic", "rows": "10"}
        with patch.object(patentscope_client._client, "get", mock_get):
            await patentscope_client._get("/search", params=params)
            await patentscope_client._get("/search", params=params)

        assert mock_get.call_count == 1  # second is a hit

        await patentscope_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"response": {"numFound": 0, "docs": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentscope_client._client, "get", mock_get):
            await patentscope_client._get("/search", params={"query": "a"})
            await patentscope_client._get("/search", params={"query": "a"})  # hit
            await patentscope_client._get("/search", params={"query": "b"})  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await patentscope_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"response": {"numFound": 1, "docs": [{"publicationNumber": "WO1"}]}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"query": "x"}
        with patch.object(patentscope_client._client, "get", mock_get):
            await patentscope_client._get("/search", params=params)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(patentscope_client._client, "get", explode):
            result = await patentscope_client._get("/search", params=params)
        assert result == payload
        assert explode.call_count == 0

        await patentscope_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        params = {"query": "missing"}
        with patch.object(patentscope_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await patentscope_client._get("/search", params=params)
        expected_key = compute_request_key(
            source="patentscope",
            method="GET",
            url="/search",
            body=json.dumps(params, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await patentscope_client.close()


# ---------------------------------------------------------------------------
# Passthrough — no cache / DISABLED
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(
        self, patentscope_client: PatentScopeClient
    ) -> None:
        payload = {"response": {"numFound": 0, "docs": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentscope_client._client, "get", mock_get):
            await patentscope_client._get("/search", params={"query": "a"})
            await patentscope_client._get("/search", params={"query": "a"})
        assert mock_get.call_count == 2

        await patentscope_client.close()

    async def test_disabled_mode_pure_passthrough_no_disk_writes(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"response": {"numFound": 0, "docs": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentscope_client._client, "get", mock_get):
            await patentscope_client._get("/search", params={"query": "a"})
            await patentscope_client._get("/search", params={"query": "a"})
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await patentscope_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed live calls must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_auth_error_is_not_recorded(
        self, patentscope_client: PatentScopeClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(patentscope_client._client, "get", mock_get):
            with pytest.raises(AuthenticationError):
                await patentscope_client._get("/search", params={"query": "x"})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await patentscope_client.close()

    async def test_compute_request_key_folds_params_into_body(self) -> None:
        params = {"query": "succinic"}
        body = json.dumps(params, sort_keys=True)
        k1 = compute_request_key(source="patentscope", method="GET", url="/search", body=body)
        k2 = compute_request_key(source="patentscope", method="GET", url="/search", body=None)
        assert k1 != k2
