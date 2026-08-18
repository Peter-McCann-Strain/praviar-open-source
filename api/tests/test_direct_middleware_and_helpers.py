"""Direct coroutine tests for RequestLoggingMiddleware and Stripe webhook helpers.

Calls coroutines directly (no TestClient / background thread) so
pytest-cov tracks coverage in the same event loop as the test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── RequestLoggingMiddleware ─────────────────────────────────────────────────


def _make_scope_request(path: str = "/test", method: str = "GET") -> MagicMock:
    req = MagicMock()
    req.method = method
    req.url = MagicMock()
    req.url.path = path
    req.state = MagicMock()
    req.headers = {}
    return req


@pytest.mark.asyncio
async def test_logging_middleware_sets_request_id_on_state():
    from starlette.responses import Response

    from api.app_lifecycle import RequestLoggingMiddleware

    app_mock = MagicMock()
    mw = RequestLoggingMiddleware(app_mock)

    response = Response(content=b"ok", status_code=200)
    call_next = AsyncMock(return_value=response)
    request = _make_scope_request()

    await mw.dispatch(request, call_next)

    assert request.state.request_id is not None
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_logging_middleware_uses_existing_request_id_header():
    from starlette.responses import Response

    from api.app_lifecycle import RequestLoggingMiddleware

    app_mock = MagicMock()
    mw = RequestLoggingMiddleware(app_mock)

    request = _make_scope_request()
    request.headers = {"X-Request-ID": "fixed-id-123"}
    response = Response(content=b"ok", status_code=200)
    call_next = AsyncMock(return_value=response)

    await mw.dispatch(request, call_next)

    assert request.state.request_id == "fixed-id-123"


@pytest.mark.asyncio
async def test_logging_middleware_sets_x_request_id_response_header():
    from starlette.responses import Response

    from api.app_lifecycle import RequestLoggingMiddleware

    app_mock = MagicMock()
    mw = RequestLoggingMiddleware(app_mock)

    request = _make_scope_request()
    request.headers = {"X-Request-ID": "resp-hdr-test"}
    response = Response(content=b"ok", status_code=200)
    call_next = AsyncMock(return_value=response)

    result = await mw.dispatch(request, call_next)

    assert result.headers.get("X-Request-ID") == "resp-hdr-test"


@pytest.mark.asyncio
async def test_logging_middleware_reraises_exception():
    from api.app_lifecycle import RequestLoggingMiddleware

    app_mock = MagicMock()
    mw = RequestLoggingMiddleware(app_mock)

    request = _make_scope_request()
    call_next = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await mw.dispatch(request, call_next)


@pytest.mark.asyncio
async def test_logging_middleware_404_response_logged():
    from starlette.responses import Response

    from api.app_lifecycle import RequestLoggingMiddleware

    app_mock = MagicMock()
    mw = RequestLoggingMiddleware(app_mock)

    request = _make_scope_request(path="/missing")
    response = Response(content=b"nope", status_code=404)
    call_next = AsyncMock(return_value=response)

    result = await mw.dispatch(request, call_next)

    assert result.status_code == 404


# ── Stripe webhook: _parse_org_uuid ─────────────────────────────────────────


def _parse_org_uuid():
    from api.routes.webhooks_stripe import _parse_org_uuid as fn

    return fn


def test_parse_org_uuid_none_returns_none():
    assert _parse_org_uuid()(None) is None


def test_parse_org_uuid_empty_string_returns_none():
    assert _parse_org_uuid()("") is None


def test_parse_org_uuid_valid_uuid_returns_uuid():
    uid = str(uuid.uuid4())
    result = _parse_org_uuid()(uid)
    assert isinstance(result, uuid.UUID)
    assert str(result) == uid


def test_parse_org_uuid_invalid_string_returns_none():
    assert _parse_org_uuid()("not-a-uuid") is None


def test_parse_org_uuid_integer_returns_none():
    assert _parse_org_uuid()(42) is None  # type: ignore[arg-type]


# ── Stripe webhook: _record_stripe_event_receipt ─────────────────────────────


def _make_mock_session(existing=None):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=existing)
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_record_event_receipt_new_event_returns_new_status():
    from api.routes.webhooks_stripe import (
        StripeWebhookReceiptStatus,
        _record_stripe_event_receipt,
    )

    session = _make_mock_session(existing=None)
    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_new", event_type="customer.created", org_id=None
        )
    assert result.status == StripeWebhookReceiptStatus.NEW
    assert result.execution_id is not None
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_receipt_existing_processed_returns_duplicate_status():
    from api.routes.webhooks_stripe import (
        StripeWebhookReceiptStatus,
        _record_stripe_event_receipt,
    )

    existing = MagicMock()
    existing.processed = True
    existing.org_id = None
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_dup", event_type="customer.created", org_id=None
        )
    assert result.status == StripeWebhookReceiptStatus.DUPLICATE_PROCESSED
    assert result.execution_id is None


@pytest.mark.asyncio
async def test_record_event_receipt_existing_not_processed_with_active_lease_returns_in_progress():
    from api.routes.webhooks_stripe import (
        StripeWebhookReceiptStatus,
        _record_stripe_event_receipt,
    )

    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = uuid.uuid4()
    existing.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_pending", event_type="customer.created", org_id=None
        )
    assert result.status == StripeWebhookReceiptStatus.IN_PROGRESS
    assert result.execution_id is None


@pytest.mark.asyncio
async def test_record_event_receipt_existing_expired_lease_claims_stale_retry():
    from api.routes.webhooks_stripe import (
        STRIPE_WEBHOOK_PROCESSING_LEASE_SECONDS,
        StripeWebhookReceiptStatus,
        _record_stripe_event_receipt,
    )

    expired_lease = datetime.now(UTC) - timedelta(seconds=1)
    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = uuid.uuid4()
    existing.processing_lease_expires_at = expired_lease
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_retry", event_type="customer.created", org_id=None
        )

    assert result.status == StripeWebhookReceiptStatus.STALE_RETRY
    assert result.execution_id == existing.processing_execution_id
    assert existing.processing_lease_expires_at > datetime.now(UTC)
    assert (
        existing.processing_lease_expires_at - datetime.now(UTC)
    ).total_seconds() <= STRIPE_WEBHOOK_PROCESSING_LEASE_SECONDS
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_receipt_updates_org_id_when_missing():
    from api.routes.webhooks_stripe import _record_stripe_event_receipt

    uid = str(uuid.uuid4())
    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = uuid.uuid4()
    existing.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _record_stripe_event_receipt(
            event_id="evt_upd", event_type="customer.created", org_id=uid
        )
    assert existing.org_id is not None
    session.commit.assert_awaited()


# ── Stripe webhook: _mark_stripe_event_processed ─────────────────────────────


@pytest.mark.asyncio
async def test_mark_processed_when_existing_record():
    from api.routes.webhooks_stripe import _mark_stripe_event_processed

    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = uuid.uuid4()
    existing.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _mark_stripe_event_processed(event_id="evt_mark", org_id=None)

    assert existing.processed is True
    assert existing.processing_execution_id is None
    assert existing.processing_lease_expires_at is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_processed_when_no_existing_record():
    from api.routes.webhooks_stripe import _mark_stripe_event_processed

    session = _make_mock_session(existing=None)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _mark_stripe_event_processed(event_id="evt_new2", org_id=None)

    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_receipt_integrity_error_falls_back_to_requery():
    """IntegrityError on commit triggers rollback + re-query (lines 74-81)."""
    from sqlalchemy.exc import IntegrityError

    from api.routes.webhooks_stripe import _record_stripe_event_receipt

    refetched = MagicMock()
    refetched.processed = True
    refetched.processing_execution_id = None
    refetched.processing_lease_expires_at = None

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.rollback = AsyncMock()

    # _bind_org_to_webhook_session consumes the first execute; then the initial
    # query returns None. After IntegrityError + rollback, the RLS context is
    # rebound before the re-query returns the refetched duplicate.
    bind_result = MagicMock()
    rebound_result = MagicMock()
    result_none = MagicMock()
    result_none.scalar_one_or_none = MagicMock(return_value=None)
    result_refetch = MagicMock()
    result_refetch.scalar_one_or_none = MagicMock(return_value=refetched)
    session.execute = AsyncMock(
        side_effect=[bind_result, result_none, rebound_result, result_refetch]
    )
    session.commit = AsyncMock(side_effect=IntegrityError("dup", {}, Exception()))

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_race", event_type="customer.created", org_id=None
        )

    from api.routes.webhooks_stripe import StripeWebhookReceiptStatus

    assert result.status == StripeWebhookReceiptStatus.DUPLICATE_PROCESSED
    session.rollback.assert_awaited_once()
    assert "set_config" in str(session.execute.await_args_list[2].args[0])


@pytest.mark.asyncio
async def test_record_event_receipt_integrity_error_refetches_active_lease_as_in_progress():
    from sqlalchemy.exc import IntegrityError

    from api.routes.webhooks_stripe import (
        StripeWebhookReceiptStatus,
        _record_stripe_event_receipt,
    )

    refetched = MagicMock()
    refetched.processed = False
    refetched.org_id = None
    refetched.processing_execution_id = uuid.uuid4()
    refetched.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.rollback = AsyncMock()

    # _bind_org_to_webhook_session consumes the first execute; then the initial
    # query returns None. After IntegrityError + rollback, the RLS context is
    # rebound before the re-query returns the in-progress duplicate.
    bind_result = MagicMock()
    rebound_result = MagicMock()
    result_none = MagicMock()
    result_none.scalar_one_or_none = MagicMock(return_value=None)
    result_refetch = MagicMock()
    result_refetch.scalar_one_or_none = MagicMock(return_value=refetched)
    session.execute = AsyncMock(
        side_effect=[bind_result, result_none, rebound_result, result_refetch]
    )
    session.commit = AsyncMock(side_effect=IntegrityError("dup", {}, Exception()))

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        result = await _record_stripe_event_receipt(
            event_id="evt_race_active", event_type="customer.created", org_id=None
        )

    assert result.status == StripeWebhookReceiptStatus.IN_PROGRESS
    session.rollback.assert_awaited_once()
    assert "set_config" in str(session.execute.await_args_list[2].args[0])


@pytest.mark.asyncio
async def test_record_event_receipt_integrity_error_without_refetched_duplicate_propagates():
    from sqlalchemy.exc import IntegrityError

    from api.routes.webhooks_stripe import _record_stripe_event_receipt

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.rollback = AsyncMock()

    result_none_initial = MagicMock()
    result_none_initial.scalar_one_or_none = MagicMock(return_value=None)
    result_none_refetch = MagicMock()
    result_none_refetch.scalar_one_or_none = MagicMock(return_value=None)
    bind_result = MagicMock()
    rebound_result = MagicMock()
    session.execute = AsyncMock(
        side_effect=[bind_result, result_none_initial, rebound_result, result_none_refetch]
    )
    session.commit = AsyncMock(side_effect=IntegrityError("fk failed", {}, Exception()))

    with (
        patch("api.routes.webhooks_stripe.async_session_factory", return_value=session),
        pytest.raises(IntegrityError),
    ):
        await _record_stripe_event_receipt(
            event_id="evt_fk_failure",
            event_type="customer.created",
            org_id=str(uuid.uuid4()),
        )

    session.rollback.assert_awaited_once()
    assert "set_config" in str(session.execute.await_args_list[2].args[0])


@pytest.mark.asyncio
async def test_mark_processed_updates_org_id_on_existing():
    """Covers the branch where existing.org_id is None and org_id is provided (line 112)."""
    import uuid

    from api.routes.webhooks_stripe import _mark_stripe_event_processed

    uid = str(uuid.uuid4())
    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = uuid.uuid4()
    existing.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _mark_stripe_event_processed(event_id="evt_orgupd", org_id=uid)

    assert existing.processed is True
    assert existing.org_id is not None
    assert existing.processing_execution_id is None
    assert existing.processing_lease_expires_at is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_stripe_event_receipt_clears_unprocessed_lease():
    from api.routes.webhooks_stripe import _release_stripe_event_receipt

    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    execution_id = uuid.uuid4()
    existing.processing_execution_id = execution_id
    existing.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _release_stripe_event_receipt(
            event_id="evt_release",
            org_id=None,
            execution_id=execution_id,
        )

    assert existing.processing_execution_id is None
    assert existing.processing_lease_expires_at is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_stripe_event_receipt_preserves_newer_owner_lease():
    from api.routes.webhooks_stripe import _release_stripe_event_receipt

    current_execution_id = uuid.uuid4()
    stale_execution_id = uuid.uuid4()
    active_lease = datetime.now(UTC) + timedelta(minutes=5)
    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = current_execution_id
    existing.processing_lease_expires_at = active_lease
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        await _release_stripe_event_receipt(
            event_id="evt_release_stale",
            org_id=None,
            execution_id=stale_execution_id,
        )

    assert existing.processing_execution_id == current_execution_id
    assert existing.processing_lease_expires_at == active_lease
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_processed_preserves_newer_owner_lease():
    from api.routes.webhooks_stripe import _mark_stripe_event_processed

    current_execution_id = uuid.uuid4()
    stale_execution_id = uuid.uuid4()
    active_lease = datetime.now(UTC) + timedelta(minutes=5)
    existing = MagicMock()
    existing.processed = False
    existing.org_id = None
    existing.processing_execution_id = current_execution_id
    existing.processing_lease_expires_at = active_lease
    session = _make_mock_session(existing=existing)

    with patch("api.routes.webhooks_stripe.async_session_factory", return_value=session):
        marked = await _mark_stripe_event_processed(
            event_id="evt_mark_stale",
            org_id=None,
            execution_id=stale_execution_id,
        )

    assert marked is False
    assert existing.processed is False
    assert existing.processing_execution_id == current_execution_id
    assert existing.processing_lease_expires_at == active_lease
    session.commit.assert_not_awaited()
