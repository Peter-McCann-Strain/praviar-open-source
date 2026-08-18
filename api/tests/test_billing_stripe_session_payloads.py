"""Focused tests for Stripe session payload builders."""

from __future__ import annotations

import uuid

from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_checkout import (
    build_checkout_session_payload,
    build_credit_pack_checkout_session_payload,
    build_portal_session_payload,
)


def test_build_checkout_session_payload_shapes_stripe_kwargs() -> None:
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    assert build_checkout_session_payload(
        customer_id="cus_test",
        org_id=org_id,
        user_id=user_id,
        plan_id=PlanTier.PRO,
        price_id="price_pro",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    ) == {
        "mode": "subscription",
        "customer": "cus_test",
        "line_items": [{"price": "price_pro", "quantity": 1}],
        "success_url": "https://app.example.com/success",
        "cancel_url": "https://app.example.com/cancel",
        "metadata": {
            "schema_version": "checkout.session.v1",
            "purpose": "subscription_checkout",
            "org_id": str(org_id),
            "user_id": str(user_id),
            "plan_id": "pro",
        },
        "allow_promotion_codes": True,
    }


def test_build_credit_pack_checkout_session_payload_shapes_stripe_kwargs() -> None:
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    assert build_credit_pack_checkout_session_payload(
        customer_id="cus_test",
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=CreditPackId.PORTFOLIO_5,
        credits=5,
        price_id="price_credit_portfolio",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    ) == {
        "mode": "payment",
        "customer": "cus_test",
        "line_items": [{"price": "price_credit_portfolio", "quantity": 1}],
        "success_url": "https://app.example.com/success",
        "cancel_url": "https://app.example.com/cancel",
        "metadata": {
            "schema_version": "checkout.session.v1",
            "purpose": "credit_pack_checkout",
            "org_id": str(org_id),
            "user_id": str(user_id),
            "credit_pack_id": "portfolio_5",
            "credits": "5",
        },
        "custom_text": {
            "submit": {
                "message": (
                    "Report Credit Packs are prepaid capacity. Included Report Credits "
                    "are used first; purchased credits are generally non-refundable "
                    "except as required by law or expressly stated in an order form."
                )
            }
        },
        "invoice_creation": {
            "enabled": True,
            "invoice_data": {
                "description": "5 Praviar Report Credits",
                "footer": (
                    "1 Report Credit = 1 first-pass FTO report request for 1 compound. "
                    "Reports are informational tools and not legal advice."
                ),
                "metadata": {
                    "org_id": str(org_id),
                    "user_id": str(user_id),
                    "credit_pack_id": "portfolio_5",
                    "credits": "5",
                },
            },
        },
        "allow_promotion_codes": True,
    }


def test_build_portal_session_payload_shapes_stripe_kwargs() -> None:
    assert build_portal_session_payload(
        customer_id="cus_test",
        return_url="https://app.example.com/settings/billing",
    ) == {
        "customer": "cus_test",
        "return_url": "https://app.example.com/settings/billing",
    }
