"""PubMed/MEDLINE E-utilities client — biomedical literature for prior art search.

Searches the NCBI PubMed database for biomedical literature that may
constitute prior art in patent invalidity analysis. Uses the E-utilities
API (esearch + esummary) for fast metadata retrieval.

Request pacing follows the operator-configured local cap.
"""

from __future__ import annotations

from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError

logger = structlog.get_logger()

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient(AsyncClientMixin):
    """Async client for the NCBI PubMed E-utilities API.

    Searches biomedical literature for prior art discovery.
    Optionally uses an NCBI API key for authenticated requests.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._api_key = settings.ncbi_api_key
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
        )
        rate = settings.pubmed_requests_per_second
        self._limiter = AsyncLimiter(max_rate=rate, time_period=1)
        logger.debug(
            "pubmed_client_init",
            status="authenticated" if self._api_key else "unauthenticated",
            configured_local_rps=rate,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    def _base_params(self) -> dict[str, str]:
        """Return base query parameters including API key if available."""
        params: dict[str, str] = {}
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def _get_json(
        self,
        path: str,
        params: dict[str, str],
        *,
        ok_on_404: bool = False,
    ) -> dict:
        """Rate-limited GET request returning JSON.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the query params (excluding the api_key auth
        credential) into the body hash so distinct queries key distinctly.
        Cache hits bypass tenacity — we only retry live calls. Exceptions
        propagate unrecorded.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_json_uncached(path, params, ok_on_404=ok_on_404)
        # Strip the api_key auth credential from the cache key so the
        # cache survives key rotation.
        key_params = {k: v for k, v in params.items() if k != "api_key"}
        body = json.dumps(key_params, sort_keys=True) if key_params else None
        return await cache.wrap(
            source="pubmed",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_json_uncached(path, params, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
    )
    async def _get_json_uncached(
        self,
        path: str,
        params: dict[str, str],
        *,
        ok_on_404: bool = False,
    ) -> dict:
        """Underlying live HTTP GET — retries via tenacity, never cached here.

        Args:
            ok_on_404: When True, a 404 is a legitimate "no such record"
                lookup result and returns an empty dict. When False (the
                default, for search endpoints), a 404 raises
                ``SourceUnavailableError``.
        """
        async with self._limiter:
            resp = await self._client.get(path, params=params)
            if resp.status_code == 429:
                logger.warning("pubmed_rate_limited")
                resp.raise_for_status()
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("pubmed_404_semantic_empty")
                    return {}
                raise SourceUnavailableError("pubmed", f"404 on {path}", status_code=404)
            resp.raise_for_status()
            return cast("dict", resp.json())

    async def search_papers(
        self,
        query: str,
        *,
        max_results: int = 20,
    ) -> list[dict]:
        """Search PubMed and return paper metadata.

        Uses esearch to find matching PMIDs, then esummary to retrieve
        metadata in a single batch call. This is faster and simpler than
        parsing efetch XML.

        Args:
            query: Search text (compound name, MeSH term, etc.).
            max_results: Maximum papers to return.

        Returns:
            List of dicts with keys: pmid, title, authors, journal,
            publication_date, doi, source.
        """
        logger.debug("pubmed_search_start", max_results=max_results)

        # Step 1: esearch — get matching PMIDs
        search_params = {
            **self._base_params(),
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
            "sort": "relevance",
        }
        search_data = await self._get_json("/esearch.fcgi", search_params)

        esearch_result = search_data.get("esearchresult", {})
        pmids = esearch_result.get("idlist", [])
        if not pmids:
            logger.debug("pubmed_search_no_results")
            return []

        total_count = int(esearch_result.get("count", 0))
        logger.debug(
            "pubmed_search_ids_found",
            returned=len(pmids),
            total_available=total_count,
        )

        # Step 2: esummary — get metadata for all PMIDs in one call
        papers = await self._fetch_summaries(pmids)
        logger.debug(
            "pubmed_search_complete",
            total_results=len(papers),
        )
        return papers

    async def get_paper_details(self, pmid: str) -> dict:
        """Get full metadata for a single PubMed ID.

        Args:
            pmid: PubMed ID (numeric string).

        Returns:
            Dict with keys: pmid, title, abstract, authors, journal,
            publication_date, doi, source, mesh_terms.
            Returns empty dict if not found.
        """
        logger.debug("pubmed_get_paper")
        papers = await self._fetch_summaries([pmid])
        if not papers:
            return {}
        return papers[0]

    async def _fetch_summaries(self, pmids: list[str]) -> list[dict]:
        """Fetch metadata for a batch of PMIDs via esummary.

        The esummary endpoint returns structured JSON with title, authors,
        journal, dates, and DOIs — sufficient for prior art identification
        without the complexity of parsing efetch XML.
        """
        if not pmids:
            return []

        summary_params = {
            **self._base_params(),
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }
        summary_data = await self._get_json("/esummary.fcgi", summary_params, ok_on_404=True)

        result_block = summary_data.get("result", {})
        papers: list[dict] = []

        for pmid in pmids:
            entry = result_block.get(pmid)
            if not entry or not isinstance(entry, dict):
                continue

            # Extract DOI from articleids list
            doi = ""
            for aid in entry.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid.get("value", "")
                    break

            # Extract author names
            authors = [a.get("name", "") for a in entry.get("authors", []) if a.get("name")]

            # Parse publication date (format: "YYYY Mon DD" or "YYYY Mon")
            pub_date = entry.get("pubdate", "")

            paper = {
                "pmid": pmid,
                "title": entry.get("title", ""),
                "authors": authors,
                "journal": entry.get("fulljournalname", "") or entry.get("source", ""),
                "publication_date": pub_date,
                "doi": doi,
                "source": "pubmed",
                "volume": entry.get("volume", ""),
                "issue": entry.get("issue", ""),
                "pages": entry.get("pages", ""),
            }
            papers.append(paper)

        return papers

    async def search_compound_literature(
        self,
        compound_name: str,
        *,
        synonyms: list[str] | None = None,
        cas_numbers: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """Search PubMed for literature about a specific compound.

        Builds a compound-optimised query combining name, synonyms, and
        CAS numbers with the configured MeSH-aware query expansion.

        Args:
            compound_name: Primary compound name.
            synonyms: Alternative names for the compound.
            cas_numbers: CAS registry numbers.
            max_results: Maximum papers to return.

        Returns:
            List of paper metadata dicts.
        """
        # Build OR-joined query from compound identifiers
        terms = [f'"{compound_name}"']
        if synonyms:
            for syn in synonyms[:5]:
                terms.append(f'"{syn}"')
        if cas_numbers:
            for cas in cas_numbers[:3]:
                terms.append(f'"{cas}"')

        query = " OR ".join(terms)
        logger.debug(
            "pubmed_compound_search",
        )
        return await self.search_papers(query, max_results=max_results)
