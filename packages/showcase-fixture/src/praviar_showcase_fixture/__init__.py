"""Canonical, deterministic Praviar showcase fixture."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

FIXTURE_RESOURCE = "showcase.v1.json"
SCHEMA_RESOURCE = "showcase.schema.v1.json"
_MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


class ShowcaseFixtureError(ValueError):
    """Raised when the packaged showcase fixture is missing or has drifted."""


def _normalize_unicode(value: str) -> str:
    normalized: list[str] = []
    index = 0
    while index < len(value):
        code_point = ord(value[index])
        if 0xD800 <= code_point <= 0xDBFF:
            if index + 1 >= len(value):
                raise ValueError(
                    "canonical fixture JSON rejects unpaired Unicode surrogates"
                )
            low = ord(value[index + 1])
            if not 0xDC00 <= low <= 0xDFFF:
                raise ValueError(
                    "canonical fixture JSON rejects unpaired Unicode surrogates"
                )
            normalized.append(
                chr(0x10000 + ((code_point - 0xD800) << 10) + (low - 0xDC00))
            )
            index += 2
            continue
        if 0xDC00 <= code_point <= 0xDFFF:
            raise ValueError(
                "canonical fixture JSON rejects unpaired Unicode surrogates"
            )
        normalized.append(value[index])
        index += 1
    return "".join(normalized)


def _normalize_canonical_value(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _normalize_unicode(value)
    if type(value) is int:
        if abs(value) > _MAX_SAFE_JSON_INTEGER:
            raise ValueError("canonical fixture JSON requires safe integers")
        return value
    if isinstance(value, list):
        return [_normalize_canonical_value(nested) for nested in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical fixture JSON requires string object keys")
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            normalized_key = _normalize_unicode(key)
            if normalized_key in normalized:
                raise ValueError("canonical fixture JSON has duplicate normalized keys")
            normalized[normalized_key] = _normalize_canonical_value(nested)
        return normalized
    raise TypeError(
        "canonical fixture JSON permits only null, strings, booleans, "
        "safe integers, arrays, and objects"
    )


def canonical_payload_bytes(payload: object) -> bytes:
    """Serialize a fixture payload using the cross-language digest contract."""
    normalized = _normalize_canonical_value(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def payload_digest(payload: object) -> str:
    """Return the SHA-256 digest of canonical payload bytes."""
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def _load_json(resource_name: str) -> dict[str, Any]:
    resource = files(__package__).joinpath(resource_name)

    def reject_non_json_constant(value: str) -> None:
        raise ShowcaseFixtureError(f"{resource_name} contains non-JSON number {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ShowcaseFixtureError(
                    f"{resource_name} contains duplicate object key {key!r}"
                )
            result[key] = value
        return result

    value = json.loads(
        resource.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_json_constant,
    )
    if not isinstance(value, dict):
        raise ShowcaseFixtureError(f"{resource_name} must contain a JSON object")
    normalized = _normalize_canonical_value(value)
    if not isinstance(normalized, dict):  # defensive; the root type was checked above
        raise ShowcaseFixtureError(f"{resource_name} must contain a JSON object")
    return normalized


def load_schema() -> dict[str, Any]:
    """Load the versioned JSON Schema bundled with the fixture package."""
    return _load_json(SCHEMA_RESOURCE)


def load_fixture(*, verify: bool = True) -> dict[str, Any]:
    """Load the canonical fixture and fail closed if its payload digest drifted."""
    fixture = _load_json(FIXTURE_RESOURCE)
    if fixture.get("fictional") is not True:
        raise ShowcaseFixtureError("showcase fixture must be explicitly fictional")
    if verify:
        observed = payload_digest(fixture.get("payload"))
        expected = fixture.get("fixture_digest")
        if observed != expected:
            raise ShowcaseFixtureError(
                f"showcase fixture digest mismatch: expected {expected}, observed {observed}"
            )
    return fixture


__all__ = [
    "ShowcaseFixtureError",
    "canonical_payload_bytes",
    "load_fixture",
    "load_schema",
    "payload_digest",
]
