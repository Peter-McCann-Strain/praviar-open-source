"""Attorney feedback routes."""

import uuid

from fastapi import APIRouter, Request, status

from api.db.models import UserRole
from api.deps import CurrentUser, DBSession
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.common import IdResponse
from api.schemas.feedback import (
    SearchRelevanceFeedbackIn,
    SearchRelevanceFeedbackListResponse,
    SearchRelevanceFeedbackOut,
    SubmitFeedbackRequest,
)
from api.services.feedback import (
    list_search_relevance_feedback,
    submit_attorney_feedback,
    submit_search_relevance_feedback,
)

router = APIRouter()


@router.post("/feedback", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def submit_feedback(
    body: SubmitFeedbackRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Submit attorney corrections on a report."""
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        raise APIError(403, "Forbidden", "Only attorneys can give feedback")

    record = await submit_attorney_feedback(
        db,
        user_id=user.id,
        org_id=user.org_id,
        body=body,
        request=request,
    )
    return {"id": record.id}


@router.post(
    "/analyses/{analysis_id}/search-relevance-feedback",
    response_model=IdResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def submit_search_relevance(
    analysis_id: uuid.UUID,
    body: SearchRelevanceFeedbackIn,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Capture an attorney relevance judgment bound to the current query plan."""
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        raise APIError(403, "Forbidden", "Only attorneys can give search relevance feedback")
    record = await submit_search_relevance_feedback(
        db,
        analysis_id=analysis_id,
        user=user,
        body=body,
        request=request,
    )
    return {"id": record.id}


@router.get(
    "/analyses/{analysis_id}/search-relevance-feedback",
    response_model=SearchRelevanceFeedbackListResponse,
)
async def list_search_relevance(
    analysis_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> SearchRelevanceFeedbackListResponse:
    """List case-scoped search relevance judgments for attorney review."""
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        raise APIError(403, "Forbidden", "Only attorneys can view search relevance feedback")
    rows, counts = await list_search_relevance_feedback(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    return SearchRelevanceFeedbackListResponse(
        items=[SearchRelevanceFeedbackOut.model_validate(row) for row in rows],
        counts=counts,
    )
