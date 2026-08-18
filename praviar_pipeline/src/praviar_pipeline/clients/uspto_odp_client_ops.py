"""Endpoint-level orchestration helpers for the USPTO ODP client."""

from __future__ import annotations

from typing import Protocol

import structlog

from praviar_pipeline.clients.uspto_odp_helpers import (
    extract_first_wrapper_record,
    extract_named_results,
    merge_continuity_entries,
    resolve_app_number_from_search,
)
from praviar_pipeline.utils.patent_ids import clean_patent_number_for_api

logger = structlog.get_logger()


class _USPTOODPClientLike(Protocol):
    _app_number_cache: dict[str, str]

    def _require_valid_key(self) -> None: ...

    async def _get(self, path: str, params: dict | None = None) -> dict | list: ...

    async def _post(self, path: str, payload: dict) -> dict | list: ...

    async def get_application_data(self, patent_number: str) -> dict: ...

    async def get_file_wrapper_documents(self, patent_number: str) -> list[dict]: ...


async def resolve_app_number(client: _USPTOODPClientLike, patent_number: str) -> str | None:
    """Resolve a patent number to an applicationNumberText via search."""
    clean = clean_patent_number_for_api(patent_number)
    if clean in client._app_number_cache:
        return client._app_number_cache[clean]

    data = await client._post(
        "/patent/applications/search",
        payload={
            "q": f"applicationMetaData.patentNumber:{clean}",
            "pagination": {"offset": 0, "limit": 10},
        },
    )
    if not data or not isinstance(data, dict):
        return None

    app_num = resolve_app_number_from_search(data, clean)
    if app_num:
        client._app_number_cache[clean] = app_num
        logger.debug("uspto_odp_resolved_app_number")
        return app_num

    logger.debug("uspto_odp_no_app_number")
    return None


async def search_patents(
    client: _USPTOODPClientLike,
    query: str,
    *,
    filters: list[dict] | None = None,
    range_filters: list[dict] | None = None,
    fields: list[str] | None = None,
    sort: list[dict] | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Search patent applications using ODP query syntax."""
    client._require_valid_key()
    logger.debug("uspto_odp_search", limit=limit)
    data = await client._post(
        "/patent/applications/search",
        payload={"q": query, "pagination": {"offset": offset, "limit": limit}},
    )
    if isinstance(data, dict):
        count = data.get("count", 0)
        logger.debug("uspto_odp_search_results", total=count)
        return data
    return {}


async def get_application_data(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> dict:
    """Get application-level data for a patent."""
    client._require_valid_key()
    clean = clean_patent_number_for_api(patent_number)
    logger.debug("uspto_odp_get_application", cleaned=clean)

    app_num = await resolve_app_number(client, clean)
    if not app_num:
        logger.debug("uspto_odp_no_application")
        return {}

    data = await client._get(f"/patent/applications/{app_num}")
    if isinstance(data, dict):
        result = extract_first_wrapper_record(data)
        if result:
            logger.debug(
                "uspto_odp_application_found",
                keys=list(result.keys())[:10],
            )
            return result
    return {}


async def get_application_metadata(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> dict:
    """Get patent metadata: patent number, grant date, status, title."""
    app_num = await resolve_app_number(client, patent_number)
    if not app_num:
        return {}
    data = await client._get(f"/patent/applications/{app_num}/meta-data")
    return data if isinstance(data, dict) else {}


async def get_file_wrapper_documents(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> list[dict]:
    """List all documents in a patent's file wrapper."""
    data = await get_file_wrapper_documents_artifact(client, patent_number)
    if not data:
        return []
    results = extract_named_results(data, "results", "documentBag")
    logger.debug("uspto_odp_file_wrapper_found", count=len(results))
    return results


async def get_file_wrapper_documents_artifact(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> dict:
    """Return the exact documents endpoint response for retained evidence."""
    client._require_valid_key()
    clean = clean_patent_number_for_api(patent_number)
    logger.debug("uspto_odp_get_file_wrapper", cleaned=clean)

    app_num = await resolve_app_number(client, clean)
    if not app_num:
        logger.debug("uspto_odp_no_file_wrapper")
        return {}

    data = await client._get(f"/patent/applications/{app_num}/documents")
    if not data:
        logger.debug("uspto_odp_no_file_wrapper")
        return {}
    return data if isinstance(data, dict) else {}


async def get_continuity_data(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> list[dict]:
    """Application continuity chain for effective filing date calculation."""
    data = await get_continuity_artifact(client, patent_number)
    if not data:
        return []
    results = merge_continuity_entries(data)
    parents = data.get("parentContinuityBag", [])
    children = data.get("childContinuityBag", [])
    logger.debug(
        "uspto_odp_continuity_found",
        parents=len(parents),
        children=len(children),
    )
    return results


async def get_continuity_artifact(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> dict:
    """Return the exact continuity endpoint response for retained evidence."""
    client._require_valid_key()
    clean = clean_patent_number_for_api(patent_number)
    logger.debug("uspto_odp_get_continuity", cleaned=clean)

    app_num = await resolve_app_number(client, clean)
    if not app_num:
        logger.debug("uspto_odp_no_continuity")
        return {}
    data = await client._get(f"/patent/applications/{app_num}/continuity")
    if not isinstance(data, dict):
        return {}
    return data


async def get_adjustment(client: _USPTOODPClientLike, patent_number: str) -> dict:
    """Get the official Patent File Wrapper PTA adjustment record."""
    app_num = await resolve_app_number(client, patent_number)
    if not app_num:
        return {}
    data = await client._get(f"/patent/applications/{app_num}/adjustment")
    return data if isinstance(data, dict) else {}


async def get_assignment(client: _USPTOODPClientLike, patent_number: str) -> list[dict]:
    """Get recorded assignment data; this is not a legal-title conclusion."""
    app_num = await resolve_app_number(client, patent_number)
    if not app_num:
        return []
    data = await client._get(f"/patent/applications/{app_num}/assignment")
    return extract_named_results(data, "assignmentBag", "results")


async def get_foreign_priority(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> list[dict]:
    """Get foreign priority claims for a patent."""
    app_num = await resolve_app_number(client, patent_number)
    if not app_num:
        return []
    data = await client._get(f"/patent/applications/{app_num}/foreign-priority")
    return extract_named_results(data, "foreignPriorityBag", "results")


async def get_transactions(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> list[dict]:
    """Get prosecution transaction history (event log)."""
    app_num = await resolve_app_number(client, patent_number)
    if not app_num:
        return []
    data = await client._get(f"/patent/applications/{app_num}/transactions")
    return extract_named_results(data, "transactionBag", "results")


async def get_office_actions(
    client: _USPTOODPClientLike,
    patent_number: str,
) -> list[dict]:
    """Get office action documents from the file wrapper."""
    clean = clean_patent_number_for_api(patent_number)
    logger.debug("uspto_odp_get_office_actions", cleaned=clean)

    docs = await client.get_file_wrapper_documents(clean)
    if not docs:
        logger.debug("uspto_odp_no_office_actions")
        return []

    oa_codes = {"CTNF", "CTFR", "OA", "NFOA", "FOA"}
    oa_docs = [d for d in docs if d.get("documentCode", "") in oa_codes]
    logger.debug("uspto_odp_office_actions_found", count=len(oa_docs))
    return oa_docs
