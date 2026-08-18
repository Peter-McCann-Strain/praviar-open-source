"""PubChem PUG REST API client — compound resolution and patent links."""

from __future__ import annotations

import json

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.http_identity import source_user_agent
from praviar_pipeline.clients.pubchem_client_ops import (
    get_patent_links,
    get_patent_links_for_cids,
    get_properties_for_cids,
    get_synonyms,
    poll_list_key,
    resolve_by_inchikey,
    resolve_by_name,
    resolve_by_smiles,
    similarity_search,
    substructure_search_cids,
)
from praviar_pipeline.clients.pubchem_helpers import extract_sdq_rows
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.response_cache import CacheMode, get_current_cache
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
SDQ_URL = "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi"


def _is_retryable_pubchem_error(exc: BaseException) -> bool:
    """Retry only failures that can plausibly recover without changing the request."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, SourceUnavailableError):
        return exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or status_code >= 500
    return False


class PubChemClient(AsyncClientMixin):
    """Async client for PubChem PUG REST API.

    Request pacing follows the operator-configured local cap.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            headers={"User-Agent": source_user_agent(settings.source_contact_email)},
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.pubchem_requests_per_second,
            time_period=1,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _get(self, path: str, *, ok_on_404: bool = False) -> dict:
        """Rate-limited GET request to PubChem.

        By default a 404 is treated as a source failure and raises
        :class:`SourceUnavailableError`. Callers performing a semantic
        lookup where "not found" is a legitimate empty result (e.g.,
        resolving a compound name/SMILES/InChIKey) should pass
        ``ok_on_404=True`` to receive an empty dict instead.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed
        via ``set_current_cache``, the live HTTP call is wrapped so the
        response is recorded / replayed. Cache hits bypass tenacity (we only
        want to retry live calls, not deterministic replays). Exceptions from
        the underlying call — including :class:`SourceUnavailableError` —
        propagate unrecorded.
        """
        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, ok_on_404=ok_on_404)
        return await cache.wrap(
            source="pubchem",
            method="GET",
            url=path,
            body=None,
            call=lambda: self._get_uncached(path, ok_on_404=ok_on_404),
        )

    @retry(
        retry=retry_if_exception(_is_retryable_pubchem_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        reraise=True,
    )
    async def _get_uncached(self, path: str, *, ok_on_404: bool = False) -> dict:
        """Underlying live HTTP GET — retries via tenacity, never cached here."""
        async with self._limiter:
            resp = await self._client.get(path)
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("api_404_not_found", source="pubchem")
                    return {}
                logger.warning("api_404_source_failure", source="pubchem")
                raise SourceUnavailableError(
                    "pubchem",
                    "request returned 404",
                    status_code=404,
                )
            if resp.status_code == 503:
                logger.warning(
                    "pubchem_server_busy",
                    status=503,
                    content_type=resp.headers.get("content-type", ""),
                )
            if resp.status_code >= 400:
                raise SourceUnavailableError(
                    "pubchem",
                    "request failed",
                    status_code=resp.status_code,
                )
            parse_failed = False
            try:
                payload = resp.json()
            except (TypeError, ValueError):
                parse_failed = True
                payload = None
            if parse_failed or not isinstance(payload, dict):
                raise SourceUnavailableError("pubchem", "response parsing failed") from None
            return payload

    async def resolve_by_name(self, name: str) -> dict:
        """Resolve a compound name to CID and properties."""
        return await resolve_by_name(self, name)

    async def resolve_by_smiles(self, smiles: str) -> dict:
        """Resolve a SMILES string to CID and properties."""
        return await resolve_by_smiles(self, smiles)

    async def resolve_by_inchikey(self, inchikey: str) -> dict:
        """Resolve an InChIKey to CID and properties."""
        return await resolve_by_inchikey(self, inchikey)

    async def get_synonyms(self, cid: int) -> list[str]:
        """Get all synonyms for a compound."""
        return await get_synonyms(self, cid)

    async def get_patent_links(self, cid: int) -> list[str]:
        """Get patent IDs linked to a compound via PubChem's cross-references."""
        return await get_patent_links(self, cid)

    async def get_patent_links_for_cids(self, cids: list[int]) -> list[dict]:
        """Get bounded CID-to-patent mappings for a corpus expansion result."""
        return await get_patent_links_for_cids(self, cids)

    async def substructure_search_cids(
        self,
        smiles: str,
        *,
        max_records: int = 200,
        max_seconds: int = 60,
    ) -> list[int]:
        """Return PubChem CIDs containing the supplied query scaffold."""
        return await substructure_search_cids(
            self,
            smiles,
            max_records=max_records,
            max_seconds=max_seconds,
        )

    # ── SDQ API (rich patent metadata) ────────────────────────────────

    async def _sdq_get(self, query: dict) -> dict:
        """Rate-limited GET request to PubChem SDQ API.

        SDQ is a server-side patent-metadata endpoint we query with CIDs we
        already know exist; a 404 here indicates the endpoint is unavailable,
        not a semantic empty result, so it is raised as
        :class:`SourceUnavailableError`.

        Cache semantics mirror :meth:`_get` — when a cache is installed, the
        live call is wrapped; cache hits skip tenacity; exceptions propagate
        unrecorded. The cache key folds the JSON-serialised query into the
        request body so different queries key differently.
        """
        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._sdq_get_uncached(query)
        body = json.dumps(query, sort_keys=True)
        return await cache.wrap(
            source="pubchem_sdq",
            method="GET",
            url=SDQ_URL,
            body=body,
            call=lambda: self._sdq_get_uncached(query),
        )

    @retry(
        retry=retry_if_exception(_is_retryable_pubchem_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        reraise=True,
    )
    async def _sdq_get_uncached(self, query: dict) -> dict:
        """Underlying live SDQ GET — retries via tenacity, never cached here."""
        settings = get_settings()
        async with self._limiter:
            resp = await self._client.get(
                SDQ_URL,
                params={"infmt": "json", "outfmt": "json", "query": json.dumps(query)},
                timeout=httpx.Timeout(
                    settings.http_timeout_long, connect=settings.http_connect_timeout
                ),
            )
            if resp.status_code == 404:
                logger.warning("api_404_source_failure", source="pubchem_sdq")
                raise SourceUnavailableError(
                    "pubchem_sdq",
                    f"404 on {SDQ_URL}",
                    status_code=404,
                )
            if resp.status_code == 503:
                logger.warning("pubchem_server_busy", status=503)
            resp.raise_for_status()
            try:
                payload = resp.json()
            except (TypeError, ValueError):
                raise SourceUnavailableError(
                    "pubchem_sdq",
                    "response parsing failed",
                ) from None
            if not isinstance(payload, dict):
                raise SourceUnavailableError(
                    "pubchem_sdq",
                    "response schema is invalid",
                )
            return payload

    async def sdq_search_patents(
        self,
        cid: int,
        jurisdiction: str = "*",
        max_patents: int | None = None,
    ) -> list[dict]:
        """Fetch rich patent metadata via PubChem SDQ API.

        Returns list of dicts with fields: publicationnumber, title, abstract,
        prioritydate, grantdate, classification, cids, assignees, familycount, etc.

        Paginates automatically (10,000 per page) up to max_patents.
        The default jurisdiction "*" passes PubChem's unscoped jurisdiction
        selector; it does not establish exhaustive office coverage.
        """
        settings = get_settings()
        if max_patents is None:
            max_patents = settings.search_max_sdq_patents

        page_size = settings.pubchem_sdq_page_size
        all_results: list[dict] = []
        start = 1

        while len(all_results) < max_patents:
            remaining = max_patents - len(all_results)
            limit = min(page_size, remaining)

            where_ands: list[dict] = [{"cid": str(cid)}]
            if jurisdiction != "*":
                where_ands.append({"publicationnumber": jurisdiction})

            query = {
                "select": "*",
                "collection": "patent",
                "where": {"ands": where_ands},
                "order": ["relevancescore,desc"],
                "start": start,
                "limit": limit,
            }

            data = await self._sdq_get(query)
            if not data:
                logger.warning("sdq_empty_response", start=start)
                break

            # SDQ wraps results: SDQOutputSet[0] has {rows, totalCount, ...}
            output_set = data.get("SDQOutputSet")
            if output_set is None:
                logger.error(
                    "sdq_unexpected_response_format",
                    response_keys=list(data.keys()),
                )
                raise SourceUnavailableError(
                    "pubchem_sdq",
                    "response schema missing output set",
                )

            parse_failure_type: str | None = None
            try:
                rows, total_available = extract_sdq_rows(data)
            except TypeError as exc:
                parse_failure_type = safe_exception_type(exc)
                logger.error(
                    "sdq_unexpected_output_set_type",
                    output_set_type=type(output_set).__name__,
                    error_type=parse_failure_type,
                )
            if parse_failure_type is not None:
                raise SourceUnavailableError(
                    "pubchem_sdq",
                    "response output set is invalid",
                ) from None
            if not rows:
                break

            all_results.extend(rows)
            logger.debug(
                "sdq_page_fetched",
                start=start,
                page_count=len(rows),
                total_so_far=len(all_results),
                total_available=total_available,
            )

            if len(rows) < limit:
                break
            start += limit

        logger.info(
            "sdq_search_complete",
            jurisdiction=jurisdiction,
            total_patents=len(all_results),
        )
        return all_results[:max_patents]

    async def similarity_search(
        self,
        smiles: str,
        threshold: float = 0.7,
        max_records: int = 50,
    ) -> list[dict]:
        """Find structurally similar compounds via 2D Tanimoto similarity.

        PubChem similarity search is asynchronous — it returns a ListKey that
        we poll until results are ready.

        Uses POST to avoid URL-encoding issues with SMILES special characters.
        """
        return await similarity_search(
            self,
            smiles,
            threshold=threshold,
            max_records=max_records,
        )

    async def _poll_list_key(
        self,
        list_key: str,
        *,
        max_records: int = 50,
        max_polls: int | None = None,
    ) -> list[dict]:
        """Poll PubChem for async search results."""
        return await poll_list_key(
            self,
            list_key,
            max_records=max_records,
            max_polls=max_polls,
        )

    async def _get_properties_for_cids(self, cids: list[int]) -> list[dict]:
        """Fetch properties for a list of CIDs."""
        return await get_properties_for_cids(self, cids)
