"""Wiring tests: PatentsViewClient ↔ ResponseCache.

Covers the handshake between ``PatentsViewClient._request`` and the
module-level ``ResponseCache`` singleton. The cache key folds the request
params/json body into the body hash so distinct queries to the same path
key distinctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.patentsview import PatentsViewClient
from praviar_pipeline.errors import SourceUnavailableError
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
def patentsview_client(mock_settings) -> PatentsViewClient:
    return PatentsViewClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://search.patentsview.org/api/v1/patent/"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"patents": [{"patent_id": "US123"}]}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        params = {"q": '{"patent_id":"US123"}', "f": "[]", "s": "[]", "o": "{}"}
        with patch.object(patentsview_client._client, "request", mock_request):
            first = await patentsview_client._request("GET", "/patent/", params=params)
            second = await patentsview_client._request("GET", "/patent/", params=params)

        assert first == payload
        assert second == payload
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "patentsview"' in lines[0]

        await patentsview_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"patents": []}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        params = {"q": "x"}
        with patch.object(patentsview_client._client, "request", mock_request):
            first = await patentsview_client._request("GET", "/patent/", params=params)
            second = await patentsview_client._request("GET", "/patent/", params=params)

        assert first == payload
        assert second == payload
        assert mock_request.call_count == 1

        await patentsview_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"patents": []}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentsview_client._client, "request", mock_request):
            await patentsview_client._request("GET", "/patent/", params={"q": "aspirin"})
            await patentsview_client._request("GET", "/patent/", params={"q": "aspirin"})  # hit
            await patentsview_client._request("GET", "/patent/", params={"q": "ibuprofen"})  # new

        assert mock_request.call_count == 2
        assert len(cache) == 2

        await patentsview_client.close()

    async def test_different_paths_produce_different_cache_keys(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"patents": []}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentsview_client._client, "request", mock_request):
            await patentsview_client._request("GET", "/patent/", params={"q": "x"})
            await patentsview_client._request("GET", "/g_claims/", params={"q": "x"})

        assert mock_request.call_count == 2
        assert len(cache) == 2

        await patentsview_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"patents": [{"patent_id": "US1"}]}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        params = {"q": "aspirin"}
        with patch.object(patentsview_client._client, "request", mock_request):
            await patentsview_client._request("GET", "/patent/", params=params)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(patentsview_client._client, "request", explode):
            result = await patentsview_client._request("GET", "/patent/", params=params)
        assert result == payload
        assert explode.call_count == 0

        await patentsview_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(patentsview_client._client, "request", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await patentsview_client._request("GET", "/patent/", params={"q": "missing"})
        expected_key = compute_request_key(
            source="patentsview",
            method="GET",
            url="/patent/",
            body=json.dumps({"params": {"q": "missing"}}, sort_keys=True, default=str),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await patentsview_client.close()


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(
        self, patentsview_client: PatentsViewClient
    ) -> None:
        payload = {"patents": []}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentsview_client._client, "request", mock_request):
            await patentsview_client._request("GET", "/patent/", params={"q": "x"})
            await patentsview_client._request("GET", "/patent/", params={"q": "x"})
        assert mock_request.call_count == 2

        await patentsview_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"patents": []}
        mock_request = AsyncMock(return_value=_fake_response(payload))
        with patch.object(patentsview_client._client, "request", mock_request):
            await patentsview_client._request("GET", "/patent/", params={"q": "x"})
            await patentsview_client._request("GET", "/patent/", params={"q": "x"})
        assert mock_request.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await patentsview_client.close()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        # SourceUnavailableError is in retry_if_not_exception_type so it
        # propagates on the first attempt.
        mock_request = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(patentsview_client._client, "request", mock_request):
            with pytest.raises(SourceUnavailableError):
                await patentsview_client._request("GET", "/patent/", params={"q": "boom"})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await patentsview_client.close()

    async def test_ok_on_404_records_empty_dict(
        self, patentsview_client: PatentsViewClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_request = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(patentsview_client._client, "request", mock_request):
            result = await patentsview_client._request(
                "GET", "/patent/", params={"q": "x"}, ok_on_404=True
            )
        assert result == {}
        assert len(cache) == 1

        await patentsview_client.close()
