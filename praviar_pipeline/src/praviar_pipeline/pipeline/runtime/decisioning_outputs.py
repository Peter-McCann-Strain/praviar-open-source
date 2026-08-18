"""Output builders for top-line clearance decisioning.

This module consolidates the deterministic output builders for top-line
clearance decisioning: jurisdiction decisions, claim-construction and
commercial-exposure records, claim-program summaries, the decision audit
record, run-level observability, the evidence-collection plan, the evidence
substrate, the final payload assembly and the top-level assembly entry
point.
"""

from __future__ import annotations

from dataclasses import dataclass

from praviar_pipeline.certification_policy import (
    certify_runtime_adapter,
    runtime_adapter_allowed_jurisdictions,
)
from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report import (
    ClaimConstructionRecord,
    ClaimProgramSummary,
    ClearanceDecision,
    ClearanceDecisionAudit,
    ClearanceOutcome,
    CommercialExposure,
    EvidenceCollectionDirective,
    EvidenceDirectivePriority,
    JurisdictionDecision,
    MatterGraph,
    MatterGraphSummary,
    RecordComponentStatusValue,
    RunObservability,
)
from praviar_pipeline.pipeline.report.blocker_family_records import (
    build_blocker_family_records,
)
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.runtime.decisioning_metrics import coverage_ratio
from praviar_pipeline.pipeline.runtime.evidence_runtime import (
    build_authority_coverage,
    build_coverage_gaps,
    build_evidence_collector_runs,
)
from praviar_pipeline.pipeline.runtime.matter_store import (
    build_matter_store,
    build_record_contradictions,
)
from praviar_pipeline.utils.patent_family import pending_family_member_ids
from praviar_pipeline.utils.patent_ids import canonical_publication_id


def _has_pending_family(detail) -> bool:
    family = getattr(detail, "family", None)
    return bool(pending_family_member_ids(list(getattr(family, "members", []) or [])))


def _has_authoritative_conflict(gate_failures: list[str]) -> bool:
    lowered = [failure.lower() for failure in gate_failures]
    return any(
        "conflicts with authoritative legal status" in failure
        or "conflicts with ep register status" in failure
        for failure in lowered
    )


def build_jurisdiction_decisions(
    *,
    jurisdiction_patents: dict[str, list[str]],
    blocking_by_jurisdiction: dict[str, list[str]],
    evidence_quality: float,
    decision_confidence: float,
    gate_failures_by_jurisdiction: dict[str, list[str]],
    claim_program_summary=None,
    claim_program_decisions: list | None = None,
) -> list[JurisdictionDecision]:
    decisions: list[JurisdictionDecision] = []

    for jurisdiction in ("US", "EP"):
        reviewed_ids = jurisdiction_patents.get(jurisdiction, [])
        jurisdiction_claim_program_summary = (
            build_claim_program_summary(
                [
                    claim_program_decision
                    for claim_program_decision in claim_program_decisions
                    if claim_program_decision.jurisdiction == jurisdiction
                ]
            )
            if claim_program_decisions is not None
            else claim_program_summary
        )
        claim_blocking_ids = [
            patent_id
            for patent_id in getattr(jurisdiction_claim_program_summary, "blocking_patent_ids", [])
            if patent_id.upper().startswith(jurisdiction)
        ]
        fallback_blocking_ids = (
            blocking_by_jurisdiction.get(jurisdiction, [])
            if not (
                getattr(jurisdiction_claim_program_summary, "total_claim_programs_reviewed", 0)
                or getattr(jurisdiction_claim_program_summary, "patent_level_fallback_count", 0)
            )
            else []
        )
        blocking_ids = claim_blocking_ids or fallback_blocking_ids
        contested_ids = [
            patent_id
            for patent_id in getattr(jurisdiction_claim_program_summary, "contested_patent_ids", [])
            if patent_id.upper().startswith(jurisdiction)
        ]
        medium_risk_ids = [
            patent_id
            for patent_id in getattr(
                jurisdiction_claim_program_summary, "medium_risk_patent_ids", []
            )
            if patent_id.upper().startswith(jurisdiction)
        ]
        insufficient_claim_ids = [
            claim_id
            for claim_id in getattr(
                jurisdiction_claim_program_summary,
                "claims_with_insufficient_evidence",
                [],
            )
            if claim_id.upper().startswith(jurisdiction)
        ]
        gate_failures = gate_failures_by_jurisdiction.get(jurisdiction, [])
        evidence_sufficient_for_clearance = bool(
            reviewed_ids and not gate_failures and not insufficient_claim_ids
        )

        if blocking_ids and not _has_authoritative_conflict(gate_failures):
            outcome = ClearanceOutcome.BLOCKED
        elif (
            reviewed_ids
            and evidence_quality >= 0.75
            and evidence_sufficient_for_clearance
            and not contested_ids
            and not medium_risk_ids
            and not insufficient_claim_ids
        ):
            outcome = ClearanceOutcome.CLEAR
        else:
            outcome = ClearanceOutcome.UNCLEAR

        reasoning: list[str] = []
        if reviewed_ids:
            reasoning.append(f"Reviewed {len(reviewed_ids)} material {jurisdiction} patent(s).")
        else:
            reasoning.append(f"No analyzed patents were mapped directly to {jurisdiction}.")

        if blocking_ids:
            if _has_authoritative_conflict(gate_failures):
                reasoning.append(
                    f"Potential blocking exposure in {jurisdiction} could not be confirmed "
                    "because authoritative status records conflict with the analysis."
                )
            else:
                reasoning.append(
                    f"Blocking exposure remains in {jurisdiction}: {', '.join(blocking_ids[:5])}."
                )
        elif outcome == ClearanceOutcome.CLEAR:
            reasoning.append(f"No blocking {jurisdiction} patents remained after analysis.")
        elif contested_ids:
            reasoning.append(
                f"High-risk {jurisdiction} claim programs remain contested by strong "
                "invalidity positions: "
                f"{', '.join(contested_ids[:5])}."
            )
        elif medium_risk_ids:
            reasoning.append(
                f"Some reviewed {jurisdiction} claim programs still carry medium infringement risk."
            )
        elif gate_failures:
            reasoning.append(gate_failures[0])
        else:
            reasoning.append(f"{jurisdiction} evidence remains incomplete or non-clearance-grade.")

        decisions.append(
            JurisdictionDecision(
                jurisdiction=jurisdiction,
                decision=outcome,
                decision_confidence=(
                    decision_confidence
                    if reviewed_ids and evidence_sufficient_for_clearance
                    else max(0.2, decision_confidence - 0.2)
                ),
                evidence_quality=(
                    evidence_quality if reviewed_ids else max(0.0, evidence_quality - 0.25)
                ),
                evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
                gate_failures=gate_failures,
                reviewed_patent_ids=reviewed_ids,
                blocking_patent_ids=blocking_ids,
                reasoning=reasoning,
            )
        )

    return decisions


