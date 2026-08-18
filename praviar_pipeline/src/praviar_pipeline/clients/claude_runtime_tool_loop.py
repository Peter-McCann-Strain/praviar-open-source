"""Claude tool-loop execution helpers."""

from __future__ import annotations

import time
from typing import Any

from praviar_pipeline.clients.claude_budget import (
    forfeit_claude_call,
    reserve_claude_call,
    settle_claude_call,
)
from praviar_pipeline.clients.claude_responses import (
    round_thinking_blocks,
    tool_use_blocks,
    usage_payload,
)
from praviar_pipeline.clients.claude_tool_use import (
    build_tool_loop_kwargs,
    execute_tool_blocks,
    serialize_content_blocks,
)
from praviar_pipeline.cost_tracker import get_current_tracker
from praviar_pipeline.manifest import get_tool_trace_recorder


def _maybe_record_tool_loop_cost(
    *,
    role: str | None,
    response: Any,
    model: str,
    total_input: int,
    total_output: int,
) -> None:
    """Record tool-loop totals against the active tracker when ``role`` is set.

    No-op when ``role`` is ``None`` (the wrapper-driven path through
    ``complete_text_impl``/``complete_with_thinking_impl``, which already
    reports via ``log_and_build_usage`` and would double-count otherwise).
    """
    if role is None or response is None:
        return
    tracker = get_current_tracker()
    if tracker is None:
        return
    tracker.record(
        role=role,
        model=model,
        usage=usage_payload(
            response=response,
            total_input=total_input,
            total_output=total_output,
            model=model,
        ),
    )


async def tool_use_loop_impl(
    *,
    client,
    max_rounds: int,
    model: str,
    max_tokens: int,
    system: str | list,
    messages: list[dict],
    toolkit: Any,
    logger,
    thinking: dict | None = None,
    temperature: float | None = 0.0,
    role: str | None = None,
) -> tuple[Any, int, int, str]:
    """Execute the Claude tool loop until a final response is produced.

    ``temperature`` defaults to ``0.0`` so every analysis/verification round
    is deterministic by default. Callers can pass an explicit value when
    sampling diversity is required (e.g. GEPA prompt evolution).

    ``role`` opts the tool-loop into per-run cost tracking. When set AND a
    :class:`~praviar_pipeline.cost_tracker.CostTracker` is installed, the loop's
    final accumulated token totals are recorded against ``role``. Callers
    that wrap the loop in their own ``log_and_build_usage`` (e.g.
    ``complete_text_impl``) MUST leave ``role`` unset to avoid double-counting;
    callers that drive the loop directly (e.g. research agents in
    ``agents/base_runtime.py``) pass ``role="agent"`` so their tokens are
    attributed instead of silently dropped.
    """
    total_input = 0
    total_output = 0
    all_thinking: list[str] = []
    response = None
    get_tool_trace_recorder().record_tool_definitions(toolkit.tool_definitions)

    for round_num in range(max_rounds):
        kwargs = build_tool_loop_kwargs(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tool_definitions=toolkit.tool_definitions,
            thinking=thinking,
            temperature=temperature,
        )

        round_t0 = time.monotonic()
        reservation = reserve_claude_call(
            model=model,
            max_output_tokens=max_tokens,
            prompt_components=(system, messages, toolkit.tool_definitions),
        )
        try:
            async with client.messages.stream(**kwargs) as stream:
                response = await stream.get_final_message()
        except BaseException:
            forfeit_claude_call(reservation)
            raise
        settle_claude_call(reservation, response=response, model=model)
        round_duration = time.monotonic() - round_t0

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        all_thinking.extend(round_thinking_blocks(response.content))

        tool_blocks = tool_use_blocks(response.content)
        if not tool_blocks or response.stop_reason != "tool_use":
            logger.debug(
                "tool_loop_final_round",
                round=round_num + 1,
                duration_s=round(round_duration, 2),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                stop_reason=response.stop_reason,
            )
            _maybe_record_tool_loop_cost(
                role=role,
                response=response,
                model=model,
                total_input=total_input,
                total_output=total_output,
            )
            return response, total_input, total_output, "\n\n".join(all_thinking)

        messages.append(
            {
                "role": "assistant",
                "content": serialize_content_blocks(response.content),
            }
        )

        tool_results = await execute_tool_blocks(
            tool_blocks=tool_blocks,
            toolkit=toolkit,
            logger=logger,
        )
        messages.append({"role": "user", "content": tool_results})

        logger.info(
            "tool_use_round",
            model=model,
            round=round_num + 1,
            round_duration_s=round(round_duration, 2),
            tools_called=[b.name for b in tool_blocks],
            round_input_tokens=response.usage.input_tokens,
            round_output_tokens=response.usage.output_tokens,
        )

    logger.warning("tool_use_max_rounds_reached", max_rounds=max_rounds)
    _maybe_record_tool_loop_cost(
        role=role,
        response=response,
        model=model,
        total_input=total_input,
        total_output=total_output,
    )
    return response, total_input, total_output, "\n\n".join(all_thinking)
