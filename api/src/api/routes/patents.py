"""Patent browser routes.

Uses SQL-level JSONB extraction to avoid loading all analyses into memory.
"""

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Query

from api.db.models import UserRole
from api.deps import CurrentUser, DBSession
from api.errors import APIError
from api.schemas.patents import (
    PatentDetailResponse,
    PatentListResponse,
    RiskRestrictedPatentDetailResponse,
    RiskRestrictedPatentListResponse,
)
from api.services.patents import (
    get_patent_detail_for_org as _get_patent_detail_for_org,
)
from api.services.patents import (
    list_patents_for_org as _list_patents_for_org,
)
from api.services.risk_access import risk_ratings_restricted_for_role

logger = structlog.get_logger()

router = APIRouter()


PatentSort = Literal["id-asc", "id-desc", "risk-desc", "risk-asc"]
PatentRiskFilter = Literal["high", "medium", "low", "clear"]


@router.get(
    "/patents",
    response_model=PatentListResponse | RiskRestrictedPatentListResponse,
)
async def list_patents(
    user: CurrentUser,
    db: DBSession,
    risk_filter: Annotated[PatentRiskFilter | None, Query()] = None,
    search: str | None = Query(default=None, max_length=200),
    sort_by: Annotated[PatentSort | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PatentListResponse | RiskRestrictedPatentListResponse:
    """Browse all patents across analyses.

    Extracts patent data from the report_data JSONB field at the SQL level
    using jsonb_array_elements, with deduplication via DISTINCT ON and
    server-side pagination.
    """
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST):
        raise APIError(403, "Forbidden", "Insufficient permissions")

    risk_ratings_restricted = risk_ratings_restricted_for_role(user.role)
    resolved_sort: PatentSort = sort_by or ("id-asc" if risk_ratings_restricted else "risk-desc")
    payload = await _list_patents_for_org(
        db,
        org_id=user.org_id,
        risk_ratings_restricted=risk_ratings_restricted,
        risk_filter=risk_filter,
        search=search,
        sort_by=resolved_sort,
        page=page,
        per_page=per_page,
    )
    response_type = (
        RiskRestrictedPatentListResponse if risk_ratings_restricted else PatentListResponse
    )
    return response_type.model_validate(payload)


@router.get(
    "/patents/{patent_id}",
    response_model=PatentDetailResponse | RiskRestrictedPatentDetailResponse,
)
async def get_patent(
    patent_id: str,
    user: CurrentUser,
    db: DBSession,
) -> PatentDetailResponse | RiskRestrictedPatentDetailResponse:
    """Get deep-dive data for a specific patent across all analyses."""
    if user.role not in (UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST):
        raise APIError(403, "Forbidden", "Insufficient permissions")
    risk_ratings_restricted = risk_ratings_restricted_for_role(user.role)
    payload = await _get_patent_detail_for_org(
        db,
        patent_id=patent_id,
        org_id=user.org_id,
        risk_ratings_restricted=risk_ratings_restricted,
    )
    response_type = (
        RiskRestrictedPatentDetailResponse if risk_ratings_restricted else PatentDetailResponse
    )
    return response_type.model_validate(payload)
