from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import chat
from api.services.no_paid_api import PaidApiBlockedError, assert_paid_api_allowed


def test_no_paid_api_guard_blocks_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PAID_API", "true")

    with pytest.raises(PaidApiBlockedError, match="NO_PAID_API=true"):
        assert_paid_api_allowed("Anthropic")


@pytest.mark.asyncio
async def test_chat_stream_blocks_live_client_factory_in_no_paid_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_PAID_API", "true")
    prepared = SimpleNamespace(
        conversation_id="conversation-1",
        policy=SimpleNamespace(model_dump=lambda mode: {}),
        system_prompt="system",
        messages=[],
        history=[],
        history_scope=SimpleNamespace(),
    )
    settings = SimpleNamespace(
        anthropic_api_key="sk-test",
        chat_model="claude-test",
        chat_max_tokens=128,
    )

    events = chat.stream_chat_events(
        settings=settings,  # type: ignore[arg-type]
        prepared=prepared,  # type: ignore[arg-type]
        client_factory=None,
        save_history_fn=AsyncMock(),
    )

    with pytest.raises(PaidApiBlockedError):
        await anext(events)
