"""USPTO ODP (Open Data Portal) patent applications search client.

Replaces the decommissioned PatentsView search.patentsview.org API (NXDOMAIN
since 2026-03-20) with the USPTO Open Data Portal endpoint at api.uspto.gov.

The configured ODP applications endpoint returns application and issued-patent
records available from that source. A successful request is not treated as a
claim of exhaustive historical coverage. Returned records can provide:
  - Invention titles and CPC classification codes
  - Assignee and applicant names (disambiguated via assignment records)
  - Application status and key dates (filing, grant)
  - Continuity relationships (continuation, divisional chains)

Note: Full-text abstract and claims are not available from the file wrapper
endpoint; those are supplied by other pipeline sources (BigQuery, EPO OPS).
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.patentsview_queries import (
    build_assignee_search_query,
    build_compound_keyword_query,
    build_cpc_search_query,
    build_patent_query,
)
from praviar_pipeline.clients.patentsview_requests import (
    DEFAULT_ASSIGNEE_FIELDS,
    DEFAULT_COMPOUND_KEYWORD_FIELDS,
    DEFAULT_CPC_FIELDS,
    DEFAULT_PATENT_DETAIL_FIELDS,
    build_search_request_params,
)
from praviar_pipeline.clients.patentsview_results import (
    extract_first_patent,
    extract_patent_citations,
    extract_patents,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import (
    AuthenticationError,
    ConfigurationError,
    SourceUnavailableError,
)

logger = structlog.get_logger()

BASE_URL = "https://api.uspto.gov/api/v1"
_SEARCH_PATH = "/patent/applications/search"


def _is_key_valid(key: str) -> bool:
    return bool(key.strip())


class PatentsViewClient(AsyncClientMixin):
    """Async client for the USPTO ODP patent applications search API.

    Provides keyword search, CPC-filtered search, assignee search, and
    single-patent lookup for US patent applications and granted patents.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()

        # Prefer the ODP-specific key; fall back to the legacy patentsview key
        # (both secrets hold the same value in current deployments).
        odp_key = settings.uspto_odp_api_key or settings.patentsview_api_key
        self._key_valid = _is_key_valid(odp_key)
        self._api_key = odp_key

        if not self._key_valid:
            logger.warning("uspto_odp_disabled")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._key_valid:
            headers["X-API-KEY"] = self._api_key
            logger.debug("uspto_odp_client_init", status="enabled")

        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            headers=headers,
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.patentsview_requests_per_minute,
            time_period=60,
        )

    def _require_valid_key(self) -> None:
        if not self._key_valid:
            raise ConfigurationError(
                "USPTO ODP API key not configured. "
                "Set 'USPTO_ODP_API_KEY' in environment or GCP secret 'uspto-odp-api-key'.",
                source="patentsview",
            )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, *, ok_on_404: bool = False, **kwargs) -> dict:
        """Make an API request with rate limiting, retry, and optional caching."""
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._request_uncached(method, path, ok_on_404=ok_on_404, **kwargs)

        key_payload: dict = {}
        if kwargs.get("params"):
            key_payload["params"] = kwargs["params"]
        if kwargs.get("json"):
            key_payload["json"] = kwargs["json"]
        body = json.dumps(key_payload, sort_keys=True, default=str) if key_payload else None
        return await cache.wrap(
            source="patentsview",
            method=method.upper(),
            url=path,
            body=body,
            call=lambda: self._request_uncached(method, path, ok_on_404=ok_on_404, **kwargs),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_not_exception_type(
            (
                AuthenticationError,
                ConfigurationError,
                asyncio.CancelledError,
                SourceUnavailableError,
            )
        ),
    )
    async def _request_uncached(
        self, method: str, path: str, *, ok_on_404: bool = False, **kwargs
    ) -> dict:
        """Underlying live HTTP request — retried via tenacity, never cached here."""
        self._require_valid_key()
        async with self._limiter:
            resp = await self._client.request(method, path, **kwargs)
            if resp.status_code in (401, 403):
                raise AuthenticationError(
                    "USPTO ODP API key is invalid or lacks access",
                    source="patentsview",
                )
            if resp.status_code == 429:
                logger.warning("uspto_odp_rate_limited")
                raise httpx.HTTPStatusError("Rate limited", request=resp.request, response=resp)
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("api_404_semantic_empty", source="patentsview")
                    return {}
                raise SourceUnavailableError(
                    "patentsview",
                    f"404 on {path}",
                    status_code=404,
                )
            resp.raise_for_status()
            return cast("dict", resp.json())

    async def search_patents(
        self,
        query: str,
        fields: list[str] | None = None,
        size: int = 100,
        sort: list[dict] | None = None,
        *,
        ok_on_404: bool = True,
    ) -> list[dict]:
        """Search patents with a Lucene query string.

        Args:
            query: Lucene query (e.g. 'applicationMetaData.inventionTitle:aspirin')
            fields: Ignored — ODP endpoint does not support field selection.
            size: Number of results (max 500 per page).
            sort: Ignored — ODP endpoint uses default relevance ordering.

        Returns:
            List of normalised patent result dicts.

        Note:
            The ODP API returns HTTP 404 with "No matching records found" when a
            search has zero results. ok_on_404=True (the default) treats this as
            an empty result set rather than a source error.
        """
        body = build_search_request_params(query, fields, size=size, sort=sort)
        data = await self._request("POST", _SEARCH_PATH, json=body, ok_on_404=ok_on_404)
        return extract_patents(data)

    async def search_by_cpc(
        self,
        cpc_prefix: str,
        keywords: list[str] | None = None,
        size: int = 100,
    ) -> list[dict]:
        """Search patents by CPC code prefix, optionally filtered by title keywords."""
        query = build_cpc_search_query(cpc_prefix, keywords)
        return await self.search_patents(query, fields=DEFAULT_CPC_FIELDS, size=size)

    async def search_by_assignee(
        self,
        assignee_name: str,
        size: int = 100,
    ) -> list[dict]:
        """Search patents by assignee organisation name."""
        query = build_assignee_search_query(assignee_name)
        return await self.search_patents(query, fields=DEFAULT_ASSIGNEE_FIELDS, size=size)

    async def get_patent(self, patent_id: str) -> dict:
        """Get metadata for a single granted patent by US patent number."""
        query = build_patent_query(patent_id)
        results = await self.search_patents(
            query, fields=DEFAULT_PATENT_DETAIL_FIELDS, size=1, ok_on_404=True
        )
        return extract_first_patent(results)

    async def get_patent_citations(self, patent_id: str) -> list[dict]:
        """Get backward citations for a patent.

        Note: the ODP file wrapper endpoint does not expose citation networks.
        Returns an empty list; use BigQuery or EPO OPS for citation data.
        """
        del patent_id
        return extract_patent_citations([])

    async def get_patent_claims_text(self, patent_id: str) -> str:
        """Get claims text for a granted patent.

        The USPTO ODP file wrapper endpoint does not return claims text.
        BigQuery is the primary source; EPO OPS covers EP/WO patents.
        """
        del patent_id
        return ""

    async def search_by_compound_keywords(
        self,
        compound_name: str,
        synonyms: list[str] | None = None,
        cpc_prefix: str = "A61K",
        size: int = 100,
    ) -> list[dict]:
        """Search patents by compound name and synonyms in invention titles.

        Combines title keyword search with CPC class filtering for
        pharmaceutical relevance.
        """
        query = build_compound_keyword_query(
            compound_name,
            synonyms,
            cpc_prefix=cpc_prefix,
        )
        return await self.search_patents(
            query,
            fields=DEFAULT_COMPOUND_KEYWORD_FIELDS,
            size=size,
        )
