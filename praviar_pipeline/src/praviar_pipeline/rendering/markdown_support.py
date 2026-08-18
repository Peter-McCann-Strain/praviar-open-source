"""Pure helpers for Markdown report rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from praviar_pipeline.models.analysis import ClaimAnalysis, RiskLevel
    from praviar_pipeline.models.invalidity import GrahamFactors

_RISK_SORT_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
    "clear": 3,
}


def risk_sort_key(risk_level: RiskLevel) -> int:
    return _RISK_SORT_ORDER.get(risk_level.value, 4)


def format_claim_numbers(claims_analyzed: Sequence[ClaimAnalysis]) -> str:
    return ", ".join(str(claim.claim_number) for claim in claims_analyzed)


def format_ptab_status(detail: Mapping[str, Any]) -> str:
    ptab_procs = detail.get("ptab_proceedings", [])
    if ptab_procs:
        return f"{len(ptab_procs)} proceeding(s)"
    return "-"


def format_orange_book_status(
    detail: Mapping[str, Any],
    patent_orange_book: object | None,
) -> str:
    ob_info = detail.get("orange_book_info")
    if ob_info and ob_info.get("is_listed"):
        return "LISTED — DELIST REQUESTED" if ob_info.get("delist_requested") else "LISTED"

    if patent_orange_book and getattr(patent_orange_book, "is_listed", False):
        return (
            "LISTED — DELIST REQUESTED"
            if getattr(patent_orange_book, "delist_requested", False)
            else "LISTED"
        )

    return "-"


def format_patent_term_lines(term_info: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []

    if term_info.get("effective_filing_date"):
        lines.append(f"- **Effective Filing Date:** {term_info['effective_filing_date']}")
    if term_info.get("grant_date"):
        lines.append(f"- **Grant Date:** {term_info['grant_date']}")
    if term_info.get("adjusted_expiry"):
        lines.append(f"- **Adjusted Expiry:** {term_info['adjusted_expiry']}")
    if term_info.get("pta_days", 0) > 0:
        lines.append(f"- **Patent Term Adjustment:** {term_info['pta_days']} days")
        pta = term_info.get("pta_breakdown")
        if pta:
            lines.append(f"  - A delay (USPTO 14-month): {pta.get('a_delay_days', 0)} days")
            lines.append(f"  - B delay (USPTO 3-year): {pta.get('b_delay_days', 0)} days")
            lines.append(f"  - C delay (interference/appeal): {pta.get('c_delay_days', 0)} days")
            if pta.get("applicant_delay_days", 0) > 0:
                lines.append(f"  - Applicant delay: -{pta['applicant_delay_days']} days")
    if term_info.get("pte_days", 0) > 0:
        lines.append(f"- **Patent Term Extension (Hatch-Waxman):** {term_info['pte_days']} days")
    if term_info.get("terminal_disclaimer"):
        td_note = "Yes"
        if term_info.get("td_linked_patent"):
            td_note += f" (linked to {term_info['td_linked_patent']}"
            if term_info.get("td_linked_expiry"):
                td_note += f", expires {term_info['td_linked_expiry']}"
            td_note += ")"
        lines.append(f"- **Terminal Disclaimer:** {td_note}")
    mf = term_info.get("maintenance_fee_status", "unknown")
    if mf != "unknown":
        lines.append(f"- **Maintenance Fee Status:** {mf.upper()}")
    conf = term_info.get("calculation_confidence", 0)
    if conf > 0:
        lines.append(f"- **Calculation Confidence:** {conf:.0%}")

    return lines


def format_assignment_entry(asgn: Mapping[str, Any]) -> str:
    date_str = asgn.get("recorded_date", "Unknown")
    conveyance = asgn.get("conveyance", "Transfer")
    assignee = asgn.get("assignee", "")
    assignor = asgn.get("assignor", "")
    reel = asgn.get("reel_frame", "")

    entry = f"- **{date_str}**: {conveyance}"
    if assignor and assignee:
        entry += f" — {assignor} → {assignee}"
    elif assignee:
        entry += f" — to {assignee}"
    if reel:
        entry += f" (Reel/Frame: {reel})"
    return entry


def collect_family_jurisdictions(family: Mapping[str, Any]) -> list[str]:
    return sorted({m.get("country", "") for m in family.get("members", []) if m.get("country")})


def format_graham_factor_lines(
    graham_factors: GrahamFactors,
    max_chars: int,
) -> list[str]:
    return [
        f"- Scope: {graham_factors.scope_and_content[:max_chars]}",
        f"- Differences: {graham_factors.differences_from_prior_art[:max_chars]}",
        f"- Skill level: {graham_factors.level_of_ordinary_skill[:max_chars]}",
        f"- Assessment: {graham_factors.overall_obviousness_assessment[:max_chars]}",
    ]
