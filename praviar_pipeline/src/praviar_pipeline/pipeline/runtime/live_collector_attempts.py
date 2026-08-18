"""Helpers for shaping runtime live collector attempt records."""

from __future__ import annotations

from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.runtime.evidence_artifacts import adapter_definition_for
from praviar_pipeline.pipeline.runtime.live_collector_helpers import LiveCollectorAttemptRecord


def required_before_clear(directives: list[object], adapter_name: str) -> bool:
    return any(
        adapter_name in list(getattr(directive, "recommended_adapters", []) or [])
        and bool(getattr(directive, "required_before_clear", False))
        for directive in directives
    )


def covered_patent_ids_if_ok(
    target_patent_ids: list[str],
    entry: SourceHealthEntry,
) -> list[str]:
    targets = unique_strings(list(target_patent_ids))
    if entry.status == SourceStatus.OK:
        return targets
    return []


def covered_patent_ids_if_count_satisfied(
    target_patent_ids: list[str],
    entry: SourceHealthEntry,
) -> list[str]:
    targets = unique_strings(list(target_patent_ids))
    if entry.status == SourceStatus.OK and entry.covered_count >= len(targets):
        return targets
    return []


def build_live_collector_attempt(
    *,
    directives: list[object],
    source: str,
    entry: SourceHealthEntry,
    target_patent_ids: list[str],
    covered_patent_ids: list[str] | None = None,
    summary: str | None = None,
) -> LiveCollectorAttemptRecord:
    covered = unique_strings(list(covered_patent_ids or []))
    targets = unique_strings(list(target_patent_ids))
    missing = [patent_id for patent_id in targets if patent_id not in covered]
    if summary is None:
        if entry.status == SourceStatus.FAILED:
            summary_text = (
                f"Collector attempt failed: {entry.error_message}"
                if entry.error_message
                else "Collector attempt failed."
            )
        elif entry.status == SourceStatus.SKIPPED:
            summary_text = entry.error_message or "Collector attempt was skipped."
        elif covered and missing:
            summary_text = "Collector covered some targeted records but left material gaps."
        elif missing:
            summary_text = "Collector ran but did not satisfy the targeted records."
        else:
            summary_text = "Collector satisfied the targeted matter records."
    else:
        summary_text = summary

    definition = adapter_definition_for(source)
    warnings = [entry.error_message] if entry.error_message else []
    return LiveCollectorAttemptRecord(
        collector_name=source,
        status=entry.status,
        patent_count=entry.patent_count,
        target_patent_ids=targets,
        covered_patent_ids=covered,
        missing_patent_ids=missing,
        warnings=warnings,
        required_before_clear=required_before_clear(directives, source),
        freshness_note=definition.freshness_note,
        summary=summary_text,
    )
