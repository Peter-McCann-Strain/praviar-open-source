from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.workers import email_task_runtime
from api.workers.email_task_digest import (
    build_top_risks_payload,
    weekly_digest_enabled,
)


def test_weekly_digest_enabled_defaults_to_weekly():
    assert weekly_digest_enabled(None) is True
    assert weekly_digest_enabled({}) is True
    assert weekly_digest_enabled({"email_digest_frequency": "weekly"}) is True
    assert weekly_digest_enabled({"email_digest_frequency": "off"}) is False


def test_build_top_risks_payload_uses_name_or_input_fallback():
    analyses = [
        SimpleNamespace(compound_name="aspirin", compound_input="aspirin", overall_risk="HIGH"),
        SimpleNamespace(
            compound_name="",
            compound_input="C" * 50,
            overall_risk=None,
        ),
    ]

    payload = build_top_risks_payload(analyses)  # type: ignore[arg-type]

    assert payload == [
        {"compound_name": "aspirin", "risk_level": "HIGH"},
        {"compound_name": "C" * 40, "risk_level": "UNKNOWN"},
    ]


@pytest.mark.asyncio
async def test_send_email_async_uses_configured_email_client(monkeypatch):
    client = object()

    def _fake_get_email_client():
        return client

    monkeypatch.setattr(
        "api.services.email.get_email_client",
        _fake_get_email_client,
    )

    async def _coro_factory(passed_client):
        assert passed_client is client
        return {"status": "ok"}

    result = await email_task_runtime.send_email_async(_coro_factory)

    assert result == {"status": "ok"}
