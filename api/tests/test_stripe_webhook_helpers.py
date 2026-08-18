"""Focused tests for Stripe webhook helper modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.billing_webhooks import (
    event_metadata,
    event_object,
    extract_audit_org_id_from_event,
    load_org_by_customer,
)


def test_event_helpers_handle_non_dict_payloads():
    assert event_object({"object": "not-a-dict"}) == {}
    assert event_metadata({"object": {"metadata": "not-a-dict"}}) == {}
    assert extract_audit_org_id_from_event({"object": {"metadata": []}}) is None


@pytest.mark.asyncio
async def test_load_org_by_customer_returns_scalar_result(mock_db):
    org = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    mock_db.execute = AsyncMock(return_value=result)

    loaded = await load_org_by_customer(mock_db, "cus_test")

    assert loaded is org
