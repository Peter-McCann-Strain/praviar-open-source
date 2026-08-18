"""Execution helpers for runtime live collector orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.runtime.live_collector_attempts import (
    covered_patent_ids_if_count_satisfied,
    covered_patent_ids_if_ok,
)
from praviar_pipeline.pipeline.runtime.live_collector_context import (
    collect_counting_enrichment_runtime,
)
from praviar_pipeline.pipeline.runtime.live_collector_helpers import (
    LiveCollectorAttemptRecord,
    patent_subset,
)
from praviar_pipeline.pipeline.search.enrichment import EnrichmentOutcome

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit

AttemptRecordFn = Callable[..., LiveCollectorAttemptRecord]
ClaimCollectorFn = Callable[
    [list["PatentHit"]],
    Awaitable[tuple[SourceHealthEntry, list[str]]],
]
FamilyCollectorFn = Callable[..., Awaitable[SourceHealthEntry]]
UsptoCollectorFn = Callable[
    ...,
    Awaitable[tuple[SourceHealthEntry, dict[str, dict[str, object]]]],
]
CountingCollectorFn = Callable[..., Awaitable[EnrichmentOutcome]]

REQUIRED_AUTHORITATIVE_CLAIM_COLLECTORS = {"patentsview", "epo_search"}


def _raise_missing_config(source: str, reason: str) -> None:
    raise ConfigurationError(reason, source=source, step="evidence_collection")


def _required_adapters(directives: list[object]) -> set[str]:
    adapters: set[str] = set()
    for directive in directives:
        if not getattr(directive, "required_before_clear", False):
            continue
        adapters.update(str(adapter) for adapter in getattr(directive, "recommended_adapters", []))
    return adapters


def raise_required_authoritative_claim_collector_failures(
    *,
    entries: list[SourceHealthEntry],
    directives: list[object],
) -> None:
    """Raise when required authoritative claim collectors produced failed health."""
    required_adapters = _required_adapters(directives)
    required_sources = required_adapters.intersection(REQUIRED_AUTHORITATIVE_CLAIM_COLLECTORS)
    failures = [
        entry
        for entry in entries
        if entry.source in required_sources and entry.status == SourceStatus.FAILED
    ]
    if not failures:
        return

    detail = "; ".join(
        f"{entry.source}: {entry.error_message or entry.status.value}" for entry in failures
    )
    source = failures[0].source if len(failures) == 1 else "evidence_collection"
    raise SourceUnavailableError(
        source,
        f"Required authoritative claim collector failed: {detail}",
    )


async def run_claim_collectors(
    *,
    patent_hits: list[PatentHit],
    claim_targets_by_source: dict[str, list[str]],
    settings,
    collect_bigquery_fn: ClaimCollectorFn,
    collect_patentsview_fn: ClaimCollectorFn,
    collect_epo_fn: ClaimCollectorFn,
    build_attempt_record: AttemptRecordFn,
) -> tuple[list[SourceHealthEntry], list[LiveCollectorAttemptRecord], list[str]]:
    bigquery_targets = claim_targets_by_source.get("bigquery", [])
    patentsview_targets = claim_targets_by_source.get("patentsview", [])
    epo_targets = claim_targets_by_source.get("epo_search", [])
    if not bigquery_targets and not patentsview_targets and not epo_targets:
        return [], [], []

    health_updates: list[SourceHealthEntry] = []
    attempt_updates: list[LiveCollectorAttemptRecord] = []
    executed_collectors: list[str] = []

    if bigquery_targets:
        bigquery_entry, bigquery_covered = await collect_bigquery_fn(
            patent_subset(patent_hits, bigquery_targets)
        )
        health_updates.append(bigquery_entry)
        attempt_updates.append(
            build_attempt_record(
                source="bigquery",
                entry=bigquery_entry,
                target_patent_ids=bigquery_targets,
                covered_patent_ids=bigquery_covered,
            )
        )
        executed_collectors.append("bigquery")

    if patentsview_targets:
        if not getattr(settings, "patentsview_api_key", ""):
            _raise_missing_config(
                "patentsview",
                "PatentsView API key not configured",
            )
        patentsview_entry, patentsview_covered = await collect_patentsview_fn(
            patent_subset(patent_hits, patentsview_targets)
        )
        health_updates.append(patentsview_entry)
        attempt_updates.append(
            build_attempt_record(
                source="patentsview",
                entry=patentsview_entry,
                target_patent_ids=patentsview_targets,
                covered_patent_ids=patentsview_covered,
            )
        )
        executed_collectors.append("patentsview")

    if epo_targets:
        if not (
            getattr(settings, "ops_consumer_key", "")
            and getattr(settings, "ops_consumer_secret", "")
        ):
            _raise_missing_config("epo_search", "EPO OPS credentials not configured")
        epo_entry, epo_covered = await collect_epo_fn(patent_subset(patent_hits, epo_targets))
        health_updates.append(epo_entry)
        attempt_updates.append(
            build_attempt_record(
                source="epo_search",
                entry=epo_entry,
                target_patent_ids=epo_targets,
                covered_patent_ids=epo_covered,
            )
        )
        executed_collectors.append("epo_search")

    return health_updates, attempt_updates, executed_collectors


async def run_family_collector(
    *,
    family_targets: list[PatentHit],
    expand_families_fn,
    collect_family_context_fn: FamilyCollectorFn,
    build_attempt_record: AttemptRecordFn,
) -> tuple[list[SourceHealthEntry], list[LiveCollectorAttemptRecord], list[str]]:
    if not family_targets:
        return [], [], []

    family_entry = await collect_family_context_fn(
        patent_hits=family_targets,
        expand_families_fn=expand_families_fn,
    )
    target_patent_ids = [hit.patent_id for hit in family_targets]
    return (
        [family_entry],
        [
            build_attempt_record(
                source="family_record",
                entry=family_entry,
                target_patent_ids=target_patent_ids,
                covered_patent_ids=covered_patent_ids_if_ok(
                    target_patent_ids,
                    family_entry,
                ),
            )
        ],
        ["family_record"],
    )


async def run_uspto_runtime_collector(
    *,
    uspto_targets: list[str],
    prosecution_cache: dict[str, dict[str, object]],
    settings,
    collect_uspto_fn: UsptoCollectorFn,
    fetch_prosecution_context_fn,
    build_attempt_record: AttemptRecordFn,
) -> tuple[
    list[SourceHealthEntry],
    list[LiveCollectorAttemptRecord],
    list[str],
    dict[str, dict[str, object]],
]:
    updated_cache = dict(prosecution_cache)
    if not uspto_targets:
        return [], [], [], updated_cache

    if not getattr(settings, "uspto_odp_api_key", ""):
        _raise_missing_config("uspto_odp", "USPTO ODP API key not configured")

    uspto_entry, updated_cache = await collect_uspto_fn(
        patent_ids=uspto_targets,
        prosecution_cache=updated_cache,
        fetch_prosecution_context_fn=fetch_prosecution_context_fn,
    )
    covered_patent_ids = [patent_id for patent_id in uspto_targets if updated_cache.get(patent_id)]
    return (
        [uspto_entry],
        [
            build_attempt_record(
                source="uspto_odp",
                entry=uspto_entry,
                target_patent_ids=uspto_targets,
                covered_patent_ids=covered_patent_ids,
            )
        ],
        ["uspto_odp"],
        updated_cache,
    )


async def run_counting_collector(
    *,
    source: str,
    patent_hits: list[PatentHit],
    collector_fn: CountingCollectorFn,
    build_attempt_record: AttemptRecordFn,
    enabled: bool = True,
    disabled_reason: str | None = None,
) -> tuple[list[SourceHealthEntry], list[LiveCollectorAttemptRecord], list[str]]:
    if not patent_hits:
        return [], [], []

    target_patent_ids = [hit.patent_id for hit in patent_hits]
    if not enabled:
        _raise_missing_config(source, disabled_reason or "Collector unavailable")

    entry = await collect_counting_enrichment_runtime(
        source=source,
        patent_hits=patent_hits,
        collector_fn=collector_fn,
    )
    return (
        [entry],
        [
            build_attempt_record(
                source=source,
                entry=entry,
                target_patent_ids=target_patent_ids,
                covered_patent_ids=covered_patent_ids_if_count_satisfied(
                    target_patent_ids,
                    entry,
                ),
            )
        ],
        [source],
    )
