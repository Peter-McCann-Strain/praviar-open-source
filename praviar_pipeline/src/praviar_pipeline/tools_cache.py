"""Cache and formatting helpers for FTO tool execution."""

from __future__ import annotations

from typing import Any


def format_cached_patent_lookup(
    patent_id: str,
    *,
    cached: dict[str, Any],
    abstract_truncation: int,
    claims_truncation: int,
) -> str:
    """Format a cached patent lookup result for LLM consumption."""
    parts = [f"Patent: {patent_id}"]
    for key, label in [
        ("title", "Title"),
        ("abstract", "Abstract"),
        ("filing_date", "Filing Date"),
        ("grant_date", "Grant Date"),
        ("priority_date", "Priority Date"),
        ("assignee", "Assignee"),
        ("claims_text", "Claims (excerpt)"),
    ]:
        value = cached.get(key)
        if not value:
            continue
        value_text = str(value)
        if key == "abstract" and len(value_text) > abstract_truncation:
            value_text = value_text[:abstract_truncation] + "... [truncated]"
        elif key == "claims_text" and len(value_text) > claims_truncation:
            value_text = value_text[:claims_truncation] + "... [truncated]"
        parts.append(f"{label}: {value_text}")
    return "\n".join(parts)


def build_status_from_cache(patent_id: str, cache: dict[str, dict]) -> str:
    """Build a patent status response from cached PatentHit data."""
    hit = cache.get(patent_id) or cache.get(f"_status_{patent_id}")
    if not hit:
        return (
            f"Patent status for {patent_id} is unavailable "
            "(USPTO ODP not configured and no cached data). "
            "Proceed with analysis using available claim text."
        )

    parts = [f"Patent: {patent_id} (from cached pipeline data)"]

    filing = hit.get("filing_date", "")
    if filing:
        parts.append(f"Filing Date: {filing}")

    assignee = hit.get("assignee", "")
    if assignee:
        parts.append(f"Assignee: {assignee}")

    legal_status = hit.get("legal_status", "")
    if legal_status:
        parts.append(f"Legal Status: {legal_status}")

    expiry = hit.get("expiry_date", "")
    if expiry:
        parts.append(f"Expected Expiry: {expiry}")

    legal_events = hit.get("legal_events", [])
    if legal_events:
        parts.append(f"Legal Events: {len(legal_events)} recorded")
        for event in legal_events[:5]:
            if isinstance(event, dict):
                parts.append(f"  - {event.get('date', '?')}: {event.get('description', '?')}")
            else:
                parts.append(f"  - {event}")

    parts.append(
        "Note: Full prosecution history unavailable (USPTO ODP not configured). "
        "Status derived from EPO/BigQuery enrichment data."
    )

    return "\n".join(parts)


def build_known_patent_cache(
    patents: list,
    *,
    claims_truncation: int,
) -> dict[str, dict[str, Any]]:
    """Serialize PatentHit-like objects into the toolkit cache."""
    known: dict[str, dict[str, Any]] = {}
    for patent in patents:
        entry: dict[str, Any] = {
            "title": patent.title,
            "abstract": patent.abstract,
            "filing_date": str(patent.filing_date) if patent.filing_date else "",
            "assignee": patent.assignees[0] if patent.assignees else "",
            "claims_text": patent.claims_text[:claims_truncation] if patent.claims_text else "",
        }
        if hasattr(patent, "legal_status"):
            entry["legal_status"] = patent.legal_status.value if patent.legal_status else ""
        if hasattr(patent, "legal_events") and patent.legal_events:
            entry["legal_events"] = [
                {"date": str(event.date) if event.date else "", "description": event.description}
                for event in patent.legal_events[:10]
            ]
        if hasattr(patent, "patent_term_info") and patent.patent_term_info:
            term_info = patent.patent_term_info
            expiry = getattr(term_info, "adjusted_expiry", None) or getattr(
                term_info,
                "expected_expiry",
                None,
            )
            if expiry:
                entry["expiry_date"] = str(expiry)
        known[patent.patent_id] = entry
    return known
