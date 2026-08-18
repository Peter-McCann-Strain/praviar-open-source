"""Decisive evidence reference helpers for deterministic matter decisions.

This module consolidates the shared decisive-reference helpers, the finding-
and gap-driven reference builders, the patent-specific reference builders, and
the top-level :func:`build_decisive_references` entry point.
"""

from __future__ import annotations

from praviar_pipeline.models.patent import (
    LegalStatus,
    has_trusted_legal_status_provenance,
    trusted_legal_status_conflict,
)
from praviar_pipeline.models.report import DecisionEvidenceCategory, DecisionEvidenceReference
from praviar_pipeline.pipeline.runtime.decisioning_metrics import derive_jurisdiction

__all__ = [
    "DecisionReferenceBuilder",
    "add_blocking_patent_references",
    "add_clearance_support_references",
    "add_future_risk_references",
    "add_legal_status_references",
    "add_prosecution_finding_references",
    "add_record_coverage_references",
    "build_decisive_references",
    "inactive_ep_register_status",
    "normalized_legal_status",
    "primary_reference_source",
]

_REFERENCE_SOURCE_PRIORITY = (
    "uspto_odp",
    "patent_term_info",
    "ptab_proceedings",
    "uspto_transactions",
    "application_number",
    "family_members",
    "examiner_metadata",
    "attorney_metadata",
)


def primary_reference_source(record_basis: list[str] | None) -> str:
    basis = list(record_basis or [])
    if not basis:
        return ""
    for candidate in _REFERENCE_SOURCE_PRIORITY:
        if candidate in basis:
            return candidate
    return basis[0]


def normalized_legal_status(detail) -> str:
    status = getattr(detail, "legal_status", None)
    if isinstance(status, LegalStatus):
        return status.value
    return str(getattr(status, "value", status) or "").lower()


def inactive_ep_register_status(detail) -> str:
    status = str(getattr(detail, "ep_register_status", "") or "").strip()
    lowered = status.lower()
    if any(token in lowered for token in ("revok", "withdraw", "lapse", "refus")):
        return status
    return ""


class DecisionReferenceBuilder:
    """Collect decisive references with stable dedupe and jurisdiction lookup."""

    def __init__(self, *, detail_map: dict[str, object]) -> None:
        self._detail_map = detail_map
        self.references: list[DecisionEvidenceReference] = []
        self._seen: set[tuple[str, str, str, str, str, str]] = set()

    def add(
        self,
        *,
        category: DecisionEvidenceCategory,
        summary: str,
        patent_id: str = "",
        jurisdiction: str = "",
        source_name: str = "",
        signal: str = "",
    ) -> None:
        key = (category.value, patent_id, jurisdiction, source_name, signal, summary)
        if key in self._seen:
            return
        self.references.append(
            DecisionEvidenceReference(
                category=category,
                summary=summary,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                source_name=source_name,
                signal=signal,
            )
        )
        self._seen.add(key)

    def jurisdiction_for_patent(self, patent_id: str) -> str:
        detail = self._detail_map.get(patent_id)
        if hasattr(detail, "model_dump"):
            detail_json = detail.model_dump(mode="json")
        elif isinstance(detail, dict):
            detail_json = detail
        elif detail is not None:
            detail_json = getattr(detail, "__dict__", None)
        else:
            detail_json = None
        return derive_jurisdiction(patent_id, detail_json)


