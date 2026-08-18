from __future__ import annotations

from unittest.mock import MagicMock, patch

from praviar_pipeline.logging_runtime import ProgressTracker, StepTimer


def test_step_timer_logs_start_and_complete() -> None:
    logger = MagicMock()
    with (
        patch("praviar_pipeline.logging_runtime.structlog.get_logger", return_value=logger),
        StepTimer("step_test", items=3),
    ):
        pass

    logger.info.assert_any_call("step_test_start", items=3)
    complete_call = logger.info.call_args_list[-1]
    assert complete_call.args[0] == "step_test_complete"
    assert "duration_s" in complete_call.kwargs


def test_step_timer_drops_unapproved_customer_fields() -> None:
    logger = MagicMock()
    with (
        patch("praviar_pipeline.logging_runtime.structlog.get_logger", return_value=logger),
        StepTimer("step_test", input="secret compound", patents_in=3),
    ):
        pass

    start_call = logger.info.call_args_list[0]
    assert "input" not in start_call.kwargs
    assert start_call.kwargs["patents_in"] == 3


def test_progress_tracker_logs_progress() -> None:
    logger = MagicMock()
    with patch("praviar_pipeline.logging_runtime.structlog.get_logger", return_value=logger):
        tracker = ProgressTracker(total=2, operation="analysis")
        tracker.mark_complete(success=True, patent_id="US123")

    call = logger.info.call_args
    assert call.args[0] == "analysis_progress"
    assert call.kwargs["done"] == 1
    assert call.kwargs["completed"] == 1
    assert call.kwargs["failed"] == 0
    assert "patent_id" not in call.kwargs
