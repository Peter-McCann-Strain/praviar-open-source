"""Tavily web search client — grounding LLM calls with real-time search results.

Used by Step 1.5 (query expansion) to fetch real CPC codes, assignee names,
and production method information before the LLM generates search queries.
This prevents the LLM from hallucinating CPC codes or using stale company names.

Uses the Tavily REST API directly via httpx — no extra SDK dependency.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import structlog
from aiolimiter import AsyncLimiter

from praviar_pipeline.clients.base import AsyncClientMixin, cached_request
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.no_paid_api import assert_paid_api_allowed
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

TAVILY_API_URL = "https://api.tavily.com/search"

# Retry backoff delays (seconds) for 432 rate-limit responses.
_RATE_LIMIT_BACKOFF = (2.0, 4.0, 8.0)


class TavilyClient(AsyncClientMixin):
    """Async Tavily web search client for grounding LLM context."""

    def __init__(self, *, required: bool = False) -> None:
        settings = get_settings()
        self._api_key = settings.tavily_api_key
        if required and not self._api_key:
            raise ConfigurationError(
                "Tavily API key not configured for required query-expansion grounding",
                source="tavily",
                step="query_expansion",
            )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.tavily_requests_per_minute,
            time_period=60,
        )

    @property
    def available(self) -> bool:
        """Whether Tavily is configured with an API key."""
        return bool(self._api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        *,
        required: bool = False,
    ) -> list[dict]:
        """Run a Tavily web search and return result snippets.

        Returns list of dicts with keys: title, url, content (snippet).
        In optional mode, returns an empty list on missing configuration or
        source failure. In required mode, raises configuration/source errors so
        the caller can fail closed.

        432 (dev-tier per-minute rate limit) is retried with exponential backoff
        before degrading. 402 (billing exhausted) is non-retryable.
        """
        if not self._api_key:
            if required:
                raise ConfigurationError(
                    "Tavily API key not configured",
                    source="tavily",
                    step="query_expansion",
                )
            return []

        assert_paid_api_allowed("Tavily")

        failure_type: str | None = None
        failure_status: int | None = None
        for attempt, _ in enumerate((*_RATE_LIMIT_BACKOFF, None), start=0):
            if attempt > 0:
                delay = _RATE_LIMIT_BACKOFF[attempt - 1]
                logger.info(
                    "tavily_rate_limit_retry",
                    attempt=attempt,
                    delay_s=delay,
                )
                await asyncio.sleep(delay)

            try:
                payload = {
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max_results,
                    "include_answer": False,
                }

                async def _live_search(payload: dict = payload) -> list[dict]:
                    async with self._limiter:
                        resp = await self._client.post(
                            TAVILY_API_URL,
                            json=payload,
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    return [
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "content": item.get("content", ""),
                        }
                        for item in data.get("results", [])
                    ]

                results = await cached_request(
                    source="tavily",
                    method="POST",
                    url=TAVILY_API_URL,
                    body=json.dumps(payload, sort_keys=True),
                    call=_live_search,
                )

                logger.debug(
                    "tavily_search_complete",
                    results=len(results),
                )
                return results

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 432:
                    # Dev-tier per-minute rate limit — retry with backoff.
                    continue
                # 402 = billing exhausted; other 4xx/5xx = source error.
                billing_exhausted = status_code == 402
                logger.warning(
                    "tavily_search_failed",
                    error_type=safe_exception_type(exc),
                    status_code=status_code,
                    billing_exhausted=billing_exhausted,
                )
                if required:
                    failure_type = safe_exception_type(exc)
                    failure_status = status_code
                    break
                return []

            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning(
                    "tavily_search_failed",
                    error_type=safe_exception_type(exc),
                )
                if required:
                    failure_type = safe_exception_type(exc)
                    break
                return []

        if failure_type is not None:
            raise SourceUnavailableError(
                "tavily",
                "grounding search failed",
                status_code=failure_status,
            ) from None

        # All retries exhausted for the 432 rate limit. Required grounding must
        # remain a terminal pipeline gap rather than fabricated empty evidence;
        # task retry policy classifies the stable source error separately.
        logger.warning(
            "tavily_search_rate_limit_exhausted",
            attempts=len(_RATE_LIMIT_BACKOFF) + 1,
        )
        if required:
            raise SourceUnavailableError(
                "tavily",
                "grounding search rate limit exhausted",
                status_code=432,
            ) from None
        return []

    async def close(self) -> None:
        await self._client.aclose()
