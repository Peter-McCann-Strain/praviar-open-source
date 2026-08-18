from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.db.models import (
    CreditCapacityRequest,
    Notification,
    NotificationType,
    User,
    UserRole,
)
from api.errors import APIError
from api.services.billing import (
    create_credit_capacity_request_data,
    fulfill_pending_credit_capacity_requests,
    list_credit_capacity_requests_data,
    resolve_credit_capacity_request_data,
)


def build_user(*, role: UserRole, name: str = "Rina Scientist") -> User:
    return User(
        id=uuid.uuid4(),
        clerk_user_id=f"user_{uuid.uuid4()}",
        org_id=uuid.uuid4(),
        email="rina@example.com",
        full_name=name,
        role=role,
    )


def build_capacity_request(
    requester: User,
    *,
    requested_reports: int = 1,
    requested_at: datetime | None = None,
) -> CreditCapacityRequest:
    return CreditCapacityRequest(
        id=uuid.uuid4(),
        org_id=requester.org_id,
        requester_user_id=requester.id,
        requester_name=requester.full_name,
        requested_reports=requested_reports,
        source="analysis_launch",
        status="pending",
        notified_admins=1,
        requested_at=requested_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_credit_capacity_request_notifies_active_admins_and_audits():
    requester = build_user(role=UserRole.SCIENTIST)
    admin_one = build_user(role=UserRole.ADMIN, name="Ada Admin")
    admin_two = build_user(role=UserRole.ADMIN, name="Max Admin")
    admin_one.org_id = requester.org_id
    admin_two.org_id = requester.org_id
    scalars = MagicMock()
    scalars.all.return_value = [admin_one, admin_two]
    result = MagicMock()
    result.scalars.return_value = scalars
    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()
    request = MagicMock()
    request.client = None

    with patch(
        "api.services.billing.write_audit_log",
        new=AsyncMock(),
    ) as write_audit:
        response = await create_credit_capacity_request_data(
            db,
            user=requester,
            requested_reports=1,
            source="analysis_launch",
            request=request,
        )

    assert response["notified_admins"] == 2
    assert response["status"] == "sent"
    assert isinstance(response["request_id"], uuid.UUID)
    assert response["requested_at"].tzinfo is not None
    notifications = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Notification)
    ]
    assert len(notifications) == 3
    admin_notifications = [
        item for item in notifications if item.data["kind"] == "credit_capacity_request"
    ]
    requester_notifications = [
        item
        for item in notifications
        if item.data["kind"] == "credit_capacity_request_confirmation"
    ]
    assert len(admin_notifications) == 2
    assert len(requester_notifications) == 1
    assert requester_notifications[0].user_id == requester.id
    assert requester_notifications[0].read is True
    assert all(item.type == NotificationType.SYSTEM for item in notifications)
    assert all(item.org_id == requester.org_id for item in notifications)
    assert admin_notifications[0].title == "Report Credit capacity requested"
    assert admin_notifications[0].data["href"].startswith("/billing?")
    assert (
        admin_notifications[0].data["request_id"] == requester_notifications[0].data["request_id"]
    )
    persisted_requests = [
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], CreditCapacityRequest)
    ]
    assert len(persisted_requests) == 1
    assert persisted_requests[0].id == response["request_id"]
    assert persisted_requests[0].status == "pending"
    assert str(response["request_id"])[:8] in requester_notifications[0].body
    assert str(response["request_id"])[:8] in admin_notifications[0].body
    statement = db.execute.await_args.args[0]
    statement_sql = str(statement)
    assert "users.org_id" in statement_sql
    assert "users.role" in statement_sql
    assert "users.membership_active IS true" in statement_sql
    assert "users.membership_deleted_at IS NULL" in statement_sql
    assert "users.membership_permission_denied_at IS NULL" in statement_sql
    write_audit.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_credit_capacity_request_does_not_persist_email_as_name_fallback():
    requester = build_user(role=UserRole.SCIENTIST, name="")
    administrator = build_user(role=UserRole.ADMIN, name="Ada Admin")
    administrator.org_id = requester.org_id
    scalars = MagicMock()
    scalars.all.return_value = [administrator]
    result = MagicMock()
    result.scalars.return_value = scalars
    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()

    with patch(
        "api.services.billing.write_audit_log",
        new=AsyncMock(),
    ):
        await create_credit_capacity_request_data(
            db,
            user=requester,
            requested_reports=1,
            source="analysis_launch",
            request=MagicMock(),
        )

    persisted_request = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], CreditCapacityRequest)
    )
    assert persisted_request.requester_name == "Workspace member"
    assert requester.email not in persisted_request.requester_name


