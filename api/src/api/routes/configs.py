"""Configuration presets and org defaults routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from api.db.models import User, UserRole
from api.deps import CurrentUser, DBSession, require_permission
from api.schemas.common import StatusResponse
from api.schemas.configs import (
    CreatePresetRequest,
    OrgDefaultsResponse,
    PresetCreatedResponse,
    PresetResponse,
    SetOrgDefaultsRequest,
)
from api.services.configs import (
    create_preset as create_config_preset,
)
from api.services.configs import (
    list_presets_for_org,
    load_org_default_config,
    set_org_default_config,
)

router = APIRouter()


@router.get("/configs/presets", response_model=list[PresetResponse])
async def list_presets(
    user: CurrentUser,
    db: DBSession,
) -> list[dict]:
    """List configuration presets for the org."""
    presets = await list_presets_for_org(db, org_id=user.org_id)
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "config": p.config,
            "is_default": p.is_default,
        }
        for p in presets
    ]


@router.post(
    "/configs/presets",
    response_model=PresetCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_preset(
    body: CreatePresetRequest,
    user: Annotated[User, Depends(require_permission("config.manage"))],
    db: DBSession,
    request: Request,
) -> dict:
    """Create a new configuration preset (admin/attorney only)."""
    preset = await create_config_preset(
        db,
        org_id=user.org_id,
        user_id=user.id,
        user_role=user.role,
        body=body,
        request=request,
    )

    return {"id": preset.id, "name": preset.name}


@router.put("/configs/defaults", response_model=StatusResponse)
async def set_org_defaults(
    body: SetOrgDefaultsRequest,
    user: Annotated[User, Depends(require_permission("config.manage"))],
    db: DBSession,
    request: Request,
) -> dict:
    """Set organization-wide default configuration (admin/attorney only)."""
    await set_org_default_config(
        db,
        org_id=user.org_id,
        user_id=user.id,
        user_role=user.role,
        body=body,
        request=request,
    )
    return {"status": "updated"}


@router.get("/configs/defaults", response_model=OrgDefaultsResponse)
async def get_org_defaults(
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Read organization-wide default configuration for this tenant."""
    config = await load_org_default_config(db, org_id=user.org_id)
    return {
        "config": config,
        "can_manage": user.role in (UserRole.ADMIN, UserRole.ATTORNEY),
    }
