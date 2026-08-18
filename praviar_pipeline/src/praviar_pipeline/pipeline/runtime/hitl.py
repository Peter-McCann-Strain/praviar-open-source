"""Runtime helpers for human-in-the-loop checkpoint enforcement."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType, HITLConfig
from praviar_pipeline.pipeline.checkpoints import (
    CheckpointDecisionProvider,
    await_checkpoint,
)

ProgressCallback = Callable[[int, str, str, dict], None] | None


def build_hitl_config(settings: Any) -> HITLConfig:
    """Build strict HITL config from runtime settings."""
    checkpoints: list[CheckpointType] = []
    for raw_value in getattr(settings, "hitl_checkpoints", []) or []:
        try:
            checkpoints.append(CheckpointType(str(raw_value)))
        except ValueError as exc:
            raise ValueError(f"Unknown HITL checkpoint: {raw_value}") from exc

    return HITLConfig(
        enabled=bool(getattr(settings, "hitl_enabled", False)),
        checkpoints=checkpoints,
        auto_skip_timeout_minutes=int(getattr(settings, "hitl_auto_skip_minutes", 60)),
    )


async def await_runtime_checkpoint(
    *,
    checkpoint_type: CheckpointType,
    context: dict[str, Any],
    settings: Any,
    on_progress: ProgressCallback,
    decision_provider: CheckpointDecisionProvider | None,
    poll_interval_seconds: float = 5.0,
) -> CheckpointDecision | None:
    """Emit/wait for a configured checkpoint and enforce fail-closed decisions."""
    hitl_config = build_hitl_config(settings)
    if checkpoint_type == CheckpointType.IDENTITY_REVIEW and bool(
        getattr(settings, "identity_review_required", False)
    ):
        hitl_config = hitl_config.model_copy(
            update={
                "enabled": True,
                "checkpoints": list(
                    dict.fromkeys(
                        [
                            *hitl_config.checkpoints,
                            CheckpointType.IDENTITY_REVIEW,
                        ]
                    )
                ),
            }
        )
    decision = await await_checkpoint(
        checkpoint_type,
        context,
        on_progress,
        hitl_config,
        decision_provider=decision_provider,
        poll_interval_seconds=poll_interval_seconds,
    )
    enforce_checkpoint_decision(decision)
    return decision


def enforce_checkpoint_decision(decision: CheckpointDecision | None) -> None:
    """Continue only for absent async checkpoints or explicit approval."""
    if decision is None or decision.action == "approve":
        return
    if decision.action == "review_required":
        raise RuntimeError("Blocking checkpoint requires persisted human review before continuing.")
    if decision.action == "reject":
        raise RuntimeError("Blocking checkpoint was rejected by a reviewer.")
    raise RuntimeError(f"Unsupported checkpoint decision action: {decision.action}")
