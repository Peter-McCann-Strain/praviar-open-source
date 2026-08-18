"""Compound library routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DBSession
from api.schemas.compounds import CompoundCompareResponse, CompoundListResponse, CompoundResponse
from api.services.compounds import (
    MAX_COMPOUND_SEARCH_LENGTH,
)
from api.services.compounds import (
    compare_compounds_for_org as _compare_compounds_for_org,
)
from api.services.compounds import (
    get_compound_for_org as _get_compound_for_org,
)
from api.services.compounds import (
    list_compounds_for_org as _list_compounds_for_org,
)

router = APIRouter()


@router.get("/compounds", response_model=CompoundListResponse)
async def list_compounds(
    user: CurrentUser,
    db: DBSession,
    search: str | None = Query(default=None, max_length=MAX_COMPOUND_SEARCH_LENGTH),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List compounds analyzed by the current org."""
    return await _list_compounds_for_org(
        db,
        user.org_id,
        search=search,
        page=page,
        per_page=per_page,
    )


@router.get("/compounds/compare", response_model=CompoundCompareResponse)
async def compare_compounds(
    user: CurrentUser,
    db: DBSession,
    ids: list[uuid.UUID] = Query(..., min_length=2, max_length=4),  # noqa: B008
) -> dict:
    """Compare 2-4 compounds side by side (org-scoped)."""
    return await _compare_compounds_for_org(db, user.org_id, ids)


@router.get("/compounds/{compound_id}", response_model=CompoundResponse)
async def get_compound(
    compound_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> CompoundResponse:
    """Get a single compound profile (org-scoped)."""
    return await _get_compound_for_org(db, user.org_id, compound_id)
