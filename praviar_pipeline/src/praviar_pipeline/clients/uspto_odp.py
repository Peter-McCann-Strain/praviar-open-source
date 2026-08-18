"""USPTO Open Data Portal client — file wrappers, prosecution history, and patent search.

Migrated to api.uspto.gov/api/v1 (ODP 3.0) from the legacy developer.uspto.gov
endpoint which is decommissioned April 20, 2026.

The new ODP API uses applicationNumberText as path params instead of
patentNumber as query params. This client resolves patent numbers to
application numbers via the search endpoint, then uses path-based lookups.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_adjustment as _get_adjustment,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_application_data as _get_application_data,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_application_metadata as _get_application_metadata,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_assignment as _get_assignment,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_continuity_artifact as _get_continuity_artifact,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_continuity_data as _get_continuity_data,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_file_wrapper_documents as _get_file_wrapper_documents,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_file_wrapper_documents_artifact as _get_file_wrapper_documents_artifact,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_foreign_priority as _get_foreign_priority,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_office_actions as _get_office_actions,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_transactions as _get_transactions,
)
from praviar_pipeline.clients.uspto_odp_client_ops import (
    resolve_app_number as _resolve_app_number_impl,
)
from praviar_pipeline.clients.uspto_odp_client_ops import search_patents as _search_patents
from praviar_pipeline.clients.uspto_odp_helpers import is_key_valid
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError, ConfigurationError

logger = structlog.get_logger()

BASE_URL = "https://api.uspto.gov/api/v1"


class USPTOODPClient(AsyncClientMixin):
    """Async client for USPTO Open Data Portal (ODP 3.0).

    Provides access to patent application search, file wrappers, office actions,
    continuity data, assignments, patent term adjustment, and more.

    All endpoints at api.uspto.gov/api/v1 use the same ODP API key. Request
    pacing follows the operator-configured local caps.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._key_valid = is_key_valid(settings.uspto_odp_api_key)
        self._app_number_cache: dict[str, str] = {}

        if not self._key_valid:
            logger.warning(
                "uspto_odp_disabled",
            )

        headers: dict[str, str] = {}
        if self._key_valid:
            headers["X-API-KEY"] = settings.uspto_odp_api_key
            logger.debug("uspto_odp_client_init", status="enabled")

        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_long, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            headers=headers,
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.uspto_odp_requests_per_minute,
            time_period=60,
        )

    def _require_valid_key(self) -> None:
        if not self._key_valid:
            raise ConfigurationError(
                "USPTO ODP API key not configured. "
                "Set 'USPTO_ODP_API_KEY' in .env or environment variables.",
                source="uspto_odp",
            )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        """Rate-limited GET request to USPTO ODP.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the JSON-serialised query params into the body
        hash. Cache hits bypass tenacity — we only retry live calls.
        Exceptions propagate unrecorded.
        """
        # Inline import — survives the aggressive format hook.
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, params=params)
        body = json.dumps(params, sort_keys=True) if params else None
        return await cache.wrap(
            source="uspto_odp",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_uncached(path, params=params),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15),
        retry=retry_if_not_exception_type(
            (AuthenticationError, ConfigurationError, asyncio.CancelledError, httpx.ConnectError)
        ),
    )
    async def _get_uncached(self, path: str, params: dict | None = None) -> dict | list:
        """Underlying live HTTP GET — retries via tenacity, never cached here."""
        self._require_valid_key()
        logger.debug("uspto_odp_request", method="GET")
        async with self._limiter:
            resp = await self._client.get(path, params=params)
            if resp.status_code in (401, 403):
                logger.error(
                    "uspto_odp_auth_rejected",
                    status_code=resp.status_code,
                )
                raise AuthenticationError(
                    "USPTO ODP API key is invalid or rejected",
                    source="uspto_odp",
                )
            if resp.status_code == 404:
                logger.debug("uspto_odp_404_not_found")
                return {}
            resp.raise_for_status()
            data = resp.json()
            logger.debug("uspto_odp_response_ok")
            return cast("dict | list", data)

    async def _post(self, path: str, payload: dict) -> dict | list:
        """Rate-limited POST request to USPTO ODP.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
        the live HTTP call is wrapped so the response is recorded/replayed.
        The cache key folds the JSON-serialised payload into the body hash.
        Cache hits bypass tenacity. Exceptions propagate unrecorded.
        """
        # Inline import — survives the aggressive format hook.
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._post_uncached(path, payload)
        body = json.dumps(payload, sort_keys=True)
        return await cache.wrap(
            source="uspto_odp",
            method="POST",
            url=path,
            body=body,
            call=lambda: self._post_uncached(path, payload),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15),
        retry=retry_if_not_exception_type(
            (AuthenticationError, ConfigurationError, asyncio.CancelledError, httpx.ConnectError)
        ),
    )
    async def _post_uncached(self, path: str, payload: dict) -> dict | list:
        """Underlying live HTTP POST — retries via tenacity, never cached here."""
        self._require_valid_key()
        logger.debug("uspto_odp_request", method="POST", payload_keys=list(payload.keys()))
        async with self._limiter:
            resp = await self._client.post(path, json=payload)
            if resp.status_code in (401, 403):
                logger.error(
                    "uspto_odp_auth_rejected",
                    status_code=resp.status_code,
                )
                raise AuthenticationError(
                    "USPTO ODP API key is invalid or rejected",
                    source="uspto_odp",
                )
            if resp.status_code == 404:
                logger.debug("uspto_odp_404_not_found")
                return {}
            resp.raise_for_status()
            data = resp.json()
            logger.debug("uspto_odp_response_ok")
            return cast("dict | list", data)

    # ── Patent number → application number resolution ──

    async def _resolve_app_number(self, patent_number: str) -> str | None:
        return await _resolve_app_number_impl(self, patent_number)

    # ── Search ──

    async def search_patents(
        self,
        query: str,
        *,
        filters: list[dict] | None = None,
        range_filters: list[dict] | None = None,
        fields: list[str] | None = None,
        sort: list[dict] | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        return await _search_patents(
            self,
            query,
            filters=filters,
            range_filters=range_filters,
            fields=fields,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    # ── Application data (path-based lookups) ──

    async def get_application_data(self, patent_number: str) -> dict:
        return await _get_application_data(self, patent_number)

    async def get_application_metadata(self, patent_number: str) -> dict:
        return await _get_application_metadata(self, patent_number)

    async def get_file_wrapper_documents(self, patent_number: str) -> list[dict]:
        return await _get_file_wrapper_documents(self, patent_number)

    async def get_file_wrapper_documents_artifact(self, patent_number: str) -> dict:
        return await _get_file_wrapper_documents_artifact(self, patent_number)

    async def get_continuity_data(self, patent_number: str) -> list[dict]:
        return await _get_continuity_data(self, patent_number)

    async def get_continuity_artifact(self, patent_number: str) -> dict:
        return await _get_continuity_artifact(self, patent_number)

    async def get_adjustment(self, patent_number: str) -> dict:
        return await _get_adjustment(self, patent_number)

    async def get_assignment(self, patent_number: str) -> list[dict]:
        return await _get_assignment(self, patent_number)

    async def get_foreign_priority(self, patent_number: str) -> list[dict]:
        return await _get_foreign_priority(self, patent_number)

    async def get_transactions(self, patent_number: str) -> list[dict]:
        return await _get_transactions(self, patent_number)

    async def get_office_actions(self, patent_number: str) -> list[dict]:
        return await _get_office_actions(self, patent_number)
