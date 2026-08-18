"""Coverage-context helpers for deterministic matter-level decisioning.

This module consolidates the coverage-rollup helper builders and the
coverage-context assembly that drives deterministic matter-level decisioning.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.patent import (
    has_trusted_claim_text_provenance,
    trusted_legal_status_conflict,
)
from praviar_pipeline.models.report import EvidenceCoverageSummary
from praviar_pipeline.pipeline.report.prosecution_helpers import has_file_wrapper_dossier
from praviar_pipeline.pipeline.runtime.decisioning_metrics import derive_jurisdiction
from praviar_pipeline.pipeline.runtime.decisioning_signals import (
    build_future_risk_findings,
    build_prosecution_finding,
    extract_patent_detail_signals,
)

_JURISDICTION_SORT_ORDER = {"US": 0, "EP": 1}
_FUTURE_RISK_SORT_ORDER = {
    "pending_family": 0,
    "terminal_disclaimer": 1,
    "ep_opposition": 2,
}


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique


def build_verification_gaps(report) -> list[str]:
    gaps: list[str] = []

    for issue in report.verification.issues:
        if issue:
            gaps.append(issue)

    for check in report.verification.checks:
        if check.passed and check.severity == "pass":
            continue
        if check.details:
            gaps.append(f"{check.check_name}: {check.details}")
        else:
            gaps.append(f"{check.check_name}: {check.severity}")

    summary_failures = (
        ("all_citations_valid", "Citation validation did not fully pass."),
        ("all_claims_grounded", "Claim grounding validation did not fully pass."),
        ("all_entities_valid", "Entity validation did not fully pass."),
        ("dates_consistent", "Date-consistency validation did not fully pass."),
        ("risk_levels_justified", "Risk-justification validation did not fully pass."),
    )
    for field_name, description in summary_failures:
        if not getattr(report.verification, field_name, False):
            gaps.append(description)

    return unique_strings(gaps)


@dataclass(slots=True)
class CoverageRollup:
    jurisdiction_patents: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    blocking_by_jurisdiction: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    prosecution_findings: list = field(default_factory=list)
    future_risk: list = field(default_factory=list)
    reviewed_patent_ids: list[str] = field(default_factory=list)
    reviewed_us_patent_ids: list[str] = field(default_factory=list)
    reviewed_ep_patent_ids: list[str] = field(default_factory=list)
    patents_missing_claims: list[str] = field(default_factory=list)
    patents_missing_family_context: list[str] = field(default_factory=list)
    us_patents_missing_prosecution_context: list[str] = field(default_factory=list)
    us_patents_missing_file_wrapper_dossier: list[str] = field(default_factory=list)
    ep_patents_missing_register_context: list[str] = field(default_factory=list)
    patents_with_claims: int = 0
    patents_with_family: int = 0
    us_patents: int = 0
    ep_patents: int = 0
    us_patents_with_prosecution_context: int = 0
    us_patents_with_file_wrapper_dossier: int = 0
    ep_patents_with_register_context: int = 0
    authoritative_record_contradictions: list[str] = field(default_factory=list)
    authoritative_record_contradictions_by_jurisdiction: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _dossier_patent_id(dossier) -> str:
    if isinstance(dossier, dict):
        return str(dossier.get("patent_id", "") or "")
    return str(getattr(dossier, "patent_id", "") or "")


def _build_dossier_map(prosecution_dossiers: list | None) -> dict[str, object]:
    return {
        patent_id: dossier
        for dossier in prosecution_dossiers or []
        if (patent_id := _dossier_patent_id(dossier))
    }


def _has_ep_register_context(detail) -> bool:
    return bool(
        getattr(detail, "designated_states", None)
        or getattr(detail, "priority_claims", None)
        or getattr(detail, "opposition_events", None)
    )


def _record_authoritative_contradiction(
    rollup: CoverageRollup,
    *,
    jurisdiction: str,
    summary: str,
) -> None:
    if summary in rollup.authoritative_record_contradictions:
        return
    rollup.authoritative_record_contradictions.append(summary)
    if jurisdiction:
        rollup.authoritative_record_contradictions_by_jurisdiction[jurisdiction].append(summary)


def collect_coverage_rollup(report, detail_map: dict[str, object]) -> CoverageRollup:
    rollup = CoverageRollup()
    dossier_map = _build_dossier_map(getattr(report, "prosecution_dossiers", []) or [])

    for analysis in report.patent_analyses:
        detail = detail_map.get(analysis.patent_id)
        detail_json = detail.model_dump(mode="json") if isinstance(detail, BaseModel) else None
        jurisdiction = derive_jurisdiction(analysis.patent_id, detail_json)
        rollup.reviewed_patent_ids.append(analysis.patent_id)

        if jurisdiction:
            rollup.jurisdiction_patents[jurisdiction].append(analysis.patent_id)
            if analysis.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
                rollup.blocking_by_jurisdiction[jurisdiction].append(analysis.patent_id)
        if jurisdiction == "US":
            rollup.reviewed_us_patent_ids.append(analysis.patent_id)
            rollup.us_patents += 1
        if jurisdiction == "EP":
            rollup.reviewed_ep_patent_ids.append(analysis.patent_id)
            rollup.ep_patents += 1

        if detail and has_trusted_claim_text_provenance(detail):
            rollup.patents_with_claims += 1
        else:
            rollup.patents_missing_claims.append(analysis.patent_id)
        if detail and getattr(detail, "family", None):
            rollup.patents_with_family += 1
        else:
            rollup.patents_missing_family_context.append(analysis.patent_id)

        if not detail:
            if jurisdiction == "US":
                rollup.us_patents_missing_prosecution_context.append(analysis.patent_id)
                rollup.us_patents_missing_file_wrapper_dossier.append(analysis.patent_id)
            if jurisdiction == "EP":
                rollup.ep_patents_missing_register_context.append(analysis.patent_id)
            continue

        signals = extract_patent_detail_signals(detail)
        dossier = dossier_map.get(analysis.patent_id)
        status_conflict = trusted_legal_status_conflict(detail)
        if status_conflict:
            statuses = ", ".join(status.value for status in status_conflict)
            _record_authoritative_contradiction(
                rollup,
                jurisdiction=jurisdiction,
                summary=(
                    f"Decision evidence for {analysis.patent_id} conflicts with "
                    f"authoritative legal status observations: {statuses}."
                ),
            )
        if jurisdiction == "US" and signals.prosecution_available:
            rollup.us_patents_with_prosecution_context += 1
        elif jurisdiction == "US":
            rollup.us_patents_missing_prosecution_context.append(analysis.patent_id)
        if jurisdiction == "US" and has_file_wrapper_dossier(dossier):
            rollup.us_patents_with_file_wrapper_dossier += 1
        elif jurisdiction == "US":
            rollup.us_patents_missing_file_wrapper_dossier.append(analysis.patent_id)
        if jurisdiction == "EP" and _has_ep_register_context(detail):
            rollup.ep_patents_with_register_context += 1
        elif jurisdiction == "EP":
            rollup.ep_patents_missing_register_context.append(analysis.patent_id)

        prosecution_finding = build_prosecution_finding(
            patent_id=analysis.patent_id,
            jurisdiction=jurisdiction,
            signals=signals,
            dossier=dossier,
        )
        if prosecution_finding:
            rollup.prosecution_findings.append(prosecution_finding)

        rollup.future_risk.extend(
            build_future_risk_findings(
                patent_id=analysis.patent_id,
                jurisdiction=jurisdiction,
                risk_level=analysis.risk_level,
                signals=signals,
            )
        )

    return rollup


def build_coverage_summary(report, rollup: CoverageRollup) -> EvidenceCoverageSummary:
    return EvidenceCoverageSummary(
        queried_source_names=unique_strings(
            [
                entry.source
                for entry in report.source_health.entries
                if entry.status.value != "skipped"
            ]
        ),
        successful_source_names=unique_strings(
            [entry.source for entry in report.source_health.entries if entry.status.value == "ok"]
        ),
        failed_source_names=report.source_health.failed_sources,
        reviewed_patent_ids=unique_strings(rollup.reviewed_patent_ids),
        reviewed_us_patent_ids=unique_strings(rollup.reviewed_us_patent_ids),
        reviewed_ep_patent_ids=unique_strings(rollup.reviewed_ep_patent_ids),
        patents_missing_claims=unique_strings(rollup.patents_missing_claims),
        patents_missing_family_context=unique_strings(rollup.patents_missing_family_context),
        us_patents_missing_prosecution_context=unique_strings(
            rollup.us_patents_missing_prosecution_context
        ),
        us_patents_missing_file_wrapper_dossier=unique_strings(
            rollup.us_patents_missing_file_wrapper_dossier
        ),
        ep_patents_missing_register_context=unique_strings(
            rollup.ep_patents_missing_register_context
        ),
        failed_analysis_patent_ids=unique_strings(
            [failure.patent_id for failure in report.analysis_failures]
        ),
        verification_gaps=build_verification_gaps(report),
    )


def _prosecution_sort_key(finding) -> tuple[int, str]:
    return (
        _JURISDICTION_SORT_ORDER.get(getattr(finding, "jurisdiction", ""), 99),
        str(getattr(finding, "patent_id", "") or ""),
    )


def _future_risk_sort_key(finding) -> tuple[int, str, int]:
    return (
        _JURISDICTION_SORT_ORDER.get(getattr(finding, "jurisdiction", ""), 99),
        str(getattr(finding, "patent_id", "") or ""),
        _FUTURE_RISK_SORT_ORDER.get(getattr(finding, "risk_type", ""), 99),
    )


@dataclass(slots=True)
class DecisionCoverageContext:
    jurisdiction_patents: dict[str, list[str]]
    blocking_by_jurisdiction: dict[str, list[str]]
    prosecution_findings: list
    future_risk: list
    blocking_patent_ids: list[str]
    analyses_by_id: dict[str, object]
    coverage_summary: EvidenceCoverageSummary
    patents_with_claims: int
    patents_with_family: int
    us_patents: int
    ep_patents: int
    us_patents_with_prosecution_context: int
    us_patents_with_file_wrapper_dossier: int
    ep_patents_with_register_context: int
    queried_sources: int
    ok_sources: int
    material_patent_count: int
    required_record_components: list[str]
    authoritative_record_contradictions: list[str]
    authoritative_record_contradictions_by_jurisdiction: dict[str, list[str]]


def build_decision_coverage_context(
    report,
    detail_map: dict[str, object],
) -> DecisionCoverageContext:
    blocking_patent_ids = [
        analysis.patent_id
        for analysis in report.patent_analyses
        if analysis.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)
    ]
    analyses_by_id = {analysis.patent_id: analysis for analysis in report.patent_analyses}
    rollup = collect_coverage_rollup(report, detail_map)
    coverage_summary = build_coverage_summary(report, rollup)

    return DecisionCoverageContext(
        jurisdiction_patents=dict(rollup.jurisdiction_patents),
        blocking_by_jurisdiction=dict(rollup.blocking_by_jurisdiction),
        prosecution_findings=sorted(rollup.prosecution_findings, key=_prosecution_sort_key),
        future_risk=sorted(rollup.future_risk, key=_future_risk_sort_key),
        blocking_patent_ids=blocking_patent_ids,
        analyses_by_id=analyses_by_id,
        coverage_summary=coverage_summary,
        patents_with_claims=rollup.patents_with_claims,
        patents_with_family=rollup.patents_with_family,
        us_patents=rollup.us_patents,
        ep_patents=rollup.ep_patents,
        us_patents_with_prosecution_context=rollup.us_patents_with_prosecution_context,
        us_patents_with_file_wrapper_dossier=rollup.us_patents_with_file_wrapper_dossier,
        ep_patents_with_register_context=rollup.ep_patents_with_register_context,
        queried_sources=len(coverage_summary.queried_source_names),
        ok_sources=len(coverage_summary.successful_source_names),
        material_patent_count=len(report.patent_analyses),
        required_record_components=[],
        authoritative_record_contradictions=list(rollup.authoritative_record_contradictions),
        authoritative_record_contradictions_by_jurisdiction=dict(
            rollup.authoritative_record_contradictions_by_jurisdiction
        ),
    )
