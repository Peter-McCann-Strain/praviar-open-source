"""Pure helper functions for research-agent prompt and context handling."""

from __future__ import annotations

import json
from typing import Any

MASKED_TOOL_OUTPUT_SENTINEL = "[Output analyzed — key findings in scratchpad]"


def build_scratchpad_section(scratchpad: dict[str, Any]) -> str:
    """Render the XML scratchpad block for prompt injection."""
    scratchpad_json = json.dumps(scratchpad, indent=2, default=str)
    return (
        "\n\n<scratchpad>\n"
        "Your running research notes (updated each round):\n"
        f"{scratchpad_json}\n"
        "</scratchpad>"
    )


def build_system_prompt(
    *,
    base_prompt: str,
    scratchpad: dict[str, Any],
    scratchpad_enabled: bool,
) -> str:
    """Build a plain system prompt with optional scratchpad state."""
    if not scratchpad or not scratchpad_enabled:
        return base_prompt
    return base_prompt + build_scratchpad_section(scratchpad)


def build_cached_system_content(
    *,
    base_prompt: str,
    scratchpad: dict[str, Any],
    scratchpad_enabled: bool,
) -> list[dict[str, Any]]:
    """Build Anthropic prompt-caching blocks with optional scratchpad content."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": base_prompt,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    if scratchpad and scratchpad_enabled:
        blocks.append({"type": "text", "text": build_scratchpad_section(scratchpad)})
    return blocks


def mask_old_tool_outputs(
    messages: list[dict],
    *,
    masking_enabled: bool,
    masked_sentinel: str = MASKED_TOOL_OUTPUT_SENTINEL,
) -> list[dict]:
    """Mask all but the most recent tool-result message."""
    if not masking_enabled:
        return messages

    tool_result_indices = []
    for index, message in enumerate(messages):
        if (
            message.get("role") == "user"
            and isinstance(message.get("content"), list)
            and any(
                isinstance(item, dict) and item.get("type") == "tool_result"
                for item in message["content"]
            )
        ):
            tool_result_indices.append(index)

    if len(tool_result_indices) <= 1:
        return messages

    for index in tool_result_indices[:-1]:
        message = messages[index]
        masked_content = []
        for item in message["content"]:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                masked_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": item["tool_use_id"],
                        "content": masked_sentinel,
                    }
                )
            else:
                masked_content.append(item)
        messages[index] = {**message, "content": masked_content}

    return messages


def estimate_context_size(messages: list[dict]) -> int:
    """Estimate total serialized context size in characters."""
    return len(json.dumps(messages, default=str))


def serialize_response_content(content_blocks: list[Any]) -> list[dict[str, Any]]:
    """Serialize Anthropic content blocks into conversation messages."""
    serialized: list[dict[str, Any]] = []
    for block in content_blocks:
        if block.type == "text":
            serialized.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            serialized.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
        elif block.type == "thinking":
            serialized.append(
                {
                    "type": "thinking",
                    "thinking": block.thinking,
                    "signature": getattr(block, "signature", ""),
                }
            )
    return serialized


def round_instruction(round_num: int, max_rounds: int, is_final: bool) -> str:
    """Generate the user instruction for the current research round."""
    if is_final:
        return (
            f"This is your final round ({round_num + 1}/{max_rounds}). "
            "Synthesize all findings into your final analysis. "
            "Do NOT call any more tools — produce your final output now."
        )
    return (
        f"Round {round_num + 1}/{max_rounds}. "
        "Review your scratchpad and decide what to investigate next. "
        "Use tools to gather evidence, then update your findings."
    )