@pytest.mark.asyncio
async def test_credit_capacity_request_fails_when_no_admin_recipient_exists():
    requester = build_user(role=UserRole.SCIENTIST)
    scalars = MagicMock()
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()
    request = MagicMock()
    request.client = None

    with pytest.raises(HTTPException) as exc_info:
        await create_credit_capacity_request_data(
            db,
            user=requester,
            requested_reports=1,
            source="analysis_launch",
            request=request,
        )

    assert exc_info.value.status_code == 409
    assert "No active workspace administrator" in str(exc_info.value.detail)
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_scientist_lists_only_own_capacity_requests():
    requester = build_user(role=UserRole.SCIENTIST)
    item = build_capacity_request(requester)
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.side_effect = [count_result, rows_result]

    response = await list_credit_capacity_requests_data(
        db,
        user=requester,
        page=1,
        per_page=20,
        request_status="pending",
    )

    assert response["total"] == 1
    assert response["items"][0]["id"] == item.id
    where_clause = str(db.execute.await_args_list[1].args[0].whereclause)
    assert "credit_capacity_requests.org_id" in where_clause
    assert "credit_capacity_requests.requester_user_id" in where_clause
    assert "credit_capacity_requests.status" in where_clause


@pytest.mark.asyncio
async def test_admin_lists_workspace_capacity_requests_without_requester_filter():
    admin = build_user(role=UserRole.ADMIN)
    item = build_capacity_request(admin)
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.side_effect = [count_result, rows_result]

    await list_credit_capacity_requests_data(
        db,
        user=admin,
        page=1,
        per_page=50,
        request_status=None,
    )

    where_clause = str(db.execute.await_args_list[1].args[0].whereclause)
    assert "credit_capacity_requests.org_id" in where_clause
    assert "requester_user_id =" not in where_clause


