"""Focused tests for session-bound Report Credit ledger reconciliation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter, ValidationError

from api.schemas.billing import CreditPackCheckoutReconciliationResponse
from api.services.billing_queries import get_credit_pack_checkout_reconciliation


@pytest.mark.asyncio
async def test_reconciliation_returns_indistinguishable_pending_without_exact_match():
    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_proxy)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session_id = "cs_test_pending123"

    result = await get_credit_pack_checkout_reconciliation(
        db,
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
    )

    assert result == {"status": "pending", "session_id": session_id}
    statement = db.execute.await_args.args[0]
    statement_text = str(statement)
    assert "analysis_credit_ledger.org_id" in statement_text
    assert "analysis_credit_ledger.user_id" in statement_text
    assert "analysis_credit_ledger.kind" in statement_text
    assert "analysis_credit_ledger.stripe_checkout_session_id" in statement_text
    assert {org_id, user_id, "purchase", session_id}.issubset(
        set(statement.compile().params.values())
    )


@pytest.mark.asyncio
async def test_reconciliation_returns_authoritative_applied_ledger_and_balance():
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    applied_at = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    ledger = SimpleNamespace(
        id=ledger_id,
        credit_pack_id="portfolio_5",
        credits_delta=5,
        stripe_payment_intent_id="pi_applied123",
        created_at=applied_at,
    )
    ledger_result = MagicMock()
    ledger_result.scalar_one_or_none.return_value = ledger
    balance_result = MagicMock()
    balance_result.scalar_one.return_value = 7
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[ledger_result, balance_result])

    result = await get_credit_pack_checkout_reconciliation(
        db,
        org_id=org_id,
        user_id=user_id,
        session_id="cs_test_applied123",
    )

    assert result == {
        "status": "applied",
        "session_id": "cs_test_applied123",
        "ledger_entry_id": ledger_id,
        "credit_pack_id": "portfolio_5",
        "credits_applied": 5,
        "current_purchased_credits_balance": 7,
        "applied_at": applied_at,
    }


@pytest.mark.asyncio
async def test_reconciliation_fails_closed_for_malformed_purchase_row():
    ledger = SimpleNamespace(
        id=uuid.uuid4(),
        credit_pack_id=None,
        credits_delta=5,
        created_at=datetime.now(UTC),
    )
    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = ledger
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_proxy)

    result = await get_credit_pack_checkout_reconciliation(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id="cs_test_malformed123",
    )

    assert result == {
        "status": "pending",
        "session_id": "cs_test_malformed123",
    }
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credits_delta", "payment_intent_id"),
    [
        (1, "pi_wrong_quantity"),
        (5, None),
        (5, "not-a-payment-intent"),
    ],
)
async def test_reconciliation_fails_closed_for_invalid_purchase_identity(
    credits_delta,
    payment_intent_id,
):
    ledger = SimpleNamespace(
        id=uuid.uuid4(),
        credit_pack_id="portfolio_5",
        credits_delta=credits_delta,
        stripe_payment_intent_id=payment_intent_id,
        created_at=datetime.now(UTC),
    )
    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = ledger
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_proxy)

    result = await get_credit_pack_checkout_reconciliation(
        db,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id="cs_test_malformed_identity123",
    )

    assert result == {
        "status": "pending",
        "session_id": "cs_test_malformed_identity123",
    }
    db.execute.assert_awaited_once()


def test_reconciliation_schema_is_discriminated_and_forbids_unknown_fields():
    adapter = TypeAdapter(CreditPackCheckoutReconciliationResponse)
    assert (
        adapter.validate_python({"status": "pending", "session_id": "cs_test_pending123"}).status
        == "pending"
    )

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "status": "pending",
                "session_id": "cs_test_pending123",
                "credit_pack_id": "portfolio_5",
            }
        )
