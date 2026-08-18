"""Verified access to the repository's canonical fictional showcase fixture.

This module is imported only by explicit showcase and dry-run paths. Production
analysis never reads, merges, or falls back to this data.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


class ShowcaseFixtureError(RuntimeError):
    """Raised when the canonical source fixture cannot be found or verified."""


def _canonical_payload_digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShowcaseFixtureError("showcase payload is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _source_fixture_path() -> Path:
    repository_root = Path(__file__).resolve().parents[3]
    return (
        repository_root
        / "packages"
        / "showcase-fixture"
        / "src"
        / "praviar_showcase_fixture"
        / "showcase.v1.json"
    )


@lru_cache(maxsize=1)
def _load_verified_fixture() -> dict[str, Any]:
    path = _source_fixture_path()
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShowcaseFixtureError(
            "canonical showcase fixture is unavailable; run this explicit "
            "development path from the Praviar source checkout"
        ) from exc
    if not isinstance(fixture, dict) or fixture.get("fictional") is not True:
        raise ShowcaseFixtureError("showcase fixture is not explicitly fictional")
    payload = fixture.get("payload")
    observed = _canonical_payload_digest(payload)
    expected = fixture.get("fixture_digest")
    if observed != expected:
        raise ShowcaseFixtureError(
            f"showcase fixture digest mismatch: expected {expected}, observed {observed}"
        )
    return fixture


def load_showcase_fixture() -> dict[str, Any]:
    """Return a defensive copy of the verified, wholly fictional fixture."""
    return deepcopy(_load_verified_fixture())


def showcase_fixture_receipt() -> dict[str, str]:
    """Return the stable identity fields consumers must record."""
    fixture = _load_verified_fixture()
    return {
        "schema_version": str(fixture["schema_version"]),
        "fixture_id": str(fixture["fixture_id"]),
        "fixture_version": str(fixture["fixture_version"]),
        "fixture_digest_algorithm": str(fixture["fixture_digest_algorithm"]),
        "fixture_digest": str(fixture["fixture_digest"]),
    }


def showcase_publication_id(index: int = 0) -> str:
    """Derive a parser-safe, visibly non-production publication identifier."""
    if index < 0:
        raise ValueError("showcase publication index must be non-negative")
    fixture = _load_verified_fixture()
    reference = str(fixture["payload"]["matter"]["reference"])
    digits = re.sub(r"\D", "", reference)
    if not digits:
        raise ShowcaseFixtureError("showcase matter reference lacks a numeric identity")
    return f"US{int(digits) + index:010d}A1"


__all__ = [
    "ShowcaseFixtureError",
    "load_showcase_fixture",
    "showcase_fixture_receipt",
    "showcase_publication_id",
]
