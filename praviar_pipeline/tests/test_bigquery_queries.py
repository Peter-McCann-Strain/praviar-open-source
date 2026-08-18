from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.clients.bigquery_queries import (
    get_patent_full_text,
    search_by_cpc_and_keywords_cached,
    search_compound_annotations_cached,
    search_patents_by_compound_cached,
    search_patents_hybrid_cached,
    search_translated_patents_cached,
)


class _CacheFacade:
    def __init__(self, cache: object) -> None:
        self.cache = cache
        self.calls = 0

    def get_cache(self):
        self.calls += 1
        return self.cache


@pytest.mark.asyncio
async def test_search_patents_by_compound_cached_returns_cached_results() -> None:
    cache = object()
    cache_facade = _CacheFacade(cache)
    cached = [{"publication_number": "US1"}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery_queries.get_cached_result",
            return_value=cached,
        ) as get_cached,
        patch(
            "praviar_pipeline.clients.bigquery_queries.search_patents_by_compound_query"
        ) as query,
        patch("praviar_pipeline.clients.bigquery_queries.put_cached_result") as put_cached,
    ):
        result = await search_patents_by_compound_cached(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            cache_facade=cache_facade,
            synonyms=["beta", "alpha"],
            cpc_codes=["C07", "A01"],
            max_results=20,
            jurisdictions=None,
        )

    assert result == cached
    assert cache_facade.calls == 1
    get_cached.assert_called_once_with(
        cache,
        "search_patents_by_compound",
        synonyms=["alpha", "beta"],
        cpc_codes=["A01", "C07"],
        max_results=20,
        jurisdictions=None,
    )
    query.assert_not_called()
    put_cached.assert_not_called()


@pytest.mark.asyncio
async def test_search_patents_hybrid_cached_uses_complete_scope_key() -> None:
    cache = object()
    cache_facade = _CacheFacade(cache)
    query_result = [{"publication_number": "US-HYBRID", "rrf_score": 0.03}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery_queries.get_cached_result",
            return_value=None,
        ) as get_cached,
        patch(
            "praviar_pipeline.clients.bigquery_queries._search_bigquery_hybrid_query",
            new=AsyncMock(return_value=query_result),
        ) as query,
        patch("praviar_pipeline.clients.bigquery_queries.put_cached_result") as put_cached,
    ):
        result = await search_patents_hybrid_cached(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            cache_facade=cache_facade,
            query_terms=["aspirin", "acetylsalicylic acid"],
            jurisdictions=["US", "EP"],
            project="project-1",
            dataset="patents",
            table="hybrid_index",
            max_results=50,
            rrf_k=60,
        )

    assert result == query_result
    cache_kwargs = {
        "query_terms": ["aspirin", "acetylsalicylic acid"],
        "jurisdictions": ["EP", "US"],
        "project": "project-1",
        "dataset": "patents",
        "table": "hybrid_index",
        "max_results": 50,
        "rrf_k": 60,
    }
    get_cached.assert_called_once_with(cache, "search_patents_hybrid", **cache_kwargs)
    query.assert_awaited_once_with(
        client=ANY,
        settings=ANY,
        query_terms=["aspirin", "acetylsalicylic acid"],
        jurisdictions=["US", "EP"],
        project="project-1",
        dataset="patents",
        table="hybrid_index",
        limit=50,
        rrf_k=60,
    )
    put_cached.assert_called_once_with(
        cache,
        "search_patents_hybrid",
        query_result,
        **cache_kwargs,
    )