def build_claim_construction_record(
    jurisdiction_decisions: list[JurisdictionDecision],
) -> ClaimConstructionRecord:
    standards: list[str] = []
    jurisdictions = [
        decision.jurisdiction for decision in jurisdiction_decisions if decision.reviewed_patent_ids
    ]

    if "US" in jurisdictions:
        standards.append("Phillips claim construction for U.S. infringement-risk assessment")
    if "EP" in jurisdictions:
        standards.append("Article 69 EPC and Protocol-informed scope assessment for EP exposure")

    return ClaimConstructionRecord(
        standard=(
            " / ".join(standards)
            if standards
            else "Jurisdiction-specific claim construction not fully established"
        ),
        jurisdictions=jurisdictions,
        assumptions=[
            "Issued claim text was prioritized over generic abstract/title language.",
            "Clearance requires conservative treatment of incomplete evidence.",
        ],
        summary=(
            "The matter was assessed using conservative, jurisdiction-aware claim "
            "construction defaults. This record captures the baseline legal "
            "standard, not a term-by-term Markman-style construction."
        ),
    )


def build_commercial_exposure(
    *,
    report,
    detail_map: dict[str, object],
    blocking_patent_ids: list[str],
    insufficiency_reasons: list[str],
) -> CommercialExposure:
    orange_book_blocking = [
        analysis.patent_id
        for analysis in report.patent_analyses
        if analysis.patent_id in blocking_patent_ids
        and getattr(detail_map.get(analysis.patent_id), "orange_book_listed", False)
    ]
    orange_book_material = [
        analysis.patent_id
        for analysis in report.patent_analyses
        if getattr(detail_map.get(analysis.patent_id), "orange_book_listed", False)
    ]
    ptab_material = [
        analysis.patent_id
        for analysis in report.patent_analyses
        if getattr(detail_map.get(analysis.patent_id), "ptab_proceedings", None)
    ]
    pending_family_material = [
        analysis.patent_id
        for analysis in report.patent_analyses
        if _has_pending_family(detail_map.get(analysis.patent_id))
    ]

    if blocking_patent_ids:
        damages_injunction_risk = "elevated"
        business_severity = "high"
        rationale = ["Material blocking exposure remains even after invalidity and DoE review."]
        if orange_book_blocking:
            rationale.append(
                "An Orange Book listing is recorded, but listing alone does not establish "
                "ownership, claim practice, enforceability, damages, or injunction entitlement."
            )
        if ptab_material:
            rationale.append(
                "PTAB history exists on reviewed patents, so enforceability and remedy "
                "posture require counsel review."
            )
    elif insufficiency_reasons:
        if ptab_material or pending_family_material:
            damages_injunction_risk = "elevated"
            business_severity = "medium"
            rationale = [
                (
                    "Authoritative post-grant or pending-family signals remain unresolved "
                    "on a non-clearance-grade record."
                ),
                insufficiency_reasons[0],
            ]
        else:
            damages_injunction_risk = "uncertain"
            business_severity = "medium"
            rationale = [
                (
                    "The matter record is not clearance-grade, so launch-at-risk "
                    "consequences remain uncertain."
                ),
                insufficiency_reasons[0],
            ]
        if orange_book_material:
            rationale.append(
                "An Orange Book listing is recorded as regulatory context only; it does "
                "not independently elevate legal coverage or remedies severity."
            )
    elif report.risk_summary.overall_risk == RiskLevel.LOW:
        damages_injunction_risk = "moderate"
        business_severity = "medium"
        rationale = [
            (
                "Literal blocking exposure is limited, but low-risk matters still "
                "require monitoring and escalation review."
            ),
        ]
    else:
        damages_injunction_risk = "limited"
        business_severity = "low"
        rationale = [
            "No material blocking exposure remained in the final deterministic decision layer."
        ]

    return CommercialExposure(
        damages_injunction_risk=damages_injunction_risk,
        business_severity=business_severity,
        blocking_patent_ids=blocking_patent_ids,
        rationale=rationale,
        summary=" ".join(rationale),
    )


_HIGH_INVALIDITY_STRENGTHS = frozenset({"strong"})


def _claim_program_identity(decision) -> tuple[str, int]:
    patent_id = canonical_publication_id(str(getattr(decision, "patent_id", "") or ""))
    raw_claim_number = getattr(decision, "claim_number", None)
    if isinstance(raw_claim_number, bool) or not isinstance(raw_claim_number, int):
        raise ValueError("claim-program claim_number must be an integer")
    if raw_claim_number < 0:
        raise ValueError("claim-program claim_number cannot be negative")
    return patent_id, raw_claim_number


def _claim_program_id(identity: tuple[str, int]) -> str:
    patent_id, claim_number = identity
    return f"{patent_id}#claim{claim_number}" if claim_number > 0 else patent_id


def _claim_program_governed_fingerprint(decision) -> tuple[object, ...]:
    return (
        str(getattr(decision, "literal_risk", "") or "").lower(),
        str(getattr(decision, "doe_risk", "") or "").lower(),
        str(getattr(decision, "invalidity_strength", "") or "").lower(),
        str(getattr(decision, "prospective_enforceability", "unresolved") or "").lower(),
        bool(getattr(decision, "legal_status_provenance_verified", False)),
        bool(getattr(decision, "accused_acts_verified", False)),
        bool(getattr(decision, "past_acts_in_scope", False)),
        tuple(sorted(str(item) for item in (getattr(decision, "future_risk_flags", []) or []))),
        getattr(decision, "evidence_sufficient", None),
        tuple(sorted(str(item) for item in (getattr(decision, "missing_components", []) or []))),
    )


def _has_high_claim_risk(decision) -> bool:
    return (
        getattr(decision, "literal_risk", "") == "high"
        or getattr(decision, "doe_risk", "") == "high"
    )


def _has_medium_claim_risk(decision) -> bool:
    return (
        getattr(decision, "literal_risk", "") == "medium"
        or getattr(decision, "doe_risk", "") == "medium"
    )


def _has_strong_invalidity(decision) -> bool:
    return getattr(decision, "invalidity_strength", "") in _HIGH_INVALIDITY_STRENGTHS


