"""Result accounting helpers for Claude runtime calls."""

from __future__ import annotations

from praviar_pipeline.clients.claude_responses import cache_token_counts, usage_payload
from praviar_pipeline.cost_tracker import get_current_tracker
from praviar_pipeline.logging_config import log_llm_call


def log_and_build_usage(
    *,
    purpose: str,
    response,
    model: str,
    total_input: int,
    total_output: int,
    duration_s: float,
    tool_calls: int | None = None,
    log_fn=None,
    role: str = "unknown",
) -> tuple[dict, int, int]:
    """Log a Claude completion and build its usage payload.

    When a :class:`~praviar_pipeline.cost_tracker.CostTracker` is installed on the
    current run (via ``set_current_tracker``), also record the call against
    ``role`` so the run's cost breakdown stamps the manifest at finalize time.
    """
    if log_fn is None:
        log_fn = log_llm_call
    cache_read, cache_creation = cache_token_counts(response)
    log_kwargs = {
        "purpose": purpose,
        "model": model,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "duration_s": duration_s,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "stop_reason": response.stop_reason or "",
    }
    if tool_calls is not None:
        log_kwargs["tool_calls"] = tool_calls
    log_fn(**log_kwargs)
    usage = usage_payload(
        response=response,
        total_input=total_input,
        total_output=total_output,
        model=model,
    )
    tracker = get_current_tracker()
    if tracker is not None:
        tracker.record(role=role, model=model, usage=usage)
    return usage, cache_read, cache_creation
