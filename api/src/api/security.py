"""Security utilities — password hashing and structured-log data minimization."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pwdlib import PasswordHash

# Argon2id with recommended defaults (memory-hard, GPU/ASIC resistant)
_hasher = PasswordHash.recommended()

_REDACTED = "[REDACTED]"
_SENSITIVE_LOG_KEYS = frozenset(
    {
        "authorization",
        "compound_input",
        "compound_name",
        "compound_smiles",
        "cookie",
        "customer_email",
        "customer_id",
        "delivery_email",
        "email",
        "executed_by_email",
        "executed_by",
        "from_email",
        "full_name",
        "org_name",
        "password",
        "recipient",
        "recipient_email",
        "recipient_email_normalized",
        "secret",
        "smiles",
        "stripe_customer_id",
        "stripe_subscription_id",
        "subscription_id",
        "requested_by",
        "target_email",
        "target_email_normalized",
        "token",
    }
)
_SENSITIVE_LOG_KEY_SUFFIXES = (
    "_authorization",
    "_cookie",
    "_email",
    "_password",
    "_secret",
    "_smiles",
    "_token",
)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9_-]+"
    r"|\bwhsec_[A-Za-z0-9_-]+"
    r"|\bsk-ant-[A-Za-z0-9_-]+"
)
_URL_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://)"
    r"[^/@\s]+(?P<suffix>@)",
    flags=re.IGNORECASE,
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)(?P<prefix>[?&](?:access_token|api_key|authorization|code|"
    r"password|secret|signature|token)=)[^&#\s]+"
)
_PUBLIC_LOCATOR_RE = re.compile(
    r"(?P<prefix>/(?:share|unsubscribe/digest)/)[^/?#\s]+",
    flags=re.IGNORECASE,
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, hash_str: str) -> bool:
    """Verify a password against an Argon2id hash."""
    return _hasher.verify(password, hash_str)


def _is_sensitive_log_key(key: object) -> bool:
    normalized = str(key).strip().lower()
    return normalized in _SENSITIVE_LOG_KEYS or normalized.endswith(_SENSITIVE_LOG_KEY_SUFFIXES)


def _scrub_log_text(value: str) -> str:
    """Remove common credentials and personal identifiers from free-form text."""
    scrubbed = _URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED}{match.group('suffix')}",
        value,
    )
    scrubbed = _EMAIL_RE.sub(_REDACTED, scrubbed)
    scrubbed = _BEARER_RE.sub(f"Bearer {_REDACTED}", scrubbed)
    scrubbed = _SECRET_VALUE_RE.sub(_REDACTED, scrubbed)
    scrubbed = _QUERY_SECRET_RE.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED}",
        scrubbed,
    )
    return _PUBLIC_LOCATOR_RE.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED}",
        scrubbed,
    )


def _redact_log_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_log_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): (_REDACTED if _is_sensitive_log_key(key) else _redact_log_value(child))
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_redact_log_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_log_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_redact_log_value(item) for item in value), key=repr)
    return value


def redact_sensitive_log_data(
    _logger: object,
    _method_name: str,
    event_dict: Mapping[str, Any],
) -> dict[str, Any]:
    """Structlog processor that minimizes personal, compound, and credential data.

    Call sites should still avoid logging sensitive values. This processor is a
    final boundary for application and foreign-library events, including nested
    dictionaries and unstructured exception messages.
    """
    return {
        str(key): (_REDACTED if _is_sensitive_log_key(key) else _redact_log_value(value))
        for key, value in event_dict.items()
    }
