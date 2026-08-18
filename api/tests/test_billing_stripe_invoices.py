"""Focused tests for Stripe invoice orchestration."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.billing_checkout import list_invoice_data_impl


@pytest.mark.asyncio
async def test_list_invoice_data_impl_returns_mapped_invoices() -> None:
    org_id = uuid.uuid4()
    db = AsyncMock()
    org = MagicMock(stripe_customer_id="cus_123", id=org_id)
    list_invoices_fn = MagicMock(return_value=MagicMock(id="invoice-list"))
    map_invoice_list_fn = MagicMock(return_value={"invoices": ["a"], "has_more": False})

    payload = await list_invoice_data_impl(
        db,
        org_id=org_id,
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(return_value=org),
        list_invoices_fn=list_invoices_fn,
        map_invoice_list_fn=map_invoice_list_fn,
        logger=MagicMock(),
    )

    assert payload == {"invoices": ["a"], "has_more": False}
    list_invoices_fn.assert_called_once_with(customer="cus_123", limit=20)


@pytest.mark.asyncio
async def test_list_invoice_data_impl_returns_empty_without_customer() -> None:
    payload = await list_invoice_data_impl(
        AsyncMock(),
        org_id=uuid.uuid4(),
        stripe_secret_key="sk_test",
        get_org_for_billing_or_404_fn=AsyncMock(
            return_value=MagicMock(stripe_customer_id=None, id=uuid.uuid4())
        ),
        list_invoices_fn=MagicMock(),
        map_invoice_list_fn=MagicMock(),
        logger=MagicMock(),
    )

    assert payload == {"invoices": [], "has_more": False}