@pytest.mark.asyncio
async def test_admin_verifies_current_capacity_and_notifies_requester():
    requester = build_user(role=UserRole.SCIENTIST)
    admin = build_user(role=UserRole.ADMIN)
    admin.org_id = requester.org_id
    item = build_capacity_request(requester)
    org = MagicMock(id=requester.org_id)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    request_result = MagicMock()
    request_result.scalar_one_or_none.return_value = item
    db = AsyncMock()
    db.execute.side_effect = [org_result, request_result]
    db.add = MagicMock()
    request = MagicMock()
    request.client = None

    with (
        patch(
            "api.services.billing.billing_queries.get_available_analysis_capacity",
            new=AsyncMock(return_value=MagicMock(available=5)),
        ) as get_capacity,
        patch(
            "api.services.billing.write_audit_log",
            new=AsyncMock(),
        ) as write_audit,
    ):
        response = await resolve_credit_capacity_request_data(
            db,
            user=admin,
            request_id=item.id,
            resolution_status="fulfilled",
            note="Credits added.",
            request=request,
        )

    assert response["status"] == "fulfilled"
    assert response["resolution_outcome"] == "resolved"
    assert item.resolved_by_user_id == admin.id
    assert item.resolution_note == "Credits added."
    notification = next(
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Notification)
    )
    assert notification.user_id == requester.id
    assert str(item.id)[:8] in notification.body
    assert "Capacity is shared, not reserved" in notification.body
    assert notification.title == "Report Credit capacity verified"
    assert notification.data["capacity_reserved"] is False
    assert notification.data["available_capacity_at_resolution"] == 5
    get_capacity.assert_awaited_once_with(db, org=org)
    assert "organizations.id" in str(db.execute.await_args_list[0].args[0])
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])
    assert "credit_capacity_requests.id" in str(db.execute.await_args_list[1].args[0])
    assert "FOR UPDATE" in str(db.execute.await_args_list[1].args[0])
    write_audit.assert_awaited_once()
    audit_details = write_audit.await_args.kwargs["details"]
    assert audit_details["resolution_kind"] == "capacity_verified"
    assert audit_details["available_capacity_at_resolution"] == 5
    assert audit_details["capacity_reserved"] is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_cannot_verify_when_current_capacity_is_insufficient():
    requester = build_user(role=UserRole.SCIENTIST)
    admin = build_user(role=UserRole.ADMIN)
    admin.org_id = requester.org_id
    item = build_capacity_request(requester, requested_reports=5)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = MagicMock(id=requester.org_id)
    request_result = MagicMock()
    request_result.scalar_one_or_none.return_value = item
    db = AsyncMock()
    db.execute.side_effect = [org_result, request_result]
    db.add = MagicMock()

    with (
        patch(
            "api.services.billing.billing_queries.get_available_analysis_capacity",
            new=AsyncMock(return_value=MagicMock(available=2)),
        ),
        patch(
            "api.services.billing.write_audit_log",
            new=AsyncMock(),
        ) as write_audit,
        pytest.raises(APIError) as exc_info,
    ):
        await resolve_credit_capacity_request_data(
            db,
            user=admin,
            request_id=item.id,
            resolution_status="fulfilled",
            note="Capacity reviewed.",
            request=MagicMock(),
        )

    assert exc_info.value.status == 409
    assert "Only 2 of 5" in exc_info.value.detail
    assert exc_info.value.type_uri == "https://problems.praviar.invalid/insufficient-capacity"
    assert item.status == "pending"
    db.add.assert_not_called()
    write_audit.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_manual_resolution_is_idempotent_without_rechecking_capacity():
    requester = build_user(role=UserRole.SCIENTIST)
    admin = build_user(role=UserRole.ADMIN)
    admin.org_id = requester.org_id
    item = build_capacity_request(requester)
    item.status = "fulfilled"
    item.resolved_at = datetime.now(UTC)
    item.resolved_by_user_id = admin.id
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = MagicMock(id=requester.org_id)
    request_result = MagicMock()
    request_result.scalar_one_or_none.return_value = item
    db = AsyncMock()
    db.execute.side_effect = [org_result, request_result]
    db.add = MagicMock()

    with patch(
        "api.services.billing.billing_queries.get_available_analysis_capacity",
        new=AsyncMock(),
    ) as get_capacity:
        response = await resolve_credit_capacity_request_data(
            db,
            user=admin,
            request_id=item.id,
            resolution_status="fulfilled",
            note=None,
            request=MagicMock(),
        )

    assert response["status"] == "fulfilled"
    assert response["resolution_outcome"] == "already_resolved"
    get_capacity.assert_not_awaited()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_rejects_unexplained_decline():
    requester = build_user(role=UserRole.SCIENTIST)
    admin = build_user(role=UserRole.ADMIN)
    admin.org_id = requester.org_id
    item = build_capacity_request(requester)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = MagicMock(id=requester.org_id)
    request_result = MagicMock()
    request_result.scalar_one_or_none.return_value = item
    db = AsyncMock()
    db.execute.side_effect = [org_result, request_result]

    with pytest.raises(APIError) as exc_info:
        await resolve_credit_capacity_request_data(
            db,
            user=admin,
            request_id=item.id,
            resolution_status="declined",
            note=" ",
            request=MagicMock(),
        )

    assert exc_info.value.status == 422
    assert "decline reason" in exc_info.value.detail.lower()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_capacity_request_rejects_cross_org_or_missing_id():
    admin = build_user(role=UserRole.ADMIN)
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = MagicMock(id=admin.org_id)
    request_result = MagicMock()
    request_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.side_effect = [org_result, request_result]

    with pytest.raises(APIError) as exc_info:
        await resolve_credit_capacity_request_data(
            db,
            user=admin,
            request_id=uuid.uuid4(),
            resolution_status="declined",
            note=None,
            request=MagicMock(),
        )

    assert exc_info.value.status == 404
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_purchase_fulfills_whole_requests_in_fifo_order():
    requester = build_user(role=UserRole.SCIENTIST)
    now = datetime.now(UTC)
    first = build_capacity_request(
        requester,
        requested_reports=2,
        requested_at=now,
    )
    second = build_capacity_request(
        requester,
        requested_reports=1,
        requested_at=now + timedelta(seconds=1),
    )
    third = build_capacity_request(
        requester,
        requested_reports=5,
        requested_at=now + timedelta(seconds=2),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second, third]
    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()
    ledger_id = uuid.uuid4()

    with patch(
        "api.services.billing.write_audit_log",
        new=AsyncMock(),
    ) as write_audit:
        fulfilled = await fulfill_pending_credit_capacity_requests(
            db,
            org_id=requester.org_id,
            purchaser_user_id=uuid.uuid4(),
            credit_ledger_id=ledger_id,
            purchased_credits=3,
        )

    assert fulfilled == [first.id, second.id]
    assert first.status == second.status == "fulfilled"
    assert first.fulfillment_credit_ledger_id == ledger_id
    assert second.fulfillment_credit_ledger_id == ledger_id
    assert third.status == "pending"
    notifications = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Notification)
    ]
    assert len(notifications) == 3
    write_audit.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_purchase_does_not_skip_oversized_fifo_head():
    requester = build_user(role=UserRole.SCIENTIST)
    now = datetime.now(UTC)
    first = build_capacity_request(
        requester,
        requested_reports=5,
        requested_at=now,
    )
    second = build_capacity_request(
        requester,
        requested_reports=1,
        requested_at=now + timedelta(seconds=1),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second]
    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "api.services.billing.write_audit_log",
        new=AsyncMock(),
    ) as write_audit:
        fulfilled = await fulfill_pending_credit_capacity_requests(
            db,
            org_id=requester.org_id,
            purchaser_user_id=uuid.uuid4(),
            credit_ledger_id=uuid.uuid4(),
            purchased_credits=1,
        )

    assert fulfilled == []
    assert first.status == second.status == "pending"
    write_audit.assert_not_awaited()