def _blocking_evidence_complete(decision) -> bool:
    return bool(
        getattr(decision, "evidence_sufficient", False)
        and getattr(decision, "legal_status_provenance_verified", False)
        and getattr(decision, "prospective_enforceability", "") == "active"
        and getattr(decision, "accused_acts_verified", False)
    )


def _inactive_coverage_resolves_prospective_exposure(decision) -> bool:
    return bool(
        getattr(decision, "evidence_sufficient", False)
        and getattr(decision, "legal_status_provenance_verified", False)
        and getattr(decision, "prospective_enforceability", "") == "inactive"
        and getattr(decision, "accused_acts_verified", False)
        and not getattr(decision, "past_acts_in_scope", False)
        and not (getattr(decision, "future_risk_flags", []) or [])
    )


def build_claim_program_summary(claim_program_decisions: list) -> ClaimProgramSummary:
    """Summarize claim-program decisions for conservative top-line decisioning."""
    blocking_claim_ids: list[str] = []
    contested_claim_ids: list[str] = []
    medium_risk_claim_ids: list[str] = []
    claims_with_strong_invalidity: list[str] = []
    claims_with_insufficient_evidence: list[str] = []
    inactive_coverage_claim_ids: list[str] = []
    blocking_patent_ids: list[str] = []
    contested_patent_ids: list[str] = []
    medium_risk_patent_ids: list[str] = []
    patent_level_fallback_count = 0
    seen_programs: dict[tuple[str, int], tuple[object, ...]] = {}
    positive_claim_patent_ids: set[str] = set()
    fallback_patent_ids: set[str] = set()

    for decision in claim_program_decisions:
        program_identity = _claim_program_identity(decision)
        fingerprint = _claim_program_governed_fingerprint(decision)
        if program_identity in seen_programs:
            if seen_programs[program_identity] != fingerprint:
                raise ValueError("contradictory duplicate claim-program decision")
            continue
        seen_programs[program_identity] = fingerprint
        patent_id, claim_number = program_identity
        if claim_number == 0:
            if patent_id in positive_claim_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            fallback_patent_ids.add(patent_id)
        else:
            if patent_id in fallback_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            positive_claim_patent_ids.add(patent_id)
        claim_id = _claim_program_id(program_identity)
        is_patent_level_fallback = claim_number == 0
        patent_level_fallback_count = len(fallback_patent_ids)

        has_strong_invalidity = _has_strong_invalidity(decision)
        if has_strong_invalidity:
            claims_with_strong_invalidity.append(claim_id)

        if not getattr(decision, "evidence_sufficient", False):
            claims_with_insufficient_evidence.append(claim_id)

        if _has_high_claim_risk(decision):
            if _blocking_evidence_complete(decision) and has_strong_invalidity:
                contested_claim_ids.append(claim_id)
                contested_patent_ids.append(patent_id)
            elif _blocking_evidence_complete(decision):
                blocking_claim_ids.append(claim_id)
                blocking_patent_ids.append(patent_id)
            elif _inactive_coverage_resolves_prospective_exposure(decision):
                inactive_coverage_claim_ids.append(claim_id)
            elif getattr(decision, "prospective_enforceability", "") == "pending" or getattr(
                decision, "future_risk_flags", []
            ):
                medium_risk_claim_ids.append(claim_id)
                medium_risk_patent_ids.append(patent_id)
            elif claim_id not in claims_with_insufficient_evidence:
                claims_with_insufficient_evidence.append(claim_id)
            continue

        if _has_medium_claim_risk(decision):
            medium_risk_claim_ids.append(claim_id)
            medium_risk_patent_ids.append(patent_id)
            continue

        if is_patent_level_fallback:
            fallback_risk = getattr(decision, "literal_risk", "")
            if fallback_risk == "high":
                if has_strong_invalidity:
                    contested_claim_ids.append(claim_id)
                    contested_patent_ids.append(patent_id)
                else:
                    blocking_claim_ids.append(claim_id)
                    blocking_patent_ids.append(patent_id)
            elif fallback_risk == "medium":
                medium_risk_claim_ids.append(claim_id)
                medium_risk_patent_ids.append(patent_id)

    ordered_blocking_patents = unique_strings(blocking_patent_ids)
    blocking_patent_set = set(ordered_blocking_patents)
    ordered_contested_patents = [
        patent_id
        for patent_id in unique_strings(contested_patent_ids)
        if patent_id not in blocking_patent_set
    ]
    contested_patent_set = set(ordered_contested_patents)
    ordered_medium_patents = [
        patent_id
        for patent_id in unique_strings(medium_risk_patent_ids)
        if patent_id not in blocking_patent_set and patent_id not in contested_patent_set
    ]
    return ClaimProgramSummary(
        total_claim_programs_reviewed=sum(
            1 for _patent_id, claim_number in seen_programs if claim_number > 0
        ),
        patent_level_fallback_count=patent_level_fallback_count,
        blocking_claim_ids=unique_strings(blocking_claim_ids),
        contested_claim_ids=unique_strings(contested_claim_ids),
        medium_risk_claim_ids=unique_strings(medium_risk_claim_ids),
        claims_with_strong_invalidity=unique_strings(claims_with_strong_invalidity),
        claims_with_insufficient_evidence=unique_strings(claims_with_insufficient_evidence),
        inactive_coverage_claim_ids=unique_strings(inactive_coverage_claim_ids),
        blocking_patent_ids=ordered_blocking_patents,
        contested_patent_ids=ordered_contested_patents,
        medium_risk_patent_ids=ordered_medium_patents,
    )


def _status_value(component_status) -> str:
    return getattr(
        getattr(component_status, "status", None),
        "value",
        str(getattr(component_status, "status", "") or ""),
    )


def _patent_ids_with_component_status(
    patent_records,
    *,
    component: str,
    statuses: set[str],
) -> list[str]:
    patent_ids: list[str] = []
    for record in patent_records:
        component_status = next(
            (
                status
                for status in getattr(record, "component_statuses", []) or []
                if getattr(status, "component", "") == component
            ),
            None,
        )
        if component_status is None:
            continue
        if _status_value(component_status) in statuses:
            patent_ids.append(record.patent_id)
    return patent_ids


