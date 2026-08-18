"""Execution helpers for the CLI pipeline orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from praviar_pipeline.models.hitl import CheckpointType
from praviar_pipeline.pipeline.analysis.adaptive_decision import dedupe_reasons
from praviar_pipeline.pipeline.drawing_rollout import (
    drawing_evidence_for_decisions,
    drawing_failures_are_fatal,
)
from praviar_pipeline.pipeline.identity_review import build_identity_review_context
from praviar_pipeline.pipeline.runtime.audit import (
    build_analysis_audit,
    build_triage_audit,
    map_relevant_patents,
)
from praviar_pipeline.pipeline.runtime.hitl import await_runtime_checkpoint
from praviar_pipeline.pipeline.runtime.live_collectors import execute_live_evidence_collectors
from praviar_pipeline.pipeline.runtime.pipeline_steps import (
    run_analysis_step,
    run_query_expansion_step,
    run_resolution_step,
    run_search_step,
    run_triage_step,
)
from praviar_pipeline.pipeline.runtime.post_analysis import (
    load_orange_book_if_available,
    run_critic_review,
    run_doe_assessment,
    run_invalidity_assessment,
    run_regulatory_enrichment,
    run_verification_step,
)
from praviar_pipeline.pipeline.runtime.search_enrichment import (
    run_claims_enrichment,
    run_post_search_enrichment,
    run_post_triage_drawing_enrichment,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type


@dataclass(slots=True)
class RunCallbacks:
    notify: Any
    raise_if_cancelled: Any
    save_checkpoint: Any
    make_timing: Any
    checkpoint_decision_provider: Any = None
    checkpoint_poll_interval_seconds: float = 5.0


async def execute_resolution_to_search_flow(*, state, callbacks: RunCallbacks) -> None:
    """Run the pre-analysis stages through search enrichment."""
    if state.completed_step < 1:
        callbacks.raise_if_cancelled(1, "resolve")
        state.compound = await run_resolution_step(
            user_input=state.user_input,
            timing_data=state.timing_data,
            notify=callbacks.notify,
            make_timing=callbacks.make_timing,
        )
        callbacks.save_checkpoint(1)

    if state.completed_step < 2:
        await _await_identity_checkpoint(state, callbacks)

    if state.completed_step < 2:
        callbacks.raise_if_cancelled(1, "expand")
        state.expanded_queries = await run_query_expansion_step(
            compound=state.compound,
            timing_data=state.timing_data,
            notify=callbacks.notify,
            make_timing=callbacks.make_timing,
        )
        callbacks.save_checkpoint(2)

    if state.completed_step < 3:
        callbacks.raise_if_cancelled(2, "search")
        search_step = await run_search_step(
            compound=state.compound,
            expanded_queries=state.expanded_queries,
            settings=state.settings,
            timing_data=state.timing_data,
            notify=callbacks.notify,
            make_timing=callbacks.make_timing,
        )
        state.patent_hits = search_step.patent_hits
        state.source_health = search_step.source_health
        state.search_funnel = search_step.search_funnel
        state.search_loop_result = search_step.search_loop_result
        callbacks.save_checkpoint(3)

    # Regulatory enrichment runs alongside the primary retrieval path. Failures
    # are non-blocking, but they must be visible in source health.
    # Guard on compound being resolved (step 1) and on not having a cached result
    # so that a checkpoint resume does not re-query paid sources.
    if state.compound is not None and not getattr(state, "regulatory_exclusivity", None):
        state.regulatory_exclusivity = await run_regulatory_enrichment(
            state.compound,
            source_health=state.source_health,
        )

    if state.patent_hits and state.completed_step < 4:
        callbacks.raise_if_cancelled(2, "family_enrichment")
        (
            state.patent_hits,
            ran_search_enrichment,
        ) = await run_post_search_enrichment(
            completed_step=state.completed_step,
            patent_hits=state.patent_hits,
            timing_data=state.timing_data,
            make_timing=callbacks.make_timing,
        )
        if ran_search_enrichment:
            callbacks.save_checkpoint(4)

    if state.completed_step < 5 and state.patent_hits:
        callbacks.raise_if_cancelled(2, "claims_enrichment")
        await run_claims_enrichment(
            completed_step=state.completed_step,
            patent_hits=state.patent_hits,
        )
        collector_result = await execute_live_evidence_collectors(
            compound=state.compound,
            patent_hits=state.patent_hits,
            source_health=state.source_health,
            prosecution_cache=state.prosecution_cache,
            collector_runs=state.collector_runs,
            settings=state.settings,
        )
        state.source_health = collector_result.source_health
        state.prosecution_cache = collector_result.prosecution_cache
        state.collector_runs = list(collector_result.collector_runs)
        callbacks.save_checkpoint(5)


async def execute_analysis_to_verification_flow(*, state, callbacks: RunCallbacks):
    """Run triage through verification and return derived audit artifacts."""
    if not state.patent_hits:
        if state.completed_step < 6:
            callbacks.notify(3, "triage", "step_skipped", {"reason": "no_patent_hits"})
            callbacks.save_checkpoint(6)
        return [], []

    if state.completed_step < 6:
        callbacks.raise_if_cancelled(3, "triage")
        # Drawings are in shadow mode and don't influence triage decisions yet,
        # so we pass empty evidence here — drawings run post-triage below.
        triage_step = await run_triage_step(
            patent_hits=state.patent_hits,
            compound=state.compound,
            drawing_evidence=drawing_evidence_for_decisions(
                state.settings,
                state.drawing_evidence,
            ),
            timing_data=state.timing_data,
            notify=callbacks.notify,
            make_timing=callbacks.make_timing,
        )
        state.triage_results = triage_step.triage_results
        state.triage_in = triage_step.triage_input_tokens
        state.triage_out = triage_step.triage_output_tokens
        state.triage_failed = triage_step.triage_failed
        state.all_triage = triage_step.all_triage
        callbacks.save_checkpoint(6)
        await _await_triage_checkpoint(state, callbacks)

    triage_audit = build_triage_audit(state.all_triage, state.triage_results)
    relevant_patents = map_relevant_patents(state.patent_hits, state.triage_results)
    _record_adaptive_escalation_reasons_if_needed(state, callbacks, relevant_patents)

    # Drawing analysis runs on the post-triage relevant set only, bounding EPO
    # OPS drawing downloads to the selected set rather than the full search set.
    if state.completed_step < 7 and state.settings.drawing_analysis_enabled and relevant_patents:
        callbacks.raise_if_cancelled(2, "drawing_enrichment")
        try:
            state.drawing_evidence = await run_post_triage_drawing_enrichment(
                patent_hits=relevant_patents,
                compound=state.compound,
                settings=state.settings,
                timing_data=state.timing_data,
                notify=callbacks.notify,
                make_timing=callbacks.make_timing,
            )
        except Exception as exc:
            if drawing_failures_are_fatal(state.settings):
                raise
            import structlog as _structlog

            _structlog.get_logger().warning(
                "drawing_enrichment_failed_non_fatal",
                error_type=safe_exception_type(exc),
            )
        callbacks.save_checkpoint(7)

    decision_drawing_evidence = drawing_evidence_for_decisions(
        state.settings,
        state.drawing_evidence,
    )

    if state.completed_step < 8:
        callbacks.raise_if_cancelled(4, "analyze")
        analysis_step = await run_analysis_step(
            relevant_patents=relevant_patents,
            compound=state.compound,
            triage_results=state.triage_results,
            global_escalation_reasons=state.analysis_escalation_reasons,
            drawing_evidence=decision_drawing_evidence,
            timing_data=state.timing_data,
            notify=callbacks.notify,
            make_timing=callbacks.make_timing,
        )
        state.analyses = analysis_step.analyses
        state.analysis_failures = analysis_step.analysis_failures
        state.reasoning_traces.extend(analysis_step.reasoning_traces)
        state.prosecution_cache = analysis_step.prosecution_cache
        callbacks.save_checkpoint(8)

    # Step 8 means the analysis bytes are durable, not that counsel approved
    # them. Re-run the digest-stable blocking gate when resuming that exact
    # checkpoint; only a later durable stage proves the review was passed.
    if state.completed_step <= 8:
        await _await_analysis_checkpoint(state, callbacks)

    analysis_audit = build_analysis_audit(relevant_patents, state.analyses)

    if state.completed_step < 9 and state.settings.critic_enabled and state.analyses:
        callbacks.raise_if_cancelled(4, "critic")
        callbacks.notify(4, "critic", "started", {"description": "Portfolio-level review"})
        (
            state.critic_report,
            state.critic_in,
            state.critic_out,
        ) = await run_critic_review(
            analyses=state.analyses,
            compound=state.compound,
            timing_data=state.timing_data,
            make_timing=callbacks.make_timing,
        )
        callbacks.notify(
            4,
            "critic",
            "completed",
            {
                "findings": len(state.critic_report.findings),
                "quality": state.critic_report.overall_quality_score,
            },
        )
        callbacks.save_checkpoint(9)

    if state.completed_step < 10:
        callbacks.raise_if_cancelled(5, "doe")
        callbacks.notify(5, "doe", "started", {"description": "Doctrine of Equivalents"})
        (
            state.doe_assessments,
            state.doe_in,
            state.doe_out,
        ) = await run_doe_assessment(
            analyses=state.analyses,
            compound=state.compound,
            drawing_evidence=decision_drawing_evidence,
            timing_data=state.timing_data,
            make_timing=callbacks.make_timing,
            prosecution_cache=state.prosecution_cache,
        )
        callbacks.notify(5, "doe", "completed", {"assessments": len(state.doe_assessments)})
        callbacks.save_checkpoint(10)

    if state.completed_step < 11:
        callbacks.raise_if_cancelled(6, "invalidity")
        callbacks.notify(6, "invalidity", "started", {"description": "Invalidity assessment"})
        (
            state.invalidity_assessments,
            state.inv_in,
            state.inv_out,
        ) = await run_invalidity_assessment(
            analyses=state.analyses,
            compound=state.compound,
            patent_hits=state.patent_hits,
            drawing_evidence=decision_drawing_evidence,
            timing_data=state.timing_data,
            make_timing=callbacks.make_timing,
        )
        callbacks.notify(
            6,
            "invalidity",
            "completed",
            {"assessed": len(state.invalidity_assessments)},
        )
        callbacks.save_checkpoint(11)

    orange_book = await load_orange_book_if_available()

    if state.completed_step < 12:
        callbacks.raise_if_cancelled(7, "verify")
        callbacks.notify(7, "verify", "started", {"description": "Cross-verification"})
        state.verification = run_verification_step(
            analyses=state.analyses,
            doe_assessments=state.doe_assessments,
            invalidity_assessments=state.invalidity_assessments,
            patent_hits=state.patent_hits,
            orange_book=orange_book,
            timing_data=state.timing_data,
            make_timing=callbacks.make_timing,
        )
        passed = sum(1 for check in state.verification.checks if check.passed)
        callbacks.notify(7, "verify", "completed", {"checks_passed": passed})
        callbacks.save_checkpoint(12)

    return triage_audit, analysis_audit


async def _await_triage_checkpoint(state, callbacks: RunCallbacks) -> None:
    await await_runtime_checkpoint(
        checkpoint_type=CheckpointType.TRIAGE_REVIEW,
        context={
            "run_id": getattr(state, "run_id", ""),
            "patent_count": len(state.patent_hits),
            "relevant_count": len(state.triage_results),
            "triage_failed": state.triage_failed,
            "items": [
                {
                    "patent_id": getattr(result, "patent_id", ""),
                    "relevance": getattr(getattr(result, "relevance", ""), "value", ""),
                    "confidence": getattr(result, "confidence", None),
                }
                for result in state.triage_results[:20]
            ],
        },
        settings=state.settings,
        on_progress=callbacks.notify,
        decision_provider=getattr(callbacks, "checkpoint_decision_provider", None),
        poll_interval_seconds=getattr(callbacks, "checkpoint_poll_interval_seconds", 5.0),
    )


async def _await_identity_checkpoint(state, callbacks: RunCallbacks) -> None:
    if state.compound is None:
        raise RuntimeError("Resolved compound is required before identity review.")
    await await_runtime_checkpoint(
        checkpoint_type=CheckpointType.IDENTITY_REVIEW,
        context=build_identity_review_context(
            state.compound,
            settings=state.settings,
            run_id=getattr(state, "run_id", ""),
        ),
        settings=state.settings,
        on_progress=callbacks.notify,
        decision_provider=getattr(callbacks, "checkpoint_decision_provider", None),
        poll_interval_seconds=getattr(callbacks, "checkpoint_poll_interval_seconds", 5.0),
    )


async def _await_analysis_checkpoint(state, callbacks: RunCallbacks) -> None:
    await await_runtime_checkpoint(
        checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
        context={
            "run_id": getattr(state, "run_id", ""),
            "analysis_count": len(state.analyses),
            "analysis_failure_count": len(state.analysis_failures),
            "high_risk_count": sum(
                1
                for analysis in state.analyses
                if getattr(getattr(analysis, "risk_level", None), "value", "") == "high"
            ),
            "quality_gate_failure_count": sum(
                1
                for analysis in state.analyses
                if getattr(analysis, "analysis_quality_gate_failures", [])
            ),
            "items": [
                {
                    "patent_id": getattr(analysis, "patent_id", ""),
                    "risk_level": getattr(getattr(analysis, "risk_level", None), "value", ""),
                    "quality_gate_failures": list(
                        getattr(analysis, "analysis_quality_gate_failures", []) or []
                    ),
                }
                for analysis in state.analyses[:20]
            ],
        },
        settings=state.settings,
        on_progress=callbacks.notify,
        decision_provider=getattr(callbacks, "checkpoint_decision_provider", None),
        poll_interval_seconds=getattr(callbacks, "checkpoint_poll_interval_seconds", 5.0),
    )


def _record_adaptive_escalation_reasons_if_needed(
    state,
    callbacks: RunCallbacks,
    relevant_patents: list,
) -> None:
    if state.completed_step >= 8:
        return

    reasons = _adaptive_escalation_reasons(state, relevant_patents)
    if not reasons:
        return

    state.analysis_escalation_reasons = dedupe_reasons(
        list(getattr(state, "analysis_escalation_reasons", []) or []) + reasons
    )
    callbacks.notify(
        4,
        "analysis_profile",
        "escalated",
        {
            "execution_profile": state.execution_profile,
            "reasons": state.analysis_escalation_reasons,
        },
    )


def _adaptive_escalation_reasons(state, relevant_patents: list) -> list[str]:
    reasons: list[str] = []
    if getattr(state, "source_health", None) is not None and state.source_health.any_failed:
        reasons.append("weak_source_coverage")

    if len(relevant_patents) >= 10:
        reasons.append("dense_relevant_landscape")

    high_risk_terms = {
        "blocking",
        "high",
        "injunction",
        "assert",
        "assertion",
        "license",
        "licence",
        "literal",
    }
    for triage in getattr(state, "triage_results", []) or []:
        raw_relevance = getattr(triage, "relevance", "")
        relevance = getattr(raw_relevance, "value", raw_relevance)
        blocking_text = str(getattr(triage, "blocking_potential", "") or "").lower()
        has_key_claims = bool(getattr(triage, "key_claims", []) or [])
        raw_confidence = getattr(triage, "confidence", None)
        confidence = float(raw_confidence) if raw_confidence is not None else 1.0
        has_high_risk_terms = bool(high_risk_terms & set(blocking_text.split()))
        if relevance == "relevant" and (has_key_claims or has_high_risk_terms):
            reasons.append("high_risk_triage")
            break
        if relevance in {"relevant", "possibly_relevant"} and confidence < 0.65:
            reasons.append("verification_uncertainty")
            break

    return list(dict.fromkeys(reasons))
