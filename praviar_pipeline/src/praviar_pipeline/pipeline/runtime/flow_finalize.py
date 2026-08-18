"""Final report assembly helpers for pipeline runtime flow orchestration."""

from __future__ import annotations

import time
from typing import cast

from praviar_pipeline.cost_tracker import get_current_tracker
from praviar_pipeline.logging_config import StepTimer
from praviar_pipeline.manifest import build_manifest, get_prompt_hasher
from praviar_pipeline.models.hitl import CheckpointType
from praviar_pipeline.models.report import (
    ActionItem,
    ActionPriority,
    ActionType,
    DataLimitation,
    SourceStatus,
)
from praviar_pipeline.models.report_source_spans import (
    build_claim_source_span_map,
    ensure_no_unsupported_customer_visible_claims,
)
from praviar_pipeline.pipeline.drawing_rollout import drawing_evidence_for_decisions
from praviar_pipeline.pipeline.runtime.decisioning import build_clearance_outputs
from praviar_pipeline.pipeline.runtime.flow_helpers import (
    attach_report_runtime_metadata,
)
from praviar_pipeline.pipeline.runtime.hitl import await_runtime_checkpoint
from praviar_pipeline.pipeline.runtime.report_review import (
    build_report_review_checkpoint_context,
)
from praviar_pipeline.response_cache import set_current_cache


def _log_cost_summary(logger) -> None:
    """Emit the per-role cost breakdown for the just-finished run."""
    tracker = get_current_tracker()
    if tracker is None:
        return
    snapshot = tracker.snapshot()
    totals = tracker.total_tokens()
    logger.info(
        "cost_summary",
        total_usd=round(tracker.total_usd(), 4),
        total_input_tokens=totals["input_tokens"],
        total_output_tokens=totals["output_tokens"],
        total_cache_read_tokens=totals["cache_read_tokens"],
        total_cache_creation_tokens=totals["cache_creation_tokens"],
        roles={role: round(data["estimated_usd"], 4) for role, data in snapshot.items()},
        call_counts={role: data["call_count"] for role, data in snapshot.items()},
    )


def _clear_cost_tracker() -> None:
    from praviar_pipeline.cost_tracker import set_current_tracker

    set_current_tracker(None)


def _source_label(value) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _search_sources_from_run(*, patent_hits, source_health) -> list[str]:
    """Return configured source names, preserving zero-hit and failed sources."""

    health_entries = (
        list(source_health.entries)
        if source_health is not None and hasattr(source_health, "entries")
        else []
    )
    if health_entries:
        return sorted(
            {
                source
                for source in (
                    _source_label(getattr(entry, "source", "")) for entry in health_entries
                )
                if source
            }
        )

    return sorted(
        {
            source
            for patent in patent_hits
            for source in (_source_label(source) for source in getattr(patent, "sources", []))
            if source
        }
    )


