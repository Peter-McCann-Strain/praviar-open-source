"""Tests for Feature 3: Multi-Perspective Analysis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import LLMResponseError
from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    MultiPerspectiveSynthesis,
    PatentAnalysis,
    PerspectiveAnalysis,
    PerspectiveType,
    RiskLevel,
)

from .helpers import make_claude_client_mock

# ---------------------------------------------------------------------------
# PerspectiveType enum tests
# ---------------------------------------------------------------------------


class TestPerspectiveType:
    def test_enum_values(self):
        assert PerspectiveType.PATENT_ATTORNEY == "patent_attorney"
        assert PerspectiveType.MEDICINAL_CHEMIST == "medicinal_chemist"
        assert PerspectiveType.BUSINESS_ANALYST == "business_analyst"

    def test_enum_has_three_members(self):
        assert len(PerspectiveType) == 3

    def test_enum_str_enum(self):
        """PerspectiveType is a StrEnum, so it can be used as a string."""
        assert isinstance(PerspectiveType.PATENT_ATTORNEY, str)
        assert f"perspective: {PerspectiveType.PATENT_ATTORNEY}" == "perspective: patent_attorney"


# ---------------------------------------------------------------------------
# PerspectiveAnalysis model tests
# ---------------------------------------------------------------------------


class TestPerspectiveAnalysis:
    def test_basic_construction(self):
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.PATENT_ATTORNEY,
            key_findings=["Claim 1 covers the target compound"],
            risk_assessment="High risk of literal infringement",
            confidence=0.85,
            recommended_risk_level=RiskLevel.HIGH,
            evidence_cited=["Claim 1, element 1"],
        )
        assert pa.perspective == PerspectiveType.PATENT_ATTORNEY
        assert len(pa.key_findings) == 1
        assert pa.confidence == 0.85
        assert pa.recommended_risk_level == RiskLevel.HIGH

    def test_defaults(self):
        pa = PerspectiveAnalysis(perspective=PerspectiveType.MEDICINAL_CHEMIST)
        assert pa.key_findings == []
        assert pa.risk_assessment == ""
        assert pa.confidence == 0.0
        assert pa.recommended_risk_level is None
        assert pa.evidence_cited == []

    def test_perspective_coercion_spaces_and_hyphens(self):
        """Perspective values with spaces or hyphens should be normalized."""
        pa = PerspectiveAnalysis(perspective="patent attorney")
        assert pa.perspective == PerspectiveType.PATENT_ATTORNEY

        pa2 = PerspectiveAnalysis(perspective="patent-attorney")
        assert pa2.perspective == PerspectiveType.PATENT_ATTORNEY

    def test_perspective_coercion_case_insensitive(self):
        pa = PerspectiveAnalysis(perspective="MEDICINAL_CHEMIST")
        assert pa.perspective == PerspectiveType.MEDICINAL_CHEMIST

    def test_perspective_coercion_invalid_falls_back(self):
        """Invalid perspective values should fall back to patent_attorney."""
        pa = PerspectiveAnalysis(perspective="unknown_expert")
        assert pa.perspective == PerspectiveType.PATENT_ATTORNEY

    def test_risk_level_coercion(self):
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.BUSINESS_ANALYST,
            recommended_risk_level="HIGH",
        )
        assert pa.recommended_risk_level == RiskLevel.HIGH

    def test_risk_level_coercion_invalid_fails_loud(self):
        """An unrecognised recommended risk level must raise, not default.

        Silently defaulting a risk-bearing enum is the silent-zero defect.
        """
        with pytest.raises(LLMResponseError):
            PerspectiveAnalysis(
                perspective=PerspectiveType.BUSINESS_ANALYST,
                recommended_risk_level="unknown",
            )

    def test_risk_level_none_allowed(self):
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.BUSINESS_ANALYST,
            recommended_risk_level=None,
        )
        assert pa.recommended_risk_level is None

    def test_confidence_bounds(self):
        pa = PerspectiveAnalysis(perspective=PerspectiveType.PATENT_ATTORNEY, confidence=0.0)
        assert pa.confidence == 0.0

        pa2 = PerspectiveAnalysis(perspective=PerspectiveType.PATENT_ATTORNEY, confidence=1.0)
        assert pa2.confidence == 1.0

    def test_confidence_out_of_bounds_raises(self):
        with pytest.raises(ValidationError):
            PerspectiveAnalysis(perspective=PerspectiveType.PATENT_ATTORNEY, confidence=1.5)

        with pytest.raises(ValidationError):
            PerspectiveAnalysis(perspective=PerspectiveType.PATENT_ATTORNEY, confidence=-0.1)

    def test_extra_fields_ignored(self):
        """Extra fields from LLM output should be silently ignored."""
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.PATENT_ATTORNEY,
            key_findings=["finding"],
            unexpected_field="should be ignored",
        )
        assert not hasattr(pa, "unexpected_field")


# ---------------------------------------------------------------------------
# MultiPerspectiveSynthesis model tests
# ---------------------------------------------------------------------------


class TestMultiPerspectiveSynthesis:
    def test_basic_construction(self):
        synthesis = MultiPerspectiveSynthesis(
            perspectives=[
                PerspectiveAnalysis(
                    perspective=PerspectiveType.PATENT_ATTORNEY,
                    risk_assessment="High risk",
                    confidence=0.9,
                    recommended_risk_level=RiskLevel.HIGH,
                ),
            ],
            synthesized_risk=RiskLevel.HIGH,
            disagreements=["Attorney says HIGH, chemist says LOW"],
            synthesis_reasoning="Weighted toward attorney perspective",
        )
        assert synthesis.synthesized_risk == RiskLevel.HIGH
        assert len(synthesis.disagreements) == 1
        assert len(synthesis.perspectives) == 1

    def test_defaults(self):
        synthesis = MultiPerspectiveSynthesis()
        assert synthesis.perspectives == []
        assert synthesis.synthesized_risk is None
        assert synthesis.disagreements == []
        assert synthesis.synthesis_reasoning == ""

    def test_synthesized_risk_coercion_invalid_fails_loud(self):
        """An unrecognised synthesised risk level must raise, not default."""
        with pytest.raises(LLMResponseError):
            MultiPerspectiveSynthesis(synthesized_risk="not_a_risk")

    def test_synthesized_risk_none_allowed(self):
        synthesis = MultiPerspectiveSynthesis(synthesized_risk=None)
        assert synthesis.synthesized_risk is None


# ---------------------------------------------------------------------------
# PatentAnalysis backwards compatibility
# ---------------------------------------------------------------------------


class TestPatentAnalysisBackwardsCompatibility:
    def test_new_fields_default_to_empty(self):
        """Existing PatentAnalysis instances should work without perspective fields."""
        analysis = PatentAnalysis(
            patent_id="US1234567B2",
            risk_level=RiskLevel.MEDIUM,
            risk_summary="Test",
        )
        assert analysis.perspective_analyses == []
        assert analysis.multi_perspective_synthesis is None

    def test_with_perspectives(self):
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.PATENT_ATTORNEY,
            key_findings=["finding"],
            confidence=0.8,
        )
        synthesis = MultiPerspectiveSynthesis(
            perspectives=[pa],
            synthesized_risk=RiskLevel.HIGH,
        )
        analysis = PatentAnalysis(
            patent_id="US1234567B2",
            risk_level=RiskLevel.MEDIUM,
            risk_summary="Test",
            perspective_analyses=[pa],
            multi_perspective_synthesis=synthesis,
        )
        assert len(analysis.perspective_analyses) == 1
        assert analysis.multi_perspective_synthesis.synthesized_risk == RiskLevel.HIGH

    def test_serialization_round_trip(self):
        """PatentAnalysis with perspective data should serialize and deserialize."""
        pa = PerspectiveAnalysis(
            perspective=PerspectiveType.MEDICINAL_CHEMIST,
            key_findings=["Tanimoto 0.92"],
            risk_assessment="High structural overlap",
            confidence=0.88,
            recommended_risk_level=RiskLevel.HIGH,
        )
        analysis = PatentAnalysis(
            patent_id="US1234567B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="Test",
            perspective_analyses=[pa],
        )
        data = analysis.model_dump(mode="json")
        restored = PatentAnalysis.model_validate(data)
        assert len(restored.perspective_analyses) == 1
        assert restored.perspective_analyses[0].perspective == PerspectiveType.MEDICINAL_CHEMIST
        assert restored.perspective_analyses[0].confidence == 0.88


# ---------------------------------------------------------------------------
# Config settings tests
# ---------------------------------------------------------------------------


class TestMultiPerspectiveConfig:
    def test_default_disabled(self, mock_settings):
        from praviar_pipeline.config import get_settings

        settings = get_settings()
        assert settings.multi_perspective_enabled is False

    def test_perspective_concurrency_default(self, mock_settings):
        from praviar_pipeline.config import get_settings

        settings = get_settings()
        assert settings.perspective_concurrency == 3

    def test_perspective_max_tokens_default(self, mock_settings):
        from praviar_pipeline.config import get_settings

        settings = get_settings()
        assert settings.perspective_max_tokens == 8192


# ---------------------------------------------------------------------------
# Adaptive prompt injection tests
# ---------------------------------------------------------------------------


class TestAdaptivePromptInjection:
    async def test_prompt_injected_when_enabled(
        self,
        succinic_acid,
        sample_patent_hits,
        sample_triage_results,
        mock_settings,
    ):
        """When multi_perspective_enabled=True, the system prompt is extended."""
        from praviar_pipeline.pipeline.step4_analyze import analyze_patents

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")

        # Track load_prompt calls to verify injection
        base_prompt = "You are a patent attorney."
        perspective_section = "--- MULTI-PERSPECTIVE ANALYSIS ---"

        def _load_prompt(filename: str) -> str:
            if filename == "claim_analysis_system.txt":
                return base_prompt
            if filename == "multi_perspective_section.txt":
                return perspective_section
            if filename == "evaluator_system.txt":
                return "You are an evaluator."
            return ""

        mock_claude.load_prompt = MagicMock(side_effect=_load_prompt)

        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Methods for producing succinic acid",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="producing succinic acid",
                            status=ElementStatus.MET,
                            reasoning="Exact match",
                            confidence=0.95,
                        ),
                    ],
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.95,
                ),
            ],
            risk_level=RiskLevel.HIGH,
            risk_summary="All elements met",
        )

        mock_claude.complete_with_thinking.return_value = (
            analysis,
            "thinking...",
            {"input_tokens": 500, "output_tokens": 300, "model": "claude-opus-4-6"},
        )
        evaluation = AnalysisEvaluation(issues=[], overall_quality="good")
        mock_claude.complete.return_value = (
            evaluation,
            {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5-20251001"},
        )
        mock_claude.close = AsyncMock()
        mock_claude.__aenter__ = AsyncMock(return_value=mock_claude)
        mock_claude.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.pipeline.step4_analyze.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step4_analyze.BigQueryClient",
            ) as mock_bq_cls,
            patch.dict("os.environ", {"MULTI_PERSPECTIVE_ENABLED": "true"}),
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.close = AsyncMock()
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            # Override settings to enable multi-perspective

            clear_settings_cache()

            patents = sample_patent_hits[:1]
            _analyses, _failures, _traces = await analyze_patents(
                patents,
                succinic_acid,
                triage_results=sample_triage_results,
            )

        # Verify multi_perspective_section.txt was loaded
        load_calls = [c.args[0] for c in mock_claude.load_prompt.call_args_list]
        assert "multi_perspective_section.txt" in load_calls

    async def test_prompt_injected_when_agentic_escalation_is_expected(
        self,
        succinic_acid,
        sample_patent_hits,
        sample_triage_results,
        mock_settings,
    ):
        """Agentic escalation reasons do not disable the shared prompt section."""
        from praviar_pipeline.pipeline.step4_analyze import analyze_patents

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Methods for producing succinic acid",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="producing succinic acid",
                            status=ElementStatus.MET,
                            reasoning="Exact match",
                            confidence=0.95,
                        ),
                    ],
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.95,
                ),
            ],
            risk_level=RiskLevel.HIGH,
            risk_summary="All elements met",
        )

        # Advanced mode: research returns (text, trace)
        from praviar_pipeline.models.reasoning import ReasoningTrace

        mock_trace = ReasoningTrace(
            agent_type="claim_analysis",
            model="claude-opus-4-6",
            patent_id="US7851188B2",
        )
        mock_trace.total_input_tokens = 500
        mock_trace.total_output_tokens = 300

        mock_claude.complete.return_value = (
            analysis,
            {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5-20251001"},
        )
        mock_claude.complete_text = AsyncMock(
            return_value=("research findings", {"input_tokens": 200, "output_tokens": 100}),
        )
        mock_claude.close = AsyncMock()
        mock_claude.__aenter__ = AsyncMock(return_value=mock_claude)
        mock_claude.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.pipeline.step4_analyze.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step4_analyze.BigQueryClient",
            ) as mock_bq_cls,
            patch(
                "praviar_pipeline.pipeline.step4_analyze._analyze_single_patent_agentic",
                new=AsyncMock(return_value=(analysis, mock_trace)),
            ),
            patch.dict("os.environ", {"MULTI_PERSPECTIVE_ENABLED": "true"}),
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.close = AsyncMock()
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            clear_settings_cache()

            patents = sample_patent_hits[:1]
            _analyses, _failures, _traces = await analyze_patents(
                patents,
                succinic_acid,
                triage_results=sample_triage_results,
                global_escalation_reasons=["high_risk_triage"],
            )

        load_calls = [c.args[0] for c in mock_claude.load_prompt.call_args_list]
        assert "multi_perspective_section.txt" in load_calls


# ---------------------------------------------------------------------------
# _run_perspectives tests
# ---------------------------------------------------------------------------


class TestRunPerspectives:
    async def test_runs_three_perspectives(self, succinic_acid, sample_patent_hit, mock_settings):
        """Should run all three perspective agents in parallel."""
        from praviar_pipeline.pipeline.step4_analyze import _run_perspectives

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
        mock_claude.load_prompt.return_value = "You are an expert."

        # Mock the research method to return findings
        mock_research = AsyncMock(
            return_value=(
                "The patent claims cover the target compound.",
                MagicMock(total_input_tokens=100, total_output_tokens=50),
            )
        )

        # Mock claude.complete for structured extraction
        mock_claude.complete = AsyncMock(
            return_value=(
                PerspectiveAnalysis(
                    perspective=PerspectiveType.PATENT_ATTORNEY,
                    key_findings=["Test finding"],
                    risk_assessment="Test assessment",
                    confidence=0.8,
                    recommended_risk_level=RiskLevel.MEDIUM,
                ),
                {"input_tokens": 50, "output_tokens": 25},
            )
        )

        base_analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Test patent",
            risk_level=RiskLevel.MEDIUM,
            risk_summary="Test summary",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[],
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.9,
                ),
            ],
        )

        with patch("praviar_pipeline.agents.perspective.PerspectiveAgent") as mock_agent:
            instance = AsyncMock()
            instance.research = mock_research
            mock_agent.return_value = instance

            results = await _run_perspectives(
                claude=mock_claude,
                patent=sample_patent_hit,
                compound=succinic_acid,
                base_analysis=base_analysis,
                compound_ctx="compound context",
                patent_ctx="patent context",
            )

        assert len(results) == 3
        # PerspectiveAgent should have been instantiated 3 times (one per perspective)
        assert mock_agent.call_count == 3

    async def test_graceful_failure(self, succinic_acid, sample_patent_hit, mock_settings):
        """If a perspective agent fails, it should return a fallback PerspectiveAnalysis."""
        from praviar_pipeline.pipeline.step4_analyze import _run_perspectives

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
        mock_claude.load_prompt.return_value = "You are an expert."

        base_analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Test patent",
            risk_level=RiskLevel.MEDIUM,
            risk_summary="Test summary",
            claims_analyzed=[],
        )

        with patch("praviar_pipeline.agents.perspective.PerspectiveAgent") as mock_agent:
            instance = AsyncMock()
            instance.research = AsyncMock(side_effect=RuntimeError("Agent crashed"))
            mock_agent.return_value = instance

            results = await _run_perspectives(
                claude=mock_claude,
                patent=sample_patent_hit,
                compound=succinic_acid,
                base_analysis=base_analysis,
                compound_ctx="compound context",
                patent_ctx="patent context",
            )

        assert len(results) == 3
        for r in results:
            assert r.confidence == 0.0
            assert "failed" in r.key_findings[0].lower()


# ---------------------------------------------------------------------------
# _synthesize_perspectives tests
# ---------------------------------------------------------------------------


class TestSynthesizePerspectives:
    async def test_basic_synthesis(self, mock_settings):
        from praviar_pipeline.pipeline.step4_analyze import _synthesize_perspectives

        mock_claude = make_claude_client_mock()

        synthesis_result = MultiPerspectiveSynthesis(
            synthesized_risk=RiskLevel.MEDIUM,
            disagreements=["Attorney vs. Chemist on structural overlap"],
            synthesis_reasoning="Weighted assessment favoring attorney perspective",
        )
        mock_claude.load_prompt.return_value = "You are a synthesis expert."
        mock_claude.complete = AsyncMock(
            return_value=(
                synthesis_result,
                {"input_tokens": 200, "output_tokens": 100},
            )
        )

        perspectives = [
            PerspectiveAnalysis(
                perspective=PerspectiveType.PATENT_ATTORNEY,
                key_findings=["Broad genus claim covers target"],
                risk_assessment="High risk",
                confidence=0.9,
                recommended_risk_level=RiskLevel.HIGH,
            ),
            PerspectiveAnalysis(
                perspective=PerspectiveType.MEDICINAL_CHEMIST,
                key_findings=["Low structural similarity"],
                risk_assessment="Low risk",
                confidence=0.7,
                recommended_risk_level=RiskLevel.LOW,
            ),
            PerspectiveAnalysis(
                perspective=PerspectiveType.BUSINESS_ANALYST,
                key_findings=["Aggressive enforcer"],
                risk_assessment="Medium risk",
                confidence=0.6,
                recommended_risk_level=RiskLevel.MEDIUM,
            ),
        ]

        base_analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Test patent",
            risk_level=RiskLevel.MEDIUM,
            risk_summary="Test",
        )

        result = await _synthesize_perspectives(mock_claude, perspectives, base_analysis)

        assert result.synthesized_risk == RiskLevel.MEDIUM
        assert len(result.disagreements) == 1
        # The perspectives list should be set to the input perspectives
        assert len(result.perspectives) == 3

    async def test_synthesis_calls_load_prompt(self, mock_settings):
        from praviar_pipeline.pipeline.step4_analyze import _synthesize_perspectives

        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "synthesis prompt"
        mock_claude.complete = AsyncMock(
            return_value=(
                MultiPerspectiveSynthesis(synthesized_risk=RiskLevel.LOW),
                {"input_tokens": 100, "output_tokens": 50},
            )
        )

        base_analysis = PatentAnalysis(
            patent_id="US1234B2",
            risk_level=RiskLevel.LOW,
            risk_summary="Test",
        )

        await _synthesize_perspectives(mock_claude, [], base_analysis)
        mock_claude.load_prompt.assert_called_once_with("perspective_synthesis_system.txt")


# ---------------------------------------------------------------------------
# PerspectiveAgent tests
# ---------------------------------------------------------------------------


class TestPerspectiveAgent:
    def test_agent_type(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "patent_attorney")
        assert agent.agent_type == "perspective_patent_attorney"

    def test_model_id_uses_analysis_model(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "medicinal_chemist")
        # Should use the analysis model (Sonnet), not the deep model (Opus)
        from praviar_pipeline.config import get_settings

        assert agent.model_id == get_settings().claude_analysis_model

    def test_prompt_file(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "business_analyst")
        assert agent.prompt_file == "perspective_business_analyst_system.txt"

    def test_max_rounds(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "patent_attorney")
        assert agent.max_rounds == 3

    def test_format_task(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "patent_attorney")
        context = {
            "compound_context": "Succinic acid",
            "patent_context": "US7851188B2 claims",
            "base_analysis_summary": "Medium risk",
        }
        result = agent.format_task("Analyze FTO risk", context)
        assert "Analyze FTO risk" in result
        assert 'type="compound_context"' in result
        assert "Succinic acid" in result
        assert 'type="patent_context"' in result
        assert 'type="prior_model_analysis"' in result

    def test_build_toolkit_with_patent_data(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "patent_attorney")
        context = {
            "patent_data": {"US1234B2": {"patent_id": "US1234B2", "title": "Test"}},
        }
        toolkit = agent.build_toolkit(context)
        assert toolkit is not None

    def test_build_toolkit_without_patent_data(self, mock_settings):
        from praviar_pipeline.agents.perspective import PerspectiveAgent

        mock_claude = make_claude_client_mock()
        agent = PerspectiveAgent(mock_claude, "patent_attorney")
        toolkit = agent.build_toolkit({})
        assert toolkit is None


# ---------------------------------------------------------------------------
# Prompt file existence tests
# ---------------------------------------------------------------------------


class TestPromptFilesExist:
    def test_multi_perspective_section_exists(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        assert (prompts_dir / "multi_perspective_section.txt").exists()

    def test_patent_attorney_prompt_exists(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        assert (prompts_dir / "perspective_patent_attorney_system.txt").exists()

    def test_medicinal_chemist_prompt_exists(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        assert (prompts_dir / "perspective_medicinal_chemist_system.txt").exists()

    def test_business_analyst_prompt_exists(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        assert (prompts_dir / "perspective_business_analyst_system.txt").exists()

    def test_synthesis_prompt_exists(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        assert (prompts_dir / "perspective_synthesis_system.txt").exists()

    def test_prompts_are_non_empty(self):
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "src" / "praviar_pipeline" / "prompts"
        for name in [
            "multi_perspective_section.txt",
            "perspective_patent_attorney_system.txt",
            "perspective_medicinal_chemist_system.txt",
            "perspective_business_analyst_system.txt",
            "perspective_synthesis_system.txt",
        ]:
            content = (prompts_dir / name).read_text()
            assert len(content) > 100, f"{name} is too short ({len(content)} chars)"