def populate_coverage_summary_from_index(
    *,
    coverage_context,
    matter_evidence_index,
    required_record_components: list[str],
) -> None:
    """Project matter-evidence index coverage into the mutable coverage summary."""
    coverage_context.coverage_summary.authoritative_source_names = (
        matter_evidence_index.authoritative_source_names
    )
    coverage_context.coverage_summary.supporting_source_names = (
        matter_evidence_index.supporting_source_names
    )
    missing_statuses = {
        RecordComponentStatusValue.MISSING.value,
        RecordComponentStatusValue.FAILED.value,
    }
    coverage_context.coverage_summary.patents_missing_claims = _patent_ids_with_component_status(
        matter_evidence_index.patent_records,
        component="claims_text",
        statuses=missing_statuses,
    )
    coverage_context.coverage_summary.patents_missing_family_context = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="family_context",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.patents_missing_claim_level_analysis = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="claim_level_analysis",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.patents_missing_authoritative_records = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="authoritative_records",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.us_patents_missing_prosecution_context = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="us_prosecution_context",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.us_patents_missing_file_wrapper_dossier = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="us_file_wrapper_dossier",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.ep_patents_missing_register_context = (
        _patent_ids_with_component_status(
            matter_evidence_index.patent_records,
            component="ep_register_context",
            statuses=missing_statuses,
        )
    )
    coverage_context.coverage_summary.clearance_grade_ready_patent_ids = (
        matter_evidence_index.clearance_grade_ready_patent_ids
    )
    coverage_context.coverage_summary.incomplete_patent_ids = (
        matter_evidence_index.incomplete_patent_ids
    )
    coverage_context.coverage_summary.clearance_grade_ready_family_ids = (
        matter_evidence_index.clearance_grade_ready_family_ids
    )
    coverage_context.coverage_summary.incomplete_family_ids = (
        matter_evidence_index.incomplete_family_ids
    )
    coverage_context.required_record_components = required_record_components
    coverage_context.coverage_summary.required_record_components = required_record_components


def determine_clearance_decision(
    *,
    overall_risk,
    evidence_quality: float,
    evidence_sufficient_for_clearance: bool,
    warnings: list[str],
    claim_program_summary,
    blocking_patent_ids: list[str],
    authoritative_record_contradictions: list[str],
):
    """Determine the top-line deterministic clearance outcome."""
    if blocking_patent_ids and not authoritative_record_contradictions:
        return ClearanceOutcome.BLOCKED
    inactive_coverage_resolved = bool(
        claim_program_summary.inactive_coverage_claim_ids
        and not claim_program_summary.blocking_claim_ids
        and not claim_program_summary.contested_claim_ids
        and not claim_program_summary.medium_risk_claim_ids
        and not claim_program_summary.claims_with_insufficient_evidence
    )
    if (
        (overall_risk == RiskLevel.CLEAR or inactive_coverage_resolved)
        and evidence_quality >= 0.75
        and evidence_sufficient_for_clearance
        and not warnings
        and not claim_program_summary.blocking_claim_ids
        and not claim_program_summary.contested_claim_ids
        and not claim_program_summary.medium_risk_claim_ids
        and not claim_program_summary.claims_with_insufficient_evidence
    ):
        return ClearanceOutcome.CLEAR
    return ClearanceOutcome.UNCLEAR


def determine_decision_confidence(
    *,
    decision,
    evidence_quality: float,
    evidence_sufficient_for_clearance: bool,
) -> float:
    """Score the confidence reported for the final deterministic decision."""
    if decision == ClearanceOutcome.BLOCKED:
        return min(0.98, round(evidence_quality + 0.10, 2))
    if decision == ClearanceOutcome.CLEAR:
        return min(0.90, round(evidence_quality, 2))
    if not evidence_sufficient_for_clearance:
        return max(0.25, min(0.45, round(evidence_quality, 2)))
    return max(0.25, round(evidence_quality - 0.05, 2))


def build_decision_audit_record(
    *,
    coverage_context,
    matter_evidence_index,
    report,
    evidence_sufficient_for_clearance: bool,
    insufficiency_reasons: list[str],
    warnings: list[str],
    claim_program_summary,
    blocker_families,
    decisive_references,
) -> ClearanceDecisionAudit:
    """Build the structured audit record attached to the top-line decision."""
    return ClearanceDecisionAudit(
        queried_sources_count=coverage_context.queried_sources,
        successful_sources_count=coverage_context.ok_sources,
        material_patents_reviewed=coverage_context.material_patent_count,
        material_us_patents=coverage_context.us_patents,
        material_ep_patents=coverage_context.ep_patents,
        patents_with_claims=coverage_context.patents_with_claims,
        patents_with_family=coverage_context.patents_with_family,
        us_patents_with_prosecution_context=coverage_context.us_patents_with_prosecution_context,
        us_patents_with_file_wrapper_dossier=(
            coverage_context.us_patents_with_file_wrapper_dossier
        ),
        ep_patents_with_register_context=coverage_context.ep_patents_with_register_context,
        analysis_failures_count=len(report.analysis_failures),
        authoritative_sources_count=len(matter_evidence_index.authoritative_source_names),
        clearance_grade_ready_patents=len(matter_evidence_index.clearance_grade_ready_patent_ids),
        incomplete_material_patents=len(matter_evidence_index.incomplete_patent_ids),
        clearance_grade_ready_families=len(matter_evidence_index.clearance_grade_ready_family_ids),
        incomplete_material_families=len(matter_evidence_index.incomplete_family_ids),
        failed_sources=report.source_health.failed_sources,
        evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
        insufficiency_reasons=insufficiency_reasons,
        evidence_warnings=warnings,
        search_iterations=(
            report.search_loop_result.iterations_completed if report.search_loop_result else 0
        ),
        coverage_summary=coverage_context.coverage_summary,
        claim_program_summary=claim_program_summary,
        blocker_families=blocker_families,
        decisive_references=decisive_references,
    )


