"""Patent-status handlers for the Claude-facing FTO tools."""

from __future__ import annotations

from typing import cast

import httpx
import structlog

from praviar_pipeline.tools_cache import build_status_from_cache

logger = structlog.get_logger()


async def handle_check_patent_status(
    input_data: dict,
    cache: dict[str, dict],
) -> str:
    """Check patent prosecution/legal status via USPTO ODP."""
    patent_id = input_data.get("patent_id", "").strip()
    if not patent_id:
        return "Error: patent_id is required."

    status_key = f"_status_{patent_id}"
    if status_key in cache:
        return cast("str", cache[status_key]["result"])

    try:
        from praviar_pipeline.clients.uspto_odp import USPTOODPClient
        from praviar_pipeline.utils.prosecution_history import _classify_document

        async with USPTOODPClient() as client:
            app_data = await client.get_application_data(patent_id)
            app_number = app_data.get("applicationNumber", "unknown")
            filing_date = app_data.get("filingDate", "unknown")
            documents = await client.get_file_wrapper_documents(patent_id)

        doc_types: dict[str, int] = {}
        for document in documents:
            doc_type = _classify_document(document)
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

        result_parts = [
            f"Patent: {patent_id}",
            f"Application Number: {app_number}",
            f"Filing Date: {filing_date}",
            f"Total File Wrapper Documents: {len(documents)}",
        ]

        if doc_types:
            result_parts.append("Document Types:")
            for doc_type, count in sorted(doc_types.items()):
                result_parts.append(f"  - {doc_type}: {count}")

        has_noa = doc_types.get("notice_of_allowance", 0) > 0
        result_parts.append(f"Notice of Allowance: {'Yes' if has_noa else 'No'}")

        has_td = doc_types.get("terminal_disclaimer", 0) > 0
        if has_td:
            result_parts.append("Terminal Disclaimer: Filed")

        result = "\n".join(result_parts)
        cache[status_key] = {"result": result}
        return result

    except (
        httpx.HTTPError,
        ConnectionError,
        TimeoutError,
        RuntimeError,
        KeyError,
        ValueError,
        OSError,
    ):
        logger.warning(
            "tool_check_patent_status_api_failed",
            fallback="cached_patent_data",
        )
        return build_status_from_cache(patent_id, cache)
