"""Shared value types for batch lifecycle services."""

from __future__ import annotations

from dataclasses import dataclass

from api.db.models import BatchAnalysis


@dataclass(frozen=True)
class BatchPage:
    items: list[BatchAnalysis]
    total: int