def build_run_observability(
    *,
    coverage_context,
    report,
    claim_program_summary,
    record_completeness,
    evidence_adapter_results,
) -> RunObservability:
    """Build run-level observability metrics and false-clear risk flags."""
    material_patents = coverage_context.material_patent_count
    authoritative_hit_rate = coverage_ratio(
        len(coverage_context.coverage_summary.reviewed_patent_ids)
        - len(coverage_context.coverage_summary.patents_missing_authoritative_records),
        material_patents,
    )
    claims_text_coverage = coverage_ratio(
        coverage_context.patents_with_claims,
        material_patents,
    )
    family_context_coverage = coverage_ratio(
        coverage_context.patents_with_family,
        material_patents,
    )
    us_file_wrapper_dossier_coverage = coverage_ratio(
        coverage_context.us_patents_with_file_wrapper_dossier,
        coverage_context.us_patents,
    )
    ep_register_coverage = coverage_ratio(
        coverage_context.ep_patents_with_register_context,
        coverage_context.ep_patents,
    )

    failed_adapter_names = [
        result.adapter_name
        for result in evidence_adapter_results
        if getattr(result.status, "value", result.status) == "failed"
    ]

    false_clear_risk_flags: list[str] = []
    if material_patents == 0:
        false_clear_risk_flags.append("no_material_patents_reviewed")
    if coverage_context.coverage_summary.patents_missing_claims:
        false_clear_risk_flags.append("claims_text_missing")
    if coverage_context.coverage_summary.patents_missing_claim_level_analysis:
        false_clear_risk_flags.append("claim_level_analysis_missing")
    if coverage_context.coverage_summary.patents_missing_authoritative_records:
        false_clear_risk_flags.append("authoritative_records_missing")
    if coverage_context.coverage_summary.verification_gaps:
        false_clear_risk_flags.append("verification_failed")
    if getattr(claim_program_summary, "contested_claim_ids", []):
        false_clear_risk_flags.append("contested_high_risk_claims")
    if getattr(claim_program_summary, "medium_risk_claim_ids", []):
        false_clear_risk_flags.append("medium_risk_claims")
    if report.analysis_failures:
        false_clear_risk_flags.append("analysis_failures_present")
    if any(
        result.supports_authoritative_findings
        and getattr(result.status, "value", result.status) == "failed"
        for result in evidence_adapter_results
    ):
        false_clear_risk_flags.append("failed_authoritative_sources")
    if record_completeness.blocking_gaps:
        false_clear_risk_flags.append("record_incomplete")
    if any(
        getattr(limitation, "category", "") == "runtime_budget_exceeded"
        for limitation in report.data_limitations
    ):
        false_clear_risk_flags.append("runtime_budget_exceeded")
    if getattr(getattr(report, "search_loop_result", None), "termination_reason", "") in {
        "record_collection_required",
        "max_iterations_reached",
        "coverage_assessment_failed",
    }:
        false_clear_risk_flags.append("search_loop_incomplete")
    if getattr(report, "critic_report", None) and getattr(report.critic_report, "findings", []):
        false_clear_risk_flags.append("critic_findings_present")
    if getattr(coverage_context, "authoritative_record_contradictions", []):
        false_clear_risk_flags.append("contradictory_authoritative_records")

    unresolved_contradictions: list[str] = []
    if getattr(claim_program_summary, "contested_claim_ids", []):
        unresolved_contradictions.append(
            "High-risk claim programs remain contested by strong invalidity positions."
        )
    if getattr(claim_program_summary, "blocking_claim_ids", []) and getattr(
        claim_program_summary, "claims_with_strong_invalidity", []
    ):
        unresolved_contradictions.append(
            "Some claim programs remain blocking while others are contested by strong invalidity."
        )
    if report.analysis_failures and coverage_context.coverage_summary.reviewed_patent_ids:
        unresolved_contradictions.append(
            "Some reviewed patents failed downstream analysis while others completed."
        )
    if any(
        getattr(limitation, "category", "") == "runtime_budget_exceeded"
        for limitation in report.data_limitations
    ):
        unresolved_contradictions.append(
            "Run terminated before completion because the configured runtime budget expired."
        )
    if (
        getattr(getattr(report, "search_loop_result", None), "termination_reason", "")
        == "record_collection_required"
    ):
        unresolved_contradictions.append(
            "Search loop stopped while required evidence-collection directives were still open."
        )
    unresolved_contradictions.extend(
        list(getattr(coverage_context, "authoritative_record_contradictions", []) or [])
    )

    return RunObservability(
        authoritative_source_hit_rate=authoritative_hit_rate,
        claims_text_coverage=claims_text_coverage,
        family_context_coverage=family_context_coverage,
        us_file_wrapper_dossier_coverage=us_file_wrapper_dossier_coverage,
        ep_register_coverage=ep_register_coverage,
        failed_adapter_names=unique_strings(failed_adapter_names),
        false_clear_risk_flags=unique_strings(false_clear_risk_flags),
        unresolved_contradictions=unique_strings(unresolved_contradictions),
    )


def _jurisdictions_for_patents(target_patent_ids: list[str]) -> list[str]:
    return unique_strings(
        [patent_id[:2].upper() for patent_id in target_patent_ids if len(patent_id) >= 2]
    )


def _directive(
    *,
    directive_type: str,
    priority: EvidenceDirectivePriority,
    required_before_clear: bool,
    target_patent_ids: list[str],
    target_claim_ids: list[str],
    recommended_adapters: list[str],
    summary: str,
    rationale: str,
) -> EvidenceCollectionDirective:
    directive_key = ":".join(
        [
            directive_type,
            ",".join(unique_strings(target_patent_ids)),
            ",".join(unique_strings(target_claim_ids)),
        ]
    )
    return EvidenceCollectionDirective(
        directive_id=directive_key,
        directive_type=directive_type,
        priority=priority,
        required_before_clear=required_before_clear,
        target_patent_ids=unique_strings(target_patent_ids),
        target_claim_ids=unique_strings(target_claim_ids),
        target_jurisdictions=_jurisdictions_for_patents(target_patent_ids),
        recommended_adapters=unique_strings(recommended_adapters),
        summary=summary,
        rationale=rationale,
    )


def _certified_adapters(
    adapters: list[str],
    *,
    settings,
    target_patent_ids: list[str],
    require_jurisdiction_match: bool = False,
) -> list[str]:
    filtered: list[str] = []
    for adapter in adapters:
        result = certify_runtime_adapter(
            adapter,
            settings=settings,
            target_patent_ids=target_patent_ids,
        )
        if not result.allowed:
            continue
        if require_jurisdiction_match and not runtime_adapter_allowed_jurisdictions(adapter):
            continue
        filtered.append(adapter)
    return unique_strings(filtered)


