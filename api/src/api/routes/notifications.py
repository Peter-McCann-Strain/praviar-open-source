"""Notification routes — in-app notifications and email preferences."""

import uuid

import structlog
from fastapi import APIRouter, Query, Request, status

from api.deps import CurrentUser, DBSession
from api.ratelimit import digest_unsubscribe_rate_limit_key, limiter
from api.schemas.notifications import (
    DigestUnsubscribeRequest,
    DigestUnsubscribeResponse,
    MarkReadRequest,
    NotificationActionResponse,
    NotificationListResponse,
    NotificationPreferencesSchema,
    UnreadCountResponse,
)
from api.services.notifications import (
    dismiss_all_notifications,
    get_notification_preferences,
    get_unread_notification_count,
    list_notifications_page,
    mark_notifications_read,
    resolve_notification_action,
    unsubscribe_weekly_digest,
    update_notification_preferences,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/notifications", tags=["notifications"])
public_router = APIRouter(prefix="/notifications", tags=["notifications"])


@public_router.post(
    "/unsubscribe/digest/{token_locator}",
    response_model=DigestUnsubscribeResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("6/hour", key_func=digest_unsubscribe_rate_limit_key)
async def unsubscribe_digest(
    token_locator: str,
    body: DigestUnsubscribeRequest,
    db: DBSession,
    request: Request,
) -> dict[str, str]:
    """Disable recurring digest delivery from a signed one-click token."""
    return await unsubscribe_weekly_digest(
        db,
        token=body.token,
        token_locator=token_locator,
        request=request,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List notifications for the current user, newest first."""
    page_data = await list_notifications_page(
        db,
        user=user,
        page=page,
        per_page=per_page,
    )
    return {
        "items": page_data.items,
        "unread_count": page_data.unread_count,
        "total": page_data.total,
    }


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Return just the unread notification count (for badge polling)."""
    count = await get_unread_notification_count(db, user_id=user.id, org_id=user.org_id)
    return {"unread_count": count}


@router.post("/mark-read", status_code=status.HTTP_200_OK)
async def mark_read(
    body: MarkReadRequest,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Mark specific notifications as read."""
    marked = await mark_notifications_read(
        db,
        user_id=user.id,
        org_id=user.org_id,
        notification_ids=body.notification_ids,
    )
    return {"marked": marked}


@router.post(
    "/{notification_id}/resolve-action",
    response_model=NotificationActionResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_action(
    notification_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Resolve a current safe destination for a recipient-owned notification."""
    result = await resolve_notification_action(
        db,
        user=user,
        notification_id=notification_id,
    )
    return {
        "notification_id": result.notification_id,
        "actionable": result.actionable,
        "destination": result.destination,
        "marked_read": result.marked_read,
    }


@router.post("/dismiss-all", status_code=status.HTTP_200_OK)
async def dismiss_all(
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Mark all notifications as read for the current user."""
    marked = await dismiss_all_notifications(db, user_id=user.id, org_id=user.org_id)
    return {"marked": marked}


@router.get("/preferences", response_model=NotificationPreferencesSchema)
async def get_preferences(
    user: CurrentUser,
) -> dict:
    """Get the current user's email notification preferences."""
    return get_notification_preferences(user)


@router.put("/preferences", response_model=NotificationPreferencesSchema)
async def update_preferences(
    body: NotificationPreferencesSchema,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Update the current user's email notification preferences.

    Merges notification preferences into the User.preferences JSONB column
    without overwriting other preference keys (theme, sidebar, etc.).
    """
    return await update_notification_preferences(
        db,
        user=user,
        body=body,
    )
