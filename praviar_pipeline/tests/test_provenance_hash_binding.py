"""Adversarial tests for content-addressed patent provenance boundaries."""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import praviar_pipeline.models.patent as patent_models
from praviar_pipeline.models.patent import (
    ClaimTextProvenance,
    LegalStatus,
    LegalStatusProvenance,
    PatentHit,
    PatentSource,
    artifact_locator_binds_sha256,
    build_claim_text_provenance,
    has_trusted_legal_status_provenance,
)
from praviar_pipeline.pipeline.search import enrichment
from tests.legal_status_test_helpers import trusted_register_provenance


def _rehash_cassette(payload: dict) -> str:
    cassette = {
        key: payload[key]
        for key in (
            "schema_version",
            "source",
            "source_document_id",
            "retrieved_at",
            "artifact_locator",
            "artifact_sha256",
            "collector_identity",
            "collector_version",
        )
    }
    return hashlib.sha256(
        json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_claim_provenance_rejects_rehashed_cassette_with_mismatched_locator() -> None:
    provenance = build_claim_text_provenance(
        patent_id="US1234567B2",
        claims_text="1. A content-addressed claim",
        source=PatentSource.PATENTSVIEW,
        artifact_locator=("https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"),
        collector_identity="runtime.patentsview_claims",
    )
    payload = provenance.model_dump(mode="json")
    payload["artifact_locator"] = f"https://attacker.invalid/artifact#sha256={'b' * 64}"
    payload["cassette_sha256"] = _rehash_cassette(payload)

    with pytest.raises(ValidationError, match="artifact locator is not allowlisted"):
        ClaimTextProvenance.model_validate(payload)


def test_claim_provenance_builder_rejects_prebound_mismatched_locator() -> None:
    with pytest.raises(ValueError, match="artifact locator SHA-256 mismatch"):
        build_claim_text_provenance(
            patent_id="US1234567B2",
            claims_text="1. The retrieved claim",
            source=PatentSource.PATENTSVIEW,
            artifact_locator=(
                "https://search.patentsview.org/api/v1/patent/"
                f"?patent_id=US1234567B2#sha256={'0' * 64}"
            ),
            collector_identity="runtime.patentsview_claims",
        )


def test_claim_provenance_preserves_locator_fragment_and_adds_content_address() -> None:
    provenance = build_claim_text_provenance(
        patent_id="US1234567B2",
        claims_text="1. The retrieved claim",
        source=PatentSource.PATENTSVIEW,
        artifact_locator=(
            "https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2#claim=1"
        ),
        collector_identity="runtime.patentsview_claims",
    )

    assert "#claim=1&sha256=" in provenance.artifact_locator
    assert artifact_locator_binds_sha256(
        provenance.artifact_locator,
        provenance.artifact_sha256,
    )


def test_claim_provenance_rejects_self_asserted_collector_identity() -> None:
    with pytest.raises(ValidationError, match="collector_identity"):
        build_claim_text_provenance(
            patent_id="US1234567B2",
            claims_text="1. The retrieved claim",
            source=PatentSource.PATENTSVIEW,
            artifact_locator=(
                "https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"
            ),
            collector_identity="attacker.self_asserted_claims",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("temporal_case", "message"),
    [
        ("future", "in the future"),
        ("stale", "is stale"),
        ("naive", "timezone-aware"),
    ],
)
def test_claim_provenance_rejects_invalid_temporal_attestation(
    temporal_case: str,
    message: str,
) -> None:
    # Construct relative timestamps when the test executes, not at collection
    # time: the complete suite can legitimately run longer than the future-skew
    # window before reaching this parameterized case.
    now = datetime.now(UTC)
    retrieved_at = {
        "future": now + timedelta(minutes=6),
        "stale": now - timedelta(days=8),
        "naive": now.replace(tzinfo=None),
    }[temporal_case]
    with pytest.raises(ValidationError, match=message):
        build_claim_text_provenance(
            patent_id="US1234567B2",
            claims_text="1. The retrieved claim",
            source=PatentSource.PATENTSVIEW,
            artifact_locator=(
                "https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"
            ),
            collector_identity="runtime.patentsview_claims",
            retrieved_at=retrieved_at,
        )


def test_claim_provenance_use_boundary_rejects_post_construction_staleness() -> None:
    provenance = build_claim_text_provenance(
        patent_id="US1234567B2",
        claims_text="1. The retrieved claim",
        source=PatentSource.PATENTSVIEW,
        artifact_locator=("https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"),
        collector_identity="runtime.patentsview_claims",
    )
    object.__setattr__(provenance, "retrieved_at", datetime.now(UTC) - timedelta(days=31))

    assert not provenance.supports("1. The retrieved claim", "US1234567B2")


def _rehash_legal_status_cassette(payload: dict) -> str:
    cassette = {
        key: payload[key]
        for key in (
            "schema_version",
            "source",
            "source_document_id",
            "observed_status",
            "retrieved_at",
            "artifact_locator",
            "artifact_sha256",
            "artifact_payload",
            "collector_identity",
            "collector_version",
        )
    }
    return hashlib.sha256(
        json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _legal_status_payload() -> dict:
    return trusted_register_provenance().model_dump(mode="json")


def _replace_legal_status_artifact(payload: dict, artifact: object) -> None:
    payload["artifact_payload"] = artifact
    payload["artifact_sha256"] = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    locator_base = str(payload["artifact_locator"]).partition("#")[0]
    payload["artifact_locator"] = f"{locator_base}#sha256={payload['artifact_sha256']}"
    payload["cassette_sha256"] = _rehash_legal_status_cassette(payload)


@pytest.mark.parametrize(
    "locator_base",
    [
        "https://attacker.invalid/3.2/rest-services/register/publication/epodoc/EP1234567B1",
        "https://ops.epo.org.attacker.invalid/3.2/rest-services/register/publication/epodoc/EP1234567B1",
        "https://ops.epo.org/3.2/rest-services/register/publication/epodoc/EP9999999B1",
        "https://ops.epo.org/3.2/rest-services/legal/publication/epodoc/EP1234567B1",
    ],
)
def test_legal_status_provenance_rejects_rehashed_non_allowlisted_locator(
    locator_base: str,
) -> None:
    payload = _legal_status_payload()
    payload["artifact_locator"] = f"{locator_base}#sha256={payload['artifact_sha256']}"
    payload["cassette_sha256"] = _rehash_legal_status_cassette(payload)

    with pytest.raises(ValidationError, match="artifact locator is not allowlisted"):
        LegalStatusProvenance.model_validate(payload)


def test_legal_status_provenance_rejects_self_asserted_collector() -> None:
    payload = _legal_status_payload()
    payload["collector_identity"] = "attacker.self_asserted_status"
    payload["cassette_sha256"] = _rehash_legal_status_cassette(payload)

    with pytest.raises(ValidationError, match="collector_identity"):
        LegalStatusProvenance.model_validate(payload)


def test_legal_status_provenance_rejects_rehashed_status_change() -> None:
    provenance = trusted_register_provenance(artifact={"status": "expired"})
    hit = PatentHit(
        patent_id="EP1234567B1",
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=provenance,
    )

    assert not provenance.supports(hit.legal_status, hit.patent_id)


def test_legal_status_builder_rejects_unrelated_attacker_controlled_artifact() -> None:
    payload = _legal_status_payload()
    _replace_legal_status_artifact(payload, {"unrelated": "attacker-controlled; no status"})
    with pytest.raises(ValidationError, match="retained artifact does not entail observed status"):
        LegalStatusProvenance.model_validate(payload)


def test_legal_status_builder_rejects_wrong_source_specific_artifact_shape() -> None:
    payload = _legal_status_payload()
    _replace_legal_status_artifact(
        payload,
        [{"event_code": "REVOKE", "event_description": "Patent revoked"}],
    )
    with pytest.raises(ValidationError, match="retained artifact does not entail observed status"):
        LegalStatusProvenance.model_validate(payload)


def test_legal_status_use_boundary_rejects_retained_artifact_tampering() -> None:
    provenance = trusted_register_provenance()
    hit = PatentHit(
        patent_id="EP1234567B1",
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=provenance,
    )
    object.__setattr__(provenance, "artifact_payload", {"status": "active"})

    assert not has_trusted_legal_status_provenance(hit)


def test_serialized_legal_status_cassette_cannot_mint_runtime_trust() -> None:
    trusted = trusted_register_provenance()
    caller_minted = LegalStatusProvenance.model_validate(trusted.model_dump(mode="python"))
    hit = PatentHit(
        patent_id="EP1234567B1",
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=caller_minted,
    )

    assert trusted.supports(LegalStatus.REVOKED, "EP1234567B1")
    assert not caller_minted.supports(LegalStatus.REVOKED, "EP1234567B1")
    assert not has_trusted_legal_status_provenance(hit)


def test_generic_caller_cannot_mint_legal_status_runtime_trust() -> None:
    with pytest.raises(PermissionError, match="trusted collector adapter"):
        patent_models._build_legal_status_provenance(
            patent_id="EP1234567B1",
            legal_status=LegalStatus.REVOKED,
            artifact={"status": "revoked"},
            collector_identity="search.enrichment.epo_register",
        )


def test_runtime_attestation_cannot_be_copied_to_reconstructed_cassette() -> None:
    trusted = trusted_register_provenance()
    reconstructed = LegalStatusProvenance.model_validate(trusted.model_dump(mode="python"))
    reconstructed._runtime_attestation = trusted._runtime_attestation

    assert trusted.supports(LegalStatus.REVOKED, "EP1234567B1")
    assert not reconstructed.supports(LegalStatus.REVOKED, "EP1234567B1")


@pytest.mark.parametrize(
    ("temporal_case", "message"),
    [
        ("future", "in the future"),
        ("stale", "is stale"),
        ("naive", "timezone-aware"),
    ],
)
def test_legal_status_provenance_rejects_invalid_temporal_attestation(
    temporal_case: str,
    message: str,
) -> None:
    now = datetime.now(UTC)
    retrieved_at = {
        "future": now + timedelta(minutes=6),
        "stale": now - timedelta(days=31),
        "naive": now.replace(tzinfo=None),
    }[temporal_case]
    payload = _legal_status_payload()
    payload["retrieved_at"] = retrieved_at.isoformat()
    payload["cassette_sha256"] = _rehash_legal_status_cassette(payload)
    with pytest.raises(ValidationError, match=message):
        LegalStatusProvenance.model_validate(payload)


def test_legal_status_provenance_accepts_fresh_attestation_within_policy() -> None:
    payload = _legal_status_payload()
    payload["retrieved_at"] = (datetime.now(UTC) - timedelta(hours=71)).isoformat()
    payload["cassette_sha256"] = _rehash_legal_status_cassette(payload)

    assert LegalStatusProvenance.model_validate(payload).observed_status == LegalStatus.REVOKED


def test_provenance_builders_are_confined_to_trusted_adapter_modules() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "praviar_pipeline"

    def callers(symbol: str) -> set[str]:
        return {
            path.relative_to(source_root).as_posix()
            for path in source_root.rglob("*.py")
            if symbol in path.read_text(encoding="utf-8")
        }

    assert callers("build_claim_text_provenance") == {
        "models/patent.py",
        "pipeline/runtime/live_collector_claims.py",
        "pipeline/search/normalizers.py",
    }
    assert callers("_build_legal_status_provenance") == {
        "models/patent.py",
        "pipeline/search/enrichment.py",
    }
    assert callers("_issue_legal_status_attestation") == {"models/patent.py"}
    assert callers("_attest_epo_ops_legal_status") == set()
    assert callers("_attest_epo_register_legal_status") == set()
    assert not hasattr(enrichment, "_attest_epo_ops_legal_status")
    assert not hasattr(enrichment, "_attest_epo_register_legal_status")
    assert (
        inspect.signature(enrichment.enrich_legal_status).parameters["client_factory"].default
        is None
    )
    assert (
        inspect.signature(enrichment.enrich_epo_register).parameters["client_factory"].default
        is None
    )
