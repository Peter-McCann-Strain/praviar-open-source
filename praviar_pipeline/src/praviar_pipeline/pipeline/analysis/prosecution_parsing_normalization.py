"""Normalization helpers for prosecution parsing."""

from __future__ import annotations

import re
from typing import Any

from praviar_pipeline.pipeline.analysis.prosecution_parsing_classifiers import (
    _clean,
    _upper,
    classify_office_action_type,
    classify_transaction_type,
    extract_rejection_bases,
    normalize_continuity_type,
)


def _normalize_claim_numbers(values: list[object] | tuple[object, ...] | None) -> list[int]:
    claim_numbers: list[int] = []
    for value in values or []:
        text = str(value).strip()
        if text.isdigit():
            claim_numbers.append(int(text))
    return claim_numbers


def _extract_claim_numbers(text: str) -> list[int]:
    if not text:
        return []

    claim_numbers: list[int] = []
    for match in re.finditer(
        r"\bclaims?\s+((?:\d+(?:\s*-\s*\d+)?)(?:\s*(?:,|and|through|to)\s*\d+(?:\s*-\s*\d+)?)*)",
        text,
        flags=re.IGNORECASE,
    ):
        segment = match.group(1)
        for token in re.split(r"\s*(?:,|and)\s*", segment):
            token = token.strip()
            if not token:
                continue
            range_match = re.fullmatch(r"(\d+)\s*(?:-|through|to)\s*(\d+)", token)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                if start <= end:
                    claim_numbers.extend(range(start, end + 1))
                else:
                    claim_numbers.extend(range(end, start + 1))
                continue
            if token.isdigit():
                claim_numbers.append(int(token))

    deduped: list[int] = []
    seen: set[int] = set()
    for claim_number in claim_numbers:
        if claim_number in seen:
            continue
        seen.add(claim_number)
        deduped.append(claim_number)
    return deduped


def normalize_office_action_events(
    office_actions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for office_action in office_actions or []:
        description = _clean(
            office_action.get("documentDescription") or office_action.get("documentCategory")
        )
        events.append(
            {
                "document_code": _upper(office_action.get("documentCode")),
                "description": description,
                "event_date": _clean(
                    office_action.get("mailDate") or office_action.get("documentDate")
                ),
                "office_action_type": classify_office_action_type(office_action),
                "claims_rejected": (
                    _normalize_claim_numbers(office_action.get("claimsRejected"))
                    or _extract_claim_numbers(description)
                ),
                "rejection_bases": extract_rejection_bases(
                    description,
                    _clean(office_action.get("rejectionBasis")),
                ),
            }
        )
    return events


def normalize_continuity_entries(
    continuity: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in continuity or []:
        parent_application = _clean(entry.get("parentApplicationNumberText"))
        child_application = _clean(entry.get("childApplicationNumberText"))
        relationship = "parent" if parent_application else "child" if child_application else ""
        application_number = parent_application or child_application
        related_application_number = child_application if parent_application else parent_application
        entries.append(
            {
                "relationship": relationship or "related",
                "application_number": application_number,
                "related_application_number": related_application_number,
                "continuity_type": normalize_continuity_type(entry),
                "filing_date": _clean(entry.get("filingDate")),
            }
        )
    return entries


def normalize_amendment_events(
    transactions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for transaction in transactions or []:
        event_type = classify_transaction_type(transaction)
        if event_type == "other":
            continue
        events.append(
            {
                "transaction_code": _upper(transaction.get("transactionCode")),
                "description": _clean(transaction.get("transactionDescription")),
                "event_date": _clean(
                    transaction.get("transactionDate") or transaction.get("recordDate")
                ),
                "event_type": event_type,
                "claim_numbers": _extract_claim_numbers(
                    _clean(transaction.get("transactionDescription"))
                ),
            }
        )
    return events