def build_evidence_collection_plan(
    *,
    record_completeness,
    coverage_context,
    evidence_adapter_results,
    claim_program_summary,
    settings=None,
) -> list[EvidenceCollectionDirective]:
    """Build an actionable evidence-collection plan for unresolved matter gaps."""
    directives: list[EvidenceCollectionDirective] = []
    summary = coverage_context.coverage_summary
    missing = set(getattr(record_completeness, "missing_components", []) or [])

    if "claims_text" in missing:
        directives.append(
            _directive(
                directive_type="collect_claims_text",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=summary.patents_missing_claims,
                target_claim_ids=[],
                recommended_adapters=_certified_adapters(
                    ["patentsview", "bigquery", "epo_search"],
                    settings=settings,
                    target_patent_ids=summary.patents_missing_claims,
                ),
                summary=(
                    "Collect full claims text for every material patent lacking claims coverage."
                ),
                rationale=(
                    "Positive clearance cannot be supported while full claims text is missing."
                ),
            )
        )
    if "claim_level_analysis" in missing:
        directives.append(
            _directive(
                directive_type="complete_claim_analysis",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=summary.patents_missing_claim_level_analysis,
                target_claim_ids=[],
                recommended_adapters=["step4_analyze"],
                summary=(
                    "Complete claim-level analysis for material patents still missing "
                    "structured claim review."
                ),
                rationale=(
                    "The decision layer must be grounded in claim-program analysis, "
                    "not only patent summaries."
                ),
            )
        )
    if "authoritative_records" in missing:
        directives.append(
            _directive(
                directive_type="collect_authoritative_records",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=summary.patents_missing_authoritative_records,
                target_claim_ids=[],
                recommended_adapters=_certified_adapters(
                    [
                        "patentsview",
                        "epo_search",
                        "uspto_odp",
                        "epo_register",
                    ],
                    settings=settings,
                    target_patent_ids=summary.patents_missing_authoritative_records,
                    require_jurisdiction_match=True,
                ),
                summary=(
                    "Collect authoritative legal-record support for material patents "
                    "still backed only by discovery sources."
                ),
                rationale=(
                    "A clearance-grade record requires official or equivalent "
                    "authoritative support."
                ),
            )
        )
    if "family_context" in missing:
        directives.append(
            _directive(
                directive_type="expand_family_context",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=summary.patents_missing_family_context,
                target_claim_ids=[],
                recommended_adapters=["family_record", "epo_register"],
                summary=(
                    "Expand patent-family context for every material patent missing "
                    "family coverage."
                ),
                rationale="Family and continuation scope can materially change clearance posture.",
            )
        )
    if "us_prosecution_context" in missing:
        directives.append(
            _directive(
                directive_type="collect_us_prosecution_context",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=summary.us_patents_missing_prosecution_context,
                target_claim_ids=[],
                recommended_adapters=["uspto_odp"],
                summary=(
                    "Collect U.S. prosecution history for material patents missing "
                    "prosecution context."
                ),
                rationale=(
                    "Arguments, amendments, and disclaimer signals are required for a "
                    "clearance-grade U.S. record."
                ),
            )
        )
    if "us_file_wrapper_dossier" in missing:
        directives.append(
            _directive(
                directive_type="collect_us_file_wrapper_dossier",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=summary.us_patents_missing_file_wrapper_dossier,
                target_claim_ids=[],
                recommended_adapters=["uspto_odp"],
                summary=(
                    "Collect dossier-grade U.S. file-wrapper records for material "
                    "patents still missing them."
                ),
                rationale=(
                    "A positive U.S. clearance conclusion requires dossier-grade "
                    "prosecution coverage."
                ),
            )
        )
    if "ep_register_context" in missing:
        directives.append(
            _directive(
                directive_type="collect_ep_register_context",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=summary.ep_patents_missing_register_context,
                target_claim_ids=[],
                recommended_adapters=["epo_register"],
                summary=(
                    "Collect EPO register and opposition context for material EP patents "
                    "still missing register coverage."
                ),
                rationale=(
                    "A positive EP clearance conclusion requires register-grade status "
                    "and post-grant context."
                ),
            )
        )
    if "verification" in missing:
        directives.append(
            _directive(
                directive_type="rerun_verification",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=summary.reviewed_patent_ids,
                target_claim_ids=[],
                recommended_adapters=["step7_verification"],
                summary=(
                    "Resolve deterministic verification gaps before allowing a positive "
                    "clearance conclusion."
                ),
                rationale=(
                    "Verification failures must be resolved before the matter can be cleared."
                ),
            )
        )

    failed_authoritative_adapters = [
        result
        for result in evidence_adapter_results
        if result.status.value == "failed" and result.supports_authoritative_findings
    ]
    if failed_authoritative_adapters:
        failed_target_patent_ids = unique_strings(
            [
                patent_id
                for result in failed_authoritative_adapters
                for patent_id in (
                    result.missing_patent_ids
                    or result.target_patent_ids
                    or summary.reviewed_patent_ids
                )
            ]
        )
        directives.append(
            _directive(
                directive_type="retry_authoritative_adapters",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=failed_target_patent_ids,
                target_claim_ids=[],
                recommended_adapters=[
                    result.adapter_name for result in failed_authoritative_adapters
                ],
                summary=(
                    "Retry failed authoritative record adapters before treating the matter "
                    "as clearance-grade."
                ),
                rationale="Official-record collection failed on one or more decisive sources.",
            )
        )

    if claim_program_summary.contested_claim_ids:
        directives.append(
            _directive(
                directive_type="review_contested_claim_programs",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=claim_program_summary.contested_patent_ids,
                target_claim_ids=claim_program_summary.contested_claim_ids,
                recommended_adapters=["step6_invalidity", "step4_analyze"],
                summary=(
                    "Review high-risk claim programs that are currently contested by "
                    "strong invalidity positions."
                ),
                rationale=(
                    "These claims are not safely blocked, but they are also not clear "
                    "on the current record."
                ),
            )
        )

    if claim_program_summary.medium_risk_claim_ids:
        directives.append(
            _directive(
                directive_type="resolve_medium_risk_claim_programs",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=claim_program_summary.medium_risk_patent_ids,
                target_claim_ids=claim_program_summary.medium_risk_claim_ids,
                recommended_adapters=["step4_analyze", "step5_doe"],
                summary=(
                    "Resolve medium-risk claim programs before attempting a positive "
                    "clearance conclusion."
                ),
                rationale="Medium-risk claim programs keep the matter in an unclear posture.",
            )
        )

    deduped: dict[str, EvidenceCollectionDirective] = {}
    for directive in directives:
        deduped.setdefault(directive.directive_id, directive)
    return list(deduped.values())


@dataclass(slots=True)
class DecisioningEvidenceSubstrate:
    """Typed bundle of runtime evidence state reused across final outputs."""

    coverage_gaps: list
    authority_coverage: object
    evidence_artifacts: list
    evidence_adapter_results: list
    evidence_collection_plan: list
    collector_runs: list
    run_observability: object
    matter_store: object


