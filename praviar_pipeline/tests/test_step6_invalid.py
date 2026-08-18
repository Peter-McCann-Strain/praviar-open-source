"""Tests for Step 6: Patent Invalidity Analysis — structured output + scholarly search."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityLLMResponse,
    PTABProceeding,
    PTABResult,
)


class TestInvalidityStructuredOutput:
    async def test_assess_invalidity_uses_structured_output(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Verify step 6 uses complete() with InvalidityLLMResponse, not complete_text()."""
        from praviar_pipeline.pipeline.step6_invalid import assess_invalidity

        blocking_analysis = PatentAnalysis(
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

        llm_response = InvalidityLLMResponse(
            arguments=[
                InvalidityArgument(
                    type="anticipation",
                    statute="35 U.S.C. § 102",
                    strength="moderate",
                    key_evidence=["Lee et al. (2005)"],
                    reasoning="Prior art shows similar fermentation process",
                ),
            ],
            overall_strength="moderate",
            overall_reasoning="Moderate invalidity case based on prior art",
            written_description_issues=["Broad genus claim may lack support"],
        )

        mock_claude = MagicMock()
        mock_claude.load_prompt.return_value = "You are a patent attorney."
        mock_claude.complete = AsyncMock()
        mock_claude.complete_text = MagicMock()
        mock_claude._models = SimpleNamespace(
            triage="claude-haiku-4-5-20251001",
            analysis="claude-sonnet-4-6",
            deep="claude-opus-4-6",
        )
        mock_claude.complete.return_value = (
            llm_response,
            {"input_tokens": 400, "output_tokens": 200, "model": "claude-sonnet-4-6"},
        )
        mock_claude.__aenter__ = AsyncMock(return_value=mock_claude)
        mock_claude.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.pipeline.step6_invalid.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid._check_ptab",
                return_value=PTABResult(has_been_challenged=False),
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid._search_scholarly_prior_art",
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid.BigQueryClient",
            ) as mock_bq_cls,
        ):
            mock_bq = MagicMock()
            mock_bq.get_examiner_citations_batch = AsyncMock(return_value={})
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            results, inp_tokens, out_tokens = await assess_invalidity(
                [blocking_analysis],
                succinic_acid,
            )

        assert len(results) == 1
        assert results[0].overall_invalidity_strength == "weak"
        assert results[0].written_description_issues == ["Broad genus claim may lack support"]
        assert "Moderate invalidity case" in results[0].reasoning
        assert inp_tokens > 0
        assert out_tokens > 0

        # Verify complete() was called (not complete_text())
        mock_claude.complete.assert_called_once()
        assert not mock_claude.complete_text.called

    async def test_evidence_quantity_does_not_override_ground_strength(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Verified effective cancellations are the only current strong deterministic signal."""
        from praviar_pipeline.pipeline.step6_invalid import assess_invalidity

        blocking_analysis = PatentAnalysis(
            patent_id="US7851188B2",
            title="Methods for producing succinic acid",
            assignee="BioAmber Inc.",
            claims_analyzed=[],
            risk_level=RiskLevel.HIGH,
            risk_summary="Blocking",
        )

        llm_response = InvalidityLLMResponse(
            arguments=[],
            overall_strength="weak",
            overall_reasoning="LLM underestimates",
        )

        mock_claude = MagicMock()
        mock_claude.load_prompt.return_value = "You are a patent attorney."
        mock_claude.complete = AsyncMock()
        mock_claude.complete_text = MagicMock()
        mock_claude._models = SimpleNamespace(
            triage="claude-haiku-4-5-20251001",
            analysis="claude-sonnet-4-6",
            deep="claude-opus-4-6",
        )
        mock_claude.complete.return_value = (
            llm_response,
            {"input_tokens": 400, "output_tokens": 200, "model": "claude-sonnet-4-6"},
        )
        mock_claude.__aenter__ = AsyncMock(return_value=mock_claude)
        mock_claude.__aexit__ = AsyncMock(return_value=False)

        # Even an asserted cancellation list cannot manufacture a merits score.
        ptab_result = PTABResult(
            has_been_challenged=True,
            proceedings=[
                PTABProceeding(
                    proceeding_number="IPR2025-00001",
                    type="IPR",
                    status="Final Written Decision",
                    claims_reported_cancelled=[1, 3],
                    claims_cancelled=[1, 3],
                    final_written_decision_verified=True,
                    cancellation_certificate_verified=True,
                    review_and_appeal_posture="Appeal period exhausted",
                )
            ],
            all_claims_cancelled=[1, 3],
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step6_invalid.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid._check_ptab",
                return_value=ptab_result,
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid._search_scholarly_prior_art",
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step6_invalid.BigQueryClient",
            ) as mock_bq_cls,
        ):
            mock_bq = MagicMock()
            mock_bq.get_examiner_citations_batch = AsyncMock(return_value={})
            mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
            mock_bq.__aexit__ = AsyncMock(return_value=False)
            mock_bq_cls.return_value = mock_bq

            results, _, _ = await assess_invalidity(
                [blocking_analysis],
                succinic_acid,
            )

        assert results[0].overall_invalidity_strength == "strong"
