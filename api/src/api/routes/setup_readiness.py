"""Organization-scoped setup readiness route."""

from fastapi import APIRouter

from api.deps import CurrentUser, DBSession
from api.schemas.setup_readiness import SetupReadinessResponse
from api.services.setup_readiness import get_setup_readiness

router = APIRouter()


@router.get("/setup-readiness", response_model=SetupReadinessResponse)
async def setup_readiness(user: CurrentUser, db: DBSession) -> SetupReadinessResponse:
    """Return the current user's authoritative tenant setup checklist."""
    return await get_setup_readiness(db, user=user)
