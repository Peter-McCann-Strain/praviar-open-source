"""Query-loading helpers for batch lifecycle operations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, AnalysisStatus, BatchAnalysis
from api.services.batch_types import BatchPage


async def load_batch_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
) -> BatchPage:
    offset = (page - 1) * per_page

    total_result = await db.execute(
        select(func.count()).select_from(BatchAnalysis).where(BatchAnalysis.org_id == org_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(BatchAnalysis)
        .where(BatchAnalysis.org_id == org_id)
        .order_by(BatchAnalysis.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    return BatchPage(items=list(result.scalars().all()), total=int(total))


async def load_batch_for_org(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    org_id: uuid.UUID,
    with_for_update: bool = False,
) -> BatchAnalysis | None:
    q = select(BatchAnalysis).where(BatchAnalysis.id == batch_id, BatchAnalysis.org_id == org_id)
    if with_for_update:
        q = q.with_for_update()
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def load_batch_by_launch_key(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    key_digest: str,
) -> BatchAnalysis | None:
    """Load one authoritative batch-launch receipt under a row lock."""
    result = await db.execute(
        select(BatchAnalysis)
        .where(
            BatchAnalysis.org_id == org_id,
            BatchAnalysis.launch_idempotency_key_digest == key_digest,
        )
        .with_for_update()
    )
    batch = result.scalar_one_or_none()
    return batch if isinstance(batch, BatchAnalysis) else None


async def load_batch_analyses_for_update(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[Analysis]:
    """Lock every child row belonging to a batch in deterministic order."""
    result = await db.execute(
        select(Analysis)
        .where(
            Analysis.batch_id == batch_id,
            Analysis.org_id == org_id,
        )
        .order_by(Analysis.created_at, Analysis.id)
        .with_for_update()
    )
    return list(result.scalars().all())


async def load_child_analysis_counts(
    db: AsyncSession,
    *,
    analysis_ids: list[str],
    org_id: uuid.UUID,
) -> tuple[int, int, int, int]:
    """Return (completed, failed, running, cancelled) counts for child analyses.

    Cancelled/deleted children are included so the batch can reach a terminal
    state when individual analyses are cancelled outside of ``cancel_batch``.
    """
    analysis_uuids = [uuid.UUID(analysis_id) for analysis_id in analysis_ids]

    result = await db.execute(
        select(
            Analysis.status,
            func.count().label("cnt"),
        )
        .select_from(Analysis)
        .where(
            Analysis.id.in_(analysis_uuids),
            Analysis.org_id == org_id,
            Analysis.status.in_(
                [
                    AnalysisStatus.COMPLETED,
                    AnalysisStatus.FAILED,
                    AnalysisStatus.RUNNING,
                    AnalysisStatus.CANCELLED,
                    AnalysisStatus.DELETED,
                ]
            ),
        )
        .group_by(Analysis.status)
    )
    counts = {row.status: row.cnt for row in result}
    return (
        counts.get(AnalysisStatus.COMPLETED, 0),
        counts.get(AnalysisStatus.FAILED, 0),
        counts.get(AnalysisStatus.RUNNING, 0),
        counts.get(AnalysisStatus.CANCELLED, 0) + counts.get(AnalysisStatus.DELETED, 0),
    )


async def load_cancelable_analyses(
    db: AsyncSession,
    *,
    analysis_ids: list[str],
    org_id: uuid.UUID,
) -> list[Analysis]:
    analysis_uuids = [uuid.UUID(analysis_id) for analysis_id in analysis_ids]
    cancel_result = await db.execute(
        select(Analysis)
        .where(
            Analysis.id.in_(analysis_uuids),
            Analysis.org_id == org_id,
            Analysis.status.in_([AnalysisStatus.PENDING, AnalysisStatus.RUNNING]),
        )
        .with_for_update()
    )
    return list(cancel_result.scalars().all())
