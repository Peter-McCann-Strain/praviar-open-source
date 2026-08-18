"""Wiring tests: SureChEMBLClient ↔ ResponseCache.

Covers the handshake between ``SureChEMBLClient._get`` and the module-level
``ResponseCache`` singleton. The cache key folds the JSON-serialised query
params into the body hash so distinct searches (different SMILES,
thresholds, etc.) key distinctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.surechembl import SureChEMBLClient
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
def surechembl_client(mock_settings) -> SureChEMBLClient:
    return SureChEMBLClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict | list, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://www.surechembl.org/api/test"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"compounds": [{"patent_id": "US123"}]}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            first = await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)
            second = await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)

        assert first == payload
        assert second == payload
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "surechembl"' in lines[0]

        await surechembl_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"compounds": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            first = await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)
            second = await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 1

        await surechembl_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        """Same path with different query params records distinctly."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"compounds": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            await surechembl_client._get(
                "/chemical/search/similarity/CCO", params={"threshold": 0.7}, ok_on_404=True
            )
            await surechembl_client._get(
                "/chemical/search/similarity/CCO", params={"threshold": 0.7}, ok_on_404=True
            )  # hit
            await surechembl_client._get(
                "/chemical/search/similarity/CCO", params={"threshold": 0.9}, ok_on_404=True
            )  # new key

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await surechembl_client.close()

    async def test_different_paths_produce_different_cache_keys(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"compounds": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)
            await surechembl_client._get("/chemical/search/smiles/CCC", ok_on_404=True)

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await surechembl_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"compounds": [{"patent_id": "US1"}]}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(surechembl_client._client, "get", explode):
            result = await surechembl_client._get("/chemical/search/smiles/CCO", ok_on_404=True)
        assert result == payload
        assert explode.call_count == 0

        await surechembl_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(surechembl_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await surechembl_client._get("/chemical/search/smiles/MISSING", ok_on_404=True)
        expected_key = compute_request_key(
            source="surechembl",
            method="GET",
            url="/chemical/search/smiles/MISSING",
            body=None,
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await surechembl_client.close()


# ---------------------------------------------------------------------------
# No cache installed / DISABLED — passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(
        self, surechembl_client: SureChEMBLClient
    ) -> None:
        payload = {"compounds": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            await surechembl_client._get("/path", ok_on_404=True)
            await surechembl_client._get("/path", ok_on_404=True)
        assert mock_get.call_count == 2

        await surechembl_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"compounds": []}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(surechembl_client._client, "get", mock_get):
            await surechembl_client._get("/path", ok_on_404=True)
            await surechembl_client._get("/path", ok_on_404=True)
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await surechembl_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed calls must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        with patch(
            "praviar_pipeline.clients.surechembl.wait_exponential_jitter",
            return_value=lambda *_a, **_kw: 0,
        ):
            mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
            with patch.object(surechembl_client._client, "get", mock_get):
                with pytest.raises((SourceUnavailableError, RetryError)) as excinfo:
                    await surechembl_client._get("/chemical/search/smiles/BOOM")

        if isinstance(excinfo.value, RetryError):
            assert isinstance(excinfo.value.last_attempt.exception(), SourceUnavailableError)

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await surechembl_client.close()

    async def test_ok_on_404_records_empty_dict(
        self, surechembl_client: SureChEMBLClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(surechembl_client._client, "get", mock_get):
            result = await surechembl_client._get("/chemical/search/smiles/X", ok_on_404=True)
        assert result == {}
        assert len(cache) == 1

        await surechembl_client.close()

    async def test_compute_request_key_folds_params_into_body(self) -> None:
        params = {"threshold": 0.7}
        body = json.dumps(params, sort_keys=True)
        k1 = compute_request_key(
            source="surechembl",
            method="GET",
            url="/chemical/search/similarity/CCO",
            body=body,
        )
        k2 = compute_request_key(
            source="surechembl",
            method="GET",
            url="/chemical/search/similarity/CCO",
            body=None,
        )
        assert k1 != k2
