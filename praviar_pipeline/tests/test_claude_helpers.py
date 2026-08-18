from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.clients.claude_prompting import build_effective_system, build_system_content
from praviar_pipeline.clients.claude_responses import (
    latest_thinking_text,
    response_text,
    tool_call_count,
    tool_use_blocks,
)
from praviar_pipeline.clients.claude_tool_use import serialize_content_blocks


def test_build_effective_system_prepends_runtime_date_context() -> None:
    system = build_effective_system("Base system prompt.")

    assert system.startswith("CURRENT DATE:")
    assert system.endswith("Base system prompt.")


def test_build_effective_system_appends_json_schema() -> None:
    system = build_effective_system("Base system prompt.", {"type": "object"})

    assert "Base system prompt." in system
    assert "Output ONLY the JSON" in system
    assert '"type": "object"' in system


def test_build_system_content_marks_cached_prompt() -> None:
    content = build_system_content("hello", cache_system=True)

    assert content == [
        {
            "type": "text",
            "text": "hello",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]


def test_response_helpers_extract_text_thinking_and_tools() -> None:
    content = [
        SimpleNamespace(type="thinking", thinking="plan"),
        SimpleNamespace(type="text", text="hello "),
        SimpleNamespace(type="tool_use", id="tool-1", name="lookup", input={"q": "abc"}),
        SimpleNamespace(type="text", text="world"),
    ]

    assert latest_thinking_text(content) == "plan"
    assert response_text(content) == "hello world"
    assert tool_call_count(content) == 1
    assert tool_use_blocks(content)[0].name == "lookup"


# ---------------------------------------------------------------------------
# Hostile tests: cache_control TTL must be the string "1h", never int 3600
# ---------------------------------------------------------------------------


def test_cache_control_ttl_is_string_not_integer() -> None:
    """The cache_control ttl field must be a str, not an int.

    The Anthropic prompt-caching API rejects numeric ttl values.  A plain
    3600 instead of "1h" would silently pass Python type checks but be
    rejected at the API boundary.
    """
    content = build_system_content("hello", cache_system=True)
    block = content[0]
    assert isinstance(block["cache_control"]["ttl"], str), (
        f"Expected ttl to be str, got {type(block['cache_control']['ttl']).__name__!r}"
    )


def test_cache_control_ttl_is_exactly_1h() -> None:
    """The cache_control ttl value must be exactly the string '1h'."""
    content = build_system_content("hello", cache_system=True)
    block = content[0]
    assert block["cache_control"]["ttl"] == "1h", (
        f"Expected ttl == '1h', got {block['cache_control']['ttl']!r}"
    )


def test_cache_control_ttl_integer_3600_is_absent() -> None:
    """The integer 3600 must never appear as the ttl value.

    This is an explicit negative assertion: if someone changes the string
    back to an integer the test suite catches it immediately.
    """
    content = build_system_content("hello", cache_system=True)
    block = content[0]
    assert block["cache_control"]["ttl"] != 3600, (
        "ttl must not be the integer 3600; use the string '1h' instead"
    )


def test_serialize_content_blocks_preserves_tool_use_history_shape() -> None:
    content = [
        SimpleNamespace(type="thinking", thinking="plan", signature="sig"),
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="tool_use", id="tool-1", name="lookup", input={"q": "abc"}),
    ]

    assert serialize_content_blocks(content) == [
        {"type": "thinking", "thinking": "plan", "signature": "sig"},
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "id": "tool-1", "name": "lookup", "input": {"q": "abc"}},
    ]
