from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_mock_db
from pydantic import ValidationError

from api.db.models import OrgPlan
from api.schemas.admin import UpdateOrgRequest
from api.services.admin_orgs import (
    _map_organization_row,
    update_organization_for_admin_impl,
)


def test_map_organization_row_builds_summary() -> None:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.name = "Praviar Labs"
    org.slug = "praviar-labs"
    org.plan = OrgPlan.STARTER
    org.max_analyses_per_month = 25
    org.free_analyses_remaining = 2
    org.created_at = datetime(2026, 4, 11, tzinfo=UTC)

    summary = _map_organization_row((org, 3, 9))

    assert summary.id == org.id
    assert summary.plan == "starter"
    assert summary.user_count == 3
    assert summary.analysis_count == 9


def test_update_org_request_rejects_invalid_plan() -> None:
    with pytest.raises(ValidationError):
        UpdateOrgRequest.model_validate({"plan": "not-a-plan"})


@pytest.mark.asyncio
async def test_update_organization_for_admin_impl_writes_fail_closed_audit() -> None:
    db = make_mock_db()
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.max_analyses_per_month = 10
    org.free_analyses_remaining = 2

    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db.execute.return_value = result
    audit_log = AsyncMock()

    await update_organization_for_admin_impl(
        db,
        org_id=org.id,
        admin_org_id=org.id,
        admin_id=uuid.uuid4(),
        body=UpdateOrgRequest(plan="starter"),  # type: ignore[call-arg]
        write_audit_log_fn=audit_log,
    )

    assert org.plan == OrgPlan.STARTER
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_organization_for_admin_impl_rolls_back_when_audit_fails() -> None:
    db = make_mock_db()
    org = MagicMock()
    org.id = uuid.uuid4()
    org.plan = OrgPlan.FREE
    org.max_analyses_per_month = 10
    org.free_analyses_remaining = 2

    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db.execute.return_value = result
    audit_log = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await update_organization_for_admin_impl(
            db,
            org_id=org.id,
            admin_org_id=org.id,
            admin_id=uuid.uuid4(),
            body=UpdateOrgRequest(plan="starter"),  # type: ignore[call-arg]
            write_audit_log_fn=audit_log,
        )

    assert org.plan == OrgPlan.STARTER
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
