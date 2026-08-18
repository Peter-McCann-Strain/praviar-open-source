"""Tests for MarkushScopeAgent (Phase E.3).

Mocks the ClaudeClient's complete_text; validates the agent's verdict parsing,
normalisation, and the "at least one tool call required" invariant.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("praviar_pipeline.agents.markush_scope")

from praviar_pipeline.agents.markush_scope import (
    MarkushScopeAgent,
    MarkushScopeInput,
    _extract_verdict_block,
    _normalise_verdict,
)
from praviar_pipeline.agents.tools.markush_tools import MarkushToolkit


class TestExtractVerdictBlock:
    def test_no_block(self):
        assert _extract_verdict_block("no verdict here") is None

    def test_empty(self):
        assert _extract_verdict_block("") is None

    def test_valid_block(self):
        text = (
            "Some reasoning text.\n"
            '<verdict>\n{"verdict": "in_scope", "reasoning": "r", "confidence": 0.9}\n</verdict>\n'
            "trailing text"
        )
        result = _extract_verdict_block(text)
        assert result is not None
        assert result["verdict"] == "in_scope"

    def test_invalid_json_in_block(self):
        text = "<verdict>not json</verdict>"
        assert _extract_verdict_block(text) is None

    def test_no_closing_tag(self):
        text = '<verdict>{"verdict": "in_scope"}'
        assert _extract_verdict_block(text) is None


class TestNormaliseVerdict:
    def test_none_produces_abstention(self):
        v = _normalise_verdict(None, tool_calls=0, agent_model="test")
        assert v.verdict == "ambiguous"
        assert v.abstained_reason == "no_verdict_block"

    def test_unknown_verdict_coerced_to_ambiguous(self):
        v = _normalise_verdict(
            {"verdict": "maybe", "reasoning": "r"},
            tool_calls=1,
            agent_model="test",
        )
        assert v.verdict == "ambiguous"

    def test_valid_in_scope(self):
        v = _normalise_verdict(
            {
                "verdict": "in_scope",
                "reasoning": "target matches",
                "enumerated_hits": ["CCO"],
                "confidence": 0.85,
            },
            tool_calls=3,
            agent_model="claude-opus-4-7",
        )
        assert v.verdict == "in_scope"
        assert v.enumerated_hits == ["CCO"]
        assert v.confidence == 0.85
        assert v.tool_calls == 3

    def test_confidence_clamped(self):
        v = _normalise_verdict(
            {"verdict": "in_scope", "confidence": 2.5},
            tool_calls=1,
            agent_model="test",
        )
        assert v.confidence == 1.0

    def test_bad_confidence_type(self):
        v = _normalise_verdict(
            {"verdict": "in_scope", "confidence": "high"},
            tool_calls=1,
            agent_model="test",
        )
        assert v.confidence == 0.0

    def test_hits_non_list_ignored(self):
        v = _normalise_verdict(
            {"verdict": "in_scope", "enumerated_hits": "not a list"},
            tool_calls=1,
            agent_model="test",
        )
        assert v.enumerated_hits == []

    def test_reasoning_truncated(self):
        long = "x" * 10_000
        v = _normalise_verdict(
            {"verdict": "in_scope", "reasoning": long},
            tool_calls=1,
            agent_model="test",
        )
        assert len(v.reasoning) <= 4000


class TestMarkushToolkit:
    @pytest.mark.asyncio
    async def test_execute_increments_counter(self):
        toolkit = MarkushToolkit()
        assert toolkit.call_count == 0
        result = await toolkit.execute("rdkit_canonical", {"smiles": "CCO"})
        assert toolkit.call_count == 1
        assert "CCO" in result

    @pytest.mark.asyncio
    async def test_execute_returns_json_string(self):
        toolkit = MarkushToolkit()
        result = await toolkit.execute(
            "rdkit_substructure_match",
            {"pattern_smiles": "c1ccccc1", "target_smiles": "Cc1ccccc1"},
        )
        import json

        parsed = json.loads(result)
        assert parsed == {"matched": True}

    def test_tool_definitions_match_module(self):
        from praviar_pipeline.agents.tools.markush_tools import agent_tool_definitions

        toolkit = MarkushToolkit()
        assert toolkit.tool_definitions == agent_tool_definitions()


class TestMarkushScopeAgentRun:
    @pytest.mark.asyncio
    async def test_missing_target_returns_ambiguous(self):
        claude = MagicMock()
        agent = MarkushScopeAgent(claude)
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="[*:1]c1ccccc1",
                target_smiles="",
                claim_text="",
                rgroup_definitions={},
            )
        )
        assert verdict.verdict == "ambiguous"
        assert verdict.abstained_reason == "missing_inputs"

    @pytest.mark.asyncio
    async def test_missing_scaffold_returns_ambiguous(self):
        claude = MagicMock()
        agent = MarkushScopeAgent(claude)
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="",
                target_smiles="Clc1ccccc1",
                claim_text="",
                rgroup_definitions={},
            )
        )
        assert verdict.verdict == "ambiguous"

    @pytest.mark.asyncio
    async def test_tool_call_and_verdict_happy_path(self):
        claude = MagicMock()

        async def _complete_text(*, toolkit, **_kwargs):
            # Simulate the agent calling a tool and then issuing a verdict
            await toolkit.execute("rdkit_canonical", {"smiles": "CCO"})
            response = (
                "I checked substructure match.\n"
                "<verdict>\n"
                '{"verdict": "in_scope", "reasoning": "matches", '
                '"enumerated_hits": ["Clc1ccccc1"], "confidence": 0.88}\n'
                "</verdict>"
            )
            return response, {}

        claude.complete_text = AsyncMock(side_effect=_complete_text)
        agent = MarkushScopeAgent(claude, model_id="claude-opus-4-7")
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="[*:1]c1ccccc1",
                target_smiles="Clc1ccccc1",
                claim_text="R1 is halogen",
                rgroup_definitions={"1": ["F", "Cl", "Br", "I"]},
                patent_id="US123",
            )
        )
        assert verdict.verdict == "in_scope"
        assert verdict.confidence == 0.88
        assert verdict.tool_calls == 1
        assert verdict.agent_model == "claude-opus-4-7"

    @pytest.mark.asyncio
    async def test_no_tool_use_coerces_to_ambiguous(self):
        """Verdict issued without any tool call must be downgraded to ambiguous."""
        claude = MagicMock()

        async def _complete_text(*, toolkit, **_kwargs):
            # Agent does NOT call a tool
            response = (
                "<verdict>\n"
                '{"verdict": "in_scope", "reasoning": "trust me", "confidence": 0.9}\n'
                "</verdict>"
            )
            return response, {}

        claude.complete_text = AsyncMock(side_effect=_complete_text)
        agent = MarkushScopeAgent(claude, model_id="claude-opus-4-7")
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="[*:1]c1ccccc1",
                target_smiles="Clc1ccccc1",
                claim_text="R1 is halogen",
                rgroup_definitions={"1": ["Cl"]},
            )
        )
        assert verdict.verdict == "ambiguous"
        assert verdict.abstained_reason == "no_tool_use"
        assert verdict.tool_calls == 0
        assert verdict.confidence == 0.0

    @pytest.mark.asyncio
    async def test_malformed_verdict_becomes_ambiguous(self):
        claude = MagicMock()

        async def _complete_text(*, toolkit, **_kwargs):
            await toolkit.execute("rdkit_canonical", {"smiles": "CCO"})
            return "blah blah no verdict block", {}

        claude.complete_text = AsyncMock(side_effect=_complete_text)
        agent = MarkushScopeAgent(claude, model_id="claude-opus-4-7")
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="[*:1]c1ccccc1",
                target_smiles="Clc1ccccc1",
                claim_text="",
                rgroup_definitions={},
            )
        )
        assert verdict.verdict == "ambiguous"
        assert verdict.abstained_reason == "no_verdict_block"
        assert verdict.tool_calls == 1

    @pytest.mark.asyncio
    async def test_ambiguous_without_tool_use_preserved(self):
        """An ambiguous verdict with zero tool calls is valid (agent abstained)."""
        claude = MagicMock()

        async def _complete_text(*, toolkit, **_kwargs):
            return (
                "<verdict>\n"
                '{"verdict": "ambiguous", "reasoning": "cannot determine", '
                '"abstained_reason": "insufficient_info"}\n'
                "</verdict>"
            ), {}

        claude.complete_text = AsyncMock(side_effect=_complete_text)
        agent = MarkushScopeAgent(claude, model_id="claude-opus-4-7")
        verdict = await agent.run(
            MarkushScopeInput(
                scaffold_cxsmiles="[*:1]c1ccccc1",
                target_smiles="Clc1ccccc1",
                claim_text="",
                rgroup_definitions={},
            )
        )
        assert verdict.verdict == "ambiguous"
        assert verdict.abstained_reason == "insufficient_info"
