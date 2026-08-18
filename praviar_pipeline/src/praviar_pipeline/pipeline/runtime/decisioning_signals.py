"""Patent-level signal extraction for top-line clearance decisioning.

This module consolidates patent-detail signal extraction and the finding
builders derived from those signals. It exposes the signal dataclass, the
extraction entry point and the prosecution/future-risk finding builders.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report import FutureRiskFinding, ProsecutionFinding
from praviar_pipeline.pipeline.report.prosecution_helpers import (
    dossier_sections,
    dossier_source_name,
    has_file_wrapper_dossier,
)
from praviar_pipeline.utils.patent_family import (
    pending_family_member_ids,
    unresolved_family_member_ids,
)

__all__ = [
    "PatentDetailSignals",
    "build_future_risk_findings",
    "build_prosecution_finding",
    "extract_patent_detail_signals",
]


@dataclass(frozen=True)
class PatentDetailSignals:
    application_number: str
    prosecution_available: bool
    transaction_count: int
    amendment_event_count: int
    narrowing_signal: bool
    terminal_disclaimer: bool
    terminal_disclaimer_linked_patent: str
    ptab_challenged: bool
    ptab_proceeding_numbers: list[str]
    pending_family_signal: bool
    pending_family_member_ids: list[str]
    ep_register_status: str
    ep_opposition_event_count: int
    ep_limitation_event_count: int
    ep_revocation_event_count: int
    ep_lapse_event_count: int
    record_basis: list[str]
    unresolved_family_identity_signal: bool = False
    unresolved_family_member_ids: list[str] = field(default_factory=list)


def ep_event_counts(detail) -> tuple[int, int, int, int]:
    seen: set[tuple[str, str, str]] = set()
    opposition_count = 0
    limitation_count = 0
    revocation_count = 0
    lapse_count = 0
    events = list(getattr(detail, "opposition_events", []) or []) + list(
        getattr(detail, "legal_events", []) or []
    )
    for event in events:
        description = str(getattr(event, "event_description", "") or "").lower()
        code = str(getattr(event, "event_code", "") or "").upper()
        date = str(getattr(event, "event_date", "") or "")
        event_key = (date, code, description)
        if event_key in seen:
            continue
        seen.add(event_key)
        if "opposition" in description or "oppos" in description or code.startswith("OPP"):
            opposition_count += 1
        if "limitation" in description or "limited" in description or code.startswith("LIM"):
            limitation_count += 1
        if "revok" in description or code.startswith("REV"):
            revocation_count += 1
        if (
            "lapse" in description
            or "lapsed" in description
            or "withdraw" in description
            or code.startswith("LAP")
            or code.startswith("WIT")
        ):
            lapse_count += 1
    return opposition_count, limitation_count, revocation_count, lapse_count


def extract_patent_detail_signals(detail) -> PatentDetailSignals:
    application_number = getattr(detail, "application_number", "") or ""
    transactions = list(getattr(detail, "transactions", []) or [])
    transaction_count = len(transactions)
    amendment_event_count = sum(
        "amend" in (transaction.event_description or "").lower() for transaction in transactions
    )
    ptab_proceedings = list(getattr(detail, "ptab_proceedings", []) or [])
    ptab_proceeding_numbers = [
        str(getattr(proceeding, "proceeding_number", "") or "")
        for proceeding in ptab_proceedings
        if str(getattr(proceeding, "proceeding_number", "") or "")
    ]
    family = getattr(detail, "family", None)
    pending_member_ids = pending_family_member_ids(list(getattr(family, "members", []) or []))
    unresolved_member_ids = unresolved_family_member_ids(list(getattr(family, "members", []) or []))
    record_basis: list[str] = []
    if application_number:
        record_basis.append("application_number")
    if transactions:
        record_basis.append("uspto_transactions")
    if getattr(detail, "examiner", ""):
        record_basis.append("examiner_metadata")
    if getattr(detail, "attorney", ""):
        record_basis.append("attorney_metadata")
    if ptab_proceedings:
        record_basis.append("ptab_proceedings")
    if family:
        record_basis.append("family_members")

    ep_register_status = str(getattr(detail, "ep_register_status", "") or "")
    (
        ep_opposition_event_count,
        ep_limitation_event_count,
        ep_revocation_event_count,
        ep_lapse_event_count,
    ) = ep_event_counts(detail)
    if (
        ep_register_status
        or ep_opposition_event_count
        or ep_limitation_event_count
        or ep_revocation_event_count
        or ep_lapse_event_count
    ):
        record_basis.append("epo_register")

    prosecution_available = any(
        (
            bool(application_number),
            bool(transactions),
            bool(getattr(detail, "examiner", "")),
            bool(getattr(detail, "attorney", "")),
            bool(ep_register_status),
            ep_opposition_event_count > 0,
            ep_limitation_event_count > 0,
            ep_revocation_event_count > 0,
            ep_lapse_event_count > 0,
        )
    )
    patent_term_info = getattr(detail, "patent_term_info", None)
    terminal_disclaimer = bool(
        patent_term_info and getattr(patent_term_info, "terminal_disclaimer", False)
    )
    terminal_disclaimer_linked_patent = (
        str(getattr(patent_term_info, "td_linked_patent", "") or "") if patent_term_info else ""
    )
    if terminal_disclaimer:
        record_basis.append("patent_term_info")

    return PatentDetailSignals(
        application_number=application_number,
        prosecution_available=prosecution_available,
        transaction_count=transaction_count,
        amendment_event_count=amendment_event_count,
        narrowing_signal=amendment_event_count > 0,
        terminal_disclaimer=terminal_disclaimer,
        terminal_disclaimer_linked_patent=terminal_disclaimer_linked_patent,
        ptab_challenged=bool(ptab_proceedings),
        ptab_proceeding_numbers=ptab_proceeding_numbers,
        pending_family_signal=bool(pending_member_ids),
        pending_family_member_ids=pending_member_ids,
        ep_register_status=ep_register_status,
        ep_opposition_event_count=ep_opposition_event_count,
        ep_limitation_event_count=ep_limitation_event_count,
        ep_revocation_event_count=ep_revocation_event_count,
        ep_lapse_event_count=ep_lapse_event_count,
        record_basis=record_basis,
        unresolved_family_identity_signal=bool(unresolved_member_ids),
        unresolved_family_member_ids=unresolved_member_ids,
    )


def dossier_list(dossier, field: str) -> list:
    if dossier is None:
        return []
    if isinstance(dossier, dict):
        return list(dossier.get(field, []) or [])
    return list(getattr(dossier, field, []) or [])


def dossier_int(dossier, field: str) -> int:
    if dossier is None:
        return 0
    if isinstance(dossier, dict):
        return int(dossier.get(field, 0) or 0)
    return int(getattr(dossier, field, 0) or 0)


def dossier_int_list(dossier, field: str) -> list[int]:
    values = dossier_list(dossier, field)
    normalized: list[int] = []
    for value in values:
        if isinstance(value, int):
            normalized.append(value)
            continue
        text = str(value).strip()
        if text.isdigit():
            normalized.append(int(text))
    return normalized


def build_prosecution_finding(
    *,
    patent_id: str,
    jurisdiction: str,
    signals: PatentDetailSignals,
    dossier=None,
) -> ProsecutionFinding | None:
    summary_parts: list[str] = []
    dossier_available = has_file_wrapper_dossier(dossier)
    dossier_sections_available = dossier_sections(dossier)
    office_action_types = dossier_list(dossier, "office_action_types")
    amendment_types = dossier_list(dossier, "amendment_types")
    continuity_types = dossier_list(dossier, "continuity_types")
    rejected_claim_numbers = dossier_int_list(dossier, "rejected_claim_numbers")
    narrowing_claim_numbers = dossier_int_list(dossier, "narrowing_claim_numbers")
    rejection_bases = dossier_list(dossier, "rejection_bases")
    estoppel_risk_flags = dossier_list(dossier, "estoppel_risk_flags")
    office_action_count = dossier_int(dossier, "office_action_count")
    continuity_entry_count = dossier_int(dossier, "continuity_entry_count")
    continuation_parent_count = dossier_int(dossier, "continuation_parent_count")
    continuation_child_count = dossier_int(dossier, "continuation_child_count")
    divisional_parent_count = dossier_int(dossier, "divisional_parent_count")
    divisional_child_count = dossier_int(dossier, "divisional_child_count")
    cip_parent_count = dossier_int(dossier, "cip_parent_count")
    cip_child_count = dossier_int(dossier, "cip_child_count")
    response_after_final_count = dossier_int(dossier, "response_after_final_count")
    rce_count = dossier_int(dossier, "rce_count")
    interview_event_count = dossier_int(dossier, "interview_event_count")
    appeal_event_count = dossier_int(dossier, "appeal_event_count")
    prosecution_history_available = signals.prosecution_available or dossier_available

    if prosecution_history_available:
        summary_parts.append("file-wrapper context available")
    if dossier_available:
        summary_parts.append(
            f"file-wrapper dossier captured ({', '.join(dossier_sections_available)})"
        )
    if office_action_count:
        summary_parts.append(f"{office_action_count} office action record(s) captured")
    if continuity_entry_count:
        summary_parts.append(f"{continuity_entry_count} continuity record(s) captured")
    if signals.transaction_count:
        summary_parts.append(f"{signals.transaction_count} prosecution transactions captured")
    if signals.narrowing_signal:
        summary_parts.append(f"{signals.amendment_event_count} amendment signal(s) detected")
    if signals.terminal_disclaimer:
        summary_parts.append("terminal disclaimer present")
    if rejection_bases:
        summary_parts.append(f"rejection bases: {', '.join(rejection_bases)}")
    if rejected_claim_numbers:
        summary_parts.append(
            "rejected claims: " + ", ".join(str(number) for number in rejected_claim_numbers[:6])
        )
    if narrowing_claim_numbers:
        summary_parts.append(
            "narrowed claims: " + ", ".join(str(number) for number in narrowing_claim_numbers[:6])
        )
    if estoppel_risk_flags:
        summary_parts.append(
            "doctrine flags: " + ", ".join(estoppel_risk_flags[:3]).replace("_", " ")
        )
    if signals.pending_family_signal:
        summary_parts.append(
            f"{len(signals.pending_family_member_ids)} pending family member(s) detected"
        )
    if signals.unresolved_family_identity_signal:
        summary_parts.append(
            f"{len(signals.unresolved_family_member_ids)} family member application "
            "identity check(s) unresolved"
        )
    if signals.ptab_challenged:
        summary_parts.append(f"{len(signals.ptab_proceeding_numbers)} PTAB proceeding(s) present")
    if signals.ep_register_status:
        summary_parts.append(f"EP register status: {signals.ep_register_status}")
    if signals.ep_opposition_event_count:
        summary_parts.append(f"{signals.ep_opposition_event_count} EP opposition event(s) captured")
    if signals.ep_limitation_event_count:
        summary_parts.append(f"{signals.ep_limitation_event_count} EP limitation event(s) captured")
    if signals.ep_revocation_event_count:
        summary_parts.append(f"{signals.ep_revocation_event_count} EP revocation event(s) captured")
    if signals.ep_lapse_event_count:
        summary_parts.append(
            f"{signals.ep_lapse_event_count} EP lapse/withdrawal event(s) captured"
        )

    if not summary_parts:
        return None

    return ProsecutionFinding(
        patent_id=patent_id,
        jurisdiction=jurisdiction,
        application_number=signals.application_number,
        prosecution_history_available=prosecution_history_available,
        transaction_count=signals.transaction_count,
        amendment_event_count=signals.amendment_event_count,
        narrowing_signal=signals.narrowing_signal,
        terminal_disclaimer=signals.terminal_disclaimer,
        terminal_disclaimer_linked_patent=signals.terminal_disclaimer_linked_patent,
        ptab_challenged=signals.ptab_challenged,
        ptab_proceeding_count=len(signals.ptab_proceeding_numbers),
        pending_family_signal=signals.pending_family_signal,
        pending_family_member_count=len(signals.pending_family_member_ids),
        ep_register_status=signals.ep_register_status,
        ep_opposition_event_count=signals.ep_opposition_event_count,
        ep_limitation_event_count=signals.ep_limitation_event_count,
        ep_revocation_event_count=signals.ep_revocation_event_count,
        ep_lapse_event_count=signals.ep_lapse_event_count,
        office_action_count=office_action_count,
        continuity_entry_count=continuity_entry_count,
        office_action_types=office_action_types,
        amendment_types=amendment_types,
        continuity_types=continuity_types,
        rejected_claim_numbers=rejected_claim_numbers,
        narrowing_claim_numbers=narrowing_claim_numbers,
        rejection_bases=rejection_bases,
        estoppel_risk_flags=estoppel_risk_flags,
        continuation_parent_count=continuation_parent_count,
        continuation_child_count=continuation_child_count,
        divisional_parent_count=divisional_parent_count,
        divisional_child_count=divisional_child_count,
        cip_parent_count=cip_parent_count,
        cip_child_count=cip_child_count,
        response_after_final_count=response_after_final_count,
        rce_count=rce_count,
        interview_event_count=interview_event_count,
        appeal_event_count=appeal_event_count,
        record_basis=list(
            dict.fromkeys(
                [
                    *([dossier_source_name(dossier)] if dossier_available else []),
                    *signals.record_basis,
                ]
            )
        ),
        summary=", ".join(summary_parts),
    )


def build_future_risk_findings(
    *,
    patent_id: str,
    jurisdiction: str,
    risk_level: RiskLevel,
    signals: PatentDetailSignals,
) -> list[FutureRiskFinding]:
    findings: list[FutureRiskFinding] = []

    if signals.pending_family_signal:
        findings.append(
            FutureRiskFinding(
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                risk_type="pending_family",
                severity="high" if risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM) else "medium",
                monitoring_required=True,
                related_patent_ids=signals.pending_family_member_ids,
                record_basis=["family_members"],
                summary=(
                    "Patent family includes pending application-family members "
                    f"({len(signals.pending_family_member_ids)}) that can change "
                    "forward-looking exposure."
                ),
            )
        )

    if signals.unresolved_family_identity_signal:
        findings.append(
            FutureRiskFinding(
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                risk_type="family_identity_unresolved",
                severity="medium",
                monitoring_required=True,
                related_patent_ids=signals.unresolved_family_member_ids,
                record_basis=["family_members"],
                summary=(
                    "Application identity is not authoritatively resolved for "
                    f"{len(signals.unresolved_family_member_ids)} A-publication "
                    "family member(s); pending/superseded posture requires review."
                ),
            )
        )

    if signals.terminal_disclaimer:
        findings.append(
            FutureRiskFinding(
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                risk_type="terminal_disclaimer",
                severity="medium",
                monitoring_required=True,
                related_patent_ids=(
                    [signals.terminal_disclaimer_linked_patent]
                    if signals.terminal_disclaimer_linked_patent
                    else []
                ),
                record_basis=["patent_term_info"],
                summary=(
                    "Terminal disclaimer links expiry and enforceability to "
                    "related patents in the family."
                ),
            )
        )

    if signals.ep_opposition_event_count:
        findings.append(
            FutureRiskFinding(
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                risk_type="ep_opposition",
                severity="high" if risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM) else "medium",
                monitoring_required=True,
                related_patent_ids=[],
                record_basis=["epo_register"],
                summary=(
                    "EPO register records show opposition or opposition-related "
                    "post-grant activity that can materially change EP enforceability."
                ),
            )
        )

    return findings
