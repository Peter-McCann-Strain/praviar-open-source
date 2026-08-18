"""Tests for Fix 8: Failed patent tracking in Step 4 (analyze_patents).

Tests that analyze_patents returns (analyses, failures) instead of
silently dropping failed patents.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.pipeline.step4_analyze import analyze_patents

from .helpers import make_claude_client_mock


class TestAnalyzePatentsFailureTracking:
    """Test that failed patents are tracked, not silently dropped."""

    async def test_returns_tuple_of_analyses_and_failures(
        self,
        succinic_acid,
        sample_patent_hits,
        mock_settings,
    ):
        """Even on success, the return type is (analyses, failures)."""
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="test",
            risk_level=RiskLevel.LOW,
            risk_summary="low risk",
        )
        mock_claude.complete_with_thinking.return_value = (
            analysis,
            "thinking",
            {"input_tokens": 100, "output_tokens": 50, "model": "test"},
        )
        evaluation = AnalysisEvaluation(issues=[], overall_quality="good", revised_risk_level=None)
        mock_claude.complete.return_value = (
            evaluation,
            {"input_tokens": 50, "output_tokens": 25, "model": "test"},
        )

        with (
            patch("praviar_pipeline.pipeline.step4_analyze.ClaudeClient", return_value=mock_claude),
            patch("praviar_pipeline.pipeline.step4_analyze.BigQueryClient") as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            result = await analyze_patents(
                sample_patent_hits[:1],
                succinic_acid,
            )

        assert isinstance(result, tuple)
        analyses, failures, _traces = result
        assert len(analyses) == 1
        assert len(failures) == 0

    async def test_empty_patents_returns_empty_tuple(self, succinic_acid):
        """Empty input returns ([], [])."""
        analyses, failures, _traces = await analyze_patents([], succinic_acid)
        assert analyses == []
        assert failures == []

    async def test_failure_creates_analysis_failure_record(
        self,
        succinic_acid,
        sample_patent_hits,
        mock_settings,
    ):
        """When a patent fails analysis, an AnalysisFailure record is created."""
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        # Simulate a failure for the first patent
        sentinel = "analysis-json-customer-claim-sentinel"
        mock_claude.complete_with_thinking.side_effect = ValueError(
            f"JSON parse failed: {sentinel}"
        )

        with (
            patch("praviar_pipeline.pipeline.step4_analyze.ClaudeClient", return_value=mock_claude),
            patch("praviar_pipeline.pipeline.step4_analyze.BigQueryClient") as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            analyses, failures, _traces = await analyze_patents(
                sample_patent_hits[:1],
                succinic_acid,
            )

        assert len(analyses) == 0
        assert len(failures) == 1
        failure = failures[0]
        assert failure.patent_id == "US7851188B2"
        assert failure.step == "step4_analyze"
        assert failure.error_type == "ValueError"
        assert failure.error_message == "patent analysis failed (ValueError)"
        assert sentinel not in failure.model_dump_json()

    async def test_mixed_success_and_failure(
        self,
        succinic_acid,
        sample_patent_hits,
        mock_settings,
    ):
        """Some patents succeed, some fail — both are tracked."""
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        # First call succeeds, second fails
        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="test",
            risk_level=RiskLevel.LOW,
            risk_summary="low risk",
        )
        mock_claude.complete_with_thinking.side_effect = [
            (analysis, "thinking", {"input_tokens": 100, "output_tokens": 50, "model": "test"}),
            ValueError("Parse error on patent 2"),
        ]
        evaluation = AnalysisEvaluation(issues=[], overall_quality="good", revised_risk_level=None)
        mock_claude.complete.return_value = (
            evaluation,
            {"input_tokens": 50, "output_tokens": 25, "model": "test"},
        )

        with (
            patch("praviar_pipeline.pipeline.step4_analyze.ClaudeClient", return_value=mock_claude),
            patch("praviar_pipeline.pipeline.step4_analyze.BigQueryClient") as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            analyses, failures, _traces = await analyze_patents(
                sample_patent_hits[:2],
                succinic_acid,
            )

        assert len(analyses) == 1
        assert len(failures) == 1

    async def test_timeout_marked_recoverable(
        self,
        succinic_acid,
        sample_patent_hits,
        mock_settings,
    ):
        """TimeoutError should be marked as recoverable."""
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a patent attorney."
        mock_claude.complete_with_thinking.side_effect = TimeoutError("Request timed out")

        with (
            patch("praviar_pipeline.pipeline.step4_analyze.ClaudeClient", return_value=mock_claude),
            patch("praviar_pipeline.pipeline.step4_analyze.BigQueryClient") as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            _, failures, _traces = await analyze_patents(
                sample_patent_hits[:1],
                succinic_acid,
            )

        assert len(failures) == 1
        assert failures[0].recoverable is True
