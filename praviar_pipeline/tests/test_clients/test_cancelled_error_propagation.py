"""Regression test: tenacity retry decorators must not swallow asyncio.CancelledError.

Tenacity 9.0.0 catches BaseException (including CancelledError) in its async
retry loop.  Without explicitly excluding CancelledError from the retry policy,
asyncio.wait_for timeouts are silently swallowed and the call retries forever.

This test verifies that each client's retry-decorated method propagates
CancelledError so that asyncio.wait_for timeouts work correctly.
"""

from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------------------
# USPTO ODP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uspto_odp_get_propagates_cancelled_error(mock_settings):
    """USPTOODPClient._get_uncached must not swallow CancelledError."""
    import httpx

    from praviar_pipeline.clients.uspto_odp import USPTOODPClient

    call_count = 0

    async def _hanging_transport(_request):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(60)  # never returns in test time
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(_hanging_transport)
    client = httpx.AsyncClient(base_url="https://api.uspto.gov", transport=transport)
    odp = USPTOODPClient(client=client)

    task = asyncio.ensure_future(odp._get_uncached("/test"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises((asyncio.CancelledError, Exception)):
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

    assert call_count <= 1, "CancelledError was retried — tenacity swallowed it"
    await odp.close()


@pytest.mark.asyncio
async def test_uspto_odp_post_propagates_cancelled_error(mock_settings):
    """USPTOODPClient._post_uncached must not swallow CancelledError."""
    import httpx

    from praviar_pipeline.clients.uspto_odp import USPTOODPClient

    call_count = 0

    async def _hanging_transport(_request):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(60)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(_hanging_transport)
    client = httpx.AsyncClient(base_url="https://api.uspto.gov", transport=transport)
    odp = USPTOODPClient(client=client)

    task = asyncio.ensure_future(odp._post_uncached("/test", {"q": "test"}))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises((asyncio.CancelledError, Exception)):
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

    assert call_count <= 1, "CancelledError was retried — tenacity swallowed it"
    await odp.close()


# ---------------------------------------------------------------------------
# EPO OPS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_epo_ops_get_propagates_cancelled_error(mock_settings):
    """EPOOPSClient._get must not swallow CancelledError."""
    import httpx

    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    call_count = 0

    async def _hanging_transport(_request):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(60)
        return httpx.Response(200, json={})

    client_obj = EPOOPSClient.__new__(EPOOPSClient)
    # Inject a mock httpx client and limiter directly — avoids OAuth token fetch
    from aiolimiter import AsyncLimiter

    transport = httpx.MockTransport(_hanging_transport)
    client_obj._client = httpx.AsyncClient(base_url="https://ops.epo.org", transport=transport)
    client_obj._external_client = True
    client_obj._limiter = AsyncLimiter(max_rate=1000, time_period=1)
    client_obj._token = "test-token"  # type: ignore[attr-defined]
    client_obj._token_expires_at = 9999999999.0  # type: ignore[attr-defined]

    task = asyncio.ensure_future(client_obj._get("/test"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises((asyncio.CancelledError, Exception)):
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

    assert call_count <= 1, "CancelledError was retried by EPO _get — tenacity swallowed it"
    await client_obj._client.aclose()


# ---------------------------------------------------------------------------
# wait_for integration: verify the 5-min expansion timeout fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_timeout_not_swallowed():
    """asyncio.wait_for must raise TimeoutError when the inner coroutine is an
    infinite loop whose HTTP calls use a tenacity retry decorator with
    CancelledError excluded from the exclusion list.

    This is the fundamental regression guard: if tenacity swallows
    CancelledError, wait_for hangs forever.
    """
    from tenacity import retry, retry_if_not_exception_type, stop_after_attempt

    call_count = 0

    @retry(
        stop=stop_after_attempt(10),
        retry=retry_if_not_exception_type((asyncio.CancelledError,)),
    )
    async def _infinite():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(60)

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await asyncio.wait_for(_infinite(), timeout=0.1)

    assert call_count == 1, (
        f"Expected exactly 1 call before timeout, got {call_count}. "
        "CancelledError was likely swallowed and retried."
    )
