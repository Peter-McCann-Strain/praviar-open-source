"""Tests for Step 4: Deep Claim Analysis — extended thinking + evaluator pass."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import LLMResponseError
from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    EvaluationIssue,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.pipeline.step4_analyze import _apply_evaluation_fixes

from .helpers import make_claude_client_mock


class TestExtendedThinking:
    async def test_analyze_uses_complete_with_thinking(
        self,
        succinic_acid,
        sample_patent_hits,
        sample_triage_results,
        mock_settings,
    ):
        from praviar_pipeline.pipeline.step4_analyze import analyze_patents

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Methods for producing succinic acid",
            assignee="BioAmber Inc.",
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

        # Mock complete_with_thinking (for deep analysis)
        mock_claude.complete_with_thinking.return_value = (
            analysis,
            "This is the thinking text from extended thinking...",
            {"input_tokens": 500, "output_tokens": 300, "model": "claude-opus-4-6"},
        )
        # Mock complete (for evaluator)
        evaluation = AnalysisEvaluation(
            issues=[],
            overall_quality="good",
        )
        mock_claude.complete.return_value = (
            evaluation,
            {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5-20251001"},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step4_analyze.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step4_analyze.BigQueryClient",
            ) as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.close = AsyncMock()
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            patents = sample_patent_hits[:1]
            analyses, failures, _traces = await analyze_patents(
                patents,
                succinic_acid,
                triage_results=[],
            )

        assert len(analyses) == 1
        assert len(failures) == 0
        # Verify complete_with_thinking was called (not complete for analysis)
        mock_claude.complete_with_thinking.assert_called()
        assert analyses[0].thinking_text == "This is the thinking text from extended thinking..."


class TestEvaluator:
    async def test_evaluator_catches_risk_claim_mismatch(
        self,
        succinic_acid,
        sample_patent_hits,
        sample_triage_results,
        mock_settings,
    ):
        """If analysis says HIGH but all claims are NOT_MET, evaluator should fix."""
        from praviar_pipeline.pipeline.step4_analyze import analyze_patents

        mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
        mock_claude.load_prompt.return_value = "You are a patent attorney."

        # Analysis with inconsistency: HIGH risk but no elements met
        inconsistent_analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Methods for producing succinic acid",
            assignee="BioAmber Inc.",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="using Mannheimia",
                            status=ElementStatus.NOT_MET,
                            reasoning="Uses E. coli",
                            confidence=0.9,
                        ),
                    ],
                    overall_status=ElementStatus.NOT_MET,
                    overall_confidence=0.9,
                ),
            ],
            risk_level=RiskLevel.HIGH,  # Inconsistent!
            risk_summary="Marked high but no elements met",
        )

        mock_claude.complete_with_thinking.return_value = (
            inconsistent_analysis,
            "thinking...",
            {"input_tokens": 500, "output_tokens": 300, "model": "claude-opus-4-6"},
        )

        # Evaluator catches the mismatch
        evaluation = AnalysisEvaluation(
            issues=[
                EvaluationIssue(
                    issue_type="risk_claim_mismatch",
                    description="HIGH risk but no claim elements met",
                    suggested_fix="Change risk to CLEAR or LOW",
                    severity="critical",
                ),
            ],
            overall_quality="needs_revision",
            revised_risk_level="low",
        )
        mock_claude.complete.return_value = (
            evaluation,
            {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5-20251001"},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step4_analyze.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step4_analyze.BigQueryClient",
            ) as mock_bq_cls,
        ):
            mock_bq = AsyncMock()
            mock_bq.get_patent_claims_batch.return_value = {}
            mock_bq.close = AsyncMock()
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            patents = sample_patent_hits[:1]
            analyses, failures, _traces = await analyze_patents(
                patents,
                succinic_acid,
                triage_results=[],
            )

        # Evaluator should have corrected HIGH → LOW
        assert len(failures) == 0
        assert analyses[0].risk_level == RiskLevel.LOW

    def test_apply_evaluation_fixes_corrects_risk(self, sample_analysis):
        evaluation = AnalysisEvaluation(
            issues=[],
            overall_quality="needs_revision",
            revised_risk_level="low",
        )
        fixed = _apply_evaluation_fixes(sample_analysis, evaluation)
        assert fixed.risk_level == RiskLevel.LOW

    def test_apply_evaluation_fixes_clamps_below_deterministic_floor(self):
        analysis = PatentAnalysis(
            patent_id="US123456B2",
            title="Ambiguous formulation claim",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="a GLP-1 analogue",
                            status=ElementStatus.UNCLEAR,
                            reasoning="Source evidence is ambiguous",
                            confidence=0.5,
                        )
                    ],
                    overall_status=ElementStatus.UNCLEAR,
                    overall_confidence=0.5,
                )
            ],
            risk_level=RiskLevel.HIGH,
            risk_summary="Ambiguous claim evidence.",
        )
        evaluation = AnalysisEvaluation(
            issues=[],
            overall_quality="needs_revision",
            revised_risk_level="clear",
        )

        fixed = _apply_evaluation_fixes(analysis, evaluation)

        assert fixed.risk_level == RiskLevel.MEDIUM

    def test_apply_evaluation_fixes_invalid_risk_fails_loud(self, sample_analysis):
        """An unrecognised revised risk level must raise at parse time.

        The evaluator's revised risk level is written straight onto the
        analysis, so a silent default would let the silent-zero defect slip
        through. The bad value must fail loud rather than being ignored.
        """
        with pytest.raises(LLMResponseError):
            AnalysisEvaluation(
                issues=[],
                overall_quality="needs_revision",
                revised_risk_level="unknown_value",
            )

    def test_apply_evaluation_fixes_no_revision(self, sample_analysis):
        evaluation = AnalysisEvaluation(
            issues=[],
            overall_quality="good",
            revised_risk_level=None,
        )
        original_risk = sample_analysis.risk_level
        fixed = _apply_evaluation_fixes(sample_analysis, evaluation)
        assert fixed.risk_level == original_risk
