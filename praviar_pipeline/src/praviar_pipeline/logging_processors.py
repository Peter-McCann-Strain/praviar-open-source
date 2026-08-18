"""Pure logging processor helpers for Praviar Pipeline."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_REDACTED = "***REDACTED***"
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "compound",
        "compound_input",
        "compound_name",
        "compound_smiles",
        "cookie",
        "customer_email",
        "delivery_email",
        "email",
        "full_name",
        "password",
        "recipient_email",
        "secret",
        "smiles",
        "target_smiles",
        "token",
    }
)
_SENSITIVE_KEY_SUFFIXES = (
    "_authorization",
    "_cookie",
    "_email",
    "_password",
    "_secret",
    "_smiles",
    "_token",
)
_SECRET_PATTERNS = [
    re.compile(r"(sk-ant-api\w{2}-)\S+"),
    re.compile(r"(sk-ant-)\S+"),
    re.compile(r"((?:sk|pk)_(?:live|test)_)\S+", re.IGNORECASE),
    re.compile(r"(whsec_)\S+", re.IGNORECASE),
    re.compile(r"(AIza)\S{35}"),
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)\S+", re.IGNORECASE),
    re.compile(r"(password[\"']?\s*[:=]\s*[\"']?)\S+", re.IGNORECASE),
]
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_URL_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://)"
    r"[^/@\s]+(?P<suffix>@)",
    flags=re.IGNORECASE,
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)(?P<prefix>[?&](?:access_token|api_key|authorization|code|"
    r"password|secret|signature|token)=)[^&#\s]+"
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower()
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)


def _mask_text(value: str) -> str:
    value = _URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED}{match.group('suffix')}",
        value,
    )
    value = _EMAIL_RE.sub(_REDACTED, value)
    value = _QUERY_SECRET_RE.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED}",
        value,
    )
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(rf"\1{_REDACTED}", value)
    return value


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): (_REDACTED if _is_sensitive_key(key) else _mask_value(child))
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_mask_value(item) for item in value)
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_mask_value(item) for item in value), key=repr)
    return value


def mask_secret_values(event_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact credentials and confidential customer fields recursively."""
    for key, value in event_dict.items():
        event_dict[key] = _REDACTED if _is_sensitive_key(key) else _mask_value(value)
    return event_dict


def truncate_event_values(
    event_dict: dict[str, Any],
    *,
    max_len: int,
) -> dict[str, Any]:
    """Truncate long string values to a bounded size."""
    for key, value in event_dict.items():
        if isinstance(value, str) and len(value) > max_len:
            event_dict[key] = value[:max_len] + f"... [{len(value)} chars]"
    return event_dict


def add_service_context(
    event_dict: dict[str, Any],
    *,
    service: str = "praviar_pipeline",
) -> dict[str, Any]:
    """Ensure every event has the configured service name."""
    event_dict.setdefault("service", service)
    return event_dict


def add_otel_context(event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject OpenTelemetry trace/span IDs when available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass
    return event_dict
