"""Wiring tests: OpenAlexClient ↔ ResponseCache.

Covers the handshake between ``OpenAlexClient._get`` and the module-level
``ResponseCache`` singleton. The cache key folds the user-supplied query
params (NOT the api_key auth credential) into the body hash so distinct
queries key distinctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.openalex import OpenAlexClient
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
def openalex_client(mock_settings) -> OpenAlexClient:
    return OpenAlexClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://api.openalex.org/works"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"results": [{"id": "W1"}], "meta": {}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"search": "aspirin", "per_page": "10", "cursor": "*"}
        with patch.object(openalex_client._client, "get", mock_get):
            first = await openalex_client._get("/works", params=params)
            second = await openalex_client._get("/works", params=params)

        assert first == payload
        assert second == payload
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "openalex"' in lines[0]

        await openalex_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"search": "aspirin"}
        with patch.object(openalex_client._client, "get", mock_get):
            first = await openalex_client._get("/works", params=params)
            second = await openalex_client._get("/works", params=params)

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 1

        await openalex_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(openalex_client._client, "get", mock_get):
            await openalex_client._get("/works", params={"search": "aspirin"})
            await openalex_client._get("/works", params={"search": "aspirin"})  # hit
            await openalex_client._get("/works", params={"search": "ibuprofen"})  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await openalex_client.close()

    async def test_different_paths_produce_different_cache_keys(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(openalex_client._client, "get", mock_get):
            await openalex_client._get("/works", params={"search": "x"})
            await openalex_client._get("/authors", params={"search": "x"})

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await openalex_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"results": [{"id": "W1"}]}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"search": "aspirin"}
        with patch.object(openalex_client._client, "get", mock_get):
            await openalex_client._get("/works", params=params)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(openalex_client._client, "get", explode):
            result = await openalex_client._get("/works", params=params)
        assert result == payload
        assert explode.call_count == 0

        await openalex_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(openalex_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await openalex_client._get("/works", params={"search": "missing"})
        expected_key = compute_request_key(
            source="openalex",
            method="GET",
            url="/works",
            body=json.dumps({"search": "missing"}, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await openalex_client.close()


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, openalex_client: OpenAlexClient) -> None:
        payload = {"results": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(openalex_client._client, "get", mock_get):
            await openalex_client._get("/works", params={"search": "x"})
            await openalex_client._get("/works", params={"search": "x"})
        assert mock_get.call_count == 2

        await openalex_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"results": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(openalex_client._client, "get", mock_get):
            await openalex_client._get("/works", params={"search": "x"})
            await openalex_client._get("/works", params={"search": "x"})
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await openalex_client.close()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(openalex_client._client, "get", mock_get):
            with pytest.raises(SourceUnavailableError):
                await openalex_client._get("/works", params={"search": "boom"})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await openalex_client.close()

    async def test_authentication_error_not_cached(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)
        mock_get = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(openalex_client._client, "get", mock_get):
            with pytest.raises(AuthenticationError):
                await openalex_client._get("/works", params={"search": "x"})
        assert len(cache) == 0

        await openalex_client.close()

    async def test_ok_on_404_records_empty_dict(
        self, openalex_client: OpenAlexClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(openalex_client._client, "get", mock_get):
            result = await openalex_client._get(
                "/works/W1", params={"select": "id"}, ok_on_404=True
            )
        assert result == {}
        assert len(cache) == 1

        await openalex_client.close()