def add_record_coverage_references(
    *,
    builder: DecisionReferenceBuilder,
    coverage_summary,
) -> None:
    if not coverage_summary.reviewed_patent_ids:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            summary="No material patents were reviewed in the final matter record.",
            signal="no_material_patents",
        )
    if not coverage_summary.queried_source_names:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            summary="No search sources were recorded for the final matter.",
            signal="no_search_sources",
        )
    elif not coverage_summary.successful_source_names:
        builder.add(
            category=DecisionEvidenceCategory.SOURCE_FAILURE,
            summary=(
                "No search source succeeded, so the matter cannot be cleared on the "
                "available record."
            ),
            signal="no_successful_sources",
        )

    for source_name in coverage_summary.failed_source_names[:2]:
        builder.add(
            category=DecisionEvidenceCategory.SOURCE_FAILURE,
            source_name=source_name,
            signal="failed",
            summary=f"Authoritative source collection failed for {source_name}.",
        )
    for patent_id in coverage_summary.patents_missing_claims[:2]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal="missing_claims",
            summary="Analyzed patent reached the final matter record without full claims text.",
        )
    for patent_id in coverage_summary.patents_missing_claim_level_analysis[:2]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal="missing_claim_level_analysis",
            summary="Analyzed patent lacks claim-level analysis in the final matter record.",
        )
    for patent_id in coverage_summary.patents_missing_authoritative_records[:2]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal="missing_authoritative_record_support",
            summary="Analyzed patent lacks authoritative record support beyond discovery search.",
        )
    for patent_id in coverage_summary.patents_missing_family_context[:2]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal="missing_family_context",
            summary="Analyzed patent lacks complete family context in the final matter record.",
        )
    for patent_id in coverage_summary.us_patents_missing_prosecution_context[:1]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction="US",
            signal="missing_prosecution_context",
            summary="Analyzed US patent lacks full prosecution/file-wrapper context.",
        )
    for patent_id in coverage_summary.us_patents_missing_file_wrapper_dossier[:1]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction="US",
            signal="missing_file_wrapper_dossier",
            summary="Analyzed US patent lacks dossier-grade file-wrapper coverage.",
        )
    for patent_id in coverage_summary.ep_patents_missing_register_context[:1]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction="EP",
            signal="missing_register_context",
            summary="Analyzed EP patent lacks complete register/opposition context.",
        )
    for patent_id in coverage_summary.failed_analysis_patent_ids[:2]:
        builder.add(
            category=DecisionEvidenceCategory.COVERAGE_GAP,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal="analysis_failure",
            summary="Patent analysis failed before the matter decision was finalized.",
        )
    for gap in coverage_summary.verification_gaps[:2]:
        builder.add(
            category=DecisionEvidenceCategory.VERIFICATION_GAP,
            signal="verification_gap",
            summary=gap,
        )


def add_prosecution_finding_references(
    *,
    builder: DecisionReferenceBuilder,
    prosecution_findings: list,
) -> None:
    for finding in prosecution_findings[:3]:
        signal_parts = []
        if finding.narrowing_signal:
            signal_parts.append("narrowing_signal")
        if finding.terminal_disclaimer:
            signal_parts.append("terminal_disclaimer")
        if finding.pending_family_signal:
            signal_parts.append("pending_family_signal")
        if finding.ptab_challenged:
            signal_parts.append("ptab_challenged")
        signal_parts.extend(list(getattr(finding, "estoppel_risk_flags", []) or []))
        if not signal_parts:
            continue
        builder.add(
            category=DecisionEvidenceCategory.PROSECUTION_SIGNAL,
            patent_id=finding.patent_id,
            jurisdiction=finding.jurisdiction,
            source_name=primary_reference_source(getattr(finding, "record_basis", [])),
            signal=",".join(signal_parts),
            summary=finding.summary,
        )


def add_future_risk_references(
    *,
    builder: DecisionReferenceBuilder,
    future_risk: list,
) -> None:
    for finding in future_risk[:2]:
        builder.add(
            category=DecisionEvidenceCategory.FUTURE_RISK,
            patent_id=finding.patent_id,
            jurisdiction=finding.jurisdiction,
            source_name=primary_reference_source(getattr(finding, "record_basis", [])),
            signal=finding.risk_type,
            summary=finding.summary,
        )


def add_blocking_patent_references(
    *,
    builder: DecisionReferenceBuilder,
    analyses_by_id: dict[str, object],
    detail_map: dict[str, object],
    blocking_patent_ids: list[str],
) -> None:
    for patent_id in blocking_patent_ids:
        analysis = analyses_by_id.get(patent_id)
        detail = detail_map.get(patent_id)
        jurisdiction = builder.jurisdiction_for_patent(patent_id)
        builder.add(
            category=DecisionEvidenceCategory.BLOCKING_PATENT,
            patent_id=patent_id,
            jurisdiction=jurisdiction,
            signal=getattr(getattr(analysis, "risk_level", None), "value", "blocking"),
            summary=getattr(analysis, "risk_summary", "")
            or "Material blocking exposure remained in the final decision layer.",
        )
        status_conflict = trusted_legal_status_conflict(detail)
        if status_conflict:
            statuses = ", ".join(status.value for status in status_conflict)
            builder.add(
                category=DecisionEvidenceCategory.COVERAGE_GAP,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                signal="authoritative_legal_status_source_conflict",
                summary=(
                    "Decision evidence conflicts with authoritative legal status "
                    "observations: "
                    f"{statuses}."
                ),
            )
        legal_status = normalized_legal_status(detail)
        if has_trusted_legal_status_provenance(detail) and legal_status in {
            LegalStatus.EXPIRED.value,
            LegalStatus.LAPSED.value,
            LegalStatus.REVOKED.value,
        }:
            builder.add(
                category=DecisionEvidenceCategory.COVERAGE_GAP,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                signal="authoritative_legal_status_conflict",
                summary=(
                    f"Blocking analysis conflicts with authoritative legal status {legal_status}."
                ),
            )
        inactive_ep_status = inactive_ep_register_status(detail)
        if inactive_ep_status and has_trusted_legal_status_provenance(
            detail,
            collector_identity="search.enrichment.epo_register",
        ):
            builder.add(
                category=DecisionEvidenceCategory.COVERAGE_GAP,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                source_name="epo_register",
                signal="ep_register_status_conflict",
                summary=(
                    f"Blocking analysis conflicts with EP register status {inactive_ep_status}."
                ),
            )


