from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.ocsr import text_validation_clients


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, text: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        return self._response


@pytest.mark.asyncio
async def test_opsin_resolve_returns_none_when_text_validation_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "praviar_pipeline.config.get_settings",
        lambda: SimpleNamespace(drawing_text_validation_enabled=False),
    )

    assert await text_validation_clients.opsin_resolve("ethanol") is None


@pytest.mark.asyncio
async def test_pubchem_name_lookup_returns_canonical_smiles(monkeypatch) -> None:
    response = _FakeResponse(
        payload={
            "PropertyTable": {
                "Properties": [
                    {"CanonicalSMILES": "CCO"},
                ]
            }
        }
    )

    monkeypatch.setattr(
        text_validation_clients.httpx,
        "AsyncClient",
        lambda timeout: _FakeClient(response),
    )

    assert await text_validation_clients._pubchem_name_lookup("ethanol") == "CCO"
