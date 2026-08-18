"""Tests for HITL checkpoint infrastructure."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType, HITLConfig
from praviar_pipeline.pipeline.checkpoints import (
    _checkpoint_id,
    _is_blocking,
    _serialize_context,
    await_checkpoint,
)


class TestCheckpointModels:
    def test_checkpoint_type_values(self):
        assert CheckpointType.IDENTITY_REVIEW == "identity_review"
        assert CheckpointType.SEARCH_REVIEW == "search_review"
        assert CheckpointType.REPORT_REVIEW == "report_review"

    def test_hitl_config_defaults(self):
        config = HITLConfig()
        assert config.enabled is False
        assert config.checkpoints == []
        assert config.auto_skip_timeout_minutes == 60

    def test_checkpoint_decision(self):
        decision = CheckpointDecision(
            checkpoint_type=CheckpointType.SEARCH_REVIEW,
            action="approve",
        )
        assert decision.action == "approve"
        assert decision.modifications == {}


class TestCheckpointHelpers:
    def test_blocking_types(self):
        assert _is_blocking(CheckpointType.IDENTITY_REVIEW) is True
        assert _is_blocking(CheckpointType.ANALYSIS_REVIEW) is True
        assert _is_blocking(CheckpointType.REPORT_REVIEW) is True
        assert _is_blocking(CheckpointType.SEARCH_REVIEW) is False
        assert _is_blocking(CheckpointType.TRIAGE_REVIEW) is False

    def test_serialize_truncates_long_lists(self):
        context = {"patents": list(range(50)), "text": "short"}
        serialized = _serialize_context(context)
        assert len(serialized["patents"]) == 20
        assert serialized["patents_total"] == 50
        assert serialized["text"] == "short"

    def test_serialize_truncates_long_strings(self):
        context = {"summary": "x" * 10000}
        serialized = _serialize_context(context)
        assert len(serialized["summary"]) < 6000
        assert "truncated" in serialized["summary"]

    def test_checkpoint_id_prefers_explicit_context_value(self):
        assert (
            _checkpoint_id(
                CheckpointType.REPORT_REVIEW,
                {"checkpoint_id": "run-1:report_review"},
            )
            == "run-1:report_review"
        )

    def test_checkpoint_id_derives_from_analysis_id_when_missing(self):
        assert (
            _checkpoint_id(
                CheckpointType.ANALYSIS_REVIEW,
                {"analysis_id": "analysis-123"},
            )
            == "analysis-123:analysis_review"
        )


class TestAwaitCheckpoint:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        config = HITLConfig(enabled=False)
        result = await await_checkpoint(
            CheckpointType.SEARCH_REVIEW,
            {},
            None,
            config,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_checkpoint_returns_none(self):
        config = HITLConfig(enabled=True, checkpoints=[CheckpointType.REPORT_REVIEW])
        result = await await_checkpoint(
            CheckpointType.SEARCH_REVIEW,
            {},
            None,
            config,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_non_blocking_returns_none(self):
        callback = MagicMock()
        config = HITLConfig(
            enabled=True,
            checkpoints=[CheckpointType.SEARCH_REVIEW],
        )
        result = await await_checkpoint(
            CheckpointType.SEARCH_REVIEW,
            {"analysis_id": "analysis-1", "patents": []},
            callback,
            config,
        )
        assert result is None
        callback.assert_called_once()
        payload = callback.call_args.args[3]
        assert payload["checkpoint_id"] == "analysis-1:search_review"
        assert payload["context"]["checkpoint_id"] == "analysis-1:search_review"

    @pytest.mark.asyncio
    async def test_blocking_requires_review_when_no_decision_handler_connected(self):
        callback = MagicMock()
        config = HITLConfig(
            enabled=True,
            checkpoints=[CheckpointType.REPORT_REVIEW],
        )
        result = await await_checkpoint(
            CheckpointType.REPORT_REVIEW,
            {},
            callback,
            config,
        )
        assert result is not None
        assert result.action == "review_required"
        assert "persisted human decision" in result.notes
        assert callback.call_count == 2
        assert callback.call_args.args[2] == "review_required"
        assert callback.call_args.args[3]["checkpoint_id"] == "report_review"

    @pytest.mark.asyncio
    async def test_blocking_returns_decision_from_connected_provider(self):
        callback = MagicMock()
        config = HITLConfig(
            enabled=True,
            checkpoints=[CheckpointType.REPORT_REVIEW],
            auto_skip_timeout_minutes=1,
        )
        expected = CheckpointDecision(
            checkpoint_type=CheckpointType.REPORT_REVIEW,
            action="approve",
            reviewer_id="reviewer-1",
            notes="Approved in persisted checkpoint store.",
        )

        async def provider(checkpoint_type, context):
            assert checkpoint_type == CheckpointType.REPORT_REVIEW
            assert context["checkpoint_id"] == "run-1:report_review"
            return expected

        result = await await_checkpoint(
            CheckpointType.REPORT_REVIEW,
            {"checkpoint_id": "run-1:report_review"},
            callback,
            config,
            decision_provider=provider,
        )

        assert result is expected
        assert callback.call_count == 1
