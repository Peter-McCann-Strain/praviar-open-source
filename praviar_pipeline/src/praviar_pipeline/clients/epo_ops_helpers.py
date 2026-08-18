"""Pure helpers for the EPO OPS client."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import TYPE_CHECKING

import httpx
from aiolimiter import AsyncLimiter

from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# Regex to convert patent IDs to DOCDB dot-separated format:
#   US7851188B2       -> US.7851188.B2
#   US-2024294466-A1  -> US.2024294466.A1
#   EP1234567A1       -> EP.1234567.A1
_PATENT_RE = re.compile(r"^([A-Z]{2})-?(\d+)-?([A-Z]\d?)$")


def _ascii_fold(text: str) -> str:
    """Fold accented characters to ASCII equivalents (e.g. é→e, ñ→n).

    EPO OPS returns HTTP 500 for CQL queries containing non-ASCII characters
    in operator values such as pa="" (assignee). NFKD decomposition followed
    by ASCII encoding drops combining marks while preserving the base letter.
    """
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _cql_value(text: str) -> str:
    """Strip characters that would break EPO CQL double-quoted operator values."""
    return text.replace('"', "")


def to_docdb_format(patent_id: str) -> str:
    """Convert a patent ID to DOCDB format CC.NNNNNNN.KK."""
    cleaned = patent_id.strip()
    m = _PATENT_RE.match(cleaned)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return cleaned


def to_epodoc_publication_format(patent_id: str) -> str:
    """Convert an EP publication identifier to the Register's EPODOC input.

    OPS Register retrieval supports EPODOC input only.  A publication number in
    that format identifies the initial publication without a DOCDB kind code.
    """
    cleaned = patent_id.strip().upper()
    match = _PATENT_RE.fullmatch(cleaned)
    if match and match.group(1) == "EP":
        return f"EP{match.group(2)}"
    raise ValueError("OPS Register retrieval requires an EP publication identifier")


def build_cql_query(
    cpc_codes: list[str] | None = None,
    claim_keywords: list[str] | None = None,
    applicants: list[str] | None = None,
) -> str:
    """Build the EPO CQL query from supported filters."""
    parts: list[str] = []

    if cpc_codes:
        cpc_parts = " OR ".join(f'cpc="{_cql_value(code)}"' for code in cpc_codes[:5])
        parts.append(f"({cpc_parts})")

    if claim_keywords:
        kw_parts = " OR ".join(f'cl="{_cql_value(kw)}"' for kw in claim_keywords[:5])
        parts.append(f"({kw_parts})")

    if applicants:
        pa_parts = " OR ".join(f'pa="{_cql_value(_ascii_fold(name))}"' for name in applicants[:5])
        parts.append(f"({pa_parts})")

    return " AND ".join(parts)


def build_drawing_page_path(docdb: str, page: int, image_format: str) -> str:
    """Build the OPS path for a specific drawing page."""
    return f"/published-data/publication/docdb/{docdb}/images"


def build_drawing_range_header(page: int) -> str:
    """Build the OPS Range header value for a specific drawing page."""
    return f"{page}-{page}"


def build_ops_client(
    *,
    base_url: str,
    settings,
) -> httpx.AsyncClient:
    """Build the long-lived authenticated OPS client."""
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(settings.http_timeout_default, connect=settings.http_connect_timeout),
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive,
        ),
    )


def build_ops_limiter(*, requests_per_minute: int) -> AsyncLimiter:
    """Build the OPS rate limiter from settings."""
    return AsyncLimiter(max_rate=requests_per_minute, time_period=60)


def build_ops_auth_client(*, settings) -> httpx.AsyncClient:
    """Build the short-lived auth client used for token refreshes."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_default, connect=settings.http_connect_timeout)
    )


async def refresh_access_token(
    *,
    auth_client: httpx.AsyncClient,
    auth_url: str,
    consumer_key: str,
    consumer_secret: str,
    request_access_token_fn: Callable[..., Awaitable[dict]],
    logger,
) -> tuple[str, float]:
    """Fetch a new access token and compute its refresh deadline."""
    logger.debug("epo_ops_token_request")
    data = await request_access_token_fn(
        auth_client=auth_client,
        auth_url=auth_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
    )

    access_token = data.get("access_token")
    if not access_token:
        logger.error(
            "epo_ops_token_missing_in_response",
            response_keys=list(data.keys()),
        )
        raise AuthenticationError(
            "EPO OPS token response missing access token",
            source="epo_ops",
        )

    expires_in = int(data.get("expires_in", 1200))
    expires_at = time.monotonic() + expires_in - 60
    logger.debug(
        "epo_ops_token_refreshed",
        expires_in_s=expires_in,
        effective_ttl_s=expires_in - 60,
    )
    return access_token, expires_at


async def collect_drawings(
    *,
    patent_id: str,
    pages_to_fetch: int,
    image_format: str,
    fetch_drawing_page: Callable[[str, int, str], Awaitable[bytes | None]],
    logger,
    fail_closed: bool = False,
) -> list[tuple[int, bytes]]:
    """Fetch drawing pages, rejecting partial acquisition in live evidence mode."""
    drawings: list[tuple[int, bytes]] = []
    failed_pages = 0
    for page_num in range(1, pages_to_fetch + 1):
        try:
            img_bytes = await fetch_drawing_page(patent_id, page_num, image_format)
            if img_bytes:
                drawings.append((page_num, img_bytes))
            else:
                failed_pages += 1
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            failed_pages += 1
            logger.warning(
                "epo_drawing_page_failed",
                page=page_num,
                error_type=safe_exception_type(exc),
            )
            continue

    logger.info(
        "epo_drawings_fetched",
        pages_fetched=len(drawings),
        pages_failed=failed_pages,
    )
    if fail_closed and failed_pages:
        raise SourceUnavailableError(
            "epo_ops",
            "one or more advertised drawing pages could not be acquired",
        )
    return drawings
