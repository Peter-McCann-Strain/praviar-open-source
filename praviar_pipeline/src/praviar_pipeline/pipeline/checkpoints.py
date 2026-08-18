"""HITL checkpoint infrastructure — pause pipeline for human review."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType, HITLConfig

if TYPE_CHECKING:
    from praviar_pipeline.run import ProgressCallback

logger = structlog.get_logger()

CheckpointDecisionProvider = Callable[
    [CheckpointType, dict[str, Any]],
    CheckpointDecision | Awaitable[CheckpointDecision | None] | None,
]


async def await_checkpoint(
    checkpoint_type: CheckpointType,
    context: dict[str, Any],
    on_progress: ProgressCallback,
    hitl_config: HITLConfig,
    decision_provider: CheckpointDecisionProvider | None = None,
    *,
    poll_interval_seconds: float = 5.0,
) -> CheckpointDecision | None:
    """Emit a checkpoint event and optionally wait for a human decision.

    Checkpoints work via the existing SSE progress callback:
    1. Emit a 'checkpoint' event with the checkpoint type and review context
    2. For async checkpoints (CP1): return None immediately, pipeline continues
    3. For blocking checkpoints (CP2.5, CP3): wait for decision via callback
    4. If no decision handler is connected before timeout: fail closed into
       review_required

    Args:
        checkpoint_type: Which checkpoint this is.
        context: Data to show the reviewer (patent list, analyses, etc.).
        on_progress: Pipeline progress callback for SSE events.
        hitl_config: HITL configuration (timeouts, which CPs are active).

    Returns:
        CheckpointDecision if a decision was received, None if skipped/async.
    """
    if not hitl_config.enabled:
        return None

    if checkpoint_type not in hitl_config.checkpoints:
        logger.debug(
            "checkpoint_not_active",
            checkpoint_type=checkpoint_type.value,
        )
        return None

    checkpoint_id = _checkpoint_id(checkpoint_type, context)
    checkpoint_context = {**context, "checkpoint_id": checkpoint_id}

    # Emit checkpoint event via progress callback
    if on_progress:
        on_progress(
            0,  # step_num not applicable for checkpoints
            checkpoint_type.value,
            "checkpoint",
            {
                "checkpoint_id": checkpoint_id,
                "checkpoint_type": checkpoint_type.value,
                "context": _serialize_context(checkpoint_context),
                "requires_response": _is_blocking(checkpoint_type),
                "timeout_minutes": hitl_config.auto_skip_timeout_minutes,
            },
        )

    logger.info(
        "checkpoint_emitted",
        checkpoint_type=checkpoint_type.value,
        blocking=_is_blocking(checkpoint_type),
        timeout_minutes=hitl_config.auto_skip_timeout_minutes,
    )

    # Non-blocking checkpoints: return immediately
    if not _is_blocking(checkpoint_type):
        return None

    # Blocking checkpoints: wait for a connected decision provider. In API-run
    # deployments this provider reads persisted reviewer decisions. If no
    # provider is connected, fail closed rather than silently approving a
    # reviewer-critical checkpoint.
    timeout_seconds = hitl_config.auto_skip_timeout_minutes * 60
    start = time.monotonic()

    logger.info(
        "checkpoint_waiting",
        checkpoint_type=checkpoint_type.value,
        timeout_seconds=timeout_seconds,
    )

    if decision_provider is not None:
        while (time.monotonic() - start) < timeout_seconds:
            candidate = decision_provider(checkpoint_type, checkpoint_context)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if candidate is not None:
                logger.info(
                    "checkpoint_decision_received",
                    checkpoint_type=checkpoint_type.value,
                    action=candidate.action,
                    elapsed_seconds=round(time.monotonic() - start, 2),
                )
                return candidate
            await asyncio.sleep(max(poll_interval_seconds, 0.0))

    elapsed_seconds = round(time.monotonic() - start, 2)
    if on_progress:
        on_progress(
            0,
            checkpoint_type.value,
            "review_required",
            {
                "checkpoint_id": checkpoint_id,
                "checkpoint_type": checkpoint_type.value,
                "requires_response": True,
                "timeout_minutes": hitl_config.auto_skip_timeout_minutes,
                "elapsed_seconds": elapsed_seconds,
            },
        )

    decision = CheckpointDecision(
        checkpoint_type=checkpoint_type,
        action="review_required",
        notes="Blocking checkpoint requires a persisted human decision before proceeding.",
    )

    logger.info(
        "checkpoint_review_required",
        checkpoint_type=checkpoint_type.value,
        elapsed_seconds=elapsed_seconds,
    )

    return decision


def _is_blocking(checkpoint_type: CheckpointType) -> bool:
    """Determine if a checkpoint blocks the pipeline."""
    blocking_types = {
        CheckpointType.IDENTITY_REVIEW,
        CheckpointType.ANALYSIS_REVIEW,
        CheckpointType.REPORT_REVIEW,
    }
    return checkpoint_type in blocking_types


def _checkpoint_id(checkpoint_type: CheckpointType, context: dict[str, Any]) -> str:
    """Return a stable checkpoint id for persistence and reviewer actions."""
    explicit = context.get("checkpoint_id")
    if explicit is not None and str(explicit).strip():
        return _safe_checkpoint_id(str(explicit))

    for key in ("run_id", "analysis_id", "pipeline_execution_id", "manifest_id"):
        value = context.get(key)
        if value is not None and str(value).strip():
            return _safe_checkpoint_id(f"{value}:{checkpoint_type.value}")

    return checkpoint_type.value


def _safe_checkpoint_id(value: str) -> str:
    cleaned = value.strip().replace("/", "_").replace("\\", "_")
    return cleaned[:128] or "checkpoint"


def _serialize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Serialize checkpoint context for SSE transmission.

    Truncates large fields to keep the SSE payload manageable.
    """
    serialized: dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, list) and len(value) > 20:
            serialized[key] = value[:20]
            serialized[f"{key}_total"] = len(value)
        elif isinstance(value, str) and len(value) > 5000:
            serialized[key] = value[:5000] + "... [truncated]"
        else:
            serialized[key] = value
    return serialized
