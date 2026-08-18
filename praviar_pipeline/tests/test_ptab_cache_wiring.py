"""Wiring tests: PTABClient ↔ ResponseCache.

PTAB is a POST-based search API (proceedings/decisions). The cache key folds
the JSON-serialised payload into the body hash so distinct queries (different
patent numbers, different proceedings) record distinctly even though they
share a path.

PTAB defaults to ``ok_on_404=True`` because most patents have no PTAB
proceeding — that "no proceeding" answer is a legitimate empty result that
must be recorded as ``{}`` so replays don't keep hitting the network.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.clients.ptab import PTABClient
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
def ptab_client(mock_settings) -> PTABClient:
    return PTABClient()


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _fake_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request(
            "POST", "https://api.uspto.gov/api/v1/patent/trials/proceedings/search"
        ),
    )


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        payload = {"results": [{"trialNumber": "IPR2020-00001"}]}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": "7851188"}
        with patch.object(ptab_client._client, "post", mock_post):
            first = await ptab_client._post_search("/proceedings/search", query)
            second = await ptab_client._post_search("/proceedings/search", query)

        assert first == payload
        assert second == payload
        assert mock_post.call_count == 2  # RECORD always calls through
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "ptab"' in lines[0]
        assert '"method": "POST"' in lines[0]

        await ptab_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": "7851188"}
        with patch.object(ptab_client._client, "post", mock_post):
            await ptab_client._post_search("/proceedings/search", query)
            await ptab_client._post_search("/proceedings/search", query)

        assert mock_post.call_count == 1

        await ptab_client.close()

    async def test_different_payloads_produce_different_cache_keys(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        payload = {"results": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        with patch.object(ptab_client._client, "post", mock_post):
            await ptab_client._post_search("/proceedings/search", {"query": "111"})
            await ptab_client._post_search("/proceedings/search", {"query": "111"})  # hit
            await ptab_client._post_search("/proceedings/search", {"query": "222"})  # new

        assert mock_post.call_count == 2
        assert len(cache) == 2

        await ptab_client.close()

    async def test_ok_on_404_records_empty_dict(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        """Most patents have no PTAB proceeding — the 404→{} answer must be cached."""
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_post = AsyncMock(return_value=_fake_response({}, status_code=404))
        with patch.object(ptab_client._client, "post", mock_post):
            result = await ptab_client._post_search("/proceedings/search", {"query": "x"})
        assert result == {}
        assert len(cache) == 1

        await ptab_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_http(self, ptab_client: PTABClient, tmp_path: Path) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = {"results": [{"trialNumber": "IPR2020-00001"}]}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        query = {"query": "7851188"}
        with patch.object(ptab_client._client, "post", mock_post):
            await ptab_client._post_search("/proceedings/search", query)

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(ptab_client._client, "post", explode):
            result = await ptab_client._post_search("/proceedings/search", query)
        assert result == payload
        assert explode.call_count == 0

        await ptab_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        query = {"query": "missing"}
        with patch.object(ptab_client._client, "post", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await ptab_client._post_search("/proceedings/search", query)
        expected_key = compute_request_key(
            source="ptab",
            method="POST",
            url="/proceedings/search",
            body=json.dumps(query, sort_keys=True),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await ptab_client.close()


# ---------------------------------------------------------------------------
# Passthrough — no cache / DISABLED
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_http_every_time(self, ptab_client: PTABClient) -> None:
        payload = {"results": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        with patch.object(ptab_client._client, "post", mock_post):
            await ptab_client._post_search("/proceedings/search", {"query": "x"})
            await ptab_client._post_search("/proceedings/search", {"query": "x"})
        assert mock_post.call_count == 2

        await ptab_client.close()

    async def test_disabled_mode_pure_passthrough_no_disk_writes(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        payload = {"results": []}
        mock_post = AsyncMock(return_value=_fake_response(payload))
        with patch.object(ptab_client._client, "post", mock_post):
            await ptab_client._post_search("/proceedings/search", {"query": "x"})
            await ptab_client._post_search("/proceedings/search", {"query": "x"})
        assert mock_post.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await ptab_client.close()


# ---------------------------------------------------------------------------
# Error propagation — failed live calls must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_auth_error_is_not_recorded(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_post = AsyncMock(return_value=_fake_response({}, status_code=401))
        with patch.object(ptab_client._client, "post", mock_post):
            with pytest.raises(AuthenticationError):
                await ptab_client._post_search("/proceedings/search", {"query": "x"})

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await ptab_client.close()

    async def test_source_unavailable_when_ok_on_404_disabled_is_not_cached(
        self, ptab_client: PTABClient, tmp_path: Path
    ) -> None:
        from tenacity import RetryError

        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        with patch(
            "praviar_pipeline.clients.ptab.wait_exponential_jitter",
            return_value=lambda *_a, **_kw: 0,
        ):
            mock_post = AsyncMock(return_value=_fake_response({}, status_code=404))
            with patch.object(ptab_client._client, "post", mock_post):
                with pytest.raises((SourceUnavailableError, RetryError)):
                    await ptab_client._post_search(
                        "/proceedings/search", {"query": "x"}, ok_on_404=False
                    )

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await ptab_client.close()
