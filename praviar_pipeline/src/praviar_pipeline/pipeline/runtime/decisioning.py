"""Deterministic matter-level clearance decision helpers."""

from __future__ import annotations

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.pipeline.accused_acts import normalize_accused_acts
from praviar_pipeline.pipeline.report.evidence_index import build_matter_evidence_index
from praviar_pipeline.pipeline.runtime.decisioning_coverage import build_decision_coverage_context
from praviar_pipeline.pipeline.runtime.decisioning_metrics import (
    build_clearance_gate_failures,
    build_decision_reasoning,
    build_evidence_warnings,
    build_jurisdiction_gate_failures,
    build_scope_contract,
    coverage_ratio,
    score_evidence_quality,
)
from praviar_pipeline.pipeline.runtime.decisioning_outputs import (
    assemble_clearance_outputs,
    build_claim_program_summary,
    determine_clearance_decision,
    determine_decision_confidence,
    populate_coverage_summary_from_index,
)
from praviar_pipeline.pipeline.runtime.decisioning_references import build_decisive_references
from praviar_pipeline.pipeline.runtime.evidence_runtime import (
    build_claim_program_decisions,
    build_evidence_adapter_results,
    build_evidence_artifacts,
    build_matter_graph,
    build_record_completeness,
    resolve_required_record_components,
    summarize_matter_graph,
)
from praviar_pipeline.pipeline.search.markush_evidence import (
    evaluate_markush_clearance_evidence,
)


def _governed_overall_risk(report, governed_patent_ids: set[str]) -> RiskLevel:
    """Return the upstream risk screen for only the governed patent cohort."""
    priorities = {
        RiskLevel.CLEAR: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }
    risks: list[RiskLevel] = [
        analysis.risk_level
        for analysis in report.patent_analyses
        if analysis.patent_id in governed_patent_ids
    ]
    if not risks:
        return RiskLevel.CLEAR
    return max(risks, key=priorities.__getitem__)


