"""Reproducibility tests — LLM sampling pinned + RNG seeded.

These tests guard the WS-2 foundation guarantee: identical inputs to the
Praviar Pipeline pipeline must produce identical structured outputs. The two
moving parts are:

1. ``temperature=0`` on every analysis/verification Claude call.
2. A single ``deterministic_seed`` that pins Python/NumPy RNG at pipeline
   entry so any future tie-breaking or sampling stays reproducible.

GEPA prompt evolution intentionally needs sampling diversity and lives in
``praviar_pipeline/improvement/``; it is *not* covered by these guarantees.
"""

from __future__ import annotations

import inspect
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.clients.claude_runtime import tool_use_loop_impl
from praviar_pipeline.clients.claude_runtime_tool_loop import (
    tool_use_loop_impl as tool_use_loop_inner_impl,
)
from praviar_pipeline.clients.claude_tool_use import build_tool_loop_kwargs
from praviar_pipeline.utils.determinism import seed_pipeline_rng

# ---------------------------------------------------------------------------
# LLM-side determinism: every analysis/verification entry point defaults to T=0
# ---------------------------------------------------------------------------


def _default_for(func, name: str):
    """Return the default value for parameter ``name`` of ``func``."""
    return inspect.signature(func).parameters[name].default


def test_claude_client_complete_defaults_to_temperature_zero() -> None:
    assert _default_for(ClaudeClient.complete, "temperature") == 0.0


def test_claude_client_complete_text_defaults_to_temperature_zero() -> None:
    assert _default_for(ClaudeClient.complete_text, "temperature") == 0.0


def test_claude_client_tool_use_loop_defaults_to_temperature_zero() -> None:
    """The multi-turn research loop must inherit T=0 even when callers omit it."""
    assert _default_for(ClaudeClient._tool_use_loop, "temperature") == 0.0


def test_runtime_tool_use_loop_impl_defaults_to_temperature_zero() -> None:
    """Both the runtime delegator and its inner implementation default to T=0."""
    assert _default_for(tool_use_loop_impl, "temperature") == 0.0
    assert _default_for(tool_use_loop_inner_impl, "temperature") == 0.0


def test_build_tool_loop_kwargs_emits_zero_temperature_when_pinned() -> None:
    """When callers pass ``temperature=0.0``, the API payload must carry it."""
    kwargs = build_tool_loop_kwargs(
        model="claude-test",
        max_tokens=128,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_definitions=[],
        thinking=None,
        temperature=0.0,
    )
    assert kwargs["temperature"] == 0.0


@pytest.mark.asyncio
async def test_research_agent_loop_passes_temperature_zero_to_claude(
    monkeypatch,
) -> None:
    """A research-agent round must call ``_tool_use_loop`` with ``temperature=0``."""
    from praviar_pipeline.agents import base_runtime

    captured: dict = {}

    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="final answer")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
    )

    async def fake_tool_use_loop(**call_kwargs):
        captured.update(call_kwargs)
        return fake_response, 1, 2, ""

    fake_claude = SimpleNamespace(_tool_use_loop=fake_tool_use_loop)

    fake_toolkit = MagicMock()
    fake_toolkit.tool_definitions = []
    # Need >=2 rounds so the first round runs the tool_use_loop branch
    # (which carries the temperature) instead of the final-round complete_text.
    fake_settings = SimpleNamespace(
        analysis_max_tokens=4096,
        agentic_max_agent_rounds=2,
    )
    agent = SimpleNamespace(
        agent_type="claim_analysis",
        model_id="claude-test",
        max_rounds=2,
        _claude=fake_claude,
        _settings=fake_settings,
        build_toolkit=lambda _ctx: fake_toolkit,
        format_task=lambda _t, _c: "task",
        _build_system_prompt=lambda _sp: "sys",
        _build_cached_system_content=lambda _sp: [{"type": "text", "text": "sys"}],
        _mask_old_tool_outputs=lambda msgs: msgs,
        _round_instruction=lambda _r, _m, _f: "do work",
        _self_critique=AsyncMock(return_value=""),
    )

    # extract_round_artifacts/should_append_response treat our SimpleNamespace
    # response just like a real Claude response (text-only block, no tools).
    text, _trace = await base_runtime.execute_research_loop(agent, "task", {})

    assert text == "final answer"
    assert captured.get("temperature") == 0.0
    assert captured.get("model") == "claude-test"


# ---------------------------------------------------------------------------
# RNG-side determinism: configured seed flows through ``seed_pipeline_rng``
# ---------------------------------------------------------------------------


def test_settings_exposes_deterministic_seed_default() -> None:
    """The runtime config must expose a ``deterministic_seed`` knob."""
    from praviar_pipeline.config import Settings

    field = Settings.model_fields["deterministic_seed"]
    assert field.default == 42


def test_seed_pipeline_rng_is_reproducible() -> None:
    """Two seeded draws with the same seed must produce identical sequences."""
    seed_pipeline_rng(123)
    first = [random.random() for _ in range(8)]
    sample_first = random.sample(["a", "b", "c", "d", "e"], k=3)

    seed_pipeline_rng(123)
    second = [random.random() for _ in range(8)]
    sample_second = random.sample(["a", "b", "c", "d", "e"], k=3)

    assert first == second
    assert sample_first == sample_second


def test_seed_pipeline_rng_returns_seed_for_audit() -> None:
    """The helper returns the applied seed so callers can record it."""
    assert seed_pipeline_rng(7) == 7