def add_legal_status_references(
    *,
    builder: DecisionReferenceBuilder,
    detail_map: dict[str, object],
) -> None:
    """Retain decisive trusted status evidence independently of blocker labels."""
    for patent_id, detail in detail_map.items():
        jurisdiction = builder.jurisdiction_for_patent(patent_id)
        status_conflict = trusted_legal_status_conflict(detail)
        if status_conflict:
            statuses = ", ".join(status.value for status in status_conflict)
            builder.add(
                category=DecisionEvidenceCategory.COVERAGE_GAP,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                signal="authoritative_legal_status_source_conflict",
                summary=(
                    "Decision evidence conflicts with authoritative legal status "
                    f"observations: {statuses}."
                ),
            )
            continue
        legal_status = normalized_legal_status(detail)
        if has_trusted_legal_status_provenance(detail) and legal_status in {
            LegalStatus.EXPIRED.value,
            LegalStatus.LAPSED.value,
            LegalStatus.REVOKED.value,
        }:
            provenance = getattr(detail, "legal_status_provenance", None)
            builder.add(
                category=DecisionEvidenceCategory.CLEARANCE_SUPPORT,
                patent_id=patent_id,
                jurisdiction=jurisdiction,
                source_name=str(getattr(provenance, "collector_identity", "") or ""),
                signal=f"trusted_inactive_status:{legal_status}",
                summary=(
                    f"Trusted current legal-status evidence records {patent_id} as "
                    f"{legal_status}; claim coverage is retained separately from "
                    "prospective enforceability."
                ),
            )


def add_clearance_support_references(
    *,
    builder: DecisionReferenceBuilder,
    decision,
    coverage_summary,
    analyses_by_id: dict[str, object],
) -> None:
    if decision.value != "clear":
        return
    reviewed_for_support = (
        coverage_summary.reviewed_us_patent_ids[:2] + coverage_summary.reviewed_ep_patent_ids[:2]
    )
    for patent_id in reviewed_for_support[:3]:
        analysis = analyses_by_id.get(patent_id)
        builder.add(
            category=DecisionEvidenceCategory.CLEARANCE_SUPPORT,
            patent_id=patent_id,
            jurisdiction=builder.jurisdiction_for_patent(patent_id),
            signal=getattr(getattr(analysis, "risk_level", None), "value", "clear"),
            summary=getattr(analysis, "risk_summary", "")
            or (
                "Reviewed material patent did not retain blocking exposure in the "
                "final decision layer."
            ),
        )


def build_decisive_references(
    *,
    decision,
    analyses_by_id: dict[str, object],
    detail_map: dict[str, object],
    coverage_summary,
    blocking_patent_ids: list[str],
    prosecution_findings: list,
    future_risk: list,
) -> list:
    builder = DecisionReferenceBuilder(detail_map=detail_map)
    add_record_coverage_references(builder=builder, coverage_summary=coverage_summary)
    add_legal_status_references(builder=builder, detail_map=detail_map)
    add_blocking_patent_references(
        builder=builder,
        analyses_by_id=analyses_by_id,
        detail_map=detail_map,
        blocking_patent_ids=blocking_patent_ids,
    )
    add_clearance_support_references(
        builder=builder,
        decision=decision,
        coverage_summary=coverage_summary,
        analyses_by_id=analyses_by_id,
    )
    add_prosecution_finding_references(
        builder=builder,
        prosecution_findings=prosecution_findings,
    )
    add_future_risk_references(
        builder=builder,
        future_risk=future_risk,
    )
    return builder.references
