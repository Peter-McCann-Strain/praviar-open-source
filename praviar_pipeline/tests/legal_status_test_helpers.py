from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from praviar_pipeline.models.patent import LegalStatus, PatentHit, PatentSource
from praviar_pipeline.pipeline.search import enrichment


class _RegisterClient:
    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get_register(self, _patent_id: str) -> dict:
        return self.artifact

    async def get_biblio(self, _patent_id: str) -> dict:
        return {}


class _LegalEventsClient:
    def __init__(self, artifact: list[dict]) -> None:
        self.artifact = artifact

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get_legal_status(self, _patent_id: str) -> list[dict]:
        return self.artifact


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        ops_consumer_key="test-key",
        ops_consumer_secret="test-secret",
        search_max_legal_status_patents=10,
    )


def trusted_register_provenance(
    *,
    patent_id: str = "EP1234567B1",
    artifact: dict | None = None,
):
    retained_artifact = artifact or {"status": "revoked"}
    hit = PatentHit(patent_id=patent_id, sources=[PatentSource.PUBCHEM])
    original_client = enrichment.EPOOPSClient
    original_settings = enrichment.get_settings
    enrichment.EPOOPSClient = lambda: _RegisterClient(retained_artifact)
    enrichment.get_settings = _settings
    try:
        asyncio.run(enrichment.enrich_epo_register([hit]))
    finally:
        enrichment.EPOOPSClient = original_client
        enrichment.get_settings = original_settings
    assert hit.legal_status_provenance is not None
    return hit.legal_status_provenance


def trusted_ops_provenance(
    *,
    patent_id: str = "US1234567B2",
    legal_status: LegalStatus = LegalStatus.REVOKED,
    artifact: list[dict] | None = None,
):
    retained_artifact = artifact or [
        {"event_code": "REVOKED_FINAL", "event_description": "Patent revoked"}
    ]
    event_date = datetime.now(UTC).date().isoformat()
    retained_artifact = [
        {**event, "event_date": event.get("event_date") or event_date}
        for event in retained_artifact
    ]
    hit = PatentHit(patent_id=patent_id, sources=[PatentSource.EPO_SEARCH])
    original_client = enrichment.EPOOPSClient
    original_settings = enrichment.get_settings
    enrichment.EPOOPSClient = lambda: _LegalEventsClient(retained_artifact)
    enrichment.get_settings = _settings
    try:
        asyncio.run(
            enrichment.enrich_legal_status(
                [hit],
                derive_legal_status=lambda _events: legal_status,
            )
        )
    finally:
        enrichment.EPOOPSClient = original_client
        enrichment.get_settings = original_settings
    assert hit.legal_status_provenance is not None
    return hit.legal_status_provenance
