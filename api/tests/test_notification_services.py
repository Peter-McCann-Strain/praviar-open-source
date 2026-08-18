"""Tests for notification service helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.db.models import NotificationType as DBNotificationType
from api.db.models import UserRole
from api.errors import APIError
from api.schemas.notifications import DigestFrequency, NotificationPreferencesSchema
from api.services.notifications import (
    dismiss_all_notifications,
    get_notification_preferences,
    get_unread_notification_count,
    list_notifications_page,
    mark_notifications_read,
    resolve_notification_action,
    update_notification_preferences,
)


@pytest.mark.asyncio
async def test_list_notifications_page_builds_counts_and_items(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    item = SimpleNamespace(
        id=uuid.uuid4(),
        type=DBNotificationType.SYSTEM,
        title="Maintenance complete",
        body="The scheduled maintenance completed.",
        read=False,
        data={"kind": "maintenance", "href": "//attacker.invalid/redirect"},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 2)
    unread_result = SimpleNamespace(scalar_one=lambda: 1)
    items_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [item]))
    mock_db.execute.side_effect = [count_result, unread_result, items_result]

    page = await list_notifications_page(
        mock_db,
        user=user,  # type: ignore[arg-type]
        page=1,
        per_page=20,
    )

    assert page.total == 2
    assert page.unread_count == 1
    assert len(page.items) == 1
    assert page.items[0].title == "Maintenance complete"
    assert page.items[0].data == {"kind": "maintenance"}
    assert page.items[0].actionable is False
    assert page.items[0].tombstoned is False


@pytest.mark.asyncio
async def test_list_notifications_tombstones_missing_analysis_without_leaking_content(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    analysis_id = uuid.uuid4()
    item = SimpleNamespace(
        id=uuid.uuid4(),
        type=DBNotificationType.ANALYSIS_COMPLETE,
        title="Secret compound is HIGH risk",
        body="Restricted patent conclusion and customer data",
        read=False,
        data={
            "analysis_id": str(analysis_id),
            "href": "https://attacker.invalid",
            "overall_risk": "HIGH",
        },
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 1)
    unread_result = SimpleNamespace(scalar_one=lambda: 1)
    items_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [item]))
    missing_analysis = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )
    mock_db.execute.side_effect = [
        count_result,
        unread_result,
        items_result,
        missing_analysis,
    ]

    page = await list_notifications_page(
        mock_db,
        user=user,  # type: ignore[arg-type]
        page=1,
        per_page=20,
    )

    notification = page.items[0]
    assert notification.title == "Notification unavailable"
    assert "Secret compound" not in notification.title
    assert "Restricted patent" not in notification.body
    assert notification.data == {"tombstoned": True}
    assert notification.actionable is False
    assert notification.tombstoned is True


@pytest.mark.asyncio
async def test_list_notifications_batches_mixed_large_page_resource_checks(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.ADMIN,
    )
    created_at = datetime(2026, 4, 11, tzinfo=UTC)
    analysis_ids = [uuid.uuid4() for _ in range(20)]
    export_job_ids = [uuid.uuid4() for _ in range(20)]
    export_analysis_ids = [uuid.uuid4() for _ in range(20)]
    monitor_ids = [uuid.uuid4() for _ in range(20)]
    alert_ids = [uuid.uuid4() for _ in range(20)]
    comment_ids = [uuid.uuid4() for _ in range(20)]
    comment_analysis_ids = [uuid.uuid4() for _ in range(20)]
    credit_request_ids = [uuid.uuid4() for _ in range(20)]
    notifications = [
        SimpleNamespace(
            id=uuid.uuid4(),
            type=DBNotificationType.ANALYSIS_COMPLETE,
            title="Stored analysis title",
            body="Stored analysis body",
            read=False,
            data={"analysis_id": str(analysis_id)},
            created_at=created_at,
        )
        for analysis_id in analysis_ids
    ]
    notifications.extend(
        SimpleNamespace(
            id=uuid.uuid4(),
            type=DBNotificationType.EXPORT_READY,
            title="Stored export title",
            body="Stored export body",
            read=False,
            data={"export_job_id": str(export_job_id)},
            created_at=created_at,
        )
        for export_job_id in export_job_ids
    )
    notifications.extend(
        SimpleNamespace(
            id=uuid.uuid4(),
            type=DBNotificationType.MONITOR_ALERT,
            title="Stored monitor title",
            body="Stored monitor body",
            read=False,
            data={
                "monitor_id": str(monitor_id),
                "alert_id": str(alert_id),
            },
            created_at=created_at,
        )
        for monitor_id, alert_id in zip(monitor_ids, alert_ids, strict=True)
    )
    notifications.extend(
        SimpleNamespace(
            id=uuid.uuid4(),
            type=DBNotificationType.SYSTEM,
            title="Stored comment title",
            body="Stored comment body",
            read=False,
            data={
                "kind": "comment_assignment",
                "comment_id": str(comment_id),
            },
            created_at=created_at,
        )
        for comment_id in comment_ids
    )
    notifications.extend(
        SimpleNamespace(
            id=uuid.uuid4(),
            type=DBNotificationType.SYSTEM,
            title="Stored credit title",
            body="Stored credit body",
            read=False,
            data={
                "kind": "credit_capacity_request",
                "request_id": str(request_id),
                "href": "//attacker.invalid",
            },
            created_at=created_at,
        )
        for request_id in credit_request_ids
    )

    mock_db.execute.side_effect = [
        SimpleNamespace(scalar_one=lambda: 100),
        SimpleNamespace(scalar_one=lambda: 100),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: notifications)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: analysis_ids)),
        SimpleNamespace(all=lambda: list(zip(export_job_ids, export_analysis_ids, strict=True))),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: monitor_ids)),
        SimpleNamespace(all=lambda: list(zip(alert_ids, monitor_ids, strict=True))),
        SimpleNamespace(all=lambda: list(zip(comment_ids, comment_analysis_ids, strict=True))),
        SimpleNamespace(
            all=lambda: [(request_id, uuid.uuid4()) for request_id in credit_request_ids]
        ),
    ]
    capabilities = SimpleNamespace(
        can_export_report=True,
        can_manage_monitors=True,
        can_view_review_queue=True,
        can_manage_billing=True,
        can_view_billing=True,
        can_view_platform_admin=True,
        risk_ratings_restricted=False,
    )

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        page = await list_notifications_page(
            mock_db,
            user=user,  # type: ignore[arg-type]
            page=1,
            per_page=100,
        )

    assert len(page.items) == 100
    assert all(item.actionable for item in page.items)
    assert all(not item.tombstoned for item in page.items)
    assert mock_db.execute.await_count == 9

    analysis_sql = str(mock_db.execute.await_args_list[3].args[0])
    export_sql = str(mock_db.execute.await_args_list[4].args[0])
    monitor_sql = str(mock_db.execute.await_args_list[5].args[0])
    alert_sql = str(mock_db.execute.await_args_list[6].args[0])
    comment_sql = str(mock_db.execute.await_args_list[7].args[0])
    credit_sql = str(mock_db.execute.await_args_list[8].args[0])
    assert "analyses.org_id" in analysis_sql
    assert "export_jobs.org_id" in export_sql
    assert "export_jobs.user_id" in export_sql
    assert "monitors.org_id" in monitor_sql
    assert "monitor_alerts.org_id" in alert_sql
    assert "monitor_alerts.monitor_id" in alert_sql
    assert "comments.org_id" in comment_sql
    assert "comments.assigned_to" in comment_sql
    assert "credit_capacity_requests.org_id" in credit_sql


@pytest.mark.asyncio
async def test_resolve_analysis_action_is_org_user_scoped_and_marks_after_success(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    analysis_id = uuid.uuid4()
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.ANALYSIS_COMPLETE,
        title="Stored title is not trusted",
        body="Stored body is not trusted",
        read=False,
        data={"analysis_id": str(analysis_id), "href": "//attacker.invalid"},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    notification_result = SimpleNamespace(scalar_one_or_none=lambda: notification)
    analysis_result = SimpleNamespace(scalar_one_or_none=lambda: analysis_id)
    mock_db.execute.side_effect = [notification_result, analysis_result]
    capabilities = SimpleNamespace(risk_ratings_restricted=False)

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        result = await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert result.actionable is True
    assert result.destination == f"/analyses/{analysis_id}/report"
    assert result.marked_read is True
    assert notification.read is True
    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
    notification_sql = str(mock_db.execute.await_args_list[0].args[0])
    analysis_sql = str(mock_db.execute.await_args_list[1].args[0])
    assert "notifications.user_id" in notification_sql
    assert "notifications.org_id" in notification_sql
    assert "analyses.org_id" in analysis_sql


@pytest.mark.asyncio
async def test_resolve_action_fails_closed_when_resource_is_missing(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.ANALYSIS_COMPLETE,
        title="Stored restricted title",
        body="Stored restricted body",
        read=False,
        data={"analysis_id": str(uuid.uuid4())},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: notification),
        SimpleNamespace(scalar_one_or_none=lambda: None),
    ]

    with pytest.raises(APIError) as error:
        await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert error.value.status == 404
    assert error.value.detail == "Notification action unavailable"
    assert notification.read is False
    mock_db.flush.assert_not_awaited()
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_benign_system_notice_does_not_trust_href_or_mark_read(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.SYSTEM,
        title="Maintenance complete",
        body="No action is required.",
        read=False,
        data={"kind": "maintenance", "href": "/admin?tab=users"},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = notification

    result = await resolve_notification_action(
        mock_db,
        user=user,  # type: ignore[arg-type]
        notification_id=notification.id,
    )

    assert result.actionable is False
    assert result.destination is None
    assert result.marked_read is False
    assert notification.read is False
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_credit_request_uses_fixed_destination_not_stored_href(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.ADMIN,
    )
    request_id = uuid.uuid4()
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.SYSTEM,
        title="Stored title",
        body="Stored body",
        read=True,
        data={
            "kind": "credit_capacity_request",
            "request_id": str(request_id),
            "href": "//attacker.invalid/phish",
        },
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    notification_result = SimpleNamespace(scalar_one_or_none=lambda: notification)
    request_result = SimpleNamespace(
        all=lambda: [SimpleNamespace(id=request_id, requester_user_id=uuid.uuid4())]
    )
    mock_db.execute.side_effect = [notification_result, request_result]
    capabilities = SimpleNamespace(can_manage_billing=True, can_view_billing=True)

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        result = await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert result.destination == "/billing?intent=credits&source=capacity_request"
    assert "attacker.invalid" not in result.destination
    assert result.marked_read is False
    request_sql = str(mock_db.execute.await_args_list[1].args[0])
    assert "credit_capacity_requests.org_id" in request_sql
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_export_ready_requires_recipient_owned_completed_job(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    analysis_id = uuid.uuid4()
    export_job_id = uuid.uuid4()
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.EXPORT_READY,
        title="Stored export title",
        body="Stored export body",
        read=False,
        data={
            "export_job_id": str(export_job_id),
            "analysis_id": str(uuid.uuid4()),
            "href": "/admin",
        },
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: notification),
        SimpleNamespace(scalar_one_or_none=lambda: analysis_id),
    ]
    capabilities = SimpleNamespace(
        can_export_report=True,
        risk_ratings_restricted=False,
    )

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        result = await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert result.destination == f"/analyses/{analysis_id}/report"
    export_sql = str(mock_db.execute.await_args_list[1].args[0])
    assert "export_jobs.user_id" in export_sql
    assert "export_jobs.org_id" in export_sql
    assert "analyses.org_id" in export_sql


@pytest.mark.asyncio
async def test_resolve_monitor_alert_requires_current_monitor_and_alert_access(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    monitor_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.MONITOR_ALERT,
        title="Stored monitor details",
        body="Stored restricted monitor summary",
        read=False,
        data={
            "monitor_id": str(monitor_id),
            "alert_id": str(alert_id),
            "href": "/admin",
        },
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: notification),
        SimpleNamespace(scalar_one_or_none=lambda: monitor_id),
        SimpleNamespace(scalar_one_or_none=lambda: alert_id),
    ]
    capabilities = SimpleNamespace(can_manage_monitors=True)

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        result = await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert result.destination == "/monitors"
    monitor_sql = str(mock_db.execute.await_args_list[1].args[0])
    alert_sql = str(mock_db.execute.await_args_list[2].args[0])
    assert "monitors.org_id" in monitor_sql
    assert "monitor_alerts.org_id" in alert_sql
    assert "monitor_alerts.monitor_id" in alert_sql


@pytest.mark.asyncio
async def test_resolve_team_invite_admin_action_fails_after_role_downgrade(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.TEAM_INVITE,
        title="Stored invitation details",
        body="Stored team details",
        read=False,
        data={"action": "manage_users", "href": "/admin?tab=users"},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = notification
    capabilities = SimpleNamespace(can_view_platform_admin=False)

    with (
        patch(
            "api.services.notifications.build_principal_capabilities",
            return_value=capabilities,
        ),
        pytest.raises(APIError) as error,
    ):
        await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert error.value.status == 404
    assert notification.read is False
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_comment_assignment_requires_current_assignee_and_org(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.ATTORNEY,
    )
    comment_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        type=DBNotificationType.SYSTEM,
        title="Assigned by Customer Name",
        body="Stored comment content",
        read=False,
        data={
            "kind": "comment_assignment",
            "comment_id": str(comment_id),
            "assigned_to": str(user.id),
            "href": "/analyses/foreign",
        },
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    mock_db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: notification),
        SimpleNamespace(scalar_one_or_none=lambda: analysis_id),
    ]
    capabilities = SimpleNamespace(can_view_review_queue=True)

    with patch(
        "api.services.notifications.build_principal_capabilities",
        return_value=capabilities,
    ):
        result = await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=notification.id,
        )

    assert result.destination == "/reviews?filter=mine&sort=priority"
    comment_sql = str(mock_db.execute.await_args_list[1].args[0])
    assert "comments.assigned_to" in comment_sql
    assert "comments.org_id" in comment_sql
    assert "analyses.org_id" in comment_sql


@pytest.mark.asyncio
async def test_resolve_notification_rejects_cross_recipient_row(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=UserRole.SCIENTIST,
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(APIError) as error:
        await resolve_notification_action(
            mock_db,
            user=user,  # type: ignore[arg-type]
            notification_id=uuid.uuid4(),
        )

    assert error.value.status == 404
    lookup_sql = str(mock_db.execute.await_args.args[0])
    assert "notifications.user_id" in lookup_sql
    assert "notifications.org_id" in lookup_sql
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_unread_notification_count_returns_scalar(mock_db):
    mock_db.execute.return_value.scalar_one.return_value = 5

    count = await get_unread_notification_count(
        mock_db,
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )

    assert count == 5


@pytest.mark.asyncio
async def test_mark_notifications_read_updates_rows(mock_db):
    notification_id = uuid.uuid4()
    mock_db.execute.return_value.rowcount = 2

    marked = await mark_notifications_read(
        mock_db,
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        notification_ids=[notification_id],
    )

    assert marked == 2
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dismiss_all_notifications_updates_rows(mock_db):
    mock_db.execute.return_value.rowcount = 3

    marked = await dismiss_all_notifications(
        mock_db,
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )

    assert marked == 3
    mock_db.commit.assert_awaited_once()


def test_get_notification_preferences_uses_defaults():
    user = SimpleNamespace(id=uuid.uuid4(), preferences={})

    prefs = get_notification_preferences(user)  # type: ignore[arg-type]

    assert prefs == {
        "email_on_analysis_complete": True,
        "email_on_monitor_alert": True,
        "email_digest_frequency": "weekly",
    }


@pytest.mark.parametrize("legacy_frequency", ["daily", "immediate"])
def test_get_notification_preferences_normalizes_known_legacy_digest_frequency(
    legacy_frequency,
):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        preferences={"email_digest_frequency": legacy_frequency},
    )

    prefs = get_notification_preferences(user)  # type: ignore[arg-type]

    assert prefs["email_digest_frequency"] == "weekly"


def test_get_notification_preferences_rejects_unknown_digest_frequency():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        preferences={"email_digest_frequency": "hourly"},
    )

    with pytest.raises(ValueError, match="digest frequency is unsupported"):
        get_notification_preferences(user)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_notification_preferences_merges_values(mock_db):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        preferences={"theme": "dark", "email_on_analysis_complete": True},
    )
    # The service refetches the user with FOR UPDATE; return the same object.
    mock_db.execute.return_value.scalar_one_or_none.return_value = user
    body = NotificationPreferencesSchema(
        email_on_analysis_complete=False,
        email_on_monitor_alert=False,
        email_digest_frequency=DigestFrequency.WEEKLY,
    )

    payload = await update_notification_preferences(
        mock_db,
        user=user,  # type: ignore[arg-type]
        body=body,
    )

    assert payload == {
        "email_on_analysis_complete": False,
        "email_on_monitor_alert": False,
        "email_digest_frequency": "weekly",
    }
    assert user.preferences["theme"] == "dark"
    assert user.preferences["email_digest_frequency"] == "weekly"
    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
