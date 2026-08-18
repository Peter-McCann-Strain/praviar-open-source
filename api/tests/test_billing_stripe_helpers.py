"""Focused tests for internal Stripe billing helpers."""

from __future__ import annotations

import uuid

from api.schemas.billing import PlanTier
from api.services.billing_checkout import (
    build_checkout_return_url,
    build_checkout_session_metadata,
    build_empty_invoice_payload,
    build_portal_return_url,
)


def test_build_checkout_session_metadata_serializes_identifiers():
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    assert build_checkout_session_metadata(
        org_id=org_id,
        user_id=user_id,
        plan_id=PlanTier.PRO,
    ) == {
        "schema_version": "checkout.session.v1",
        "purpose": "subscription_checkout",
        "org_id": str(org_id),
        "user_id": str(user_id),
        "plan_id": "pro",
    }


def test_build_checkout_return_url_adds_billing_path():
    assert build_checkout_return_url(lambda: "https://app.example.com", state="success") == (
        "https://app.example.com/billing?checkout=success"
    )


def test_build_portal_return_url_points_at_billing_path():
    assert build_portal_return_url(lambda: "https://app.example.com") == (
        "https://app.example.com/billing"
    )


def test_build_empty_invoice_payload_is_stable():
    assert build_empty_invoice_payload() == {"invoices": [], "has_more": False}
