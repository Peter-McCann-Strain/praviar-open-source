"""SureChEMBL REST API client — chemical structure to patent mappings.

SureChEMBL migrated to a new async POST-based API in 2025. The old GET
endpoints (/chemical/search/smiles/*, /chemical/search/similarity/*) all
return 404. The new flow is:

  1. POST /search/structure  {"StructureSearchRequest": {...}} → {"data": {"hash": "<uuid>"}}
  2. GET  /search/<hash>/status → {"data": {"state": "Searching finished." | ...}}
  3. GET  /search/<hash>/results → {"data": {"query": {"structures": [<chemId>, ...]}}}
  4. POST /search/documents_for_structures?chemicalIds=<id>&... → patent IDs

Step 4 currently returns INTERNAL_SERVER_ERROR on the SureChEMBL server.
Until that is fixed upstream, search_by_smiles / similarity_search /
substructure_search return empty lists. The client is kept so that once the
server-side bug is resolved, a one-line un-flag restores the full flow.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

BASE_URL = "https://www.surechembl.org/api"
_POLL_INTERVAL = 2.0
_POLL_MAX_ATTEMPTS = 15


class SureChEMBLClient(AsyncClientMixin):
    """Async client for the SureChEMBL REST API (v3 / async hash-polling).

    Provides compound-to-patent mappings via chemical structure search.
    Rate limited conservatively since API limits aren't documented.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_long, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.surechembl_requests_per_second,
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
    ) -> dict | list:
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._get_uncached(path, params=params, ok_on_404=ok_on_404)
        body = json.dumps(params, sort_keys=True) if params else None
        return await cache.wrap(
            source="surechembl",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._get_uncached(path, params=params, ok_on_404=ok_on_404),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=20),
    )
    async def _get_uncached(
        self,
        path: str,
        params: dict | None = None,
        *,
        ok_on_404: bool = False,
    ) -> dict | list:
        async with self._limiter:
            resp = await self._client.get(path, params=params)
            if resp.status_code == 404:
                if ok_on_404:
                    logger.debug("api_404_semantic_empty", source="surechembl")
                    return {}
                raise SourceUnavailableError("surechembl", f"404 on {path}", status_code=404)
            if resp.status_code >= 400:
                logger.error(
                    "surechembl_http_error",
                    status=resp.status_code,
                )
                raise SourceUnavailableError(
                    "surechembl",
                    "request failed",
                    status_code=resp.status_code,
                )
            parse_failed = False
            try:
                payload = resp.json()
            except (TypeError, ValueError):
                parse_failed = True
                payload = None
            if parse_failed or not isinstance(payload, (dict, list)):
                raise SourceUnavailableError(
                    "surechembl",
                    "response parsing failed",
                ) from None
            return payload

    async def _post(self, path: str, json: dict | None = None) -> dict:
        async with self._limiter:
            resp = await self._client.post(path, json=json)
            if resp.status_code >= 400:
                logger.debug(
                    "surechembl_post_error",
                    status=resp.status_code,
                )
                raise SourceUnavailableError(
                    "surechembl",
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
                raise SourceUnavailableError(
                    "surechembl",
                    "response parsing failed",
                ) from None
            return payload

    async def _start_structure_search(
        self,
        smiles: str,
        search_type: str,
        max_results: int,
    ) -> str:
        """POST /search/structure and return the polling hash."""
        payload = {
            "StructureSearchRequest": {
                "struct": smiles,
                "structSearchType": search_type,
                "maxResults": max_results,
            }
        }
        data = await self._post("/search/structure", json=payload)
        hash_val = data.get("data", {}).get("hash", "")
        if not hash_val:
            raise SourceUnavailableError(
                "surechembl", "structure search returned no hash", status_code=0
            )
        return cast("str", hash_val)

    async def _poll_search_results(self, hash_val: str) -> list[int]:
        """Poll /search/<hash>/status then fetch /search/<hash>/results.

        Returns a list of SureChEMBL chemical IDs.
        """
        for _ in range(_POLL_MAX_ATTEMPTS):
            status_data = await self._get(f"/search/{hash_val}/status", ok_on_404=True)
            state = (
                status_data.get("data", {}).get("state", "")
                if isinstance(status_data, dict)
                else ""
            )
            if "finished" in state.lower() or "complete" in state.lower():
                break
            await asyncio.sleep(_POLL_INTERVAL)

        results_data = await self._get(
            f"/search/{hash_val}/results", params={"page": 0, "max_results": 500}, ok_on_404=True
        )
        structures = (
            results_data.get("data", {}).get("query", {}).get("structures", [])
            if isinstance(results_data, dict)
            else []
        )
        return [s for s in structures if isinstance(s, int)]

    async def _get_patents_for_chemical_ids(self, chemical_ids: list[int]) -> list[dict]:
        """POST /search/documents_for_structures to map chemical IDs → patent IDs.

        NOTE: This endpoint returns INTERNAL_SERVER_ERROR on the SureChEMBL
        server as of 2025-06. Returns empty list until fixed upstream.
        """
        if not chemical_ids:
            return []

        params = [("chemicalIds", cid) for cid in chemical_ids]
        params.append(("page", 0))
        query_string = "&".join(f"{k}={v}" for k, v in params)
        failure_type: str | None = None
        try:
            async with self._limiter:
                resp = await self._client.post(f"/search/documents_for_structures?{query_string}")
            if resp.status_code >= 500:
                logger.warning(
                    "surechembl_documents_for_structures_unavailable",
                    status=resp.status_code,
                )
                raise SourceUnavailableError(
                    "surechembl",
                    "patent lookup failed",
                    status_code=resp.status_code,
                )
            if resp.status_code >= 400:
                raise SourceUnavailableError(
                    "surechembl",
                    "patent lookup rejected request",
                    status_code=resp.status_code,
                )
            data = resp.json()
            docs = data.get("data", {}).get("documents", [])
            return docs if isinstance(docs, list) else []
        except Exception as exc:
            failure_type = safe_exception_type(exc)
            logger.debug(
                "surechembl_documents_for_structures_failed",
                error_type=failure_type,
            )
        if failure_type is not None:
            raise SourceUnavailableError("surechembl", "patent lookup failed") from None
        raise AssertionError("SureChEMBL patent lookup reached an unreachable state")

    async def search_by_smiles(
        self,
        smiles: str,
        *,
        max_results: int = 500,
    ) -> list[dict]:
        """Search for patents containing a compound by SMILES (exact match).

        Returns list of patent mappings. Currently returns empty list while
        the SureChEMBL /search/documents_for_structures endpoint is broken.
        """
        failure_type: str | None = None
        try:
            hash_val = await self._start_structure_search(smiles, "EXACT", max_results)
            chemical_ids = await self._poll_search_results(hash_val)
            logger.debug("surechembl_smiles_chemical_ids", count=len(chemical_ids))
            return await self._get_patents_for_chemical_ids(chemical_ids)
        except SourceUnavailableError as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_smiles_search_failed", error_type=failure_type)
        except Exception as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_smiles_search_error", error_type=failure_type)
        if failure_type is not None:
            raise SourceUnavailableError("surechembl", "exact structure search failed") from None
        raise AssertionError("SureChEMBL exact search reached an unreachable state")

    async def similarity_search(
        self,
        smiles: str,
        threshold: float = 0.7,
    ) -> list[dict]:
        """Find patents for structurally similar compounds (Tanimoto).

        Returns compounds with their patent associations. Currently returns
        empty list while the SureChEMBL patent-lookup endpoint is broken.
        """
        failure_type: str | None = None
        try:
            hash_val = await self._start_structure_search(smiles, "SIMILARITY", 500)
            chemical_ids = await self._poll_search_results(hash_val)
            logger.debug("surechembl_similarity_chemical_ids", count=len(chemical_ids))
            return await self._get_patents_for_chemical_ids(chemical_ids)
        except SourceUnavailableError as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_similarity_search_failed", error_type=failure_type)
        except Exception as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_similarity_search_error", error_type=failure_type)
        if failure_type is not None:
            raise SourceUnavailableError("surechembl", "similarity search failed") from None
        raise AssertionError("SureChEMBL similarity search reached an unreachable state")

    async def substructure_search(
        self,
        smiles: str,
        max_results: int = 500,
    ) -> list[dict]:
        """Find patents for compounds containing this substructure.

        Returns compounds with their patent associations. Currently returns
        empty list while the SureChEMBL patent-lookup endpoint is broken.
        """
        failure_type: str | None = None
        try:
            hash_val = await self._start_structure_search(smiles, "SUBSTRUCTURE", max_results)
            chemical_ids = await self._poll_search_results(hash_val)
            logger.debug("surechembl_substructure_chemical_ids", count=len(chemical_ids))
            return await self._get_patents_for_chemical_ids(chemical_ids)
        except SourceUnavailableError as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_substructure_search_failed", error_type=failure_type)
        except Exception as exc:
            failure_type = safe_exception_type(exc)
            logger.warning("surechembl_substructure_search_error", error_type=failure_type)
        if failure_type is not None:
            raise SourceUnavailableError("surechembl", "substructure search failed") from None
        raise AssertionError("SureChEMBL substructure search reached an unreachable state")
