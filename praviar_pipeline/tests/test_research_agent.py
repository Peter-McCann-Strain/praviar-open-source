"""Tests for ReasoningTrace models and the ResearchAgent base class."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.reasoning import AgentRound, ReasoningTrace, ToolCall

# ── ReasoningTrace Model Tests ────────────────────────────────────────────────


class TestToolCall:
    def test_construction(self):
        tc = ToolCall(
            tool_name="lookup_patent",
            tool_input={"patent_id": "US-1234-A"},
            tool_output_summary="Found patent with 5 claims",
            duration_ms=150,
        )
        assert tc.tool_name == "lookup_patent"
        assert tc.tool_input == {"patent_id": "US-1234-A"}
        assert tc.duration_ms == 150

    def test_defaults(self):
        tc = ToolCall(tool_name="test")
        assert tc.tool_input == {}
        assert tc.tool_output_summary == ""
        assert tc.duration_ms == 0

    def test_serialization(self):
        tc = ToolCall(tool_name="test", tool_input={"key": "val"}, duration_ms=42)
        d = tc.model_dump()
        assert d["tool_name"] == "test"
        roundtrip = ToolCall.model_validate(d)
        assert roundtrip == tc


class TestAgentRound:
    def test_construction(self):
        ar = AgentRound(
            round_number=1,
            thinking_summary="Analyzing claim 1...",
            tool_calls=[ToolCall(tool_name="fetch_spec", duration_ms=100)],
            observations="Spec defines 'compound' broadly",
            scratchpad_delta={"claim_terms": ["compound"]},
            decision="Need to check dependent claims",
        )
        assert ar.round_number == 1
        assert len(ar.tool_calls) == 1
        assert ar.scratchpad_delta["claim_terms"] == ["compound"]

    def test_defaults(self):
        ar = AgentRound(round_number=1)
        assert ar.thinking_summary == ""
        assert ar.tool_calls == []
        assert ar.observations == ""
        assert ar.scratchpad_delta == {}
        assert ar.decision == ""


class TestReasoningTrace:
    def test_construction(self):
        trace = ReasoningTrace(
            agent_type="claim_analysis",
            model="claude-opus-4-6",
            patent_id="US-1234-A",
            rounds=[AgentRound(round_number=1)],
            self_critique="Analysis looks consistent",
            confidence=0.85,
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_duration_ms=15000,
        )
        assert trace.agent_type == "claim_analysis"
        assert len(trace.rounds) == 1
        assert trace.confidence == 0.85

    def test_defaults(self):
        trace = ReasoningTrace(agent_type="test")
        assert trace.model == ""
        assert trace.patent_id == ""
        assert trace.rounds == []
        assert trace.self_critique == ""
        assert trace.revisions_made == []
        assert trace.confidence == 0.0
        assert trace.total_input_tokens == 0

    def test_full_serialization_roundtrip(self):
        trace = ReasoningTrace(
            agent_type="prosecution",
            model="claude-sonnet-4-6",
            patent_id="US-5678-B",
            rounds=[
                AgentRound(
                    round_number=1,
                    tool_calls=[
                        ToolCall(tool_name="fetch_wrapper", duration_ms=200),
                        ToolCall(tool_name="fetch_document", duration_ms=300),
                    ],
                    observations="Found 3 office actions",
                    scratchpad_delta={"amendments": 2},
                ),
                AgentRound(
                    round_number=2,
                    observations="Estoppel applies to claims 1-3",
                    decision="final_output",
                ),
            ],
            self_critique="Should have checked continuation chain",
            revisions_made=["Added continuation note"],
            confidence=0.72,
            total_input_tokens=10000,
            total_output_tokens=4000,
            total_duration_ms=30000,
        )
        json_str = trace.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["agent_type"] == "prosecution"
        assert len(parsed["rounds"]) == 2
        assert len(parsed["rounds"][0]["tool_calls"]) == 2

        # Roundtrip
        restored = ReasoningTrace.model_validate_json(json_str)
        assert restored == trace


# ── ResearchAgent Base Class Tests ────────────────────────────────────────────


class _MockToolkit:
    """Simple mock toolkit for testing."""

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        return f"Result for {tool_name}: {tool_input}"


class TestResearchAgentBase:
    """Test the base ResearchAgent class via a minimal concrete subclass."""

    def _make_agent_class(self):
        """Create a minimal concrete subclass of ResearchAgent."""
        from praviar_pipeline.agents.base import ResearchAgent

        class TestAgent(ResearchAgent):
            @property
            def agent_type(self) -> str:
                return "test_agent"

            @property
            def model_id(self) -> str:
                return "claude-haiku-4-5-20251001"

            @property
            def max_rounds(self) -> int:
                return 3

            @property
            def prompt_file(self) -> str:
                return "triage_system.txt"  # Use existing prompt for test

            def build_toolkit(self, context):
                return _MockToolkit()

            def format_task(self, task, context):
                return f"Research task: {task}"

        return TestAgent

    @pytest.fixture
    def mock_settings(self):
        """Patch settings for testing."""
        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            settings = MagicMock()
            settings.agentic_max_agent_rounds = 3
            settings.agentic_observation_masking = True
            settings.agentic_scratchpad_enabled = True
            settings.analysis_max_tokens = 8192
            settings.claude_triage_model = "claude-haiku-4-5-20251001"
            mock.return_value = settings
            yield settings

    def test_observation_masking(self, mock_settings):
        """Test that old tool outputs get masked."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        messages = [
            {"role": "user", "content": "task"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "test_tool", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "old result data"},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "test_tool", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t2", "content": "new result data"},
                ],
            },
        ]

        masked = agent._mask_old_tool_outputs(messages)

        # First tool result should be masked
        assert (
            masked[2]["content"][0]["content"] == "[Output analyzed — key findings in scratchpad]"
        )
        # Second (latest) tool result should be intact
        assert masked[4]["content"][0]["content"] == "new result data"

    def test_observation_masking_disabled(self, mock_settings):
        """Test masking is skipped when disabled."""
        mock_settings.agentic_observation_masking = False
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "old data"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t2", "content": "new data"},
                ],
            },
        ]

        result = agent._mask_old_tool_outputs(messages)
        assert result[0]["content"][0]["content"] == "old data"

    def test_round_instruction_final(self, mock_settings):
        """Test that final round instruction is correct."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        instruction = agent._round_instruction(4, 5, True)
        assert "final round" in instruction.lower()
        assert "5/5" in instruction

    def test_round_instruction_normal(self, mock_settings):
        """Test normal round instruction."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        instruction = agent._round_instruction(1, 5, False)
        assert "2/5" in instruction

    def test_context_size_estimation(self, mock_settings):
        """Test context size is estimated correctly."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        messages = [{"role": "user", "content": "x" * 1000}]
        size = agent._estimate_context_size(messages)
        assert size > 1000

    def test_system_prompt_includes_scratchpad(self, mock_settings):
        """Test scratchpad injection into system prompt."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        scratchpad = {"findings": ["claim 1 is broad"], "risk": "high"}
        prompt = agent._build_system_prompt(scratchpad)
        assert "<scratchpad>" in prompt
        assert "claim 1 is broad" in prompt

    def test_system_prompt_no_scratchpad_when_empty(self, mock_settings):
        """Test no scratchpad section when empty."""
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        agent = agent_class(claude_mock)

        prompt = agent._build_system_prompt({})
        assert "<scratchpad>" not in prompt

    @pytest.mark.asyncio
    async def test_research_smoke_no_toolkit(self, mock_settings):
        mock_settings.agentic_max_agent_rounds = 1
        agent_class = self._make_agent_class()
        claude_mock = MagicMock()
        claude_mock.complete_text = AsyncMock(
            return_value=("final answer", {"input_tokens": 11, "output_tokens": 7})
        )
        agent = agent_class(claude_mock)
        agent.build_toolkit = lambda context: None  # type: ignore[method-assign]

        final_text, trace = await agent.research("Investigate", {"patent_id": "US123"})

        assert final_text == "final answer"
        assert len(trace.rounds) == 1
        assert trace.rounds[0].decision == "final_output"
        assert trace.total_input_tokens == 11
        assert trace.total_output_tokens == 7


