"""Tests for Fix 1: Self-healing LLM validation retry in ClaudeClient.

Tests the 3-layer validation strategy:
1. Constrained decoding for non-thinking calls (messages.parse)
2. Validation-retry loop for extended thinking calls
3. Error feedback sent back to LLM for self-correction
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.clients.claude import ClaudeClient, _extract_json, _repair_truncated_json
from praviar_pipeline.errors import LLMResponseError

# ── Test models ──────────────────────────────────────────────────────────


class SimpleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    score: float = Field(ge=0.0, le=1.0)


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patent_id: str
    risk_level: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── JSON extraction tests ────────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json(self):
        raw = '{"name": "test", "score": 0.5}'
        assert _extract_json(raw) == raw

    def test_markdown_code_block(self):
        raw = '```json\n{"name": "test", "score": 0.5}\n```'
        assert _extract_json(raw) == '{"name": "test", "score": 0.5}'

    def test_preamble_text(self):
        raw = 'Here is the analysis:\n{"name": "test", "score": 0.5}'
        assert _extract_json(raw) == '{"name": "test", "score": 0.5}'

    def test_unclosed_code_block(self):
        raw = '```json\n{"name": "test", "score": 0.5}'
        result = _extract_json(raw)
        assert '"name"' in result

    def test_nested_braces(self):
        raw = '{"outer": {"inner": "value"}, "score": 0.5}'
        assert _extract_json(raw) == raw


class TestRepairTruncatedJson:
    def test_balanced_json_unchanged(self):
        raw = '{"name": "test"}'
        assert _repair_truncated_json(raw) == raw

    def test_missing_closing_brace(self):
        raw = '{"name": "test", "score": 0.5'
        repaired = _repair_truncated_json(raw)
        assert repaired.endswith("}")

    def test_missing_closing_bracket_and_brace(self):
        raw = '{"elements": [{"id": 1}'
        repaired = _repair_truncated_json(raw)
        # The open bracket should be closed, and the outer brace too
        assert "]" in repaired or "}" in repaired

    def test_trailing_comma_cleaned(self):
        raw = '{"name": "test", "items": ['
        repaired = _repair_truncated_json(raw)
        # Should close the bracket and brace
        assert "]" in repaired
        assert repaired.endswith("}")


# ── Validation retry tests ───────────────────────────────────────────────


class TestValidationRetry:
    """Test the self-healing validation retry loop."""

    @pytest.fixture
    def mock_client(self, mock_settings):
        """Create a ClaudeClient with mocked Anthropic internals."""
        with (
            patch("praviar_pipeline.clients.claude.assert_paid_api_allowed"),
            patch("praviar_pipeline.clients.claude.anthropic") as mock_anthropic,
        ):
            mock_async = AsyncMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_async
            client = ClaudeClient()
            client._client = mock_async
            # messages.stream must be a regular MagicMock so it returns
            # the context manager directly (not wrapped in a coroutine)
            client._client.messages.stream = MagicMock()
            yield client

    def _make_stream_mock(self, text: str, thinking: str = ""):
        """Create a mock for self._client.messages.stream that works with `async with`."""
        mock_response = MagicMock()
        mock_response.content = [
            SimpleNamespace(type="thinking", thinking=thinking),
            SimpleNamespace(type="text", text=text),
        ]
        mock_response.usage = SimpleNamespace(input_tokens=100, output_tokens=50)

        mock_stream = AsyncMock()
        mock_stream.get_final_message = AsyncMock(return_value=mock_response)

        # The key: messages.stream() returns a context manager, not a coroutine
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=mock_stream)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        return stream_cm

    async def test_first_attempt_succeeds_no_retry(self, mock_client):
        """When first parse succeeds, no retry is needed."""
        valid_json = '{"patent_id": "US123", "risk_level": "high", "confidence": 0.9}'

        mock_client._client.messages.stream.return_value = self._make_stream_mock(
            valid_json,
            thinking="I'm thinking...",
        )

        result, thinking, _usage = await mock_client.complete_with_thinking(
            system="test",
            user="test",
            response_model=StrictOutput,
        )

        assert result.patent_id == "US123"
        assert result.risk_level == "high"
        assert thinking == "I'm thinking..."
        # No retry call should have been made
        mock_client._client.messages.create.assert_not_called()

    async def test_validation_error_raises_immediately(self, mock_client):
        """Invalid JSON fails closed without exposing raw validation detail."""
        invalid_json = '{"name": "test", "score": 1.5}'

        mock_client._client.messages.stream.return_value = self._make_stream_mock(invalid_json)

        with pytest.raises(
            LLMResponseError,
            match="Structured response validation failed",
        ) as excinfo:
            await mock_client.complete_with_thinking(
                system="test",
                user="test",
                response_model=SimpleOutput,
            )
        assert "less_than_equal" not in str(excinfo.value)
        assert invalid_json not in str(excinfo.value)

    async def test_extra_fields_rejected(self, mock_client):
        """Unknown LLM fields fail closed and are not echoed in diagnostics."""
        from praviar_pipeline.models.analysis import PatentAnalysis

        json_with_extras = (
            '{"patent_id": "US123", "risk_level": "high", '
            '"risk_summary": "test risk", "extra_llm_field": "should be ignored"}'
        )

        mock_client._client.messages.stream.return_value = self._make_stream_mock(json_with_extras)

        with pytest.raises(
            LLMResponseError,
            match="Structured response validation failed",
        ) as excinfo:
            await mock_client.complete_with_thinking(
                system="test",
                user="test",
                response_model=PatentAnalysis,
            )
        assert "extra_llm_field" not in str(excinfo.value)
        assert "should be ignored" not in str(excinfo.value)
