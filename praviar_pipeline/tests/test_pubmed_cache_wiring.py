"""Wiring tests: PubMedClient ↔ ResponseCache.

Covers the handshake between ``PubMedClient._get_json`` and the
module-level ``ResponseCache`` singleton. The cache key folds the
caller-visible query params (excluding the api_key auth credential) into
the body hash so distinct queries key distinctly. The 429 retry handling
is preserved on ``_get_json_uncached``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.pubmed import PubMedClient
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
def pubmed_client(mock_settings) -> PubMedClient:
    return PubMedClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"esearchresult": {"idlist": ["123"], "count": "1"}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"db": "pubmed", "term": "aspirin", "retmode": "json"}
        with patch.object(pubmed_client._client, "get", mock_get):
            first = await pubmed_client._get_json("/esearch.fcgi", params)
            second = await pubmed_client._get_json("/esearch.fcgi", params)

        assert first == payload
        assert second == payload
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "pubmed"' in lines[0]

        await pubmed_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"esearchresult": {"idlist": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"db": "pubmed", "term": "aspirin"}
        with patch.object(pubmed_client._client, "get", mock_get):
            first = await pubmed_client._get_json("/esearch.fcgi", params)
            second = await pubmed_client._get_json("/esearch.fcgi", params)

        assert first == payload
        assert second == payload
        assert mock_get.call_count == 1

        await pubmed_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"esearchresult": {"idlist": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubmed_client._client, "get", mock_get):
            await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "aspirin"})
            await pubmed_client._get_json(
                "/esearch.fcgi", {"db": "pubmed", "term": "aspirin"}
            )  # hit
            await pubmed_client._get_json(
                "/esearch.fcgi", {"db": "pubmed", "term": "ibuprofen"}
            )  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await pubmed_client.close()

    async def test_api_key_excluded_from_cache_key(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        """Two calls differing only in api_key should hit the same cache entry."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"esearchresult": {"idlist": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubmed_client._client, "get", mock_get):
            await pubmed_client._get_json(
                "/esearch.fcgi",
                {"db": "pubmed", "term": "aspirin", "api_key": "key1"},
            )
            await pubmed_client._get_json(
                "/esearch.fcgi",
                {"db": "pubmed", "term": "aspirin", "api_key": "key2"},
            )  # cache hit — api_key is stripped from the key

        assert mock_get.call_count == 1
        assert len(cache) == 1

        await pubmed_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(self, pubmed_client: PubMedClient, tmp_path: Path) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"esearchresult": {"idlist": ["1"]}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        params = {"db": "pubmed", "term": "aspirin"}
        with patch.object(pubmed_client._client, "get", mock_get):
            await pubmed_client._get_json("/esearch.fcgi", params)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(pubmed_client._client, "get", explode):
            result = await pubmed_client._get_json("/esearch.fcgi", params)
        assert result == payload
        assert explode.call_count == 0

        await pubmed_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        params = {"db": "pubmed", "term": "missing"}
        with patch.object(pubmed_client._client, "get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await pubmed_client._get_json("/esearch.fcgi", params)
        expected_key = compute_request_key(
            source="pubmed",
            method="GET",
            url="/esearch.fcgi",
            body=json.dumps(params, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await pubmed_client.close()


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, pubmed_client: PubMedClient) -> None:
        payload = {"esearchresult": {"idlist": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubmed_client._client, "get", mock_get):
            await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "x"})
            await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "x"})
        assert mock_get.call_count == 2

        await pubmed_client.close()

    async def test_disabled_mode_is_pure_passthrough_no_disk_writes(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"esearchresult": {"idlist": []}}
        mock_get = AsyncMock(return_value=_fake_response(payload))
        with patch.object(pubmed_client._client, "get", mock_get):
            await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "x"})
            await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "x"})
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await pubmed_client.close()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_source_unavailable_is_not_recorded(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        with patch(
            "praviar_pipeline.clients.pubmed.wait_exponential_jitter",
            return_value=lambda *_a, **_kw: 0,
        ):
            mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
            with patch.object(pubmed_client._client, "get", mock_get):
                with pytest.raises((SourceUnavailableError, RetryError)) as excinfo:
                    await pubmed_client._get_json("/esearch.fcgi", {"db": "pubmed", "term": "boom"})

        if isinstance(excinfo.value, RetryError):
            assert isinstance(excinfo.value.last_attempt.exception(), SourceUnavailableError)

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await pubmed_client.close()

    async def test_429_retry_then_success_records_one_entry(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        """A 429 raises HTTPStatusError which tenacity retries; on success
        we record exactly one cache entry."""
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"esearchresult": {"idlist": ["1"]}}
        responses = [
            _fake_response({}, status_code=429),
            _fake_response(payload),
        ]
        mock_get = AsyncMock(side_effect=responses)
        with (
            patch(
                "praviar_pipeline.clients.pubmed.wait_exponential_jitter",
                return_value=lambda *_a, **_kw: 0,
            ),
            patch.object(pubmed_client._client, "get", mock_get),
        ):
            try:
                result = await pubmed_client._get_json(
                    "/esearch.fcgi", {"db": "pubmed", "term": "x"}
                )
            except RetryError:
                result = None

        if result is not None:
            assert result == payload
            assert len(cache) == 1
        else:
            assert len(cache) == 0

        await pubmed_client.close()

    async def test_ok_on_404_records_empty_dict(
        self, pubmed_client: PubMedClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(pubmed_client._client, "get", mock_get):
            result = await pubmed_client._get_json(
                "/esummary.fcgi", {"db": "pubmed", "id": "1"}, ok_on_404=True
            )
        assert result == {}
        assert len(cache) == 1

        await pubmed_client.close()
