from __future__ import annotations

import json
from pathlib import Path

import pytest

from praviar_showcase_fixture import (
    canonical_payload_bytes,
    load_fixture,
    load_schema,
    payload_digest,
)


def test_fixture_matches_schema_and_digest() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    fixture = load_fixture()
    schema = load_schema()

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(fixture)
    assert payload_digest(fixture["payload"]) == fixture["fixture_digest"]


def test_fixture_is_repeatable_and_entirely_fictional() -> None:
    first = load_fixture()
    second = load_fixture()
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["fictional"] is True
    assert first["payload"]["matter"]["confidential_data_allowed"] is False
    assert "NOT LEGAL ADVICE" in first["payload"]["export"]["watermark"]
    assert "XX-FICTION" in serialized
    assert "@" not in serialized


def test_tampered_payload_is_detectable(tmp_path: Path) -> None:
    fixture = load_fixture()
    fixture["payload"]["matter"]["title"] = "tampered"

    assert payload_digest(fixture["payload"]) != fixture["fixture_digest"]


@pytest.mark.parametrize("value", [float("nan"), 1.5, 9_007_199_254_740_992])
def test_canonical_payload_rejects_cross_runtime_unsafe_numbers(
    value: float | int,
) -> None:
    with pytest.raises((TypeError, ValueError), match="safe integers"):
        canonical_payload_bytes({"not_json": value})


def test_canonical_payload_normalizes_valid_surrogate_pairs() -> None:
    escaped_pair = canonical_payload_bytes({"value": "\ud800\udc00"})
    unicode_scalar = canonical_payload_bytes({"value": "\U00010000"})

    assert escaped_pair == unicode_scalar


def test_canonical_payload_rejects_unpaired_surrogate() -> None:
    with pytest.raises(ValueError, match="unpaired Unicode surrogates"):
        canonical_payload_bytes({"value": "\ud800"})
