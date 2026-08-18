from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.agents.base_helpers import (
    MASKED_TOOL_OUTPUT_SENTINEL,
    build_cached_system_content,
    build_system_prompt,
    estimate_context_size,
    mask_old_tool_outputs,
    round_instruction,
    serialize_response_content,
)


def test_build_system_prompt_appends_scratchpad() -> None:
    prompt = build_system_prompt(
        base_prompt="base",
        scratchpad={"risk": "high"},
        scratchpad_enabled=True,
    )

    assert prompt.startswith("base")
    assert "<scratchpad>" in prompt
    assert '"risk": "high"' in prompt


def test_build_cached_system_content_marks_base_prompt_ephemeral() -> None:
    blocks = build_cached_system_content(
        base_prompt="base",
        scratchpad={"risk": "high"},
        scratchpad_enabled=True,
    )

    assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "<scratchpad>" in blocks[1]["text"]


def test_mask_old_tool_outputs_preserves_latest_result() -> None:
    messages = [
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "old"}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "new"}],
        },
    ]

    masked = mask_old_tool_outputs(messages, masking_enabled=True)

    assert masked[0]["content"][0]["content"] == MASKED_TOOL_OUTPUT_SENTINEL
    assert masked[1]["content"][0]["content"] == "new"


def test_estimate_context_size_and_round_instruction() -> None:
    assert estimate_context_size([{"role": "user", "content": "x" * 10}]) > 10
    assert "final round" in round_instruction(2, 3, True).lower()


def test_serialize_response_content_keeps_supported_block_types() -> None:
    blocks = [
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="tool_use", id="1", name="lookup", input={"q": "x"}),
        SimpleNamespace(type="thinking", thinking="reasoning", signature="sig"),
    ]

    serialized = serialize_response_content(blocks)

    assert serialized == [
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "id": "1", "name": "lookup", "input": {"q": "x"}},
        {"type": "thinking", "thinking": "reasoning", "signature": "sig"},
    ]
