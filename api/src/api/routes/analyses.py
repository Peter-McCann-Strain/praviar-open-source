"""Analysis CRUD routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from api.db.models import AnalysisStatus, User
from api.deps import (
    AuthenticatedPrincipal,
    DBSession,
    require_permission,
    require_permission_or_api_key_scope,
)
from api.errors import APIError, problem_type_uri
from api.middleware.input_validation import validate_analysis_input
from api.middleware.rate_limit import rate_limit_analysis
from api.ratelimit import limiter
from api.schemas.analyses import (
    AnalysisCursorListResponse,
    AnalysisListResponse,
    AnalysisResponse,
    CreateAnalysisRequest,
)
from api.schemas.common import StatusResponse
from api.schemas.review_handoff import (
    AnalysisReviewHandoffResponse,
    CreateAnalysisReviewHandoffRequest,
)
from api.schemas.review_status import (
    AnalysisReviewStatusResponse,
    UpdateAnalysisReviewStatusRequest,
)
from api.services.analyses import (
    create_analysis as create_analysis_service,
)
from api.services.analyses import (
    delete_analysis as delete_analysis_service,
)
from api.services.analyses import (
    flag_analysis_for_review as flag_analysis_for_review_service,
)
from api.services.analyses import (
    get_analysis_for_org,
    list_analyses_cursor,
    list_analyses_page,
    load_analysis_review_status,
    load_analysis_review_status_lookup,
    review_status_visible_for_role,
    serialize_analysis,
    serialize_analysis_page,
    serialize_cursor_page,
)
from api.services.review_status import (
    create_analysis_review_handoff_impl,
    get_analysis_review_status_impl,
    update_analysis_review_status_impl,
)
from api.services.risk_access import risk_ratings_restricted_for_role

router = APIRouter()

AnalysisCreatePrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("analysis.create", "analyses:write")),
]
AnalysisReadPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission_or_api_key_scope("analysis.view", "analyses:read")),
]

# Reusable 4xx Problem Details response schemas for OpenAPI spec
_PROBLEM_4XX = {
    "403": {
        "description": "Forbidden",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "404": {
        "description": "Not found",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "422": {
        "description": "Validation error",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
    "429": {
        "description": "Rate limit exceeded",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
}


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_analysis_input), Depends(rate_limit_analysis)],
    openapi_extra={
        "responses": _PROBLEM_4XX,
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "aspirin_fto": {
                            "summary": "Aspirin FTO (SMILES input)",
                            "value": {
                                "compound_input": "CC(=O)Oc1ccccc1C(=O)O",
                                "input_type": "smiles",
                                "submitted_identity_confirmed": True,
                                "submitted_identity_value": "CC(=O)Oc1ccccc1C(=O)O",
                                "trust_mode": "explorer",
                                "target_jurisdictions": ["US", "EP"],
                                "jurisdiction_bundle": "custom",
                                "development_stage": "discovery",
                            },
                        },
                        "ibuprofen_fto": {
                            "summary": "Ibuprofen FTO (name input)",
                            "value": {
                                "compound_input": "ibuprofen",
                                "input_type": "name",
                                "submitted_identity_confirmed": True,
                                "submitted_identity_value": "ibuprofen",
                                "trust_mode": "counsel",
                                "target_jurisdictions": ["US", "EP", "JP"],
                                "jurisdiction_bundle": "custom",
                                "development_stage": "preclinical",
                                "asset_type_hint": "formulation",
                                "product_context": {
                                    "dosage_form": "Oral tablet",
                                    "route_of_administration": "Oral",
                                    "strength": "200 mg",
                                },
                            },
                        },
                    }
                }
            }
        },
    },
)
@limiter.limit("10/minute")
async def create_analysis(
    body: CreateAnalysisRequest,
    user: AnalysisCreatePrincipal,
    db: DBSession,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[!-~]+$",
        ),
    ],
) -> dict:
    """Start or reconcile one idempotent FTO analysis pipeline run."""
    creation = await create_analysis_service(
        db,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
        idempotency_key=idempotency_key,
    )
    response.headers["Idempotency-Replayed"] = "true" if creation.replayed else "false"
    return serialize_analysis(
        creation.analysis,
        current_user_role=user.role.value,
        risk_ratings_restricted=risk_ratings_restricted_for_role(user.role),
    )


@router.get(
    "/analyses",
    response_model=AnalysisListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_analyses(
    user: AnalysisReadPrincipal,
    db: DBSession,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[AnalysisStatus | None, Query()] = None,
    risk_filter: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    sort_by: Annotated[
        str, Query(pattern="^(date-desc|date-asc|risk-desc|risk-asc)$")
    ] = "date-desc",
) -> dict:
    """List analyses for the current org (offset-based pagination)."""
    risk_ratings_restricted = risk_ratings_restricted_for_role(user.role)
    if risk_ratings_restricted and (
        risk_filter is not None or sort_by in {"risk-desc", "risk-asc"}
    ):
        raise APIError(
            403,
            "Forbidden",
            "Risk filters and risk sorting are restricted to attorney-role users",
            type_uri=problem_type_uri("risk-query-restricted"),
        )
    page_data = await list_analyses_page(
        db,
        org_id=user.org_id,
        page=page,
        per_page=per_page,
        status_filter=status_filter,
        risk_filter=risk_filter,
        search=search or None,
        sort_by=sort_by,
    )
    review_status_by_analysis_id = (
        await load_analysis_review_status_lookup(
            db,
            analyses=page_data.items,
            org_id=user.org_id,
        )
        if review_status_visible_for_role(user.role.value)
        else {}
    )
    return serialize_analysis_page(
        page_data,
        review_status_by_analysis_id=review_status_by_analysis_id,
        current_user_role=user.role.value,
        risk_ratings_restricted=risk_ratings_restricted,
    )


@router.get(
    "/analyses/cursor",
    response_model=AnalysisCursorListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_analyses_by_cursor(
    user: AnalysisReadPrincipal,
    db: DBSession,
    cursor: Annotated[
        str | None,
        Query(description="Opaque pagination cursor returned by the previous response."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[AnalysisStatus | None, Query()] = None,
    risk_filter: Annotated[str | None, Query()] = None,
) -> dict:
    """List analyses using stable cursor-based pagination.

    Pass the ``next_cursor`` value from a previous response as ``cursor`` to
    retrieve the following page.  When ``next_cursor`` is null the final page
    has been reached.  Results are ordered by ``created_at`` descending.
    """
    risk_ratings_restricted = risk_ratings_restricted_for_role(user.role)
    if risk_ratings_restricted and risk_filter is not None:
        raise APIError(
            403,
            "Forbidden",
            "Risk filters are restricted to attorney-role users",
            type_uri=problem_type_uri("risk-query-restricted"),
        )
    page_data = await list_analyses_cursor(
        db,
        org_id=user.org_id,
        cursor=cursor,
        limit=limit,
        status_filter=status_filter,
        risk_filter=risk_filter,
    )
    review_status_by_analysis_id = (
        await load_analysis_review_status_lookup(
            db,
            analyses=page_data.items,
            org_id=user.org_id,
        )
        if review_status_visible_for_role(user.role.value)
        else {}
    )
    return serialize_cursor_page(
        page_data,
        review_status_by_analysis_id=review_status_by_analysis_id,
        current_user_role=user.role.value,
        risk_ratings_restricted=risk_ratings_restricted,
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    openapi_extra={
        "responses": {
            **_PROBLEM_4XX,
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "completed_analysis": {
                                "summary": "Completed aspirin FTO analysis",
                                "value": {
                                    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                                    "compound_name": "aspirin",
                                    "compound_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                                    "status": "completed",
                                    "risk_rating": "low",
                                    "created_at": "2026-05-29T09:00:00Z",
                                    "completed_at": "2026-05-29T09:04:12Z",
                                },
                            }
                        }
                    }
                }
            },
        }
    },
)
async def get_analysis(
    analysis_id: uuid.UUID,
    user: AnalysisReadPrincipal,
    db: DBSession,
) -> dict:
    """Get a single analysis."""
    analysis = await get_analysis_for_org(db, analysis_id=analysis_id, org_id=user.org_id)
    review_status = (
        await load_analysis_review_status(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
        )
        if review_status_visible_for_role(user.role.value)
        else None
    )
    return serialize_analysis(
        analysis,
        review_status=review_status,
        current_user_role=user.role.value,
        risk_ratings_restricted=risk_ratings_restricted_for_role(user.role),
    )


@router.get(
    "/analyses/{analysis_id}/review-status",
    response_model=AnalysisReviewStatusResponse,
)
async def get_analysis_review_status(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("reviewer_decision.view"))],
    db: DBSession,
) -> AnalysisReviewStatusResponse:
    """Return persisted report-level review workflow state for an analysis."""
    return await get_analysis_review_status_impl(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )


@router.put(
    "/analyses/{analysis_id}/review-status",
    response_model=AnalysisReviewStatusResponse,
)
async def update_analysis_review_status(
    analysis_id: uuid.UUID,
    body: UpdateAnalysisReviewStatusRequest,
    user: Annotated[User, Depends(require_permission("reviewer_decision.create"))],
    db: DBSession,
    request: Request,
) -> AnalysisReviewStatusResponse:
    """Persist a report-level review workflow decision for an analysis."""
    return await update_analysis_review_status_impl(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        user=user,
        body=body,
        request=request,
    )


@router.post(
    "/analyses/{analysis_id}/review-handoff",
    response_model=AnalysisReviewHandoffResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis_review_handoff(
    analysis_id: uuid.UUID,
    body: CreateAnalysisReviewHandoffRequest,
    user: Annotated[User, Depends(require_permission("comment.create"))],
    db: DBSession,
    request: Request,
) -> AnalysisReviewHandoffResponse:
    """Create a targeted review handoff comment and escalate pending review state."""
    return await create_analysis_review_handoff_impl(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        user=user,
        body=body,
        request=request,
    )


@router.delete(
    "/analyses/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_analysis(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("analysis.delete"))],
    db: DBSession,
    request: Request,
) -> Response:
    """Cancel or soft-delete an analysis (attorney+ only).

    Soft deletes instead of hard deletes to prevent FK constraint violations
    from related comments, exports, and audit logs.
    """
    await delete_analysis_service(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/analyses/{analysis_id}/flag",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
)
async def flag_for_review(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("analysis.create"))],
    db: DBSession,
    request: Request,
) -> dict:
    """Flag an analysis for attorney review (scientist only)."""
    return await flag_analysis_for_review_service(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )
