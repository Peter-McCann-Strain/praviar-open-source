"""Serialization helpers for batch analysis models."""

from __future__ import annotations

from typing import Protocol

from api.db.models import BatchAnalysis


class BatchPageLike(Protocol):
    @property
    def items(self) -> list[BatchAnalysis]: ...

    @property
    def total(self) -> int: ...


def serialize_batch(batch: BatchAnalysis) -> dict:
    return {
        "id": batch.id,
        "name": batch.name,
        "total_compounds": batch.total_compounds,
        "completed_count": batch.completed_count,
        "failed_count": batch.failed_count,
        "status": batch.status.value,
        "analysis_ids": batch.analysis_ids,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def serialize_batch_page(page: BatchPageLike) -> dict:
    return {"items": [serialize_batch(batch) for batch in page.items], "total": page.total}
