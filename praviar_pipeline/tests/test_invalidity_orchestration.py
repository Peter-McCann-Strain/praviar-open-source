from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import GoogleAPIError

from praviar_pipeline.errors import InvalidityAssessmentError, SourceUnavailableError
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityLLMResponse,
    PriorArtReference,
    PTABResult,
)
from praviar_pipeline.pipeline.invalidity.llm import assess_invalidity_llm_impl
from praviar_pipeline.pipeline.invalidity.orchestration import (
    aggregate_invalidity_results,
    fetch_examiner_citations,
    process_single_patent,
)


def _client_ctx(client):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


@pytest.mark.asyncio
async def test_process_single_patent_keeps_prior_art_separate_from_llm_arguments(
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
    argument = InvalidityArgument(
        type="obviousness",
        statute="35 U.S.C. § 103",
        strength="moderate",
        key_evidence=["Lee2005"],
        reasoning="Lee2005 supplies the missing fermentation teaching.",
    )
    claude = MagicMock()
    claude._models = SimpleNamespace(analysis="claude-sonnet-4-6")
    claude.complete = AsyncMock(
        return_value=(
            InvalidityLLMResponse(
                arguments=[argument],
                overall_strength="moderate",
                overall_reasoning="Moderate invalidity case",
            ),
            {"input_tokens": 120, "output_tokens": 45},
        )
    )

    async def assessor(*args, **kwargs):
        return await assess_invalidity_llm_impl(
            *args,
            **kwargs,
            settings_factory=lambda: SimpleNamespace(invalidity_max_tokens=2048),
            build_prompt_fn=lambda **_kwargs: "assembled prompt",
            compute_confidence_fn=lambda *_args: (0.76, "MODERATE"),
        )

    assessment, input_tokens, output_tokens = await process_single_patent(
        analysis,
        semaphore=asyncio.Semaphore(1),
        claude=claude,
        system_prompt="system prompt",
        compound=succinic_acid,
        priority_dates={},
        citations_map={},
        drawing_evidence=None,
        ptab_checker=AsyncMock(return_value=PTABResult()),
        prior_art_searcher=AsyncMock(return_value=prior_art),
        llm_assessor=assessor,
        strength_chooser=lambda strength, _prior_art, _ptab: strength,
    )

    assert assessment.prior_art == prior_art
    assert assessment.arguments == [argument]
    assert (input_tokens, output_tokens) == (120, 45)


@pytest.mark.asyncio
async def test_fetch_examiner_citations_fails_closed_on_fetch_error():
    logger = MagicMock()
    client = AsyncMock()
    sentinel = "examiner-credential-sentinel-must-not-escape"
    client.get_examiner_citations_batch.side_effect = GoogleAPIError(
        f"https://bigquery.example.invalid?access_token={sentinel}"
    )

    with pytest.raises(SourceUnavailableError) as exc_info:
        await fetch_examiner_citations(
            [
                PatentAnalysis(
                    patent_id="US1234567B2",
                    title="Patent",
                    assignee="Praviar",
                    risk_level=RiskLevel.HIGH,
                    risk_summary="Blocking",
                )
            ],
            client_factory=_client_ctx(client),
            logger=logger,
        )

    logger.error.assert_called_once()
    assert logger.error.call_args.kwargs["error_type"] == "GoogleAPIError"
    assert "error" not in logger.error.call_args.kwargs
    assert "exc_info" not in logger.error.call_args.kwargs
    assert sentinel not in repr((logger.error.call_args.args, logger.error.call_args.kwargs))
    assert str(exc_info.value) == ("examiner_citations unavailable: examiner citation fetch failed")
    assert sentinel not in str(exc_info.value)
    assert sentinel not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_aggregate_invalidity_results_fails_closed_on_patent_failure():
    """One patent failure invalidates the complete blocking-patent assessment set."""
    logger = MagicMock()
    assessment = MagicMock()
    assessment.ptab.has_been_challenged = True
    assessment.prior_art = ["Lee2005"]
    assessment.overall_invalidity_strength = "strong"

    results = [
        (assessment, 120, 45),
        RuntimeError("secret-token-must-not-escape"),
        (assessment, 30, 10),
    ]

    with pytest.raises(InvalidityAssessmentError) as exc_info:
        aggregate_invalidity_results(
            results,
            compound_name="succinic acid",
            logger=logger,
        )

    logger.warning.assert_called()
    for call in logger.warning.call_args_list:
        assert call.kwargs.get("error") is None
        assert "exc_info" not in call.kwargs
        assert "secret-token-must-not-escape" not in repr((call.args, call.kwargs))
    assert str(exc_info.value) == "Invalidity assessment failed"
    assert exc_info.value.failure_types == ("RuntimeError",)
    assert "secret-token-must-not-escape" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_aggregate_invalidity_results_raises_when_all_fail():
    """Raises the first exception only when every patent failed."""
    logger = MagicMock()

    results = [RuntimeError("boom"), ValueError("other")]

    with pytest.raises(InvalidityAssessmentError) as exc_info:
        aggregate_invalidity_results(
            results,
            compound_name="succinic acid",
            logger=logger,
        )

    assert exc_info.value.failure_types == ("RuntimeError", "ValueError")
    assert "boom" not in str(exc_info.value)
    assert "other" not in repr(exc_info.value)
