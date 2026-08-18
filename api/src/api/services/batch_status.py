"""Batch status aggregation helpers."""

from __future__ import annotations

from api.db.models import AnalysisStatus


def recompute_batch_status(
    *,
    total_compounds: int,
    completed_count: int,
    failed_count: int,
    running_count: int,
    cancelled_count: int = 0,
) -> AnalysisStatus:
    # Individually cancelled/deleted children reduce the effective target so the
    # batch can reach a terminal state even when not all were dispatched.
    effective_total = max(0, total_compounds - cancelled_count)
    if effective_total == 0:
        return AnalysisStatus.CANCELLED
    if running_count > 0:
        return AnalysisStatus.RUNNING
    if completed_count >= effective_total:
        return AnalysisStatus.COMPLETED
    if (completed_count + failed_count) >= effective_total:
        return AnalysisStatus.FAILED if failed_count > 0 else AnalysisStatus.COMPLETED
    if completed_count > 0 or failed_count > 0:
        return AnalysisStatus.RUNNING
    return AnalysisStatus.PENDING
