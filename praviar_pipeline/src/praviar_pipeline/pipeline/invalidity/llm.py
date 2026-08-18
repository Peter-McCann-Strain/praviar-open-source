"""LLM-backed invalidity assessment helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from praviar_pipeline.config import Settings, get_settings
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityLLMResponse,
    PriorArtReference,
)
from praviar_pipeline.pipeline.invalidity.prompting import build_invalidity_prompt
from praviar_pipeline.pipeline.invalidity.scoring import _compute_invalidity_confidence

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.invalidity import PTABResult


InvalidityLlmResult = tuple[
    list[InvalidityArgument],
    list[str],
    str,
    float,
    str,
    str,
    list,
    object | None,
    object | None,
    dict,
]


class _CompletionEffortKwargs(TypedDict):
    effort: NotRequired[str]


async def assess_invalidity_llm_impl(
    claude: ClaudeClient,
    analysis: PatentAnalysis,
    compound: ResolvedCompound,
    ptab: PTABResult,
    system_prompt: str,
    prior_art: list[PriorArtReference] | None = None,
    examiner_citations: dict[str, list[str]] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    *,
    settings_factory: Callable[[], Settings] = get_settings,
    build_prompt_fn: Callable[..., str] = build_invalidity_prompt,
    compute_confidence_fn: Callable[..., tuple[float, str]] = _compute_invalidity_confidence,
) -> InvalidityLlmResult:
    """Run the structured invalidity assessment and normalize its outputs."""
    settings = settings_factory()
    normalized_prior_art = prior_art or []

    user_prompt = build_prompt_fn(
        analysis=analysis,
        compound=compound,
        ptab=ptab,
        prior_art=normalized_prior_art,
        examiner_citations=examiner_citations,
        drawing_evidence=drawing_evidence,
    )

    effort = getattr(settings, "thinking_effort_analysis", None)
    effort_kwargs: _CompletionEffortKwargs = {}
    if effort is not None:
        effort_kwargs["effort"] = effort
    llm_response, usage = await claude.complete(
        system=system_prompt,
        user=user_prompt,
        response_model=InvalidityLLMResponse,
        model=claude._models.analysis,
        max_tokens=settings.invalidity_max_tokens,
        cache_system=True,
        role="invalidity",
        **effort_kwargs,
    )

    confidence, confidence_band = compute_confidence_fn(
        llm_response,
        normalized_prior_art,
        examiner_citations,
        ptab,
    )

    return (
        llm_response.arguments,
        llm_response.written_description_issues,
        llm_response.overall_reasoning,
        confidence,
        llm_response.overall_strength,
        confidence_band,
        llm_response.claim_charts,
        llm_response.graham_factors,
        llm_response.enablement_screening,
        usage,
    )
