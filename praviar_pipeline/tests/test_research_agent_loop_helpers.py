from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.agents.base_loop_helpers import (
    build_agent_round,
    build_critique_prompt,
    extract_round_artifacts,
    serialize_message_content,
    serialize_response_content,
    should_append_response,
)
from praviar_pipeline.models.reasoning import ToolCall


def test_serialize_message_content_normalizes_non_strings() -> None:
    assert serialize_message_content({"a": 1}) == '{"a": 1}'
    assert serialize_message_content("plain text") == "plain text"


def test_extract_round_artifacts_and_round_record() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="final analysis"),
            SimpleNamespace(type="tool_use", name="lookup", input={"q": "x"}),
        ]
    )

    round_text, tool_calls = extract_round_artifacts(response)
    agent_round = build_agent_round(
        round_number=2,
        thinking="reasoning" * 100,
        tool_calls=tool_calls,
        observations=round_text,
        is_final_round=True,
    )

    assert round_text == "final analysis"
    assert tool_calls == [ToolCall(tool_name="lookup", tool_input={"q": "x"}, duration_ms=0)]
    assert agent_round.thinking_summary == ("reasoning" * 100)[:500]
    assert agent_round.observations == "final analysis"
    assert agent_round.decision == "final_output"


def test_serialize_response_content_and_append_gate() -> None:
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[
            SimpleNamespace(type="text", text="hello"),
            SimpleNamespace(type="thinking", thinking="r", signature="sig"),
        ],
    )

    assert should_append_response(response) is True
    assert should_append_response(None) is False
    assert should_append_response(SimpleNamespace(stop_reason="tool_use")) is False
    assert serialize_response_content(response.content) == [
        {"type": "text", "text": "hello"},
        {"type": "thinking", "thinking": "r", "signature": "sig"},
    ]


def test_build_critique_prompt_truncates_output() -> None:
    prompt = build_critique_prompt("x" * 6000)

    assert '<untrusted_source_data type="model_analysis" encoding="xml-escaped-text">' in prompt
    assert "</untrusted_source_data>" in prompt
    assert "<your_analysis>" not in prompt
    assert "[TRUNCATED]" in prompt
    assert len(prompt) < 5300
