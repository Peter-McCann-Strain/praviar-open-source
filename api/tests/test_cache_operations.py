"""Targeted tests for API cache misses, bounded pools, and fail-closed Redis errors."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aioredis

from api import cache

# ---------------------------------------------------------------------------
# get_redis
# ---------------------------------------------------------------------------


async def test_get_redis_builds_bounded_singleton_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = AsyncMock()
    from_url = MagicMock(return_value=fake_pool)
    settings = SimpleNamespace(
        redis_url="redis://cache.example:6379/0",
        redis_socket_connect_timeout_seconds=1.25,
        redis_socket_timeout_seconds=2.5,
        redis_health_check_interval_seconds=15,
    )

    monkeypatch.setattr(cache, "_redis_pool", None)
    monkeypatch.setattr(cache.aioredis, "from_url", from_url)
    monkeypatch.setattr(cache, "get_settings", lambda: settings)

    first = await cache.get_redis()
    second = await cache.get_redis()

    assert first is fake_pool
    assert second is fake_pool
    from_url.assert_called_once_with(
        "redis://cache.example:6379/0",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=1.25,
        socket_timeout=2.5,
        health_check_interval=15,
    )


async def test_get_chat_budget_redis_uses_dedicated_bounded_singleton_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pool = AsyncMock()
    from_url = MagicMock(return_value=fake_pool)
    settings = SimpleNamespace(
        chat_budget_redis_url="rediss://ledger.example:6380/0",
        redis_socket_connect_timeout_seconds=1.25,
        redis_socket_timeout_seconds=2.5,
        redis_health_check_interval_seconds=15,
    )

    monkeypatch.setattr(cache, "_chat_budget_redis_pool", None)
    monkeypatch.setattr(cache.aioredis, "from_url", from_url)
    monkeypatch.setattr(cache, "get_settings", lambda: settings)

    first = await cache.get_chat_budget_redis()
    second = await cache.get_chat_budget_redis()

    assert first is fake_pool
    assert second is fake_pool
    from_url.assert_called_once_with(
        "rediss://ledger.example:6380/0",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=1.25,
        socket_timeout=2.5,
        health_check_interval=15,
    )


async def test_get_chat_budget_redis_rejects_missing_ledger_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache, "_chat_budget_redis_pool", None)
    monkeypatch.setattr(
        cache,
        "get_settings",
        lambda: SimpleNamespace(chat_budget_redis_url=""),
    )

    with pytest.raises(RuntimeError, match="CHAT_BUDGET_REDIS_URL"):
        await cache.get_chat_budget_redis()


# ---------------------------------------------------------------------------
# get_cached_report
# ---------------------------------------------------------------------------


class TestGetCachedReport:
    """Tests for cache.get_cached_report."""

    async def test_cache_miss_returns_none(self) -> None:
        """r.get returning None -> function returns None without raising."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("api.cache.get_redis", return_value=mock_redis):
            from api.cache import get_cached_report

            result = await get_cached_report("org-1", "analysis-123")

        assert result is None
        mock_redis.get.assert_awaited_once_with("report:org-1:analysis-123")

    async def test_cache_hit_returns_parsed_dict(self) -> None:
        """r.get returning JSON -> function returns the parsed dict."""
        payload = {"compound": "aspirin", "risk": "low"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))

        with patch("api.cache.get_redis", return_value=mock_redis):
            from api.cache import get_cached_report

            result = await get_cached_report("org-2", "analysis-456")

        assert result == payload
        mock_redis.get.assert_awaited_once_with("report:org-2:analysis-456")

    async def test_versioned_cache_hit_uses_report_fingerprint_key(self) -> None:
        payload = {"compound": "aspirin", "risk": "low"}
        report_version = "a" * 64
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))

        with patch("api.cache.get_redis", return_value=mock_redis):
            from api.cache import get_cached_report

            result = await get_cached_report(
                "org-versioned",
                "analysis-versioned",
                version=report_version,
            )

        assert result == payload
        mock_redis.get.assert_awaited_once_with(
            f"report:org-versioned:analysis-versioned:{report_version}"
        )

    async def test_redis_error_is_re_raised(self) -> None:
        """A RedisError from r.get must propagate — no silent fallback."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=aioredis.RedisError("connection refused"))

        with patch("api.cache.get_redis", return_value=mock_redis):
            from api.cache import get_cached_report

            with pytest.raises(aioredis.RedisError):
                await get_cached_report("org-err", "analysis-err")

    async def test_json_decode_error_is_re_raised(self) -> None:
        """Corrupt JSON in cache must raise — not silently return None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not-valid-json{{{")

        with patch("api.cache.get_redis", return_value=mock_redis):
            from api.cache import get_cached_report

            with pytest.raises((json.JSONDecodeError, TypeError)):
                await get_cached_report("org-corrupt", "analysis-corrupt")


# ---------------------------------------------------------------------------
# set_cached_report
# ---------------------------------------------------------------------------


class TestSetCachedReport:
    """Tests for cache.set_cached_report."""

    async def test_set_calls_redis_with_correct_args(self) -> None:
        """set_cached_report should call r.set with the JSON payload and TTL."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        report = {"compound": "paracetamol", "score": 0.9}

        with (
            patch("api.cache.get_redis", return_value=mock_redis),
            patch("api.cache.get_settings") as mock_settings,
        ):
            mock_settings.return_value.report_cache_ttl = 3600
            from api.cache import set_cached_report

            await set_cached_report("org-3", "analysis-789", report, ttl=600)

        mock_redis.set.assert_awaited_once()
        call_args = mock_redis.set.call_args
        # First positional arg: key
        assert call_args.args[0] == "report:org-3:analysis-789"
        # Second positional arg: JSON-encoded payload
        assert json.loads(call_args.args[1]) == report
        # ex kwarg: TTL
        assert call_args.kwargs.get("ex") == 600

    async def test_redis_error_on_set_is_re_raised(self) -> None:
        """RedisError during set must propagate."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=aioredis.RedisError("write failed"))

        with (
            patch("api.cache.get_redis", return_value=mock_redis),
            patch("api.cache.get_settings") as mock_settings,
        ):
            mock_settings.return_value.report_cache_ttl = 3600
            from api.cache import set_cached_report

            with pytest.raises(aioredis.RedisError):
                await set_cached_report("org-err", "analysis-err", {"data": 1})

    async def test_uses_default_ttl_from_settings(self) -> None:
        """When ttl=None the value from settings is used."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with (
            patch("api.cache.get_redis", return_value=mock_redis),
            patch("api.cache.get_settings") as mock_settings,
        ):
            mock_settings.return_value.report_cache_ttl = 7200
            from api.cache import set_cached_report

            await set_cached_report("org-default", "analysis-default-ttl", {"x": 1}, ttl=None)

        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == 7200
