"""Small model helpers for Praviar Pipeline settings."""

from __future__ import annotations

from pydantic import BaseModel


class ClaudeModels(BaseModel):
    """Claude model identifiers for each pipeline role."""

    triage: str
    analysis: str
    deep: str


def build_claude_models(settings) -> ClaudeModels:
    """Build the normalized Claude model bundle from Settings."""
    return ClaudeModels(
        triage=settings.claude_triage_model,
        analysis=settings.claude_analysis_model,
        deep=settings.claude_deep_model,
    )
