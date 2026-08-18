"""Tests for analysis patent-enrichment helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.patent import PatentHit
from praviar_pipeline.pipeline.analysis.enrichment import enrich_patents_for_analysis_impl


def _patent(patent_id: str, *, claims_text: str = "") -> PatentHit:
    return PatentHit(
        patent_id=patent_id,
        title="Test patent",
        claims_text=claims_text,
    )


@pytest.mark.asyncio
async def test_enrich_patents_for_analysis_populates_claims_specs_and_prosecution(
    mock_settings,
) -> None:
    patents = [_patent("US1"), _patent("EP1", claims_text="already present")]
    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {"US1": "Claim 1 text"}
    bigquery_client.get_patent_full_text.side_effect = ["Spec text", "EP spec"]
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    async def fake_fetch_prosecution_context(patent_id: str) -> dict[str, str]:
        return {"office_actions": f"context for {patent_id}"}

    spec_text_cache, prosecution_cache = await enrich_patents_for_analysis_impl(
        patents,
        get_settings(),
        bigquery_client_cls=lambda: bigquery_client,
        fetch_prosecution_context=fake_fetch_prosecution_context,
    )

    assert patents[0].claims_text == "Claim 1 text"
    assert spec_text_cache == {"US1": "Spec text", "EP1": "EP spec"}
    assert prosecution_cache == {"US1": {"office_actions": "context for US1"}}


@pytest.mark.asyncio
async def test_enrich_patents_for_analysis_uses_patentsview_fallback(mock_settings) -> None:
    patents = [_patent("US1"), _patent("US2")]
    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {}
    bigquery_client.get_patent_full_text.return_value = "Full specification"
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    patentsview_client = AsyncMock()
    patentsview_client.get_patent_claims_text.side_effect = ["PV claims 1", None]
    patentsview_client.__aenter__.return_value = patentsview_client
    patentsview_client.__aexit__.return_value = False

    async def fake_fetch_prosecution_context(_: str) -> dict[str, str]:
        return {}

    with patch(
        "praviar_pipeline.clients.patentsview.PatentsViewClient",
        return_value=patentsview_client,
    ):
        await enrich_patents_for_analysis_impl(
            patents,
            get_settings(),
            bigquery_client_cls=lambda: bigquery_client,
            fetch_prosecution_context=fake_fetch_prosecution_context,
        )

    assert patents[0].claims_text == "PV claims 1"
    assert patents[1].claims_text == ""


@pytest.mark.asyncio
async def test_specification_retrieval_failure_does_not_use_abstract(mock_settings) -> None:
    from praviar_pipeline.errors import SourceUnavailableError

    patents = [_patent("US1")]
    patents[0].abstract = "customer-confidential abstract fallback"
    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {"US1": "Claim 1"}
    bigquery_client.get_patent_full_text.side_effect = RuntimeError(
        "provider secret and customer text"
    )
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    with pytest.raises(SourceUnavailableError) as exc_info:
        await enrich_patents_for_analysis_impl(
            patents,
            get_settings(),
            bigquery_client_cls=lambda: bigquery_client,
            fetch_prosecution_context=AsyncMock(return_value={}),
        )

    assert "provider secret" not in str(exc_info.value)
    assert "customer-confidential" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.asyncio
async def test_empty_specification_is_a_coverage_failure(mock_settings) -> None:
    from praviar_pipeline.errors import SourceUnavailableError

    patents = [_patent("US1")]
    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {"US1": "Claim 1"}
    bigquery_client.get_patent_full_text.return_value = ""
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    with pytest.raises(SourceUnavailableError):
        await enrich_patents_for_analysis_impl(
            patents,
            get_settings(),
            bigquery_client_cls=lambda: bigquery_client,
            fetch_prosecution_context=AsyncMock(return_value={}),
        )


@pytest.mark.asyncio
async def test_spec_text_cache_preserves_definition_beyond_80k(mock_settings) -> None:
    """Spec-text enrichment must not regress to the historical 80k truncation.

    A definition placed well past 80k characters must survive into the cache so
    an ambiguous claim term can be construed against the specification
    (Phillips v. AWH Corp.).
    """
    patents = [_patent("US1")]

    filler = ("[0001] " + ("routine prior-art discussion. " * 60) + "\n\n") * 1000
    definition = (
        '[9000] As used herein, the term "carrier" means a pharmaceutically '
        "acceptable excipient suitable for oral administration."
    )
    full_spec = filler + definition
    assert len(full_spec) > 80_000

    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {"US1": "Claim 1 text"}
    bigquery_client.get_patent_full_text.return_value = full_spec
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    async def fake_fetch_prosecution_context(_: str) -> dict[str, str]:
        return {}

    spec_text_cache, _ = await enrich_patents_for_analysis_impl(
        patents,
        get_settings(),
        bigquery_client_cls=lambda: bigquery_client,
        fetch_prosecution_context=fake_fetch_prosecution_context,
    )

    cached = spec_text_cache["US1"]
    assert len(cached) <= get_settings().spec_text_max_chars
    assert 'the term "carrier" means' in cached


@pytest.mark.asyncio
async def test_spec_text_cache_extends_coverage_beyond_first_ten(mock_settings) -> None:
    """Coverage extends to spec_text_max_patents, not the historical first ten."""
    patents = [_patent(f"US{index}") for index in range(15)]

    async def fake_get_full_text(patent_id: str) -> str:
        return f"[0001] Specification for {patent_id}."

    bigquery_client = AsyncMock()
    bigquery_client.get_patent_claims_batch.return_value = {
        patent.patent_id: "Claim 1 text" for patent in patents
    }
    bigquery_client.get_patent_full_text.side_effect = fake_get_full_text
    bigquery_client.__aenter__.return_value = bigquery_client
    bigquery_client.__aexit__.return_value = False

    async def fake_fetch_prosecution_context(_: str) -> dict[str, str]:
        return {}

    spec_text_cache, _ = await enrich_patents_for_analysis_impl(
        patents,
        get_settings(),
        bigquery_client_cls=lambda: bigquery_client,
        fetch_prosecution_context=fake_fetch_prosecution_context,
    )

    # The 11th and later patents now receive specification text.
    assert "US10" in spec_text_cache
    assert "US14" in spec_text_cache
    assert len(spec_text_cache) == 15
