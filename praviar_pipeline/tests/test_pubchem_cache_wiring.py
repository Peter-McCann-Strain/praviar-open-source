"""Wiring tests: PubChem client ↔ ResponseCache.

Covers the handshake between ``PubChemClient._get`` / ``_sdq_get`` and the
module-level ``ResponseCache`` singleton. The client implementation owns
the decision to consult the cache; these tests pin the behaviour end to
end: record, replay, miss, default passthrough, and error propagation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from tenacity import wait_none

from praviar_pipeline.clients.pubchem import PubChemClient
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
def pubchem_client(mock_settings) -> PubChemClient:
    """Fresh PubChemClient with default settings."""
    return PubChemClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    """Ensure the module-level cache is clean before and after each test."""
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://pubchem.ncbi.nlm.nih.gov/rest/pug/test"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_get_records_response_once_on_repeated_calls(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        """In pure RECORD mode, live calls still happen every time (we want to
        surface nondeterminism), but the JSONL only captures the first
        observation. See ``test_record_mode_dedupes_identical_calls`` for the
        cache-level pin of this contract."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"hello": "world"}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubchem_client._client, "get", mock_get):
            first = await pubchem_client._get("/compound/name/aspirin/cids/JSON")
            second = await pubchem_client._get("/compound/name/aspirin/cids/JSON")

        assert first == payload
        assert second == payload
        # JSONL has exactly one line for this request (dedup on write).
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "pubchem"' in lines[0]

        await pubchem_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        """REPLAY_THEN_RECORD: first call is live + recorded; second is a hit."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"hello": "world"}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubchem_client._client, "get", mock_get):
            first = await pubchem_client._get("/compound/name/aspirin/cids/JSON")
            second = await pubchem_client._get("/compound/name/aspirin/cids/JSON")

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 1  # second call served from cache

        await pubchem_client.close()

    async def test_sdq_get_records_keyed_by_query_body(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        """Different SDQ queries produce distinct cache entries (body hash)."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"SDQOutputSet": [{"rows": []}]}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubchem_client._client, "get", mock_get):
            q1 = {"collection": "patent", "where": {"ands": [{"cid": "111"}]}}
            q2 = {"collection": "patent", "where": {"ands": [{"cid": "222"}]}}
            await pubchem_client._sdq_get(q1)
            await pubchem_client._sdq_get(q1)  # cache hit
            await pubchem_client._sdq_get(q2)  # distinct — live call

        assert mock_get.call_count == 2  # q1 once, q2 once
        assert len(cache) == 2

        await pubchem_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_returns_cached_response_without_httpx(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        # Pre-populate the cache on disk using RECORD mode.
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"cid": 2244}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubchem_client._client, "get", mock_get):
            await pubchem_client._get("/compound/name/aspirin/cids/JSON")
        assert mock_get.call_count == 1

        # Now open a fresh replay cache from the same dir.
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(pubchem_client._client, "get", explode):
            result = await pubchem_client._get("/compound/name/aspirin/cids/JSON")
        assert result == payload
        assert explode.call_count == 0

        await pubchem_client.close()

    async def test_replay_miss_raises_cache_miss_error_without_httpx(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(pubchem_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await pubchem_client._get("/compound/name/missing/cids/JSON")
        expected_key = compute_request_key(
            source="pubchem",
            method="GET",
            url="/compound/name/missing/cids/JSON",
            body=None,
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await pubchem_client.close()


# ---------------------------------------------------------------------------
# No cache installed (default production behaviour)
# ---------------------------------------------------------------------------


class TestNoCacheInstalled:
    async def test_get_hits_httpx_every_time(self, pubchem_client: PubChemClient) -> None:
        # Sanity: no cache installed (autouse fixture guarantees this).
        payload = {"x": 1}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubchem_client._client, "get", mock_get):
            await pubchem_client._get("/path")
            await pubchem_client._get("/path")
            await pubchem_client._get("/path")
        assert mock_get.call_count == 3

        await pubchem_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed live calls must NOT be recorded
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_error_propagates_and_is_not_cached(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        """A 404 without ``ok_on_404`` raises :class:`SourceUnavailableError`
        without retrying a permanent response. The cache MUST NOT record the failure.
        """
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        # The decorator owns an already-instantiated retry controller, so
        # patch its wait policy rather than the factory used at import time.
        with patch.object(PubChemClient._get_uncached.retry, "wait", wait_none()):
            mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
            with patch.object(pubchem_client._client, "get", mock_get):
                with pytest.raises(SourceUnavailableError):
                    await pubchem_client._get("/compound/name/boom/cids/JSON")
        mock_get.assert_awaited_once()

        # Nothing recorded — cache captures successes only.
        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await pubchem_client.close()

    async def test_transient_server_error_retries_only_three_times(
        self, pubchem_client: PubChemClient
    ) -> None:
        mock_get = AsyncMock(return_value=_fake_response({}, status_code=503))
        with (
            patch.object(PubChemClient._get_uncached.retry, "wait", wait_none()),
            patch.object(pubchem_client._client, "get", mock_get),
            pytest.raises(SourceUnavailableError),
        ):
            await pubchem_client._get("/compound/name/busy/cids/JSON")

        assert mock_get.await_count == 3
        await pubchem_client.close()

    async def test_ok_on_404_survives_wrapping_and_records_empty_dict(
        self, pubchem_client: PubChemClient, tmp_path: Path
    ) -> None:
        """``ok_on_404=True`` returns ``{}`` as a legitimate semantic empty.
        That IS a successful call — it must be recorded so replay matches."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(pubchem_client._client, "get", mock_get):
            result = await pubchem_client._get("/compound/name/x/cids/JSON", ok_on_404=True)
        assert result == {}
        assert len(cache) == 1

        await pubchem_client.close()
