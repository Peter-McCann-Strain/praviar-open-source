"""Authoritative legal-status collectors bind field-level provenance."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.models.patent import (
    LegalStatus,
    PatentHit,
    PatentSource,
    trusted_legal_status_conflict,
    trusted_legal_status_observations,
)
from praviar_pipeline.pipeline.search import enrichment


class _EPOClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get_legal_status(self, _patent_id: str) -> list[dict]:
        return [
            {
                "event_date": "2025-01-01",
                "event_code": "LAPSED_FINAL",
                "event_description": "Patent lapsed",
                "country": "EP",
            }
        ]

    async def get_register(self, _patent_id: str) -> dict:
        return {
            "status": "Revoked",
            "designated_states": ["DE"],
            "legal_events": [],
            "opposition_events": [],
        }

    async def get_biblio(self, _patent_id: str) -> dict:
        return {"priority_claims": []}


@pytest.fixture(autouse=True)
def _epo_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrichment, "EPOOPSClient", _EPOClient)
    monkeypatch.setattr(
        enrichment,
        "get_settings",
        lambda: SimpleNamespace(
            ops_consumer_key="configured",
            ops_consumer_secret="configured",
            search_max_legal_status_patents=10,
        ),
    )


@pytest.mark.asyncio
async def test_inpadoc_collector_populates_content_bound_status_provenance() -> None:
    hit = PatentHit(patent_id="EP1234567B1", sources=[PatentSource.PUBCHEM])

    count = await enrichment.enrich_legal_status(
        [hit],
        derive_legal_status=lambda _events: LegalStatus.LAPSED,
    )

    assert count == 1
    assert hit.legal_status == LegalStatus.LAPSED
    provenance = hit.legal_status_provenance
    assert provenance is not None
    assert provenance.source == PatentSource.EPO_SEARCH
    assert provenance.collector_identity == "search.enrichment.epo_ops_legal_status"
    assert provenance.retrieved_at is not None
    assert provenance.artifact_locator.startswith("https://ops.epo.org/")
    assert f"#sha256={provenance.artifact_sha256}" in provenance.artifact_locator
    assert len(provenance.artifact_sha256) == 64
    assert provenance.supports(hit.legal_status, hit.patent_id)
    assert PatentSource.EPO_SEARCH in hit.sources
    assert trusted_legal_status_observations(hit) == (provenance,)


@pytest.mark.asyncio
async def test_ep_register_retains_an_independent_status_observation() -> None:
    hit = PatentHit(patent_id="EP7654321B1", sources=[PatentSource.PUBCHEM])

    outcome = await enrichment.enrich_epo_register([hit])

    assert outcome.evidence_count == 1
    assert outcome.covered_count == 1
    assert hit.legal_status == LegalStatus.REVOKED
    provenance = hit.legal_status_provenance
    assert provenance is not None
    assert provenance.source == PatentSource.EPO_SEARCH
    assert provenance.collector_identity == "search.enrichment.epo_register"
    assert provenance.retrieved_at is not None
    assert "#sha256=" in provenance.artifact_locator
    assert len(provenance.artifact_sha256) == 64
    assert provenance.supports(hit.legal_status, hit.patent_id)
    assert trusted_legal_status_observations(hit) == (provenance,)


@pytest.mark.asyncio
async def test_conflicting_authoritative_statuses_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ConflictingEPOClient(_EPOClient):
        async def get_legal_status(self, _patent_id: str) -> list[dict]:
            return [
                {
                    "event_date": "2025-01-01",
                    "event_code": "B1",
                    "event_description": "Patent granted",
                    "country": "EP",
                }
            ]

    monkeypatch.setattr(enrichment, "EPOOPSClient", ConflictingEPOClient)
    hit = PatentHit(patent_id="EP2468101B1", sources=[PatentSource.PUBCHEM])

    await enrichment.enrich_legal_status(
        [hit],
        derive_legal_status=lambda _events: LegalStatus.ACTIVE,
    )
    outcome = await enrichment.enrich_epo_register([hit])

    assert outcome.evidence_count == 1
    assert hit.legal_status == LegalStatus.UNKNOWN
    assert hit.legal_status_provenance is None
    assert {
        observation.collector_identity for observation in trusted_legal_status_observations(hit)
    } == {
        "search.enrichment.epo_ops_legal_status",
        "search.enrichment.epo_register",
    }
    assert trusted_legal_status_conflict(hit) == (
        LegalStatus.ACTIVE,
        LegalStatus.REVOKED,
    )


def test_non_authoritative_status_value_never_infers_provenance() -> None:
    hit = PatentHit(
        patent_id="US9999999B2",
        sources=[PatentSource.PUBCHEM],
        legal_status=LegalStatus.EXPIRED,
    )

    assert hit.legal_status_provenance is None