def build_decisioning_evidence_substrate(
    *,
    report,
    coverage_context,
    matter_evidence_index,
    record_completeness,
    claim_program_summary,
    claim_program_decisions,
    settings,
    matter_graph,
    matter_graph_summary,
    build_coverage_gaps_fn,
    build_authority_coverage_fn,
    reuse_or_build_evidence_artifacts_fn,
    reuse_or_build_evidence_adapter_results_fn,
    build_evidence_collection_plan_fn,
    reuse_or_build_collector_runs_fn,
    build_run_observability_fn,
    reuse_or_build_matter_store_fn,
    build_evidence_artifacts,
    build_evidence_adapter_results,
) -> DecisioningEvidenceSubstrate:
    """Assemble the persistent evidence substrate for final decision outputs."""
    coverage_gaps = list(getattr(report, "coverage_gaps", []) or [])
    if not coverage_gaps:
        coverage_gaps = build_coverage_gaps_fn(
            report=report,
            coverage_context=coverage_context,
            record_completeness=record_completeness,
        )

    authority_coverage = build_authority_coverage_fn(
        matter_evidence_index=matter_evidence_index,
        record_completeness=record_completeness,
        settings=settings,
    )
    evidence_artifacts = reuse_or_build_evidence_artifacts_fn(
        report=report,
        matter_evidence_index=matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        coverage_gaps=coverage_gaps,
        build_evidence_artifacts=build_evidence_artifacts,
    )
    evidence_adapter_results = reuse_or_build_evidence_adapter_results_fn(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=evidence_artifacts,
        record_completeness=record_completeness,
        build_evidence_adapter_results=build_evidence_adapter_results,
    )
    evidence_collection_plan = build_evidence_collection_plan_fn(
        record_completeness=record_completeness,
        coverage_context=coverage_context,
        evidence_adapter_results=evidence_adapter_results,
        claim_program_summary=claim_program_summary,
        settings=settings,
    )
    collector_runs = reuse_or_build_collector_runs_fn(
        report=report,
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=evidence_collection_plan,
    )
    run_observability = build_run_observability_fn(
        coverage_context=coverage_context,
        report=report,
        claim_program_summary=claim_program_summary,
        record_completeness=record_completeness,
        evidence_adapter_results=evidence_adapter_results,
    )
    matter_store = reuse_or_build_matter_store_fn(
        report=report,
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_evidence_index=matter_evidence_index,
        claim_program_summary=claim_program_summary,
        claim_program_decisions=claim_program_decisions,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        evidence_collection_plan=evidence_collection_plan,
        coverage_gaps=coverage_gaps,
        authority_coverage=authority_coverage,
        record_completeness=record_completeness,
        run_observability=run_observability,
    )
    return DecisioningEvidenceSubstrate(
        coverage_gaps=coverage_gaps,
        authority_coverage=authority_coverage,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=evidence_collection_plan,
        collector_runs=collector_runs,
        run_observability=run_observability,
        matter_store=matter_store,
    )


def build_clearance_output_payload(
    *,
    report,
    patent_hits,
    coverage_context,
    claim_program_decisions,
    evidence_quality: float,
    insufficiency_reasons: list[str],
    decision,
    decision_confidence: float,
    decision_reasoning: list[str],
    decision_audit,
    decision_scope,
    supporting_scope,
    certification_scope,
    cohort_status,
    jurisdiction_decisions,
    evidence_substrate,
    record_completeness,
    blocking_patent_ids: list[str],
    matter_graph,
    matter_graph_summary,
    build_claim_construction_record_fn,
    build_commercial_exposure_fn,
) -> dict:
    """Build the stable public clearance-output payload."""
    return {
        "clearance_decision": ClearanceDecision(
            decision=decision,
            decision_confidence=decision_confidence,
            evidence_quality=evidence_quality,
            decision_reasoning=decision_reasoning,
            decision_audit=decision_audit,
        ),
        "decision_scope": decision_scope,
        "supporting_scope": supporting_scope,
        "certification_scope": certification_scope,
        "cohort_status": cohort_status,
        "jurisdiction_decisions": jurisdiction_decisions,
        "prosecution_findings": coverage_context.prosecution_findings,
        "claim_construction_record": build_claim_construction_record_fn(jurisdiction_decisions),
        "future_risk": coverage_context.future_risk,
        "claim_program_decisions": claim_program_decisions,
        "evidence_artifacts": evidence_substrate.evidence_artifacts,
        "evidence_adapter_results": evidence_substrate.evidence_adapter_results,
        "collector_runs": evidence_substrate.collector_runs,
        "evidence_collection_plan": evidence_substrate.evidence_collection_plan,
        "coverage_gaps": evidence_substrate.coverage_gaps,
        "matter_graph": matter_graph,
        "matter_graph_summary": matter_graph_summary,
        "matter_store": evidence_substrate.matter_store,
        "authority_coverage": evidence_substrate.authority_coverage,
        "record_completeness": record_completeness,
        "run_observability": evidence_substrate.run_observability,
        "commercial_exposure": build_commercial_exposure_fn(
            report=report,
            detail_map={
                getattr(hit, "patent_id", ""): hit
                for hit in patent_hits
                if getattr(hit, "patent_id", "")
            },
            blocking_patent_ids=blocking_patent_ids,
            insufficiency_reasons=insufficiency_reasons,
        ),
    }


def _reuse_or_build_matter_graph(
    *,
    report,
    matter_evidence_index,
    claim_program_decisions,
    patent_hits,
    analyses,
    build_matter_graph,
):
    existing_matter_graph = getattr(report, "matter_graph", None)
    if isinstance(existing_matter_graph, MatterGraph) and (
        existing_matter_graph.nodes or existing_matter_graph.edges
    ):
        return existing_matter_graph
    return build_matter_graph(
        report=report,
        matter_evidence_index=matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        patent_hits=patent_hits,
        analyses=analyses,
    )


def _reuse_or_build_matter_graph_summary(
    *,
    report,
    matter_graph,
    build_summarize_matter_graph,
):
    existing_matter_graph_summary = getattr(report, "matter_graph_summary", None)
    if isinstance(existing_matter_graph_summary, MatterGraphSummary) and (
        existing_matter_graph_summary.node_count or existing_matter_graph_summary.edge_count
    ):
        return existing_matter_graph_summary
    return build_summarize_matter_graph(
        matter_graph,
        compound_name=getattr(report.compound, "name", ""),
    )


