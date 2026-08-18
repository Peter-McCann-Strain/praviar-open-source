"""Bounded async wrappers for synchronous third-party SDK calls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

import structlog

from api.observability.spans import record_span_exception, start_span

logger = structlog.get_logger()

T = TypeVar("T")

_SDK_CALL_CONCURRENCY_LIMIT = 16
_sdk_call_semaphore = asyncio.Semaphore(_SDK_CALL_CONCURRENCY_LIMIT)

# Provider names (operation_name prefix) that have a named circuit breaker.
_CIRCUIT_BREAKER_PROVIDERS = frozenset({"stripe", "anthropic"})


class BlockingSDKCallTimeoutError(TimeoutError):
    """Raised when a synchronous SDK call exceeds its bounded timeout."""


def retryable_exception_types(*candidates: object) -> tuple[type[BaseException], ...]:
    """Return only valid exception classes from optional SDK attributes."""
    return tuple(
        candidate
        for candidate in candidates
        if isinstance(candidate, type) and issubclass(candidate, BaseException)
    )


def _get_breaker(provider: str):
    """Return the circuit breaker for a known external provider, or None."""
    if provider not in _CIRCUIT_BREAKER_PROVIDERS:
        return None
    try:
        from api.circuit_breaker import anthropic_breaker, stripe_breaker

        return {"stripe": stripe_breaker, "anthropic": anthropic_breaker}.get(provider)
    except Exception:
        return None


async def run_blocking_sdk_call(
    operation_name: str,
    fn: Callable[..., T],
    *args: Any,
    timeout_seconds: float = 10.0,
    max_attempts: int = 2,
    retry_exceptions: tuple[type[BaseException], ...] = (),
    retry_base_delay_seconds: float = 0.15,
    retry_jitter_seconds: float = 0.1,
    logger_override: structlog.stdlib.BoundLogger | None = None,
    **kwargs: Any,
) -> T:
    """Run a synchronous SDK call off the event loop with timeout and retry telemetry.

    Circuit breakers are automatically applied for known external providers
    (stripe, anthropic).  A CircuitOpenError propagates to the caller so it
    can return a graceful 503 rather than waiting for a full timeout sequence.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    active_logger = logger_override or logger
    provider = operation_name.split(".", 1)[0] or "unknown"
    breaker = _get_breaker(provider)

    if breaker is not None:

        async def _protected() -> T:
            return await _run_sdk_attempts(
                operation_name=operation_name,
                fn=fn,
                args=args,
                kwargs=kwargs,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                retry_exceptions=retry_exceptions,
                retry_base_delay_seconds=retry_base_delay_seconds,
                retry_jitter_seconds=retry_jitter_seconds,
                active_logger=active_logger,
                provider=provider,
            )

        return cast(T, await breaker.call(_protected))

    return await _run_sdk_attempts(
        operation_name=operation_name,
        fn=fn,
        args=args,
        kwargs=kwargs,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        retry_exceptions=retry_exceptions,
        retry_base_delay_seconds=retry_base_delay_seconds,
        retry_jitter_seconds=retry_jitter_seconds,
        active_logger=active_logger,
        provider=provider,
    )


async def _run_sdk_attempts(
    *,
    operation_name: str,
    fn: Callable[..., T],
    args: tuple,
    kwargs: dict,
    timeout_seconds: float,
    max_attempts: int,
    retry_exceptions: tuple[type[BaseException], ...],
    retry_base_delay_seconds: float,
    retry_jitter_seconds: float,
    active_logger: structlog.stdlib.BoundLogger,
    provider: str,
) -> T:
    """Inner retry loop — separated so it can run inside or outside a breaker."""
    last_exception: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        span_attributes = {
            "sdk.operation": operation_name,
            "sdk.provider": provider,
            "sdk.attempt": attempt,
            "sdk.max_attempts": max_attempts,
            "sdk.timeout_seconds": timeout_seconds,
        }
        try:
            with start_span("sdk.blocking_call", span_attributes):
                async with _sdk_call_semaphore:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(fn, *args, **kwargs),
                        timeout=timeout_seconds,
                    )
            duration_s = time.perf_counter() - started
            _record_provider_metric(provider, operation_name, duration_s, "success")
            active_logger.info(
                "blocking_sdk_call_succeeded",
                operation=operation_name,
                attempt=attempt,
                duration_ms=round(duration_s * 1000, 2),
            )
            return result
        except TimeoutError as exc:
            last_exception = BlockingSDKCallTimeoutError(
                f"{operation_name} timed out after {timeout_seconds:.2f}s"
            )
            retryable = True
            error_type = type(last_exception).__name__
            last_exception.__cause__ = exc
        except retry_exceptions as exc:
            last_exception = exc
            retryable = True
            error_type = type(exc).__name__
        except Exception as exc:
            _record_provider_metric(
                provider,
                operation_name,
                time.perf_counter() - started,
                "error",
            )
            active_logger.error(
                "blocking_sdk_call_failed",
                operation=operation_name,
                attempt=attempt,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            raise

        if not retryable or attempt == max_attempts:
            _record_provider_metric(
                provider,
                operation_name,
                time.perf_counter() - started,
                "error",
            )
            with start_span("sdk.blocking_call.failure", span_attributes) as span:
                if last_exception is not None:
                    record_span_exception(span, last_exception)
            active_logger.error(
                "blocking_sdk_call_exhausted",
                operation=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=error_type,
                exc_info=True,
            )
            raise last_exception

        delay = retry_base_delay_seconds * (2 ** (attempt - 1))
        if retry_jitter_seconds:
            delay += random.uniform(0, retry_jitter_seconds)
        active_logger.warning(
            "blocking_sdk_call_retrying",
            operation=operation_name,
            attempt=attempt,
            next_attempt=attempt + 1,
            max_attempts=max_attempts,
            delay_seconds=round(delay, 3),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=error_type,
        )
        await asyncio.sleep(delay)

    raise AssertionError("unreachable blocking SDK retry loop exit")


def _record_provider_metric(
    provider: str,
    operation: str,
    duration_s: float,
    status: str,
) -> None:
    try:
        from api.metrics import record_provider_call

        record_provider_call(
            provider=provider,
            operation=operation,
            duration_s=duration_s,
            errored=status != "success",
        )
    except Exception:
        return
