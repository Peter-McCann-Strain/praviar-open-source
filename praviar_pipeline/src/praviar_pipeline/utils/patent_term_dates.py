"""Date and continuity helpers for deterministic patent term calculation."""

from __future__ import annotations

from datetime import date

import structlog

logger = structlog.get_logger()


def _safe_add_years(d: date, years: int) -> date:
    """Add years to a date, handling Feb. 29 edge cases."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)


def _effective_filing_date_from_continuity(
    app_data: dict,
    continuity_data: list[dict],
) -> tuple[date | None, list[str]]:
    """Walk the continuity chain to find the effective filing date."""
    notes: list[str] = []

    filing_str = app_data.get("filingDate", "")
    filing_date: date | None = None
    if filing_str:
        try:
            filing_date = date.fromisoformat(filing_str[:10])
        except ValueError as exc:
            logger.error(
                "patent_term_malformed_filing_date",
                truncated=filing_str[:10],
            )
            raise ValueError(
                f"Malformed filing date '{filing_str}' in application data — "
                f"expected ISO format (YYYY-MM-DD)"
            ) from exc

    if not continuity_data:
        return filing_date, notes

    earliest = filing_date
    for parent in continuity_data:
        parent_filing = parent.get("parentFilingDate", "")
        if not parent_filing:
            parent_filing = parent.get("filingDate", "")
        parent_type = parent.get("claimType", parent.get("claimParentageTypeCode", "")).lower()
        type_desc = parent.get(
            "claimParentageTypeCodeDescriptionText",
            parent_type,
        ).lower()

        if not parent_filing:
            continue

        try:
            parent_date = date.fromisoformat(parent_filing[:10])
        except ValueError as exc:
            parent_app = parent.get(
                "parentApplicationNumber",
                parent.get("parentApplicationNumberText", "?"),
            )
            logger.error(
                "patent_term_malformed_parent_filing_date",
                truncated=parent_filing[:10],
            )
            raise ValueError(
                f"Malformed parent filing date '{parent_filing}' for parent "
                f"{parent_app} — expected ISO format (YYYY-MM-DD)"
            ) from exc

        is_term_affecting = (
            parent_type in ("continuation", "divisional", "continuation in part", "con", "div", "")
            or "continuation" in type_desc
            or "divisional" in type_desc
        )
        is_provisional = parent_type == "pro" or "provisional" in type_desc

        if (
            is_term_affecting
            and not is_provisional
            and (earliest is None or parent_date < earliest)
        ):
            earliest = parent_date
            parent_app = parent.get(
                "parentApplicationNumber",
                parent.get("parentApplicationNumberText", "?"),
            )
            notes.append(
                f"Effective filing date adjusted to parent "
                f"{parent_app} ({type_desc or parent_type}): "
                f"{parent_date.isoformat()}"
            )

    return earliest, notes


def extract_grant_date(patent_id: str, meta: dict, app_data: dict) -> date | None:
    """Extract and validate the grant date from ODP metadata."""
    grant_str = meta.get("grantDate", meta.get("patentIssueDate", ""))
    if not grant_str:
        grant_meta = app_data.get("grantDocumentMetaData", {})
        grant_str = grant_meta.get("grantDate", "")
    if not grant_str:
        return None

    try:
        return date.fromisoformat(grant_str[:10])
    except ValueError as exc:
        logger.error(
            "patent_term_malformed_grant_date",
            truncated=grant_str[:10],
        )
        raise ValueError(
            f"Malformed grant date '{grant_str}' for patent {patent_id} — "
            f"expected ISO format (YYYY-MM-DD)"
        ) from exc
