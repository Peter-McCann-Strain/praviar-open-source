"""Authenticated principal capability route."""

from fastapi import APIRouter

from api.deps import CurrentUser
from api.schemas.principal import PrincipalCapabilitiesResponse
from api.services.principal_capabilities import build_principal_capabilities

router = APIRouter()


@router.get(
    "/principal/capabilities",
    response_model=PrincipalCapabilitiesResponse,
)
async def get_principal_capabilities(
    user: CurrentUser,
) -> PrincipalCapabilitiesResponse:
    """Return the current user's lightweight role and capability snapshot."""
    return build_principal_capabilities(user)
