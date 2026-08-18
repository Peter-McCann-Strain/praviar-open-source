from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.no_paid_api import PaidApiBlockedError


def test_get_client_initializes_lazily() -> None:
    client = BigQueryClient()
    bq_client = object()

    with (
        patch("praviar_pipeline.clients.bigquery.assert_paid_api_allowed"),
        patch("praviar_pipeline.clients.bigquery._get_bq_client", return_value=bq_client) as get_bq,
    ):
        result = client.get_client()
        assert result is bq_client
        assert client.get_client() is bq_client

    get_bq.assert_called_once_with()


def test_get_client_blocks_live_bigquery_in_no_paid_mode(monkeypatch) -> None:
    client = BigQueryClient()
    monkeypatch.setenv("NO_PAID_API", "true")

    with (
        patch("praviar_pipeline.clients.bigquery._get_bq_client") as get_bq,
        pytest.raises(PaidApiBlockedError, match="NO_PAID_API=true"),
    ):
        client.get_client()

    get_bq.assert_not_called()


@pytest.mark.asyncio
async def test_search_by_cpc_and_keywords_delegates_to_helper() -> None:
    client = BigQueryClient()
    sentinel_client = object()
    client._client = sentinel_client
    helper_result = [{"publication_number": "US3"}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery.get_settings", return_value=MagicMock()
        ) as get_settings,
        patch(
            "praviar_pipeline.clients.bigquery.search_by_cpc_and_keywords_cached",
            new=AsyncMock(return_value=helper_result),
        ) as helper,
    ):
        result = await client.search_by_cpc_and_keywords(
            ["C07", "A01"],
            ["alpha", "beta"],
            max_results=42,
            jurisdictions=["US", "EP"],
        )

    assert result == helper_result
    get_settings.assert_called_once_with()
    helper.assert_awaited_once()
    call_kwargs = helper.await_args.kwargs
    assert call_kwargs["client"] is sentinel_client
    assert call_kwargs["cache_facade"] is client._cache_facade
    assert call_kwargs["cpc_codes"] == ["C07", "A01"]
    assert call_kwargs["keywords"] == ["alpha", "beta"]
    assert call_kwargs["max_results"] == 42
    assert call_kwargs["jurisdictions"] == ["US", "EP"]


@pytest.mark.asyncio
async def test_search_patents_hybrid_delegates_through_client_boundary() -> None:
    client = BigQueryClient()
    sentinel_client = object()
    client._client = sentinel_client
    helper_result = [{"publication_number": "US4", "rrf_score": 0.02}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery.get_settings",
            return_value=MagicMock(),
        ) as get_settings,
        patch(
            "praviar_pipeline.clients.bigquery.search_patents_hybrid_cached",
            new=AsyncMock(return_value=helper_result),
        ) as helper,
    ):
        result = await client.search_patents_hybrid(
            ["aspirin", "acetylsalicylic acid"],
            jurisdictions=["US", "EP"],
            project="project-1",
            dataset="patents",
            table="hybrid_index",
            max_results=42,
        )

    assert result == helper_result
    get_settings.assert_called_once_with()
    helper.assert_awaited_once()
    call_kwargs = helper.await_args.kwargs
    assert call_kwargs["client"] is sentinel_client
    assert call_kwargs["cache_facade"] is client._cache_facade
    assert call_kwargs["query_terms"] == ["aspirin", "acetylsalicylic acid"]
    assert call_kwargs["jurisdictions"] == ["US", "EP"]
    assert call_kwargs["project"] == "project-1"
    assert call_kwargs["dataset"] == "patents"
    assert call_kwargs["table"] == "hybrid_index"
    assert call_kwargs["max_results"] == 42
    assert call_kwargs["rrf_k"] == 60


@pytest.mark.asyncio
async def test_search_patents_hybrid_honors_no_paid_api(monkeypatch) -> None:
    client = BigQueryClient()
    monkeypatch.setenv("NO_PAID_API", "true")

    with (
        patch("praviar_pipeline.clients.bigquery._get_bq_client") as get_bq,
        pytest.raises(PaidApiBlockedError, match="NO_PAID_API=true"),
    ):
        await client.search_patents_hybrid(
            ["aspirin"],
            jurisdictions=["US"],
            project="project-1",
            dataset="patents",
            table="hybrid_index",
        )

    get_bq.assert_not_called()


@pytest.mark.asyncio
async def test_close_resets_cached_client() -> None:
    client = BigQueryClient()
    inner = MagicMock()
    client._client = inner

    with patch("praviar_pipeline.clients.bigquery.asyncio.to_thread", new=AsyncMock()) as to_thread:
        await client.close()

    to_thread.assert_awaited_once_with(inner.close)
    assert client._client is None


@pytest.mark.asyncio
async def test_get_patent_claims_uses_batch_wrapper() -> None:
    client = BigQueryClient()

    with patch.object(
        client,
        "get_patent_claims_batch",
        new=AsyncMock(return_value={"US123": "Claim 1. Example text."}),
    ) as batch_getter:
        result = await client.get_patent_claims("US123")

    assert result == "Claim 1. Example text."
    batch_getter.assert_awaited_once_with(["US123"])


@pytest.mark.asyncio
async def test_get_examiner_citations_uses_batch_wrapper() -> None:
    client = BigQueryClient()
    citation_payload = {"examiner": ["US1"], "applicant": ["US2"]}

    with patch.object(
        client,
        "get_examiner_citations_batch",
        new=AsyncMock(return_value={"US123": citation_payload}),
    ) as batch_getter:
        result = await client.get_examiner_citations("US123")

    assert result == citation_payload
    batch_getter.assert_awaited_once_with(["US123"])
