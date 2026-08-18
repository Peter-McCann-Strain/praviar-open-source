"""Focused tests for pure Stripe billing value builders."""

from __future__ import annotations

import uuid

import pytest

from api.errors import APIError
from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_checkout import (
    add_checkout_session_id_placeholder,
    build_checkout_session_audit_details,
    build_checkout_session_line_items,
    build_credit_pack_checkout_return_url,
    build_portal_session_audit_details,
    resolve_checkout_return_urls,
)


def test_add_checkout_session_id_placeholder_is_literal_and_server_owned():
    assert add_checkout_session_id_placeholder(
        "https://app.example.com/analyses/new"
        "?resume=credit_checkout&checkout_session_id=forged#review"
    ) == (
        "https://app.example.com/analyses/new"
        "?resume=credit_checkout&checkout_session_id={CHECKOUT_SESSION_ID}#review"
    )


def test_credit_pack_checkout_return_url_is_credit_specific():
    assert build_credit_pack_checkout_return_url(
        lambda: "https://app.example.com/",
        credit_pack_id=CreditPackId.PORTFOLIO_5,
        state="success",
    ) == ("https://app.example.com/billing?checkout=success&credit_pack=portfolio_5&intent=credits")


def test_resolve_checkout_return_urls_uses_billing_origin_fallbacks():
    assert resolve_checkout_return_urls(
        lambda: "https://app.example.com",
        success_url="",
        cancel_url="",
    ) == (
        "https://app.example.com/billing?checkout=success",
        "https://app.example.com/billing?checkout=cancelled",
    )


def test_resolve_checkout_return_urls_accepts_same_origin_custom_paths():
    assert resolve_checkout_return_urls(
        lambda: "https://app.example.com",
        success_url="https://app.example.com/settings/billing/success",
        cancel_url="https://app.example.com/settings/billing/cancel",
    ) == (
        "https://app.example.com/settings/billing/success",
        "https://app.example.com/settings/billing/cancel",
    )


def test_resolve_checkout_return_urls_treats_default_port_as_same_origin():
    assert resolve_checkout_return_urls(
        lambda: "https://app.example.com",
        success_url="https://app.example.com:443/settings/billing/success",
        cancel_url="https://app.example.com/settings/billing/cancel",
    ) == (
        "https://app.example.com:443/settings/billing/success",
        "https://app.example.com/settings/billing/cancel",
    )


def test_resolve_checkout_return_urls_strips_trailing_origin_slash_for_fallbacks():
    assert resolve_checkout_return_urls(
        lambda: "https://app.example.com/",
        success_url="",
        cancel_url="",
    ) == (
        "https://app.example.com/billing?checkout=success",
        "https://app.example.com/billing?checkout=cancelled",
    )


def test_resolve_checkout_return_urls_rejects_external_origin():
    with pytest.raises(APIError) as exc_info:
        resolve_checkout_return_urls(
            lambda: "https://app.example.com",
            success_url="https://evil.example/phish",
            cancel_url="https://app.example.com/settings/billing",
        )

    assert exc_info.value.status == 400


def test_resolve_checkout_return_urls_rejects_relative_url():
    with pytest.raises(APIError) as exc_info:
        resolve_checkout_return_urls(
            lambda: "https://app.example.com",
            success_url="/settings/billing",
            cancel_url="https://app.example.com/settings/billing",
        )

    assert exc_info.value.status == 400


@pytest.mark.parametrize(
    "success_url",
    [
        "https://app.example.com:notaport/settings/billing",
        "https://app.example.com:99999/settings/billing",
    ],
)
def test_resolve_checkout_return_urls_rejects_malformed_port_as_api_error(success_url: str):
    with pytest.raises(APIError) as exc_info:
        resolve_checkout_return_urls(
            lambda: "https://app.example.com",
            success_url=success_url,
            cancel_url="https://app.example.com/settings/billing",
        )

    assert exc_info.value.status == 400


def test_build_checkout_session_line_items_wraps_price_id():
    assert build_checkout_session_line_items("price_pro") == [{"price": "price_pro", "quantity": 1}]


def test_build_checkout_session_audit_details_serializes_plan_and_urls():
    assert build_checkout_session_audit_details(
        plan_id=PlanTier.STARTER,
        session_id="cs_test",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    ) == {
        "plan_id": "starter",
        "session_id": "cs_test",
        "success_url": "https://app.example.com/success",
        "cancel_url": "https://app.example.com/cancel",
    }


def test_build_portal_session_audit_details_wraps_session_id():
    portal_session_id = str(uuid.uuid4())

    assert build_portal_session_audit_details(
        portal_session_id=portal_session_id,
    ) == {"portal_session_id": portal_session_id}
