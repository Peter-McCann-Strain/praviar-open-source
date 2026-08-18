"""Wiring tests: KIPRISClient ↔ ResponseCache.

Covers the handshake between ``KIPRISClient._get_and_parse`` and the
module-level ``ResponseCache`` singleton. Caching wraps the parsed list
(not the raw XML text), so XML parse errors raised by ``_parse_items``
propagate as ``SourceUnavailableError`` and never get recorded.

The cache key folds the JSON-serialised query params (minus ``ServiceKey``)
into the body hash so distinct searches key distinctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.clients.kipris import KIPRISClient
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

SAMPLE_XML_ASPIRIN = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <body>
    <items>
      <item>
        <applicationNumber>1020200000001</applicationNumber>
        <inventionTitle>Aspirin formulation</inventionTitle>
        <astrtCont>An aspirin formulation.</astrtCont>
        <applicationDate>20200101</applicationDate>
        <applicantName>Bayer KR</applicantName>
        <cpcNumber>A61K9/00</cpcNumber>
      </item>
    </items>
  </body>
</response>
"""

SAMPLE_XML_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<response><body><items/></body></response>
"""


@pytest.fixture
def kipris_client(monkeypatch, mock_settings) -> KIPRISClient:
    monkeypatch.setenv("KIPRIS_API_KEY", "test-kipris-key")
    client = KIPRISClient()
    client._api_key = "test-kipris-key"
    return client


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


def _params_for(word: str) -> dict[str, str]:
    return {"word": word, "numOfRows": "10", "pageNo": "1"}


def _expected_body(params: dict[str, str]) -> str:
    keyed = {k: v for k, v in params.items() if k != "ServiceKey"}
    return json.dumps(keyed, sort_keys=True)


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_captures_first_observation_only(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=SAMPLE_XML_ASPIRIN)
        params = _params_for("aspirin")
        with patch.object(kipris_client, "_get", mock_get):
            first = await kipris_client._get_and_parse("/search", dict(params))
            second = await kipris_client._get_and_parse("/search", dict(params))

        assert isinstance(first, list)
        assert first == second
        assert len(first) == 1
        # RECORD always calls through, JSONL dedups on key.
        assert mock_get.call_count == 2
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "kipris"' in lines[0]

        await kipris_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=SAMPLE_XML_EMPTY)
        params = _params_for("foo")
        with patch.object(kipris_client, "_get", mock_get):
            await kipris_client._get_and_parse("/search", dict(params))
            await kipris_client._get_and_parse("/search", dict(params))

        assert mock_get.call_count == 1

        await kipris_client.close()

    async def test_different_params_produce_different_cache_keys(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value=SAMPLE_XML_EMPTY)
        with patch.object(kipris_client, "_get", mock_get):
            await kipris_client._get_and_parse("/search", _params_for("a"))
            await kipris_client._get_and_parse("/search", _params_for("a"))  # hit
            await kipris_client._get_and_parse("/search", _params_for("b"))  # new

        assert mock_get.call_count == 2
        assert len(cache) == 2

        await kipris_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_get(self, kipris_client: KIPRISClient, tmp_path: Path) -> None:
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        mock_get = AsyncMock(return_value=SAMPLE_XML_ASPIRIN)
        params = _params_for("aspirin")
        with patch.object(kipris_client, "_get", mock_get):
            await kipris_client._get_and_parse("/search", dict(params))

        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(kipris_client, "_get", explode):
            result = await kipris_client._get_and_parse("/search", dict(params))
        assert isinstance(result, list)
        assert result[0]["publication_number"] == "KR1020200000001"
        assert explode.call_count == 0

        await kipris_client.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)
        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        params = _params_for("missing")
        with patch.object(kipris_client, "_get", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await kipris_client._get_and_parse("/search", dict(params))
        expected_key = compute_request_key(
            source="kipris",
            method="GET",
            url="/search",
            body=_expected_body(params),
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await kipris_client.close()


# ---------------------------------------------------------------------------
# Passthrough — no cache / DISABLED
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_get_every_time(self, kipris_client: KIPRISClient) -> None:
        mock_get = AsyncMock(return_value=SAMPLE_XML_EMPTY)
        with patch.object(kipris_client, "_get", mock_get):
            await kipris_client._get_and_parse("/search", _params_for("a"))
            await kipris_client._get_and_parse("/search", _params_for("a"))
        assert mock_get.call_count == 2

        await kipris_client.close()

    async def test_disabled_mode_pure_passthrough_no_disk_writes(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        mock_get = AsyncMock(return_value=SAMPLE_XML_EMPTY)
        with patch.object(kipris_client, "_get", mock_get):
            await kipris_client._get_and_parse("/search", _params_for("a"))
            await kipris_client._get_and_parse("/search", _params_for("a"))
        assert mock_get.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await kipris_client.close()


# ---------------------------------------------------------------------------
# Error propagation — XML parse errors must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_xml_parse_error_is_not_recorded(
        self, kipris_client: KIPRISClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_get = AsyncMock(return_value="<<<not valid xml>>>")
        with patch.object(kipris_client, "_get", mock_get):
            with pytest.raises(SourceUnavailableError):
                await kipris_client._get_and_parse("/search", _params_for("boom"))

        # Parse failure was an exception, so cache must hold nothing.
        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await kipris_client.close()
