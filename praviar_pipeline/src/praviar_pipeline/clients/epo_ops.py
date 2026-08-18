"""EPO Open Patent Services (OPS) v3.2 client — legal status & patent families.

Provides access to INPADOC legal events and DOCDB patent families.
Uses OAuth2 with consumer key/secret for authentication.
Request pacing follows the operator-configured local cap.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.epo_ops_client_ops import (
    fetch_all_drawings as _fetch_all_drawings,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    fetch_drawing_page as _fetch_drawing_page,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_biblio as _get_biblio,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_claims_text as _get_claims_text,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_drawing_page_count as _get_drawing_page_count,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_family as _get_family,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_legal_status as _get_legal_status,
)
from praviar_pipeline.clients.epo_ops_client_ops import (
    get_register as _get_register,
)
from praviar_pipeline.clients.epo_ops_helpers import (
    build_ops_auth_client,
    build_ops_client,
    build_ops_limiter,
    refresh_access_token,
    to_docdb_format,
)
from praviar_pipeline.clients.epo_ops_runtime import (
    authenticated_ops_binary_get_impl,
    authenticated_ops_json_get,
    ensure_access_token,
    search_published_data_impl,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError

if TYPE_CHECKING:
    import httpx

logger = structlog.get_logger()

AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
BASE_URL = "https://ops.epo.org/3.2/rest-services"

_to_docdb_format = to_docdb_format


class EPOOPSClient(AsyncClientMixin):
    """Async client for EPO Open Patent Services (OPS) v3.2.

    Provides INPADOC legal status and DOCDB patent family data.
    Requires consumer key + secret from developers.epo.org.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._consumer_key = settings.ops_consumer_key
        self._consumer_secret = settings.ops_consumer_secret

        if not self._consumer_key or not self._consumer_secret:
            logger.warning(
                "epo_ops_disabled",
                has_key=bool(self._consumer_key),
                has_secret=bool(self._consumer_secret),
            )
        else:
            logger.debug("epo_ops_client_init", status="enabled")

        self._client = client or build_ops_client(base_url=BASE_URL, settings=settings)
        self._limiter = build_ops_limiter(requests_per_minute=int(settings.ops_requests_per_minute))
        # Token cache
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _ensure_token(self) -> str:
        """Obtain or refresh the OAuth2 access token."""
        return await ensure_access_token(
            self,
            auth_url=AUTH_URL,
            build_ops_auth_client_fn=build_ops_auth_client,
            refresh_access_token_fn=refresh_access_token,
            logger=logger,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15),
        retry=retry_if_not_exception_type((AuthenticationError, asyncio.CancelledError)),
    )
    async def _get(self, path: str, *, ok_on_404: bool = False) -> dict:
        """Rate-limited, authenticated GET request to OPS.

        Set ``ok_on_404=True`` for endpoints where 404 is a semantic empty
        (family/biblio/register of a patent with no matching record). Default
        False treats 404 as a source failure and raises
        ``SourceUnavailableError`` so the orchestrator can record a FAILED
        SourceHealthEntry.
        """
        return await authenticated_ops_json_get(
            self,
            path=path,
            logger=logger,
            ok_on_404=ok_on_404,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15),
        retry=retry_if_not_exception_type((AuthenticationError, asyncio.CancelledError)),
    )
    async def search_published_data(
        self,
        cpc_codes: list[str] | None = None,
        claim_keywords: list[str] | None = None,
        applicants: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """Search EPO published data using CQL (EPO query language).

        Combines CPC codes, claim text keywords, and applicant names into a
        single CQL query against the configured EPO OPS published-data source.
        Source success does not imply complete jurisdictional coverage.

        EPO OPS search supports:
        - cpc= : CPC classification codes
        - cl=  : claims text
        - ta=  : title/abstract
        - pa=  : applicant (assignee)

        Returns list of dicts with publication_number, title, applicant fields.
        """
        return await search_published_data_impl(
            self,
            cpc_codes=cpc_codes,
            claim_keywords=claim_keywords,
            applicants=applicants,
            max_results=max_results,
            logger=logger,
        )

    async def get_legal_status(self, patent_id: str) -> list[dict]:
        """Get INPADOC legal events for a patent.

        Returns a list of legal event dicts with keys:
        event_date, event_code, event_description, country.
        """
        return await _get_legal_status(self, patent_id)

    async def get_family(self, patent_id: str) -> dict:
        """Get DOCDB patent family for a patent.

        Returns a dict with keys:
        family_id, members (list of dicts with country, doc_number, kind).
        """
        return await _get_family(self, patent_id)

    # --- Bibliographic Data ---

    async def get_biblio(self, patent_id: str) -> dict:
        """Get full bibliographic data for a patent.

        Includes title, abstract, applicants, inventors, and classifications.
        """
        return await _get_biblio(self, patent_id)

    async def get_claims_text(self, patent_id: str) -> str:
        """Get claims text for a patent from EPO OPS."""
        return await _get_claims_text(self, patent_id)

    async def get_register(self, patent_id: str) -> dict:
        """Get EP register data: designated states, status, opposition, divisionals.

        Returns structured register information for EP patents.
        """
        return await _get_register(self, patent_id)

    # --- Patent Drawing Image Fetch ---

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15),
        retry=retry_if_not_exception_type((AuthenticationError, asyncio.CancelledError)),
    )
    async def _get_binary(
        self,
        path: str,
        accept: str = "image/png",
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> bytes | None:
        """Rate-limited, authenticated GET for binary content (images, PDFs)."""
        return await authenticated_ops_binary_get_impl(
            self,
            path=path,
            accept=accept,
            headers=headers,
            max_bytes=max_bytes,
            logger=logger,
        )

    async def get_drawing_page_count(self, patent_id: str) -> int:
        """Get the number of drawing pages available for a patent.

        Uses the images inquiry endpoint to check page availability.
        Returns 0 if no drawings are available or patent not found.
        """
        return await _get_drawing_page_count(self, patent_id)

    async def fetch_drawing_page(
        self,
        patent_id: str,
        page: int = 1,
        image_format: str = "image/png",
    ) -> bytes | None:
        """Fetch a single drawing page image from EPO OPS.

        Args:
            patent_id: Patent identifier (e.g., "US7851188B2").
            page: Page number (1-indexed).
            image_format: MIME type — "image/png" or "image/tiff".

        Returns:
            Raw image bytes, or None if not available.
        """
        return await _fetch_drawing_page(
            self,
            patent_id,
            page=page,
            image_format=image_format,
        )

    async def fetch_all_drawings(
        self,
        patent_id: str,
        max_pages: int = 0,
        image_format: str = "image/png",
        *,
        fail_closed: bool = False,
    ) -> list[tuple[int, bytes]]:
        """Fetch all drawing pages for a patent.

        Args:
            patent_id: Patent identifier.
            max_pages: Maximum pages to fetch (0 = unlimited).
            image_format: MIME type for images.
            fail_closed: Raise when any advertised page cannot be acquired.

        Returns:
            List of (page_number, image_bytes) tuples.
        """
        return await _fetch_all_drawings(
            self,
            patent_id,
            max_pages=max_pages,
            image_format=image_format,
            fail_closed=fail_closed,
        )
