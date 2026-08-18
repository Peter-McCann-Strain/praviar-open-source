"""Hard-budget guards placed immediately around live Anthropic requests."""

from __future__ import annotations

import json
from typing import Any

from praviar_pipeline.clients.claude_responses import usage_payload
from praviar_pipeline.cost_tracker import (
    PaidCallReservation,
    forfeit_current_paid_call,
    reserve_current_paid_call,
    settle_current_paid_call,
)


def _serialize_prompt_component(value: Any) -> Any:
    model_json_schema = getattr(value, "model_json_schema", None)
    if callable(model_json_schema):
        return model_json_schema()
    return str(value)


def estimate_prompt_tokens(*components: Any) -> int:
    """Return a fail-closed upper-bound estimate for request input tokens."""
    serialized = json.dumps(
        components,
        ensure_ascii=False,
        sort_keys=True,
        default=_serialize_prompt_component,
        separators=(",", ":"),
    )
    # Reserve one token per UTF-8 byte plus an envelope allowance. Normal
    # tokenization is materially smaller, but a hard pre-dispatch budget must
    # remain safe for byte-fallback tokens, structured-output schemas, and
    # provider-added message framing.
    return max(1, len(serialized.encode("utf-8")) + 4096)


def reserve_claude_call(
    *,
    model: str,
    max_output_tokens: int,
    prompt_components: tuple[Any, ...],
) -> PaidCallReservation | None:
    return reserve_current_paid_call(
        model=model,
        max_output_tokens=max_output_tokens,
        estimated_input_tokens=estimate_prompt_tokens(*prompt_components),
    )


def settle_claude_call(
    reservation: PaidCallReservation | None,
    *,
    response: Any,
    model: str,
    total_input: int | None = None,
    total_output: int | None = None,
) -> None:
    settle_current_paid_call(
        reservation,
        model=model,
        usage=usage_payload(
            response=response,
            total_input=(
                int(total_input) if total_input is not None else int(response.usage.input_tokens)
            ),
            total_output=(
                int(total_output) if total_output is not None else int(response.usage.output_tokens)
            ),
            model=model,
        ),
    )


def forfeit_claude_call(reservation: PaidCallReservation | None) -> None:
    forfeit_current_paid_call(reservation)
