"""Tests for the shared HTTP retry/jitter utility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from api.http_utils import retry_with_jitter


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://example.com/api")
    return httpx.Response(status_code=status_code, request=request)


def _raise_status(status_code: int):
    response = _make_response(status_code)
    raise httpx.HTTPStatusError(f"HTTP {status_code}", request=response.request, response=response)


# ── retryable status codes ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_retries_on_retryable_status(status: int):
    """Retryable status codes (429/502/503/504) trigger retry and eventually succeed."""
    call_count = 0

    async def _fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            _raise_status(status)
        return "ok"

    with patch("asyncio.sleep"):  # suppress back-off sleep in tests
        result = await retry_with_jitter(_fn, max_attempts=3)

    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_exhausts_attempts_and_reraises_last_exception():
    """When all attempts fail with a retryable status, last_exc is re-raised."""

    async def _always_fail():
        _raise_status(503)

    with patch("asyncio.sleep"), pytest.raises(httpx.HTTPStatusError) as exc_info:
        await retry_with_jitter(_always_fail, max_attempts=3)

    assert exc_info.value.response.status_code == 503


# ── non-retryable status codes ────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
async def test_raises_immediately_on_non_retryable_status(status: int):
    """Non-retryable HTTP status codes propagate on the first attempt."""
    call_count = 0

    async def _fn():
        nonlocal call_count
        call_count += 1
        _raise_status(status)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_with_jitter(_fn, max_attempts=3)

    assert call_count == 1  # no retry


# ── network errors ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retries_on_request_error():
    """Network-layer errors (httpx.RequestError) trigger retry."""
    call_count = 0

    async def _fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectError("refused")
        return "ok"

    with patch("asyncio.sleep"):
        result = await retry_with_jitter(_fn, max_attempts=3)

    assert result == "ok"
    assert call_count == 2


# ── non-retryable exceptions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_raises_immediately_on_non_retryable_exception():
    """Non-HTTP, non-network exceptions propagate without retry."""
    call_count = 0

    async def _fn():
        nonlocal call_count
        call_count += 1
        raise ValueError("unexpected")

    with pytest.raises(ValueError):
        await retry_with_jitter(_fn, max_attempts=3)

    assert call_count == 1


# ── metric emission ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emits_status_code_metric_on_retryable_http_error():
    """http_retries_total is incremented with reason='status_code' on retryable HTTP errors."""
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels

    async def _fn():
        _raise_status(429)

    with (
        patch("asyncio.sleep"),
        patch("api.metrics.http_retries_total", mock_counter),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await retry_with_jitter(_fn, max_attempts=2, caller="test.caller")

    mock_counter.labels.assert_any_call(caller="test.caller", reason="status_code")
    assert mock_labels.inc.call_count == 3  # 2 failed attempts + 1 exhausted


@pytest.mark.asyncio
async def test_emits_network_error_metric_on_request_error():
    """http_retries_total is incremented with reason='network_error' on network failures."""
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels

    async def _fn():
        raise httpx.ConnectError("refused")

    with (
        patch("asyncio.sleep"),
        patch("api.metrics.http_retries_total", mock_counter),
        pytest.raises(httpx.ConnectError),
    ):
        await retry_with_jitter(_fn, max_attempts=2, caller="test.network")

    mock_counter.labels.assert_any_call(caller="test.network", reason="network_error")
    assert mock_labels.inc.call_count == 3  # 2 failed attempts + 1 exhausted


@pytest.mark.asyncio
async def test_emits_exhausted_metric_when_all_attempts_fail():
    """http_retries_total{reason='exhausted'} is incremented once when all attempts are used up."""
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels

    async def _fn():
        _raise_status(503)

    with (
        patch("asyncio.sleep"),
        patch("api.metrics.http_retries_total", mock_counter),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await retry_with_jitter(_fn, max_attempts=2, caller="test.exhausted")

    reasons = [c.kwargs["reason"] for c in mock_counter.labels.call_args_list]
    assert "exhausted" in reasons
    assert reasons.count("exhausted") == 1


@pytest.mark.asyncio
async def test_emits_recovered_metric_when_retry_succeeds():
    """http_retries_total{reason='recovered'} is emitted when a retry attempt succeeds."""
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    call_count = 0

    async def _fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            _raise_status(503)
        return "ok"

    with patch("asyncio.sleep"), patch("api.metrics.http_retries_total", mock_counter):
        result = await retry_with_jitter(_fn, max_attempts=3, caller="test.recovered")

    assert result == "ok"
    reasons = [c.kwargs["reason"] for c in mock_counter.labels.call_args_list]
    assert "recovered" in reasons
    assert "exhausted" not in reasons


@pytest.mark.asyncio
async def test_no_recovered_metric_on_first_attempt_success():
    """No metric is emitted when the first attempt succeeds (no retry needed)."""
    mock_counter = MagicMock()
    mock_counter.labels.return_value = MagicMock()

    async def _fn():
        return "ok"

    with patch("api.metrics.http_retries_total", mock_counter):
        result = await retry_with_jitter(_fn, max_attempts=3, caller="test.clean")

    assert result == "ok"
    mock_counter.labels.assert_not_called()
