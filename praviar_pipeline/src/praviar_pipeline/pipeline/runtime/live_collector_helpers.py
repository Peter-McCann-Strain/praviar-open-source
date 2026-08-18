"""Shared helper primitives for runtime live collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.utils.safe_diagnostics import safe_failure_message

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import EvidenceCollectorRun


@dataclass(slots=True)
class LiveCollectorAttemptRecord:
    collector_name: str
    status: SourceStatus
    patent_count: int = 0
    target_patent_ids: list[str] = field(default_factory=list)
    covered_patent_ids: list[str] = field(default_factory=list)
    missing_patent_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_before_clear: bool = False
    freshness_note: str = ""
    summary: str = ""


@dataclass(slots=True)
class LiveCollectorExecutionResult:
    source_health: SourceHealth
    prosecution_cache: dict[str, dict[str, object]] = field(default_factory=dict)
    executed_collectors: list[str] = field(default_factory=list)
    collector_runs: list[EvidenceCollectorRun] = field(default_factory=list)

    @property
    def executed(self) -> bool:
        return bool(self.executed_collectors)


def merge_source_health_entries(
    source_health: SourceHealth | None,
    entries: list[SourceHealthEntry],
) -> SourceHealth:
    merged_entries = list(getattr(source_health, "entries", []) or [])
    index_by_source = {entry.source: idx for idx, entry in enumerate(merged_entries)}
    for entry in entries:
        idx = index_by_source.get(entry.source)
        if idx is None:
            index_by_source[entry.source] = len(merged_entries)
            merged_entries.append(entry)
        else:
            merged_entries[idx] = entry
    return SourceHealth(entries=merged_entries)


def patent_subset(hits: list[PatentHit], patent_ids: list[str]) -> list[PatentHit]:
    target_ids = set(unique_strings(patent_ids))
    if not target_ids:
        return []
    return [hit for hit in hits if hit.patent_id in target_ids]


def directive_targets_by_adapter(directives: list[object]) -> dict[str, list[str]]:
    targets: dict[str, list[str]] = {}
    for directive in directives:
        target_patent_ids = list(getattr(directive, "target_patent_ids", []) or [])
        if not target_patent_ids:
            continue
        for adapter_name in list(getattr(directive, "recommended_adapters", []) or []):
            targets.setdefault(adapter_name, [])
            targets[adapter_name].extend(target_patent_ids)
    return {name: unique_strings(ids) for name, ids in targets.items()}


def skip_entry(source: str, reason: str) -> SourceHealthEntry:
    return SourceHealthEntry(
        source=source,
        status=SourceStatus.SKIPPED,
        patent_count=0,
        error_message=reason,
    )


def ok_entry(
    source: str,
    patent_count: int,
    *,
    attempted_count: int | None = None,
    covered_count: int | None = None,
) -> SourceHealthEntry:
    attempted = patent_count if attempted_count is None else attempted_count
    covered = patent_count if covered_count is None else covered_count
    return SourceHealthEntry(
        source=source,
        status=SourceStatus.OK,
        patent_count=patent_count,
        attempted_count=attempted,
        covered_count=covered,
        error_message="",
    )


def failed_entry(
    source: str,
    error: Exception,
    *,
    attempted_count: int = 0,
    covered_count: int = 0,
) -> SourceHealthEntry:
    return SourceHealthEntry(
        source=source,
        status=SourceStatus.FAILED,
        patent_count=0,
        attempted_count=attempted_count,
        covered_count=covered_count,
        error_message=safe_failure_message("live collector", error),
    )


def not_configured_error_entry(source: str, error: Exception) -> SourceHealthEntry:
    return SourceHealthEntry(
        source=source,
        status=SourceStatus.NOT_CONFIGURED,
        patent_count=0,
        error_message=safe_failure_message("live collector configuration", error),
    )


def not_configured_entry(source: str, reason: str = "") -> SourceHealthEntry:
    return SourceHealthEntry(
        source=source,
        status=SourceStatus.NOT_CONFIGURED,
        patent_count=0,
        error_message=reason,
    )
