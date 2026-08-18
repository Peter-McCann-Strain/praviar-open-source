from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from praviar_pipeline.clients.claude_runtime_completion_helpers import validate_thinking_response
from praviar_pipeline.errors import LLMResponseError


class _SimpleOutput(BaseModel):
    name: str


def test_validate_thinking_response_returns_parsed_model() -> None:
    logger = SimpleNamespace(debug=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)

    parsed = validate_thinking_response(
        response_model=_SimpleOutput,
        result_text='{"name": "example"}',
        thinking_text="reasoning",
        model="claude-test",
        budget_tokens=123,
        logger=logger,
    )

    assert parsed == _SimpleOutput(name="example")


def test_validate_thinking_response_raises_safe_llm_error() -> None:
    logger = SimpleNamespace(debug=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)

    with pytest.raises(LLMResponseError, match="Structured response validation failed"):
        validate_thinking_response(
            response_model=_SimpleOutput,
            result_text='{"missing": "name"}',
            thinking_text="reasoning",
            model="claude-test",
            budget_tokens=123,
            logger=logger,
        )
