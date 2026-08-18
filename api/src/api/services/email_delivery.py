"""Transport helpers for Postmark-backed email delivery."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import structlog

from api.services.email_models import DeliveryResult
from api.services.email_payloads import (
    build_postmark_email_payload,
    build_postmark_template_payload,
)


def _recipient_domain(address: str) -> str:
    """Return a non-mailbox log label for delivery diagnostics."""
    _local, separator, domain = address.rpartition("@")
    return domain.casefold() if separator else "invalid"


async def send_email_impl(
    *,
    is_configured: bool,
    from_email: str,
    to: str,
    subject: str,
    html_body: str,
    get_client_fn: Callable[[], Awaitable[httpx.AsyncClient]],
    logger: structlog.stdlib.BoundLogger,
    text_body: str | None = None,
    tag: str | None = None,
    message_stream: str | None = None,
    headers: list[dict[str, str]] | None = None,
) -> DeliveryResult:
    """Send a single email via Postmark."""
    if not is_configured:
        logger.warning(
            "email_skipped_incomplete_configuration",
            recipient_domain=_recipient_domain(to),
            reason="Postmark token and explicit sender must both be configured",
        )
        return DeliveryResult(success=False, error="Postmark sender configuration is incomplete")

    payload = build_postmark_email_payload(
        from_email=from_email,
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tag=tag,
        message_stream=message_stream,
        headers=headers,
    )

    from api.circuit_breaker import CircuitOpenError, postmark_breaker
    from api.http_utils import retry_with_jitter

    async def _send() -> DeliveryResult:
        # Stable across retry attempts — best-effort dedup signal (Postmark has
        # no native idempotency key; delivery is at-least-once on 5xx retries).
        send_id = str(uuid.uuid4())

        async def _attempt() -> DeliveryResult:
            client = await get_client_fn()
            response = await client.post(
                "/email", json={**payload, "Metadata": {"send_id": send_id}}
            )
            response.raise_for_status()
            data = response.json()
            return DeliveryResult(success=True, message_id=data.get("MessageID", ""))

        return await retry_with_jitter(_attempt, max_attempts=3, caller="postmark.send_email")

    try:
        result = await postmark_breaker.call(_send)
        logger.info(
            "email_sent",
            recipient_domain=_recipient_domain(to),
            tag=tag,
            message_id=result.message_id,
        )
        return result
    except CircuitOpenError as exc:
        logger.warning(
            "email_circuit_open",
            recipient_domain=_recipient_domain(to),
            retry_after_s=exc.retry_after_s,
        )
        return DeliveryResult(
            success=False, error=f"Email provider circuit open; retry in {exc.retry_after_s:.0f}s"
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "email_send_failed",
            recipient_domain=_recipient_domain(to),
            status_code=exc.response.status_code,
            exc_info=True,
        )
        return DeliveryResult(success=False, error=f"Postmark API error {exc.response.status_code}")
    except httpx.HTTPError as exc:
        logger.error(
            "email_send_failed",
            recipient_domain=_recipient_domain(to),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return DeliveryResult(success=False, error="HTTP error sending email")


async def send_template_email_impl(
    *,
    is_configured: bool,
    from_email: str,
    to: str,
    template_alias: str,
    template_model: dict[str, Any],
    get_client_fn: Callable[[], Awaitable[httpx.AsyncClient]],
    logger: structlog.stdlib.BoundLogger,
) -> DeliveryResult:
    """Send a templated email via Postmark server-side templates."""
    if not is_configured:
        logger.warning(
            "template_email_skipped_incomplete_configuration",
            recipient_domain=_recipient_domain(to),
            template_alias=template_alias,
            reason="Postmark token and explicit sender must both be configured",
        )
        return DeliveryResult(success=False, error="Postmark sender configuration is incomplete")

    payload = build_postmark_template_payload(
        from_email=from_email,
        to=to,
        template_alias=template_alias,
        template_model=template_model,
    )

    from api.circuit_breaker import CircuitOpenError, postmark_breaker
    from api.http_utils import retry_with_jitter

    async def _send() -> DeliveryResult:
        send_id = str(uuid.uuid4())

        async def _attempt() -> DeliveryResult:
            client = await get_client_fn()
            response = await client.post(
                "/email/withTemplate", json={**payload, "Metadata": {"send_id": send_id}}
            )
            response.raise_for_status()
            data = response.json()
            return DeliveryResult(success=True, message_id=data.get("MessageID", ""))

        return await retry_with_jitter(
            _attempt, max_attempts=3, caller="postmark.send_template_email"
        )

    try:
        result = await postmark_breaker.call(_send)
        logger.info(
            "template_email_sent",
            recipient_domain=_recipient_domain(to),
            template_alias=template_alias,
            message_id=result.message_id,
        )
        return result
    except CircuitOpenError as exc:
        logger.warning(
            "template_email_circuit_open",
            recipient_domain=_recipient_domain(to),
            template_alias=template_alias,
            retry_after_s=exc.retry_after_s,
        )
        return DeliveryResult(
            success=False,
            error=f"Email provider circuit open; retry in {exc.retry_after_s:.0f}s",
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "template_email_send_failed",
            recipient_domain=_recipient_domain(to),
            template_alias=template_alias,
            status_code=exc.response.status_code,
            exc_info=True,
        )
        return DeliveryResult(success=False, error=f"Postmark API error {exc.response.status_code}")
    except httpx.HTTPError as exc:
        logger.error(
            "template_email_send_failed",
            recipient_domain=_recipient_domain(to),
            template_alias=template_alias,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return DeliveryResult(success=False, error="HTTP error sending template email")
