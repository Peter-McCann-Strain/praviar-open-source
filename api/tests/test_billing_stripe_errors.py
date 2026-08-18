"""Focused tests for Stripe billing error helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from api.errors import APIError
from api.services.billing_checkout import (
    build_stripe_api_error,
    build_stripe_sync_error_response,
    log_stripe_operation_error,
)


def test_build_stripe_api_error_standardizes_502_message() -> None:
    error = build_stripe_api_error(
        "create checkout session",
        Exception("sk_test_secret cus_123 https://checkout.stripe.com/session"),
    )

    assert isinstance(error, APIError)
    assert "Failed to create checkout session." in error.detail
    assert "Stripe could not confirm this billing operation" in error.detail
    assert "sk_test_secret" not in error.detail
    assert "cus_123" not in error.detail
    assert "checkout.stripe.com" not in error.detail


def test_build_stripe_sync_error_response_standardizes_error_payload() -> None:
    assert build_stripe_sync_error_response(
        Exception("sk_test_secret cus_123 https://checkout.stripe.com/session"),
    ) == {"error": "Stripe synchronization failed. No billing changes are being claimed."}


def test_log_stripe_operation_error_merges_extra_fields() -> None:
    logger = MagicMock()

    log_stripe_operation_error(
        logger,
        event_name="sync_stripe_error",
        org_id="org_123",
        exc=Exception("sk_test_secret cus_123 https://checkout.stripe.com/session"),
        extra_fields={"subscription_id": "sub_123"},
    )

    logger.error.assert_called_once()
    args, kwargs = logger.error.call_args
    assert args == ("sync_stripe_error",)
    assert kwargs["org_id"] == "org_123"
    assert kwargs["subscription_id"] == "sub_123"
    assert kwargs["error_type"] == "Exception"
    assert "error" not in kwargs
    assert "exc_info" not in kwargs
    assert "sk_test_secret" not in repr(kwargs)
    assert "checkout.stripe.com" not in repr(kwargs)
