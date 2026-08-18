"""Helper routines for pipeline bootstrap restoration and final report decoration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

from praviar_pipeline.certification_policy import (
    normalize_jurisdiction,
    normalize_matter_type,
    normalize_trust_mode,
)
from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report_decisioning import OpinionReadiness
from praviar_pipeline.pipeline.analysis.adaptive_decision import WORLD_CLASS_EXECUTION_PROFILE
from praviar_pipeline.pipeline.report.governed_actions import (
    build_governed_action_items,
    build_governed_key_risks,
)

if TYPE_CHECKING:
    from praviar_pipeline.pipeline.runtime.flow import RunBootstrapResult


def _opinion_readiness(report, settings) -> OpinionReadiness:
    """Derive fail-closed export readiness from the governed signed report."""

    trust_mode = cast(
        'Literal["explorer", "counsel", "monitor"]',
        normalize_trust_mode(getattr(settings, "trust_mode", "")),
    )
    target_jurisdictions = list(
        dict.fromkeys(
            normalize_jurisdiction(jurisdiction)
            for jurisdiction in getattr(settings, "target_jurisdictions", []) or []
            if normalize_jurisdiction(jurisdiction)
        )
    )
    if not target_jurisdictions:
        target_jurisdictions = list(report.decision_scope.jurisdictions)

    certification = report.certification_scope
    decision_scope = {
        normalize_jurisdiction(jurisdiction)
        for jurisdiction in getattr(report.decision_scope, "jurisdictions", []) or []
        if normalize_jurisdiction(jurisdiction)
    }

    def decision_value(decision, name: str, default=None):
        if isinstance(decision, Mapping):
            return decision.get(name, default)
        return getattr(decision, name, default)

    decisions = {}
    for decision in report.jurisdiction_decisions:
        jurisdiction = normalize_jurisdiction(decision_value(decision, "jurisdiction", ""))
        if jurisdiction:
            decisions[jurisdiction] = decision

    gate_failures: list[str] = []
    blocked_jurisdictions: list[str] = []
    if trust_mode != "counsel":
        gate_failures.append("counsel_trust_mode_required")
    if not target_jurisdictions:
        gate_failures.append("target_jurisdictions_missing")
    if getattr(certification, "evidence_verified", False) is not True:
        gate_failures.append("release_certification_receipt_invalid_or_missing")
    if getattr(certification, "current_matter_type_certified", False) is not True:
        gate_failures.append("matter_type_not_certified")

    for jurisdiction in target_jurisdictions:
        decision = decisions.get(jurisdiction)
        jurisdiction_blocked = (
            jurisdiction not in decision_scope
            or decision is None
            or decision_value(decision, "evidence_sufficient_for_clearance", False) is not True
            or bool(decision_value(decision, "gate_failures", []))
            or decision_value(decision, "local_review_required", False) is True
        )
        if jurisdiction_blocked:
            blocked_jurisdictions.append(jurisdiction)

    if blocked_jurisdictions:
        gate_failures.append("selected_jurisdiction_lanes_incomplete")
    gate_failures = list(dict.fromkeys(gate_failures))
    export_ready = not gate_failures
    if export_ready:
        summary = (
            "The selected jurisdiction lanes have signed release evidence and "
            "clearance-grade records. Persisted legal approval and all required "
            "reviewer decisions remain mandatory before export or sharing."
        )
    else:
        summary = (
            "Export remains blocked until counsel mode, signed release certification, "
            "and complete clearance-grade evidence are present for every selected "
            "jurisdiction lane."
        )
    return OpinionReadiness(
        trust_mode=trust_mode,
        attorney_supervision_required=True,
        export_ready=export_ready,
        jurisdictions_blocking_export=blocked_jurisdictions,
        gate_failures=gate_failures,
        summary=summary,
    )


def restore_run_context_from_checkpoint(
    context: RunBootstrapResult,
    *,
    resume_state,
    resolved_checkpoint_dir,
    bind_compound_context_fn,
    logger,
) -> RunBootstrapResult:
    """Mutate the bootstrap context with restored checkpoint state."""
    context.completed_step = resume_state.completed_step
    context.run_id = resume_state.run_id
    context.execution_profile = resume_state.execution_profile
    context.analysis_escalation_reasons = list(resume_state.analysis_escalation_reasons)
    context.started_at_epoch = resume_state.started_at_epoch
    context.deadline_epoch = resume_state.deadline_epoch
    context.user_input = resume_state.compound_input
    context.checkpoint_dir = resolved_checkpoint_dir / context.run_id
    context.compound = resume_state.compound
    context.expanded_queries = resume_state.expanded_queries
    context.patent_hits = resume_state.patent_hits
    context.source_health = resume_state.source_health
    context.search_funnel = resume_state.search_funnel
    context.matter_graph = getattr(resume_state, "matter_graph", None)
    context.matter_graph_summary = getattr(resume_state, "matter_graph_summary", None)
    context.matter_store = getattr(resume_state, "matter_store", None)
    context.evidence_artifacts = list(getattr(resume_state, "evidence_artifacts", []) or [])
    context.evidence_adapter_results = list(
        getattr(resume_state, "evidence_adapter_results", []) or []
    )
    context.collector_runs = list(getattr(resume_state, "collector_runs", []) or [])
    context.drawing_evidence = resume_state.drawing_evidence
    context.triage_results = resume_state.triage_results
    context.all_triage = resume_state.all_triage_results
    context.triage_in = resume_state.triage_input_tokens
    context.triage_out = resume_state.triage_output_tokens
    context.triage_failed = resume_state.triage_failed
    context.analyses = resume_state.analyses
    context.analysis_failures = resume_state.analysis_failures
    context.prosecution_cache = getattr(resume_state, "prosecution_cache", {}) or {}
    context.reasoning_traces = resume_state.reasoning_traces
    context.critic_report = resume_state.critic_report
    context.critic_in = resume_state.critic_input_tokens
    context.critic_out = resume_state.critic_output_tokens
    context.search_loop_result = resume_state.search_loop_result
    context.doe_assessments = resume_state.doe_assessments
    context.doe_in = resume_state.doe_input_tokens
    context.doe_out = resume_state.doe_output_tokens
    context.invalidity_assessments = resume_state.invalidity_assessments
    context.inv_in = resume_state.inv_input_tokens
    context.inv_out = resume_state.inv_output_tokens
    context.verification = resume_state.verification
    context.timing_data = resume_state.timing_data

    if context.compound:
        bind_compound_context_fn(name=context.compound.name, cid=context.compound.pubchem_cid)

    logger.info(
        "pipeline_resumed",
        from_step=context.completed_step,
    )
    return context


def attach_report_runtime_metadata(
    report,
    *,
    execution_profile: str,
    settings,
    reasoning_traces: list,
    search_loop_result,
    clearance_outputs_builder,
    patent_hits,
    matter_graph=None,
    matter_graph_summary=None,
    matter_store=None,
    evidence_artifacts=None,
    evidence_adapter_results=None,
    collector_runs=None,
):
    """Attach runtime metadata and derived clearance outputs to the final report."""
    report.execution_profile = WORLD_CLASS_EXECUTION_PROFILE
    report.report_pipeline = WORLD_CLASS_EXECUTION_PROFILE
    if reasoning_traces:
        report.reasoning_traces = [trace.model_dump(mode="json") for trace in reasoning_traces]
    if search_loop_result:
        report.search_loop_result = search_loop_result
    if matter_graph is not None:
        report.matter_graph = matter_graph
    if matter_graph_summary is not None:
        report.matter_graph_summary = matter_graph_summary
    if matter_store is not None:
        report.matter_store = matter_store
    if evidence_artifacts is not None:
        report.evidence_artifacts = list(evidence_artifacts)
    if evidence_adapter_results is not None:
        report.evidence_adapter_results = list(evidence_adapter_results)
    if collector_runs is not None:
        report.collector_runs = list(collector_runs)

    clearance_outputs = clearance_outputs_builder(report, patent_hits, settings=settings)
    report.clearance_decision = clearance_outputs["clearance_decision"]
    report.jurisdiction_decisions = clearance_outputs["jurisdiction_decisions"]
    report.decision_scope = clearance_outputs["decision_scope"]
    report.supporting_scope = clearance_outputs["supporting_scope"]
    report.certification_scope = clearance_outputs["certification_scope"]
    report.trust_mode = normalize_trust_mode(getattr(settings, "trust_mode", ""))
    report.intended_actions = list(
        dict.fromkeys(
            str(action).strip().lower()
            for action in getattr(settings, "intended_actions", []) or []
            if str(action).strip()
        )
    )
    report.target_jurisdictions = list(
        dict.fromkeys(
            normalize_jurisdiction(jurisdiction)
            for jurisdiction in getattr(settings, "target_jurisdictions", []) or []
            if normalize_jurisdiction(jurisdiction)
        )
    )
    report.jurisdiction_bundle = (
        str(getattr(settings, "jurisdiction_bundle", "") or "").strip() or "custom"
    )
    report.development_stage = (
        str(getattr(settings, "development_stage", "") or "").strip().lower() or "discovery"
    )
    report.asset_type_hint = (
        str(getattr(settings, "asset_type_hint", "") or "").strip().lower() or "unknown"
    )
    routed_modality = normalize_matter_type(
        report.asset_type_hint
        if report.asset_type_hint != "unknown"
        else getattr(report.decision_scope, "matter_type", "")
    )
    report.routing_profile = {
        "modality": routed_modality or "unknown",
        "capability_profile": (
            "counsel_certified"
            if getattr(
                report.certification_scope,
                "current_matter_type_certified",
                False,
            )
            else "specialist_supervised"
        ),
        "execution_profile": WORLD_CLASS_EXECUTION_PROFILE,
    }
    report.opinion_readiness = _opinion_readiness(report, settings)
    decision_value = report.clearance_decision.decision.value
    report.risk_summary.overall_risk = {
        "clear": RiskLevel.CLEAR,
        "unclear": RiskLevel.MEDIUM,
        "blocked": RiskLevel.HIGH,
    }[decision_value]
    blocking_patent_ids = list(
        report.clearance_decision.decision_audit.claim_program_summary.blocking_patent_ids
    )
    report.risk_summary.blocking_patents_count = len(blocking_patent_ids)
    report.risk_summary.key_risks = build_governed_key_risks(clearance_outputs)
    analyzed_count = report.risk_summary.total_patents_analyzed
    posture_label = (
        "POTENTIAL BLOCKER — COUNSEL REVIEW REQUIRED"
        if decision_value == "blocked"
        else decision_value.upper()
    )
    report.risk_summary.executive_summary = (
        f"Screening posture: {posture_label}. {len(blocking_patent_ids)} potential blocking "
        f"patent{'s' if len(blocking_patent_ids) != 1 else ''} identified from "
        f"{analyzed_count} analyzed."
    )
    report.prosecution_findings = clearance_outputs["prosecution_findings"]
    report.claim_construction_record = clearance_outputs["claim_construction_record"]
    report.future_risk = clearance_outputs["future_risk"]
    report.claim_program_decisions = clearance_outputs.get("claim_program_decisions", [])
    report.evidence_artifacts = clearance_outputs.get("evidence_artifacts", [])
    report.evidence_adapter_results = clearance_outputs.get("evidence_adapter_results", [])
    report.collector_runs = clearance_outputs.get("collector_runs", [])
    report.evidence_collection_plan = clearance_outputs.get("evidence_collection_plan", [])
    report.coverage_gaps = clearance_outputs.get("coverage_gaps", [])
    report.matter_graph = clearance_outputs.get("matter_graph", {})
    report.matter_graph_summary = clearance_outputs.get("matter_graph_summary", {})
    report.matter_store = clearance_outputs.get("matter_store", {})
    report.authority_coverage = clearance_outputs.get("authority_coverage", {})
    report.record_completeness = clearance_outputs.get("record_completeness", {})
    report.run_observability = clearance_outputs.get("run_observability", {})
    report.commercial_exposure = clearance_outputs["commercial_exposure"]
    report.action_items = build_governed_action_items(report, clearance_outputs)
    return report
