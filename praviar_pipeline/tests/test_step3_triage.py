"""Tests for Step 3: LLM Triage — mock the Claude client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    DrawingStructure,
    PatentDrawingAnalysis,
)
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult

from .helpers import make_claude_client_mock


def _patent(pid: str, *, abstract: str = "", claims_text: str = "") -> PatentHit:
    return PatentHit(
        patent_id=pid,
        title=f"Patent {pid}",
        abstract=abstract,
        claims_text=claims_text,
        sources=[PatentSource.PUBCHEM],
    )


def _llm_settings(
    *,
    batch_size: int = 20,
    concurrency: int = 4,
    max_tokens: int = 4096,
) -> SimpleNamespace:
    return SimpleNamespace(
        triage_batch_size=batch_size,
        triage_concurrency=concurrency,
        triage_max_tokens=max_tokens,
    )


def _triage_settings(
    *,
    rollout_state: str = "production",
    evidence_gate_passed: bool = True,
    calibration_config: dict[str, object] | None = None,
) -> SimpleNamespace:
    values: dict[str, object] = {
        "drawing_analysis_rollout_state": rollout_state,
        "drawing_analysis_evidence_gate_passed": evidence_gate_passed,
        "drawing_analysis_jurisdictions": ["US"],
        "triage_max_abstract_chars": 400,
        "triage_max_claims_chars": 800,
        "triage_drawing_auto_relevant_tanimoto": 0.85,
        "triage_drawing_auto_relevant_require_substructure": True,
        "triage_drawing_auto_not_relevant_tanimoto": 0.10,
        "triage_drawing_auto_not_relevant_min_structures": 3,
        "triage_drawing_auto_not_relevant_min_confidence": 0.80,
    }
    values.update(calibration_config or {})
    return SimpleNamespace(**values)


class TestTriagePatents:
    async def test_triage_filters_relevant(self, succinic_acid, sample_patent_hits, mock_settings):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        # Build a properly structured mock claude client
        mock_claude = make_claude_client_mock(
            analysis_model="claude-sonnet-4-6",
            deep_model="claude-opus-4-6",
        )
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."

        # Mock the complete() call to return a TriageBatch
        triage_batch = TriageBatch(
            results=[
                TriageResult(
                    patent_id="US7851188B2",
                    relevance=Relevance.RELEVANT,
                    reason="Directly covers succinic acid production",
                    confidence=0.95,
                ),
                TriageResult(
                    patent_id="US6265190B1",
                    relevance=Relevance.POSSIBLY_RELEVANT,
                    reason="Related purification method",
                    confidence=0.6,
                ),
                TriageResult(
                    patent_id="US9999999B2",
                    relevance=Relevance.NOT_RELEVANT,
                    reason="Unrelated polymer processing",
                    confidence=0.9,
                ),
            ],
            model_used="claude-haiku-4-5-20251001",
            input_tokens=200,
            output_tokens=100,
        )
        mock_claude.complete.return_value = (
            triage_batch,
            {"input_tokens": 200, "output_tokens": 100, "model": "claude-haiku-4-5-20251001"},
        )

        with patch(
            "praviar_pipeline.pipeline.step3_triage.ClaudeClient",
            return_value=mock_claude,
        ):
            results, inp_tokens, out_tokens, failed_count, _all = await triage_patents(
                sample_patent_hits,
                succinic_acid,
            )

        # Only RELEVANT and POSSIBLY_RELEVANT should be returned
        assert len(results) == 2
        assert inp_tokens > 0
        assert out_tokens > 0
        assert failed_count == 0
        relevant_ids = {r.patent_id for r in results}
        assert "US7851188B2" in relevant_ids
        assert "US6265190B1" in relevant_ids
        assert "US9999999B2" not in relevant_ids

    async def test_triage_empty_patents(self, succinic_acid, mock_settings):
        """Triage of empty patent list returns empty."""
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        results, inp_tokens, out_tokens, failed_count, _all = await triage_patents(
            [], succinic_acid
        )
        assert results == []
        assert inp_tokens == 0
        assert out_tokens == 0
        assert failed_count == 0

    async def test_triage_skips_llm_when_auto_filter_classifies_all(
        self,
        succinic_acid,
        verified_calibration_config: dict[str, object],
    ):
        """Drawing-only classifications should not require Claude configuration."""
        from praviar_pipeline.config import get_triage_local_settings
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patent = PatentHit(
            patent_id="US111",
            title="Patent US111",
            sources=[PatentSource.PUBCHEM],
        )
        structure = DrawingStructure(
            patent_id="US111",
            page_number=1,
            structure_index=0,
            canonical_smiles="c1ccccc1",
            confidence=0.95,
            tanimoto_to_target=0.92,
            is_substructure_of_target=True,
            drawing_risk_signal=DrawingRiskLevel.HIGH,
            rdkit_valid=True,
        )
        drawing_evidence = DrawingEvidenceStore(
            DrawingAnalysisResults(
                patent_analyses=[
                    PatentDrawingAnalysis(
                        patent_id="US111",
                        structures_found=1,
                        structures=[structure],
                        highest_tanimoto=0.92,
                        highest_risk_signal=DrawingRiskLevel.HIGH,
                    )
                ]
            )
        )

        clear_settings_cache()
        get_triage_local_settings.cache_clear()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False),
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_triage_local_settings",
                return_value=_triage_settings(
                    rollout_state="production",
                    calibration_config=verified_calibration_config,
                ),
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient") as mock_claude_client,
        ):
            results, inp_tokens, out_tokens, failed_count, all_results = await triage_patents(
                [patent],
                succinic_acid,
                drawing_evidence=drawing_evidence,
            )

        clear_settings_cache()
        get_triage_local_settings.cache_clear()

        mock_claude_client.assert_not_called()
        assert inp_tokens == 0
        assert out_tokens == 0
        assert failed_count == 0
        assert len(results) == 1
        assert len(all_results) == 1
        assert results[0].relevance == Relevance.RELEVANT

    async def test_triage_merges_auto_and_llm_results(
        self,
        succinic_acid,
        mock_settings,
        verified_calibration_config: dict[str, object],
    ):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patent_auto = _patent("US111")
        patent_llm = _patent("US222")
        drawing_evidence = DrawingEvidenceStore(
            DrawingAnalysisResults(
                patent_analyses=[
                    PatentDrawingAnalysis(
                        patent_id="US111",
                        structures_found=1,
                        structures=[
                            DrawingStructure(
                                patent_id="US111",
                                page_number=1,
                                structure_index=0,
                                canonical_smiles="c1ccccc1",
                                confidence=0.95,
                                tanimoto_to_target=0.92,
                                is_substructure_of_target=True,
                                drawing_risk_signal=DrawingRiskLevel.HIGH,
                                rdkit_valid=True,
                            )
                        ],
                        highest_tanimoto=0.92,
                        highest_risk_signal=DrawingRiskLevel.HIGH,
                    )
                ]
            )
        )
        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."
        mock_batch = TriageBatch(
            results=[
                TriageResult(
                    patent_id="US222",
                    relevance=Relevance.RELEVANT,
                    reason="Relevant by LLM",
                    confidence=0.8,
                )
            ],
            model_used="claude-haiku-4-5-20251001",
            input_tokens=120,
            output_tokens=45,
        )
        mock_claude.complete.return_value = (
            mock_batch,
            {"input_tokens": 120, "output_tokens": 45, "model": "claude-haiku-4-5-20251001"},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_settings", return_value=_llm_settings()
            ),
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_triage_local_settings",
                return_value=_triage_settings(
                    rollout_state="production",
                    calibration_config=verified_calibration_config,
                ),
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient", return_value=mock_claude),
        ):
            results, inp_tokens, out_tokens, failed_count, all_results = await triage_patents(
                [patent_auto, patent_llm],
                succinic_acid,
                drawing_evidence=drawing_evidence,
            )

        assert failed_count == 0
        assert inp_tokens == 120
        assert out_tokens == 45
        assert {result.patent_id for result in results} == {"US111", "US222"}
        assert {result.patent_id for result in all_results} == {"US111", "US222"}
        auto_result = next(result for result in all_results if result.patent_id == "US111")
        assert auto_result.drawing_auto_filtered is True

    async def test_shadow_rollout_keeps_drawing_evidence_out_of_triage(
        self, succinic_acid, mock_settings
    ):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patent = _patent("US111")
        drawing_evidence = DrawingEvidenceStore(
            DrawingAnalysisResults(
                patent_analyses=[
                    PatentDrawingAnalysis(
                        patent_id="US111",
                        structures_found=1,
                        structures=[
                            DrawingStructure(
                                patent_id="US111",
                                page_number=1,
                                structure_index=0,
                                canonical_smiles="c1ccccc1",
                                confidence=0.95,
                                tanimoto_to_target=0.92,
                                is_substructure_of_target=True,
                                drawing_risk_signal=DrawingRiskLevel.HIGH,
                                rdkit_valid=True,
                            )
                        ],
                        highest_tanimoto=0.92,
                        highest_risk_signal=DrawingRiskLevel.HIGH,
                    )
                ]
            )
        )
        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."
        mock_claude.complete.return_value = (
            TriageBatch(
                results=[
                    TriageResult(
                        patent_id="US111",
                        relevance=Relevance.RELEVANT,
                        reason="Relevant without drawing evidence",
                        confidence=0.8,
                    )
                ],
                model_used="claude-haiku-4-5-20251001",
                input_tokens=120,
                output_tokens=45,
            ),
            {"input_tokens": 120, "output_tokens": 45, "model": "claude-haiku-4-5-20251001"},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_settings", return_value=_llm_settings()
            ),
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_triage_local_settings",
                return_value=_triage_settings(
                    rollout_state="shadow",
                    evidence_gate_passed=False,
                ),
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient", return_value=mock_claude),
        ):
            results, inp_tokens, out_tokens, failed_count, all_results = await triage_patents(
                [patent],
                succinic_acid,
                drawing_evidence=drawing_evidence,
            )

        mock_claude.complete.assert_awaited_once()
        user_prompt = mock_claude.complete.await_args.kwargs["user"]
        assert "DRAWING EVIDENCE:" not in user_prompt
        assert failed_count == 0
        assert inp_tokens == 120
        assert out_tokens == 45
        assert len(results) == 1
        assert len(all_results) == 1
        assert all_results[0].drawing_auto_filtered is False

    async def test_triage_batch_failure_counts_patents_lost(self, succinic_acid, mock_settings):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patents = [_patent("US111"), _patent("US222"), _patent("US333")]
        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."
        successful_batch = TriageBatch(
            results=[
                TriageResult(
                    patent_id="US111",
                    relevance=Relevance.RELEVANT,
                    reason="Relevant",
                    confidence=0.9,
                ),
                TriageResult(
                    patent_id="US222",
                    relevance=Relevance.NOT_RELEVANT,
                    reason="Not relevant",
                    confidence=0.9,
                ),
            ],
            model_used="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        mock_claude.complete.side_effect = [
            (
                successful_batch,
                {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5-20251001"},
            ),
            RuntimeError("boom"),
        ]

        with (
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_settings",
                return_value=_llm_settings(batch_size=2, concurrency=1),
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient", return_value=mock_claude),
        ):
            results, inp_tokens, out_tokens, failed_count, all_results = await triage_patents(
                patents,
                succinic_acid,
            )

        assert failed_count == 1
        assert inp_tokens == 100
        assert out_tokens == 50
        assert {result.patent_id for result in all_results} == {"US111", "US222", "US333"}
        unknown = next(result for result in all_results if result.patent_id == "US333")
        assert unknown.relevance == Relevance.UNKNOWN
        assert {result.patent_id for result in results} == {"US111", "US333"}

    async def test_triage_drops_unknown_patent_ids(self, succinic_acid, mock_settings):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patents = [_patent("US111")]
        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."
        mock_batch = TriageBatch(
            results=[
                TriageResult(
                    patent_id="US111",
                    relevance=Relevance.RELEVANT,
                    reason="Known patent",
                    confidence=0.9,
                ),
                TriageResult(
                    patent_id="US999",
                    relevance=Relevance.RELEVANT,
                    reason="Hallucinated patent",
                    confidence=0.7,
                ),
            ],
            model_used="claude-haiku-4-5-20251001",
            input_tokens=80,
            output_tokens=40,
        )
        mock_claude.complete.return_value = (
            mock_batch,
            {"input_tokens": 80, "output_tokens": 40, "model": "claude-haiku-4-5-20251001"},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_settings", return_value=_llm_settings()
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient", return_value=mock_claude),
        ):
            results, _inp_tokens, _out_tokens, failed_count, all_results = await triage_patents(
                patents,
                succinic_acid,
            )

        assert failed_count == 0
        assert {result.patent_id for result in all_results} == {"US111"}
        assert {result.patent_id for result in results} == {"US111"}

    async def test_triage_aggregates_tokens_across_multiple_batches(
        self, succinic_acid, mock_settings
    ):
        from praviar_pipeline.pipeline.step3_triage import triage_patents

        patents = [_patent("US111"), _patent("US222")]
        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a patent triage assistant."
        mock_claude.complete.side_effect = [
            (
                TriageBatch(
                    results=[
                        TriageResult(
                            patent_id="US111",
                            relevance=Relevance.RELEVANT,
                            reason="Relevant",
                            confidence=0.9,
                        )
                    ],
                    model_used="claude-haiku-4-5-20251001",
                    input_tokens=100,
                    output_tokens=40,
                ),
                {"input_tokens": 100, "output_tokens": 40, "model": "claude-haiku-4-5-20251001"},
            ),
            (
                TriageBatch(
                    results=[
                        TriageResult(
                            patent_id="US222",
                            relevance=Relevance.POSSIBLY_RELEVANT,
                            reason="Possibly relevant",
                            confidence=0.7,
                        )
                    ],
                    model_used="claude-haiku-4-5-20251001",
                    input_tokens=150,
                    output_tokens=60,
                ),
                {"input_tokens": 150, "output_tokens": 60, "model": "claude-haiku-4-5-20251001"},
            ),
        ]

        with (
            patch(
                "praviar_pipeline.pipeline.step3_triage.get_settings",
                return_value=_llm_settings(batch_size=1, concurrency=1),
            ),
            patch("praviar_pipeline.pipeline.step3_triage.ClaudeClient", return_value=mock_claude),
        ):
            results, inp_tokens, out_tokens, failed_count, all_results = await triage_patents(
                patents,
                succinic_acid,
            )

        assert failed_count == 0
        assert inp_tokens == 250
        assert out_tokens == 100
        assert {result.patent_id for result in all_results} == {"US111", "US222"}
        assert {result.patent_id for result in results} == {"US111", "US222"}


class TestTriagePrompt:
    def test_prompt_includes_few_shot_examples(self):
        """Verify the triage prompt has been upgraded with <example> tags."""
        from praviar_pipeline.clients.claude import _load_prompt

        prompt = _load_prompt("triage_system.txt")
        assert "<example>" in prompt
        assert "</example>" in prompt
        # Should have at least 2 examples (positive + negative)
        assert prompt.count("<example") >= 2

    def test_prompt_includes_chain_of_thought(self):
        from praviar_pipeline.clients.claude import _load_prompt

        prompt = _load_prompt("triage_system.txt")
        assert "reason through" in prompt.lower()
