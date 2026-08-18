"""Structured prosecution dossier builders for final reports."""

from __future__ import annotations

from typing import Any

from praviar_pipeline.models.report import (
    ProsecutionAmendmentEvent,
    ProsecutionContinuityEntry,
    ProsecutionDossier,
    ProsecutionOfficeActionEvent,
)
from praviar_pipeline.pipeline.runtime.decisioning_signals import extract_patent_detail_signals


def _line_count(summary: str) -> int:
    return sum(1 for line in summary.splitlines() if line.strip().startswith("-"))


def _normalize_model_list(values: list[Any] | None, model_cls) -> list:
    normalized: list = []
    for value in values or []:
        if isinstance(value, model_cls):
            normalized.append(value)
        elif isinstance(value, dict):
            normalized.append(model_cls.model_validate(value))
    return normalized


def _humanize_flag(flag: str) -> str:
    mapping = {
        "after_final_response_history": "after-final response history present",
        "rce_history": "RCE history present",
        "interview_history": "interview history present",
        "appeal_history": "appeal history present",
        "continuation_lineage": "continuation lineage present",
        "divisional_lineage": "divisional lineage present",
        "cip_lineage": "CIP lineage present",
        "prior_art_rejection_history": "prior-art rejection history present",
        "written_description_or_indefiniteness_history": ("Section 112 history present"),
        "double_patenting_history": "double-patenting history present",
        "terminal_disclaimer_history": "terminal disclaimer filing history present",
        "amendment_after_office_action_history": "amendment-after-office-action history present",
    }
    return mapping.get(flag, flag.replace("_", " "))


def _build_summary(
    *,
    office_action_count: int,
    continuity_entry_count: int,
    amendment_entry_count: int,
    rejection_bases: list[str],
    estoppel_risk_flags: list[str],
    terminal_disclaimer: bool,
    ptab_challenged: bool,
    pending_family_signal: bool,
) -> str:
    parts: list[str] = []
    if office_action_count:
        parts.append(f"{office_action_count} office action record(s) summarized")
    if continuity_entry_count:
        parts.append(f"{continuity_entry_count} continuity record(s) summarized")
    if amendment_entry_count:
        parts.append(f"{amendment_entry_count} amendment/response record(s) summarized")
    if terminal_disclaimer:
        parts.append("terminal disclaimer noted")
    if ptab_challenged:
        parts.append("PTAB challenge history present")
    if pending_family_signal:
        parts.append("pending family member signal present")
    if rejection_bases:
        parts.append(f"rejection bases: {', '.join(rejection_bases)}")
    for flag in estoppel_risk_flags[:3]:
        parts.append(_humanize_flag(flag))
    return ", ".join(parts)


