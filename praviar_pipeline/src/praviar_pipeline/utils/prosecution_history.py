"""Prosecution history parser — fetch and classify USPTO file wrapper documents.

Extracts rejections, narrowing amendments, and applicant arguments
from the prosecution record to support estoppel analysis.
"""

from __future__ import annotations

import httpx
import structlog

from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.models.equivalents import (
    ClaimAmendment,
    ProsecutionHistory,
    RejectionRecord,
)
from praviar_pipeline.utils.prosecution_history_helpers import (
    build_rejections_from_documents,
    build_rejections_from_office_actions,
    count_documents_of_type,
    extract_applicant_arguments,
    extract_application_number,
    extract_attorney_name,
    extract_current_assignee,
    extract_examiner_name,
    extract_filing_date,
    extract_grant_date,
    extract_inventor_names,
)
from praviar_pipeline.utils.prosecution_history_helpers import (
    classify_document as _classify_document_impl,
)
from praviar_pipeline.utils.prosecution_history_helpers import (
    identify_narrowing_amendments as _identify_narrowing_amendments_impl,
)

logger = structlog.get_logger()


def _classify_document(doc: dict) -> str:
    return _classify_document_impl(doc)


async def _extract_rejections(
    client: USPTOODPClient,
    patent_id: str,
    documents: list[dict],
) -> list[RejectionRecord]:
    """Extract rejection records from classified documents.

    Uses document metadata to identify rejection types. For deeper
    analysis, the structured Office Action API would be needed.
    """
    # Try structured office action data first
    try:
        oa_data = await client.get_office_actions(patent_id)
        if oa_data:
            return build_rejections_from_office_actions(oa_data)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error(
            "structured_oa_unavailable",
            error_type=type(exc).__name__,
        )
        # Fall through to document classification fallback

    return build_rejections_from_documents(documents)


def _identify_narrowing_amendments(documents: list[dict]) -> list[ClaimAmendment]:
    return _identify_narrowing_amendments_impl(documents)


async def fetch_prosecution_history(patent_id: str) -> ProsecutionHistory:
    """Fetch and parse prosecution history from USPTO file wrapper.

    Extracts rich data from ODP v3: rejections, amendments, transaction
    history, inventor/examiner/attorney names, assignment chain, and
    prosecution timeline.
    """
    async with USPTOODPClient() as client:
        # Get file wrapper documents
        try:
            documents = await client.get_file_wrapper_documents(patent_id)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error(
                "file_wrapper_fetch_failed",
                error_type=type(exc).__name__,
            )
            return ProsecutionHistory(patent_id=patent_id)

        if not documents:
            return ProsecutionHistory(patent_id=patent_id)

        # Get full application data (includes metadata, assignments, events)
        app_data = await client.get_application_data(patent_id)
        meta = app_data.get("applicationMetaData", {})

        # Extract application number (support both ODP v3 and legacy formats)
        app_number = extract_application_number(app_data, meta)

        # Extract filing and grant dates
        filing_date = extract_filing_date(meta)
        grant_date = extract_grant_date(meta, app_data)

        # Extract inventor names
        inventors = extract_inventor_names(meta, patent_id)

        # Extract examiner and attorney
        examiner = extract_examiner_name(meta)
        attorney = extract_attorney_name(app_data)

        # Extract current assignee from assignment chain
        current_assignee = extract_current_assignee(app_data)

        # Extract rejections
        rejections = await _extract_rejections(client, patent_id, documents)

        # Identify narrowing amendments
        amendments = _identify_narrowing_amendments(documents)

        # Check for terminal disclaimer
        has_td = count_documents_of_type(documents, "terminal_disclaimer") > 0

        # Check for Notice of Allowance (prosecution complete)
        has_noa = count_documents_of_type(documents, "notice_of_allowance") > 0

        # Count OAs and responses
        total_oas = count_documents_of_type(documents, "rejection")
        total_responses = count_documents_of_type(documents, "response")

        # Calculate prosecution duration
        prosecution_duration: int | None = None
        if filing_date and grant_date:
            prosecution_duration = (grant_date - filing_date).days

        # Extract applicant arguments (from response descriptions)
        arguments = extract_applicant_arguments(documents)

        logger.info(
            "prosecution_history_parsed",
            rejections=len(rejections),
            amendments=len(amendments),
            office_actions=total_oas,
            has_td=has_td,
            prosecution_complete=has_noa,
        )

        return ProsecutionHistory(
            patent_id=patent_id,
            application_number=app_number,
            filing_date=filing_date,
            grant_date=grant_date,
            rejections=rejections,
            amendments=amendments,
            applicant_arguments=arguments,
            has_terminal_disclaimer=has_td,
            prosecution_complete=has_noa,
            inventor_names=inventors,
            examiner_name=examiner,
            attorney_name=attorney,
            current_assignee=current_assignee,
            total_office_actions=total_oas,
            total_responses=total_responses,
            prosecution_duration_days=prosecution_duration,
        )