@pytest.mark.asyncio
async def test_search_by_cpc_and_keywords_cached_runs_query_and_stores_result() -> None:
    cache = object()
    cache_facade = _CacheFacade(cache)
    query_result = [{"publication_number": "US2"}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery_queries.get_cached_result",
            return_value=None,
        ) as get_cached,
        patch(
            "praviar_pipeline.clients.bigquery_queries.search_by_cpc_and_keywords_query",
            new=AsyncMock(return_value=query_result),
        ) as query,
        patch("praviar_pipeline.clients.bigquery_queries.put_cached_result") as put_cached,
    ):
        result = await search_by_cpc_and_keywords_cached(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            cache_facade=cache_facade,
            cpc_codes=["C07", "A01"],
            keywords=["zeta", "alpha"],
            max_results=25,
            jurisdictions=["US", "EP"],
        )

    assert result == query_result
    get_cached.assert_called_once_with(
        cache,
        "search_by_cpc_and_keywords",
        cpc_codes=["A01", "C07"],
        keywords=["alpha", "zeta"],
        max_results=25,
        jurisdictions=["EP", "US"],
    )
    query.assert_awaited_once()
    put_cached.assert_called_once_with(
        cache,
        "search_by_cpc_and_keywords",
        query_result,
        cpc_codes=["A01", "C07"],
        keywords=["alpha", "zeta"],
        max_results=25,
        jurisdictions=["EP", "US"],
    )


@pytest.mark.asyncio
async def test_search_compound_annotations_cached_runs_query() -> None:
    cache = object()
    cache_facade = _CacheFacade(cache)
    query_result = [{"publication_number": "US4"}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery_queries.get_cached_result",
            return_value=None,
        ) as get_cached,
        patch(
            "praviar_pipeline.clients.bigquery_queries.search_compound_annotations_query",
            new=AsyncMock(return_value=query_result),
        ) as query,
        patch("praviar_pipeline.clients.bigquery_queries.put_cached_result") as put_cached,
    ):
        result = await search_compound_annotations_cached(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            cache_facade=cache_facade,
            name="Amber Acid",
            inchikey="ABC",
            max_results=10,
        )

    assert result == query_result
    get_cached.assert_called_once_with(
        cache,
        "search_compound_annotations",
        name="amber acid",
        inchikey="ABC",
        max_results=10,
    )
    query.assert_awaited_once_with(
        client=ANY,
        settings=ANY,
        name="Amber Acid",
        inchikey="ABC",
        max_results=10,
    )
    put_cached.assert_called_once_with(
        cache,
        "search_compound_annotations",
        query_result,
        name="amber acid",
        inchikey="ABC",
        max_results=10,
    )


@pytest.mark.asyncio
async def test_search_translated_patents_cached_applies_default_jurisdictions() -> None:
    cache = object()
    cache_facade = _CacheFacade(cache)
    query_result = [{"publication_number": "JP1"}]

    with (
        patch(
            "praviar_pipeline.clients.bigquery_queries.get_cached_result",
            return_value=None,
        ) as get_cached,
        patch(
            "praviar_pipeline.clients.bigquery_queries.search_translated_patents_query",
            new=AsyncMock(return_value=query_result),
        ) as query,
        patch("praviar_pipeline.clients.bigquery_queries.put_cached_result") as put_cached,
    ):
        result = await search_translated_patents_cached(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            cache_facade=cache_facade,
            synonyms=["gamma", "beta"],
            jurisdictions=["JP", "KR", "CN", "IN", "DE", "FR"],
            max_results=15,
        )

    assert result == query_result
    get_cached.assert_called_once_with(
        cache,
        "search_translated_patents",
        synonyms=["beta", "gamma"],
        jurisdictions=["CN", "DE", "FR", "IN", "JP", "KR"],
        max_results=15,
    )
    query.assert_awaited_once_with(
        client=ANY,
        settings=ANY,
        synonyms=["gamma", "beta"],
        jurisdictions=["JP", "KR", "CN", "IN", "DE", "FR"],
        max_results=15,
    )
    put_cached.assert_called_once_with(
        cache,
        "search_translated_patents",
        query_result,
        synonyms=["beta", "gamma"],
        jurisdictions=["CN", "DE", "FR", "IN", "JP", "KR"],
        max_results=15,
    )


@pytest.mark.asyncio
async def test_get_patent_full_text_delegates_to_query_helper() -> None:
    helper_result = "full specification text"

    with patch(
        "praviar_pipeline.clients.bigquery_queries.get_patent_full_text_query",
        new=AsyncMock(return_value=helper_result),
    ) as query:
        result = await get_patent_full_text(
            client=MagicMock(name="client"),
            settings=SimpleNamespace(),
            patent_id="US123",
        )

    assert result == helper_result
    query.assert_awaited_once_with(
        client=ANY,
        settings=ANY,
        patent_id="US123",
    )
