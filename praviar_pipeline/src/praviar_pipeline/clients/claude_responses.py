"""Response parsing helpers for the Claude client."""

from __future__ import annotations

from typing import Any


def cache_token_counts(response: Any) -> tuple[int, int]:
    """Return Anthropic cache read and cache creation token counts."""
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
    return cache_read, cache_creation


def usage_payload(
    *,
    response: Any,
    total_input: int,
    total_output: int,
    model: str,
) -> dict[str, Any]:
    """Build the common usage payload returned by ClaudeClient methods."""
    cache_read, cache_creation = cache_token_counts(response)
    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "model": model,
    }


def response_text(content: list[Any]) -> str:
    """Concatenate Claude text content blocks into one string."""
    return "".join(block.text for block in content if block.type == "text")


def latest_thinking_text(content: list[Any]) -> str:
    """Return the latest thinking block text from a Claude response."""
    thinking_blocks = [block.thinking for block in content if block.type == "thinking"]
    return thinking_blocks[-1] if thinking_blocks else ""


def round_thinking_blocks(content: list[Any]) -> list[str]:
    """Return all thinking block texts for a response round."""
    return [block.thinking for block in content if block.type == "thinking"]


def tool_use_blocks(content: list[Any]) -> list[Any]:
    """Return all tool-use blocks in a response."""
    return [block for block in content if block.type == "tool_use"]


def tool_call_count(content: list[Any]) -> int:
    """Count tool-use blocks in a response."""
    return sum(1 for block in content if block.type == "tool_use")
