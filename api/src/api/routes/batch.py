"""Batch analysis routes."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response

from api.db.models import User
from api.deps import DBSession, require_permission
from api.ratelimit import limiter
from api.schemas.batch import (
    BatchListResponse,
    BatchResponse,
    CreateBatchRequest,
)
from api.services.batch import (
    cancel_batch as cancel_batch_service,
)
from api.services.batch import (
    create_batch as create_batch_service,
)
from api.services.batch import (
    get_batch_with_live_status,
    list_batches_page,
    serialize_batch,
    serialize_batch_page,
)

logger = structlog.get_logger()

router = APIRouter()

BatchUser = Annotated[User, Depends(require_permission("batch.create"))]

_PROBLEM_4XX = {
    "401": {
        "description": "Authentication required",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
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
    "409": {
        "description": "Idempotency key reused with a different request",
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
    "503": {
        "description": "Pipeline dispatch outcome could not be confirmed",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
        },
    },
}


@router.post(
    "/batch",
    response_model=BatchResponse,
    status_code=201,
    openapi_extra={"responses": _PROBLEM_4XX},
)
@limiter.limit("5/minute")
async def create_batch(
    body: CreateBatchRequest,
    user: BatchUser,
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
    """Create a batch analysis for multiple compounds."""
    logger.info(
        "create_batch",
        user_id=str(user.id),
        org_id=str(user.org_id),
        name=body.name,
        compound_count=len(body.compounds),
    )

    creation = await create_batch_service(
        db,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
        idempotency_key=idempotency_key,
    )

    response.headers["Idempotency-Replayed"] = "true" if creation.replayed else "false"
    return serialize_batch(creation.batch)


@router.get(
    "/batch",
    response_model=BatchListResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def list_batches(
    user: BatchUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    """List batch analyses for the current org."""
    page_data = await list_batches_page(db, org_id=user.org_id, page=page, per_page=per_page)
    return serialize_batch_page(page_data)


@router.get(
    "/batch/{batch_id}",
    response_model=BatchResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def get_batch(
    batch_id: uuid.UUID,
    user: BatchUser,
    db: DBSession,
) -> dict:
    """Get a batch analysis with live status recomputed from child analyses."""
    batch = await get_batch_with_live_status(db, batch_id=batch_id, org_id=user.org_id)
    return serialize_batch(batch)


@router.delete(
    "/batch/{batch_id}",
    openapi_extra={"responses": _PROBLEM_4XX},
)
async def cancel_batch(
    batch_id: uuid.UUID,
    user: BatchUser,
    db: DBSession,
    request: Request,
) -> dict:
    """Cancel a batch and all its pending/running analyses."""
    await cancel_batch_service(
        db,
        batch_id=batch_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )
    logger.info("batch_cancelled", batch_id=str(batch_id), user_id=str(user.id))

    return {"status": "cancelled"}
