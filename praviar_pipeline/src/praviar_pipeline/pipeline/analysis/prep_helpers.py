"""Pure helpers for Step 4 analysis prep."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult


def build_triage_map(
    triage_results: list[TriageResult] | None,
) -> dict[str, TriageResult]:
    if not triage_results:
        return {}
    return {triage_result.patent_id: triage_result for triage_result in triage_results}


def build_enabled_analysis_tools(
    *,
    tools_enabled: bool,
    has_uspto_odp_api_key: bool,
) -> list[str] | None:
    if not tools_enabled:
        return None

    enabled_tools = ["get_current_date", "lookup_patent"]
    if has_uspto_odp_api_key:
        enabled_tools.append("check_patent_status")
    return enabled_tools


def format_office_actions_summary(office_actions: Sequence[dict[str, Any]]) -> str | None:
    lines = []
    for office_action in office_actions[:10]:
        code = office_action.get("documentCode", "")
        description = office_action.get(
            "documentDescription",
            office_action.get("documentCategory", ""),
        )
        date = office_action.get("mailDate", office_action.get("documentDate", ""))
        lines.append(f"- [{code}] {description} ({date})")
    return "\n".join(lines) if lines else None


def format_continuity_summary(continuity: Sequence[dict[str, Any]]) -> str | None:
    lines = []
    for entry in continuity[:10]:
        parent_application = entry.get("parentApplicationNumberText", "")
        child_application = entry.get("childApplicationNumberText", "")
        claim_type = entry.get("claimTypeCd", entry.get("continuityType", ""))
        filing_date = entry.get("filingDate", "")
        if parent_application:
            lines.append(f"- Parent: {parent_application} ({claim_type}, filed {filing_date})")
        elif child_application:
            lines.append(f"- Child: {child_application} ({claim_type}, filed {filing_date})")
    return "\n".join(lines) if lines else None


def format_amendments_summary(
    transactions: Sequence[dict[str, Any]],
) -> tuple[str | None, int]:
    amendment_codes = {
        "AMND",
        "RCE",
        "RESP.ARG",
        "AMAL",
        "AMEN",
        "A...",
        "REFU",
        "REEX",
        "REM",
        "REQA",
    }
    amendment_transactions = [
        transaction
        for transaction in transactions
        if transaction.get("transactionCode", "") in amendment_codes
        or "amend" in transaction.get("transactionDescription", "").lower()
        or "response" in transaction.get("transactionDescription", "").lower()
    ]
    lines = []
    for transaction in amendment_transactions[:15]:
        code = transaction.get("transactionCode", "")
        description = transaction.get("transactionDescription", "")
        date = transaction.get("transactionDate", transaction.get("recordDate", ""))
        lines.append(f"- [{code}] {description} ({date})")
    return ("\n".join(lines) if lines else None, len(amendment_transactions))


def filter_us_patents(patents: Sequence[PatentHit]) -> list[PatentHit]:
    return [patent for patent in patents if patent.patent_id.upper().startswith("US")]
