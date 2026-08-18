"""Focused tests for Stripe checkout and portal orchestration."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.errors import APIError
from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_checkout import (
    create_checkout_session_data_impl,
    create_credit_pack_checkout_session_data_impl,
    create_portal_session_data_impl,
)


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_creates_session_and_audits() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_123", url="https://checkout.example.com")

    result = await create_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        plan_id=PlanTier.PRO,
        success_url="",
        cancel_url="",
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        checkout_price_id_fn=MagicMock(return_value="price_pro"),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=AsyncMock(),
        create_checkout_session_fn=MagicMock(return_value=session),
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    assert result == {
        "checkout_url": "https://checkout.example.com",
        "session_id": "cs_123",
    }
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_rolls_back_when_audit_fails() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_123", url="https://checkout.example.com")

    with pytest.raises(RuntimeError, match="audit failed"):
        await create_checkout_session_data_impl(
            db,
            org_id=org_id,
            user_id=user_id,
            plan_id=PlanTier.PRO,
            success_url="",
            cancel_url="",
            request=MagicMock(),
            stripe_secret_key="sk_test",
            get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
            checkout_price_id_fn=MagicMock(return_value="price_pro"),
            get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
            write_audit_log_fn=AsyncMock(side_effect=RuntimeError("audit failed")),
            create_checkout_session_fn=MagicMock(return_value=session),
            billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
            logger=MagicMock(),
        )

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_rolls_back_when_commit_fails() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("commit failed")
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_123", url="https://checkout.example.com")

    with pytest.raises(RuntimeError, match="commit failed"):
        await create_checkout_session_data_impl(
            db,
            org_id=org_id,
            user_id=user_id,
            plan_id=PlanTier.PRO,
            success_url="",
            cancel_url="",
            request=MagicMock(),
            stripe_secret_key="sk_test",
            get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
            checkout_price_id_fn=MagicMock(return_value="price_pro"),
            get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
            write_audit_log_fn=AsyncMock(),
            create_checkout_session_fn=MagicMock(return_value=session),
            billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
            logger=MagicMock(),
        )

    assert db.rollback.await_count >= 1


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_rejects_external_success_url() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    get_or_create_customer = AsyncMock(return_value="cus_123")
    create_checkout_session = MagicMock()

    with pytest.raises(APIError) as exc_info:
        await create_checkout_session_data_impl(
            db,
            org_id=org_id,
            user_id=user_id,
            plan_id=PlanTier.PRO,
            success_url="https://evil.example/phish",
            cancel_url="https://app.example.com/settings/billing",
            request=MagicMock(),
            stripe_secret_key="sk_test",
            get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
            checkout_price_id_fn=MagicMock(return_value="price_pro"),
            get_or_create_customer_fn=get_or_create_customer,
            write_audit_log_fn=AsyncMock(),
            create_checkout_session_fn=create_checkout_session,
            billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
            logger=MagicMock(),
        )

    assert exc_info.value.status == 400
    get_or_create_customer.assert_not_awaited()
    create_checkout_session.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_reuses_idempotency_key_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_123", url="https://checkout.example.com")
    create_checkout_session = MagicMock(return_value=session)

    async def run_twice(_operation_name: str, fn, **_kwargs):
        fn()
        return fn()

    monkeypatch.setattr(
        "api.services.billing_checkout.run_blocking_sdk_call",
        run_twice,
    )

    await create_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        plan_id=PlanTier.PRO,
        success_url="",
        cancel_url="",
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        checkout_price_id_fn=MagicMock(return_value="price_pro"),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=AsyncMock(),
        create_checkout_session_fn=create_checkout_session,
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    idempotency_keys = [
        call.kwargs["idempotency_key"] for call in create_checkout_session.call_args_list
    ]
    assert len(idempotency_keys) == 2
    assert idempotency_keys[0] == idempotency_keys[1]


@pytest.mark.asyncio
async def test_create_credit_pack_checkout_session_data_impl_creates_payment_session() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_credit_123", url="https://checkout.example.com/credits")
    create_checkout_session = MagicMock(return_value=session)
    write_audit_log = AsyncMock()

    result = await create_credit_pack_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=CreditPackId.PORTFOLIO_5,
        success_url="",
        cancel_url="",
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        credit_pack_price_id_fn=MagicMock(return_value="price_credit_portfolio"),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=write_audit_log,
        create_checkout_session_fn=create_checkout_session,
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    assert result == {
        "checkout_url": "https://checkout.example.com/credits",
        "session_id": "cs_credit_123",
    }
    checkout_kwargs = create_checkout_session.call_args.kwargs
    assert checkout_kwargs["mode"] == "payment"
    assert checkout_kwargs["success_url"] == (
        "https://app.example.com/billing"
        "?checkout=success&credit_pack=portfolio_5&intent=credits"
        "&checkout_session_id={CHECKOUT_SESSION_ID}"
    )
    assert checkout_kwargs["cancel_url"] == (
        "https://app.example.com/billing?checkout=cancelled&credit_pack=portfolio_5&intent=credits"
    )
    assert checkout_kwargs["metadata"]["credit_pack_id"] == "portfolio_5"
    assert checkout_kwargs["metadata"]["credits"] == "5"
    assert (
        checkout_kwargs["custom_text"]["submit"]["message"]
        == "Report Credit Packs are prepaid capacity. Included Report Credits "
        "are used first; purchased credits are generally non-refundable "
        "except as required by law or expressly stated in an order form."
    )
    assert checkout_kwargs["invoice_creation"] == {
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
    }
    assert checkout_kwargs["idempotency_key"].startswith(f"credit-pack:{org_id}:{user_id}:")
    assert write_audit_log.await_args.kwargs["action"] == "billing.credit_pack.checkout.started"
    assert write_audit_log.await_args.kwargs["details"]["success_url"].endswith(
        "checkout_session_id={CHECKOUT_SESSION_ID}"
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_credit_pack_checkout_session_data_impl_supports_scale_pack() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    session = MagicMock(id="cs_credit_scale", url="https://checkout.example.com/scale")
    create_checkout_session = MagicMock(return_value=session)

    result = await create_credit_pack_checkout_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=CreditPackId.SCALE_30,
        success_url="",
        cancel_url="",
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        credit_pack_price_id_fn=MagicMock(return_value="price_credit_scale"),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=AsyncMock(),
        create_checkout_session_fn=create_checkout_session,
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    assert result["session_id"] == "cs_credit_scale"
    checkout_kwargs = create_checkout_session.call_args.kwargs
    assert checkout_kwargs["metadata"]["credit_pack_id"] == "scale_30"
    assert checkout_kwargs["metadata"]["credits"] == "30"
    assert checkout_kwargs["line_items"] == [{"price": "price_credit_scale", "quantity": 1}]
    assert checkout_kwargs["invoice_creation"]["invoice_data"]["description"] == (
        "30 Praviar Report Credits"
    )


@pytest.mark.asyncio
async def test_create_portal_session_data_impl_creates_session_and_audits() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    portal = MagicMock(id="bps_123", url="https://portal.example.com")

    result = await create_portal_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=AsyncMock(),
        create_portal_session_fn=MagicMock(return_value=portal),
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    assert result == {"portal_url": "https://portal.example.com"}
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_portal_session_data_impl_rolls_back_when_audit_fails() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    portal = MagicMock(id="bps_123", url="https://portal.example.com")

    with pytest.raises(RuntimeError, match="audit failed"):
        await create_portal_session_data_impl(
            db,
            org_id=org_id,
            user_id=user_id,
            request=MagicMock(),
            stripe_secret_key="sk_test",
            get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
            get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
            write_audit_log_fn=AsyncMock(side_effect=RuntimeError("audit failed")),
            create_portal_session_fn=MagicMock(return_value=portal),
            billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
            logger=MagicMock(),
        )

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_portal_session_data_impl_reuses_idempotency_key_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(id=org_id)
    portal = MagicMock(id="bps_123", url="https://portal.example.com")
    create_portal_session = MagicMock(return_value=portal)

    async def run_twice(_operation_name: str, fn, **_kwargs):
        fn()
        return fn()

    monkeypatch.setattr(
        "api.services.billing_checkout.run_blocking_sdk_call",
        run_twice,
    )

    await create_portal_session_data_impl(
        db,
        org_id=org_id,
        user_id=user_id,
        request=MagicMock(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        get_or_create_customer_fn=AsyncMock(return_value="cus_123"),
        write_audit_log_fn=AsyncMock(),
        create_portal_session_fn=create_portal_session,
        billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
        logger=MagicMock(),
    )

    idempotency_keys = [
        call.kwargs["idempotency_key"] for call in create_portal_session.call_args_list
    ]
    assert len(idempotency_keys) == 2
    assert idempotency_keys[0] == idempotency_keys[1]
