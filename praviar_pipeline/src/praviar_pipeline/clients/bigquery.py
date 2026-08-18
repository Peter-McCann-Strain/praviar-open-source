"""Google BigQuery client for the configured patent full-text dataset."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.bigquery_bootstrap import create_bigquery_client
from praviar_pipeline.clients.bigquery_cache_facade import BigQueryCacheFacade
from praviar_pipeline.clients.bigquery_client_execution import (
    run_bigquery_query_operation,
    run_bigquery_search_operation,
)
from praviar_pipeline.clients.bigquery_ops import (
    close_bigquery_client_impl,
    get_examiner_citations_batch_impl,
    get_patent_claims_batch_impl,
    get_patent_full_text_impl,
    get_patent_metadata_batch_impl,
    search_by_assignee_impl,
    search_by_cpc_and_keywords_impl,
    search_compound_annotations_impl,
    search_patents_by_compound_impl,
    search_patents_hybrid_impl,
    search_translated_patents_impl,
)
from praviar_pipeline.clients.bigquery_queries import (
    get_examiner_citations_batch,
    get_patent_claims_batch,
    get_patent_full_text,
    get_patent_metadata_batch,
    search_by_assignee_cached,
    search_by_cpc_and_keywords_cached,
    search_compound_annotations_cached,
    search_patents_by_compound_cached,
    search_patents_hybrid_cached,
    search_translated_patents_cached,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.no_paid_api import assert_paid_api_allowed

logger = structlog.get_logger()


def _get_bq_client():
    """Lazy-load BigQuery client using Application Default Credentials (ADC)."""
    return create_bigquery_client()


class BigQueryClient(AsyncClientMixin):
    """Async wrapper around Google BigQuery for patent search.

    Uses asyncio.to_thread to avoid blocking the event loop since the
    BigQuery SDK is synchronous. Includes optional file-based result
    caching to avoid redundant scans on repeated queries.
    """

    def __init__(self) -> None:
        self._client = None
        self._cache_facade = BigQueryCacheFacade()

    def _get_cache(self):
        return self._cache_facade.get_cache()

    def _ensure_client(self):
        if self._client is None:
            assert_paid_api_allowed("BigQuery")
            logger.debug("bigquery_initializing_client")
            self._client = _get_bq_client()
            logger.debug("bigquery_client_ready")
        return self._client

    def get_client(self):
        """Return the underlying BigQuery client, initializing if needed.

        Public wrapper around _ensure_client for external callers.
        """
        return self._ensure_client()

    async def _run_search(self, *, impl_fn, search_fn, **kwargs):
        """Outer boundary for a BigQuery search operation.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the whole search (including the file-backed BigQuery result cache
        managed by ``_cache_facade``) is wrapped so replays are deterministic.
        The two caches are independent: the response cache keys on the logical
        call signature (search_fn name + kwargs), the file cache keys on the
        SQL query text.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await run_bigquery_search_operation(
                ensure_client_fn=self._ensure_client,
                settings_fn=get_settings,
                cache_facade=self._cache_facade,
                impl_fn=impl_fn,
                search_fn=search_fn,
                **kwargs,
            )
        body = json.dumps(kwargs, sort_keys=True, default=str)
        return await cache.wrap(
            source="bigquery",
            method="POST",
            url=getattr(search_fn, "__name__", repr(search_fn)),
            body=body,
            call=lambda: run_bigquery_search_operation(
                ensure_client_fn=self._ensure_client,
                settings_fn=get_settings,
                cache_facade=self._cache_facade,
                impl_fn=impl_fn,
                search_fn=search_fn,
                **kwargs,
            ),
        )

    async def _run_query(self, *, impl_fn, query_fn, **kwargs):
        """Outer boundary for a BigQuery query operation.

        Mirrors :meth:`_run_search` — cache keys on ``query_fn`` name plus
        kwargs so two ``get_patent_claims_batch`` calls with different
        ``patent_ids`` produce distinct entries.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await run_bigquery_query_operation(
                ensure_client_fn=self._ensure_client,
                settings_fn=get_settings,
                impl_fn=impl_fn,
                query_fn=query_fn,
                **kwargs,
            )
        body = json.dumps(kwargs, sort_keys=True, default=str)
        return await cache.wrap(
            source="bigquery",
            method="POST",
            url=getattr(query_fn, "__name__", repr(query_fn)),
            body=body,
            call=lambda: run_bigquery_query_operation(
                ensure_client_fn=self._ensure_client,
                settings_fn=get_settings,
                impl_fn=impl_fn,
                query_fn=query_fn,
                **kwargs,
            ),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def search_patents_by_compound(
        self,
        synonyms: list[str],
        cpc_codes: list[str] | None = None,
        max_results: int = 200,
        jurisdictions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search patents-public-data for patents mentioning compound synonyms.

        Uses EXISTS subqueries instead of cross-joins to avoid row explosion.
        Claims text is not returned — fetched separately in step 4 when needed.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_patents_by_compound_impl,
                search_fn=search_patents_by_compound_cached,
                synonyms=synonyms,
                cpc_codes=cpc_codes,
                max_results=max_results,
                jurisdictions=jurisdictions,
            ),
        )

    async def search_patents_hybrid(
        self,
        query_terms: list[str],
        *,
        jurisdictions: list[str] | None,
        project: str,
        dataset: str,
        table: str,
        max_results: int = 200,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Search the configured embedding corpus with sparse+dense RRF.

        Unlike standard transient source calls, schema/configuration failures
        are not retried with another retrieval algorithm.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_patents_hybrid_impl,
                search_fn=search_patents_hybrid_cached,
                query_terms=query_terms,
                jurisdictions=jurisdictions,
                project=project,
                dataset=dataset,
                table=table,
                max_results=max_results,
                rrf_k=rrf_k,
            ),
        )

    async def get_patent_claims(self, patent_id: str) -> str:
        """Fetch full claim text for a specific patent."""
        batch = await self.get_patent_claims_batch([patent_id])
        return batch.get(patent_id, "")

    async def get_patent_claims_batch(
        self,
        patent_ids: list[str],
    ) -> dict[str, str]:
        """Fetch full claim text for multiple patents in one query.

        BigQuery scans the full claims column regardless of row count,
        so batching N lookups into one query costs the same as a single lookup.

        Returns:
            Dict mapping patent_id → claims_text.
        """
        return cast(
            "dict[str, str]",
            await self._run_query(
                impl_fn=get_patent_claims_batch_impl,
                query_fn=get_patent_claims_batch,
                patent_ids=patent_ids,
            ),
        )

    async def get_examiner_citations(
        self,
        patent_id: str,
    ) -> dict[str, list[str]]:
        """Get examiner vs applicant citations for a single patent."""
        batch = await self.get_examiner_citations_batch([patent_id])
        return batch.get(patent_id, {"examiner": [], "applicant": []})

    async def get_examiner_citations_batch(
        self,
        patent_ids: list[str],
    ) -> dict[str, dict[str, list[str]]]:
        """Get examiner vs applicant citations for multiple patents in one query.

        Returns:
            Dict mapping patent_id → {examiner: [...], applicant: [...]}.
        """
        return cast(
            "dict[str, dict[str, list[str]]]",
            await self._run_query(
                impl_fn=get_examiner_citations_batch_impl,
                query_fn=get_examiner_citations_batch,
                patent_ids=patent_ids,
            ),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def search_compound_annotations(
        self,
        name: str,
        inchikey: str = "",
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search Google Patents Research annotations for compound mentions.

        Uses the google_patents_research.annotations table which links
        compounds to patents via NLP extraction.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_compound_annotations_impl,
                search_fn=search_compound_annotations_cached,
                name=name,
                inchikey=inchikey,
                max_results=max_results,
            ),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def search_by_cpc_and_keywords(
        self,
        cpc_codes: list[str],
        keywords: list[str],
        max_results: int = 500,
        jurisdictions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search patents by CPC classification codes combined with keywords.

        Uses EXISTS subqueries to avoid cross-join row explosion.
        Claims text is not returned — fetched separately in step 4 when needed.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_by_cpc_and_keywords_impl,
                search_fn=search_by_cpc_and_keywords_cached,
                cpc_codes=cpc_codes,
                keywords=keywords,
                max_results=max_results,
                jurisdictions=jurisdictions,
            ),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def search_by_assignee(
        self,
        assignees: list[str],
        cpc_codes: list[str] | None = None,
        max_results: int = 500,
        jurisdictions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search patents by assignee name, optionally filtered by CPC codes.

        Uses EXISTS subqueries to avoid cross-join row explosion.
        Claims text is not returned — fetched separately in step 4 when needed.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_by_assignee_impl,
                search_fn=search_by_assignee_cached,
                assignees=assignees,
                cpc_codes=cpc_codes,
                max_results=max_results,
                jurisdictions=jurisdictions,
            ),
        )

    async def get_patent_metadata_batch(
        self,
        patent_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch metadata for specific patent IDs.

        Used to promote citation-discovered patents to first-class PatentHit
        objects by fetching their title, abstract, assignees, and CPC codes.
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_query(
                impl_fn=get_patent_metadata_batch_impl,
                query_fn=get_patent_metadata_batch,
                patent_ids=patent_ids,
            ),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def search_translated_patents(
        self,
        synonyms: list[str],
        jurisdictions: list[str] | None = None,
        max_results: int = 200,
    ) -> list[dict[str, Any]]:
        """Search non-English patents using machine-translated titles and abstracts.

        Uses scalar subqueries instead of CROSS JOINs to avoid row explosion.
        Searches across all language variants via EXISTS, then returns the
        best available text (English preferred, any language as fallback).
        """
        return cast(
            "list[dict[str, Any]]",
            await self._run_search(
                impl_fn=search_translated_patents_impl,
                search_fn=search_translated_patents_cached,
                synonyms=synonyms,
                jurisdictions=jurisdictions,
                max_results=max_results,
            ),
        )

    async def get_patent_full_text(self, patent_id: str) -> str:
        """Fetch full description/specification text for a patent.

        Used by research agents to access claim term definitions and
        detailed patent description for claim construction analysis.
        """
        return cast(
            "str",
            await self._run_query(
                impl_fn=get_patent_full_text_impl,
                query_fn=get_patent_full_text,
                patent_id=patent_id,
            ),
        )

    async def close(self) -> None:
        if self._client is not None:
            logger.debug("bigquery_client_closing")
            await close_bigquery_client_impl(self._client, to_thread_fn=asyncio.to_thread)
            self._client = None
