"""Tests for the manifest-v2 response cache foundation."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import pytest

from praviar_pipeline.clients.base import cached_bytes_request
from praviar_pipeline.response_cache import (
    CacheEntry,
    CacheMissError,
    CacheMode,
    ResponseCache,
    compute_request_key,
    get_current_cache,
    set_current_cache,
)

# ---------------------------------------------------------------------------
# compute_request_key
# ---------------------------------------------------------------------------


def test_same_inputs_produce_same_key() -> None:
    a = compute_request_key(source="pubchem", method="GET", url="/cid/123", body=None)
    b = compute_request_key(source="pubchem", method="GET", url="/cid/123", body=None)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_method_case_normalised() -> None:
    upper = compute_request_key(source="s", method="GET", url="/x", body=None)
    lower = compute_request_key(source="s", method="get", url="/x", body=None)
    assert upper == lower


def test_different_source_produces_different_key() -> None:
    a = compute_request_key(source="pubchem", method="GET", url="/x", body=None)
    b = compute_request_key(source="lens", method="GET", url="/x", body=None)
    assert a != b


def test_different_body_produces_different_key() -> None:
    a = compute_request_key(source="x", method="POST", url="/q", body='{"a":1}')
    b = compute_request_key(source="x", method="POST", url="/q", body='{"a":2}')
    assert a != b


def test_body_bytes_and_str_equivalent() -> None:
    a = compute_request_key(source="x", method="POST", url="/q", body='{"a":1}')
    b = compute_request_key(source="x", method="POST", url="/q", body=b'{"a":1}')
    assert a == b


# ---------------------------------------------------------------------------
# RECORD mode
# ---------------------------------------------------------------------------


def test_record_mode_persists_to_jsonl(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)

    async def call() -> dict:
        return {"hello": "world"}

    result = asyncio.run(
        cache.wrap(
            source="pubchem",
            method="GET",
            url="/compound/aspirin",
            body=None,
            call=call,
        )
    )
    assert result == {"hello": "world"}
    assert cache.cache_path.exists()
    lines = cache.cache_path.read_text("utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"source": "pubchem"' in lines[0]
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(cache.cache_path.stat().st_mode) == 0o600


def test_record_mode_dedupes_identical_calls(tmp_path: Path) -> None:
    """A second call with the same key records only once."""
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    calls = 0

    async def call() -> int:
        nonlocal calls
        calls += 1
        return calls

    # Both results go through (RECORD always calls), but only the first
    # is persisted — so replay sees the first, not the last.
    r1 = asyncio.run(cache.wrap(source="s", method="GET", url="/x", body=None, call=call))
    r2 = asyncio.run(cache.wrap(source="s", method="GET", url="/x", body=None, call=call))
    assert r1 == 1
    assert r2 == 2  # live call still runs; only cache dedupes on write
    lines = cache.cache_path.read_text("utf-8").strip().splitlines()
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# REPLAY mode
# ---------------------------------------------------------------------------


def test_replay_returns_cached_response(tmp_path: Path) -> None:
    # First record.
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)

    async def live() -> dict:
        return {"cid": 2244}

    asyncio.run(rec.wrap(source="p", method="GET", url="/n/aspirin", body=None, call=live))

    # Now open a fresh cache in replay mode from the same directory.
    rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    assert len(rep) == 1

    async def should_not_be_called() -> dict:
        raise AssertionError("live call in replay mode")

    result = asyncio.run(
        rep.wrap(
            source="p",
            method="GET",
            url="/n/aspirin",
            body=None,
            call=should_not_be_called,
        )
    )
    assert result == {"cid": 2244}


def test_replay_raises_on_miss(tmp_path: Path) -> None:
    rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)

    async def live() -> dict:
        return {"never": "called"}

    with pytest.raises(CacheMissError) as excinfo:
        asyncio.run(rep.wrap(source="p", method="GET", url="/missing", body=None, call=live))
    assert "Cache miss" in str(excinfo.value)
    assert excinfo.value.cache_path == rep.cache_path


# ---------------------------------------------------------------------------
# REPLAY_THEN_RECORD mode
# ---------------------------------------------------------------------------


def test_replay_then_record_falls_through_on_miss(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)

    async def live() -> dict:
        return {"fresh": True}

    result = asyncio.run(cache.wrap(source="p", method="GET", url="/new", body=None, call=live))
    assert result == {"fresh": True}
    # The new response is persisted.
    assert len(cache) == 1

    # A second call hits the cache.
    async def should_not_be_called() -> dict:
        raise AssertionError("expected cache hit")

    result2 = asyncio.run(
        cache.wrap(
            source="p",
            method="GET",
            url="/new",
            body=None,
            call=should_not_be_called,
        )
    )
    assert result2 == {"fresh": True}


# ---------------------------------------------------------------------------
# DISABLED mode
# ---------------------------------------------------------------------------


def test_disabled_is_passthrough(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)

    async def live() -> str:
        return "always live"

    result = asyncio.run(cache.wrap(source="s", method="GET", url="/x", body=None, call=live))
    assert result == "always live"
    # No file written.
    assert not cache.cache_path.exists()


# ---------------------------------------------------------------------------
# Manifest integration
# ---------------------------------------------------------------------------


def test_digest_is_stable_across_insertion_order(tmp_path: Path) -> None:
    """Two caches with the same keys produce the same digest regardless of
    the order they were recorded in. This is what makes the digest safe to
    pin in the manifest for drift detection."""
    cache1 = ResponseCache(cache_dir=tmp_path / "a", mode=CacheMode.RECORD)
    cache2 = ResponseCache(cache_dir=tmp_path / "b", mode=CacheMode.RECORD)

    async def call_x() -> int:
        return 1

    async def call_y() -> int:
        return 2

    # cache1: x then y
    asyncio.run(cache1.wrap(source="s", method="GET", url="/x", body=None, call=call_x))
    asyncio.run(cache1.wrap(source="s", method="GET", url="/y", body=None, call=call_y))
    # cache2: y then x
    asyncio.run(cache2.wrap(source="s", method="GET", url="/y", body=None, call=call_y))
    asyncio.run(cache2.wrap(source="s", method="GET", url="/x", body=None, call=call_x))

    assert cache1.digest() == cache2.digest()


def test_digest_changes_when_a_key_changes(tmp_path: Path) -> None:
    cache1 = ResponseCache(cache_dir=tmp_path / "a", mode=CacheMode.RECORD)
    cache2 = ResponseCache(cache_dir=tmp_path / "b", mode=CacheMode.RECORD)

    async def call_() -> int:
        return 1

    asyncio.run(cache1.wrap(source="s", method="GET", url="/a", body=None, call=call_))
    asyncio.run(cache2.wrap(source="s", method="GET", url="/b", body=None, call=call_))
    assert cache1.digest() != cache2.digest()


def test_digest_changes_when_response_or_metadata_changes(tmp_path: Path) -> None:
    cache1 = ResponseCache(cache_dir=tmp_path / "a", mode=CacheMode.RECORD)
    cache2 = ResponseCache(cache_dir=tmp_path / "b", mode=CacheMode.RECORD)

    async def first() -> dict:
        return {"value": 1}

    async def second() -> dict:
        return {"value": 2}

    asyncio.run(
        cache1.wrap(source="s", method="GET", url="/same", body=None, call=first, meta={"v": 1})
    )
    asyncio.run(
        cache2.wrap(source="s", method="GET", url="/same", body=None, call=second, meta={"v": 2})
    )
    assert cache1.keys() == cache2.keys()
    assert cache1.digest() != cache2.digest()


def test_existing_cache_permissions_are_hardened(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o755)
    cache_file = cache_dir / ResponseCache.JSONL_FILENAME
    cache_file.write_text("", encoding="utf-8")
    cache_file.chmod(0o644)

    ResponseCache(cache_dir=cache_dir, mode=CacheMode.REPLAY)

    assert stat.S_IMODE(cache_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(cache_file.stat().st_mode) == 0o600


def test_nested_symlink_cache_path_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError, match="symlink"):
        ResponseCache(cache_dir=alias / "nested", mode=CacheMode.RECORD)


@pytest.mark.skipif(not os.path.islink("/tmp"), reason="platform /tmp is not a symlink alias")
def test_macos_tmp_platform_alias_is_accepted() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="praviar-private-") as directory:
        cache = ResponseCache(cache_dir=Path(directory) / "cache", mode=CacheMode.RECORD)
        assert stat.S_IMODE(cache.cache_path.parent.stat().st_mode) == 0o700


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


def test_current_cache_install_and_clear(tmp_path: Path) -> None:
    assert get_current_cache() is None
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)
    try:
        assert get_current_cache() is cache
    finally:
        set_current_cache(None)
    assert get_current_cache() is None


@pytest.mark.asyncio
async def test_current_cache_is_isolated_between_concurrent_runs(tmp_path: Path) -> None:
    ready = asyncio.Event()
    count = 0
    lock = asyncio.Lock()

    async def run(label: str) -> ResponseCache:
        nonlocal count
        cache = ResponseCache(cache_dir=tmp_path / label, mode=CacheMode.RECORD)
        set_current_cache(cache)
        async with lock:
            count += 1
            if count == 2:
                ready.set()
        await ready.wait()
        assert get_current_cache() is cache
        return cache

    first, second = await asyncio.gather(run("first"), run("second"))
    assert first is not second
    set_current_cache(None)


@pytest.mark.asyncio
async def test_authenticated_digest_detects_response_tampering(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    await cache.wrap(
        source="pubchem",
        method="GET",
        url="/compound/1",
        body=None,
        call=lambda: asyncio.sleep(0, result={"cid": 1}),
    )
    key = b"test-response-cache-audit-key-0001"
    first = cache.authenticated_digest(key=key)

    cache._entries[next(iter(cache._entries))].response = {"cid": 2}

    assert cache.authenticated_digest(key=key) != first
    assert get_current_cache() is None


# ---------------------------------------------------------------------------
# CacheEntry sanity
# ---------------------------------------------------------------------------


def test_cache_entry_defaults_are_independent() -> None:
    a = CacheEntry(key="k1", source="s", method="GET", url="/x", response={})
    b = CacheEntry(key="k2", source="s", method="GET", url="/y", response={})
    a.meta["x"] = 1
    assert b.meta == {}


@pytest.mark.asyncio
async def test_cached_bytes_request_records_and_replays_without_live_call(tmp_path: Path) -> None:
    record = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.RECORD)
    set_current_cache(record)
    try:
        first = await cached_bytes_request(
            source="paragraph_iv",
            method="GET",
            url="https://example.invalid/evidence.pdf",
            body=None,
            call=lambda: asyncio.sleep(0, result=b"exact-binary-evidence"),
        )
    finally:
        set_current_cache(None)

    replay = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.REPLAY)
    set_current_cache(replay)

    async def forbidden_live_call() -> bytes:
        raise AssertionError("exact replay reached live network")

    try:
        second = await cached_bytes_request(
            source="paragraph_iv",
            method="GET",
            url="https://example.invalid/evidence.pdf",
            body=None,
            call=forbidden_live_call,
        )
    finally:
        set_current_cache(None)

    assert first == second == b"exact-binary-evidence"
