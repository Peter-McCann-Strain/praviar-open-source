"""Pure helper functions for the research-agent execution loop."""

from __future__ import annotations

import json
from typing import Any

from praviar_pipeline.agents.base_helpers import (
    serialize_response_content as _serialize_response_content,
)
from praviar_pipeline.models.reasoning import AgentRound, ToolCall
from praviar_pipeline.sanitize import sanitize_untrusted_text


def serialize_message_content(content: Any) -> str:
    """Normalize a message content payload for Claude completion calls."""
    if isinstance(content, str):
        return content
    return json.dumps(content)


def extract_round_artifacts(response: Any) -> tuple[str, list[ToolCall]]:
    """Extract the latest round text and tool calls from an Anthropic response."""
    round_text = ""
    round_tool_calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            round_text = block.text
        elif block.type == "tool_use":
            round_tool_calls.append(
                ToolCall(
                    tool_name=block.name,
                    tool_input=block.input if isinstance(block.input, dict) else {},
                    duration_ms=0,
                )
            )
    return round_text, round_tool_calls


def build_agent_round(
    *,
    round_number: int,
    thinking: str,
    tool_calls: list[ToolCall],
    observations: str,
    is_final_round: bool,
) -> AgentRound:
    """Build a trace entry for one research round."""
    return AgentRound(
        round_number=round_number,
        thinking_summary=thinking[:500] if thinking else "",
        tool_calls=tool_calls,
        observations=observations[:500] if observations else "",
        scratchpad_delta={},
        decision="final_output" if is_final_round else "continue_research",
    )


def should_append_response(response: Any) -> bool:
    """Return True when a response should be appended to the conversation."""
    return response is not None and response.stop_reason != "tool_use"


def build_critique_prompt(output: str) -> str:
    """Build the prompt used for the self-critique pass."""
    return (
        "Review your analysis below for any inconsistencies, gaps, or errors. "
        "Be specific about what might be wrong and why.\n\n"
        + sanitize_untrusted_text(output, max_len=5000, data_type="model_analysis")
    )


def serialize_response_content(content_blocks: list[Any]) -> list[dict[str, Any]]:
    """Serialize Anthropic response content blocks into conversation messages."""
    return _serialize_response_content(content_blocks)
