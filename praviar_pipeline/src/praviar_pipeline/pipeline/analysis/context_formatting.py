"""Context-formatting helpers for Step 4 analysis prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.utils.formatting import format_compound_context, format_patent_context

if TYPE_CHECKING:
    from collections.abc import Callable


def format_patent_for_analysis(patent, triage) -> str:
    """Format patent details for adaptive claim analysis."""
    patent_context = format_patent_context(patent, triage=triage)
    if triage and getattr(triage, "reason", ""):
        return f"{patent_context}\n\nTriage rationale: {triage.reason}"
    return patent_context


def format_compound_for_analysis(
    compound,
    *,
    get_settings_fn: Callable = get_settings,
) -> str:
    """Format compound details for claim analysis."""
    settings = get_settings_fn()
    return format_compound_context(
        compound,
        include_inchi=True,
        include_weight=True,
        max_synonyms=settings.analysis_context_max_synonyms,
    )
