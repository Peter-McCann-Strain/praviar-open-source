"""Prosecution-history fetching helpers for Step 4 preparation."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.pipeline.analysis.prosecution_parsing import (
    build_prosecution_context_payload,
    normalize_amendment_events,
    normalize_continuity_entries,
    normalize_office_action_events,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

SourceResult = list[dict[str, Any]] | BaseException


def _log_result_state(patent_id: str, result: dict[str, Any]) -> None:
    if result:
        logger.info(
            "prosecution_context_fetched",
            sections=list(result.get("sections_available", [])),
            office_action_count=int(result.get("office_action_count", 0) or 0),
            continuity_entry_count=int(result.get("continuity_entry_count", 0) or 0),
            amendment_entry_count=int(result.get("amendment_entry_count", 0) or 0),
        )
    else:
        logger.debug("prosecution_context_empty")


async def fetch_prosecution_context_impl(patent_id: str) -> dict[str, Any] | None:
    """Fetch prosecution history summary for claim construction context."""
    if not patent_id.upper().startswith("US"):
        logger.debug(
            "prosecution_context_skipped",
        )
        return {}

    settings = get_settings()
    if not settings.uspto_odp_api_key:
        raise ConfigurationError(
            "USPTO ODP API key not configured",
            source="uspto_odp",
            step="prosecution_context",
        )

    outer_failure_type: str | None = None
    try:
        from praviar_pipeline.clients.uspto_odp import USPTOODPClient

        async with USPTOODPClient() as odp:
            fetched = await asyncio.gather(
                odp.get_office_actions(patent_id),
                odp.get_continuity_data(patent_id),
                odp.get_transactions(patent_id),
                odp.get_file_wrapper_documents(patent_id),
                return_exceptions=True,
            )
        office_actions = cast("SourceResult", fetched[0])
        continuity = cast("SourceResult", fetched[1])
        transactions = cast("SourceResult", fetched[2])
        file_wrapper_documents = cast("SourceResult", fetched[3])

        source_failures: list[BaseException] = []
        if isinstance(office_actions, BaseException):
            source_failures.append(office_actions)
            logger.warning(
                "prosecution_office_actions_failed",
                error_type=safe_exception_type(office_actions),
            )
        if isinstance(continuity, BaseException):
            source_failures.append(continuity)
            logger.warning(
                "prosecution_continuity_failed",
                error_type=safe_exception_type(continuity),
            )
        if isinstance(transactions, BaseException):
            source_failures.append(transactions)
            logger.warning(
                "prosecution_transactions_failed",
                error_type=safe_exception_type(transactions),
            )
        if isinstance(file_wrapper_documents, BaseException):
            source_failures.append(file_wrapper_documents)
            logger.warning(
                "prosecution_file_wrapper_failed",
                error_type=safe_exception_type(file_wrapper_documents),
            )
        if source_failures:
            raise SourceUnavailableError(
                "uspto_odp",
                "prosecution context coverage failed",
            ) from None

        result = build_prosecution_context_payload(
            office_actions=office_actions if isinstance(office_actions, list) else [],
            continuity=continuity if isinstance(continuity, list) else [],
            transactions=transactions if isinstance(transactions, list) else [],
            file_wrapper_documents=(
                file_wrapper_documents if isinstance(file_wrapper_documents, list) else []
            ),
        )
        if isinstance(office_actions, list) and office_actions:
            logger.debug(
                "prosecution_office_actions",
                count=len(normalize_office_action_events(office_actions)),
            )
        if isinstance(continuity, list) and continuity:
            logger.debug(
                "prosecution_continuity",
                count=len(normalize_continuity_entries(continuity)),
            )
        if isinstance(transactions, list) and transactions:
            logger.debug(
                "prosecution_transactions",
                total=len(transactions),
                amendment_related=len(normalize_amendment_events(transactions)),
            )
        if isinstance(file_wrapper_documents, list) and file_wrapper_documents:
            logger.debug(
                "prosecution_file_wrapper_documents",
                total=len(file_wrapper_documents),
            )
        _log_result_state(patent_id, result)
        return result
    except (ConfigurationError, SourceUnavailableError):
        raise
    except Exception as exc:
        outer_failure_type = safe_exception_type(exc)
        logger.warning(
            "prosecution_context_fetch_failed",
            error_type=outer_failure_type,
        )

    if outer_failure_type is not None:
        raise SourceUnavailableError(
            "uspto_odp",
            "prosecution context fetch failed",
        ) from None
    raise AssertionError("prosecution context reached an unreachable state")
