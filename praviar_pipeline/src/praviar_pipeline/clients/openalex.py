"""OpenAlex API client for scholarly-metadata prior-art search.

Live requests require an operator-provided API key. Request pacing is governed
by the configured local cap; provider budgets and limits remain an external
deployment concern rather than a hard-coded runtime claim.
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
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import (
    AuthenticationError,
    ConfigurationError,
    SourceUnavailableError,
)

logger = structlog.get_logger()

BASE_URL = "https://api.openalex.org"


class _RateLimitError(Exception):
    """Raised on 429 to trigger rate-limit-specific retry."""

    def __init__(self, retry_after: float = 0):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


def _wait_for_rate_limit(retry_state: RetryCallState) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RateLimitError) and exc.retry_after > 0:
        logger.debug(
            "openalex_wait_retry_after",
            retry_after_s=exc.retry_after,
            attempt=retry_state.attempt_number,
        )
        return exc.retry_after
    return wait_exponential_jitter(initial=1, max=10)(retry_state)


class OpenAlexClient(AsyncClientMixin):
    """Async client for the OpenAlex API.

    Searches scholarly works for prior art discovery.
    Authenticates via api_key query parameter.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._api_key = settings.openalex_api_key.strip()
        if not self._api_key:
            raise ConfigurationError(
                "OpenAlex API key not configured",
                source="openalex",
                step="client",
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
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.openalex_requests_per_second,
            time_period=1,
        )

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
        """Rate-limited GET request to OpenAlex.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the user-supplied query params (NOT the
        api_key) into the body hash so distinct queries key distinctly.
        Cache hits bypass tenacity. Exceptions propagate unrecorded.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, params=params, ok_on_404=ok_on_404)
        # Key on the caller-supplied params only — the api_key is an
        # auth credential, not a logical part of the request.
        body = json.dumps(params, sort_keys=True) if params else None
        return await cache.wrap(
            source="openalex",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_uncached(path, params=params, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=_wait_for_rate_limit,
        retry=retry_if_not_exception_type(
            (AuthenticationError, asyncio.CancelledError, SourceUnavailableError)
        ),
    )
    async def _get_uncached(
        self,
        path: str,
        params: dict | None = None,
        *,
        ok_on_404: bool = False,
    ) -> dict:
        """Underlying live HTTP GET — retries via tenacity, never cached here."""
        query_params = dict(params or {})
        query_params["api_key"] = self._api_key
        async with self._limiter:
            resp = await self._client.get(path, params=query_params)
            if resp.status_code in (401, 403):
                raise AuthenticationError(
                    "OpenAlex API authentication failed",
                    source="openalex",
                )
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("api_404_semantic_empty", source="openalex")
                    return {}
                raise SourceUnavailableError("openalex", f"404 on {path}", status_code=404)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                logger.warning(
                    "openalex_rate_limited",
                    retry_after=retry_after,
                )
                raise _RateLimitError(retry_after)
            resp.raise_for_status()
            return cast("dict", resp.json())

    async def search_works(
        self,
        query: str,
        *,
        year_before: int | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """Search for scholarly works matching a text query.

        Args:
            query: Search text (compound name, reaction, etc.).
            year_before: Only return works published before this year.
            max_results: Maximum works to return.

        Returns:
            List of work dicts from OpenAlex.
        """
        all_results: list[dict] = []
        page_size = min(max_results, 200)
        cursor = "*"
        total_available = 0

        while len(all_results) < max_results:
            params: dict[str, str] = {
                "search": query,
                "per_page": str(page_size),
                "cursor": cursor,
            }
            if year_before is not None:
                params["filter"] = f"publication_year:<{year_before}"

            data = await self._get("/works", params=params)
            page = data.get("results", [])
            if not page:
                break
            all_results.extend(page)

            # OpenAlex uses cursor-based pagination
            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor

        if len(all_results) > max_results:
            logger.warning(
                "openalex_results_truncated",
                requested=max_results,
                available=total_available,
            )
        return all_results[:max_results]
