"""Execution helpers for report verification tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.agents.tools.report_verification_tool_matching import normalize_assignee

if TYPE_CHECKING:
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore


async def exec_check_patent_exists(store: ReportDataStore, input_data: dict) -> str:
    patent_id = input_data.get("patent_id", "")
    analysis = store.get_analysis(patent_id)
    if analysis is None:
        return (
            f"NOT FOUND: Patent {patent_id} does not exist in pipeline data. "
            f"Known patents: {', '.join(sorted(store.all_patent_ids())[:20])}"
        )
    return (
        f"FOUND: {patent_id} — risk_level={analysis.risk_level.value}, "
        f"assignee={analysis.assignee}, expiry={analysis.expiry_date}"
    )


async def exec_check_risk_level(store: ReportDataStore, input_data: dict) -> str:
    patent_id = input_data.get("patent_id", "")
    claimed = input_data.get("claimed_risk_level", "").lower().strip()
    analysis = store.get_analysis(patent_id)
    if analysis is None:
        return f"CANNOT VERIFY: Patent {patent_id} not in pipeline data."

    actual = analysis.risk_level.value
    if claimed == actual:
        return f"MATCH: {patent_id} risk level is correctly stated as {actual.upper()}."
    return (
        f"MISMATCH: {patent_id} risk level — "
        f"report says '{claimed.upper()}', actual is '{actual.upper()}'."
    )


async def exec_check_element_status(store: ReportDataStore, input_data: dict) -> str:
    patent_id = input_data.get("patent_id", "")
    claim_num = input_data.get("claim_number", 0)
    elem_num = input_data.get("element_number", 0)
    claimed = input_data.get("claimed_status", "").lower().strip()

    analysis = store.get_analysis(patent_id)
    if analysis is None:
        return f"CANNOT VERIFY: Patent {patent_id} not in pipeline data."

    for claim in analysis.claims_analyzed:
        if claim.claim_number != claim_num:
            continue
        for elem in claim.elements:
            if elem.element_number != elem_num:
                continue
            actual = elem.status.value
            if claimed == actual:
                return (
                    f"MATCH: {patent_id} Claim {claim_num} Element {elem_num} "
                    f"is correctly stated as {actual.upper()}. "
                    f"Reasoning: {elem.reasoning[:200]}"
                )
            return (
                f"MISMATCH: {patent_id} Claim {claim_num} Element {elem_num} — "
                f"report says '{claimed.upper()}', actual is '{actual.upper()}'. "
                f"Actual reasoning: {elem.reasoning[:200]}"
            )
        return (
            f"CANNOT VERIFY: Claim {claim_num} of {patent_id} has no "
            f"element {elem_num}. Elements: "
            f"{[e.element_number for e in claim.elements]}"
        )

    return (
        f"CANNOT VERIFY: {patent_id} has no Claim {claim_num}. "
        f"Claims: {[c.claim_number for c in analysis.claims_analyzed]}"
    )


async def exec_check_date(store: ReportDataStore, input_data: dict) -> str:
    patent_id = input_data.get("patent_id", "")
    date_type = input_data.get("date_type", "").lower().strip()
    claimed_date = input_data.get("claimed_date", "").strip()

    analysis = store.get_analysis(patent_id)
    detail = store.get_patent_detail(patent_id)
    actual_date = None

    if date_type == "expiry":
        if analysis and analysis.expiry_date:
            actual_date = str(analysis.expiry_date)
        elif detail and detail.get("patent_term_info", {}).get("adjusted_expiry"):
            actual_date = str(detail["patent_term_info"]["adjusted_expiry"])
    elif date_type == "filing":
        if detail:
            actual_date = detail.get("filing_date", "")
    elif date_type == "grant" and detail:
        actual_date = detail.get("grant_date", "")
    elif date_type == "priority" and detail:
        actual_date = detail.get("priority_date", "")

    if not actual_date:
        return f"CANNOT VERIFY: No {date_type} date found for {patent_id} in pipeline data."

    actual_norm = str(actual_date)[:10]
    claimed_norm = claimed_date[:10]

    if actual_norm == claimed_norm:
        return f"MATCH: {patent_id} {date_type} date is correctly stated as {actual_norm}."
    if actual_norm[:4] == claimed_norm[:4]:
        return (
            f"PARTIAL MATCH: {patent_id} {date_type} date — "
            f"report says '{claimed_date}', actual is '{actual_norm}'. "
            f"Year matches but exact date differs."
        )
    return (
        f"MISMATCH: {patent_id} {date_type} date — "
        f"report says '{claimed_date}', actual is '{actual_norm}'."
    )


async def exec_check_assignee(store: ReportDataStore, input_data: dict) -> str:
    patent_id = input_data.get("patent_id", "")
    claimed = input_data.get("claimed_assignee", "")

    analysis = store.get_analysis(patent_id)
    if analysis is None:
        return f"CANNOT VERIFY: Patent {patent_id} not in pipeline data."

    actual = analysis.assignee
    if claimed.lower().strip() == actual.lower().strip():
        return f"MATCH: {patent_id} assignee is correctly stated as '{actual}'."

    normalized_claimed = normalize_assignee(claimed)
    normalized_actual = normalize_assignee(actual)
    if normalized_claimed == normalized_actual:
        return (
            f"MATCH (fuzzy): {patent_id} assignee — "
            f"report says '{claimed}', data says '{actual}'. "
            f"These are equivalent after normalization."
        )
    if normalized_claimed in normalized_actual or normalized_actual in normalized_claimed:
        return (
            f"PARTIAL MATCH: {patent_id} assignee — "
            f"report says '{claimed}', data says '{actual}'. "
            f"One name contains the other."
        )
    return f"MISMATCH: {patent_id} assignee — report says '{claimed}', actual is '{actual}'."
