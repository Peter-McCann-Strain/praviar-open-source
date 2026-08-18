"""Request/response schemas for compounds."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CompoundResponse(BaseModel):
    id: uuid.UUID
    canonical_smiles: str
    inchi_key: str
    name: str
    molecular_formula: str
    molecular_weight: float | None
    functional_groups: list[str]
    pubchem_cid: int | None
    first_analyzed_at: datetime
    analysis_count: int


class CompoundListResponse(BaseModel):
    items: list[CompoundResponse]
    total: int
    page: int = 1
    per_page: int = 20


class CompoundCompareResponse(BaseModel):
    compounds: list[CompoundResponse]
    overlapping_patents: list[dict[str, Any]]
