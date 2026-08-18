"""Execute deterministic authoritative collectors against unresolved runtime gaps."""

from __future__ import annotations

import time
from functools import partial
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.pipeline.analysis.prosecution import fetch_prosecution_context_impl
from praviar_pipeline.pipeline.runtime.evidence_collectors import record_live_collector_attempts
from praviar_pipeline.pipeline.runtime.live_collector_attempts import build_live_collector_attempt
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    collect_claims_from_bigquery_impl,
    collect_claims_from_epo_impl,
    collect_claims_from_patentsview_impl,
)
from praviar_pipeline.pipeline.runtime.live_collector_context import (
    collect_family_context_runtime_impl,
    collect_uspto_odp_runtime_context_impl,
)
from praviar_pipeline.pipeline.runtime.live_collector_execution import (
    raise_required_authoritative_claim_collector_failures,
    run_claim_collectors,
    run_counting_collector,
    run_family_collector,
    run_uspto_runtime_collector,
)
from praviar_pipeline.pipeline.runtime.live_collector_helpers import (
    LiveCollectorExecutionResult,
    directive_targets_by_adapter,
    merge_source_health_entries,
    patent_subset,
)
from praviar_pipeline.pipeline.runtime.matter_graph_state import build_runtime_evidence_snapshot
from praviar_pipeline.pipeline.search.enrichment import (
    enrich_epo_register,
    enrich_orange_book,
    enrich_ptab_proceedings,
    expand_families,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import SourceHealthEntry

logger = structlog.get_logger()


async def _collect_claims_from_bigquery(
    patent_hits: list[PatentHit],
) -> tuple[SourceHealthEntry, list[str]]:
    return await collect_claims_from_bigquery_impl(patent_hits)


async def _collect_claims_from_patentsview(
    patent_hits: list[PatentHit],
) -> tuple[SourceHealthEntry, list[str]]:
    return await collect_claims_from_patentsview_impl(patent_hits)


async def _collect_claims_from_epo(
    patent_hits: list[PatentHit],
) -> tuple[SourceHealthEntry, list[str]]:
    return await collect_claims_from_epo_impl(patent_hits)


async def _collect_uspto_odp_runtime_context(
    *,
    patent_ids: list[str],
    prosecution_cache: dict[str, dict[str, object]],
    fetch_prosecution_context_fn,
) -> tuple[SourceHealthEntry, dict[str, dict[str, object]]]:
    return await collect_uspto_odp_runtime_context_impl(
        patent_ids=patent_ids,
        prosecution_cache=prosecution_cache,
        fetch_prosecution_context_fn=fetch_prosecution_context_fn,
    )


async def _collect_family_context_runtime(
    *,
    patent_hits: list[PatentHit],
    expand_families_fn,
) -> SourceHealthEntry:
    return await collect_family_context_runtime_impl(
        patent_hits=patent_hits,
        expand_families_fn=expand_families_fn,
    )


async def execute_live_evidence_collectors(
    *,
    compound: ResolvedCompound | None,
    patent_hits: list[PatentHit],
    source_health: SourceHealth | None,
    prosecution_cache: dict[str, dict[str, object]] | None,
    collector_runs: list | None = None,
    settings,
    build_runtime_evidence_snapshot_fn=build_runtime_evidence_snapshot,
    fetch_prosecution_context_fn=fetch_prosecution_context_impl,
    enrich_ptab_proceedings_fn=enrich_ptab_proceedings,
    enrich_epo_register_fn=enrich_epo_register,
    enrich_orange_book_fn=enrich_orange_book,
    expand_families_fn=expand_families,
) -> LiveCollectorExecutionResult:
    """Run authoritative collectors against unresolved record gaps after search enrichment."""
    if compound is None or not patent_hits:
        return LiveCollectorExecutionResult(
            source_health=source_health or SourceHealth(entries=[]),
            prosecution_cache=dict(prosecution_cache or {}),
            collector_runs=list(collector_runs or []),
        )

    t_start = time.perf_counter()
    logger.info(
        "live_evidence_collection_start",
        patent_hits=len(patent_hits),
    )

    snapshot = build_runtime_evidence_snapshot_fn(
        compound=compound,
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache or {},
        source_health=source_health or SourceHealth(entries=[]),
        search_loop_result=None,
        settings=settings,
        existing_collector_runs=collector_runs,
    )
    directives = list(getattr(snapshot.matter_store, "evidence_collection_plan", []) or [])
    if not directives:
        logger.info(
            "live_evidence_collection_skipped",
        )
        return LiveCollectorExecutionResult(
            source_health=source_health or SourceHealth(entries=[]),
            prosecution_cache=dict(prosecution_cache or {}),
            collector_runs=list(getattr(snapshot, "collector_runs", []) or collector_runs or []),
        )

    targets_by_adapter = directive_targets_by_adapter(directives)
    logger.info(
        "live_evidence_collection_targets",
        directives=len(directives),
        bigquery_targets=len(targets_by_adapter.get("bigquery", [])),
        patentsview_targets=len(targets_by_adapter.get("patentsview", [])),
        epo_search_targets=len(targets_by_adapter.get("epo_search", [])),
        family_targets=len(targets_by_adapter.get("family_record", [])),
        uspto_targets=len(targets_by_adapter.get("uspto_odp", [])),
        ptab_targets=len(targets_by_adapter.get("ptab", [])),
        epo_register_targets=len(targets_by_adapter.get("epo_register", [])),
        orange_book_targets=len(targets_by_adapter.get("orange_book", [])),
    )
    attempt_record = partial(build_live_collector_attempt, directives=directives)
    health_updates: list[SourceHealthEntry] = []
    attempt_updates = []
    updated_cache = dict(prosecution_cache or {})
    executed_collectors: list[str] = []

    t0 = time.perf_counter()
    claim_health, claim_attempts, claim_collectors = await run_claim_collectors(
        patent_hits=patent_hits,
        claim_targets_by_source={
            "bigquery": targets_by_adapter.get("bigquery", []),
            "patentsview": targets_by_adapter.get("patentsview", []),
            "epo_search": targets_by_adapter.get("epo_search", []),
        },
        settings=settings,
        collect_bigquery_fn=_collect_claims_from_bigquery,
        collect_patentsview_fn=_collect_claims_from_patentsview,
        collect_epo_fn=_collect_claims_from_epo,
        build_attempt_record=attempt_record,
    )
    logger.info(
        "live_evidence_claims_done",
        collectors=claim_collectors,
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(claim_health)
    attempt_updates.extend(claim_attempts)
    executed_collectors.extend(claim_collectors)
    raise_required_authoritative_claim_collector_failures(
        entries=claim_health,
        directives=directives,
    )

    t0 = time.perf_counter()
    family_targets = patent_subset(patent_hits, targets_by_adapter.get("family_record", []))
    family_health, family_attempts, family_collectors = await run_family_collector(
        family_targets=family_targets,
        expand_families_fn=expand_families_fn,
        collect_family_context_fn=_collect_family_context_runtime,
        build_attempt_record=attempt_record,
    )
    logger.info(
        "live_evidence_family_done",
        target_count=len(family_targets),
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(family_health)
    attempt_updates.extend(family_attempts)
    executed_collectors.extend(family_collectors)

    t0 = time.perf_counter()
    uspto_targets = targets_by_adapter.get("uspto_odp", [])
    (
        uspto_health,
        uspto_attempts,
        uspto_collectors,
        updated_cache,
    ) = await run_uspto_runtime_collector(
        uspto_targets=uspto_targets,
        prosecution_cache=updated_cache,
        settings=settings,
        collect_uspto_fn=_collect_uspto_odp_runtime_context,
        fetch_prosecution_context_fn=fetch_prosecution_context_fn,
        build_attempt_record=attempt_record,
    )
    logger.info(
        "live_evidence_uspto_done",
        target_count=len(uspto_targets),
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(uspto_health)
    attempt_updates.extend(uspto_attempts)
    executed_collectors.extend(uspto_collectors)

    t0 = time.perf_counter()
    ptab_targets = patent_subset(patent_hits, targets_by_adapter.get("ptab", []))
    ptab_health, ptab_attempts, ptab_collectors = await run_counting_collector(
        source="ptab",
        patent_hits=ptab_targets,
        collector_fn=enrich_ptab_proceedings_fn,
        build_attempt_record=attempt_record,
        enabled=bool(getattr(settings, "uspto_odp_api_key", "")),
        disabled_reason="USPTO ODP API key not configured",
    )
    logger.info(
        "live_evidence_ptab_done",
        target_count=len(ptab_targets),
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(ptab_health)
    attempt_updates.extend(ptab_attempts)
    executed_collectors.extend(ptab_collectors)

    t0 = time.perf_counter()
    ep_targets = patent_subset(patent_hits, targets_by_adapter.get("epo_register", []))
    ep_health, ep_attempts, ep_collectors = await run_counting_collector(
        source="epo_register",
        patent_hits=ep_targets,
        collector_fn=enrich_epo_register_fn,
        build_attempt_record=attempt_record,
        enabled=bool(getattr(settings, "ops_consumer_key", ""))
        and bool(getattr(settings, "ops_consumer_secret", "")),
        disabled_reason="EPO OPS credentials not configured",
    )
    logger.info(
        "live_evidence_epo_register_done",
        target_count=len(ep_targets),
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(ep_health)
    attempt_updates.extend(ep_attempts)
    executed_collectors.extend(ep_collectors)

    t0 = time.perf_counter()
    orange_targets = patent_subset(patent_hits, targets_by_adapter.get("orange_book", []))
    orange_health, orange_attempts, orange_collectors = await run_counting_collector(
        source="orange_book",
        patent_hits=orange_targets,
        collector_fn=enrich_orange_book_fn,
        build_attempt_record=attempt_record,
    )
    logger.info(
        "live_evidence_orange_book_done",
        target_count=len(orange_targets),
        elapsed_s=round(time.perf_counter() - t0, 2),
    )
    health_updates.extend(orange_health)
    attempt_updates.extend(orange_attempts)
    executed_collectors.extend(orange_collectors)

    updated_collector_runs = record_live_collector_attempts(
        collector_runs=getattr(snapshot, "collector_runs", []) or collector_runs or [],
        evidence_collection_plan=directives,
        attempt_records=attempt_updates,
    )

    logger.info(
        "live_evidence_collection_done",
        executed_collectors=list(dict.fromkeys(executed_collectors)),
        total_elapsed_s=round(time.perf_counter() - t_start, 2),
    )

    return LiveCollectorExecutionResult(
        source_health=merge_source_health_entries(source_health, health_updates),
        prosecution_cache=updated_cache,
        executed_collectors=list(dict.fromkeys(executed_collectors)),
        collector_runs=updated_collector_runs,
    )
