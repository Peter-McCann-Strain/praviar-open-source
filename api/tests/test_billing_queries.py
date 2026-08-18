from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db

from api.db.models import OrgPlan
from api.services.billing_queries import check_usage_limit, get_org_for_billing_or_404


def _make_org(**kw: object) -> MagicMock:
    org = MagicMock()
    org.id = kw.get("id", uuid.uuid4())
    org.plan = kw.get("plan", OrgPlan.STARTER)
    org.max_analyses_per_month = kw.get("max_analyses_per_month", 8)
    org.billing_cycle_start = kw.get(
        "billing_cycle_start",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    return org


@pytest.mark.asyncio
async def test_get_org_for_billing_or_404_raises_for_missing_org() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(Exception, match="Organization not found"):
        await get_org_for_billing_or_404(db, uuid.uuid4())


@pytest.mark.asyncio
async def test_check_usage_limit_returns_zero_tuple_for_missing_org() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    assert await check_usage_limit(db, uuid.uuid4()) == (False, 0, 0)


@pytest.mark.asyncio
async def test_check_usage_limit_uses_policy_limit_when_org_cap_missing() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    usage_result = MagicMock()
    usage_result.scalar_one.return_value = 5
    credit_balance_result = MagicMock()
    credit_balance_result.scalar_one.return_value = 0
    consumed_credit_result = MagicMock()
    consumed_credit_result.scalar_one.return_value = 0
    db.execute = AsyncMock(
        side_effect=[
            result,
            usage_result,
            credit_balance_result,
            consumed_credit_result,
        ]
    )

    settings = MagicMock()
    settings.plan_free_analyses_per_month = 1
    settings.plan_starter_analyses_per_month = 8
    settings.plan_pro_analyses_per_month = 20

    with patch("api.services.billing_queries.get_settings", return_value=settings):
        assert await check_usage_limit(db, org.id) == (True, 5, 8)