async def finalize_report_output(
    *,
    settings,
    compound,
    analyses,
    doe_assessments,
    invalidity_assessments,
    verification,
    patent_hits,
    source_health,
    analysis_failures,
    prosecution_cache,
    critic_report,
    drawing_evidence,
    timing_data,
    execution_profile: str,
    reasoning_traces: list,
    triage_audit,
    analysis_audit,
    search_funnel,
    expanded_queries=None,
    triage_results,
    triage_in: int,
    triage_out: int,
    critic_in: int,
    critic_out: int,
    search_loop_result,
    doe_in: int,
    doe_out: int,
    inv_in: int,
    inv_out: int,
    audit_trail_builder,
    prior_step_tokens_builder,
    generate_report_fn,
    write_pipeline_outputs_fn,
    notify_fn,
    raise_if_cancelled_fn,
    save_checkpoint_fn,
    make_timing_fn,
    checkpoint_decision_provider=None,
    checkpoint_poll_interval_seconds: float = 5.0,
    pipeline_start: float,
    output_format: str,
    logger,
    matter_graph=None,
    matter_graph_summary=None,
    matter_store=None,
    evidence_artifacts=None,
    evidence_adapter_results=None,
    collector_runs=None,
    clearance_outputs_builder=build_clearance_outputs,
    runtime_termination=None,
    regulatory_exclusivity=None,
    user_input: str = "",
    run_id: str = "",
) -> dict:
    """Build audit/report inputs, generate the report, and write outputs."""
    # Snapshot the process-wide PromptHasher once so the same dict is used in
    # both the audit trail and the report manifest — they must agree.
    prompt_hashes = get_prompt_hasher().snapshot()

    audit_trail = audit_trail_builder(
        search_funnel=search_funnel,
        triage_audit=triage_audit,
        analysis_audit=analysis_audit,
        timing_data=timing_data,
        patent_hits=patent_hits,
        triage_results=triage_results,
        analyses=analyses,
        prompt_hashes=prompt_hashes,
        compound=compound,
        expanded_queries=expanded_queries,
        search_loop_result=search_loop_result,
        source_health=source_health,
        settings=settings,
    )
    prior_step_tokens = prior_step_tokens_builder(
        triage_input_tokens=triage_in,
        triage_output_tokens=triage_out,
        critic_input_tokens=critic_in,
        critic_output_tokens=critic_out,
        search_loop_input_tokens=(
            search_loop_result.total_input_tokens if search_loop_result else 0
        ),
        search_loop_output_tokens=(
            search_loop_result.total_output_tokens if search_loop_result else 0
        ),
        doe_input_tokens=doe_in,
        doe_output_tokens=doe_out,
        invalidity_input_tokens=inv_in,
        invalidity_output_tokens=inv_out,
    )

    raise_if_cancelled_fn(8, "report")
    notify_fn(8, "report", "started", {"description": "Generating report"})
    step_start = time.time()
    search_sources = _search_sources_from_run(
        patent_hits=patent_hits,
        source_health=source_health,
    )
    analysis_in = sum(getattr(a, "input_tokens", 0) for a in analyses)
    analysis_out = sum(getattr(a, "output_tokens", 0) for a in analyses)
    prior_tokens = (
        triage_in
        + analysis_in
        + doe_in
        + inv_in
        + critic_in
        + (search_loop_result.total_input_tokens if search_loop_result else 0),
        triage_out
        + analysis_out
        + doe_out
        + inv_out
        + critic_out
        + (search_loop_result.total_output_tokens if search_loop_result else 0),
    )
    decision_drawing_evidence = drawing_evidence_for_decisions(settings, drawing_evidence)

    with StepTimer("step8_report", analyses_in=len(analyses)):
        report = await generate_report_fn(
            compound=compound,
            analyses=analyses,
            doe_assessments=doe_assessments,
            invalidity_assessments=invalidity_assessments,
            verification=verification,
            execution_profile=execution_profile,
            total_patents_found=len(patent_hits),
            search_sources=search_sources,
            source_health=source_health,
            prior_llm_tokens=prior_tokens,
            audit_trail=audit_trail,
            prior_step_tokens=prior_step_tokens,
            analysis_failures=analysis_failures,
            prosecution_cache=prosecution_cache,
            regulatory_exclusivity=regulatory_exclusivity,
            patent_hits=patent_hits,
            drawing_evidence=decision_drawing_evidence,
            critic_report=critic_report,
        )

    # Bind prompt provenance and exact claim/source spans before the report is
    # exposed at the human review checkpoint. A reviewer must never approve a
    # version whose source ledger is attached only after their decision.
    prompt_hashes = get_prompt_hasher().snapshot()
    if not prompt_hashes:
        _clear_cost_tracker()
        raise RuntimeError("pipeline completed without prompt hashes")
    report.audit_trail.prompt_hashes = prompt_hashes
    evidence_integrity_keys = settings.checkpoint_integrity_keys
    report.claim_source_span_map = build_claim_source_span_map(
        report.patent_analyses,
        getattr(report, "patent_details", {}) or {},
        trusted_patent_hits=patent_hits,
        evidence_attestation_key_id=evidence_integrity_keys.active_key_id,
        evidence_attestation_key=evidence_integrity_keys.active_key(),
        evidence_attestation_subject_id=str(report.report_id),
    )
    try:
        ensure_no_unsupported_customer_visible_claims(report.claim_source_span_map)
    except Exception:
        _clear_cost_tracker()
        raise

    try:
        report_review_context = build_report_review_checkpoint_context(
            report=report,
            run_id=run_id,
            analysis_failure_count=len(analysis_failures),
            prompt_hashes=prompt_hashes,
            evidence_attestation_key_id=evidence_integrity_keys.active_key_id,
            evidence_attestation_key=evidence_integrity_keys.active_key(),
        )
        await await_runtime_checkpoint(
            checkpoint_type=CheckpointType.REPORT_REVIEW,
            context=report_review_context,
            settings=settings,
            on_progress=notify_fn,
            decision_provider=checkpoint_decision_provider,
            poll_interval_seconds=checkpoint_poll_interval_seconds,
        )
    except Exception:
        _clear_cost_tracker()
        raise

    if runtime_termination:
        report.data_limitations.append(
            DataLimitation(
                category=runtime_termination.reason,
                description=runtime_termination.description,
                impact=runtime_termination.impact,
            )
        )
        report.action_items.insert(
            0,
            ActionItem(
                action_type=ActionType.HALT,
                priority=ActionPriority.CRITICAL,
                description=runtime_termination.action_description,
                patent_ids=[],
                reasoning=runtime_termination.action_reasoning,
                estimated_timeline="Before relying on any clearance conclusion.",
            ),
        )

    step8_timing = make_timing_fn("step8_report", step_start, len(analyses), 1)
    timing_data.append(step8_timing)
    # ``audit_trail_builder`` validated/copies the timings before report
    # generation starts. Persist the completion timing on the report itself so
    # downstream receipts can prove Step 8 actually completed instead of
    # inferring it merely because a report object exists.
    report.audit_trail.timing_data.append(step8_timing)
    logger.info(
        "step8_result",
        overall_risk=report.risk_summary.overall_risk.value,
        total_input_tokens=report.total_input_tokens,
        total_output_tokens=report.total_output_tokens,
        estimated_cost_usd=report.estimated_cost_usd,
    )

    elapsed = time.time() - pipeline_start
    total_tokens = report.total_input_tokens + report.total_output_tokens

    # Confidence-calibration metrics: make search coverage and risk-floor
    # decisions visible in production logs so operators can diagnose
    # under-coverage and calibrate confidence in the overall risk verdict.
    _sh = source_health
    _sh_entries = list(_sh.entries) if _sh is not None and hasattr(_sh, "entries") else []

    _queried_entries = [e for e in _sh_entries if e.status != SourceStatus.SKIPPED]
    _sources_queried_count = len(_queried_entries)
    _sources_with_results_count = sum(1 for e in _queried_entries if e.patent_count > 0)
    _overall_risk_val = report.risk_summary.overall_risk.value
    # Risk floor is triggered when the overall risk on a zero-analysis run is
    # anything other than CLEAR — i.e. the source-health policy promoted it.
    _risk_floor_triggered = not analyses and _overall_risk_val != "clear"

    logger.info(
        "pipeline_complete",
        elapsed_seconds=round(elapsed, 1),
        overall_risk=_overall_risk_val,
        total_tokens=total_tokens,
        estimated_cost_usd=report.estimated_cost_usd,
        patents_found=len(patent_hits),
        patents_analyzed=len(analyses),
        analysis_failures=len(analysis_failures),
        # Confidence calibration
        sources_queried_count=_sources_queried_count,
        sources_with_results_count=_sources_with_results_count,
        patents_found_total=len(patent_hits),
        patents_analyzed_count=len(analyses),
        risk_floor_triggered=_risk_floor_triggered,
    )

    attach_report_runtime_metadata(
        report,
        execution_profile=execution_profile,
        settings=settings,
        reasoning_traces=reasoning_traces,
        search_loop_result=search_loop_result,
        clearance_outputs_builder=clearance_outputs_builder,
        patent_hits=patent_hits,
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_store=matter_store,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
    )

    compound_query = user_input
    if not compound_query and compound is not None:
        compound_query = getattr(compound, "original_input", "") or getattr(compound, "name", "")

    manifest_source_health = source_health if hasattr(source_health, "entries") else None

    report.manifest = build_manifest(
        compound_query=compound_query,
        source_health=manifest_source_health,
        settings=settings,
    )
    if report.manifest.prompt_hashes != report.audit_trail.prompt_hashes:
        _clear_cost_tracker()
        raise RuntimeError("report manifest prompt hashes do not match audit trail")

    # Emit the per-role cost breakdown at end-of-run then tear down the tracker
    # singleton so the next run starts with a clean slate (and crashed runs
    # can't leak their usage into a subsequent one).
    try:
        _log_cost_summary(logger)
    finally:
        _clear_cost_tracker()

    raise_if_cancelled_fn(8, "write_json_report")
    try:
        output = cast("dict", await write_pipeline_outputs_fn(report, output_format))
        # Persist report completion only after the output has been written.
        # Step 12 already represents verification; reusing the former step-11
        # value here regressed resume ordering and could overwrite the latest
        # upstream checkpoint with an older stage number.
        save_checkpoint_fn(13)
        return output
    finally:
        set_current_cache(None)
