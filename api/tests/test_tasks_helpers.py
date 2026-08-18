"""Tests for extracted helper functions in workers/task_state.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import redis

from api.db.models import AnalysisStatus
from api.workers.task_runtime import build_pipeline_runtime
from api.workers.task_state import (
    classify_pipeline_execution_status,
    is_cancelled,
    is_pipeline_terminal,
    persist_pipeline_cancellation,
    persist_pipeline_failure,
    publish_pipeline_event,
    store_pipeline_results,
)


class TestPublishPipelineEvent:
    def test_records_lost_events_when_redis_is_unavailable(self):
        redis_client = MagicMock()
        redis_client.publish.side_effect = redis.RedisError("boom")
        logger = MagicMock()
        lost_event_counts: dict[str, int] = {}

        publish_pipeline_event(
            redis_client,
            "analysis-1",
            2,
            "search",
            "started",
            {"query": "aspirin"},
            lost_event_counts=lost_event_counts,
            logger=logger,
        )

        assert lost_event_counts["analysis-1"] == 1
        logger.error.assert_called_once()


def test_build_pipeline_runtime_passes_bounded_redis_connection_kwargs():
    settings = SimpleNamespace(
        redis_url="redis://worker.example:6379/0",
        redis_socket_connect_timeout_seconds=1.0,
        redis_socket_timeout_seconds=2.0,
        redis_health_check_interval_seconds=15,
    )
    redis_client = MagicMock()
    redis_from_url = MagicMock(return_value=redis_client)
    engine = MagicMock()

    runtime = build_pipeline_runtime(
        get_settings_fn=lambda: settings,
        redis_from_url=redis_from_url,
        get_sync_engine_fn=lambda: engine,
    )

    assert runtime.redis_client is redis_client
    assert runtime.engine is engine
    redis_from_url.assert_called_once_with(
        "redis://worker.example:6379/0",
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
        health_check_interval=15,
    )


class TestStateHelpers:
    def test_is_cancelled_matches_terminal_states(self):
        assert is_cancelled(AnalysisStatus.CANCELLED) is True
        assert is_cancelled(AnalysisStatus.DELETED) is True
        assert is_cancelled(AnalysisStatus.RUNNING) is False

    def test_is_pipeline_terminal_includes_completed(self):
        assert is_pipeline_terminal(AnalysisStatus.COMPLETED) is True
        assert is_pipeline_terminal(AnalysisStatus.CANCELLED) is True
        assert is_pipeline_terminal(AnalysisStatus.DELETED) is True
        assert is_pipeline_terminal(AnalysisStatus.FAILED) is False

    def test_classify_pipeline_execution_status(self):
        now = datetime(2026, 5, 25, tzinfo=UTC)

        assert (
            classify_pipeline_execution_status(
                AnalysisStatus.COMPLETED,
                None,
                now=now,
            )
            == "already_completed"
        )
        assert (
            classify_pipeline_execution_status(
                AnalysisStatus.CANCELLED,
                None,
                now=now,
            )
            == "cancelled"
        )
        assert (
            classify_pipeline_execution_status(
                AnalysisStatus.DELETED,
                None,
                now=now,
            )
            == "deleted"
        )
        assert (
            classify_pipeline_execution_status(
                AnalysisStatus.RUNNING,
                now + timedelta(minutes=5),
                now=now,
            )
            == "already_running"
        )
        assert (
            classify_pipeline_execution_status(
                AnalysisStatus.RUNNING,
                now - timedelta(seconds=1),
                now=now,
            )
            is None
        )
        assert (
            classify_pipeline_execution_status(AnalysisStatus.FAILED, None, now=now)
            == "already_failed"
        )
        assert classify_pipeline_execution_status("pending", None, now=now) is None

    def test_classify_pipeline_execution_status_rejects_unsafe_values(self):
        now = datetime(2026, 5, 25, tzinfo=UTC)

        with pytest.raises(ValueError, match="Unsupported analysis status"):
            classify_pipeline_execution_status("surprise", None, now=now)

        with pytest.raises(ValueError, match="timezone-aware"):
            classify_pipeline_execution_status(
                AnalysisStatus.RUNNING,
                datetime(2026, 5, 25),
                now=now,
            )

    def test_persist_pipeline_cancellation_sets_final_state(self):
        db = MagicMock()
        db.commit = MagicMock()
        # pipeline_execution_id=None reflects the state after the inner handler
        # already cleared it (the normal cancellation path, not a zombie-worker
        # reclaim).
        analysis = MagicMock(status=AnalysisStatus.RUNNING, pipeline_execution_id=None)

        persist_pipeline_cancellation(db, analysis, 12.5)

        assert analysis.status == AnalysisStatus.CANCELLED
        assert analysis.pipeline_duration_seconds == 12.5
        assert analysis.pipeline_execution_id is None
        assert analysis.pipeline_lease_expires_at is None
        db.commit.assert_called_once()

    def test_persist_pipeline_cancellation_skips_zombie_reclaim(self):
        """Outer handler must not overwrite a new worker's RUNNING lease."""
        import uuid

        db = MagicMock()
        db.commit = MagicMock()
        analysis = MagicMock(
            status=AnalysisStatus.RUNNING,
            pipeline_execution_id=uuid.uuid4(),
        )

        persist_pipeline_cancellation(db, analysis, 12.5)

        assert analysis.status == AnalysisStatus.RUNNING
        db.commit.assert_not_called()

    def test_persist_pipeline_cancellation_preserves_deleted_state(self):
        db = MagicMock()
        analysis = MagicMock(status=AnalysisStatus.DELETED)

        persist_pipeline_cancellation(db, analysis, 12.5)

        assert analysis.status == AnalysisStatus.DELETED
        assert analysis.pipeline_execution_id is None
        assert analysis.pipeline_lease_expires_at is None
        db.commit.assert_called_once()

    def test_persist_pipeline_failure_sets_error_message(self):
        db = MagicMock()
        db.commit = MagicMock()
        analysis = MagicMock(status=AnalysisStatus.RUNNING, pipeline_execution_id=None)
        traceback_text = "Traceback (most recent call last):\n  File '/srv/api/secret.py'\n"
        exc = RuntimeError("unsupported customer-visible claim assertions detected")

        persist_pipeline_failure(db, analysis, 42.0, traceback_text, exc=exc)

        assert analysis.status == AnalysisStatus.FAILED
        assert analysis.pipeline_duration_seconds == 42.0
        assert analysis.error_message == (
            "Pipeline failed: RuntimeError. See worker logs for scrubbed diagnostics."
        )
        assert "unsupported customer-visible claim" not in analysis.error_message
        assert "Traceback" not in analysis.error_message
        assert "/srv/api/secret.py" not in analysis.error_message
        assert analysis.pipeline_execution_id is None
        assert analysis.pipeline_lease_expires_at is None
        db.commit.assert_called_once()

    def test_persist_pipeline_failure_skips_zombie_reclaim(self):
        """Outer handler must not overwrite a new worker's RUNNING lease."""
        import uuid

        db = MagicMock()
        db.commit = MagicMock()
        analysis = MagicMock(
            status=AnalysisStatus.RUNNING,
            pipeline_execution_id=uuid.uuid4(),
        )

        persist_pipeline_failure(db, analysis, 42.0, "", exc=None)

        assert analysis.status == AnalysisStatus.RUNNING
        db.commit.assert_not_called()

    def test_persist_pipeline_failure_fallback_message_is_bounded(self):
        db = MagicMock()
        db.commit = MagicMock()
        analysis = MagicMock(status=AnalysisStatus.RUNNING, pipeline_execution_id=None)
        traceback_text = "boom\n" * 1000

        persist_pipeline_failure(db, analysis, 42.0, traceback_text)

        assert analysis.error_message == "Pipeline failed. See worker logs for traceback."
        assert len(analysis.error_message) <= 2000

    def test_store_pipeline_results_sets_summary_fields(self):
        analysis = MagicMock()
        report = {
            "risk_summary": {
                "overall_risk": "high",
                "blocking_patents_count": 3,
                "executive_summary": "Risk found.",
            },
            "total_patents_found": 100,
            "total_input_tokens": 5000,
            "total_output_tokens": 2000,
            "estimated_cost_usd": 1.50,
            "compound": {
                "name": "aspirin",
                "canonical_smiles": "CC(=O)Oc1ccccc1C(O)=O",
                "pubchem_cid": 2244,
            },
        }

        store_pipeline_results(analysis, report, 120.5)

        assert analysis.report_data == report
        assert analysis.progress_pct == 100.0
        assert analysis.current_step == 8
        assert analysis.pipeline_duration_seconds == 120.5
        assert analysis.overall_risk == "high"
        assert analysis.blocking_patents_count == 3
        assert analysis.total_patents_found == 100
        assert analysis.executive_summary == "Risk found."
        assert analysis.total_input_tokens == 5000
        assert analysis.total_output_tokens == 2000
        assert analysis.estimated_cost_usd == 1.50
        assert analysis.compound_name == "aspirin"
        assert analysis.compound_smiles == "CC(=O)Oc1ccccc1C(O)=O"
        assert analysis.compound_cid == 2244

    def test_store_pipeline_results_invalidates_grant_state_when_report_replaced(self):
        analysis = MagicMock()
        analysis.report_data = {"report_id": "old-report"}
        analysis.flagged_for_review = False
        analysis.share_active_grant_count = 2
        analysis.share_active_until = "soon"
        report = {
            "report_id": "new-report",
            "risk_summary": {},
            "compound": {},
        }

        store_pipeline_results(analysis, report, 1.0)

        assert analysis.flagged_for_review is True
        assert analysis.share_active_grant_count == 0
        assert analysis.share_active_until is None

    def test_store_pipeline_results_handles_missing_fields(self):
        analysis = MagicMock()
        store_pipeline_results(analysis, {}, 0.0)

        assert analysis.overall_risk == ""
        assert analysis.blocking_patents_count == 0
        assert analysis.compound_name == ""
        assert analysis.estimated_cost_usd == 0.0
