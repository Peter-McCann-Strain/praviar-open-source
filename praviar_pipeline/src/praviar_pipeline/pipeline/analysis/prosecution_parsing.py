"""Structured parsing helpers for Step 4 prosecution context."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.pipeline.analysis import prosecution_parsing_helpers as _helpers
from praviar_pipeline.pipeline.analysis.prep_helpers import (
    format_amendments_summary,
    format_continuity_summary,
    format_office_actions_summary,
)


def normalize_office_action_events(
    office_actions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    return _helpers.normalize_office_action_events(office_actions)


def normalize_continuity_entries(
    continuity: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    return _helpers.normalize_continuity_entries(continuity)


def normalize_amendment_events(
    transactions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    return _helpers.normalize_amendment_events(transactions)


def derive_prosecution_profile(
    *,
    office_action_events: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    continuity_entries: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    amendment_events: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    return _helpers.derive_prosecution_profile(
        office_action_events=office_action_events,
        continuity_entries=continuity_entries,
        amendment_events=amendment_events,
    )


def build_prosecution_context_payload(
    *,
    office_actions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    continuity: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    transactions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    file_wrapper_documents: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    office_actions_list = list(office_actions or [])
    continuity_list = list(continuity or [])
    transactions_list = list(transactions or [])
    file_wrapper_documents_list = list(file_wrapper_documents or [])

    office_action_events = normalize_office_action_events(office_actions_list)
    continuity_entries = normalize_continuity_entries(continuity_list)
    amendment_events = normalize_amendment_events(transactions_list)

    office_actions_summary = format_office_actions_summary(office_actions_list)
    continuity_summary = format_continuity_summary(continuity_list)
    amendments_summary, _amendment_count = format_amendments_summary(transactions_list)

    result: dict[str, Any] = {}
    if office_actions_summary:
        result["office_actions"] = office_actions_summary
    if continuity_summary:
        result["continuity"] = continuity_summary
    if amendments_summary:
        result["amendments"] = amendments_summary
    if office_action_events:
        result["office_action_events"] = office_action_events
    if continuity_entries:
        result["continuity_entries"] = continuity_entries
    if amendment_events:
        result["amendment_events"] = amendment_events
    if file_wrapper_documents_list:
        result["file_wrapper_document_count"] = len(file_wrapper_documents_list)
    rejected_claim_numbers = sorted(
        {
            int(claim_number)
            for event in office_action_events
            for claim_number in list(event.get("claims_rejected", []) or [])
            if isinstance(claim_number, int)
        }
    )
    narrowing_claim_numbers = sorted(
        {
            int(claim_number)
            for event in amendment_events
            for claim_number in list(event.get("claim_numbers", []) or [])
            if isinstance(claim_number, int)
        }
    )
    if rejected_claim_numbers:
        result["rejected_claim_numbers"] = rejected_claim_numbers
    if narrowing_claim_numbers:
        result["narrowing_claim_numbers"] = narrowing_claim_numbers

    sections_available = [
        section
        for section, present in (
            ("office_actions", bool(office_actions_summary or office_action_events)),
            ("continuity", bool(continuity_summary or continuity_entries)),
            ("amendments", bool(amendments_summary or amendment_events)),
            ("us_file_wrapper_dossier", bool(file_wrapper_documents_list)),
        )
        if present
    ]
    if sections_available:
        result["sections_available"] = sections_available

    if office_action_events or continuity_entries or amendment_events:
        result.update(
            derive_prosecution_profile(
                office_action_events=office_action_events,
                continuity_entries=continuity_entries,
                amendment_events=amendment_events,
            )
        )

    return result
