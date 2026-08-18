"""Focused tests for Stripe-facing billing helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.db.models import OrgPlan
from api.errors import APIError
from api.schemas.billing import PlanTier
from api.services.billing_checkout import (
    create_checkout_session_data_impl,
    list_invoice_data_impl,
)
from api.services.billing_sync import (
    sync_subscription_status_orchestrated as sync_subscription_status_impl,
)


@pytest.mark.asyncio
async def test_create_checkout_session_data_impl_rejects_free_plan_before_org_lookup():
    with pytest.raises(APIError) as exc_info:
        await create_checkout_session_data_impl(
            MagicMock(),
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=PlanTier.FREE,
            success_url="",
            cancel_url="",
            request=MagicMock(),
            stripe_secret_key="sk_test",
            get_org_for_billing_or_404_fn=AsyncMock(),
            checkout_price_id_fn=MagicMock(return_value="price_starter"),
            get_or_create_customer_fn=AsyncMock(),
            write_audit_log_fn=AsyncMock(),
            create_checkout_session_fn=MagicMock(),
            billing_origin_url_fn=MagicMock(return_value="https://app.example.com"),
            logger=MagicMock(),
        )

    assert "free plan" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_invoice_data_impl_returns_empty_when_not_configured():
    payload = await list_invoice_data_impl(
        MagicMock(),
        org_id=uuid.uuid4(),
        stripe_secret_key=None,
        get_org_for_billing_or_404_fn=AsyncMock(),
        list_invoices_fn=MagicMock(),
        map_invoice_list_fn=MagicMock(),
        logger=MagicMock(),
    )

    assert payload == {"invoices": [], "has_more": False}


@pytest.mark.asyncio
async def test_sync_subscription_status_impl_returns_error_for_missing_org():
    result = await sync_subscription_status_impl(
        MagicMock(),
        org_id=uuid.uuid4(),
        get_org_by_id_fn=AsyncMock(return_value=None),
        retrieve_subscription_fn=MagicMock(),
        price_id_to_plan_fn=MagicMock(return_value=OrgPlan.FREE),
        plan_limit_for_fn=MagicMock(return_value=3),
        sync_subscription_mutation_fn=AsyncMock(),
        logger=MagicMock(),
    )

    assert result == {"error": "Organization not found"}
