"""Patent-level evidence record builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from praviar_pipeline.models.patent import has_trusted_claim_text_provenance
from praviar_pipeline.models.report import PatentEvidenceRecord
from praviar_pipeline.pipeline.report.evidence_index_patent_helpers import (
    build_authoritative_record_categories,
    build_patent_component_statuses,
    build_patent_gate_failures,
    classify_source_authority,
    collect_source_names,
    derive_jurisdiction,
    normalize_dossier,
)
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.report.prosecution_helpers import (
    dossier_sections,
    has_file_wrapper_dossier,
)
from praviar_pipeline.pipeline.runtime.decisioning_signals import (
    PatentDetailSignals,
    build_future_risk_findings,
    extract_patent_detail_signals,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis


@dataclass(frozen=True)
class _FamilyEvidence:
    family_id: str
    member_count: int
    jurisdictions: list[str]
    broadest: bool
    has_context: bool


@dataclass(frozen=True)
class _DetailEvidence:
    legal_status: str
    is_granted: bool
    assignees: list[str]
    family: _FamilyEvidence
    application_number: str
    has_claims_text: bool
    has_assignments: bool
    has_priority_claims: bool
    has_ptab_proceedings: bool
    has_orange_book_listing: bool
    has_ep_register_context: bool
    has_opposition_events: bool


@dataclass(frozen=True)
class _AnalysisEvidence:
    title: str
    completed: bool
    failed: bool
    claims_analyzed_count: int
    risk_level: str
    doe_assessed: bool
    invalidity_assessed: bool


@dataclass(frozen=True)
class _SourceEvidence:
    names: list[str]
    authoritative_names: list[str]
    supporting_names: list[str]


def _analysis_quality_gate_failures(analysis: PatentAnalysis | None) -> list[str]:
    return unique_strings(
        list(getattr(analysis, "analysis_quality_gate_failures", []) or []) if analysis else []
    )


def _detail_signals(detail: object | None) -> PatentDetailSignals | None:
    return extract_patent_detail_signals(detail) if detail else None


def _future_risk_signals(
    *,
    patent_id: str,
    jurisdiction: str,
    analysis: PatentAnalysis | None,
    signals: PatentDetailSignals | None,
    dossier: object | None,
) -> list[str]:
    future_risks = (
        [
            finding.risk_type
            for finding in build_future_risk_findings(
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                risk_level=analysis.risk_level,
                signals=signals,
            )
        ]
        if analysis and signals
        else []
    )
    if dossier and bool(getattr(dossier, "pending_family_signal", False)):
        future_risks.append("pending_family")
    if dossier and bool(getattr(dossier, "terminal_disclaimer", False)):
        future_risks.append("terminal_disclaimer")
    return unique_strings(future_risks)


def _detail_prosecution_signals(signals: PatentDetailSignals | None) -> list[str]:
    prosecution_signals: list[str] = []
    if not signals:
        return prosecution_signals
    if signals.narrowing_signal:
        prosecution_signals.append("narrowing_signal")
    if signals.terminal_disclaimer:
        prosecution_signals.append("terminal_disclaimer")
    if signals.pending_family_signal:
        prosecution_signals.append("pending_family_signal")
    if signals.ptab_challenged:
        prosecution_signals.append("ptab_challenged")
    return prosecution_signals


def _dossier_estoppel_flags(dossier: object | None) -> list[str]:
    return list(
        (dossier.get("estoppel_risk_flags", []) if isinstance(dossier, dict) else [])
        or getattr(dossier, "estoppel_risk_flags", [])
        or []
    )


def _dossier_boolean_signals(dossier: object | None) -> list[str]:
    prosecution_signals: list[str] = []
    for field_name, signal_name in (
        ("narrowing_signal", "narrowing_signal"),
        ("terminal_disclaimer", "terminal_disclaimer"),
        ("ptab_challenged", "ptab_challenged"),
        ("pending_family_signal", "pending_family_signal"),
    ):
        if dossier and bool(getattr(dossier, field_name, False)):
            prosecution_signals.append(signal_name)
    return prosecution_signals


def _combined_prosecution_signals(
    initial_signals: list[str],
    *,
    dossier: object | None,
    has_us_file_wrapper_dossier: bool,
) -> list[str]:
    prosecution_signals = unique_strings(initial_signals + _dossier_estoppel_flags(dossier))
    prosecution_signals.extend(_dossier_boolean_signals(dossier))
    if has_us_file_wrapper_dossier:
        prosecution_signals.append("file_wrapper_dossier")
    return unique_strings(prosecution_signals)


def _critic_issue_severities(findings: list[object]) -> list[str]:
    return unique_strings(
        [
            getattr(
                getattr(finding, "severity", None),
                "value",
                str(getattr(finding, "severity", "")),
            )
            for finding in findings
        ]
    )


def _family_evidence(detail: object | None) -> _FamilyEvidence:
    family = getattr(detail, "family", None) if detail else None
    return _FamilyEvidence(
        family_id=getattr(family, "family_id", "") if family else "",
        member_count=len(getattr(family, "members", []) or []) if family else 0,
        jurisdictions=list(getattr(family, "jurisdictions", [])) if family else [],
        broadest=bool(getattr(detail, "family_broadest", False)) if detail else False,
        has_context=bool(family),
    )


def _detail_evidence(detail: object | None, *, jurisdiction: str) -> _DetailEvidence:
    family = _family_evidence(detail)
    if not detail:
        return _DetailEvidence(
            legal_status="",
            is_granted=True,
            assignees=[],
            family=family,
            application_number="",
            has_claims_text=False,
            has_assignments=False,
            has_priority_claims=False,
            has_ptab_proceedings=False,
            has_orange_book_listing=False,
            has_ep_register_context=False,
            has_opposition_events=False,
        )
    return _DetailEvidence(
        legal_status=getattr(getattr(detail, "legal_status", None), "value", ""),
        is_granted=getattr(detail, "is_granted", True),
        assignees=list(getattr(detail, "assignees", []) or []),
        family=family,
        application_number=getattr(detail, "application_number", ""),
        has_claims_text=has_trusted_claim_text_provenance(detail),
        has_assignments=bool(getattr(detail, "assignments", []) or []),
        has_priority_claims=bool(
            getattr(detail, "foreign_priority", None) or getattr(detail, "priority_claims", None)
        ),
        has_ptab_proceedings=bool(getattr(detail, "ptab_proceedings", []) or []),
        has_orange_book_listing=bool(getattr(detail, "orange_book_listed", False)),
        has_ep_register_context=bool(
            jurisdiction == "EP"
            and (
                getattr(detail, "designated_states", None)
                or getattr(detail, "priority_claims", None)
                or getattr(detail, "opposition_events", None)
            )
        ),
        has_opposition_events=bool(getattr(detail, "opposition_events", []) or []),
    )


def _analysis_evidence(
    patent_id: str,
    *,
    analysis: PatentAnalysis | None,
    detail: object | None,
    failure_by_id: dict[str, object],
    doe_patent_ids: set[str],
    invalidity_patent_ids: set[str],
) -> _AnalysisEvidence:
    title = (
        analysis.title
        if analysis and analysis.title
        else getattr(detail, "title", "")
        if detail
        else ""
    )
    return _AnalysisEvidence(
        title=title,
        completed=analysis is not None,
        failed=patent_id in failure_by_id,
        claims_analyzed_count=len(getattr(analysis, "claims_analyzed", []) or [])
        if analysis
        else 0,
        risk_level=getattr(getattr(analysis, "risk_level", None), "value", "") if analysis else "",
        doe_assessed=patent_id in doe_patent_ids,
        invalidity_assessed=patent_id in invalidity_patent_ids,
    )


def _source_evidence(
    *,
    detail: object | None,
    dossier: object | None,
    detail_evidence: _DetailEvidence,
) -> _SourceEvidence:
    source_names = collect_source_names(
        detail=detail,
        dossier=dossier,
        has_ptab_proceedings=detail_evidence.has_ptab_proceedings,
        has_orange_book_listing=detail_evidence.has_orange_book_listing,
        has_ep_register_context=detail_evidence.has_ep_register_context,
    )
    authoritative_names, supporting_names = classify_source_authority(source_names)
    return _SourceEvidence(
        names=source_names,
        authoritative_names=authoritative_names,
        supporting_names=supporting_names,
    )


def _authoritative_categories(
    *,
    jurisdiction: str,
    sources: _SourceEvidence,
    detail: _DetailEvidence,
    has_us_prosecution_context: bool,
    has_us_file_wrapper_dossier: bool,
) -> list[str]:
    return build_authoritative_record_categories(
        jurisdiction=jurisdiction,
        authoritative_source_names=sources.authoritative_names,
        has_family_context=detail.family.has_context,
        has_us_prosecution_context=has_us_prosecution_context,
        has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
        has_ep_register_context=detail.has_ep_register_context,
        has_assignments=detail.has_assignments,
        has_priority_claims=detail.has_priority_claims,
        has_ptab_proceedings=detail.has_ptab_proceedings,
        has_orange_book_listing=detail.has_orange_book_listing,
    )


def _assemble_patent_record(
    patent_id: str,
    *,
    jurisdiction: str,
    detail: _DetailEvidence,
    analysis: _AnalysisEvidence,
    sources: _SourceEvidence,
    authoritative_record_categories: list[str],
    has_us_prosecution_context: bool,
    has_us_file_wrapper_dossier: bool,
    prosecution_dossier_sections: list[str],
    critic_issue_count: int,
    critic_issue_severities: list[str],
    prosecution_signals: list[str],
    future_risk_signals: list[str],
) -> PatentEvidenceRecord:
    return PatentEvidenceRecord(
        patent_id=patent_id,
        title=analysis.title,
        jurisdiction=jurisdiction,
        legal_status=detail.legal_status,
        is_granted=detail.is_granted,
        source_names=sources.names,
        authoritative_source_names=sources.authoritative_names,
        supporting_source_names=sources.supporting_names,
        assignees=detail.assignees,
        family_id=detail.family.family_id,
        family_member_count=detail.family.member_count,
        family_jurisdictions=detail.family.jurisdictions,
        family_broadest=detail.family.broadest,
        application_number=detail.application_number,
        has_claims_text=detail.has_claims_text,
        has_family_context=detail.family.has_context,
        has_us_prosecution_context=has_us_prosecution_context,
        has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
        prosecution_dossier_sections=prosecution_dossier_sections,
        has_ep_register_context=detail.has_ep_register_context,
        has_assignments=detail.has_assignments,
        has_priority_claims=detail.has_priority_claims,
        has_ptab_proceedings=detail.has_ptab_proceedings,
        has_orange_book_listing=detail.has_orange_book_listing,
        has_opposition_events=detail.has_opposition_events,
        authoritative_record_categories=authoritative_record_categories,
        component_statuses=build_patent_component_statuses(
            patent_id=patent_id,
            jurisdiction=jurisdiction,
            has_claims_text=detail.has_claims_text,
            has_family_context=detail.family.has_context,
            has_authoritative_records=bool(authoritative_record_categories),
            has_us_prosecution_context=has_us_prosecution_context,
            has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
            has_ep_register_context=detail.has_ep_register_context,
            has_ptab_proceedings=detail.has_ptab_proceedings,
            has_orange_book_listing=detail.has_orange_book_listing,
            analysis_completed=analysis.completed,
            analysis_failed=analysis.failed,
            claims_analyzed_count=analysis.claims_analyzed_count,
            doe_assessed=analysis.doe_assessed,
            invalidity_assessed=analysis.invalidity_assessed,
        ),
        analysis_completed=analysis.completed,
        analysis_failed=analysis.failed,
        claims_analyzed_count=analysis.claims_analyzed_count,
        risk_level=analysis.risk_level,
        doe_assessed=analysis.doe_assessed,
        invalidity_assessed=analysis.invalidity_assessed,
        critic_issue_count=critic_issue_count,
        critic_issue_severities=critic_issue_severities,
        prosecution_signals=prosecution_signals,
        future_risk_signals=future_risk_signals,
    )


def build_patent_record(
    patent_id: str,
    *,
    analysis_by_id: dict[str, PatentAnalysis],
    detail_map: dict[str, object],
    doe_patent_ids: set[str],
    invalidity_patent_ids: set[str],
    failure_by_id: dict[str, object],
    critic_findings_by_patent: dict[str, list[object]],
    dossier_map: dict[str, object] | None = None,
) -> PatentEvidenceRecord:
    analysis = analysis_by_id.get(patent_id)
    analysis_quality_gate_failures = _analysis_quality_gate_failures(analysis)
    detail = detail_map.get(patent_id)
    dossier = normalize_dossier((dossier_map or {}).get(patent_id))
    jurisdiction = derive_jurisdiction(patent_id, detail)
    signals = _detail_signals(detail)
    future_risk_signals = _future_risk_signals(
        patent_id=patent_id,
        jurisdiction=jurisdiction,
        analysis=analysis,
        signals=signals,
        dossier=dossier,
    )
    prosecution_signals = _detail_prosecution_signals(signals)
    critic_findings = critic_findings_by_patent.get(patent_id, [])
    critic_issue_severities = _critic_issue_severities(critic_findings)
    detail_evidence = _detail_evidence(detail, jurisdiction=jurisdiction)
    source_evidence = _source_evidence(
        detail=detail,
        dossier=dossier,
        detail_evidence=detail_evidence,
    )
    has_us_prosecution_context = bool(
        jurisdiction == "US" and signals and signals.prosecution_available
    )
    prosecution_dossier_sections = dossier_sections(dossier)
    has_us_file_wrapper_dossier = bool(jurisdiction == "US" and has_file_wrapper_dossier(dossier))
    prosecution_signals = _combined_prosecution_signals(
        prosecution_signals,
        dossier=dossier,
        has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
    )
    authoritative_record_categories = _authoritative_categories(
        jurisdiction=jurisdiction,
        sources=source_evidence,
        detail=detail_evidence,
        has_us_prosecution_context=has_us_prosecution_context,
        has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
    )
    analysis_evidence = _analysis_evidence(
        patent_id,
        analysis=analysis,
        detail=detail,
        failure_by_id=failure_by_id,
        doe_patent_ids=doe_patent_ids,
        invalidity_patent_ids=invalidity_patent_ids,
    )
    record = _assemble_patent_record(
        patent_id,
        jurisdiction=jurisdiction,
        detail=detail_evidence,
        analysis=analysis_evidence,
        sources=source_evidence,
        authoritative_record_categories=authoritative_record_categories,
        has_us_prosecution_context=has_us_prosecution_context,
        has_us_file_wrapper_dossier=has_us_file_wrapper_dossier,
        prosecution_dossier_sections=prosecution_dossier_sections,
        critic_issue_count=len(critic_findings),
        critic_issue_severities=critic_issue_severities,
        prosecution_signals=prosecution_signals,
        future_risk_signals=future_risk_signals,
    )
    record.gate_failures = unique_strings(
        build_patent_gate_failures(record) + analysis_quality_gate_failures
    )
    record.clearance_grade_ready = len(record.gate_failures) == 0
    return record
