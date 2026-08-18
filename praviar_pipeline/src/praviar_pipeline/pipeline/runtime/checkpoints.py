"""Checkpoint helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from praviar_pipeline.checkpoint import (
    build_checkpoint,
    load_latest_checkpoint,
    restore_from_checkpoint,
    save_checkpoint,
)


@dataclass(slots=True)
class RuntimeCheckpointState:
    completed_step: int = 0
    run_id: str = ""
    compound_input: str = ""
    execution_profile: str = "world_class_adaptive"
    analysis_escalation_reasons: list[str] = field(default_factory=list)
    started_at_epoch: float = 0.0
    deadline_epoch: float | None = None
    compound: Any = None
    expanded_queries: Any = None
    patent_hits: list = field(default_factory=list)
    source_health: Any = None
    search_funnel: list = field(default_factory=list)
    matter_graph: Any = None
    matter_graph_summary: Any = None
    matter_store: Any = None
    evidence_artifacts: list = field(default_factory=list)
    evidence_adapter_results: list = field(default_factory=list)
    collector_runs: list = field(default_factory=list)
    drawing_evidence: Any = None
    triage_results: list = field(default_factory=list)
    all_triage_results: list = field(default_factory=list)
    triage_input_tokens: int = 0
    triage_output_tokens: int = 0
    triage_failed: int = 0
    analyses: list = field(default_factory=list)
    analysis_failures: list = field(default_factory=list)
    prosecution_cache: dict[str, dict[str, object]] = field(default_factory=dict)
    reasoning_traces: list = field(default_factory=list)
    critic_report: Any = None
    critic_input_tokens: int = 0
    critic_output_tokens: int = 0
    search_loop_result: Any = None
    doe_assessments: list = field(default_factory=list)
    doe_input_tokens: int = 0
    doe_output_tokens: int = 0
    invalidity_assessments: list = field(default_factory=list)
    inv_input_tokens: int = 0
    inv_output_tokens: int = 0
    verification: Any = None
    regulatory_exclusivity: Any = None
    timing_data: list = field(default_factory=list)


def restore_runtime_state(
    resume_from: str | None,
    *,
    integrity_keys,
) -> RuntimeCheckpointState | None:
    if not resume_from:
        return None

    checkpoint = load_latest_checkpoint(Path(resume_from), integrity_keys=integrity_keys)
    if checkpoint is None:
        return None

    state = restore_from_checkpoint(checkpoint)
    return RuntimeCheckpointState(
        completed_step=checkpoint.completed_step,
        run_id=checkpoint.run_id,
        compound_input=checkpoint.compound_input,
        execution_profile=checkpoint.execution_profile,
        analysis_escalation_reasons=list(checkpoint.analysis_escalation_reasons),
        started_at_epoch=checkpoint.started_at_epoch,
        deadline_epoch=checkpoint.deadline_epoch,
        compound=state["compound"],
        expanded_queries=state["expanded_queries"],
        patent_hits=state["patent_hits"] or [],
        source_health=state["source_health"],
        search_funnel=state["search_funnel"] or [],
        matter_graph=state.get("matter_graph"),
        matter_graph_summary=state.get("matter_graph_summary"),
        matter_store=state.get("matter_store"),
        evidence_artifacts=state.get("evidence_artifacts") or [],
        evidence_adapter_results=state.get("evidence_adapter_results") or [],
        collector_runs=state.get("collector_runs") or [],
        drawing_evidence=state.get("drawing_results"),
        triage_results=state["triage_results"] or [],
        all_triage_results=state.get("all_triage_results") or [],
        triage_input_tokens=state["triage_input_tokens"],
        triage_output_tokens=state["triage_output_tokens"],
        triage_failed=state["triage_failed"],
        analyses=state["analyses"] or [],
        analysis_failures=state["analysis_failures"] or [],
        prosecution_cache=state.get("prosecution_cache") or {},
        reasoning_traces=state["reasoning_traces"] or [],
        critic_report=state.get("critic_report"),
        critic_input_tokens=state.get("critic_input_tokens", 0),
        critic_output_tokens=state.get("critic_output_tokens", 0),
        search_loop_result=state.get("search_loop_result"),
        doe_assessments=state["doe_assessments"] or [],
        doe_input_tokens=state["doe_input_tokens"],
        doe_output_tokens=state["doe_output_tokens"],
        invalidity_assessments=state["invalidity_assessments"] or [],
        inv_input_tokens=state["inv_input_tokens"],
        inv_output_tokens=state["inv_output_tokens"],
        verification=state["verification"],
        regulatory_exclusivity=state.get("regulatory_exclusivity"),
        timing_data=state["timing_data"] or [],
    )


def save_runtime_checkpoint(
    *,
    checkpoint_enabled: bool,
    checkpoint_dir: Path,
    run_id: str,
    completed_step: int,
    compound_input: str,
    execution_profile: str,
    analysis_escalation_reasons: list[str] | None = None,
    started_at_epoch: float = 0.0,
    deadline_epoch: float | None = None,
    compound: Any = None,
    expanded_queries: Any = None,
    patent_hits: Any = None,
    source_health: Any = None,
    search_funnel: Any = None,
    matter_graph: Any = None,
    matter_graph_summary: Any = None,
    matter_store: Any = None,
    evidence_artifacts: Any = None,
    evidence_adapter_results: Any = None,
    collector_runs: Any = None,
    drawing_evidence: Any = None,
    triage_results: Any = None,
    all_triage_results: Any = None,
    triage_input_tokens: int = 0,
    triage_output_tokens: int = 0,
    triage_failed: int = 0,
    analyses: Any = None,
    analysis_failures: Any = None,
    prosecution_cache: Any = None,
    reasoning_traces: Any = None,
    critic_report: Any = None,
    critic_input_tokens: int = 0,
    critic_output_tokens: int = 0,
    search_loop_result: Any = None,
    doe_assessments: Any = None,
    doe_input_tokens: int = 0,
    doe_output_tokens: int = 0,
    invalidity_assessments: Any = None,
    inv_input_tokens: int = 0,
    inv_output_tokens: int = 0,
    verification: Any = None,
    regulatory_exclusivity: Any = None,
    timing_data: Any = None,
    integrity_keys=None,
) -> None:
    if not checkpoint_enabled:
        return

    checkpoint = build_checkpoint(
        run_id=run_id,
        completed_step=completed_step,
        compound_input=compound_input,
        execution_profile=execution_profile,
        analysis_escalation_reasons=analysis_escalation_reasons or [],
        started_at_epoch=started_at_epoch,
        deadline_epoch=deadline_epoch,
        compound=compound,
        expanded_queries=expanded_queries,
        patent_hits=patent_hits,
        source_health=source_health,
        search_funnel=search_funnel,
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_store=matter_store,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        drawing_results=drawing_evidence,
        triage_results=triage_results,
        all_triage_results=all_triage_results,
        triage_input_tokens=triage_input_tokens,
        triage_output_tokens=triage_output_tokens,
        triage_failed=triage_failed,
        analyses=analyses,
        analysis_failures=analysis_failures,
        prosecution_cache=prosecution_cache,
        reasoning_traces=reasoning_traces,
        critic_report=critic_report,
        critic_input_tokens=critic_input_tokens,
        critic_output_tokens=critic_output_tokens,
        search_loop_result=search_loop_result,
        doe_assessments=doe_assessments,
        doe_input_tokens=doe_input_tokens,
        doe_output_tokens=doe_output_tokens,
        invalidity_assessments=invalidity_assessments,
        inv_input_tokens=inv_input_tokens,
        inv_output_tokens=inv_output_tokens,
        verification=verification,
        regulatory_exclusivity=regulatory_exclusivity,
        timing_data=timing_data,
    )
    if integrity_keys is None:
        raise ValueError("pipeline checkpoint integrity key is required")
    save_checkpoint(checkpoint, checkpoint_dir, integrity_keys=integrity_keys)
