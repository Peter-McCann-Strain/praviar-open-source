"""Wiring tests: USPTOODPClient ↔ ResponseCache.

USPTO ODP exposes both GET (file wrapper, application metadata, continuity,
etc.) and POST (search) helpers. Both are wired to the ``ResponseCache``
singleton so prosecution-history retrievals (the most expensive ODP calls)
record once and replay deterministically.

The cache key folds the JSON-serialised query params / payloads into the
body hash so distinct lookups key distinctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.uspto_odp import USPTOODPClient
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
def odp_client(mock_settings) -> USPTOODPClient:
    return USPTOODPClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://api.uspto.gov/api/v1/test"),
    )


# ---------------------------------------------------------------------------
# RECORD mode — GET
# ---------------------------------------------------------------------------


class TestRecordModeGet:
    async def test_record_captures_first_observation_only(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"applicationMetaData": {"patentNumber": "10000000"}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            first = await odp_client._get("/patent/applications/12345678")
            second = await odp_client._get("/patent/applications/12345678")

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 2
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "uspto_odp"' in lines[0]
        assert '"method": "GET"' in lines[0]

        await odp_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"applicationMetaData": {}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/patent/applications/1")
            await odp_client._get("/patent/applications/1")

        assert mock_get.call_count == 1

        await odp_client.close()

    async def test_different_paths_produce_different_cache_keys(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"x": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/patent/applications/1")
            await odp_client._get("/patent/applications/1")  # hit
            await odp_client._get("/patent/applications/2")  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await odp_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"x": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/path", params={"a": "1"})
            await odp_client._get("/path", params={"a": "1"})  # hit
            await odp_client._get("/path", params={"a": "2"})  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await odp_client.close()


# ---------------------------------------------------------------------------
# RECORD mode — POST
# ---------------------------------------------------------------------------


class TestRecordModePost:
    async def test_post_payload_keys_distinctly(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        body_a = {"q": "aspirin"}
        body_b = {"q": "ibuprofen"}
        with patch.object(odp_client._client, "post", mock_post):
            await odp_client._post("/patent/search", body_a)
            await odp_client._post("/patent/search", body_a)  # hit
            await odp_client._post("/patent/search", body_b)  # new

        assert mock_post.call_count == 2
        assert len(cache) == 2

        # Confirm POST entries are stored as "POST".
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert all('"method": "POST"' in line for line in lines)

        await odp_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(self, odp_client: USPTOODPClient, tmp_path: Path) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"applicationMetaData": {"patentNumber": "10000000"}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/patent/applications/123")

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(odp_client._client, "get", explode):
            result = await odp_client._get("/patent/applications/123")
        assert result == payload
        assert explode.call_count == 0

        await odp_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(odp_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await odp_client._get("/patent/applications/missing")
        expected_key = compute_request_key(
            source="uspto_odp",
            method="GET",
            url="/patent/applications/missing",
            body=None,
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await odp_client.close()


# ---------------------------------------------------------------------------
# Passthrough — no cache / DISABLED
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, odp_client: USPTOODPClient) -> None:
        payload = {"x": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/path")
            await odp_client._get("/path")
        assert mock_get.call_count == 2

        await odp_client.close()

    async def test_disabled_mode_pure_passthrough_no_disk_writes(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"x": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(odp_client._client, "get", mock_get):
            await odp_client._get("/path")
            await odp_client._get("/path")
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await odp_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed live calls must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_auth_error_is_not_recorded(
        self, odp_client: USPTOODPClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(odp_client._client, "get", mock_get):
            with pytest.raises(AuthenticationError):
                await odp_client._get("/path")

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await odp_client.close()

    async def test_404_records_empty_dict(self, odp_client: USPTOODPClient, tmp_path: Path) -> None:
        """ODP _get returns ``{}`` on 404 (no application found) — that empty
        result is a legitimate semantic answer and must be recorded so replay
        matches it without hitting the network."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(odp_client._client, "get", mock_get):
            result = await odp_client._get("/patent/applications/missing")
        assert result == {}
        assert len(cache) == 1

        await odp_client.close()

    async def test_compute_request_key_folds_params_into_body(self) -> None:
        params = {"a": "1"}
        body = json.dumps(params, sort_keys=True)
        k1 = compute_request_key(source="uspto_odp", method="GET", url="/path", body=body)
        k2 = compute_request_key(source="uspto_odp", method="GET", url="/path", body=None)
        assert k1 != k2
