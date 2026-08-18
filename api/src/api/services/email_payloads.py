"""Payload builders for the Postmark email API."""

from __future__ import annotations

from typing import Any


def build_postmark_email_payload(
    *,
    from_email: str,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    tag: str | None = None,
    message_stream: str | None = None,
    headers: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a Postmark payload for a plain email send."""
    payload: dict[str, Any] = {
        "From": from_email,
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
    }
    if text_body:
        payload["TextBody"] = text_body
    if tag:
        payload["Tag"] = tag
    if message_stream:
        payload["MessageStream"] = message_stream
    if headers:
        payload["Headers"] = headers
    return payload


def build_postmark_template_payload(
    *,
    from_email: str,
    to: str,
    template_alias: str,
    template_model: dict[str, Any],
) -> dict[str, Any]:
    """Build a Postmark payload for a template-backed send."""
    return {
        "From": from_email,
        "To": to,
        "TemplateAlias": template_alias,
        "TemplateModel": template_model,
    }
