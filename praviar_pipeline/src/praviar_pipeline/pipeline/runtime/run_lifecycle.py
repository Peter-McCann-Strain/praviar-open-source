"""Lifecycle helpers for the CLI pipeline orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from praviar_pipeline.errors import PipelineCancelledError, RuntimeBudgetExceededError
from praviar_pipeline.models.audit import StepTiming
from praviar_pipeline.pipeline.runtime.flow import RuntimeTerminationInfo

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class RunLifecycleAdapters:
    notify: Callable[[int, str, str, dict], None]
    raise_if_cancelled: Callable[[int, str], None]
    raise_if_cancelled_for_report: Callable[[int, str], None]
    save_checkpoint: Callable[[int], None]
    make_timing: Callable[[str, float, int, int], StepTiming]


def build_step_timing(step_name: str, start: float, items_in: int, items_out: int) -> StepTiming:
    """Create a StepTiming record for a completed step."""
    now = time.time()
    return StepTiming(
        step_name=step_name,
        started_at=datetime.fromtimestamp(start, tz=UTC),
        completed_at=datetime.fromtimestamp(now, tz=UTC),
        duration_seconds=round(now - start, 2),
        items_processed=items_in,
        items_output=items_out,
    )


def build_run_lifecycle_adapters(
    *,
    state,
    on_progress,
    should_cancel,
    build_runtime_evidence_snapshot_fn,
    save_runtime_checkpoint_fn,
) -> RunLifecycleAdapters:
    """Build the stateful helpers used across the CLI runtime."""

    def notify(step: int, name: str, event: str, payload: dict | None = None) -> None:
        if on_progress:
            on_progress(step, name, event, payload or {})

    def raise_if_cancelled(step: int, name: str) -> None:
        if state.deadline_epoch is not None and time.time() >= state.deadline_epoch:
            raise RuntimeBudgetExceededError(
                f"Pipeline exceeded max_run_duration_hours before step transition: {name}",
                step=name,
                deadline_epoch=state.deadline_epoch,
                elapsed_seconds=time.time() - state.started_at_epoch,
            )
        if should_cancel and should_cancel():
            raise PipelineCancelledError(
                f"Pipeline cancelled before step transition: {name}",
                step=name,
            )

    def raise_if_cancelled_for_report(step: int, name: str) -> None:
        if should_cancel and should_cancel():
            raise PipelineCancelledError(
                f"Pipeline cancelled before step transition: {name}",
                step=name,
            )

    def save_checkpoint(step: int) -> None:
        state.completed_step = max(getattr(state, "completed_step", 0), step)
        if getattr(state, "compound", None) is not None:
            evidence_snapshot = build_runtime_evidence_snapshot_fn(
                compound=state.compound,
                analyses=state.analyses,
                doe_assessments=state.doe_assessments,
                invalidity_assessments=state.invalidity_assessments,
                analysis_failures=state.analysis_failures,
                patent_hits=state.patent_hits,
                prosecution_cache=state.prosecution_cache,
                source_health=state.source_health,
                verification=state.verification,
                critic_report=state.critic_report,
                search_loop_result=state.search_loop_result,
                settings=state.settings,
                existing_collector_runs=state.collector_runs,
            )
            state.matter_graph = evidence_snapshot.matter_graph
            state.matter_graph_summary = evidence_snapshot.matter_graph_summary
            state.matter_store = evidence_snapshot.matter_store
            state.evidence_artifacts = evidence_snapshot.evidence_artifacts
            state.evidence_adapter_results = evidence_snapshot.evidence_adapter_results
            state.collector_runs = evidence_snapshot.collector_runs
        save_runtime_checkpoint_fn(
            integrity_keys=state.checkpoint_integrity_keys,
            checkpoint_enabled=state.settings.checkpoint_enabled,
            checkpoint_dir=state.checkpoint_dir,
            run_id=state.run_id,
            completed_step=step,
            compound_input=state.user_input,
            execution_profile=state.execution_profile,
            analysis_escalation_reasons=state.analysis_escalation_reasons,
            started_at_epoch=state.started_at_epoch,
            deadline_epoch=state.deadline_epoch,
            compound=state.compound,
            expanded_queries=state.expanded_queries,
            patent_hits=state.patent_hits,
            source_health=state.source_health,
            search_funnel=state.search_funnel,
            matter_graph=getattr(state, "matter_graph", None),
            matter_graph_summary=getattr(state, "matter_graph_summary", None),
            matter_store=getattr(state, "matter_store", None),
            evidence_artifacts=getattr(state, "evidence_artifacts", None),
            evidence_adapter_results=getattr(state, "evidence_adapter_results", None),
            collector_runs=getattr(state, "collector_runs", None),
            drawing_evidence=state.drawing_evidence,
            triage_results=state.triage_results,
            all_triage_results=state.all_triage,
            triage_input_tokens=state.triage_in,
            triage_output_tokens=state.triage_out,
            triage_failed=state.triage_failed,
            analyses=state.analyses,
            analysis_failures=state.analysis_failures,
            prosecution_cache=state.prosecution_cache,
            reasoning_traces=state.reasoning_traces,
            critic_report=state.critic_report,
            critic_input_tokens=state.critic_in,
            critic_output_tokens=state.critic_out,
            search_loop_result=state.search_loop_result,
            doe_assessments=state.doe_assessments,
            doe_input_tokens=state.doe_in,
            doe_output_tokens=state.doe_out,
            invalidity_assessments=state.invalidity_assessments,
            inv_input_tokens=state.inv_in,
            inv_output_tokens=state.inv_out,
            verification=state.verification,
            regulatory_exclusivity=getattr(state, "regulatory_exclusivity", None),
            timing_data=state.timing_data,
        )

    return RunLifecycleAdapters(
        notify=notify,
        raise_if_cancelled=raise_if_cancelled,
        raise_if_cancelled_for_report=raise_if_cancelled_for_report,
        save_checkpoint=save_checkpoint,
        make_timing=build_step_timing,
    )


def build_runtime_budget_termination(
    *,
    state,
    exc: RuntimeBudgetExceededError,
) -> RuntimeTerminationInfo:
    """Build the report-facing runtime termination summary for timed-out runs."""
    return RuntimeTerminationInfo(
        reason="runtime_budget_exceeded",
        step=exc.step,
        description=(
            f"Run stopped at '{exc.step}' after exceeding the configured runtime budget "
            f"of {state.settings.max_run_duration_hours} hour(s)."
        ),
        impact=(
            "The matter record is incomplete and cannot support a clearance-grade conclusion "
            "until the run is resumed or rerun to completion."
        ),
        action_description=(
            "Resume or rerun this matter to complete the missing evidence collection "
            "and legal review."
        ),
        action_reasoning=(
            "The configured runtime budget expired before the pipeline completed "
            "all required stages."
        ),
    )
