"""Shared HTTP utility helpers for outbound calls."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
import structlog

logger = structlog.get_logger()

T = TypeVar("T")

_DEFAULT_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 502, 503, 504})


def _inc_retry_metric(caller: str, reason: str) -> None:
    try:
        from api.metrics import http_retries_total

        http_retries_total.labels(caller=caller, reason=reason).inc()
    except Exception:
        logger.debug("http_retry_metric_failed", caller=caller, reason=reason, exc_info=True)


async def retry_with_jitter(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 10.0,
    retryable_status_codes: frozenset[int] = _DEFAULT_RETRYABLE_STATUS_CODES,
    caller: str = "unknown",
) -> T:
    """Retry an async callable with exponential back-off and full-jitter.

    Retries on:
    - httpx.RequestError  (network-layer transients: timeout, connection refused)
    - httpx.HTTPStatusError whose status code is in retryable_status_codes

    All other exceptions propagate immediately (no retry).

    Args:
        fn:                   Zero-argument async callable to call.
        max_attempts:         Total attempts including the first one.
        base_delay_s:         Initial back-off before jitter (doubles each attempt).
        max_delay_s:          Cap on the computed back-off before jitter.
        retryable_status_codes: HTTP status codes that are worth retrying.
        caller:               Log label identifying the call site.
    """
    last_exc: BaseException | None = None
    had_retries = False
    for attempt in range(max_attempts):
        try:
            result = await fn()
            if had_retries:
                _inc_retry_metric(caller, "recovered")
            return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in retryable_status_codes:
                if had_retries:
                    _inc_retry_metric(caller, "exhausted")
                raise
            last_exc = exc
            had_retries = True
            logger.warning(
                "http_retryable_status",
                caller=caller,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                status=exc.response.status_code,
            )
            _inc_retry_metric(caller, "status_code")
        except httpx.RequestError as exc:
            last_exc = exc
            had_retries = True
            logger.warning(
                "http_retryable_network_error",
                caller=caller,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                error=type(exc).__name__,
            )
            _inc_retry_metric(caller, "network_error")

        if attempt < max_attempts - 1:
            cap = min(base_delay_s * (2**attempt), max_delay_s)
            # Full-jitter: uniform [0, cap] avoids thundering-herd on correlated failures.
            await asyncio.sleep(random.uniform(0, cap))  # noqa: S311

    _inc_retry_metric(caller, "exhausted")
    raise last_exc  # type: ignore[misc]