def build_prosecution_dossiers(
    *,
    analyses: list,
    patent_hits: list | None,
    prosecution_cache: dict[str, dict[str, Any]] | None,
) -> list[ProsecutionDossier]:
    """Build structured prosecution dossiers from cached Step 4 enrichment."""
    if not analyses or not prosecution_cache:
        return []

    detail_map = {
        getattr(hit, "patent_id", ""): hit
        for hit in (patent_hits or [])
        if getattr(hit, "patent_id", "")
    }

    dossiers: list[ProsecutionDossier] = []
    for analysis in analyses:
        context = prosecution_cache.get(analysis.patent_id)
        if not context:
            continue

        detail = detail_map.get(analysis.patent_id)
        signals = extract_patent_detail_signals(detail) if detail else None
        office_actions_summary = context.get("office_actions", "")
        continuity_summary = context.get("continuity", "")
        amendments_summary = context.get("amendments", "")
        office_action_events = _normalize_model_list(
            context.get("office_action_events"),
            ProsecutionOfficeActionEvent,
        )
        continuity_entries = _normalize_model_list(
            context.get("continuity_entries"),
            ProsecutionContinuityEntry,
        )
        amendment_events = _normalize_model_list(
            context.get("amendment_events"),
            ProsecutionAmendmentEvent,
        )
        sections_available = list(context.get("sections_available", []) or []) or [
            section
            for section in ("office_actions", "continuity", "amendments")
            if context.get(section)
        ]
        office_action_count = int(
            context.get("office_action_count")
            or len(office_action_events)
            or _line_count(office_actions_summary)
        )
        continuity_entry_count = int(
            context.get("continuity_entry_count")
            or len(continuity_entries)
            or _line_count(continuity_summary)
        )
        amendment_entry_count = int(
            context.get("amendment_entry_count")
            or len(amendment_events)
            or _line_count(amendments_summary)
        )
        office_action_types = list(context.get("office_action_types", []) or [])
        amendment_types = list(context.get("amendment_types", []) or [])
        continuity_types = list(context.get("continuity_types", []) or [])
        rejected_claim_numbers = list(context.get("rejected_claim_numbers", []) or [])
        narrowing_claim_numbers = list(context.get("narrowing_claim_numbers", []) or [])
        rejection_bases = list(context.get("rejection_bases", []) or [])
        estoppel_risk_flags = list(context.get("estoppel_risk_flags", []) or [])
        summary = _build_summary(
            office_action_count=office_action_count,
            continuity_entry_count=continuity_entry_count,
            amendment_entry_count=amendment_entry_count,
            rejection_bases=rejection_bases,
            estoppel_risk_flags=estoppel_risk_flags,
            terminal_disclaimer=bool(signals and signals.terminal_disclaimer),
            ptab_challenged=bool(signals and signals.ptab_challenged),
            pending_family_signal=bool(signals and signals.pending_family_signal),
        )

        dossiers.append(
            ProsecutionDossier(
                patent_id=analysis.patent_id,
                jurisdiction=str(getattr(detail, "jurisdiction", "") or "").upper()
                if detail
                else "",
                application_number=(
                    signals.application_number
                    if signals
                    else str(getattr(detail, "application_number", "") or "")
                ),
                sections_available=sections_available,
                office_actions_summary=office_actions_summary,
                continuity_summary=continuity_summary,
                amendments_summary=amendments_summary,
                office_action_events=office_action_events,
                continuity_entries=continuity_entries,
                amendment_events=amendment_events,
                office_action_count=office_action_count,
                continuity_entry_count=continuity_entry_count,
                amendment_entry_count=amendment_entry_count,
                office_action_types=office_action_types,
                amendment_types=amendment_types,
                continuity_types=continuity_types,
                rejected_claim_numbers=rejected_claim_numbers,
                narrowing_claim_numbers=narrowing_claim_numbers,
                rejection_bases=rejection_bases,
                estoppel_risk_flags=estoppel_risk_flags,
                continuation_parent_count=int(context.get("continuation_parent_count", 0) or 0),
                continuation_child_count=int(context.get("continuation_child_count", 0) or 0),
                divisional_parent_count=int(context.get("divisional_parent_count", 0) or 0),
                divisional_child_count=int(context.get("divisional_child_count", 0) or 0),
                cip_parent_count=int(context.get("cip_parent_count", 0) or 0),
                cip_child_count=int(context.get("cip_child_count", 0) or 0),
                response_after_final_count=int(context.get("response_after_final_count", 0) or 0),
                rce_count=int(context.get("rce_count", 0) or 0),
                interview_event_count=int(context.get("interview_event_count", 0) or 0),
                appeal_event_count=int(context.get("appeal_event_count", 0) or 0),
                narrowing_signal=bool(signals and signals.narrowing_signal),
                terminal_disclaimer=bool(signals and signals.terminal_disclaimer),
                terminal_disclaimer_linked_patent=(
                    signals.terminal_disclaimer_linked_patent if signals else ""
                ),
                ptab_challenged=bool(signals and signals.ptab_challenged),
                pending_family_signal=bool(signals and signals.pending_family_signal),
                record_basis=(
                    list(dict.fromkeys(["uspto_odp", *(signals.record_basis if signals else [])]))
                ),
                summary=summary,
            )
        )

    return dossiers
