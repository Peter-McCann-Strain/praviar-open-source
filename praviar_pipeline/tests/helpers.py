"""Shared test helpers for Praviar Pipeline tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import create_autospec

from praviar_pipeline.clients.claude import ClaudeClient


def make_claude_client_mock(
    *,
    triage_model: str = "claude-haiku-4-5-20251001",
    analysis_model: str = "claude-sonnet-4-6",
    deep_model: str = "claude-sonnet-4-6",
) -> ClaudeClient:
    """Create a ClaudeClient test double with sync and async methods typed correctly."""
    mock_client = create_autospec(ClaudeClient, instance=True)
    mock_client._models = SimpleNamespace(
        triage=triage_model,
        analysis=analysis_model,
        deep=deep_model,
    )
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    return mock_client
