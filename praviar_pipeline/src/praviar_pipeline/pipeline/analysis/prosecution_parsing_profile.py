"""Profile derivation helpers for prosecution parsing."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.pipeline.analysis.prosecution_parsing_classifiers import _unique_strings


def derive_prosecution_profile(
    *,
    office_action_events: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    continuity_entries: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    amendment_events: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    office_action_events = list(office_action_events or [])
    continuity_entries = list(continuity_entries or [])
    amendment_events = list(amendment_events or [])

    office_action_types = _unique_strings(
        [str(event.get("office_action_type", "") or "") for event in office_action_events]
    )
    amendment_types = _unique_strings(
        [str(event.get("event_type", "") or "") for event in amendment_events]
    )
    continuity_types = _unique_strings(
        [str(entry.get("continuity_type", "") or "") for entry in continuity_entries]
    )
    rejection_bases = _unique_strings(
        [
            basis
            for event in office_action_events
            for basis in list(event.get("rejection_bases", []) or [])
        ]
    )

    continuation_parent_count = sum(
        entry.get("continuity_type") == "continuation" and entry.get("relationship") == "parent"
        for entry in continuity_entries
    )
    continuation_child_count = sum(
        entry.get("continuity_type") == "continuation" and entry.get("relationship") == "child"
        for entry in continuity_entries
    )
    divisional_parent_count = sum(
        entry.get("continuity_type") == "divisional" and entry.get("relationship") == "parent"
        for entry in continuity_entries
    )
    divisional_child_count = sum(
        entry.get("continuity_type") == "divisional" and entry.get("relationship") == "child"
        for entry in continuity_entries
    )
    cip_parent_count = sum(
        entry.get("continuity_type") == "cip" and entry.get("relationship") == "parent"
        for entry in continuity_entries
    )
    cip_child_count = sum(
        entry.get("continuity_type") == "cip" and entry.get("relationship") == "child"
        for entry in continuity_entries
    )
    response_after_final_count = sum(
        event.get("event_type") == "after_final_response" for event in amendment_events
    )
    rce_count = sum(event.get("event_type") == "rce" for event in amendment_events)
    interview_event_count = sum(
        event.get("event_type") == "interview" for event in amendment_events
    ) + sum(
        event.get("office_action_type") == "interview_summary" for event in office_action_events
    )
    appeal_event_count = sum(
        event.get("event_type") == "appeal" for event in amendment_events
    ) + sum(event.get("office_action_type") == "appeal_event" for event in office_action_events)

    estoppel_risk_flags: list[str] = []
    if response_after_final_count:
        estoppel_risk_flags.append("after_final_response_history")
    if rce_count:
        estoppel_risk_flags.append("rce_history")
    if interview_event_count:
        estoppel_risk_flags.append("interview_history")
    if appeal_event_count:
        estoppel_risk_flags.append("appeal_history")
    if continuation_parent_count or continuation_child_count:
        estoppel_risk_flags.append("continuation_lineage")
    if divisional_parent_count or divisional_child_count:
        estoppel_risk_flags.append("divisional_lineage")
    if cip_parent_count or cip_child_count:
        estoppel_risk_flags.append("cip_lineage")
    if any(base in {"102", "103", "prior_art"} for base in rejection_bases):
        estoppel_risk_flags.append("prior_art_rejection_history")
    if any(base in {"112", "112_a", "112_b"} for base in rejection_bases):
        estoppel_risk_flags.append("written_description_or_indefiniteness_history")
    if "double_patenting" in rejection_bases:
        estoppel_risk_flags.append("double_patenting_history")
    if any(event.get("event_type") == "terminal_disclaimer" for event in amendment_events):
        estoppel_risk_flags.append("terminal_disclaimer_history")
    if office_action_events and amendment_events:
        estoppel_risk_flags.append("amendment_after_office_action_history")

    return {
        "office_action_count": len(office_action_events),
        "continuity_entry_count": len(continuity_entries),
        "amendment_entry_count": len(amendment_events),
        "office_action_types": office_action_types,
        "amendment_types": amendment_types,
        "continuity_types": continuity_types,
        "rejection_bases": rejection_bases,
        "estoppel_risk_flags": _unique_strings(estoppel_risk_flags),
        "continuation_parent_count": continuation_parent_count,
        "continuation_child_count": continuation_child_count,
        "divisional_parent_count": divisional_parent_count,
        "divisional_child_count": divisional_child_count,
        "cip_parent_count": cip_parent_count,
        "cip_child_count": cip_child_count,
        "response_after_final_count": response_after_final_count,
        "rce_count": rce_count,
        "interview_event_count": interview_event_count,
        "appeal_event_count": appeal_event_count,
    }