def _reuse_or_build_evidence_artifacts(
    *,
    report,
    matter_evidence_index,
    claim_program_decisions,
    coverage_gaps,
    build_evidence_artifacts,
):
    existing_evidence_artifacts = list(getattr(report, "evidence_artifacts", []) or [])
    if existing_evidence_artifacts:
        return existing_evidence_artifacts
    return build_evidence_artifacts(
        report=report,
        matter_evidence_index=matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        coverage_gaps=coverage_gaps,
    )


def _reuse_or_build_evidence_adapter_results(
    *,
    report,
    matter_evidence_index,
    evidence_artifacts,
    record_completeness,
    build_evidence_adapter_results,
):
    existing_evidence_adapter_results = list(getattr(report, "evidence_adapter_results", []) or [])
    if existing_evidence_adapter_results:
        return existing_evidence_adapter_results
    return build_evidence_adapter_results(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=evidence_artifacts,
        record_completeness=record_completeness,
    )


def _reuse_or_build_collector_runs(
    *,
    report,
    evidence_adapter_results,
    evidence_collection_plan,
):
    existing_collector_runs = list(getattr(report, "collector_runs", []) or [])
    if existing_collector_runs:
        return existing_collector_runs
    return build_evidence_collector_runs(
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=evidence_collection_plan,
    )


def _reuse_or_build_matter_store(
    *,
    report,
    matter_graph,
    matter_graph_summary,
    matter_evidence_index,
    claim_program_summary,
    claim_program_decisions,
    evidence_artifacts,
    evidence_adapter_results,
    collector_runs,
    evidence_collection_plan,
    coverage_gaps,
    authority_coverage,
    record_completeness,
    run_observability,
):
    record_contradictions = build_record_contradictions(
        run_observability=run_observability,
        claim_program_summary=claim_program_summary,
        evidence_adapter_results=evidence_adapter_results,
    )
    return build_matter_store(
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_evidence_index=matter_evidence_index,
        prosecution_dossiers=getattr(report, "prosecution_dossiers", []),
        claim_program_decisions=claim_program_decisions,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        evidence_collection_plan=evidence_collection_plan,
        coverage_gaps=coverage_gaps,
        authority_coverage=authority_coverage,
        record_completeness=record_completeness,
        run_observability=run_observability,
        record_contradictions=record_contradictions,
    )


def assemble_clearance_outputs(
    *,
    report,
    patent_hits,
    matter_evidence_index,
    coverage_context,
    record_completeness,
    claim_program_decisions,
    claim_program_summary,
    evidence_quality: float,
    warnings: list[str],
    insufficiency_reasons: list[str],
    evidence_sufficient_for_clearance: bool,
    decision,
    decision_confidence: float,
    decision_reasoning: list[str],
    decisive_references,
    blocking_patent_ids: list[str],
    jurisdiction_gate_failures: dict[str, list[str]],
    decision_scope,
    supporting_scope,
    certification_scope,
    cohort_status,
    settings=None,
    build_matter_graph=None,
    summarize_matter_graph=None,
    build_evidence_artifacts=None,
    build_evidence_adapter_results=None,
) -> dict:
    """Assemble the final deterministic clearance payload."""
    matter_graph = _reuse_or_build_matter_graph(
        report=report,
        matter_evidence_index=matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        patent_hits=patent_hits,
        analyses=report.patent_analyses,
        build_matter_graph=build_matter_graph,
    )
    matter_graph_summary = _reuse_or_build_matter_graph_summary(
        report=report,
        matter_graph=matter_graph,
        build_summarize_matter_graph=summarize_matter_graph,
    )
    evidence_substrate = build_decisioning_evidence_substrate(
        report=report,
        coverage_context=coverage_context,
        matter_evidence_index=matter_evidence_index,
        record_completeness=record_completeness,
        claim_program_summary=claim_program_summary,
        claim_program_decisions=claim_program_decisions,
        settings=settings,
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        build_coverage_gaps_fn=build_coverage_gaps,
        build_authority_coverage_fn=build_authority_coverage,
        reuse_or_build_evidence_artifacts_fn=_reuse_or_build_evidence_artifacts,
        reuse_or_build_evidence_adapter_results_fn=_reuse_or_build_evidence_adapter_results,
        build_evidence_collection_plan_fn=build_evidence_collection_plan,
        reuse_or_build_collector_runs_fn=_reuse_or_build_collector_runs,
        build_run_observability_fn=build_run_observability,
        reuse_or_build_matter_store_fn=_reuse_or_build_matter_store,
        build_evidence_artifacts=build_evidence_artifacts,
        build_evidence_adapter_results=build_evidence_adapter_results,
    )
    blocker_families = build_blocker_family_records(
        decision=decision,
        claim_program_summary=claim_program_summary,
        claim_program_decisions=claim_program_decisions,
        matter_evidence_index=matter_evidence_index,
    )
    decision_audit = build_decision_audit_record(
        coverage_context=coverage_context,
        matter_evidence_index=matter_evidence_index,
        report=report,
        evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
        insufficiency_reasons=insufficiency_reasons,
        warnings=warnings,
        claim_program_summary=claim_program_summary,
        blocker_families=blocker_families,
        decisive_references=decisive_references,
    )
    jurisdiction_decisions = build_jurisdiction_decisions(
        jurisdiction_patents=coverage_context.jurisdiction_patents,
        blocking_by_jurisdiction=coverage_context.blocking_by_jurisdiction,
        evidence_quality=evidence_quality,
        decision_confidence=decision_confidence,
        gate_failures_by_jurisdiction=jurisdiction_gate_failures,
        claim_program_summary=claim_program_summary,
        claim_program_decisions=claim_program_decisions,
    )
    return build_clearance_output_payload(
        report=report,
        patent_hits=patent_hits,
        coverage_context=coverage_context,
        claim_program_decisions=claim_program_decisions,
        evidence_quality=evidence_quality,
        insufficiency_reasons=insufficiency_reasons,
        decision=decision,
        decision_confidence=decision_confidence,
        decision_reasoning=decision_reasoning,
        decision_audit=decision_audit,
        decision_scope=decision_scope,
        supporting_scope=supporting_scope,
        certification_scope=certification_scope,
        cohort_status=cohort_status,
        jurisdiction_decisions=jurisdiction_decisions,
        evidence_substrate=evidence_substrate,
        record_completeness=record_completeness,
        blocking_patent_ids=blocking_patent_ids,
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        build_claim_construction_record_fn=build_claim_construction_record,
        build_commercial_exposure_fn=build_commercial_exposure,
    )