# ── Unified Config Contract Tests ─────────────────────────────────────────────


class TestUnifiedPipelineConfig:
    def test_pipeline_mode_field_removed(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            from praviar_pipeline.config import Settings

            s = Settings(anthropic_api_key="sk-ant-test123")
            assert not hasattr(s, "pipeline_mode")

    def test_legacy_pipeline_mode_rejected(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            from praviar_pipeline.config import Settings

            with pytest.raises(ValueError, match="Extra inputs are not permitted"):
                Settings(anthropic_api_key="sk-ant-test123", pipeline_mode="advanced")

    def test_agentic_settings_defaults(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            from praviar_pipeline.config import Settings

            s = Settings(anthropic_api_key="sk-ant-test123")
            assert s.agentic_max_agent_rounds == 5
            assert s.agentic_observation_masking is True
            assert s.agentic_scratchpad_enabled is True

    def test_legacy_advanced_agent_settings_rejected(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            from pydantic import ValidationError

            from praviar_pipeline.config import Settings

            with pytest.raises(ValidationError):
                Settings(
                    anthropic_api_key="sk-ant-test123",
                    advanced_max_agent_rounds=3,
                )


# ── FTOReport Model Tests ────────────────────────────────────────────────────


class TestFTOReportReasoningTraces:
    @pytest.fixture
    def _compound(self):
        from praviar_pipeline.models.compound import ResolvedCompound

        return ResolvedCompound(
            name="test",
            canonical_smiles="C",
            inchi="InChI=1S/CH4/h1H4",
            inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
            pubchem_cid=297,
            molecular_formula="CH4",
            molecular_weight=16.04,
            original_input="test",
            input_type="name",
        )

    def test_report_has_execution_profile_metadata(self, _compound):
        """FTOReport includes unified execution metadata."""
        from praviar_pipeline.models.analysis import RiskLevel
        from praviar_pipeline.models.report import FTOReport, RiskSummary

        report = FTOReport(
            compound=_compound,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.LOW,
                executive_summary="Test summary for low risk assessment.",
            ),
        )
        assert not hasattr(report, "pipeline_mode")
        assert not hasattr(report, "analysis_depth")
        assert report.execution_profile == "world_class_adaptive"

    def test_report_reasoning_traces_default_empty(self, _compound):
        from praviar_pipeline.models.analysis import RiskLevel
        from praviar_pipeline.models.report import FTOReport, RiskSummary

        report = FTOReport(
            compound=_compound,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.LOW,
                executive_summary="Test summary for low risk assessment.",
            ),
        )
        assert report.reasoning_traces == []
        assert report.execution_profile == "world_class_adaptive"

    def test_report_rejects_legacy_execution_identity(self, _compound):
        from praviar_pipeline.models.analysis import RiskLevel
        from praviar_pipeline.models.report import FTOReport, RiskSummary

        with pytest.raises(ValidationError, match="world_class_adaptive"):
            FTOReport(
                compound=_compound,
                risk_summary=RiskSummary(
                    overall_risk=RiskLevel.LOW,
                    executive_summary="Test summary for low risk assessment.",
                ),
                execution_profile="v1",
            )

        with pytest.raises(ValidationError, match="world_class_adaptive"):
            FTOReport(
                compound=_compound,
                risk_summary=RiskSummary(
                    overall_risk=RiskLevel.LOW,
                    executive_summary="Test summary for low risk assessment.",
                ),
                report_pipeline="report_pipeline_v2",
            )

    def test_report_with_reasoning_trace_dict(self, _compound):
        from praviar_pipeline.models.analysis import RiskLevel
        from praviar_pipeline.models.report import FTOReport, RiskSummary

        trace_dict = ReasoningTrace(
            agent_type="claim_analysis",
            model="claude-opus-4-6",
            confidence=0.85,
        ).model_dump(mode="json")

        report = FTOReport(
            compound=_compound,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.LOW,
                executive_summary="Test summary for low risk assessment.",
            ),
            reasoning_traces=[trace_dict],
        )
        assert len(report.reasoning_traces) == 1
        assert report.reasoning_traces[0]["agent_type"] == "claim_analysis"


# ── Run Pipeline Signature Tests ──────────────────────────────────────────────


class TestRunPipelineSignature:
    @pytest.mark.asyncio
    async def test_mode_parameter_removed(self):
        """Verify run_pipeline no longer accepts mode/depth selection."""
        import inspect

        from praviar_pipeline.run import run_pipeline

        sig = inspect.signature(run_pipeline)
        assert "mode" not in sig.parameters
