"""Runtime evidence snapshot helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.pipeline.runtime.matter_graph_snapshot import (
    RuntimeEvidenceSnapshot,
    assemble_runtime_evidence_snapshot,
    prepare_runtime_snapshot_inputs,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import (
        EvidenceCollectorRun,
        MatterGraph,
        MatterGraphSummary,
    )


def build_runtime_evidence_snapshot(
    *,
    compound,
    analyses: list | None,
    doe_assessments: list | None,
    invalidity_assessments: list | None,
    analysis_failures: list | None,
    patent_hits: list | None,
    prosecution_cache: dict[str, dict[str, object]] | None,
    source_health,
    verification=None,
    critic_report=None,
    search_loop_result=None,
    data_limitations: list | None = None,
    settings=None,
    existing_collector_runs: list[EvidenceCollectorRun] | None = None,
) -> RuntimeEvidenceSnapshot:
    """Build the best-available evidence substrate from live runtime state."""
    if compound is None:
        return RuntimeEvidenceSnapshot()

    analyses = analyses or []
    doe_assessments = doe_assessments or []
    invalidity_assessments = invalidity_assessments or []
    analysis_failures = analysis_failures or []
    patent_hits = patent_hits or []
    prepared = prepare_runtime_snapshot_inputs(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache or {},
        source_health=source_health,
        verification=verification,
        critic_report=critic_report,
        search_loop_result=search_loop_result,
        data_limitations=data_limitations or [],
        settings=settings,
    )
    return assemble_runtime_evidence_snapshot(
        compound=compound,
        analyses=analyses,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache,
        settings=settings,
        existing_collector_runs=existing_collector_runs,
        prepared=prepared,
    )


def build_runtime_matter_graph_snapshot(
    *,
    compound,
    analyses: list | None,
    doe_assessments: list | None,
    invalidity_assessments: list | None,
    analysis_failures: list | None,
    patent_hits: list | None,
    prosecution_cache: dict[str, dict[str, object]] | None,
    source_health,
    verification=None,
    critic_report=None,
    search_loop_result=None,
    data_limitations: list | None = None,
    existing_collector_runs: list[EvidenceCollectorRun] | None = None,
) -> tuple[MatterGraph, MatterGraphSummary]:
    """Build the best-available matter graph from live runtime state."""
    snapshot = build_runtime_evidence_snapshot(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache,
        source_health=source_health,
        verification=verification,
        critic_report=critic_report,
        search_loop_result=search_loop_result,
        data_limitations=data_limitations,
        existing_collector_runs=existing_collector_runs,
    )
    return snapshot.matter_graph, snapshot.matter_graph_summary
