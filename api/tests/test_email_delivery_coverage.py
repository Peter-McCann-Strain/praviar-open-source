from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from api.circuit_breaker import CircuitOpenError
from api.services.email_delivery import send_email_impl, send_template_email_impl


class _Breaker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def call(self, operation):
        if self.error is not None:
            raise self.error
        return await operation()


def _status_error(code: int = 503) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://postmark.invalid/email")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("provider error", request=request, response=response)


def _install_delivery_runtime(monkeypatch, *, error: Exception | None = None) -> None:
    import api.circuit_breaker
    import api.http_utils

    monkeypatch.setattr(api.circuit_breaker, "postmark_breaker", _Breaker(error))

    async def _retry(operation, **kwargs):
        return await operation()

    monkeypatch.setattr(api.http_utils, "retry_with_jitter", _retry)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CircuitOpenError("postmark", 12.4), "Email provider circuit open; retry in 12s"),
        (_status_error(429), "Postmark API error 429"),
        (httpx.ConnectError("offline"), "HTTP error sending email"),
    ],
)
async def test_send_email_normalizes_provider_failures(monkeypatch, error, expected):
    _install_delivery_runtime(monkeypatch, error=error)
    logger = MagicMock()

    result = await send_email_impl(
        is_configured=True,
        from_email="sender@praviar.test",
        to="recipient@example.com",
        subject="Subject",
        html_body="<p>Body</p>",
        get_client_fn=AsyncMock(),
        logger=logger,
    )

    assert result.success is False
    assert result.error == expected


@pytest.mark.asyncio
async def test_template_email_rejects_unconfigured_transport():
    logger = MagicMock()

    result = await send_template_email_impl(
        is_configured=False,
        from_email="sender@praviar.test",
        to="invalid-address",
        template_alias="welcome",
        template_model={},
        get_client_fn=AsyncMock(),
        logger=logger,
    )

    assert result.success is False
    assert result.error == "Postmark sender configuration is incomplete"
    logger.warning.assert_called_once_with(
        "template_email_skipped_incomplete_configuration",
        recipient_domain="invalid",
        template_alias="welcome",
        reason="Postmark token and explicit sender must both be configured",
    )


@pytest.mark.asyncio
async def test_template_email_posts_payload_and_records_message_id(monkeypatch):
    _install_delivery_runtime(monkeypatch)
    response = MagicMock()
    response.json.return_value = {"MessageID": "template-message"}
    response.raise_for_status.return_value = None
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    logger = MagicMock()

    result = await send_template_email_impl(
        is_configured=True,
        from_email="sender@praviar.test",
        to="recipient@example.com",
        template_alias="welcome",
        template_model={"name": "Recipient"},
        get_client_fn=AsyncMock(return_value=client),
        logger=logger,
    )

    assert result.success is True
    assert result.message_id == "template-message"
    path, payload = client.post.await_args.args[0], client.post.await_args.kwargs["json"]
    assert path == "/email/withTemplate"
    assert payload["Metadata"]["send_id"]
    logger.info.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CircuitOpenError("postmark", 8.1), "Email provider circuit open; retry in 8s"),
        (_status_error(500), "Postmark API error 500"),
        (httpx.ReadTimeout("timed out"), "HTTP error sending template email"),
    ],
)
async def test_template_email_normalizes_provider_failures(monkeypatch, error, expected):
    _install_delivery_runtime(monkeypatch, error=error)

    result = await send_template_email_impl(
        is_configured=True,
        from_email="sender@praviar.test",
        to="recipient@example.com",
        template_alias="welcome",
        template_model={},
        get_client_fn=AsyncMock(),
        logger=MagicMock(),
    )

    assert result.success is False
    assert result.error == expected
