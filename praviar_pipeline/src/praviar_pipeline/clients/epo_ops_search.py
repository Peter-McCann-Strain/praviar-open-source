"""Search orchestration helpers for the EPO OPS client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from praviar_pipeline.clients.base import cached_request
from praviar_pipeline.clients.epo_ops_parsing import parse_search_results
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from aiolimiter import AsyncLimiter


async def search_published_data(
    *,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    token: str,
    cql_query: str,
    max_results: int,
    logger,
    ok_on_404: bool = True,
) -> list[dict]:
    """Execute an OPS published-data search and parse the results.

    Args:
        ok_on_404: Treat 404 as "no results found" (semantic empty). EPO OPS
            normally returns 200 with zero hits, but has been observed to 404
            on queries with no matches — honour that as empty.
    """
    if max_results > 100:
        raise ValueError(
            f"EPO OPS published-data search is capped at 100 results per request; "
            f"got max_results={max_results}. Issue multiple calls with smaller ranges instead."
        )
    range_end = max_results

    async def _live_search() -> list[dict]:
        transport_failure_type: str | None = None
        try:
            async with limiter:
                resp = await client.get(
                    "/published-data/search",
                    params={"q": cql_query},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "X-OPS-Range": f"1-{range_end}",
                    },
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            transport_failure_type = safe_exception_type(exc)

        if transport_failure_type is not None:
            raise SourceUnavailableError("epo_ops", "search request failed") from None
        if resp.status_code == 404:
            if ok_on_404:
                logger.debug("epo_search_no_results")
                return []
            raise SourceUnavailableError(
                "epo_ops",
                "search endpoint returned 404 unexpectedly",
                status_code=404,
            )
        if resp.status_code in (401, 403):
            raise AuthenticationError("EPO OPS token rejected during search", source="epo_ops")
        if resp.status_code == 400:
            logger.warning("epo_search_bad_query", status=resp.status_code)
            return []
        if resp.status_code >= 500:
            raise SourceUnavailableError(
                "epo_ops",
                "search endpoint failed",
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise SourceUnavailableError(
                "epo_ops",
                "search endpoint rejected request",
                status_code=resp.status_code,
            )
        try:
            return parse_search_results(resp.json())
        except (TypeError, ValueError, KeyError):
            raise SourceUnavailableError(
                "epo_ops",
                "search response parsing failed",
            ) from None

    results = await cached_request(
        source="epo_ops_search",
        method="GET",
        url="/published-data/search",
        body=json.dumps(
            {"q": cql_query, "max_results": max_results, "ok_on_404": ok_on_404},
            sort_keys=True,
        ),
        call=_live_search,
    )
    logger.info("epo_search_complete", results=len(results))
    return results
