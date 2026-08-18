"""WIPO PatentScope REST API client with cross-lingual retrieval.

Provides configured access to WIPO PatentScope. Cross-lingual information
retrieval (CLIR) can search non-English records from English-language queries;
the runtime does not infer complete jurisdictional coverage from source health.

Authentication: HTTP Basic Auth with username/password.
Request pacing uses the operator-configured local cap.
"""

from __future__ import annotations

import httpx
import structlog
from aiolimiter import AsyncLimiter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.patentscope_helpers import (
    build_keyword_query,
    parse_results,
)
from praviar_pipeline.clients.patentscope_searches import (
    cross_lingual_search_impl,
    patentscope_get,
    search_by_applicant_impl,
    search_patents_impl,
)
from praviar_pipeline.config import get_settings

logger = structlog.get_logger()

BASE_URL = "https://patentscope.wipo.int/search/en/api"


class PatentScopeClient(AsyncClientMixin):
    """Async client for the WIPO PatentScope REST API.

    Searches the configured PatentScope source, including cross-lingual
    information retrieval (CLIR) for non-English records.
    Requires a WIPO PatentScope account (username + password).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._username = settings.patentscope_username
        self._password = settings.patentscope_password
        self._max_results = settings.patentscope_max_results

        if not self._username or not self._password:
            logger.warning(
                "patentscope_disabled",
                has_username=bool(self._username),
                has_password=bool(self._password),
            )
        else:
            logger.debug(
                "patentscope_client_init",
                status="enabled",
            )

        # Build auth header for Basic Auth
        auth = (
            httpx.BasicAuth(self._username, self._password)
            if self._username and self._password
            else None
        )

        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            auth=auth,
        )
        # Convert rpm to per-minute rate limiter
        self._limiter = AsyncLimiter(
            max_rate=settings.patentscope_requests_per_minute,
            time_period=60,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    def _is_configured(self) -> bool:
        """Check whether credentials are present."""
        return bool(self._username and self._password)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Rate-limited, authenticated GET request to PatentScope.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the JSON-serialised query params into the body
        hash so distinct searches key distinctly. Cache hits bypass tenacity
        — we only retry live calls. Exceptions propagate unrecorded.
        """
        # Inline import — survives the aggressive format hook.
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, params=params)
        body = json.dumps(params, sort_keys=True) if params else None
        return await cache.wrap(
            source="patentscope",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_uncached(path, params=params),
        )

    async def _get_uncached(self, path: str, params: dict | None = None) -> dict:
        """Underlying live HTTP GET — retries via tenacity, never cached here."""
        return await patentscope_get(
            client=self._client,
            limiter=self._limiter,
            path=path,
            params=params,
        )

    def _build_keyword_query(
        self,
        keywords: list[str],
        jurisdictions: list[str] | None = None,
    ) -> str:
        """Build a PatentScope query string from keywords and jurisdictions."""
        return build_keyword_query(keywords, jurisdictions)

    def _parse_results(self, data: dict) -> list[dict]:
        """Parse PatentScope search response into normalized dicts."""
        return parse_results(data)

    async def search_patents(
        self,
        keywords: list[str],
        jurisdictions: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict]:
        """Search PatentScope for patents by keywords across specified jurisdictions.

        Args:
            keywords: Search terms to combine with OR.
            jurisdictions: Optional list of 2-letter country codes to filter by
                (e.g., ["US", "EP", "WO", "JP"]).
            max_results: Maximum results to return. Defaults to config value.

        Returns:
            List of dicts with keys: publication_number, title, abstract,
            filing_date, priority_date, assignees, cpc_codes.
        """
        return await search_patents_impl(
            is_configured=self._is_configured(),
            keywords=keywords,
            jurisdictions=jurisdictions,
            max_results=max_results,
            default_max_results=self._max_results,
            build_keyword_query_fn=self._build_keyword_query,
            parse_results_fn=self._parse_results,
            get_fn=self._get,
        )

    async def search_by_applicant(
        self,
        applicant: str,
        jurisdictions: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict]:
        """Search PatentScope by applicant (assignee) name.

        Args:
            applicant: Applicant/assignee name to search for.
            jurisdictions: Optional list of 2-letter country codes to filter by.
            max_results: Maximum results to return. Defaults to config value.

        Returns:
            List of dicts with same format as search_patents.
        """
        return await search_by_applicant_impl(
            is_configured=self._is_configured(),
            applicant=applicant,
            jurisdictions=jurisdictions,
            max_results=max_results,
            default_max_results=self._max_results,
            parse_results_fn=self._parse_results,
            get_fn=self._get,
        )

    async def cross_lingual_search(
        self,
        keywords: list[str],
        source_lang: str = "EN",
        target_langs: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict]:
        """Search PatentScope using Cross-Lingual Information Retrieval (CLIR).

        Searches in English but finds results published in other languages
        (JP, KR, CN, DE, FR, etc.) using WIPO's machine translation index.

        Args:
            keywords: English-language search terms.
            source_lang: Source language code (default "EN").
            target_langs: Target language codes to search across
                (e.g., ["JA", "KO", "ZH"]). If None, searches all available.
            max_results: Maximum results to return. Defaults to config value.

        Returns:
            List of dicts with same format as search_patents.
        """
        return await cross_lingual_search_impl(
            is_configured=self._is_configured(),
            keywords=keywords,
            source_lang=source_lang,
            target_langs=target_langs,
            max_results=max_results,
            default_max_results=self._max_results,
            parse_results_fn=self._parse_results,
            get_fn=self._get,
        )
