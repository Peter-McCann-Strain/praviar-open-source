"""Direct handler tests for the Stripe webhook route.

Tests call the handler coroutine directly so pytest-cov tracks coverage
in the same thread without background-thread tracing issues.
Covers the previously-uncovered lines in routes/webhooks_stripe.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.webhooks_stripe import StripeWebhookReceiptStatus


def _handler():
    from api.routes.webhooks_stripe import stripe_webhook

    return stripe_webhook


def _make_request(body: bytes = b"{}", sig_header: str = "t=1,v1=abc") -> MagicMock:
    req = MagicMock()
    req.body = AsyncMock(return_value=body)
    req.headers = {"stripe-signature": sig_header}
    return req


def _make_settings(secret: str = "whsec_test") -> MagicMock:
    s = MagicMock()
    s.stripe_webhook_secret = secret
    return s


@pytest.mark.asyncio
async def test_missing_stripe_secret_raises_500():
    from api.errors import APIError

    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("")),
        pytest.raises(APIError) as exc_info,
    ):
        await _handler()(_make_request())
    assert exc_info.value.status == 500


@pytest.mark.asyncio
async def test_missing_signature_header_raises_401():
    from api.errors import APIError

    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        pytest.raises(APIError) as exc_info,
    ):
        await _handler()(_make_request(sig_header=""))
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_invalid_signature_raises_401():
    import stripe

    from api.errors import APIError

    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        patch.object(
            stripe.Webhook,
            "construct_event",
            side_effect=stripe.SignatureVerificationError("bad sig", sig_header=""),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await _handler()(_make_request())
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_invalid_payload_raises_400():
    import stripe

    from api.errors import APIError

    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        patch.object(stripe.Webhook, "construct_event", side_effect=ValueError("bad payload")),
        pytest.raises(APIError) as exc_info,
    ):
        await _handler()(_make_request())
    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_duplicate_event_returns_ok_with_flag():
    import stripe

    mock_event = {"type": "customer.subscription.updated", "id": "evt_dup", "data": {}}
    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        patch.object(stripe.Webhook, "construct_event", return_value=mock_event),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.DUPLICATE_PROCESSED),
        ),
        patch("api.routes.webhooks_stripe.extract_audit_org_id", return_value=None),
    ):
        result = await _handler()(_make_request())
    assert result["status"] == "ok"
    assert result["duplicate"] is True


@pytest.mark.asyncio
async def test_ignored_event_returns_ignored():
    import stripe

    mock_event = {"type": "payment_method.attached", "id": "evt_123", "data": {}}
    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        patch.object(stripe.Webhook, "construct_event", return_value=mock_event),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch("api.routes.webhooks_stripe.extract_audit_org_id", return_value=None),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value={"status": "ignored", "org_id": None}),
        ),
        patch("api.routes.webhooks_stripe._mark_stripe_event_processed", new=AsyncMock()),
    ):
        result = await _handler()(_make_request())
    assert result["status"] == "ignored"


@pytest.mark.asyncio
async def test_processed_event_returns_ok():
    import stripe

    mock_event = {"type": "customer.subscription.created", "id": "evt_456", "data": {}}
    with (
        patch("api.routes.webhooks_stripe.get_settings", return_value=_make_settings("whsec_test")),
        patch.object(stripe.Webhook, "construct_event", return_value=mock_event),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch("api.routes.webhooks_stripe.extract_audit_org_id", return_value=None),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value={"status": "ok", "org_id": "org_1"}),
        ),
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()),
        patch("api.routes.webhooks_stripe._mark_stripe_event_processed", new=AsyncMock()),
    ):
        result = await _handler()(_make_request())
    assert result["status"] == "ok"
