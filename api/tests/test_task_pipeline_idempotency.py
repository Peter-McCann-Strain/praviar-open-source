"""Idempotency regressions for analysis pipeline execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
)
from praviar_pipeline.errors import PipelineCancelledError
from praviar_pipeline.report_certification_binding import (
    ReportCertificationVerificationKeyRing,
    verify_report_certification_binding,
)
from pydantic import SecretStr

from api.db.models import AnalysisStatus
from api.workers.task_pipeline import run_pipeline_execution


def _build_kwargs(
    *,
    status: AnalysisStatus,
    lease_expires_at=None,
    run_async_fn=None,
    pipeline_runner_factory=None,
) -> dict:
    analysis = SimpleNamespace(
        id="analysis-1",
        org_id="org-1",
        status=status,
        current_step=7,
        progress_pct=80.0,
        pipeline_execution_id=None,
        pipeline_lease_expires_at=lease_expires_at,
        completed_at=None,
        overall_risk="",
        pipeline_duration_seconds=None,
    )
    db = MagicMock()
    logger = MagicMock()
    run_async = run_async_fn or MagicMock(
        return_value={"report_id": "test-report-id", "compound": {}}
    )
    runner_factory = pipeline_runner_factory or MagicMock(return_value=object())

    def is_cancelled(current_status):
        return current_status in {AnalysisStatus.CANCELLED, AnalysisStatus.DELETED}

    return {
        "db": db,
        "analysis": analysis,
        "analysis_id": "analysis-1",
        "pipeline_start": 0.0,
        "redis_client": MagicMock(),
        "lost_event_counts": {},
        "logger": logger,
        "publish_event_fn": MagicMock(),
        "is_cancelled_fn": is_cancelled,
        "store_pipeline_results_fn": MagicMock(),
        "upsert_compound_fn": MagicMock(),
        "run_async_fn": run_async,
        "pipeline_runner_factory": runner_factory,
        "log_output_dir_fn": MagicMock(),
        "write_audit_fn": MagicMock(),
        "lease_ttl_seconds": 1800,
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (AnalysisStatus.COMPLETED, "already_completed"),
        (AnalysisStatus.CANCELLED, "cancelled"),
        (AnalysisStatus.DELETED, "deleted"),
    ],
)
def test_run_pipeline_execution_skips_terminal_analyses(status, expected):
    kwargs = _build_kwargs(status=status)

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": expected, "analysis_id": "analysis-1"}
    kwargs["db"].refresh.assert_called_once_with(kwargs["analysis"], with_for_update=True)
    kwargs["db"].rollback.assert_called_once()
    kwargs["db"].commit.assert_not_called()
    kwargs["run_async_fn"].assert_not_called()
    kwargs["pipeline_runner_factory"].assert_not_called()
    kwargs["store_pipeline_results_fn"].assert_not_called()


def test_run_pipeline_execution_skips_active_duplicate_delivery():
    kwargs = _build_kwargs(
        status=AnalysisStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "already_running", "analysis_id": "analysis-1"}
    kwargs["db"].rollback.assert_called_once()
    kwargs["db"].commit.assert_not_called()
    kwargs["run_async_fn"].assert_not_called()
    kwargs["logger"].info.assert_called_once_with(
        "pipeline_skipped_idempotent_analysis",
        analysis_id="analysis-1",
        status=str(AnalysisStatus.RUNNING),
        skip_status="already_running",
    )


def test_provider_retry_adopts_matching_active_execution_fence() -> None:
    execution_id = uuid.uuid4()
    kwargs = _build_kwargs(
        status=AnalysisStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    kwargs["analysis"].pipeline_execution_id = execution_id
    kwargs["expected_execution_id"] = execution_id
    kwargs["provider_retry_attempt"] = 1

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "completed", "analysis_id": "analysis-1"}
    kwargs["run_async_fn"].assert_called_once()
    kwargs["logger"].warning.assert_any_call(
        "pipeline_provider_retry_adopting_active_fence",
        analysis_id="analysis-1",
        execution_id=str(execution_id),
        provider_retry_attempt=1,
    )


def test_initial_provider_attempt_cannot_adopt_matching_active_fence() -> None:
    execution_id = uuid.uuid4()
    kwargs = _build_kwargs(
        status=AnalysisStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    kwargs["analysis"].pipeline_execution_id = execution_id
    kwargs["expected_execution_id"] = execution_id

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "already_running", "analysis_id": "analysis-1"}
    kwargs["run_async_fn"].assert_not_called()


def test_provider_retry_cannot_adopt_a_different_active_execution_fence() -> None:
    kwargs = _build_kwargs(
        status=AnalysisStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    kwargs["analysis"].pipeline_execution_id = uuid.uuid4()
    kwargs["expected_execution_id"] = uuid.uuid4()
    kwargs["provider_retry_attempt"] = 1

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "already_running", "analysis_id": "analysis-1"}
    kwargs["run_async_fn"].assert_not_called()


def test_run_pipeline_execution_rolls_back_when_initial_lease_commit_fails():
    kwargs = _build_kwargs(status=AnalysisStatus.PENDING)
    kwargs["db"].commit.side_effect = RuntimeError("lease write failed")

    with (
        patch("api.workers.task_pipeline.active_analyses_gauge") as gauge,
        pytest.raises(RuntimeError, match="lease write failed"),
    ):
        run_pipeline_execution(**kwargs)

    kwargs["db"].rollback.assert_called_once()
    kwargs["run_async_fn"].assert_not_called()
    kwargs["pipeline_runner_factory"].assert_not_called()
    gauge.inc.assert_not_called()
    gauge.dec.assert_not_called()


def test_run_pipeline_execution_adopts_matching_persisted_job_fence() -> None:
    execution_id = uuid.uuid4()
    observed: dict[str, object] = {}

    def fake_run_async(_pipeline):
        observed["execution_id"] = kwargs["analysis"].pipeline_execution_id
        return {"report_id": "test-report-id", "compound": {}}

    kwargs = _build_kwargs(
        status=AnalysisStatus.PENDING,
        run_async_fn=MagicMock(side_effect=fake_run_async),
    )
    kwargs["analysis"].pipeline_execution_id = execution_id
    kwargs["expected_execution_id"] = execution_id

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "completed", "analysis_id": "analysis-1"}
    assert observed["execution_id"] == execution_id


def test_run_pipeline_execution_rejects_stale_job_fence() -> None:
    current_execution_id = uuid.uuid4()
    stale_execution_id = uuid.uuid4()
    kwargs = _build_kwargs(status=AnalysisStatus.PENDING)
    kwargs["analysis"].pipeline_execution_id = current_execution_id
    kwargs["expected_execution_id"] = stale_execution_id

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "stale_execution", "analysis_id": "analysis-1"}
    kwargs["db"].rollback.assert_called_once()
    kwargs["run_async_fn"].assert_not_called()


def test_run_pipeline_execution_without_job_fence_cannot_steal_reservation() -> None:
    kwargs = _build_kwargs(status=AnalysisStatus.PENDING)
    kwargs["analysis"].pipeline_execution_id = uuid.uuid4()

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "launch_reserved", "analysis_id": "analysis-1"}
    kwargs["db"].rollback.assert_called_once()
    kwargs["run_async_fn"].assert_not_called()


def test_run_pipeline_execution_reclaims_expired_running_lease():
    observed: dict[str, object] = {}

    def fake_run_async(_pipeline):
        analysis = kwargs["analysis"]
        observed["status"] = analysis.status
        observed["execution_id"] = analysis.pipeline_execution_id
        observed["lease_expires_at"] = analysis.pipeline_lease_expires_at
        return {"report_id": "test-report-id", "compound": {}}

    kwargs = _build_kwargs(
        status=AnalysisStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        run_async_fn=MagicMock(side_effect=fake_run_async),
    )

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "completed", "analysis_id": "analysis-1"}
    assert observed["status"] == AnalysisStatus.RUNNING
    assert observed["execution_id"] is not None
    assert observed["lease_expires_at"] is not None
    assert kwargs["analysis"].status == AnalysisStatus.COMPLETED
    assert kwargs["analysis"].completed_at is not None
    assert kwargs["analysis"].completed_at.tzinfo is not None
    assert kwargs["analysis"].pipeline_execution_id is None
    assert kwargs["analysis"].pipeline_lease_expires_at is None
    assert kwargs["db"].commit.call_count == 2
    kwargs["db"].rollback.assert_not_called()
    kwargs["store_pipeline_results_fn"].assert_called_once()
    kwargs["upsert_compound_fn"].assert_called_once_with(
        kwargs["db"],
        {},
        org_id="org-1",
        completed_at=kwargs["analysis"].completed_at,
    )


def test_zombie_worker_discards_progress_after_execution_fence_rotates() -> None:
    successor_execution_id = uuid.uuid4()

    def runner_factory(on_progress, _should_cancel):
        kwargs["analysis"].pipeline_execution_id = successor_execution_id
        on_progress(
            4,
            "claim_analysis",
            "completed",
            {"patents_analyzed": 1},
        )
        return {"report_id": "must-not-persist", "compound": {}}

    kwargs = _build_kwargs(
        status=AnalysisStatus.PENDING,
        run_async_fn=MagicMock(side_effect=lambda pipeline: pipeline),
        pipeline_runner_factory=runner_factory,
    )

    with (
        patch("api.workers.task_pipeline.active_analyses_gauge") as gauge,
        patch("api.workers.task_pipeline.record_pipeline_run") as record_run,
        pytest.raises(PipelineCancelledError, match="execution_fence_lost"),
    ):
        run_pipeline_execution(**kwargs)

    assert kwargs["analysis"].pipeline_execution_id == successor_execution_id
    kwargs["db"].add.assert_not_called()
    kwargs["store_pipeline_results_fn"].assert_not_called()
    kwargs["upsert_compound_fn"].assert_not_called()
    gauge.inc.assert_called_once()
    gauge.dec.assert_called_once()
    record_run.assert_called_once()
    assert record_run.call_args.kwargs["status"] == "failed"
    assert record_run.call_args.kwargs["execution_profile"] == "world_class_adaptive"


def test_run_pipeline_execution_flushes_checkpoint_events_immediately():
    def runner_factory(on_progress, _should_cancel):
        on_progress(
            4,
            "analysis_review",
            "checkpoint",
            {
                "checkpoint_id": "run-1:analysis_review",
                "checkpoint_type": "analysis_review",
                "requires_response": True,
            },
        )
        return {"report_id": "test-report-id", "compound": {}}

    kwargs = _build_kwargs(
        status=AnalysisStatus.PENDING,
        run_async_fn=MagicMock(side_effect=lambda result: result),
        pipeline_runner_factory=runner_factory,
    )

    result = run_pipeline_execution(**kwargs)

    assert result == {"status": "completed", "analysis_id": "analysis-1"}
    assert kwargs["db"].add.call_count == 1
    event = kwargs["db"].add.call_args.args[0]
    assert event.event_type == "checkpoint"
    assert event.payload["checkpoint_id"] == "run-1:analysis_review"
    assert kwargs["db"].commit.call_count == 3


def test_worker_binds_clear_report_to_exact_analysis_and_org_before_storage() -> None:
    report = {
        "report_id": "report-1",
        "compound": {},
        "clearance_decision": {"decision": "clear"},
        "certification_scope": {
            "evidence_verified": True,
            "evidence_receipt_id": "receipt-1",
            "evidence_receipt_sha256": "a" * 64,
            "evidence_pipeline_git_sha": "b" * 40,
            "verified_lane_ids": ["us-small-molecule-compound-adaptive-v1"],
        },
    }
    kwargs = _build_kwargs(
        status=AnalysisStatus.PENDING,
        run_async_fn=MagicMock(return_value=report),
    )

    with patch(
        "api.config.get_settings",
        return_value=SimpleNamespace(
            report_certification_signing_keyring_secret=SecretStr(
                TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
            )
        ),
    ):
        result = run_pipeline_execution(**kwargs)

    assert result == {"status": "completed", "analysis_id": "analysis-1"}
    stored_report = kwargs["store_pipeline_results_fn"].call_args.args[1]
    failures = verify_report_certification_binding(
        stored_report,
        keyring=ReportCertificationVerificationKeyRing.from_json(
            TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING
        ),
        expected_analysis_id="analysis-1",
        expected_org_id="org-1",
    )
    assert failures == []
