"""Focused tests for Stripe subscription sync orchestration."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.db.models import OrgPlan
from api.services.billing_sync import (
    sync_subscription_status_orchestrated as sync_subscription_status_impl,
)


@pytest.mark.asyncio
async def test_sync_subscription_status_impl_returns_error_for_missing_org() -> None:
    result = await sync_subscription_status_impl(
        AsyncMock(),
        org_id=uuid.uuid4(),
        get_org_by_id_fn=AsyncMock(return_value=None),
        retrieve_subscription_fn=MagicMock(),
        price_id_to_plan_fn=MagicMock(return_value=OrgPlan.FREE),
        plan_limit_for_fn=MagicMock(return_value=3),
        sync_subscription_mutation_fn=AsyncMock(),
        logger=MagicMock(),
    )

    assert result == {"error": "Organization not found"}
