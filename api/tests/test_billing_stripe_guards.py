"""Focused tests for Stripe billing guard helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.errors import APIError
from api.schemas.billing import PlanTier
from api.services.billing_checkout import (
    get_org_for_sync,
    require_billing_configured,
    resolve_checkout_price_id,
)


def test_require_billing_configured_raises_service_unavailable() -> None:
    logger = MagicMock()

    with pytest.raises(APIError) as exc_info:
        require_billing_configured(
            None,
            unavailable_message="Billing is not configured.",
            logger=logger,
        )

    assert "Billing is not configured." in str(exc_info.value)
    logger.error.assert_called_once_with("billing_stripe_not_configured")


def test_resolve_checkout_price_id_rejects_free_and_enterprise() -> None:
    with pytest.raises(APIError):
        resolve_checkout_price_id(PlanTier.FREE, checkout_price_id_fn=MagicMock())

    with pytest.raises(APIError):
        resolve_checkout_price_id(PlanTier.ENTERPRISE, checkout_price_id_fn=MagicMock())


def test_resolve_checkout_price_id_returns_configured_price() -> None:
    assert (
        resolve_checkout_price_id(
            PlanTier.PRO,
            checkout_price_id_fn=MagicMock(return_value="price_pro"),
        )
        == "price_pro"
    )


@pytest.mark.asyncio
async def test_get_org_for_sync_logs_missing_org() -> None:
    logger = MagicMock()
    result = await get_org_for_sync(
        MagicMock(),
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        get_org_by_id_fn=AsyncMock(return_value=None),
        logger=logger,
    )

    assert result is None
    logger.error.assert_called_once()
