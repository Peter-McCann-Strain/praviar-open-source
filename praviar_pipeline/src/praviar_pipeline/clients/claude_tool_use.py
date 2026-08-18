"""Tool-use helpers for the Claude client."""

from __future__ import annotations

import time
from typing import Any

from praviar_pipeline.manifest import get_tool_trace_recorder
from praviar_pipeline.sanitize import sanitize_untrusted_text


def build_tool_loop_kwargs(
    *,
    model: str,
    max_tokens: int,
    system: str | list,
    messages: list[dict[str, Any]],
    tool_definitions: list[dict[str, Any]],
    thinking: dict[str, Any] | None,
    temperature: float | None,
) -> dict[str, Any]:
    """Build Anthropic streaming kwargs for a tool-use round."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "tools": tool_definitions,
    }
    if thinking:
        kwargs["thinking"] = thinking
    elif temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


def serialize_content_blocks(content: list[Any]) -> list[dict[str, Any]]:
    """Serialize Anthropic content blocks for history replay in tool loops."""
    serialized_content: list[dict[str, Any]] = []
    for block in content:
        if block.type == "thinking":
            serialized_content.append(
                {
                    "type": "thinking",
                    "thinking": block.thinking,
                    "signature": getattr(block, "signature", ""),
                }
            )
        elif block.type == "text":
            serialized_content.append(
                {
                    "type": "text",
                    "text": block.text,
                }
            )
        elif block.type == "tool_use":
            serialized_content.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return serialized_content


async def execute_tool_blocks(
    *,
    tool_blocks: list[Any],
    toolkit: Any,
    logger: Any,
) -> list[dict[str, Any]]:
    """Execute Claude tool-use blocks and return Anthropic tool results."""
    tool_results = []
    for block in tool_blocks:
        tool_t0 = time.monotonic()
        get_tool_trace_recorder().record_call(block.name, block.input)
        raw_result = await toolkit.execute(block.name, block.input)
        result = sanitize_untrusted_text(
            raw_result,
            data_type=f"tool_result_{block.name}",
        )
        tool_dur = time.monotonic() - tool_t0
        tool_results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            }
        )
        logger.debug(
            "tool_executed",
            tool_name=block.name,
            tool_input_keys=(list(block.input.keys()) if isinstance(block.input, dict) else None),
            duration_s=round(tool_dur, 2),
            result_length=len(result) if isinstance(result, str) else None,
        )
    return tool_results
