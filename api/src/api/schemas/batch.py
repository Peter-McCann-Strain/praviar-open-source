"""Batch analysis schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.analyses import AnalysisConfigSchema


class CreateBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    compounds: list[Annotated[str, Field(min_length=1, max_length=5000)]] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of compound inputs (SMILES or names)",
    )
    config: AnalysisConfigSchema | None = Field(
        default=None,
        description="Shared pipeline config for all compounds in batch",
    )


class BatchResponse(BaseModel):
    id: uuid.UUID
    name: str
    total_compounds: int
    completed_count: int
    failed_count: int
    status: str
    analysis_ids: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchListResponse(BaseModel):
    items: list[BatchResponse]
    total: int
