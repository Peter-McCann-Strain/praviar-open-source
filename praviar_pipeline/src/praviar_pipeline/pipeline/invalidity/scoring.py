"""Confidence and strength scoring helpers for invalidity analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings

if TYPE_CHECKING:
    from praviar_pipeline.models.invalidity import (
        InvalidityLLMResponse,
        PriorArtReference,
        PTABResult,
    )


def _compute_invalidity_confidence(
    llm_response: InvalidityLLMResponse,
    prior_art: list[PriorArtReference],
    examiner_citations: dict[str, list[str]] | None,
    ptab: PTABResult,
) -> tuple[float, str]:
    """Compute evidence-grounded confidence for invalidity screening."""
    settings = get_settings()
    score = 0.0

    for chart in llm_response.claim_charts:
        if chart.all_elements_disclosed:
            score += settings.invalidity_weight_prosecution
            break
    else:
        if llm_response.claim_charts:
            score += settings.invalidity_weight_prior_art_exists

    # Evidence volume, examiner citation count, and the existence of a PTAB
    # challenge do not make an invalidity theory stronger or more reliable.
    # Only an independently supported effective cancellation can add PTAB
    # confidence here.
    if ptab.all_claims_cancelled:
        score += settings.invalidity_weight_ptab_success

    if llm_response.graham_factors:
        score += settings.invalidity_weight_narrow_claims

    if llm_response.enablement_screening and (
        llm_response.enablement_screening.genus_claim_detected
        or llm_response.enablement_screening.amgen_v_sanofi_flags
    ):
        score += settings.invalidity_weight_continuation

    score = min(score, settings.invalidity_confidence_cap)
    if score >= settings.invalidity_confidence_high:
        return score, "HIGH"
    if score >= settings.invalidity_confidence_moderate:
        return score, "MODERATE"
    return score, "LOW"


def choose_invalidity_strength(
    llm_strength: str,
    prior_art: list[PriorArtReference],
    ptab: PTABResult,
) -> str:
    """Derive a conservative portfolio signal without trusting an unbound LLM label."""
    del llm_strength, prior_art
    if ptab.all_claims_cancelled:
        return "strong"
    return "weak"
