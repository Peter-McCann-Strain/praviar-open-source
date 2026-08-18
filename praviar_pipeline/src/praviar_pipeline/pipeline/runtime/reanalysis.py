"""Reanalysis helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praviar_pipeline.checkpoint import (
    build_checkpoint,
    load_latest_checkpoint,
    restore_from_checkpoint,
    save_checkpoint,
)


@dataclass(slots=True)
class ReanalysisContext:
    checkpoint: Any
    state: dict[str, Any]
    compound: Any
    patent_hits: list
    analyses: list
    analysis_failures: list
    triage_results: list
    checkpoint_integrity_keys: Any


def load_reanalysis_context(
    checkpoint_dir_path: str,
    *,
    integrity_keys,
) -> ReanalysisContext:
    checkpoint = load_latest_checkpoint(
        Path(checkpoint_dir_path),
        integrity_keys=integrity_keys,
    )
    if checkpoint is None:
        raise FileNotFoundError(f"No checkpoint found in {checkpoint_dir_path}")

    state = restore_from_checkpoint(checkpoint)
    return ReanalysisContext(
        checkpoint=checkpoint,
        state=state,
        compound=state["compound"],
        patent_hits=state["patent_hits"] or [],
        analyses=state["analyses"] or [],
        analysis_failures=state["analysis_failures"] or [],
        triage_results=state["triage_results"] or [],
        checkpoint_integrity_keys=integrity_keys,
    )


def select_failed_patents(patent_hits: list, analysis_failures: list) -> tuple[set[str], list]:
    failed_ids = {failure.patent_id for failure in analysis_failures}
    retry_patents = [patent for patent in patent_hits if patent.patent_id in failed_ids]
    return failed_ids, retry_patents


def merge_reanalysis_results(
    analyses: list,
    analysis_failures: list,
    new_analyses: list,
    new_failures: list,
) -> tuple[list, list]:
    # Deduplicate by patent_id, preferring new_analyses (re-analysis results)
    # over the original analyses. Without dedup, evidence_index dict-comprehensions
    # silently drop the higher-risk original if the re-analysis yields a lower risk,
    # and downstream loops over the merged list double-count the same patent.
    by_id: dict[str, object] = {a.patent_id: a for a in analyses}
    by_id.update({a.patent_id: a for a in new_analyses})
    merged_analyses = list(by_id.values())

    new_analysis_ids = {analysis.patent_id for analysis in new_analyses}
    remaining_failures = [
        failure for failure in analysis_failures if failure.patent_id not in new_analysis_ids
    ]
    return merged_analyses, remaining_failures + new_failures


def write_reanalysis_checkpoint(
    *,
    checkpoint_dir_path: str,
    checkpoint,
    state: dict[str, Any],
    patent_hits: list,
    triage_results: list,
    merged_analyses: list,
    merged_failures: list,
    integrity_keys,
) -> None:
    updated_checkpoint = build_checkpoint(
        run_id=checkpoint.run_id,
        completed_step=8,
        compound_input=checkpoint.compound_input,
        execution_profile=checkpoint.execution_profile,
        analysis_escalation_reasons=list(checkpoint.analysis_escalation_reasons),
        compound=state.get("compound"),
        expanded_queries=state.get("expanded_queries"),
        patent_hits=patent_hits,
        source_health=state.get("source_health"),
        search_funnel=state.get("search_funnel"),
        drawing_results=state.get("drawing_results"),
        triage_results=triage_results,
        all_triage_results=state.get("all_triage_results"),
        triage_input_tokens=state.get("triage_input_tokens", 0),
        triage_output_tokens=state.get("triage_output_tokens", 0),
        triage_failed=state.get("triage_failed", 0),
        analyses=merged_analyses,
        analysis_failures=merged_failures,
        prosecution_cache=state.get("prosecution_cache"),
        reasoning_traces=state.get("reasoning_traces"),
        timing_data=state.get("timing_data"),
    )
    save_checkpoint(
        updated_checkpoint,
        Path(checkpoint_dir_path),
        integrity_keys=integrity_keys,
    )
