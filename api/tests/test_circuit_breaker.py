"""Tests for the in-process circuit breaker."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from api.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

# ── helpers ──────────────────────────────────────────────────────────────────


def make_breaker(**kwargs) -> CircuitBreaker:
    """Return a circuit breaker with metrics emission suppressed."""
    with patch("api.circuit_breaker.CircuitBreaker._emit_state_metric"):
        cb = CircuitBreaker("test", **kwargs)
    cb._emit_state_metric = MagicMock()
    return cb


async def _succeed():
    return "ok"


async def _fail():
    raise RuntimeError("boom")


def _succeed_sync():
    return "ok"


def _fail_sync():
    raise RuntimeError("boom")


# ── initial state ─────────────────────────────────────────────────────────────


def test_initial_state_is_closed():
    cb = make_breaker()
    assert cb.state == CircuitState.CLOSED


# ── async call — success path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_call_passes_through_when_closed():
    cb = make_breaker()
    result = await cb.call(_succeed)
    assert result == "ok"


@pytest.mark.asyncio
async def test_async_call_propagates_exception_and_counts_failure():
    cb = make_breaker(failure_threshold=3)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb._failure_count == 1
    assert cb.state == CircuitState.CLOSED


# ── sync call ────────────────────────────────────────────────────────────────


def test_sync_call_passes_through_when_closed():
    cb = make_breaker()
    result = cb.call_sync(_succeed_sync)
    assert result == "ok"


def test_sync_call_propagates_exception_and_counts_failure():
    cb = make_breaker(failure_threshold=3)
    with pytest.raises(RuntimeError):
        cb.call_sync(_fail_sync)
    assert cb._failure_count == 1


# ── trip to OPEN ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    cb = make_breaker(failure_threshold=3)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
    assert cb.state == CircuitState.OPEN


def test_circuit_opens_after_threshold_sync_failures():
    cb = make_breaker(failure_threshold=2)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call_sync(_fail_sync)
    assert cb.state == CircuitState.OPEN


# ── fast-fail when OPEN ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_circuit_fast_fails_async():
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=999)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as exc_info:
        await cb.call(_succeed)
    assert exc_info.value.breaker_name == "test"


def test_open_circuit_fast_fails_sync():
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=999)
    with pytest.raises(RuntimeError):
        cb.call_sync(_fail_sync)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.call_sync(_succeed_sync)


# ── recovery: OPEN → HALF_OPEN → CLOSED ──────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_transitions_to_half_open_after_timeout():
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01, success_threshold=1)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.05)  # let recovery timeout elapse

    result = await cb.call(_succeed)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit():
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01, success_threshold=2)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    # First probe fails — should reopen
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb.state == CircuitState.OPEN


# ── HALF_OPEN single-probe: concurrent callers are fast-failed ───────────────


@pytest.mark.asyncio
async def test_half_open_concurrent_callers_fast_failed():
    """Only one probe request passes through HALF_OPEN; others fast-fail."""
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01, success_threshold=1)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    # Manually set _probing to simulate an in-flight probe
    import time

    cb._probing = True
    cb._probe_started_at = time.monotonic()
    cb._state = type(cb._state).HALF_OPEN  # stay in HALF_OPEN

    with pytest.raises(CircuitOpenError):
        await cb.call(_succeed)


@pytest.mark.asyncio
async def test_half_open_single_probe_under_gather_concurrency():
    """Under actual asyncio.gather concurrency exactly one caller probes."""
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01, success_threshold=1)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    # A slow probe — holds HALF_OPEN/probing=True while others arrive.
    probe_started = asyncio.Event()
    probe_released = asyncio.Event()

    async def _slow_succeed():
        probe_started.set()
        await probe_released.wait()
        return "ok"

    # Kick off the probe in the background; wait until it has entered _slow_succeed.
    probe_task = asyncio.create_task(cb.call(_slow_succeed))
    await probe_started.wait()

    # Concurrent callers that arrive while the probe is in-flight must fast-fail.
    results = await asyncio.gather(
        cb.call(_succeed),
        cb.call(_succeed),
        return_exceptions=True,
    )
    assert all(isinstance(r, CircuitOpenError) for r in results), results

    # Release the probe; circuit should close.
    probe_released.set()
    await probe_task
    assert cb.state == CircuitState.CLOSED


# ── success_threshold requires multiple successes to close ───────────────────


@pytest.mark.asyncio
async def test_half_open_requires_multiple_successes_to_close():
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01, success_threshold=2)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    await cb.call(_succeed)
    assert cb.state == CircuitState.HALF_OPEN  # one success, need two

    await cb.call(_succeed)
    assert cb.state == CircuitState.CLOSED


# ── success resets failure count while CLOSED ────────────────────────────────


@pytest.mark.asyncio
async def test_success_resets_failure_count():
    cb = make_breaker(failure_threshold=3)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb._failure_count == 1

    await cb.call(_succeed)
    assert cb._failure_count == 0


# ── probe-deadline recovery ──────────────────────────────────────────────────


def test_probe_deadline_recovery_allows_new_probe():
    """When a HALF_OPEN probe exceeds probe_timeout_s the next caller becomes the probe."""
    import time
    from unittest.mock import patch

    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.1, probe_timeout_s=0.05)
    # Simulate HALF_OPEN with a stale probe.
    cb._state = CircuitState.HALF_OPEN
    cb._probing = True
    cb._probe_started_at = time.monotonic() - 1.0  # 1s ago, well past 0.05s timeout

    with patch("api.circuit_breaker._record_probe_deadline_exceeded") as mock_record:
        # _check_and_maybe_probe should NOT raise — caller becomes new probe.
        cb._check_and_maybe_probe()
        mock_record.assert_called_once_with(cb.name)

    # _probing stays True (this caller is now the probe) and _probe_started_at is refreshed.
    assert cb._probing is True
    assert cb._probe_started_at > time.monotonic() - 0.1  # recently reset


def test_probe_deadline_live_probe_still_fast_fails():
    """A live in-flight probe (within probe_timeout_s) still fast-fails concurrent callers."""
    import time

    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.1, probe_timeout_s=60.0)
    cb._state = CircuitState.HALF_OPEN
    cb._probing = True
    cb._probe_started_at = time.monotonic()  # just started

    with pytest.raises(CircuitOpenError):
        cb._check_and_maybe_probe()


# ── record_success / record_failure direct API ───────────────────────────────


def test_record_success_resets_count():
    cb = make_breaker()
    cb._failure_count = 2
    cb.record_success()
    assert cb._failure_count == 0


def test_record_failure_increments_count():
    cb = make_breaker(failure_threshold=5)
    cb.record_failure(RuntimeError("x"))
    assert cb._failure_count == 1
    assert cb.state == CircuitState.CLOSED


def test_record_failure_opens_at_threshold():
    cb = make_breaker(failure_threshold=2)
    cb.record_failure(RuntimeError("x"))
    cb.record_failure(RuntimeError("y"))
    assert cb.state == CircuitState.OPEN


# ── record_cancelled ─────────────────────────────────────────────────────────


def test_record_cancelled_releases_probe_lock_without_failure():
    """Client disconnect (GeneratorExit) releases the probe lock, never counts as failure."""
    cb = make_breaker(failure_threshold=3, recovery_timeout_s=0.01)
    # Trip the circuit open, then allow it to transition to HALF_OPEN.
    cb._failure_count = cb.failure_threshold
    cb._opened_at = 0.0  # far in the past so recovery_timeout has elapsed
    cb._transition(CircuitState.OPEN)
    # Simulate the probe caller acquiring the probe.
    import time

    cb._state = CircuitState.HALF_OPEN
    cb._probing = True
    cb._probe_started_at = time.monotonic()

    cb.record_cancelled()

    assert cb._probing is False  # probe lock released
    assert cb._failure_count == cb.failure_threshold  # not incremented
    assert cb.state == CircuitState.HALF_OPEN  # still HALF_OPEN; next caller probes


def test_record_cancelled_emits_metric_when_probing():
    """record_cancelled increments circuit_breaker_cancelled_total on the probe path."""
    import time
    from unittest.mock import patch

    cb = make_breaker(failure_threshold=3)
    cb._state = CircuitState.HALF_OPEN
    cb._probing = True
    cb._probe_started_at = time.monotonic()

    with patch("api.circuit_breaker._record_cancelled") as mock_record:
        cb.record_cancelled()
        mock_record.assert_called_once_with(cb.name)


def test_record_cancelled_does_not_emit_metric_when_not_probing():
    """record_cancelled is a no-op (no metric) when _probing is False."""
    from unittest.mock import patch

    cb = make_breaker(failure_threshold=3)
    assert cb._probing is False

    with patch("api.circuit_breaker._record_cancelled") as mock_record:
        cb.record_cancelled()
        mock_record.assert_not_called()


def test_record_cancelled_noop_when_not_probing():
    """record_cancelled is safe to call when _probing is False (non-probe caller)."""
    cb = make_breaker(failure_threshold=3)
    assert cb._probing is False
    cb.record_cancelled()  # must not raise or corrupt state
    assert cb._probing is False
    assert cb.state == CircuitState.CLOSED


def test_record_cancelled_does_not_open_circuit_after_n_disconnects():
    """Five client disconnects must not open a healthy circuit."""
    cb = make_breaker(failure_threshold=5, recovery_timeout_s=0.01)
    import time

    for _ in range(5):
        cb._state = CircuitState.HALF_OPEN
        cb._probing = True
        cb._probe_started_at = time.monotonic()
        cb.record_cancelled()

    # After 5 cancellations, the circuit must still not be OPEN.
    assert cb.state != CircuitState.OPEN
    assert cb._failure_count == 0  # cancellations never increment failure count


@pytest.mark.asyncio
async def test_half_open_probe_cancelled_allows_next_caller_to_probe():
    """After a probe cancellation, the next caller enters HALF_OPEN (not fast-failed)."""
    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    # Simulate probe cancellation: manually acquire the probe state then cancel.
    import time

    cb._state = CircuitState.HALF_OPEN
    cb._probing = True
    cb._probe_started_at = time.monotonic()
    cb.record_cancelled()

    # The next call should be allowed through as a probe (not fast-failed).
    result = await cb.call(_succeed)
    assert result == "ok"


# ── cancellation through .call() ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_inner_cancelled_releases_probe():
    """CancelledError during a HALF_OPEN probe via .call() releases _probing without failure."""
    cancel_entered = asyncio.Event()

    cb = make_breaker(failure_threshold=1, recovery_timeout_s=0.01)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    await asyncio.sleep(0.05)

    async def _slow():
        cancel_entered.set()
        await asyncio.sleep(100)

    task = asyncio.create_task(cb.call(_slow))
    await cancel_entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cb._probing is False  # probe lock released by record_cancelled()
    assert cb._failure_count == 1  # cancellation did not increment failure count
    assert cb.state == CircuitState.HALF_OPEN  # still HALF_OPEN; next caller can probe


# ── metric emission: fast-fails, inflight, state ──────────────────────────────


def test_record_fast_fail_called_when_circuit_open():
    """_record_fast_fail is invoked when an OPEN circuit rejects a call."""
    import time

    cb = make_breaker(failure_threshold=1, recovery_timeout_s=999)
    cb._state = CircuitState.OPEN
    cb._opened_at = time.monotonic()

    with patch("api.circuit_breaker._record_fast_fail") as mock_ff:
        with pytest.raises(CircuitOpenError):
            cb._check_and_maybe_probe()
        mock_ff.assert_called_once_with(cb.name)


@pytest.mark.asyncio
async def test_inflight_metric_incremented_and_decremented_on_call():
    """When max_concurrency is set, in-flight metric goes +1/-1 around the call."""
    cb = make_breaker(max_concurrency=5)
    deltas: list[int] = []
    cb._emit_inflight_metric = lambda d: deltas.append(d)

    await cb.call(_succeed)

    assert deltas == [1, -1]


def test_emit_state_metric_called_on_transition():
    """_emit_state_metric is called when the circuit transitions state."""
    with patch("api.circuit_breaker.CircuitBreaker._emit_state_metric") as mock_emit:
        cb = CircuitBreaker("test_state_emit")
        mock_emit.assert_called_once_with(CircuitState.CLOSED)
        mock_emit.reset_mock()

        cb._transition(CircuitState.OPEN)
        mock_emit.assert_called_once_with(CircuitState.OPEN)


# ── CircuitOpenError attributes ──────────────────────────────────────────────


def test_circuit_open_error_attributes():
    exc = CircuitOpenError("svc", 42.5)
    assert exc.breaker_name == "svc"
    assert exc.retry_after_s == 42.5
    assert "svc" in str(exc)


# ── named module-level breakers exist ────────────────────────────────────────


def test_named_breakers_are_instances():
    from api.circuit_breaker import (
        anthropic_breaker,
        clerk_jwks_breaker,
        licensed_overlay_breaker,
        postmark_breaker,
        stripe_breaker,
    )

    for breaker in (
        anthropic_breaker,
        stripe_breaker,
        postmark_breaker,
        clerk_jwks_breaker,
        licensed_overlay_breaker,
    ):
        assert isinstance(breaker, CircuitBreaker)
        assert breaker.state == CircuitState.CLOSED
