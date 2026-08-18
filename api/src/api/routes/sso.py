"""SSO configuration endpoints.

GET  /admin/sso/status     — return live SSO state for the caller's org
POST /admin/sso/configure  — log intent and return Clerk dashboard instructions
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request

from api.db.models import User
from api.deps import DBSession, require_permission
from api.schemas.sso import SSOConfigureRequest, SSOConfigureResponse, SSOStatusResponse
from api.services.sso import configure_sso, get_sso_status

logger = structlog.get_logger()

router = APIRouter()

SSOAdmin = Annotated[User, Depends(require_permission("admin.view"))]
SSOManager = Annotated[User, Depends(require_permission("admin.manage_users"))]

_PROBLEM_4XX = {
    "401": {
        "description": "Authentication required",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "403": {
        "description": "Forbidden — admin role required",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "404": {
        "description": "Organization not found",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "503": {
        "description": "SSO status persistence or freshness unavailable",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
}


@router.get(
    "/admin/sso/status",
    response_model=SSOStatusResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Get SSO status",
    description=(
        "Returns the current Clerk Enterprise Connection status for the caller's organisation. "
        "Queries the Clerk Backend API and syncs the result into the local database. "
        "When Clerk is unavailable, preserves cached identity fields while explicitly marking "
        "the response unavailable and stale."
    ),
)
async def get_sso_status_endpoint(
    user: SSOAdmin,
    db: DBSession,
) -> SSOStatusResponse:
    return await get_sso_status(db, org_id=user.org_id)


@router.post(
    "/admin/sso/configure",
    response_model=SSOConfigureResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
    summary="Request SSO configuration",
    description=(
        "Logs an admin intent to enable or disable SSO and returns step-by-step instructions "
        "for completing the configuration in the Clerk dashboard. Full SAML/OIDC setup "
        "(IdP metadata upload, attribute mapping) must be completed there."
    ),
)
async def configure_sso_endpoint(
    body: SSOConfigureRequest,
    user: SSOManager,
    db: DBSession,
    request: Request,
) -> SSOConfigureResponse:
    return await configure_sso(
        db,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
    )
