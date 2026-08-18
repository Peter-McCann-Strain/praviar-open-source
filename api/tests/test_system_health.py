"""Tests for api.services.system_health.

Covers the three public functions:
  - check_database_health  -- raises on DB failure
  - check_redis_health     -- raises on Redis failure, always closes the client
  - collect_readiness_errors -- collects errors from both checks
  - run_startup_checks     -- skipped in test env, raises on infra failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.system_health import (
    check_database_health,
    check_redis_health,
    collect_readiness_errors,
    run_startup_checks,
)

# Unit tests use a mock DB with no alembic_version table, so we bypass the
# migration head check.  The check itself has its own focused tests.
_PATCH_MIGRATION = patch(
    "api.services.system_health.check_migration_head",
    new=AsyncMock(),
)


# ---------------------------------------------------------------------------
# check_database_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_database_health_success():
    """A reachable DB executes SELECT 1 without raising."""
    session = AsyncMock()
    session.execute = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=ctx)
    # Should not raise
    await check_database_health(async_session_factory_fn=factory)
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_check_database_health_raises_on_failure():
    """A DB that raises propagates the exception."""
    session = AsyncMock()
    session.execute.side_effect = ConnectionError("pg down")
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=ctx)
    with pytest.raises(ConnectionError, match="pg down"):
        await check_database_health(async_session_factory_fn=factory)


# ---------------------------------------------------------------------------
# check_redis_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_redis_health_success():
    """A reachable Redis pings and is closed afterward."""
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock()
    redis_client.aclose = AsyncMock()

    redis_from_url = MagicMock(return_value=redis_client)

    await check_redis_health(redis_url="redis://localhost:6379", redis_from_url_fn=redis_from_url)

    redis_client.ping.assert_awaited_once()
    redis_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_health_passes_bounded_connection_kwargs():
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock()
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    await check_redis_health(
        redis_url="redis://localhost:6379",
        redis_from_url_fn=redis_from_url,
        redis_connection_kwargs={
            "socket_connect_timeout": 1.0,
            "socket_timeout": 2.0,
            "health_check_interval": 15,
        },
    )

    redis_from_url.assert_called_once_with(
        "redis://localhost:6379",
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
        health_check_interval=15,
    )


@pytest.mark.asyncio
async def test_check_redis_health_closes_on_failure():
    """aclose() is always called even when ping raises."""
    redis_client = AsyncMock()
    redis_client.ping.side_effect = OSError("connection refused")
    redis_client.aclose = AsyncMock()

    redis_from_url = MagicMock(return_value=redis_client)

    with pytest.raises(OSError, match="connection refused"):
        await check_redis_health(
            redis_url="redis://localhost:6379", redis_from_url_fn=redis_from_url
        )

    # aclose must still have been called (finally block)
    redis_client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# collect_readiness_errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_readiness_errors_all_healthy():
    """When both checks pass, the error list is empty."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    errors = await collect_readiness_errors(
        redis_url="redis://localhost",
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    assert errors == []


@pytest.mark.asyncio
async def test_collect_readiness_errors_db_failure():
    """A DB failure is captured and returned as a string; Redis still checked."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db timeout")
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    errors = await collect_readiness_errors(
        redis_url="redis://localhost",
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    assert len(errors) == 1
    assert "database:" in errors[0]
    assert "database" in errors[0]
    assert "unavailable" in errors[0]


@pytest.mark.asyncio
async def test_collect_readiness_errors_redis_failure():
    """A Redis failure is captured and returned; DB check still runs first."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.ping.side_effect = ConnectionError("redis gone")
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    errors = await collect_readiness_errors(
        redis_url="redis://localhost",
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    assert len(errors) == 1
    assert "redis:" in errors[0]
    assert "redis" in errors[0]
    assert "unavailable" in errors[0]


@pytest.mark.asyncio
async def test_collect_readiness_errors_both_fail():
    """Both checks failing returns two error strings."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db down")
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.ping.side_effect = OSError("redis down")
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    errors = await collect_readiness_errors(
        redis_url="redis://localhost",
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    assert len(errors) == 2
    assert any("database:" in e for e in errors)
    assert any("redis:" in e for e in errors)


# ---------------------------------------------------------------------------
# run_startup_checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_startup_checks_skipped_in_test_env():
    """When app_env='test', the function returns immediately without checking infra."""
    logger = MagicMock()
    # factory/from_url should never be called
    db_factory = MagicMock()
    redis_from_url = MagicMock()

    await run_startup_checks(
        app_env="test",
        database_url="postgresql://ignored",
        redis_url="redis://ignored",
        db_pool_size=5,
        db_max_overflow=10,
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    db_factory.assert_not_called()
    redis_from_url.assert_not_called()
    logger.info.assert_called_once()
    # Should log reason=APP_ENV=test
    call_kwargs = logger.info.call_args[1]
    assert call_kwargs.get("reason") == "APP_ENV=test"


@pytest.mark.asyncio
async def test_run_startup_checks_raises_on_db_failure():
    """A DB failure during startup raises RuntimeError."""
    session = AsyncMock()
    session.execute.side_effect = OSError("cannot connect")
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_from_url = MagicMock()
    logger = MagicMock()

    with pytest.raises(RuntimeError, match="Database not reachable at startup"):
        await run_startup_checks(
            app_env="dev",
            database_url="postgresql://user:pass@host/db",
            redis_url="redis://localhost",
            db_pool_size=5,
            db_max_overflow=10,
            async_session_factory_fn=db_factory,
            redis_from_url_fn=redis_from_url,
            logger=logger,
        )


@_PATCH_MIGRATION
@pytest.mark.asyncio
async def test_run_startup_checks_raises_on_redis_failure():
    """A Redis failure during startup raises RuntimeError."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.ping.side_effect = OSError("redis down")
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    with pytest.raises(RuntimeError, match="Redis not reachable at startup"):
        await run_startup_checks(
            app_env="dev",
            database_url="postgresql://host/db",
            redis_url="redis://localhost",
            db_pool_size=5,
            db_max_overflow=10,
            async_session_factory_fn=db_factory,
            redis_from_url_fn=redis_from_url,
            logger=logger,
        )


@_PATCH_MIGRATION
@pytest.mark.asyncio
async def test_run_startup_checks_success_logs_db_and_redis():
    """Successful startup logs ok messages for both DB and Redis."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    await run_startup_checks(
        app_env="staging",
        database_url="postgresql://host/db",
        redis_url="redis://localhost",
        db_pool_size=5,
        db_max_overflow=10,
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    debug_calls = [str(c) for c in logger.debug.call_args_list]
    assert any("startup_db_ok" in c for c in debug_calls)
    assert any("startup_redis_ok" in c for c in debug_calls)


@_PATCH_MIGRATION
@pytest.mark.asyncio
async def test_run_startup_checks_redacts_db_password():
    """The database_url password is not logged — only the host part."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db_factory = MagicMock(return_value=ctx)

    redis_client = AsyncMock()
    redis_client.aclose = AsyncMock()
    redis_from_url = MagicMock(return_value=redis_client)

    logger = MagicMock()

    await run_startup_checks(
        app_env="dev",
        database_url="postgresql://user:supersecret@myhost/db",
        redis_url="redis://localhost",
        db_pool_size=5,
        db_max_overflow=10,
        async_session_factory_fn=db_factory,
        redis_from_url_fn=redis_from_url,
        logger=logger,
    )

    # Confirm that the logged database_url does NOT contain the password
    all_debug_calls_text = str(logger.debug.call_args_list)
    assert "supersecret" not in all_debug_calls_text
    assert "myhost" in all_debug_calls_text
