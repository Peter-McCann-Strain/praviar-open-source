"""Lens.org API client — patent-to-scholarly and scholarly-to-patent links.

Lens uniquely links patents and scholarly works, making it valuable for
finding scholarly prior art cited by patents and vice versa.
Requires an API key from lens.org.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.lens_queries import (
    build_patent_search_payload,
    build_scholarly_search_payload,
)
from praviar_pipeline.clients.lens_results import normalize_patent_results
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

logger = structlog.get_logger()

BASE_URL = "https://api.lens.org"


class LensClient(AsyncClientMixin):
    """Async client for the Lens.org API.

    Links patents to scholarly works and vice versa.
    Requires a free or institutional API key.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._api_key = settings.lens_api_key
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
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
            max_rate=settings.lens_requests_per_second,
            time_period=1,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _post(self, path: str, payload: dict, *, ok_on_404: bool = False) -> dict:
        """Rate-limited POST request to Lens.org.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live call is wrapped so the response is recorded/replayed. The
        cache key folds the JSON-serialised payload into the request body so
        distinct searches key distinctly. Cache hits bypass tenacity — we
        only retry live calls, not deterministic replays. Exceptions
        (including :class:`AuthenticationError` and
        :class:`SourceUnavailableError`) propagate unrecorded.
        """
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._post_uncached(path, payload, ok_on_404=ok_on_404)
        body = json.dumps(payload, sort_keys=True)
        return await cache.wrap(
            source="lens",
            method="POST",
            url=path,
            body=body,
            call=lambda: self._post_uncached(path, payload, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_not_exception_type(
            (AuthenticationError, asyncio.CancelledError, SourceUnavailableError)
        ),
    )
    async def _post_uncached(self, path: str, payload: dict, *, ok_on_404: bool = False) -> dict:
        """Underlying live HTTP POST — retries via tenacity, never cached here."""
        async with self._limiter:
            resp = await self._client.post(
                path,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError(
                    "Lens.org API key is invalid or missing",
                    source="lens",
                )
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("api_404_semantic_empty", source="lens")
                    return {}
                raise SourceUnavailableError(
                    "lens",
                    f"404 on {path}",
                    status_code=404,
                )
            resp.raise_for_status()
            return cast("dict", resp.json())

    async def search_scholarly_by_patent(
        self,
        patent_id: str,
        *,
        max_results: int = 20,
    ) -> list[dict]:
        """Find scholarly works cited by or citing a patent.

        Args:
            patent_id: Patent document number (e.g. "US7851188B2").
            max_results: Maximum scholarly works to return.

        Returns:
            List of scholarly work dicts from Lens.
        """
        all_results: list[dict] = []
        page_size = min(max_results, 50)
        offset = 0

        while len(all_results) < max_results:
            payload = build_scholarly_search_payload(
                patent_id=patent_id,
                page_size=page_size,
                offset=offset,
            )
            data = await self._post("/scholarly/search", payload=payload)
            page = data.get("data", [])
            if not page:
                break
            all_results.extend(page)

            total = data.get("total", len(all_results))
            if len(all_results) >= total or len(page) < page_size:
                break
            offset += page_size

        if len(all_results) > max_results:
            logger.warning(
                "lens_results_truncated",
                requested=max_results,
                fetched=len(all_results),
            )
        return all_results[:max_results]

    async def search_patents(
        self,
        keywords: list[str],
        jurisdictions: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict]:
        """Search the Lens patent collection by keywords.

        Args:
            keywords: Terms to search across title, abstract, and claims.
            jurisdictions: Optional list of jurisdiction codes (e.g. ["US", "EP"]).
            max_results: Maximum patents to return (default from settings).

        Returns:
            List of normalized patent dicts.
        """
        settings = get_settings()
        if max_results is None:
            max_results = settings.lens_max_patent_results

        all_results: list[dict] = []
        page_size = min(max_results, 50)
        offset = 0

        while len(all_results) < max_results:
            payload = build_patent_search_payload(
                keywords=keywords,
                jurisdictions=jurisdictions,
                page_size=page_size,
                offset=offset,
            )
            data = await self._post("/patent/search", payload=payload)
            page = data.get("data", [])
            if not page:
                break
            all_results.extend(page)

            total = data.get("total", len(all_results))
            if len(all_results) >= total or len(page) < page_size:
                break
            offset += page_size

        normalized = normalize_patent_results(
            hits=all_results,
            max_results=max_results,
        )

        logger.info(
            "lens_patent_search_complete",
            jurisdictions=jurisdictions,
            results=len(normalized),
        )
        return normalized

    async def search_patents_by_compound(
        self,
        compound_name: str,
        synonyms: list[str],
        max_results: int | None = None,
    ) -> list[dict]:
        """Search patents by compound name and synonyms.

        Convenience method that builds keywords from the compound name
        and its synonyms, then delegates to :meth:`search_patents`.

        Args:
            compound_name: Primary compound name.
            synonyms: Alternative names / synonyms for the compound.
            max_results: Maximum patents to return (default from settings).

        Returns:
            List of normalized patent dicts.
        """
        keywords = [compound_name, *synonyms]
        return await self.search_patents(
            keywords=keywords,
            max_results=max_results,
        )
