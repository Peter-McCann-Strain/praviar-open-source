"""USPTO PTAB API v3 client — IPR/PGR/CBM proceedings and outcomes.

As of Jan 2026, PTAB API v2 at developer.uspto.gov is decommissioned.
PTAB v3 is on the Open Data Portal (ODP) at api.uspto.gov.
Requires a free ODP API key from data.uspto.gov.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import (
    RetryError,
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
from praviar_pipeline.utils.patent_ids import clean_patent_number_for_api

logger = structlog.get_logger()

BASE_URL = "https://api.uspto.gov/api/v1/patent/trials"


def _is_key_valid(key: str) -> bool:
    """Check whether the PTAB API key is configured."""
    return bool(key.strip())


class PTABClient(AsyncClientMixin):
    """Async client for USPTO PTAB API v3 (Open Data Portal).

    Provides access to IPR/PGR/CBM proceedings and decisions.
    Requires a free ODP API key from data.uspto.gov.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._key_valid = _is_key_valid(settings.uspto_odp_api_key)

        if not self._key_valid:
            logger.warning(
                "ptab_disabled",
            )

        # Only set Authorization header when we have a real key
        headers: dict[str, str] = {}
        if self._key_valid:
            headers["X-API-KEY"] = settings.uspto_odp_api_key
            logger.debug("ptab_client_init", status="enabled")

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
            max_rate=settings.ptab_requests_per_minute,
            time_period=60,
        )

    def _require_valid_key(self) -> None:
        """Raise ConfigurationError if the API key is not configured.

        Called at the start of every public method so callers get an
        immediate, clear error instead of a cryptic 401 from the server.
        """
        if not self._key_valid:
            raise ConfigurationError(
                "PTAB API key not configured. "
                "Set 'USPTO_ODP_API_KEY' in .env or environment variables.",
                source="ptab",
            )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _post_search(self, path: str, payload: dict, *, ok_on_404: bool = True) -> dict:
        """POST search request to PTAB ODP API.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the JSON-serialised payload into the body hash.
        Cache hits bypass tenacity — we only retry live calls. Exceptions
        (including :class:`AuthenticationError` and
        :class:`SourceUnavailableError`) propagate unrecorded. ``ok_on_404``
        semantics are preserved: ``True`` records ``{}`` legitimately.

        Args:
            path: API path (relative to BASE_URL).
            payload: JSON payload.
            ok_on_404: If True (default for PTAB), a 404 response is treated
                as a semantic empty result — most patents have no PTAB
                proceeding, so the "does this patent have a proceeding?"
                lookup legitimately returns 404. If False, raise
                :class:`SourceUnavailableError`.
        """
        # Inline import — survives the aggressive format hook.
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            try:
                return await self._post_search_uncached(path, payload, ok_on_404=ok_on_404)
            except RetryError:
                raise SourceUnavailableError("ptab", "request failed after retries") from None
        body = json.dumps(payload, sort_keys=True)
        return await cache.wrap(
            source="ptab",
            method="POST",
            url=path,
            body=body,
            call=lambda: self._post_search_uncached(path, payload, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_not_exception_type(
            (
                AuthenticationError,
                ConfigurationError,
                asyncio.CancelledError,
                SourceUnavailableError,
            )
        ),
    )
    async def _post_search_uncached(
        self, path: str, payload: dict, *, ok_on_404: bool = True
    ) -> dict:
        """Underlying live HTTP POST — retries via tenacity, never cached here."""
        self._require_valid_key()
        logger.debug("ptab_request", method="POST", payload_keys=list(payload.keys()))
        async with self._limiter:
            resp = await self._client.post(path, json=payload)
            if resp.status_code in (401, 403):
                logger.error(
                    "ptab_auth_rejected",
                    status_code=resp.status_code,
                )
                raise AuthenticationError(
                    "PTAB ODP API key is invalid or missing",
                    source="ptab",
                )
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("ptab_404_semantic_empty")
                    return {}
                raise SourceUnavailableError(
                    "ptab",
                    f"404 on {path}",
                    status_code=404,
                )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise SourceUnavailableError(
                    "ptab",
                    "response was not a JSON object",
                    status_code=resp.status_code,
                )
            logger.debug(
                "ptab_response_ok",
                keys=list(data.keys()),
            )
            return data

    async def get_proceedings(self, patent_number: str) -> list[dict]:
        """Get all PTAB proceedings (IPR/PGR/CBM) for a patent.

        The patent_number should be in format like '7851188' (no prefix/suffix).
        Raises ConfigurationError if the API key is not configured.
        """
        exchange = await self.get_proceedings_artifact(patent_number)
        data = exchange.get("response", {})
        if not isinstance(data, dict):
            data = {}
        if not data:
            logger.debug("ptab_no_proceedings")
            return []
        results = data.get(
            "patentTrialProceedingDataBag", data.get("results", data.get("hits", []))
        )
        if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
            raise SourceUnavailableError("ptab", "proceedings response shape is invalid")
        logger.debug("ptab_proceedings_found", count=len(results))
        return cast("list[dict]", results)

    async def get_proceedings_artifact(self, patent_number: str) -> dict:
        """Return the exact query-bound ODP response for evidence retention."""
        self._require_valid_key()
        clean = clean_patent_number_for_api(patent_number)
        logger.debug("ptab_get_proceedings", cleaned=clean)
        request: dict[str, object] = {
            "q": f"patentOwnerData.patentNumber:{clean}",
            "pagination": {"offset": 0, "limit": 1000},
        }
        response = await self._post_search(
            "/proceedings/search",
            payload=request,
        )
        return {"request": request, "response": response}

    async def get_decisions(self, proceeding_number: str) -> list[dict]:
        """Get decisions for a specific PTAB proceeding.

        Raises ConfigurationError if the API key is not configured.
        """
        exchange = await self.get_decisions_artifact(proceeding_number)
        data = exchange.get("response", {})
        if not isinstance(data, dict):
            data = {}
        if not data:
            logger.debug("ptab_no_decisions")
            return []
        results = data.get(
            "patentTrialDocumentDataBag",
            data.get(
                "patentTrialDecisionDataBag",
                data.get("results", data.get("hits", [])),
            ),
        )
        if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
            raise SourceUnavailableError("ptab", "decisions response shape is invalid")
        logger.debug("ptab_decisions_found", count=len(results))
        return cast("list[dict]", results)

    async def get_decisions_artifact(self, proceeding_number: str) -> dict:
        """Return the exact ODP decisions response for one PTAB trial."""
        self._require_valid_key()
        logger.debug("ptab_get_decisions")
        request: dict[str, object] = {
            "q": f"trialNumber:{proceeding_number}",
            "pagination": {"offset": 0, "limit": 1000},
        }
        response = await self._post_search(
            "/decisions/search",
            payload=request,
        )
        return {"request": request, "response": response}
