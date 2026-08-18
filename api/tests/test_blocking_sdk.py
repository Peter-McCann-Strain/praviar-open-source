"""Tests for bounded synchronous SDK execution wrappers."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from api.services.blocking_sdk import (
    BlockingSDKCallTimeoutError,
    retryable_exception_types,
    run_blocking_sdk_call,
)


class TransientSDKError(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_run_blocking_sdk_call_runs_sync_function_off_loop() -> None:
    fn = MagicMock(return_value="ok")

    with pytest.MonkeyPatch.context() as monkeypatch:
        metric = MagicMock()
        monkeypatch.setattr("api.metrics.record_provider_call", metric)
        result = await run_blocking_sdk_call(
            "test.sync",
            fn,
            "value",
            timeout_seconds=1,
            max_attempts=1,
            logger_override=MagicMock(),
        )

    assert result == "ok"
    fn.assert_called_once_with("value")
    metric.assert_called_once()
    assert metric.call_args.kwargs["provider"] == "test"
    assert metric.call_args.kwargs["operation"] == "test.sync"
    assert metric.call_args.kwargs["errored"] is False


@pytest.mark.asyncio
async def test_run_blocking_sdk_call_retries_configured_transient_errors() -> None:
    fn = MagicMock(side_effect=[TransientSDKError("try again"), "ok"])

    result = await run_blocking_sdk_call(
        "test.retry",
        fn,
        timeout_seconds=1,
        max_attempts=2,
        retry_exceptions=(TransientSDKError,),
        retry_base_delay_seconds=0,
        retry_jitter_seconds=0,
        logger_override=MagicMock(),
    )

    assert result == "ok"
    assert fn.call_count == 2


@pytest.mark.asyncio
async def test_run_blocking_sdk_call_times_out() -> None:
    def slow_call() -> str:
        time.sleep(0.05)
        return "late"

    with pytest.raises(BlockingSDKCallTimeoutError):
        await run_blocking_sdk_call(
            "test.timeout",
            slow_call,
            timeout_seconds=0.001,
            max_attempts=1,
            logger_override=MagicMock(),
        )


@pytest.mark.asyncio
async def test_run_blocking_sdk_call_logs_error_type_without_exception_text() -> None:
    logger = MagicMock()

    with pytest.raises(RuntimeError):
        await run_blocking_sdk_call(
            "test.failure",
            MagicMock(side_effect=RuntimeError("sensitive compound detail")),
            timeout_seconds=1,
            max_attempts=1,
            logger_override=logger,
        )

    kwargs = logger.error.call_args.kwargs
    assert kwargs["error_type"] == "RuntimeError"
    assert "error" not in kwargs


def test_retryable_exception_types_filters_missing_sdk_attrs() -> None:
    assert retryable_exception_types(None, TransientSDKError, object()) == (TransientSDKError,)
