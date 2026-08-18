"""Tests for live_collector_claims: cap, logging, and not-configured handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.models.patent import PatentHit
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    collect_claims_from_bigquery_impl,
    collect_claims_from_epo_impl,
    collect_claims_from_patentsview_impl,
)


def _ep_hit(patent_id: str, claims_text: str = "") -> PatentHit:
    hit = PatentHit(patent_id=patent_id, title=f"Patent {patent_id}")
    hit.claims_text = claims_text
    return hit


def _us_hit(patent_id: str, claims_text: str = "") -> PatentHit:
    hit = PatentHit(patent_id=patent_id, title=f"Patent {patent_id}")
    hit.claims_text = claims_text
    return hit


@pytest.mark.asyncio
async def test_epo_claims_cap_limits_processed_patents() -> None:
    """EPO claims collection must not exceed the configured max_patents cap."""
    hits = [_ep_hit(f"EP{i:07d}B1") for i in range(300)]
    called_ids: list[str] = []

    async def fake_claims_text(patent_id: str) -> str:
        called_ids.append(patent_id)
        return f"1. A claim text for {patent_id}."

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_claims_text = fake_claims_text

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.EPOOPSClient",
        return_value=fake_client,
    ):
        entry, enriched_ids = await collect_claims_from_epo_impl(hits, max_patents=50)

    assert len(called_ids) == 50
    assert len(enriched_ids) == 50
    assert entry.patent_count == 50
    provenance = hits[0].claims_text_provenance
    assert provenance is not None
    assert provenance.supports(hits[0].claims_text, hits[0].patent_id)
    assert provenance.collector_identity == "runtime.epo_ops_claims"
    assert "#sha256=" in provenance.artifact_locator


@pytest.mark.asyncio
async def test_epo_claims_returns_not_configured_on_connect_error() -> None:
    """A ConnectError during EPO claims should return NOT_CONFIGURED, not FAILED."""
    hits = [_ep_hit("EP1234567B1")]
    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_claims_text = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.EPOOPSClient",
        return_value=fake_client,
    ):
        entry, enriched_ids = await collect_claims_from_epo_impl(hits, max_patents=10)

    assert entry.status.value == "not_configured"
    assert enriched_ids == []


@pytest.mark.asyncio
async def test_epo_claims_skips_patents_with_existing_claims() -> None:
    """Patents that already have claims_text should not trigger EPO calls."""
    hits = [
        _ep_hit("EP0000001B1", claims_text="already has claims"),
        _ep_hit("EP0000002B1"),
    ]
    called_ids: list[str] = []

    async def fake_claims_text(patent_id: str) -> str:
        called_ids.append(patent_id)
        return "new claims"

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_claims_text = fake_claims_text

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.EPOOPSClient",
        return_value=fake_client,
    ):
        _entry, enriched_ids = await collect_claims_from_epo_impl(hits, max_patents=10)

    assert called_ids == ["EP0000002B1"]
    assert len(enriched_ids) == 1


@pytest.mark.asyncio
async def test_epo_claims_empty_when_no_ep_patents() -> None:
    """Non-EP patents should be silently skipped."""
    hits = [PatentHit(patent_id="US1234567B2", title="US patent")]
    entry, enriched_ids = await collect_claims_from_epo_impl(hits, max_patents=10)

    assert entry.patent_count == 0
    assert enriched_ids == []


@pytest.mark.asyncio
async def test_patentsview_claims_cap_limits_processed_patents() -> None:
    """PatentsView claims collection must not exceed the configured max_patents cap."""
    hits = [_us_hit(f"US{i:07d}B2") for i in range(200)]
    called_ids: list[str] = []

    async def fake_claims_text(patent_id: str) -> str:
        called_ids.append(patent_id)
        return f"1. A claim text for {patent_id}."

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_patent_claims_text = fake_claims_text

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.PatentsViewClient",
        return_value=fake_client,
    ):
        entry, enriched_ids = await collect_claims_from_patentsview_impl(hits, max_patents=30)

    assert len(called_ids) == 30
    assert len(enriched_ids) == 30
    assert entry.patent_count == 30
    provenance = hits[0].claims_text_provenance
    assert provenance is not None
    assert provenance.supports(hits[0].claims_text, hits[0].patent_id)
    assert provenance.collector_identity == "runtime.patentsview_claims"
    assert "#sha256=" in provenance.artifact_locator


@pytest.mark.asyncio
async def test_bigquery_claims_records_artifact_grade_provenance() -> None:
    hit = _us_hit("US1234567B2")
    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_patent_claims_batch = AsyncMock(
        return_value={hit.patent_id: "1. A cassette-bound claim"}
    )

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.BigQueryClient",
        return_value=fake_client,
    ):
        entry, enriched_ids = await collect_claims_from_bigquery_impl([hit])

    assert entry.patent_count == 1
    assert enriched_ids == [hit.patent_id]
    provenance = hit.claims_text_provenance
    assert provenance is not None
    assert provenance.supports(hit.claims_text, hit.patent_id)
    assert provenance.collector_identity == "runtime.bigquery_claims_batch"
    assert len(provenance.cassette_sha256) == 64


@pytest.mark.asyncio
async def test_patentsview_claims_skips_non_us_patents() -> None:
    """EP and WO patents should not trigger PatentsView calls."""
    hits = [
        _ep_hit("EP1234567B1"),
        _us_hit("US9999999B2"),
    ]
    called_ids: list[str] = []

    async def fake_claims_text(patent_id: str) -> str:
        called_ids.append(patent_id)
        return "claims"

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_patent_claims_text = fake_claims_text

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_claims.PatentsViewClient",
        return_value=fake_client,
    ):
        _entry, enriched_ids = await collect_claims_from_patentsview_impl(hits, max_patents=10)

    assert called_ids == ["US9999999B2"]
    assert len(enriched_ids) == 1
