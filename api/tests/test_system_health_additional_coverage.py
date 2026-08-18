from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from api.services.system_health import (
    _probe,
    _timed_check,
    check_migration_head,
    collect_health_detail,
    run_startup_checks,
)


def _session_factory(*, rows=None, execute_error: Exception | None = None):
    result = MagicMock()
    result.fetchall.return_value = rows or []
    session = AsyncMock()
    if execute_error is not None:
        session.execute.side_effect = execute_error
    else:
        session.execute.return_value = result
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    return MagicMock(return_value=context), session


@pytest.mark.asyncio
async def test_check_migration_head_accepts_exact_multi_head_schema() -> None:
    factory, session = _session_factory(rows=[("head-a",), ("head-b",)])
    script = MagicMock()
    script.get_heads.return_value = ["head-a", "head-b"]

    with (
        patch("alembic.config.Config", return_value=MagicMock()) as config,
        patch("alembic.script.ScriptDirectory.from_config", return_value=script),
    ):
        await check_migration_head(
            async_session_factory_fn=factory,
            alembic_cfg_path="custom-alembic.ini",
        )

    config.assert_called_once_with("custom-alembic.ini")
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_migration_head_reports_missing_and_unexpected_revisions() -> None:
    factory, _ = _session_factory(rows=[("old-head",)])
    script = MagicMock()
    script.get_heads.return_value = ["new-head"]

    with (
        patch("alembic.config.Config", return_value=MagicMock()),
        patch("alembic.script.ScriptDirectory.from_config", return_value=script),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await check_migration_head(
            async_session_factory_fn=factory,
            alembic_cfg_path="alembic.ini",
        )

    message = str(exc_info.value)
    assert "missing: ['new-head']" in message
    assert "extra: ['old-head']" in message
    assert "alembic upgrade head" in message


@pytest.mark.asyncio
async def test_check_migration_head_treats_missing_version_table_as_empty_schema() -> None:
    factory, _ = _session_factory(execute_error=RuntimeError("table does not exist"))
    script = MagicMock()
    script.get_heads.return_value = ["expected-head"]

    with (
        patch("alembic.config.Config", return_value=MagicMock()),
        patch("alembic.script.ScriptDirectory.from_config", return_value=script),
        pytest.raises(RuntimeError, match=r"current: \[\]") as exc_info,
    ):
        await check_migration_head(
            async_session_factory_fn=factory,
            alembic_cfg_path="alembic.ini",
        )

    assert "missing: ['expected-head']" in str(exc_info.value)


@pytest.mark.asyncio
async def test_timed_check_reports_ok_with_measured_latency() -> None:
    async def succeeds() -> None:
        return None

    status, latency_ms, error = await _timed_check(succeeds())

    assert status == "ok"
    assert latency_ms >= 0
    assert error is None


@pytest.mark.asyncio
async def test_timed_check_reports_timeout_as_degraded() -> None:
    async def pending() -> None:
        return None

    async def timeout(coro, *, timeout):
        coro.close()
        raise TimeoutError

    with patch("api.services.system_health.asyncio.wait_for", new=timeout):
        status, latency_ms, error = await _timed_check(pending())

    assert status == "degraded"
    assert latency_ms >= 0
    assert error == "timeout"


@pytest.mark.asyncio
async def test_timed_check_reports_dependency_exception_as_error() -> None:
    async def fails() -> None:
        raise ConnectionError("database unavailable")

    status, latency_ms, error = await _timed_check(fails())

    assert status == "error"
    assert latency_ms >= 0
    assert error == "database unavailable"


@pytest.mark.asyncio
async def test_collect_health_detail_returns_ok_and_rounded_latency() -> None:
    logger = MagicMock()
    outcomes = iter([("ok", 1.24, None), ("ok", 2.26, None)])

    async def timed_check(coro):
        coro.close()
        return next(outcomes)

    with patch(
        "api.services.system_health._timed_check",
        new=timed_check,
    ):
        detail = await collect_health_detail(
            redis_url="redis://localhost",
            async_session_factory_fn=MagicMock(),
            redis_from_url_fn=MagicMock(),
            logger=logger,
        )

    assert detail == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
        "latency_ms": {"database": 1.2, "redis": 2.3},
    }
    logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_collect_health_detail_degrades_and_logs_each_failed_dependency() -> None:
    logger = MagicMock()
    outcomes = iter(
        [
            ("error", 3.04, "database unavailable"),
            ("degraded", 100.04, "timeout"),
        ]
    )

    async def timed_check(coro):
        coro.close()
        return next(outcomes)

    with patch(
        "api.services.system_health._timed_check",
        new=timed_check,
    ):
        detail = await collect_health_detail(
            redis_url="redis://localhost",
            async_session_factory_fn=MagicMock(),
            redis_from_url_fn=MagicMock(),
            logger=logger,
            redis_connection_kwargs={"socket_timeout": 0.05},
        )

    assert detail["status"] == "degraded"
    assert detail["checks"] == {"database": "error", "redis": "degraded"}
    assert detail["latency_ms"] == {"database": 3.0, "redis": 100.0}
    assert logger.error.call_args_list == [
        call(
            "health_db_check_failed",
            status="error",
            error="database unavailable",
        ),
        call("health_redis_check_failed", status="degraded", error="timeout"),
    ]


@pytest.mark.asyncio
async def test_probe_reports_timeout_without_exposing_dependency_details() -> None:
    logger = MagicMock()

    async def pending() -> None:
        return None

    async def timeout(coro, *, timeout):
        coro.close()
        raise TimeoutError

    with patch("api.services.system_health.asyncio.wait_for", new=timeout):
        error = await _probe(pending(), "database", logger)

    assert error == "database: timed out"
    logger.error.assert_called_once_with(
        "readiness_probe_timeout",
        check="database",
        timeout_s=2.0,
    )


@pytest.mark.asyncio
async def test_startup_checks_wraps_unexpected_migration_configuration_error() -> None:
    logger = MagicMock()

    with (
        patch(
            "api.services.system_health.check_database_health",
            new=AsyncMock(),
        ),
        patch(
            "api.services.system_health.check_migration_head",
            new=AsyncMock(side_effect=ValueError("invalid alembic config")),
        ),
        patch(
            "api.services.system_health.check_redis_health",
            new=AsyncMock(),
        ) as redis_check,
        pytest.raises(RuntimeError, match="Migration head check failed at startup") as exc_info,
    ):
        await run_startup_checks(
            app_env="production",
            database_url="postgresql://user:secret@db/prod",
            redis_url="redis://cache",
            db_pool_size=5,
            db_max_overflow=10,
            async_session_factory_fn=MagicMock(),
            redis_from_url_fn=MagicMock(),
            logger=logger,
            alembic_cfg_path="broken.ini",
        )

    assert isinstance(exc_info.value.__cause__, ValueError)
    redis_check.assert_not_awaited()
    logger.error.assert_called_once_with(
        "startup_migration_check_failed",
        error="invalid alembic config",
        exc_info=True,
    )
