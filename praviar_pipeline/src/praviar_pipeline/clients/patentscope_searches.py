"""Search helpers for the PatentScope client."""

from __future__ import annotations

import asyncio
from typing import cast

import structlog
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.patentscope_helpers import (
    build_applicant_query,
    build_clir_params,
    build_clir_query,
    build_search_params,
)
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

logger = structlog.get_logger()


class _ThrottleError(Exception):
    """Raised on 429/503 to trigger retriable backoff."""

    def __init__(self, status_code: int, retry_after: float = 0):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"PatentScope throttle {status_code}, retry after {retry_after}s")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_not_exception_type(
        (AuthenticationError, asyncio.CancelledError, SourceUnavailableError)
    ),
)
async def patentscope_get(
    *,
    client,
    limiter,
    path: str,
    params: dict | None = None,
    ok_on_404: bool = True,
) -> dict:
    """Rate-limited, authenticated GET request to PatentScope."""
    async with limiter:
        resp = await client.get(path, params=params)
        if resp.status_code in (401, 403):
            logger.error(
                "patentscope_auth_failed",
                status_code=resp.status_code,
            )
            raise AuthenticationError(
                "PatentScope authentication failed — check username/password",
                source="patentscope",
            )
        if resp.status_code == 404:
            if ok_on_404:
                logger.debug("api_404_not_found", source="patentscope")
                return {}
            logger.warning(
                "patentscope_unexpected_404",
            )
            raise SourceUnavailableError(
                "patentscope",
                f"Unexpected 404 on {path} — endpoint may be misconfigured",
                status_code=404,
            )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            logger.warning(
                "patentscope_rate_limited",
                retry_after=retry_after,
            )
            raise _ThrottleError(429, retry_after)
        if resp.status_code == 503:
            retry_after = float(resp.headers.get("Retry-After", "30"))
            logger.warning(
                "patentscope_service_unavailable",
                retry_after=retry_after,
            )
            raise _ThrottleError(503, retry_after)
        if resp.status_code >= 500:
            logger.error(
                "patentscope_server_error",
                status_code=resp.status_code,
            )
            raise SourceUnavailableError(
                "patentscope",
                f"Server error {resp.status_code} from PatentScope",
                status_code=resp.status_code,
            )
        resp.raise_for_status()
        return cast("dict", resp.json())


async def search_patents_impl(
    *,
    is_configured: bool,
    keywords: list[str],
    jurisdictions: list[str] | None,
    max_results: int | None,
    default_max_results: int,
    build_keyword_query_fn,
    parse_results_fn,
    get_fn,
) -> list[dict]:
    """Search PatentScope for patents by keywords."""
    if not is_configured:
        logger.debug("patentscope_search_skipped")
        return []

    if not keywords:
        return []

    rows = max_results or default_max_results
    query = build_keyword_query_fn(keywords, jurisdictions)
    logger.debug(
        "patentscope_search",
    )

    data = await get_fn("/search", params=build_search_params(query, rows))
    if not data:
        return []

    results = cast("list[dict]", parse_results_fn(data))
    logger.info(
        "patentscope_search_complete",
        jurisdictions=jurisdictions,
        results=len(results),
    )
    return results


async def search_by_applicant_impl(
    *,
    is_configured: bool,
    applicant: str,
    jurisdictions: list[str] | None,
    max_results: int | None,
    default_max_results: int,
    parse_results_fn,
    get_fn,
) -> list[dict]:
    """Search PatentScope by applicant name."""
    if not is_configured:
        logger.debug("patentscope_applicant_search_skipped")
        return []

    if not applicant:
        return []

    rows = max_results or default_max_results
    query = build_applicant_query(applicant, jurisdictions)

    logger.debug(
        "patentscope_applicant_search",
    )

    data = await get_fn("/search", params=build_search_params(query, rows))
    if not data:
        return []

    results = cast("list[dict]", parse_results_fn(data))
    logger.info(
        "patentscope_applicant_search_complete",
        jurisdictions=jurisdictions,
        results=len(results),
    )
    return results


async def cross_lingual_search_impl(
    *,
    is_configured: bool,
    keywords: list[str],
    source_lang: str,
    target_langs: list[str] | None,
    max_results: int | None,
    default_max_results: int,
    parse_results_fn,
    get_fn,
) -> list[dict]:
    """Search PatentScope using CLIR."""
    if not is_configured:
        logger.debug("patentscope_clir_skipped")
        return []

    if not keywords:
        return []

    rows = max_results or default_max_results
    query = build_clir_query(keywords)

    logger.debug(
        "patentscope_clir_search",
        source_lang=source_lang,
        target_langs=target_langs,
    )

    data = await get_fn(
        "/search",
        params=build_clir_params(
            query,
            rows,
            source_lang=source_lang,
            target_langs=target_langs,
        ),
    )
    if not data:
        return []

    results = cast("list[dict]", parse_results_fn(data))
    logger.info(
        "patentscope_clir_complete",
        source_lang=source_lang,
        target_langs=target_langs,
        results=len(results),
    )
    return results
