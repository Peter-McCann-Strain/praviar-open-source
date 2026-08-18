"""Semantic Scholar Graph API client — scholarly prior art search.

Searches for academic papers that may constitute prior art for patent
invalidity analysis. Request pacing uses a conservative local cap.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

logger = structlog.get_logger()

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# Fields to request from the API
_PAPER_FIELDS = (
    "paperId,title,abstract,year,publicationDate,authors,journal,externalIds,citationCount"
)
_LOCAL_RATE_CAP_THRESHOLD = 1.0
_CONSERVATIVE_LOCAL_REQUESTS_PER_SECOND = 0.8


def _effective_requests_per_second(configured_rate: float) -> float:
    """Return the bounded local request rate used by this client."""
    return min(float(configured_rate), _CONSERVATIVE_LOCAL_REQUESTS_PER_SECOND)


def _build_rate_limiter(configured_rate: float) -> AsyncLimiter:
    effective_rate = _effective_requests_per_second(configured_rate)
    return AsyncLimiter(max_rate=1, time_period=1 / effective_rate)


class _RateLimitError(Exception):
    """Raised on 429 to trigger rate-limit-specific retry."""

    def __init__(self, retry_after: float = 0):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


def _wait_for_rate_limit(retry_state: RetryCallState) -> float:
    """Custom wait function that respects the Retry-After header fully.

    Falls back to exponential jitter if no Retry-After was captured.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RateLimitError) and exc.retry_after > 0:
        # Respect the server's Retry-After header with NO cap
        logger.debug(
            "semantic_scholar_wait_retry_after",
            retry_after_s=exc.retry_after,
            attempt=retry_state.attempt_number,
        )
        return exc.retry_after

    # Fallback: exponential jitter for transient errors
    return wait_exponential_jitter(initial=2, max=60)(retry_state)


class SemanticScholarClient(AsyncClientMixin):
    """Async client for the Semantic Scholar Graph API.

    Searches academic papers for prior art discovery.
    Optionally requires an API key for higher rate limits.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._api_key = settings.semantic_scholar_api_key
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
            logger.debug("semantic_scholar_client_init", status="authenticated")
        else:
            logger.debug("semantic_scholar_client_init", status="unauthenticated")
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
        self._effective_requests_per_second = _effective_requests_per_second(
            settings.semantic_scholar_requests_per_second
        )
        if settings.semantic_scholar_requests_per_second >= _LOCAL_RATE_CAP_THRESHOLD:
            logger.info(
                "semantic_scholar_rate_limit_capped",
                configured_rps=settings.semantic_scholar_requests_per_second,
                effective_rps=self._effective_requests_per_second,
            )
        self._limiter = _build_rate_limiter(settings.semantic_scholar_requests_per_second)

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _get(
        self,
        path: str,
        params: dict | None = None,
        *,
        ok_on_404: bool = False,
    ) -> dict:
        """Rate-limited GET request to Semantic Scholar.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the query params into the body hash so distinct
        queries to the same path key distinctly. Cache hits bypass tenacity
        (and therefore the 429 retry-after handling) — we only retry live
        calls. Exceptions propagate unrecorded.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, params=params, ok_on_404=ok_on_404)
        body = json.dumps(params, sort_keys=True) if params else None
        return await cache.wrap(
            source="semantic_scholar",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_uncached(path, params=params, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(8),
        wait=_wait_for_rate_limit,
        retry=(
            retry_if_exception_type(_RateLimitError)
            | retry_if_not_exception_type(
                (
                    AuthenticationError,
                    asyncio.CancelledError,
                    SourceUnavailableError,
                    _RateLimitError,
                )
            )
        ),
    )
    async def _get_uncached(
        self,
        path: str,
        params: dict | None = None,
        *,
        ok_on_404: bool = False,
    ) -> dict:
        """Underlying live HTTP GET — retries via tenacity, never cached here.

        Single retry decorator handles both:
        - 429 rate limiting (respects Retry-After header, up to 8 attempts)
        - Transient errors like 5xx and timeouts
        AuthenticationError is never retried.

        Args:
            ok_on_404: When True, a 404 is a legitimate "no such paper"
                lookup result and returns an empty dict. When False (the
                default, for search endpoints), a 404 raises
                ``SourceUnavailableError`` so the orchestrator can mark the
                source as FAILED.
        """
        logger.debug("semantic_scholar_request", method="GET")
        async with self._limiter:
            resp = await self._client.get(path, params=params or {})
            if resp.status_code in (401, 403):
                logger.error(
                    "semantic_scholar_auth_rejected",
                    status_code=resp.status_code,
                )
                raise AuthenticationError(
                    "Semantic Scholar API key is invalid",
                    source="semantic_scholar",
                )
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("semantic_scholar_404_semantic_empty")
                    return {}
                raise SourceUnavailableError("semantic_scholar", f"404 on {path}", status_code=404)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                logger.warning(
                    "semantic_scholar_rate_limited",
                    retry_after=retry_after,
                )
                # Raise with the Retry-After value — tenacity's
                # _wait_for_rate_limit will honor the full duration.
                # Do NOT sleep here to avoid double-waiting.
                raise _RateLimitError(retry_after)
            resp.raise_for_status()
            logger.debug("semantic_scholar_response_ok")
            return cast("dict", resp.json())

    async def search_papers(
        self,
        query: str,
        *,
        year_before: int | None = None,
        fields_of_study: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """Search for papers matching a text query.

        Args:
            query: Search text (compound name, reaction, etc.).
            year_before: Only return papers published before this year.
            fields_of_study: Filter by S2 fields (e.g. "Chemistry").
            max_results: Maximum papers to return.

        Returns:
            List of paper dicts with S2 fields.
        """
        logger.debug(
            "semantic_scholar_search_start",
            year_before=year_before,
            max_results=max_results,
        )
        all_results: list[dict] = []
        page_size = min(max_results, 100)
        offset = 0
        total_available = 0

        while len(all_results) < max_results:
            params: dict[str, str] = {
                "query": query,
                "fields": _PAPER_FIELDS,
                "limit": str(page_size),
                "offset": str(offset),
            }
            if year_before is not None:
                params["year"] = f"-{year_before}"
            if fields_of_study:
                params["fieldsOfStudy"] = ",".join(fields_of_study)

            data = await self._get("/paper/search", params=params)
            page = data.get("data", [])
            if not page:
                break
            all_results.extend(page)

            total_available = data.get("total", len(all_results))
            logger.debug(
                "semantic_scholar_search_page",
                offset=offset,
                page_count=len(page),
                total_so_far=len(all_results),
                total_available=total_available,
            )
            if len(all_results) >= total_available:
                break
            if len(page) < page_size:
                break
            offset += page_size

        if len(all_results) > max_results:
            logger.warning(
                "semantic_scholar_results_truncated",
                requested=max_results,
                available=total_available,
            )
        logger.debug(
            "semantic_scholar_search_complete",
            total_results=len(all_results[:max_results]),
        )
        return all_results[:max_results]

    async def get_paper(self, paper_id: str) -> dict:
        """Get detailed information about a specific paper.

        Args:
            paper_id: Semantic Scholar paper ID, DOI, or other external ID.

        Returns:
            Paper dict with requested fields, or empty dict if not found.
        """
        logger.debug("semantic_scholar_get_paper")
        params = {"fields": _PAPER_FIELDS}
        return await self._get(f"/paper/{paper_id}", params=params, ok_on_404=True)
