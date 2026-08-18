"""API key management routes."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, Request

from api.db.models import User
from api.deps import DBSession, require_permission
from api.ratelimit import limiter
from api.schemas.apikeys import (
    APIKeyCreatedResponse,
    APIKeyListResponse,
    CreateAPIKeyRequest,
)
from api.services.apikeys import (
    create_api_key as create_api_key_record,
)
from api.services.apikeys import (
    list_api_keys_for_org,
)
from api.services.apikeys import (
    revoke_api_key as revoke_api_key_record,
)

logger = structlog.get_logger()

router = APIRouter()

APIKeyAdmin = Annotated[User, Depends(require_permission("apikey.manage"))]


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
@limiter.limit("10/minute")
async def create_api_key(
    body: CreateAPIKeyRequest,
    user: APIKeyAdmin,
    db: DBSession,
    request: Request,
) -> dict:
    """Create an API key. The secret is returned once and cannot be retrieved again."""
    logger.info(
        "create_api_key",
        user_id=str(user.id),
        org_id=str(user.org_id),
        name=body.name,
        scopes=list(body.scopes),
        expires_at=body.expires_at.isoformat(),
    )

    created = await create_api_key_record(
        db,
        org_id=user.org_id,
        user_id=user.id,
        body=body,
        request=request,
    )

    return {
        "id": created.api_key.id,
        "name": created.api_key.name,
        "key_prefix": created.api_key.key_prefix,
        "secret_key": created.secret_key,
        "scopes": created.api_key.scopes,
        "expires_at": created.api_key.expires_at,
        "created_at": created.api_key.created_at,
    }


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys(
    user: APIKeyAdmin,
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    """List API keys for the current org (secrets are never returned)."""
    result = await list_api_keys_for_org(
        db,
        org_id=user.org_id,
        page=page,
        per_page=per_page,
    )
    return {"items": result.items, "total": result.total}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: uuid.UUID,
    user: APIKeyAdmin,
    db: DBSession,
    request: Request,
) -> dict:
    """Revoke an API key (soft delete — preserves audit trail)."""
    await revoke_api_key_record(
        db,
        key_id=key_id,
        org_id=user.org_id,
        user_id=user.id,
        request=request,
    )

    return {"status": "revoked"}
