"""CLI entry point: run full FTO pipeline on a single compound.

Usage:
    praviar-pipeline run "succinic acid"
    praviar-pipeline run "OC(=O)CCC(O)=O"
    praviar-pipeline run "110-15-6"
    praviar-pipeline run "succinic acid" --format markdown
    praviar-pipeline run "succinic acid" --format pdf
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import structlog

from praviar_pipeline.errors import RuntimeBudgetExceededError
from praviar_pipeline.logging_config import (
    bind_compound_context,
    bind_pipeline_context,
    configure_logging,
)
from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.runtime.audit import (
    build_analysis_audit,
    build_pipeline_audit_trail,
    build_prior_step_tokens,
    build_triage_audit,
    map_relevant_patents,
)
from praviar_pipeline.pipeline.runtime.checkpoints import (
    restore_runtime_state,
    save_runtime_checkpoint,
)
from praviar_pipeline.pipeline.runtime.cli_args import (
    emit_json_report,
    parse_run_args,
    print_usage,
)
from praviar_pipeline.pipeline.runtime.cli_runner import (
    exit_cli,
    reanalyze_failed_impl,
)
from praviar_pipeline.pipeline.runtime.config import apply_analysis_config_overrides
from praviar_pipeline.pipeline.runtime.database import (
    sync_pipeline_to_database as _sync_to_database,
)
from praviar_pipeline.pipeline.runtime.flow import bootstrap_run_context, finalize_report_output
from praviar_pipeline.pipeline.runtime.matter_graph_state import build_runtime_evidence_snapshot
from praviar_pipeline.pipeline.runtime.output import write_pipeline_outputs
from praviar_pipeline.pipeline.runtime.reanalysis import (
    load_reanalysis_context,
    merge_reanalysis_results,
    select_failed_patents,
    write_reanalysis_checkpoint,
)
from praviar_pipeline.pipeline.runtime.run_execution import (
    RunCallbacks,
    execute_analysis_to_verification_flow,
    execute_resolution_to_search_flow,
)
from praviar_pipeline.pipeline.runtime.run_lifecycle import (
    build_run_lifecycle_adapters,
    build_runtime_budget_termination,
)
from praviar_pipeline.pipeline.step4_analyze import analyze_patents
from praviar_pipeline.pipeline.step8_report import generate_report

logger = structlog.get_logger()


# Type for optional progress callback: (step_num, step_name, event_type, payload) -> None
ProgressCallback = Callable[[int, str, str, dict], None] | None
CancellationCheck = Callable[[], bool] | None


async def run_pipeline(
    user_input: str,
    output_format: str = "json",
    on_progress: ProgressCallback = None,
    should_cancel: CancellationCheck = None,
    resume_from: str | None = None,
    config_overrides: dict | None = None,
    checkpoint_decision_provider=None,
) -> dict:
    """Run the full 8-step FTO pipeline and return the report as a dict.

    Args:
        user_input: Compound name, SMILES, InChI, or CAS number.
        output_format: Output format ("json", "markdown", "pdf").
        on_progress: Optional callback for step progress updates.
            Called with (step_num, step_name, event_type, payload).
        resume_from: Path to checkpoint directory to resume from.
        config_overrides: Per-analysis config from the API (search_jurisdictions,
            enable_bigquery, etc.). Applied on top of global settings.
    """
    from praviar_pipeline.config import get_settings, runtime_settings_context

    state = bootstrap_run_context(
        user_input=user_input,
        resume_from=resume_from,
        config_overrides=config_overrides,
        get_settings_fn=get_settings,
        apply_analysis_config_overrides_fn=apply_analysis_config_overrides,
        bind_pipeline_context_fn=bind_pipeline_context,
        bind_compound_context_fn=bind_compound_context,
        restore_runtime_state_fn=restore_runtime_state,
        logger=logger,
    )
    with runtime_settings_context(state.settings):
        return await _execute_pipeline_state(
            state=state,
            user_input=user_input,
            output_format=output_format,
            on_progress=on_progress,
            should_cancel=should_cancel,
            checkpoint_decision_provider=checkpoint_decision_provider,
        )


async def _execute_pipeline_state(
    *,
    state,
    user_input: str,
    output_format: str,
    on_progress: ProgressCallback,
    should_cancel: CancellationCheck,
    checkpoint_decision_provider,
) -> dict:
    """Execute one bootstrapped run inside its task-local settings context."""
    pipeline_start = state.started_at_epoch
    adapters = build_run_lifecycle_adapters(
        state=state,
        on_progress=on_progress,
        should_cancel=should_cancel,
        build_runtime_evidence_snapshot_fn=build_runtime_evidence_snapshot,
        save_runtime_checkpoint_fn=save_runtime_checkpoint,
    )

    logger.info(
        "pipeline_start",
        output_format=output_format,
        execution_profile=state.execution_profile,
    )

    callbacks = RunCallbacks(
        notify=adapters.notify,
        raise_if_cancelled=adapters.raise_if_cancelled,
        save_checkpoint=adapters.save_checkpoint,
        make_timing=adapters.make_timing,
        checkpoint_decision_provider=checkpoint_decision_provider,
    )
    triage_audit = []
    analysis_audit = []
    runtime_termination = None

    try:
        await execute_resolution_to_search_flow(state=state, callbacks=callbacks)
        triage_audit, analysis_audit = await execute_analysis_to_verification_flow(
            state=state,
            callbacks=callbacks,
        )
    except RuntimeBudgetExceededError as exc:
        if state.compound is None:
            raise
        logger.warning(
            "pipeline_runtime_budget_exceeded",
            step=exc.step,
            deadline_epoch=exc.deadline_epoch,
            elapsed_seconds=exc.elapsed_seconds,
        )
        triage_audit = build_triage_audit(state.all_triage, state.triage_results)
        analysis_audit = build_analysis_audit(
            map_relevant_patents(state.patent_hits, state.triage_results),
            state.analyses,
        )
        runtime_termination = build_runtime_budget_termination(state=state, exc=exc)

    return await finalize_report_output(
        settings=state.settings,
        compound=state.compound,
        analyses=state.analyses,
        doe_assessments=state.doe_assessments,
        invalidity_assessments=state.invalidity_assessments,
        verification=state.verification or VerificationResult(),
        patent_hits=state.patent_hits,
        source_health=state.source_health or SourceHealth(entries=[]),
        analysis_failures=state.analysis_failures,
        prosecution_cache=state.prosecution_cache,
        critic_report=state.critic_report,
        drawing_evidence=state.drawing_evidence,
        timing_data=state.timing_data,
        execution_profile=state.execution_profile,
        reasoning_traces=state.reasoning_traces,
        triage_audit=triage_audit,
        analysis_audit=analysis_audit,
        search_funnel=state.search_funnel,
        expanded_queries=state.expanded_queries,
        triage_results=state.triage_results,
        triage_in=state.triage_in,
        triage_out=state.triage_out,
        critic_in=state.critic_in,
        critic_out=state.critic_out,
        search_loop_result=state.search_loop_result,
        doe_in=state.doe_in,
        doe_out=state.doe_out,
        inv_in=state.inv_in,
        inv_out=state.inv_out,
        audit_trail_builder=build_pipeline_audit_trail,
        prior_step_tokens_builder=build_prior_step_tokens,
        generate_report_fn=generate_report,
        write_pipeline_outputs_fn=write_pipeline_outputs,
        notify_fn=adapters.notify,
        raise_if_cancelled_fn=(
            adapters.raise_if_cancelled_for_report
            if runtime_termination
            else adapters.raise_if_cancelled
        ),
        save_checkpoint_fn=adapters.save_checkpoint,
        make_timing_fn=adapters.make_timing,
        checkpoint_decision_provider=checkpoint_decision_provider,
        pipeline_start=pipeline_start,
        output_format=output_format,
        logger=logger,
        matter_graph=getattr(state, "matter_graph", None),
        matter_graph_summary=getattr(state, "matter_graph_summary", None),
        matter_store=getattr(state, "matter_store", None),
        evidence_artifacts=getattr(state, "evidence_artifacts", None),
        evidence_adapter_results=getattr(state, "evidence_adapter_results", None),
        collector_runs=getattr(state, "collector_runs", None),
        runtime_termination=runtime_termination,
        regulatory_exclusivity=getattr(state, "regulatory_exclusivity", None),
        user_input=user_input,
        run_id=state.run_id,
    )


async def reanalyze_failed(
    checkpoint_dir_path: str,
) -> dict:
    """Re-run analysis on patents that failed in a previous run."""
    from praviar_pipeline.config import get_settings

    return await reanalyze_failed_impl(
        checkpoint_dir_path,
        load_reanalysis_context_fn=load_reanalysis_context,
        select_failed_patents_fn=select_failed_patents,
        analyze_patents_fn=analyze_patents,
        merge_reanalysis_results_fn=merge_reanalysis_results,
        write_reanalysis_checkpoint_fn=write_reanalysis_checkpoint,
        run_pipeline_fn=run_pipeline,
        logger=logger,
        checkpoint_integrity_keys=get_settings().checkpoint_integrity_keys,
    )


def main():
    exit_cli(
        sys.argv,
        parse_run_args_fn=parse_run_args,
        print_usage_fn=print_usage,
        configure_logging_fn=configure_logging,
        reanalyze_failed_fn=reanalyze_failed,
        run_pipeline_fn=run_pipeline,
        sync_to_database_fn=_sync_to_database,
        emit_json_report_fn=emit_json_report,
    )


if __name__ == "__main__":
    main()
