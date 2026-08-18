"""Regression tests for Stripe webhook handlers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import api.services.stripe_webhooks as stripe_webhooks_module
from api.db.models import AnalysisCreditLedger, OrgPlan
from api.errors import APIError
from api.routes.webhooks_stripe import (
    STRIPE_WEBHOOK_VERIFY_TIMEOUT_SECONDS,
    StripeWebhookReceipt,
    StripeWebhookReceiptStatus,
    _mark_stripe_event_processed,
    _record_stripe_event_receipt,
    _release_stripe_event_receipt,
    stripe_webhook,
)
from api.schemas.billing import PlanTier
from api.services import billing_webhooks
from api.services.billing import plan_limit_for
from api.services.billing_checkout import build_checkout_session_payload
from api.services.billing_metadata import build_credit_pack_checkout_metadata
from api.services.stripe_webhooks import (
    handle_checkout_completed,
    handle_invoice_payment_failed,
    handle_invoice_payment_succeeded,
    handle_subscription_deleted,
    handle_subscription_updated,
    process_stripe_webhook_event,
)


def _session_ctx(db: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _request(signature: str | None = "sig_test") -> MagicMock:
    request = MagicMock()
    request.body = AsyncMock(return_value=b"{}")
    request.headers = {}
    if signature is not None:
        request.headers["stripe-signature"] = signature
    return request


@pytest.mark.asyncio
async def test_release_stripe_event_receipt_does_not_clear_newer_lease_owner():
    stale_execution_id = uuid.uuid4()
    current_execution_id = uuid.uuid4()
    existing = SimpleNamespace(
        processed=False,
        processing_execution_id=current_execution_id,
        processing_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        org_id=None,
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.routes.webhooks_stripe.async_session_factory",
        return_value=_session_ctx(db),
    ):
        await _release_stripe_event_receipt(
            event_id="evt_retry",
            org_id=str(uuid.uuid4()),
            execution_id=stale_execution_id,
        )

    assert existing.processing_execution_id == current_execution_id
    assert existing.processing_lease_expires_at is not None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_stripe_event_processed_does_not_complete_newer_lease_owner():
    stale_execution_id = uuid.uuid4()
    current_execution_id = uuid.uuid4()
    existing = SimpleNamespace(
        processed=False,
        processing_execution_id=current_execution_id,
        processing_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        org_id=None,
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.routes.webhooks_stripe.async_session_factory",
        return_value=_session_ctx(db),
    ):
        marked = await _mark_stripe_event_processed(
            event_id="evt_retry",
            org_id=str(uuid.uuid4()),
            execution_id=stale_execution_id,
        )

    assert marked is False
    assert existing.processed is False
    assert existing.processing_execution_id == current_execution_id
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_stripe_event_receipt_reraises_non_duplicate_integrity_error():
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = None
    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    bind_result = MagicMock()
    rebound_result = MagicMock()
    db.execute = AsyncMock(
        side_effect=[bind_result, first_result, rebound_result, second_result]
    )
    db.add = MagicMock()
    db.commit = AsyncMock(
        side_effect=IntegrityError("insert failed", params=None, orig=Exception("fk failed"))
    )
    db.rollback = AsyncMock()

    with (
        patch(
            "api.routes.webhooks_stripe.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(IntegrityError, match="insert failed"),
    ):
        await _record_stripe_event_receipt(
            event_id="evt_bad_org",
            event_type="checkout.session.completed",
            org_id=str(uuid.uuid4()),
        )

    db.rollback.assert_awaited_once()
    assert "set_config" in str(db.execute.await_args_list[2].args[0])


@pytest.mark.asyncio
async def test_resolve_receipt_org_id_uses_customer_fallback_for_subscription_event():
    org_id = uuid.uuid4()
    org = SimpleNamespace(
        id=org_id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        resolved = await stripe_webhooks_module.resolve_receipt_org_id(
            "customer.subscription.updated",
            {
                "object": {
                    "id": "sub_test",
                    "customer": "cus_test",
                    "metadata": {},
                }
            },
        )

    assert resolved == str(org_id)


@pytest.mark.asyncio
async def test_resolve_receipt_org_id_rejects_subscription_identity_mismatch():
    org = SimpleNamespace(
        id=uuid.uuid4(),
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_expected",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        resolved = await stripe_webhooks_module.resolve_receipt_org_id(
            "customer.subscription.updated",
            {
                "object": {
                    "id": "sub_injected",
                    "customer": "cus_test",
                    "metadata": {},
                }
            },
        )

    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_receipt_org_id_uses_customer_org_over_poisoned_metadata():
    metadata_org_id = uuid.uuid4()
    customer_org_id = uuid.uuid4()
    org = SimpleNamespace(
        id=customer_org_id,
        stripe_customer_id="cus_real",
        stripe_subscription_id="sub_real",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        resolved = await stripe_webhooks_module.resolve_receipt_org_id(
            "customer.subscription.updated",
            {
                "object": {
                    "id": "sub_real",
                    "customer": "cus_real",
                    "metadata": {"org_id": str(metadata_org_id)},
                }
            },
        )

    assert resolved == str(customer_org_id)


@pytest.mark.asyncio
async def test_checkout_completed_maps_starter_plan_correctly():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.max_analyses_per_month = 3
    user_id = uuid.uuid4()
    checkout_payload = build_checkout_session_payload(
        customer_id="cus_test",
        org_id=org.id,
        user_id=user_id,
        plan_id=PlanTier.STARTER,
        price_id="price_starter",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_checkout_completed(
            {
                "object": {
                    "customer": "cus_test",
                    "subscription": "sub_test",
                    "mode": "subscription",
                    "metadata": checkout_payload["metadata"],
                }
            }
        )

    assert result == {
        "status": "ok",
        "org_id": str(org.id),
        "plan": OrgPlan.STARTER.value,
    }
    assert org.plan == OrgPlan.STARTER
    assert org.stripe_customer_id == "cus_test"
    assert org.stripe_subscription_id == "sub_test"
    assert org.subscription_status == "active"
    assert org.max_analyses_per_month == plan_limit_for(OrgPlan.STARTER.value)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkout_completed_grants_paid_credit_pack():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = None
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=5,
    )

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    ledger_result = MagicMock()
    ledger_result.scalar_one_or_none.return_value = None
    pending_requests_result = MagicMock()
    pending_requests_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            org_result,
            ledger_result,
            pending_requests_result,
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_123",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    assert result == {
        "status": "ok",
        "org_id": str(org.id),
        "credit_pack_id": "portfolio_5",
        "credits": 5,
    }
    assert org.stripe_customer_id == "cus_test"
    ledger = db.add.call_args.args[0]
    assert isinstance(ledger, AnalysisCreditLedger)
    assert ledger.org_id == org.id
    assert ledger.user_id == user_id
    assert ledger.kind == "purchase"
    assert ledger.credits_delta == 5
    assert ledger.credit_pack_id == "portfolio_5"
    assert ledger.stripe_checkout_session_id == "cs_credit_123"
    first_statement = db.execute.await_args_list[0].args[0]
    assert "set_config" in str(first_statement)
    assert "app.current_org_id" in first_statement.compile().params.values()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkout_completed_skips_foreign_payment_checkout_without_credit_pack_purpose():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ) as session_factory:
        result = await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_payment_foreign",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": {
                        "schema_version": "checkout.session.v1",
                        "org_id": str(uuid.uuid4()),
                    },
                }
            }
        )

    assert result == {
        "status": "skipped",
        "reason": "payment checkout session is not a Praviar credit-pack checkout",
    }
    session_factory.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", ["id", "customer", "payment_intent"])
async def test_checkout_completed_rejects_credit_pack_missing_stripe_identity(
    missing_field: str,
):
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = None
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=uuid.uuid4(),
        credit_pack_id="portfolio_5",
        credits=5,
    )
    session = {
        "id": "cs_credit_123",
        "customer": "cus_test",
        "payment_intent": "pi_test",
        "mode": "payment",
        "payment_status": "paid",
        "metadata": metadata,
    }
    session[missing_field] = "  "
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ) as session_factory,
        pytest.raises(ValueError, match="required Stripe identity"),
    ):
        await handle_checkout_completed({"object": session})

    session_factory.assert_not_called()
    assert org.stripe_customer_id is None
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_completed_skips_duplicate_credit_pack_grant():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=5,
    )

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    ledger_result = MagicMock()
    ledger_result.scalar_one_or_none.return_value = SimpleNamespace(
        org_id=org.id,
        user_id=user_id,
        kind="purchase",
        credits_delta=5,
        credit_pack_id="portfolio_5",
        stripe_checkout_session_id="cs_credit_123",
        stripe_payment_intent_id="pi_test",
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), org_result, ledger_result])
    db.add = MagicMock()
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_123",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    assert result["duplicate"] is True
    first_statement = db.execute.await_args_list[0].args[0]
    assert "set_config" in str(first_statement)
    assert "app.current_org_id" in first_statement.compile().params.values()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_completed_rejects_mismatched_existing_credit_purchase() -> None:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=5,
    )
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    ledger_result = MagicMock()
    ledger_result.scalar_one_or_none.return_value = SimpleNamespace(
        org_id=org.id,
        user_id=user_id,
        kind="purchase",
        credits_delta=30,
        credit_pack_id="scale_30",
        stripe_checkout_session_id="cs_credit_123",
        stripe_payment_intent_id="pi_other",
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), org_result, ledger_result])

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(ValueError, match="does not match Stripe checkout event"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_123",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )


def _constraint_integrity_error(constraint_name: str) -> IntegrityError:
    original = SimpleNamespace(
        diag=SimpleNamespace(constraint_name=constraint_name),
    )
    return IntegrityError("insert failed", params=None, orig=original)


@pytest.mark.asyncio
async def test_credit_pack_unique_race_acknowledges_only_matching_purchase() -> None:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=5,
    )
    duplicate = SimpleNamespace(
        org_id=org.id,
        user_id=user_id,
        kind="purchase",
        credits_delta=5,
        credit_pack_id="portfolio_5",
        stripe_checkout_session_id="cs_credit_race",
        stripe_payment_intent_id="pi_test",
    )

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = duplicate
    pending_requests_result = MagicMock()
    pending_requests_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            org_result,
            missing_result,
            pending_requests_result,
            MagicMock(),
            duplicate_result,
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock(
        side_effect=_constraint_integrity_error(
            billing_webhooks.CREDIT_LEDGER_SESSION_UNIQUE_CONSTRAINT
        )
    )
    db.rollback = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_race",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    assert result["duplicate"] is True
    assert db.rollback.await_count >= 1
    assert db.execute.await_count == 6


@pytest.mark.asyncio
async def test_credit_pack_foreign_key_integrity_error_propagates_for_retry() -> None:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=uuid.uuid4(),
        credit_pack_id="portfolio_5",
        credits=5,
    )
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    pending_requests_result = MagicMock()
    pending_requests_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            org_result,
            missing_result,
            pending_requests_result,
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock(
        side_effect=_constraint_integrity_error("analysis_credit_ledger_user_id_fkey")
    )
    db.rollback = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(IntegrityError, match="insert failed"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_fk_failure",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    assert db.rollback.await_count >= 1
    assert db.execute.await_count == 4


@pytest.mark.asyncio
async def test_credit_pack_unique_conflict_with_mismatched_row_propagates() -> None:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=5,
    )
    mismatched = SimpleNamespace(
        org_id=org.id,
        user_id=user_id,
        kind="purchase",
        credits_delta=30,
        credit_pack_id="scale_30",
        stripe_checkout_session_id="cs_credit_mismatch",
        stripe_payment_intent_id="pi_other",
    )
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = mismatched
    pending_requests_result = MagicMock()
    pending_requests_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            org_result,
            missing_result,
            pending_requests_result,
            MagicMock(),
            duplicate_result,
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock(
        side_effect=_constraint_integrity_error(
            billing_webhooks.CREDIT_LEDGER_SESSION_UNIQUE_CONSTRAINT
        )
    )
    db.rollback = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(IntegrityError, match="insert failed"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_mismatch",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    assert db.execute.await_count == 6


@pytest.mark.asyncio
async def test_checkout_completed_rejects_credit_pack_metadata_credit_mismatch():
    org = MagicMock()
    org.id = uuid.uuid4()
    user_id = uuid.uuid4()
    metadata = build_credit_pack_checkout_metadata(
        org_id=org.id,
        user_id=user_id,
        credit_pack_id="portfolio_5",
        credits=30,
    )

    db = AsyncMock()
    db.commit = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(ValueError, match="configured pack size"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "id": "cs_credit_tampered",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": metadata,
                }
            }
        )

    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_completed_rejects_legacy_untyped_plan_metadata():
    org = MagicMock()
    org.id = uuid.uuid4()
    db = AsyncMock()
    db.commit = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(ValidationError, match="plan_id"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "customer": "cus_test",
                    "subscription": "sub_test",
                    "mode": "subscription",
                    "metadata": {
                        "org_id": str(org.id),
                        "plan": "starter",
                    },
                }
            }
        )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_completed_rolls_back_when_commit_fails():
    org = MagicMock()
    org.id = uuid.uuid4()
    user_id = uuid.uuid4()
    checkout_payload = build_checkout_session_payload(
        customer_id="cus_test",
        org_id=org.id,
        user_id=user_id,
        plan_id=PlanTier.STARTER,
        price_id="price_starter",
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock(side_effect=SQLAlchemyError("commit failed"))
    db.rollback = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(SQLAlchemyError, match="commit failed"),
    ):
        await handle_checkout_completed(
            {
                "object": {
                    "customer": "cus_test",
                    "subscription": "sub_test",
                    "mode": "subscription",
                    "metadata": checkout_payload["metadata"],
                }
            }
        )

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_deleted_resolves_org_via_typed_customer_id():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.PRO
    org.stripe_customer_id = "cus_test"
    org.stripe_subscription_id = "sub_test"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_deleted(
            {
                "object": {
                    "id": "sub_test",
                    "customer": "cus_test",
                    "metadata": {},
                }
            }
        )

    assert result == {"status": "ok", "org_id": str(org.id)}
    assert org.plan == OrgPlan.FREE
    assert org.max_analyses_per_month == plan_limit_for(OrgPlan.FREE.value)
    assert org.subscription_status == "canceled"
    assert org.stripe_subscription_id is None
    assert org.current_period_end is None
    assert org.cancel_at_period_end is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_deleted_rolls_back_when_commit_fails():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    org.stripe_subscription_id = "sub_test"
    org.stripe_subscription_id = "sub_test"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock(side_effect=SQLAlchemyError("commit failed"))
    db.rollback = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(SQLAlchemyError, match="commit failed"),
    ):
        await handle_subscription_deleted(
            {
                "object": {
                    "id": "sub_test",
                    "customer": "cus_test",
                    "metadata": {},
                }
            }
        )

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_updated_resolves_org_via_customer_fallback():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.stripe_customer_id = "cus_test"
    org.stripe_subscription_id = "sub_test"
    org.max_analyses_per_month = 3

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_updated(
            {
                "object": {
                    "id": "sub_test",
                    "customer": "cus_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "items": {"data": [{"price": {"id": "missing-price"}}]},
                    "metadata": {},
                }
            }
        )

    assert result == {
        "status": "ok",
        "org_id": str(org.id),
        "subscription_status": "active",
    }
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_updated_rejects_metadata_customer_mismatch():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.stripe_customer_id = "cus_A"
    org.stripe_subscription_id = "sub_A"
    org.subscription_status = "active"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_updated(
            {
                "object": {
                    "id": "sub_B",
                    "customer": "cus_B",
                    "status": "canceled",
                    "cancel_at_period_end": True,
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                    "metadata": {"org_id": str(org.id)},
                }
            }
        )

    assert result == {
        "status": "error",
        "reason": "stripe identity mismatch",
        "org_id": str(org.id),
    }
    assert org.plan == OrgPlan.FREE
    assert org.subscription_status == "active"
    assert org.cancel_at_period_end is not True
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_updated_rejects_metadata_when_org_has_blank_stripe_identity():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.stripe_customer_id = ""
    org.stripe_subscription_id = ""
    org.subscription_status = "trialing"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_updated(
            {
                "object": {
                    "id": "sub_B",
                    "customer": "cus_B",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                    "metadata": {"org_id": str(org.id)},
                }
            }
        )

    assert result == {
        "status": "error",
        "reason": "stripe identity mismatch",
        "org_id": str(org.id),
    }
    assert org.plan == OrgPlan.FREE
    assert org.subscription_status == "trialing"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_updated_rolls_back_when_commit_fails():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.stripe_customer_id = "cus_test"
    org.stripe_subscription_id = "sub_test"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock(side_effect=SQLAlchemyError("commit failed"))
    db.rollback = AsyncMock()

    with (
        patch(
            "api.services.stripe_webhooks.async_session_factory",
            return_value=_session_ctx(db),
        ),
        pytest.raises(SQLAlchemyError, match="commit failed"),
    ):
        await handle_subscription_updated(
            {
                "object": {
                    "id": "sub_test",
                    "customer": "cus_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "items": {"data": []},
                    "metadata": {},
                }
            }
        )

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_deleted_rejects_metadata_customer_mismatch():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.PRO
    org.max_analyses_per_month = plan_limit_for(OrgPlan.PRO.value)
    org.stripe_customer_id = "cus_A"
    org.stripe_subscription_id = "sub_A"
    org.subscription_status = "active"
    org.cancel_at_period_end = False

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_deleted(
            {
                "object": {
                    "id": "sub_B",
                    "customer": "cus_B",
                    "metadata": {"org_id": str(org.id)},
                }
            }
        )

    assert result == {
        "status": "error",
        "reason": "stripe identity mismatch",
        "org_id": str(org.id),
    }
    assert org.plan == OrgPlan.PRO
    assert org.stripe_subscription_id == "sub_A"
    assert org.subscription_status == "active"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_deleted_rejects_metadata_when_org_has_blank_stripe_identity():
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.PRO
    org.max_analyses_per_month = plan_limit_for(OrgPlan.PRO.value)
    org.stripe_customer_id = ""
    org.stripe_subscription_id = ""
    org.subscription_status = "active"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_subscription_deleted(
            {
                "object": {
                    "id": "sub_B",
                    "customer": "cus_B",
                    "metadata": {"org_id": str(org.id)},
                }
            }
        )

    assert result == {
        "status": "error",
        "reason": "stripe identity mismatch",
        "org_id": str(org.id),
    }
    assert org.plan == OrgPlan.PRO
    assert org.subscription_status == "active"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_invoice_handlers_do_not_trust_metadata_org_id_without_customer_resolution():
    event = {
        "object": {
            "customer": "cus_test",
            "subscription": "sub_test",
            "amount_paid": 1200,
            "amount_due": 2200,
            "attempt_count": 2,
            "metadata": {"org_id": "org_test"},
        }
    }

    # org not found by customer → neither invoice handler may trust metadata org_id
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        succeeded = await handle_invoice_payment_succeeded(event)
        failed = await handle_invoice_payment_failed(event)

    assert succeeded == {"status": "ok", "org_id": None}
    assert failed == {
        "status": "ok",
        "warning": "payment_failed",
        "org_id": None,
    }


@pytest.mark.asyncio
async def test_invoice_dispatch_uses_customer_org_over_poisoned_metadata():
    metadata_org_id = uuid.uuid4()
    customer_org_id = uuid.uuid4()
    org = SimpleNamespace(
        id=customer_org_id,
        stripe_customer_id="cus_real",
        stripe_subscription_id="sub_real",
        subscription_status="active",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    event = {
        "object": {
            "customer": "cus_real",
            "subscription": "sub_real",
            "amount_paid": 1200,
            "metadata": {"org_id": str(metadata_org_id)},
        }
    }

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await process_stripe_webhook_event("invoice.payment_succeeded", event)

    assert result["status"] == "ok"
    assert result["org_id"] == str(customer_org_id)


@pytest.mark.asyncio
async def test_invoice_payment_succeeded_restores_past_due_org_to_active():
    """A successful dunning retry must clear past_due so paid quota returns.

    Symmetric with handle_invoice_payment_failed marking active → past_due:
    without this the org stays free-tier capped until the lagging
    customer.subscription.updated arrives.
    """
    org = SimpleNamespace(
        id=uuid.uuid4(),
        stripe_customer_id="cus_real",
        stripe_subscription_id="sub_real",
        subscription_status="past_due",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    event = {
        "object": {
            "customer": "cus_real",
            "subscription": "sub_real",
            "amount_paid": 4900,
        }
    }

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_invoice_payment_succeeded(event)

    assert result == {"status": "ok", "org_id": str(org.id)}
    assert org.subscription_status == "active"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_invoice_payment_succeeded_ignores_mismatched_subscription():
    """A paid invoice on a different subscription must not clear past_due."""
    org = SimpleNamespace(
        id=uuid.uuid4(),
        stripe_customer_id="cus_real",
        stripe_subscription_id="sub_real",
        subscription_status="past_due",
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    event = {
        "object": {
            "customer": "cus_real",
            "subscription": "sub_other",
            "amount_paid": 4900,
        }
    }

    with patch(
        "api.services.stripe_webhooks.async_session_factory",
        return_value=_session_ctx(db),
    ):
        result = await handle_invoice_payment_succeeded(event)

    assert result == {"status": "ok", "org_id": str(org.id)}
    assert org.subscription_status == "past_due"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_webhook_returns_ok_after_dispatch_and_audits_org_id():
    request = _request()
    event = {
        "type": "customer.subscription.updated",
        "id": "evt_test",
        "data": {
            "object": {
                "metadata": {"org_id": "org_test"},
            }
        },
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch("api.routes.webhooks_stripe.stripe.Webhook.construct_event", return_value=event),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            return_value={"status": "ok", "org_id": "org_test"},
        ) as process_mock,
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(),
        ),
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
    ):
        response = await stripe_webhook(request)

    assert response == {"status": "ok", "event_type": "customer.subscription.updated"}
    process_mock.assert_awaited_once()
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args is not None
    audit_kwargs = audit_mock.await_args.kwargs
    assert audit_kwargs["org_id"] == "org_test"
    assert audit_kwargs["success"] is True


@pytest.mark.asyncio
async def test_stripe_webhook_records_receipt_with_customer_fallback_org_id():
    request = _request()
    org_id = str(uuid.uuid4())
    event = {
        "type": "customer.subscription.updated",
        "id": "evt_customer_fallback",
        "data": {
            "object": {
                "id": "sub_test",
                "customer": "cus_test",
                "metadata": {},
            }
        },
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe.resolve_receipt_org_id",
            new=AsyncMock(return_value=org_id),
        ) as resolve_mock,
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ) as record_mock,
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value={"status": "ok", "org_id": None}),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(return_value=True),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
    ):
        response = await stripe_webhook(request)

    assert response == {"status": "ok", "event_type": "customer.subscription.updated"}
    resolve_mock.assert_awaited_once_with("customer.subscription.updated", event["data"])
    record_mock.assert_awaited_once_with(
        event_id="evt_customer_fallback",
        event_type="customer.subscription.updated",
        org_id=org_id,
    )
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args is not None
    assert audit_mock.await_args.kwargs["org_id"] == org_id
    mark_processed_mock.assert_awaited_once()
    assert mark_processed_mock.await_args is not None
    assert mark_processed_mock.await_args.kwargs["org_id"] == org_id


@pytest.mark.asyncio
async def test_stripe_webhook_does_not_ack_ok_result_when_receipt_mark_is_superseded():
    request = _request()
    execution_id = uuid.uuid4()
    event = {
        "type": "checkout.session.completed",
        "id": "evt_superseded",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch("api.routes.webhooks_stripe.stripe.Webhook.construct_event", return_value=event),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value={"status": "ok", "org_id": "org_test"}),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(
                return_value=StripeWebhookReceipt(
                    StripeWebhookReceiptStatus.STALE_RETRY,
                    execution_id=execution_id,
                )
            ),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(return_value=False),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 409
    mark_processed_mock.assert_awaited_once()
    assert mark_processed_mock.await_args is not None
    assert mark_processed_mock.await_args.kwargs["execution_id"] == execution_id
    audit_mock.assert_awaited_once()
    release_mock.assert_awaited_once()
    assert release_mock.await_args is not None
    assert release_mock.await_args.kwargs["execution_id"] == execution_id


@pytest.mark.asyncio
async def test_stripe_webhook_does_not_ack_ignored_result_when_receipt_mark_is_superseded():
    request = _request()
    execution_id = uuid.uuid4()
    event = {
        "type": "invoice.created",
        "id": "evt_ignored_superseded",
        "data": {"object": {}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch("api.routes.webhooks_stripe.stripe.Webhook.construct_event", return_value=event),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value={"status": "ignored", "org_id": None}),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(
                return_value=StripeWebhookReceipt(
                    StripeWebhookReceiptStatus.STALE_RETRY,
                    execution_id=execution_id,
                )
            ),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(return_value=False),
        ) as mark_processed_mock,
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 409
    mark_processed_mock.assert_awaited_once()
    assert mark_processed_mock.await_args is not None
    assert mark_processed_mock.await_args.kwargs["execution_id"] == execution_id
    release_mock.assert_awaited_once()
    assert release_mock.await_args is not None
    assert release_mock.await_args.kwargs["execution_id"] == execution_id


@pytest.mark.asyncio
async def test_stripe_webhook_verifies_signature_with_bounded_sdk_wrapper():
    request = _request()
    event = {
        "type": "invoice.created",
        "id": "evt_duplicate",
        "data": {"object": {}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ) as verify_mock,
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.DUPLICATE_PROCESSED),
        ),
    ):
        response = await stripe_webhook(request)

    assert response == {
        "status": "ok",
        "event_type": "invoice.created",
        "duplicate": True,
    }
    verify_mock.assert_awaited_once()
    assert verify_mock.await_args is not None
    args, kwargs = verify_mock.await_args
    assert args == ("stripe.webhook.construct_event", stripe.Webhook.construct_event)
    assert kwargs["payload"] == b"{}"
    assert kwargs["sig_header"] == "sig_test"
    assert kwargs["secret"] == "whsec_test"
    assert kwargs["timeout_seconds"] == STRIPE_WEBHOOK_VERIFY_TIMEOUT_SECONDS
    assert kwargs["max_attempts"] == 1


@pytest.mark.asyncio
async def test_stripe_webhook_returns_retryable_conflict_for_in_progress_duplicate():
    request = _request()
    event = {
        "type": "customer.subscription.updated",
        "id": "evt_in_progress",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.IN_PROGRESS),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(),
        ) as process_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 409
    process_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_webhook_raises_500_on_handler_failure():
    request = _request()
    execution_id = uuid.uuid4()
    event = {
        "type": "customer.subscription.updated",
        "id": "evt_test",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch("api.routes.webhooks_stripe.stripe.Webhook.construct_event", return_value=event),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(
                return_value=StripeWebhookReceipt(
                    StripeWebhookReceiptStatus.NEW,
                    execution_id=execution_id,
                )
            ),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            side_effect=ValueError("boom"),
        ),
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 500
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args is not None
    assert audit_mock.await_args.kwargs["success"] is False
    release_mock.assert_awaited_once()
    assert release_mock.await_args is not None
    assert release_mock.await_args.kwargs["execution_id"] == execution_id


@pytest.mark.asyncio
async def test_stripe_webhook_releases_receipt_for_credit_ledger_integrity_failure():
    request = _request()
    execution_id = uuid.uuid4()
    event = {
        "type": "checkout.session.completed",
        "id": "evt_credit_fk_failure",
        "data": {"object": {"metadata": {"org_id": str(uuid.uuid4())}}},
    }
    integrity_error = _constraint_integrity_error("analysis_credit_ledger_user_id_fkey")

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(
                return_value=StripeWebhookReceipt(
                    StripeWebhookReceiptStatus.NEW,
                    execution_id=execution_id,
                )
            ),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(side_effect=integrity_error),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed_or_raise",
            new=AsyncMock(),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()),
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 500
    mark_processed_mock.assert_not_awaited()
    release_mock.assert_awaited_once()
    assert release_mock.await_args is not None
    assert release_mock.await_args.kwargs["execution_id"] == execution_id


@pytest.mark.asyncio
async def test_stripe_webhook_does_not_mark_error_handler_result_processed():
    request = _request()
    event = {
        "type": "checkout.session.completed",
        "id": "evt_org_missing",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(
                return_value={
                    "status": "error",
                    "reason": "org not found",
                    "org_id": "org_test",
                }
            ),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 500
    mark_processed_mock.assert_not_awaited()
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args is not None
    audit_kwargs = audit_mock.await_args.kwargs
    assert audit_kwargs["success"] is False
    assert audit_kwargs["details"]["status"] == "error"
    release_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_stripe_webhook_marks_skipped_handler_result_processed():
    """skipped is a deliberate no-op outcome — mark processed so Stripe does not retry."""
    request = _request()
    event = {
        "type": "checkout.session.completed",
        "id": "evt_test_mode",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(
                return_value={
                    "status": "skipped",
                    "reason": "unexpected checkout mode: payment",
                    "org_id": "org_test",
                }
            ),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed_or_raise",
            new=AsyncMock(),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()),
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ),
    ):
        result = await stripe_webhook(request)

    assert result["status"] == "skipped"
    mark_processed_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_stripe_webhook_audits_malformed_handler_result_without_marking_processed():
    request = _request()
    event = {
        "type": "checkout.session.completed",
        "id": "evt_malformed_result",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.routes.webhooks_stripe._mark_stripe_event_processed",
            new=AsyncMock(),
        ) as mark_processed_mock,
        patch("api.routes.webhooks_stripe._write_webhook_audit", new=AsyncMock()) as audit_mock,
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 500
    mark_processed_mock.assert_not_awaited()
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args is not None
    audit_kwargs = audit_mock.await_args.kwargs
    assert audit_kwargs["success"] is False
    assert audit_kwargs["details"]["error_type"] == "TypeError"
    release_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_stripe_webhook_returns_503_on_signature_verification_timeout():
    request = _request()

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(side_effect=TimeoutError("slow Stripe verifier")),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(),
        ) as record_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 503
    record_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        {"type": "invoice.created", "data": {"object": {}}},
        {"id": "evt_missing_type", "data": {"object": {}}},
        {"id": " ", "type": "invoice.created", "data": {"object": {}}},
    ],
)
async def test_stripe_webhook_rejects_missing_event_identity_before_receipt(event):
    request = _request()

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.run_blocking_sdk_call",
            new=AsyncMock(return_value=event),
        ),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(),
        ) as record_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await stripe_webhook(request)

    assert exc_info.value.status == 400
    assert "missing id or type" in exc_info.value.detail
    record_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_missing_signature():
    request = _request(signature=None)

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        pytest.raises(APIError),
    ):
        await stripe_webhook(request)


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_invalid_signature():
    request = _request()

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError("bad sig", "sig_test"),
        ),
        pytest.raises(APIError),
    ):
        await stripe_webhook(request)


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_invalid_payload():
    request = _request()

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch(
            "api.routes.webhooks_stripe.stripe.Webhook.construct_event",
            side_effect=ValueError("bad payload"),
        ),
        pytest.raises(APIError),
    ):
        await stripe_webhook(request)


@pytest.mark.asyncio
async def test_process_stripe_webhook_event_ignores_unhandled_events():
    result = await process_stripe_webhook_event("invoice.created", {"object": {}})

    assert result == {
        "status": "ignored",
        "event_type": "invoice.created",
        "org_id": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_result,error_type",
    [
        (None, TypeError),
        ({"status": "ignored"}, ValueError),
        ({"status": "unknown"}, ValueError),
        ({}, ValueError),
    ],
)
async def test_process_stripe_webhook_event_rejects_invalid_handled_results(
    monkeypatch,
    handler_result,
    error_type,
):
    async def invalid_handler(_event_data):
        return handler_result

    monkeypatch.setitem(
        stripe_webhooks_module._EVENT_HANDLERS,
        "checkout.session.completed",
        invalid_handler,
    )

    with pytest.raises(error_type):
        await process_stripe_webhook_event("checkout.session.completed", {"object": {}})


@pytest.mark.asyncio
async def test_stripe_webhook_propagates_unexpected_errors():
    """Non-narrow exception types (e.g. RuntimeError) must NOT be silently swallowed."""
    request = _request()
    event = {
        "type": "customer.subscription.updated",
        "id": "evt_test",
        "data": {"object": {"metadata": {"org_id": "org_test"}}},
    }

    with (
        patch(
            "api.routes.webhooks_stripe.get_settings",
            return_value=SimpleNamespace(stripe_webhook_secret="whsec_test"),
        ),
        patch("api.routes.webhooks_stripe.stripe.Webhook.construct_event", return_value=event),
        patch(
            "api.routes.webhooks_stripe._record_stripe_event_receipt",
            new=AsyncMock(return_value=StripeWebhookReceiptStatus.NEW),
        ),
        patch(
            "api.routes.webhooks_stripe._release_stripe_event_receipt",
            new=AsyncMock(),
        ) as release_mock,
        patch(
            "api.routes.webhooks_stripe.process_stripe_webhook_event",
            side_effect=RuntimeError("unexpected"),
        ),
        pytest.raises(RuntimeError),
    ):
        await stripe_webhook(request)

    release_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_webhook_audit_logs_db_error_at_error_severity():
    """Audit failures must propagate via structured log at error severity."""
    from sqlalchemy.exc import SQLAlchemyError

    from api.routes.webhooks_stripe import _write_webhook_audit

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=SQLAlchemyError("db down"))

    with (
        patch(
            "api.routes.webhooks_stripe.async_session_factory",
            return_value=_session_ctx(db),
        ),
        patch("api.routes.webhooks_stripe.logger") as logger_mock,
    ):
        await _write_webhook_audit(
            org_id=None,
            event_id="evt_test",
            event_type="customer.subscription.updated",
            details={},
            success=False,
        )

    logger_mock.error.assert_called_once()
    call_kwargs = logger_mock.error.call_args.kwargs
    assert call_kwargs["severity"] == "error"
    # Concrete subclasses of SQLAlchemyError are still caught by the narrowed
    # exception list; we just want to assert the type was recorded.
    assert "Error" in call_kwargs["error_type"]
