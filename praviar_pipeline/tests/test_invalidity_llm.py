from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityLLMResponse,
    PriorArtReference,
    PTABResult,
)
from praviar_pipeline.pipeline.invalidity.llm import assess_invalidity_llm_impl


@pytest.mark.asyncio
async def test_assess_invalidity_llm_impl_builds_prompt_and_computes_confidence(
    succinic_acid,
):
    analysis = PatentAnalysis(
        patent_id="US1234567B2",
        title="Fermentation process",
        assignee="Praviar",
        risk_level=RiskLevel.HIGH,
        risk_summary="Blocking",
    )
    prior_art = [
        PriorArtReference(
            reference_id="Lee2005",
            title="Succinic acid fermentation",
            source_database="pubmed",
            reference_type="journal_article",
        )
    ]
    ptab = PTABResult(has_been_challenged=False)

    claude = MagicMock()
    claude._models = SimpleNamespace(analysis="claude-sonnet-4-6")
    argument = InvalidityArgument(
        type="obviousness",
        statute="35 U.S.C. § 103",
        strength="moderate",
        key_evidence=["Lee2005"],
        reasoning="Lee2005 supplies the missing fermentation teaching.",
    )
    claude.complete = AsyncMock(
        return_value=(
            InvalidityLLMResponse(
                arguments=[argument],
                overall_strength="moderate",
                overall_reasoning="Moderate invalidity case",
                written_description_issues=["Support gap"],
            ),
            {"input_tokens": 120, "output_tokens": 45},
        )
    )

    build_prompt_fn = MagicMock(return_value="assembled prompt")
    compute_confidence_fn = MagicMock(return_value=(0.76, "moderate"))
    settings_factory = MagicMock(return_value=SimpleNamespace(invalidity_max_tokens=2048))

    result = await assess_invalidity_llm_impl(
        claude,
        analysis,
        succinic_acid,
        ptab,
        "system prompt",
        prior_art=prior_art,
        examiner_citations={"examiner": ["US7654321"]},
        settings_factory=settings_factory,
        build_prompt_fn=build_prompt_fn,
        compute_confidence_fn=compute_confidence_fn,
    )

    build_prompt_fn.assert_called_once()
    compute_confidence_fn.assert_called_once()
    claude.complete.assert_awaited_once_with(
        system="system prompt",
        user="assembled prompt",
        response_model=InvalidityLLMResponse,
        model="claude-sonnet-4-6",
        max_tokens=2048,
        cache_system=True,
        role="invalidity",
    )
    assert result[0] == [argument]
    assert result[1] == ["Support gap"]
    assert result[3] == 0.76
    assert result[4] == "moderate"
    assert result[5] == "moderate"
    assert result[9] == {"input_tokens": 120, "output_tokens": 45}
