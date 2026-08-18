"""In-process circuit breaker for external dependency protection.

Implements a thread-safe, async-compatible state machine with three states:
  CLOSED   — normal operation; all calls pass through
  OPEN     — failing fast; calls are rejected immediately for recovery_timeout_s
  HALF_OPEN — recovery probe; one call is allowed through to test the dependency

Each Cloud Run instance maintains independent circuit state.  Failures across
instances do NOT share state (by design — Redis coupling the breaker would
create an availability dependency on Redis itself).

Usage:
    breaker = CircuitBreaker("anthropic", failure_threshold=5, recovery_timeout_s=60)

    try:
        result = await breaker.call(my_async_fn, arg1, arg2)
    except CircuitOpenError:
        raise APIError(503, "Service temporarily unavailable", "AI provider is offline")
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and the call is fast-failed."""

    def __init__(self, breaker_name: str, retry_after_s: float) -> None:
        self.breaker_name = breaker_name
        self.retry_after_s = retry_after_s
        super().__init__(f"Circuit '{breaker_name}' is open; retry after {retry_after_s:.1f}s")


class CircuitBreaker:
    """Thread-safe circuit breaker usable from both sync and async code.

    Uses threading.Lock for state transitions (held only for microseconds —
    never during the actual call) so it can be called from sync request handlers,
    asyncio coroutines, and Celery workers without adaptation.

    Args:
        name: Identifies the protected dependency (used in logs + metrics).
        failure_threshold: Consecutive failures before the circuit opens.
        recovery_timeout_s: Seconds the circuit stays open before entering HALF_OPEN.
        success_threshold: Consecutive successes in HALF_OPEN before closing.
        max_concurrency: If set, cap concurrent in-flight calls via an asyncio.Semaphore
            (bulkhead pattern). Callers that exceed the limit block until a slot frees
            rather than failing fast, so keep this generous enough not to be a bottleneck
            under normal load. None disables the bulkhead.
        probe_timeout_s: How long a single HALF_OPEN probe is allowed to run before
            it is assumed to have disconnected (e.g. SSE GeneratorExit) and a new
            probe is allowed through. Defaults to recovery_timeout_s. Set this to
            at least the downstream call timeout so a slow-but-valid probe is not
            pre-empted (e.g. Anthropic's 120s client timeout needs probe_timeout_s≥120).
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 60.0,
        success_threshold: int = 2,
        max_concurrency: int | None = None,
        probe_timeout_s: float | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.success_threshold = success_threshold
        self._probe_timeout_s = (
            probe_timeout_s if probe_timeout_s is not None else recovery_timeout_s
        )

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float = 0.0
        self._probing = False  # True while exactly one probe request is in-flight in HALF_OPEN
        self._probe_started_at: float = 0.0  # monotonic timestamp when current probe began
        self._lock = threading.Lock()
        # Bulkhead semaphore — created lazily on first async call so it binds to the
        # running event loop (avoids "no running event loop" at module-import time).
        self._max_concurrency = max_concurrency
        self._semaphore: asyncio.Semaphore | None = None

        self._emit_state_metric(CircuitState.CLOSED)

    @property
    def state(self) -> CircuitState:
        return self._state

    def _check_and_maybe_probe(self) -> None:
        """Raise CircuitOpenError if the circuit is still open, or transition to HALF_OPEN.

        Enforces single-probe semantics: once HALF_OPEN, only the first caller is
        allowed through (_probing=True); all concurrent callers fast-fail with the
        remaining recovery timeout until the probe completes (record_success or
        record_failure resets _probing).
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._opened_at
                remaining = self.recovery_timeout_s - elapsed
                if remaining > 0:
                    logger.warning(
                        "circuit_fast_failed",
                        circuit=self.name,
                        retry_after_s=round(remaining, 1),
                    )
                    _record_fast_fail(self.name)
                    raise CircuitOpenError(self.name, remaining)
                # Recovery timeout elapsed — allow one probe request through
                self._transition(CircuitState.HALF_OPEN)
                self._probing = True
                self._probe_started_at = time.monotonic()
            elif self._state == CircuitState.HALF_OPEN and self._probing:
                probe_age = time.monotonic() - self._probe_started_at
                if probe_age <= self._probe_timeout_s:
                    # A live probe is in-flight; fast-fail concurrent callers
                    _record_fast_fail(self.name)
                    raise CircuitOpenError(self.name, self._probe_timeout_s - probe_age)
                # Probe deadline exceeded — the probing caller likely disconnected
                # (e.g. GeneratorExit from SSE client disconnect) without calling
                # record_success/record_failure. Allow a new probe attempt.
                logger.warning(
                    "circuit_probe_deadline_exceeded",
                    circuit=self.name,
                    probe_age_s=round(probe_age, 1),
                )
                _record_probe_deadline_exceeded(self.name)
                self._probe_started_at = time.monotonic()
                # _probing remains True; this caller becomes the new probe

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._probing = False
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._failure_count = 0
                    self._success_count = 0
                    self._transition(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_cancelled(self) -> None:
        """Record a client-cancelled call (GeneratorExit, CancelledError).

        Releases the HALF_OPEN probe lock so other callers can probe, without
        counting the cancellation as a provider failure. Client disconnects are
        not evidence of provider health degradation.

        Precondition: should only be called by the caller that owns the current
        probe (i.e. the one that passed _check_and_maybe_probe without raising).
        No-op when _probing is False to be safe if called from a non-probe path.
        """
        with self._lock:
            if self._probing:
                self._probing = False
                _record_cancelled(self.name)

    def record_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._probing = False
            self._failure_count += 1
            self._success_count = 0
            if (
                self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)
                and self._failure_count >= self.failure_threshold
            ):
                self._opened_at = time.monotonic()
                self._transition(CircuitState.OPEN)
                logger.error(
                    "circuit_opened",
                    circuit=self.name,
                    failure_threshold=self.failure_threshold,
                    error_type=type(exc).__name__,
                    recovery_timeout_s=self.recovery_timeout_s,
                    exc_info=True,
                )

    def _get_semaphore(self) -> asyncio.Semaphore | None:
        """Return the bulkhead semaphore, creating it lazily on first async call."""
        if self._max_concurrency is None:
            return None
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
        return self._semaphore

    async def bulkhead_acquire(self) -> None:
        """Acquire the bulkhead semaphore and increment the in-flight metric.

        No-op when max_concurrency is None.  MUST be paired with a matching
        bulkhead_release() in a finally block.  Used by streaming code paths
        that cannot route through .call() but still need the concurrency ceiling.
        """
        sem = self._get_semaphore()
        if sem is None:
            return
        await sem.acquire()
        self._emit_inflight_metric(1)

    def bulkhead_release(self) -> None:
        """Release the bulkhead semaphore and decrement the in-flight metric.

        No-op when max_concurrency is None.
        """
        if self._semaphore is None:
            return
        self._emit_inflight_metric(-1)
        self._semaphore.release()

    def _emit_inflight_metric(self, delta: int) -> None:
        try:
            from api.metrics import circuit_breaker_inflight_gauge

            g = circuit_breaker_inflight_gauge.labels(circuit=self.name)
            if delta > 0:
                g.inc()
            else:
                g.dec()
        except Exception:
            logger.debug("circuit_breaker_inflight_metric_failed", circuit=self.name, exc_info=True)

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run an async callable through the circuit breaker.

        If max_concurrency is set, acquires the bulkhead semaphore and tracks
        in-flight count via the praviar_circuit_breaker_inflight metric before
        checking circuit state.
        """
        sem = self._get_semaphore()
        if sem is not None:
            async with sem:
                self._emit_inflight_metric(1)
                try:
                    return await self._call_inner(fn, *args, **kwargs)
                finally:
                    self._emit_inflight_metric(-1)
        return await self._call_inner(fn, *args, **kwargs)

    async def _call_inner(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        self._check_and_maybe_probe()
        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self.record_failure(exc)
            raise
        except BaseException:
            # asyncio.CancelledError is a BaseException (not Exception) in Python 3.8+.
            # Client cancellation is not evidence of provider degradation — release the
            # probe lock so HALF_OPEN doesn't stall for probe_timeout_s.
            self.record_cancelled()
            raise

    def call_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a synchronous callable through the circuit breaker."""
        self._check_and_maybe_probe()
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self.record_failure(exc)
            raise

    def _transition(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        if new_state != CircuitState.HALF_OPEN:
            self._probing = False
        self._emit_state_metric(new_state)
        logger.info(
            "circuit_state_changed",
            circuit=self.name,
            from_state=old_state,
            to_state=new_state,
        )

    def _emit_state_metric(self, state: CircuitState) -> None:
        try:
            from api.metrics import circuit_breaker_state_gauge

            circuit_breaker_state_gauge.labels(circuit=self.name, state=state.value).set(1)
            for other_state in CircuitState:
                if other_state != state:
                    circuit_breaker_state_gauge.labels(
                        circuit=self.name, state=other_state.value
                    ).set(0)
        except Exception:
            logger.debug("circuit_breaker_metric_emission_failed", circuit=self.name, exc_info=True)


def _record_fast_fail(name: str) -> None:
    try:
        from api.metrics import circuit_breaker_fast_fails_total

        circuit_breaker_fast_fails_total.labels(circuit=name).inc()
    except Exception:
        logger.debug("circuit_breaker_fast_fail_metric_failed", circuit=name, exc_info=True)


def _record_probe_deadline_exceeded(name: str) -> None:
    try:
        from api.metrics import circuit_breaker_probe_deadline_exceeded_total

        circuit_breaker_probe_deadline_exceeded_total.labels(circuit=name).inc()
    except Exception:
        logger.debug("circuit_breaker_probe_deadline_metric_failed", circuit=name, exc_info=True)


def _record_cancelled(name: str) -> None:
    try:
        from api.metrics import circuit_breaker_cancelled_total

        circuit_breaker_cancelled_total.labels(circuit=name).inc()
    except Exception:
        logger.debug("circuit_breaker_cancelled_metric_failed", circuit=name, exc_info=True)


# ─── Named circuit breakers ──────────────────────────────────────────────────
# One breaker per external dependency.  Instantiated at module level so state
# persists for the lifetime of the Cloud Run instance.

anthropic_breaker = CircuitBreaker(
    "anthropic",
    failure_threshold=5,
    recovery_timeout_s=60.0,
    max_concurrency=20,  # streaming calls; cap to avoid saturating the async worker pool
    probe_timeout_s=150.0,  # must exceed the Anthropic client timeout (120s) so a slow
    # but valid stream is not pre-empted by the probe-deadline recovery path
)

stripe_breaker = CircuitBreaker(
    "stripe",
    failure_threshold=5,
    recovery_timeout_s=30.0,
    max_concurrency=30,  # fast synchronous-style API; generous ceiling
)

postmark_breaker = CircuitBreaker(
    "postmark",
    failure_threshold=3,
    recovery_timeout_s=120.0,
    max_concurrency=10,  # low-volume transactional email
)

clerk_jwks_breaker = CircuitBreaker(
    "clerk_jwks",
    failure_threshold=3,
    recovery_timeout_s=30.0,
    # max_concurrency omitted: only caller uses call_sync which cannot acquire
    # an asyncio.Semaphore; a limit here would be dead config.
)

clerk_breaker = CircuitBreaker(
    "clerk",
    failure_threshold=3,
    recovery_timeout_s=60.0,
    max_concurrency=10,  # SSO + admin invite; modest parallelism
)

licensed_overlay_breaker = CircuitBreaker(
    "licensed_overlay",
    failure_threshold=3,
    recovery_timeout_s=60.0,
    max_concurrency=10,  # external ML service; modest parallelism
)
