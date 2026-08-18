from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType
from praviar_pipeline.pipeline.runtime.hitl import (
    await_runtime_checkpoint,
    build_hitl_config,
    enforce_checkpoint_decision,
)


def test_build_hitl_config_rejects_unknown_checkpoint() -> None:
    settings = SimpleNamespace(
        hitl_enabled=True,
        hitl_checkpoints=["analysis_review", "legacy_review"],
        hitl_auto_skip_minutes=5,
    )

    with pytest.raises(ValueError, match="Unknown HITL checkpoint: legacy_review"):
        build_hitl_config(settings)


def test_enforce_checkpoint_decision_only_allows_approval() -> None:
    enforce_checkpoint_decision(None)
    enforce_checkpoint_decision(
        CheckpointDecision(
            checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
            action="approve",
        )
    )

    with pytest.raises(RuntimeError, match="rejected"):
        enforce_checkpoint_decision(
            CheckpointDecision(
                checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
                action="reject",
            )
        )


@pytest.mark.asyncio
async def test_required_identity_review_overrides_disabled_optional_hitl() -> None:
    notify = MagicMock()
    settings = SimpleNamespace(
        hitl_enabled=False,
        hitl_checkpoints=[],
        hitl_auto_skip_minutes=1,
        identity_review_required=True,
    )

    async def provider(checkpoint_type, _context):
        assert checkpoint_type == CheckpointType.IDENTITY_REVIEW
        return CheckpointDecision(
            checkpoint_type=CheckpointType.IDENTITY_REVIEW,
            action="approve",
        )

    decision = await await_runtime_checkpoint(
        checkpoint_type=CheckpointType.IDENTITY_REVIEW,
        context={"run_id": "run-1"},
        settings=settings,
        on_progress=notify,
        decision_provider=provider,
        poll_interval_seconds=0,
    )

    assert decision is not None
    assert decision.action == "approve"
    assert notify.call_args.args[3]["requires_response"] is True


@pytest.mark.asyncio
async def test_await_runtime_checkpoint_polls_provider_and_continues_on_approval() -> None:
    notify = MagicMock()
    settings = SimpleNamespace(
        hitl_enabled=True,
        hitl_checkpoints=["analysis_review"],
        hitl_auto_skip_minutes=1,
    )

    async def provider(checkpoint_type, context):
        assert checkpoint_type == CheckpointType.ANALYSIS_REVIEW
        assert context["checkpoint_id"] == "run-1:analysis_review"
        return CheckpointDecision(
            checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
            action="approve",
        )

    decision = await await_runtime_checkpoint(
        checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
        context={"run_id": "run-1"},
        settings=settings,
        on_progress=notify,
        decision_provider=provider,
        poll_interval_seconds=0,
    )

    assert decision is not None
    assert decision.action == "approve"
    assert notify.call_args.args[2] == "checkpoint"
    assert notify.call_args.args[3]["checkpoint_id"] == "run-1:analysis_review"
