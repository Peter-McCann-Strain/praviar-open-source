"""Contract tests for the source-checkout canonical showcase adapter."""

from __future__ import annotations

import json

import pytest

from praviar_pipeline import showcase_fixture as subject


@pytest.fixture(autouse=True)
def _clear_fixture_cache() -> None:
    subject._load_verified_fixture.cache_clear()
    yield
    subject._load_verified_fixture.cache_clear()


def test_loader_verifies_receipt_and_returns_defensive_copies() -> None:
    first = subject.load_showcase_fixture()
    second = subject.load_showcase_fixture()

    first["payload"]["matter"]["reference"] = "mutated"

    assert second["fictional"] is True
    assert second["payload"]["matter"]["reference"] == "DEMO-0042"
    assert subject.showcase_fixture_receipt()["fixture_digest"] == second["fixture_digest"]
    assert subject.showcase_publication_id() == "US0000000042A1"
    assert subject.showcase_publication_id(1) == "US0000000043A1"


def test_loader_fails_closed_when_payload_digest_is_tampered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fixture = subject.load_showcase_fixture()
    fixture["payload"]["disclaimer"] = "tampered"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(subject, "_source_fixture_path", lambda: path)
    subject._load_verified_fixture.cache_clear()

    with pytest.raises(subject.ShowcaseFixtureError, match="digest mismatch"):
        subject.load_showcase_fixture()


def test_publication_projection_rejects_negative_indexes() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        subject.showcase_publication_id(-1)
