"""Fail-closed contracts for the API-to-ledger service boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from api.errors import APIError
from api.services import claimed_use_ledger_client as ledger_client


class _FakeAsyncClient:
    response = httpx.Response(
        200,
        json={"accepted": True},
        request=httpx.Request("POST", "https://workers.example.com"),
    )
    observed: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.observed["init"] = kwargs

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.observed["url"] = url
        self.observed["post"] = kwargs
        return self.response


@pytest.mark.asyncio
async def test_ledger_client_uses_api_workload_identity_and_exact_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        app_env="prod",
        service_role="api",
        workers_service_url="https://workers.example.com/",
    )
    observed_token_audience: list[str] = []

    def _token(audience: str) -> str:
        observed_token_audience.append(audience)
        return "google-signed-id-token"

    _FakeAsyncClient.observed = {}
    _FakeAsyncClient.response = httpx.Response(
        200,
        json={"accepted": True},
        request=httpx.Request("POST", "https://workers.example.com"),
    )
    monkeypatch.setattr(ledger_client, "get_settings", lambda: settings)
    monkeypatch.setattr(ledger_client, "_fetch_worker_identity_token", _token)

    result = await ledger_client.call_claimed_use_ledger(
        operation="erase-org",
        payload={"org_id": "tenant-1"},
        http_client_cls=_FakeAsyncClient,  # type: ignore[arg-type]
    )

    assert result == {"accepted": True}
    assert observed_token_audience == ["https://workers.example.com"]
    assert _FakeAsyncClient.observed["url"] == (
        "https://workers.example.com/internal/claimed-use/erase-org"
    )
    assert _FakeAsyncClient.observed["post"]["headers"]["Authorization"] == (
        "Bearer google-signed-id-token"
    )
    assert _FakeAsyncClient.observed["post"]["json"] == {"org_id": "tenant-1"}
    assert _FakeAsyncClient.observed["init"]["follow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("app_env", "service_role", "workers_url"),
    [
        ("test", "api", "https://workers.example.com"),
        ("prod", "worker", "https://workers.example.com"),
        ("prod", "api", "http://workers.example.com"),
    ],
)
async def test_ledger_client_rejects_wrong_runtime_or_insecure_origin(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    service_role: str,
    workers_url: str,
) -> None:
    monkeypatch.setattr(
        ledger_client,
        "get_settings",
        lambda: SimpleNamespace(
            app_env=app_env,
            service_role=service_role,
            workers_service_url=workers_url,
        ),
    )

    with pytest.raises(RuntimeError):
        await ledger_client.call_claimed_use_ledger(
            operation="list",
            payload={},
            http_client_cls=_FakeAsyncClient,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_ledger_client_preserves_problem_response_and_rejects_malformed_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ledger_client,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="prod",
            service_role="api",
            workers_service_url="https://workers.example.com",
        ),
    )
    monkeypatch.setattr(
        ledger_client,
        "_fetch_worker_identity_token",
        lambda _audience: "token",
    )
    _FakeAsyncClient.response = httpx.Response(
        403,
        json={"title": "Forbidden", "detail": "Actor binding failed"},
        request=httpx.Request("POST", "https://workers.example.com"),
    )

    with pytest.raises(APIError) as exc_info:
        await ledger_client.call_claimed_use_ledger(
            operation="issue",
            payload={},
            http_client_cls=_FakeAsyncClient,  # type: ignore[arg-type]
        )
    assert exc_info.value.status == 403
    assert exc_info.value.detail == "Actor binding failed"

    _FakeAsyncClient.response = httpx.Response(
        200,
        content=b"not-json",
        request=httpx.Request("POST", "https://workers.example.com"),
    )
    with pytest.raises(APIError) as malformed:
        await ledger_client.call_claimed_use_ledger(
            operation="list",
            payload={},
            http_client_cls=_FakeAsyncClient,  # type: ignore[arg-type]
        )
    assert malformed.value.status == 502
