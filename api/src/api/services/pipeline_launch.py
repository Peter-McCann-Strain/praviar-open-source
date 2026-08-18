"""Durable execution reservations for the Cloud Tasks → Cloud Run Jobs handoff."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.db.models import AnalysisStatus

PIPELINE_JOB_LAUNCH_RESERVATION_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class PipelineJobReservation:
    """One persisted execution fence shared by every duplicate launch attempt."""

    status: str
    execution_id: uuid.UUID | None
    reused: bool

    @property
    def launchable(self) -> bool:
        return self.execution_id is not None


def reserve_pipeline_job_execution(
    analysis,
    *,
    now: datetime | None = None,
) -> PipelineJobReservation:
    """Reserve or reuse a Job execution ID on an authoritative locked Analysis row."""
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("pipeline launch reservation time must be timezone-aware")

    if analysis.status == AnalysisStatus.COMPLETED:
        return PipelineJobReservation("already_completed", None, False)
    if analysis.status == AnalysisStatus.FAILED:
        return PipelineJobReservation("already_failed", None, False)
    if analysis.status == AnalysisStatus.CANCELLED:
        return PipelineJobReservation("cancelled", None, False)
    if analysis.status == AnalysisStatus.DELETED:
        return PipelineJobReservation("deleted", None, False)
    if analysis.status == AnalysisStatus.RUNNING:
        return PipelineJobReservation("already_running", None, False)
    if analysis.status != AnalysisStatus.PENDING:
        raise ValueError(f"Unsupported analysis status for pipeline launch: {analysis.status!r}")

    existing_execution_id = analysis.pipeline_execution_id
    existing_expiry = analysis.pipeline_lease_expires_at
    if existing_expiry is not None and existing_expiry.tzinfo is None:
        raise ValueError("pipeline launch reservation expiry must be timezone-aware")
    if (
        existing_execution_id is not None
        and existing_expiry is not None
        and existing_expiry > current_time
    ):
        return PipelineJobReservation(
            status="launch_reserved",
            execution_id=existing_execution_id,
            reused=True,
        )

    execution_id = uuid.uuid4()
    analysis.pipeline_execution_id = execution_id
    analysis.pipeline_lease_expires_at = current_time + PIPELINE_JOB_LAUNCH_RESERVATION_TTL
    return PipelineJobReservation(
        status="launch_reserved",
        execution_id=execution_id,
        reused=False,
    )