def build_clearance_outputs(report, patent_hits: list | None, settings=None) -> dict:
    """Build deterministic top-line decision outputs from the completed report."""
    patent_hits = patent_hits or []
    intended_actions = list(
        dict.fromkeys(
            str(action).strip().lower()
            for action in getattr(settings, "intended_actions", []) or []
            if str(action).strip()
        )
    )
    product_context = getattr(settings, "product_context", None)
    accused_acts = normalize_accused_acts(intended_actions, product_context)
    detail_map = {
        getattr(hit, "patent_id", ""): hit for hit in patent_hits if getattr(hit, "patent_id", "")
    }
    coverage_context = build_decision_coverage_context(report, detail_map)
    (
        decision_scope,
        supporting_scope,
        certification_scope,
        cohort_status,
        cohort_gate_reason,
    ) = build_scope_contract(report, coverage_context, settings=settings)
    target_jurisdictions = list(
        dict.fromkeys(
            str(jurisdiction).strip().upper()
            for jurisdiction in getattr(settings, "target_jurisdictions", []) or []
            if str(jurisdiction).strip()
        )
    )
    reviewed_jurisdictions = [
        jurisdiction
        for jurisdiction, patent_ids in coverage_context.jurisdiction_patents.items()
        if patent_ids
    ]
    governed_jurisdictions = target_jurisdictions or reviewed_jurisdictions
    governed_patent_ids = {
        patent_id
        for jurisdiction in governed_jurisdictions
        for patent_id in coverage_context.jurisdiction_patents.get(jurisdiction, [])
    }
    explicit_governed_patent_ids = governed_patent_ids if target_jurisdictions else None
    matter_evidence_index = build_matter_evidence_index(
        analyses=report.patent_analyses,
        doe_assessments=report.doe_assessments,
        invalidity_assessments=report.invalidity_assessments,
        analysis_failures=report.analysis_failures,
        patent_hits=patent_hits,
        prosecution_dossiers=getattr(report, "prosecution_dossiers", None),
        critic_report=report.critic_report,
        source_health=report.source_health,
    )
    required_record_components = resolve_required_record_components(settings, coverage_context)
    populate_coverage_summary_from_index(
        coverage_context=coverage_context,
        matter_evidence_index=matter_evidence_index,
        required_record_components=required_record_components,
    )

    source_ok_ratio = (
        coverage_ratio(coverage_context.ok_sources, coverage_context.queried_sources)
        if coverage_context.queried_sources
        else 0.0
    )
    governed_material_patent_count = len(governed_patent_ids)
    governed_missing_claim_ids = set(
        coverage_context.coverage_summary.patents_missing_claims
    ).intersection(governed_patent_ids)
    governed_missing_family_ids = set(
        coverage_context.coverage_summary.patents_missing_family_context
    ).intersection(governed_patent_ids)
    governed_patents_with_claims = governed_material_patent_count - len(governed_missing_claim_ids)
    governed_patents_with_family = governed_material_patent_count - len(governed_missing_family_ids)
    claims_ratio = (
        coverage_ratio(
            governed_patents_with_claims,
            governed_material_patent_count,
        )
        if governed_material_patent_count
        else 0.0
    )
    family_ratio = (
        coverage_ratio(
            governed_patents_with_family,
            governed_material_patent_count,
        )
        if governed_material_patent_count
        else 0.0
    )
    governed_us_patent_ids = governed_patent_ids.intersection(
        coverage_context.coverage_summary.reviewed_us_patent_ids
    )
    governed_ep_patent_ids = governed_patent_ids.intersection(
        coverage_context.coverage_summary.reviewed_ep_patent_ids
    )
    governed_us_patents_with_prosecution_context = len(governed_us_patent_ids) - len(
        governed_us_patent_ids.intersection(
            coverage_context.coverage_summary.us_patents_missing_prosecution_context
        )
    )
    governed_us_patents_with_file_wrapper_dossier = len(governed_us_patent_ids) - len(
        governed_us_patent_ids.intersection(
            coverage_context.coverage_summary.us_patents_missing_file_wrapper_dossier
        )
    )
    governed_ep_patents_with_register_context = len(governed_ep_patent_ids) - len(
        governed_ep_patent_ids.intersection(
            coverage_context.coverage_summary.ep_patents_missing_register_context
        )
    )
    us_prosecution_ratio = coverage_ratio(
        governed_us_patents_with_file_wrapper_dossier,
        len(governed_us_patent_ids),
    )
    ep_register_ratio = coverage_ratio(
        governed_ep_patents_with_register_context,
        len(governed_ep_patent_ids),
    )
    evidence_quality = score_evidence_quality(
        source_ok_ratio=source_ok_ratio,
        claims_ratio=claims_ratio,
        family_ratio=family_ratio,
        us_prosecution_ratio=us_prosecution_ratio,
        ep_register_ratio=ep_register_ratio,
    )

    warnings = build_evidence_warnings(
        report=report,
        required_record_components=required_record_components,
        queried_sources=coverage_context.queried_sources,
        successful_sources=coverage_context.ok_sources,
        material_patent_count=governed_material_patent_count,
        claims_ratio=claims_ratio,
        patents_missing_claim_level_analysis=len(
            governed_patent_ids.intersection(
                coverage_context.coverage_summary.patents_missing_claim_level_analysis
            )
        ),
        patents_missing_authoritative_records=len(
            governed_patent_ids.intersection(
                coverage_context.coverage_summary.patents_missing_authoritative_records
            )
        ),
        us_patents=len(governed_us_patent_ids),
        us_patents_with_prosecution_context=governed_us_patents_with_prosecution_context,
        us_patents_with_file_wrapper_dossier=(governed_us_patents_with_file_wrapper_dossier),
        ep_patents=len(governed_ep_patent_ids),
        ep_patents_with_register_context=governed_ep_patents_with_register_context,
        reviewed_patent_ids=explicit_governed_patent_ids,
    )
    governed_authoritative_contradictions = (
        [
            contradiction
            for jurisdiction in governed_jurisdictions
            for contradiction in (
                coverage_context.authoritative_record_contradictions_by_jurisdiction.get(
                    jurisdiction, []
                )
            )
        ]
        if target_jurisdictions
        else list(coverage_context.authoritative_record_contradictions or [])
    )
    warnings = list(dict.fromkeys(warnings + governed_authoritative_contradictions))
    if coverage_context.coverage_summary.verification_gaps:
        warnings.append(
            "Verification did not fully pass: "
            f"{coverage_context.coverage_summary.verification_gaps[0]}"
        )
    record_completeness = build_record_completeness(
        report=report,
        coverage_context=coverage_context,
        settings=settings,
        reviewed_patent_ids=explicit_governed_patent_ids,
        jurisdictions=governed_jurisdictions,
    )
    insufficiency_reasons = build_clearance_gate_failures(
        report=report,
        coverage_context=coverage_context,
        reviewed_patent_ids=explicit_governed_patent_ids,
    )
    missing_target_jurisdictions = [
        jurisdiction
        for jurisdiction in target_jurisdictions
        if not coverage_context.jurisdiction_patents.get(jurisdiction, [])
    ]
    target_jurisdiction_gate_reason = (
        (
            "No material patent record was reviewed for target jurisdiction(s): "
            f"{', '.join(missing_target_jurisdictions)}."
        )
        if missing_target_jurisdictions
        else ""
    )
    accused_act_gate_reason = (
        ""
        if accused_acts
        else (
            "Accused commercial acts are not specified; manufacture, import, offer-for-sale, "
            "sale, and use exposure cannot be resolved."
        )
    )
    insufficiency_reasons = list(
        dict.fromkeys(
            insufficiency_reasons
            + record_completeness.blocking_gaps
            + governed_authoritative_contradictions
            + ([accused_act_gate_reason] if accused_act_gate_reason else [])
            + ([target_jurisdiction_gate_reason] if target_jurisdiction_gate_reason else [])
            + ([cohort_gate_reason] if cohort_gate_reason else [])
        )
    )
    claim_program_decisions = build_claim_program_decisions(
        report=report,
        detail_map=detail_map,
        coverage_context=coverage_context,
        intended_actions=intended_actions,
        product_context=product_context,
        target_jurisdictions=target_jurisdictions,
        development_stage=getattr(settings, "development_stage", ""),
        receipt_verification_keys=getattr(
            settings,
            "checkpoint_integrity_keys",
            None,
        ),
    )
    governed_claim_program_decisions = (
        [
            claim_program_decision
            for claim_program_decision in claim_program_decisions
            if claim_program_decision.patent_id in governed_patent_ids
        ]
        if target_jurisdictions
        else claim_program_decisions
    )
    claim_program_summary = build_claim_program_summary(governed_claim_program_decisions)
    claim_program_blocking_patent_ids = list(claim_program_summary.blocking_patent_ids)
    blocking_patent_ids = claim_program_blocking_patent_ids or (
        [
            patent_id
            for jurisdiction in governed_jurisdictions
            for patent_id in coverage_context.blocking_by_jurisdiction.get(jurisdiction, [])
        ]
        if not (
            claim_program_summary.total_claim_programs_reviewed
            or claim_program_summary.patent_level_fallback_count
        )
        else []
    )
    overall_risk = (
        _governed_overall_risk(report, governed_patent_ids)
        if target_jurisdictions
        else report.risk_summary.overall_risk
    )
    if not blocking_patent_ids and overall_risk == RiskLevel.CLEAR:
        markush_clearance_evidence = evaluate_markush_clearance_evidence(
            report,
            settings,
        )
        insufficiency_reasons = list(
            dict.fromkeys(insufficiency_reasons + markush_clearance_evidence.failure_reasons)
        )
    evidence_sufficient_for_clearance = not insufficiency_reasons
    jurisdiction_gate_failures = {
        jurisdiction: build_jurisdiction_gate_failures(
            jurisdiction=jurisdiction,
            reviewed_patent_ids=coverage_context.jurisdiction_patents.get(jurisdiction, []),
            coverage_summary=coverage_context.coverage_summary,
            report=report,
        )
        for jurisdiction in ("US", "EP")
    }
    if cohort_gate_reason:
        for jurisdiction in ("US", "EP"):
            if coverage_context.jurisdiction_patents.get(jurisdiction):
                jurisdiction_gate_failures[jurisdiction] = list(
                    dict.fromkeys(
                        [*jurisdiction_gate_failures.get(jurisdiction, []), cohort_gate_reason]
                    )
                )
    for jurisdiction in ("US", "EP"):
        missing_target_reason = (
            target_jurisdiction_gate_reason if jurisdiction in missing_target_jurisdictions else ""
        )
        if coverage_context.jurisdiction_patents.get(jurisdiction):
            jurisdiction_gate_failures[jurisdiction] = list(
                dict.fromkeys(
                    jurisdiction_gate_failures.get(jurisdiction, [])
                    + ([accused_act_gate_reason] if accused_act_gate_reason else [])
                    + ([missing_target_reason] if missing_target_reason else [])
                    + list(
                        coverage_context.authoritative_record_contradictions_by_jurisdiction.get(
                            jurisdiction, []
                        )
                    )
                )
            )
        elif missing_target_reason:
            jurisdiction_gate_failures[jurisdiction] = list(
                dict.fromkeys(
                    [*jurisdiction_gate_failures.get(jurisdiction, []), missing_target_reason]
                )
            )

    decision = determine_clearance_decision(
        overall_risk=overall_risk,
        evidence_quality=evidence_quality,
        evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
        warnings=warnings,
        claim_program_summary=claim_program_summary,
        blocking_patent_ids=blocking_patent_ids,
        authoritative_record_contradictions=governed_authoritative_contradictions,
    )
    decision_confidence = determine_decision_confidence(
        decision=decision,
        evidence_quality=evidence_quality,
        evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
    )
    decision_reasoning = build_decision_reasoning(
        overall_risk=overall_risk,
        decision=decision,
        evidence_quality=evidence_quality,
        evidence_sufficient=evidence_sufficient_for_clearance,
        material_patent_count=governed_material_patent_count,
        blocking_patent_ids=blocking_patent_ids,
        blocking_claim_ids=claim_program_summary.blocking_claim_ids,
        contested_claim_ids=claim_program_summary.contested_claim_ids,
        medium_risk_claim_ids=claim_program_summary.medium_risk_claim_ids,
        inactive_coverage_claim_ids=claim_program_summary.inactive_coverage_claim_ids,
        insufficiency_reasons=insufficiency_reasons,
        warnings=warnings,
    )
    decisive_references = build_decisive_references(
        decision=decision,
        analyses_by_id=coverage_context.analyses_by_id,
        detail_map=detail_map,
        coverage_summary=coverage_context.coverage_summary,
        blocking_patent_ids=blocking_patent_ids,
        prosecution_findings=coverage_context.prosecution_findings,
        future_risk=coverage_context.future_risk,
    )

    return assemble_clearance_outputs(
        report=report,
        patent_hits=patent_hits,
        matter_evidence_index=matter_evidence_index,
        coverage_context=coverage_context,
        record_completeness=record_completeness,
        claim_program_decisions=claim_program_decisions,
        claim_program_summary=claim_program_summary,
        evidence_quality=evidence_quality,
        warnings=warnings,
        insufficiency_reasons=insufficiency_reasons,
        evidence_sufficient_for_clearance=evidence_sufficient_for_clearance,
        decision=decision,
        decision_confidence=decision_confidence,
        decision_reasoning=decision_reasoning,
        decisive_references=decisive_references,
        blocking_patent_ids=blocking_patent_ids,
        jurisdiction_gate_failures=jurisdiction_gate_failures,
        decision_scope=decision_scope,
        supporting_scope=supporting_scope,
        certification_scope=certification_scope,
        cohort_status=cohort_status,
        settings=settings,
        build_matter_graph=build_matter_graph,
        summarize_matter_graph=summarize_matter_graph,
        build_evidence_artifacts=build_evidence_artifacts,
        build_evidence_adapter_results=build_evidence_adapter_results,
    )
