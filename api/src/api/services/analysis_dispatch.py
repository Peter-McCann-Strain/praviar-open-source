"""Bounded, persisted dispatch reconciliation for orphaned analysis launches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.db.models import AnalysisStatus
from api.db.models_analysis import Analysis

PIPELINE_RECONCILIATION_COOLDOWN = timedelta(hours=1)
MAX_PIPELINE_RECONCILIATION_GENERATIONS = 6


@dataclass(frozen=True)
class PipelineReconciliationReservation:
    """One stable Cloud Tasks name generation within a bounded cooldown."""

    generation: int
    advanced: bool
    exhausted: bool = False

    @property
    def task_key(self) -> str:
        return f"repair-{self.generation}"


def reserve_pipeline_reconciliation(
    analysis: Analysis,
    *,
    now: datetime | None = None,
) -> PipelineReconciliationReservation | None:
    """Reserve or reuse the repair generation on an authoritative locked row."""
    if analysis.status != AnalysisStatus.PENDING or analysis.pipeline_execution_id is not None:
        return None

    current_time = now or datetime.now(UTC)
    generation = max(0, int(analysis.pipeline_reconciliation_generation or 0))
    last_dispatched_at = analysis.pipeline_reconciliation_dispatched_at
    if last_dispatched_at is not None and last_dispatched_at.tzinfo is None:
        last_dispatched_at = last_dispatched_at.replace(tzinfo=UTC)

    within_cooldown = (
        generation > 0
        and last_dispatched_at is not None
        and last_dispatched_at > current_time - PIPELINE_RECONCILIATION_COOLDOWN
    )
    if within_cooldown:
        return PipelineReconciliationReservation(
            generation=generation,
            advanced=False,
        )

    if generation >= MAX_PIPELINE_RECONCILIATION_GENERATIONS:
        return PipelineReconciliationReservation(
            generation=generation,
            advanced=False,
            exhausted=True,
        )

    generation += 1
    analysis.pipeline_reconciliation_generation = generation
    analysis.pipeline_reconciliation_dispatched_at = current_time
    return PipelineReconciliationReservation(
        generation=generation,
        advanced=True,
    )
