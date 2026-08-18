"""Wiring tests: PatCIDClient ↔ ResponseCache.

PatCID hits a local SQLite index rather than the network, but it IS a data
source and benefits from the same record/replay contract as the HTTP-based
clients — replays no longer require the 5.7 GB local database to be present.

Cache key uses ``method="QUERY"`` and the InChIKey (or InChIKey prefix) as
the URL.

These tests stub the uncached SQLite helpers (rather than wiring up a real
SQLite database) because PatCID's connection is created on one thread but
its queries run inside ``asyncio.to_thread``, which trips SQLite's default
``check_same_thread`` check during pytest. The mock pattern mirrors how the
HTTP clients patch ``_client.get`` instead of standing up a real server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.clients.patcid import PatCIDClient
from praviar_pipeline.errors import PatCIDDatabaseNotFoundError
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
def patcid_client(tmp_path: Path) -> PatCIDClient:
    # The DB path can be missing — every test stubs the uncached helpers
    # so the database is never actually consulted.
    return PatCIDClient(db_path=tmp_path / "patcid.db")


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


class TestRecordMode:
    async def test_record_persists_first_call_dedupes_second(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.RECORD)
        set_current_cache(cache)

        mock_lookup = AsyncMock(return_value=["US1234567", "EP9876543"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            first = await patcid_client.lookup_by_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
            second = await patcid_client.lookup_by_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")

        assert first == ["US1234567", "EP9876543"]
        assert second == first
        # RECORD always calls through; JSONL dedups on key.
        assert mock_lookup.call_count == 2
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "patcid"' in lines[0]
        assert '"method": "QUERY"' in lines[0]

        await patcid_client.close()

    async def test_replay_then_record_serves_second_call_from_cache(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        mock_lookup = AsyncMock(return_value=["US1"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            await patcid_client.lookup_by_inchikey("KEY-A")
            await patcid_client.lookup_by_inchikey("KEY-A")
        assert mock_lookup.call_count == 1

        await patcid_client.close()

    async def test_different_inchikeys_produce_different_cache_keys(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        mock_lookup = AsyncMock(side_effect=lambda k: [f"PAT-{k}"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            await patcid_client.lookup_by_inchikey("KEY-A")
            await patcid_client.lookup_by_inchikey("KEY-A")  # hit
            await patcid_client.lookup_by_inchikey("KEY-B")  # new

        assert mock_lookup.call_count == 2
        assert len(cache) == 2

        await patcid_client.close()

    async def test_inchikey_and_prefix_lookups_are_distinct_entries(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        """Same string used as full key vs prefix must record distinctly."""
        cache = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        mock_full = AsyncMock(return_value=["FULL"])
        mock_prefix = AsyncMock(return_value=[{"inchikey": "X", "patent_id": "PRE"}])
        with (
            patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_full),
            patch.object(patcid_client, "_lookup_by_inchikey_prefix_uncached", mock_prefix),
        ):
            await patcid_client.lookup_by_inchikey("BSYNRYMUTXBXSQ")
            await patcid_client.lookup_by_inchikey_prefix("BSYNRYMUTXBXSQ")

        assert len(cache) == 2

        await patcid_client.close()


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


class TestReplayMode:
    async def test_replay_hit_skips_database(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        rec = ResponseCache(cache_dir=cache_dir, mode=CacheMode.RECORD)
        set_current_cache(rec)
        mock_lookup = AsyncMock(return_value=["US1234567"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            await patcid_client.lookup_by_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
        assert mock_lookup.call_count == 1

        # Reopen with a fresh client whose DB doesn't exist — replay must still work.
        replayed = PatCIDClient(db_path=tmp_path / "no_such.db")
        rep = ResponseCache(cache_dir=cache_dir, mode=CacheMode.REPLAY)
        set_current_cache(rep)

        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(replayed, "_lookup_by_inchikey_uncached", explode):
            result = await replayed.lookup_by_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
        assert result == ["US1234567"]
        assert explode.call_count == 0

        await replayed.close()

    async def test_replay_miss_raises_cache_miss_error(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.REPLAY)
        set_current_cache(rep)

        explode = AsyncMock(side_effect=AssertionError("live call in replay mode"))
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", explode):
            with pytest.raises(CacheMissError) as excinfo:
                await patcid_client.lookup_by_inchikey("MISSINGKEY")
        expected_key = compute_request_key(
            source="patcid",
            method="QUERY",
            url="inchikey=MISSINGKEY",
            body=None,
        )
        assert excinfo.value.key == expected_key
        assert explode.call_count == 0

        await patcid_client.close()


# ---------------------------------------------------------------------------
# Passthrough — no cache / DISABLED
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_no_cache_calls_database_every_time(self, patcid_client: PatCIDClient) -> None:
        mock_lookup = AsyncMock(return_value=["US1"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            await patcid_client.lookup_by_inchikey("KEY")
            await patcid_client.lookup_by_inchikey("KEY")
        assert mock_lookup.call_count == 2

        await patcid_client.close()

    async def test_disabled_mode_pure_passthrough_no_disk_writes(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        cache = ResponseCache(cache_dir=cache_dir, mode=CacheMode.DISABLED)
        set_current_cache(cache)
        mock_lookup = AsyncMock(return_value=["US1"])
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", mock_lookup):
            await patcid_client.lookup_by_inchikey("KEY")
            await patcid_client.lookup_by_inchikey("KEY")
        assert mock_lookup.call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

        await patcid_client.close()


# ---------------------------------------------------------------------------
# Error propagation — DB errors must NOT be cached
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    async def test_db_not_found_is_not_cached(
        self, patcid_client: PatCIDClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.RECORD)
        set_current_cache(cache)

        boom = AsyncMock(side_effect=PatCIDDatabaseNotFoundError(str(tmp_path / "x.db")))
        with patch.object(patcid_client, "_lookup_by_inchikey_uncached", boom):
            with pytest.raises(PatCIDDatabaseNotFoundError):
                await patcid_client.lookup_by_inchikey("KEY")

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

        await patcid_client.close()
