from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import make_analysis_mock

from api.db.models import AnalysisStatus
from api.services.analysis_dispatch import (
    MAX_PIPELINE_RECONCILIATION_GENERATIONS,
    PIPELINE_RECONCILIATION_COOLDOWN,
    reserve_pipeline_reconciliation,
)


def test_reconciliation_reuses_generation_within_cooldown_and_advances_later() -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    analysis = make_analysis_mock(
        status=AnalysisStatus.PENDING,
        pipeline_reconciliation_generation=0,
    )

    first = reserve_pipeline_reconciliation(analysis, now=now)
    repeated = reserve_pipeline_reconciliation(
        analysis,
        now=now + timedelta(minutes=15),
    )
    later = reserve_pipeline_reconciliation(
        analysis,
        now=now + PIPELINE_RECONCILIATION_COOLDOWN + timedelta(seconds=1),
    )

    assert first is not None
    assert repeated is not None
    assert later is not None
    assert first.task_key == "repair-1"
    assert first.advanced is True
    assert repeated.task_key == first.task_key
    assert repeated.advanced is False
    assert later.task_key == "repair-2"
    assert later.advanced is True


def test_reconciliation_exhausts_only_after_final_generation_cooldown() -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    analysis = make_analysis_mock(
        status=AnalysisStatus.PENDING,
        pipeline_reconciliation_generation=MAX_PIPELINE_RECONCILIATION_GENERATIONS,
        pipeline_reconciliation_dispatched_at=now,
    )

    within_cooldown = reserve_pipeline_reconciliation(
        analysis,
        now=now + timedelta(minutes=15),
    )
    exhausted = reserve_pipeline_reconciliation(
        analysis,
        now=now + PIPELINE_RECONCILIATION_COOLDOWN + timedelta(seconds=1),
    )

    assert within_cooldown is not None
    assert within_cooldown.exhausted is False
    assert within_cooldown.task_key == (f"repair-{MAX_PIPELINE_RECONCILIATION_GENERATIONS}")
    assert exhausted is not None
    assert exhausted.exhausted is True


def test_reconciliation_skips_claimed_or_terminal_analysis() -> None:
    claimed = make_analysis_mock(
        status=AnalysisStatus.PENDING,
        pipeline_execution_id="worker-lease",
    )
    terminal = make_analysis_mock(status=AnalysisStatus.FAILED)

    assert reserve_pipeline_reconciliation(claimed) is None
    assert reserve_pipeline_reconciliation(terminal) is None
