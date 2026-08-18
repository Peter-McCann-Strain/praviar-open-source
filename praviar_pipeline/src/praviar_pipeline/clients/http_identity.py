"""Truthful HTTP identity helpers for external scientific sources."""

from __future__ import annotations

import re

_BASE_USER_AGENT = "PraviarResearchPreview/0.1.0"
_CONTACT_EMAIL = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)


def normalize_source_contact_email(contact_email: str) -> str:
    """Return a strict ASCII mailbox safe for headers and query parameters."""
    if contact_email == "":
        return ""
    if len(contact_email) > 254 or not contact_email.isascii():
        raise ValueError("source_contact_email must be an ASCII mailbox")
    local_part, separator, _domain = contact_email.partition("@")
    if separator == "" or len(local_part.encode("ascii")) > 64:
        raise ValueError("source_contact_email local part is invalid")
    if not _CONTACT_EMAIL.fullmatch(contact_email):
        raise ValueError("source_contact_email is not a safe mailbox")
    return contact_email


def source_user_agent(contact_email: str) -> str:
    """Return a stable user agent without inventing a public contact channel."""
    normalized = normalize_source_contact_email(contact_email)
    if not normalized:
        return _BASE_USER_AGENT
    return f"{_BASE_USER_AGENT} (contact={normalized})"


def optional_contact_parameter(contact_email: str) -> dict[str, str]:
    """Return an upstream contact parameter only when an operator configured one."""
    normalized = normalize_source_contact_email(contact_email)
    return {"email": normalized} if normalized else {}
