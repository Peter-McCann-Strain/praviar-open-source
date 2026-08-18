"""Orchestration helpers for the Step 2 patent search pipeline.

Consolidates what was previously spread across six modules:
  orchestration.py, assembly.py, preparation.py, outcomes.py,
  contributions.py, audit.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.errors import (
    AllSourcesFailedError,
    ConfigurationError,
    PatCIDDatabaseNotFoundError,
    SearchSourceFailedError,
)
from praviar_pipeline.models.audit import (
    SearchFunnelEntry,
    build_search_funnel_entry,
)
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.search.models import (
    PreparedRankingInputs,
    PreparedSearchResults,
    RunSourceFn,
    SearchContributionSummary,
    SearchExecutionSummary,
    SearchRunOutcome,
)
from praviar_pipeline.utils.safe_diagnostics import (
    safe_exception_type,
    safe_failure_message,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit, PatentSource
    from praviar_pipeline.models.search import ExpandedSearchQueries
    from praviar_pipeline.pipeline.search.enrichment import SearchEnrichmentCounts

logger = structlog.get_logger()

OPTIONAL_EXPANDED_SEARCH_SOURCES = frozenset(
    {
        "cpc_search",
        "assignee_search",
        "epo_search",
    }
)

__all__ = [
    "SearchExecutionSummary",
    "assemble_prepared_search_results",
    "build_search_contribution_summary",
    "emit_search_completion_logs",
    "execute_search_coordinator",
    "execute_search_plan",
    "finalize_search_run",
    "maybe_expand_via_citations",
    "partition_source_outcomes",
    "prepare_ranked_search_inputs",
    "prepare_search_results",
    "run_source",
]

# ---------------------------------------------------------------------------
# outcomes -- source-outcome partitioning
# ---------------------------------------------------------------------------


def _status_for_error(error: Exception) -> SourceStatus:
    if isinstance(error, (ConfigurationError, PatCIDDatabaseNotFoundError)):
        return SourceStatus.NOT_CONFIGURED
    return SourceStatus.FAILED


def partition_source_outcomes(
    outcomes: list[tuple[str, Any | None, Exception | None, int]],
) -> SearchExecutionSummary:
    entries: list[SourceHealthEntry] = []
    summary = SearchExecutionSummary()

    for name, result, error, elapsed_ms in outcomes:
        summary.source_timings[name] = elapsed_ms
        if error is not None:
            diagnostic = safe_failure_message("source search", error)
            entries.append(
                SourceHealthEntry(
                    source=name,
                    status=_status_for_error(error),
                    error_message=diagnostic,
                )
            )
            summary.failures[name] = diagnostic
            continue

        count = len(result) if result else 0
        entries.append(
            SourceHealthEntry(
                source=name,
                status=SourceStatus.OK,
                patent_count=count,
            )
        )

        if name == "pubchem_sdq":
            summary.sdq_results = result or []
        elif name == "surechembl":
            summary.surechembl_results = result or []
        elif name == "bigquery":
            summary.bigquery_rows = result or []
        elif name == "bigquery_annotations":
            summary.bq_annotation_results = result or []
        elif name == "patcid":
            summary.patcid_results = result or []
        elif name == "pubchem_similar":
            summary.pubchem_similar_results = result or []
        elif name == "pubchem_genus":
            summary.pubchem_genus_results = result or []
        elif name == "cpc_search":
            summary.cpc_search_rows = result or []
        elif name == "assignee_search":
            summary.assignee_search_rows = result or []
        elif name == "epo_search":
            summary.epo_search_results = result or []
        elif name == "lens":
            summary.lens_results = result or []
        elif name == "kipris":
            summary.kipris_results = result or []
        elif name == "patentscope":
            summary.patentscope_results = result or []
        elif name == "bigquery_translated":
            summary.bq_translated_results = result or []
        elif name == "patentsview":
            summary.patentsview_results = result or []
        elif name == "ncbi_patent_sequence":
            summary.ncbi_patent_sequence_results = result or []

    summary.health = SourceHealth(entries=entries)
    return summary


# ---------------------------------------------------------------------------
# contributions -- source contribution metrics
# ---------------------------------------------------------------------------


def _build_source_metrics(
    *,
    sdq_results: list[dict],
    source_map: dict[str, set[PatentSource]],
    source_timings: dict[str, int],
    normalize_patent_id: Callable[[str], str],
) -> tuple[dict[str, dict[str, int]], int, int]:
    source_to_patents: dict[str, set[str]] = defaultdict(set)
    for patent_id, sources in source_map.items():
        for source in sources:
            source_to_patents[source.value].add(patent_id)

    sdq_patent_ids: set[str] = set()
    for patent in sdq_results:
        publication_number = str(patent.get("publicationnumber", ""))
        if publication_number:
            sdq_patent_ids.add(normalize_patent_id(publication_number))
    source_to_patents["pubchem_sdq"] = sdq_patent_ids

    all_patent_ids = sdq_patent_ids | set(source_map.keys())

    source_metrics: dict[str, dict[str, int]] = {}
    for source_name, patent_ids in source_to_patents.items():
        if not patent_ids:
            continue
        unique_patent_ids = {
            patent_id
            for patent_id in patent_ids
            if all(
                patent_id not in source_to_patents[other]
                for other in source_to_patents
                if other != source_name
            )
        }
        source_metrics[source_name] = {
            "total": len(patent_ids),
            "unique": len(unique_patent_ids),
            "overlap": len(patent_ids) - len(unique_patent_ids),
            "elapsed_ms": source_timings.get(source_name, 0),
        }

    return source_metrics, len(all_patent_ids), len(sdq_patent_ids)


def build_search_contribution_summary(
    *,
    sdq_results: list[dict],
    source_map: dict[str, set[PatentSource]],
    source_timings: dict[str, int],
    hits: list[PatentHit],
    normalize_patent_id: Callable[[str], str],
) -> SearchContributionSummary:
    from praviar_pipeline.pipeline.search.results import build_final_source_counts

    source_metrics, total_unique_patents, sdq_total = _build_source_metrics(
        sdq_results=sdq_results,
        source_map=source_map,
        source_timings=source_timings,
        normalize_patent_id=normalize_patent_id,
    )
    final_source_counts, final_sole_source = build_final_source_counts(hits)
    return SearchContributionSummary(
        source_metrics=source_metrics,
        total_unique_patents=total_unique_patents,
        sdq_total=sdq_total,
        final_source_counts=final_source_counts,
        final_sole_source=final_sole_source,
    )


# ---------------------------------------------------------------------------
# audit -- audit funnel and completion logging
# ---------------------------------------------------------------------------


def emit_search_completion_logs(
    *,
    compound_name: str,
    hits: list[PatentHit],
    summary: SearchExecutionSummary,
    contribution_summary: SearchContributionSummary,
    enrichment_counts: SearchEnrichmentCounts,
    ranked_sdq_count: int,
) -> None:
    """Emit the final search contribution and completion logs."""
    logger.info(
        "final_hit_source_contribution",
        total_final_hits=len(hits),
        source_counts=contribution_summary.final_source_counts,
        sole_source_counts=contribution_summary.final_sole_source,
    )

    logger.info(
        "patent_search_complete",
        total_hits=len(hits),
        sdq_count=len(summary.sdq_results),
        ranked_sdq_count=ranked_sdq_count,
        surechembl_count=len(summary.surechembl_results),
        bigquery_count=len(summary.bigquery_rows),
        bigquery_annotations_count=len(summary.bq_annotation_results),
        patcid_count=len(summary.patcid_results),
        pubchem_similar_count=len(summary.pubchem_similar_results),
        pubchem_genus_count=len(summary.pubchem_genus_results),
        cpc_search_count=len(summary.cpc_search_rows),
        assignee_search_count=len(summary.assignee_search_rows),
        epo_search_count=len(summary.epo_search_results),
        lens_count=len(summary.lens_results),
        kipris_count=len(summary.kipris_results),
        patentscope_count=len(summary.patentscope_results),
        bq_translated_count=len(summary.bq_translated_results),
        legal_enriched=enrichment_counts.legal,
        families_expanded=enrichment_counts.families,
        patentsview_count=len(summary.patentsview_results),
        ncbi_patent_sequence_count=len(summary.ncbi_patent_sequence_results),
        patent_term_calculated=enrichment_counts.patent_term,
        application_data_enriched=enrichment_counts.application_data,
        epo_register_enriched=enrichment_counts.epo_register,
        ptab_enriched=enrichment_counts.ptab,
        orange_book_enriched=enrichment_counts.orange_book,
        source_timings=summary.source_timings,
        source_health=summary.health.model_dump(),
    )


def build_search_funnel(
    hits: list[PatentHit],
    *,
    collect_audit: bool,
    ranking_audit_rows: list[dict] | None = None,
) -> list[SearchFunnelEntry]:
    if not collect_audit:
        return []

    from praviar_pipeline.utils.patent_ids import normalize_patent_id

    hits_by_normalized_id: dict[str, tuple[int, PatentHit]] = {}
    for index, hit in enumerate(hits, start=1):
        hits_by_normalized_id.setdefault(
            normalize_patent_id(hit.patent_id),
            (index, hit),
        )

    search_funnel: list[SearchFunnelEntry] = []
    represented_ids: set[str] = set()
    for row in ranking_audit_rows or []:
        payload = dict(row)
        normalized = normalize_patent_id(str(payload.get("patent_id", "")))
        included_hit = hits_by_normalized_id.get(normalized)
        if bool(payload.get("included_in_triage")):
            if included_hit is None:
                raise ValueError("included ranking candidate is absent from final hits")
            final_rank, hit = included_hit
            payload["final_rank"] = final_rank
            payload["sources_found_in"] = [source.value for source in hit.sources]
            represented_ids.add(normalized)
        search_funnel.append(build_search_funnel_entry(**payload))

    for index, hit in enumerate(hits, start=1):
        normalized = normalize_patent_id(hit.patent_id)
        if normalized in represented_ids:
            continue
        hit_payload = hit.model_dump(mode="json")
        input_row_sha256 = hashlib.sha256(
            json.dumps(
                hit_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        search_funnel.append(
            build_search_funnel_entry(
                patent_id=hit.patent_id,
                sources_found_in=[source.value for source in hit.sources],
                disposition="supplementary_included",
                passed_hard_filter=True,
                included_in_triage=True,
                composite_score=hit.ranking_composite_score,
                bm25_score=hit.ranking_bm25_score,
                bm25_normalized_score=hit.ranking_bm25_normalized_score,
                embedding_score=hit.ranking_embedding_score,
                embedding_normalized_score=hit.ranking_embedding_normalized_score,
                final_blend_score=hit.ranking_final_blend_score,
                final_rank=index,
                input_row_sha256=input_row_sha256,
            )
        )
        represented_ids.add(normalized)
    return search_funnel


# ---------------------------------------------------------------------------
# preparation -- pre-ranking preparation
# ---------------------------------------------------------------------------


def prepare_ranked_search_inputs(
    *,
    summary: SearchExecutionSummary,
    compound,
    settings,
    build_source_map_fn,
    rank_patents_fn,
) -> PreparedRankingInputs:
    """Build the source map and ranked SDQ candidates before hit assembly."""
    from praviar_pipeline.models.patent import PatentSource
    from praviar_pipeline.utils.patent_ids import normalize_patent_id

    source_map = build_source_map_fn(
        surechembl_results=summary.surechembl_results,
        patcid_results=summary.patcid_results,
        bq_annotation_results=summary.bq_annotation_results,
        pubchem_similar_results=summary.pubchem_similar_results,
        pubchem_genus_results=summary.pubchem_genus_results,
        bigquery_rows=summary.bigquery_rows,
        cpc_search_rows=summary.cpc_search_rows,
        assignee_search_rows=summary.assignee_search_rows,
        epo_search_results=summary.epo_search_results,
        lens_results=summary.lens_results,
        kipris_results=summary.kipris_results,
        patentscope_results=summary.patentscope_results,
        bq_translated_results=summary.bq_translated_results,
        patentsview_results=summary.patentsview_results,
        ncbi_patent_sequence_results=summary.ncbi_patent_sequence_results,
    )
    multi_source_ids = set(source_map.keys())

    ranked_sdq = rank_patents_fn(
        summary.sdq_results,
        compound,
        multi_source_ids=multi_source_ids,
        max_results=settings.search_max_ranked_results,
        collect_audit=settings.collect_audit_trail,
    )
    ranking_audit_rows: list[dict] = []
    for audit_row in list(getattr(ranked_sdq, "audit_rows", []) or []):
        row = dict(audit_row)
        normalized = normalize_patent_id(str(row.get("patent_id", "")))
        row["sources_found_in"] = [
            PatentSource.PUBCHEM.value,
            *sorted(source.value for source in source_map.get(normalized, set())),
        ]
        row["sources_found_in"] = list(dict.fromkeys(row["sources_found_in"]))
        ranking_audit_rows.append(row)

    return PreparedRankingInputs(
        source_map=source_map,
        multi_source_ids=multi_source_ids,
        ranked_sdq=ranked_sdq,
        ranking_audit_rows=ranking_audit_rows,
    )


# ---------------------------------------------------------------------------
# assembly -- prepared search-result assembly
# ---------------------------------------------------------------------------


def assemble_prepared_search_results(
    *,
    summary: SearchExecutionSummary,
    ranked_inputs: PreparedRankingInputs,
    assemble_hits_fn,
    build_search_contribution_summary_fn,
    normalize_patent_id,
) -> PreparedSearchResults:
    """Assemble hits and contribution metadata from ranked search inputs."""
    hits, seen_norm_ids = assemble_hits_fn(
        summary=summary,
        ranked_sdq=ranked_inputs.ranked_sdq,
        source_map=ranked_inputs.source_map,
    )
    contribution_summary = build_search_contribution_summary_fn(
        sdq_results=summary.sdq_results,
        source_map=ranked_inputs.source_map,
        source_timings=summary.source_timings,
        hits=hits,
        normalize_patent_id=normalize_patent_id,
    )

    return PreparedSearchResults(
        source_map=ranked_inputs.source_map,
        multi_source_ids=ranked_inputs.multi_source_ids,
        ranked_sdq=ranked_inputs.ranked_sdq,
        hits=hits,
        seen_norm_ids=seen_norm_ids,
        contribution_summary=contribution_summary,
        ranking_audit_rows=ranked_inputs.ranking_audit_rows,
    )


# ---------------------------------------------------------------------------
# orchestration -- the main coordinator and helpers
# ---------------------------------------------------------------------------


def _successful_sources(health: SourceHealth) -> set[str]:
    return {entry.source for entry in health.entries if entry.status == SourceStatus.OK}


def _coverage_required_failures(
    *,
    health: SourceHealth,
    failures: dict[str, str],
    compound_type: str = "",
    require_genus_expansion: bool = False,
) -> dict[str, str]:
    """Return synthetic required failures when minimum legal coverage is absent."""
    from praviar_pipeline.pipeline.search.source_registry import (
        BIBLIOGRAPHIC_LEGAL_SOURCES,
        GENUS_EXPANSION_SOURCES,
        SEQUENCE_IDENTITY_SOURCES,
        STRUCTURE_IDENTITY_SOURCES,
    )

    ok_sources = _successful_sources(health)
    required: dict[str, str] = {}
    if not ok_sources.intersection(STRUCTURE_IDENTITY_SOURCES):
        relevant = {
            name: message
            for name, message in failures.items()
            if name in STRUCTURE_IDENTITY_SOURCES
        }
        detail = "; ".join(f"{name}: {message}" for name, message in relevant.items())
        required["coverage:structure_identity"] = (
            detail or "No structure/identity patent source succeeded."
        )
    if not ok_sources.intersection(BIBLIOGRAPHIC_LEGAL_SOURCES):
        relevant = {
            name: message
            for name, message in failures.items()
            if name in BIBLIOGRAPHIC_LEGAL_SOURCES
        }
        detail = "; ".join(f"{name}: {message}" for name, message in relevant.items())
        required["coverage:bibliographic_legal"] = (
            detail or "No bibliographic/legal patent source succeeded."
        )
    if compound_type in {"biologic", "peptide"} and not ok_sources.intersection(
        SEQUENCE_IDENTITY_SOURCES
    ):
        sequence_entries = [
            entry for entry in health.entries if entry.source in SEQUENCE_IDENTITY_SOURCES
        ]
        detail = "; ".join(
            f"{entry.source}: {entry.error_message or entry.status.value}"
            for entry in sequence_entries
        )
        required["coverage:sequence_identity"] = (
            detail or "No patent sequence-identity source succeeded."
        )
    if (
        compound_type == "small_molecule"
        and require_genus_expansion
        and not ok_sources.intersection(GENUS_EXPANSION_SOURCES)
    ):
        genus_entries = [
            entry for entry in health.entries if entry.source in GENUS_EXPANSION_SOURCES
        ]
        detail = "; ".join(
            f"{entry.source}: {entry.error_message or entry.status.value}"
            for entry in genus_entries
        )
        required["coverage:genus_expansion"] = (
            detail or "No developed-structure genus-expansion source succeeded."
        )
    return required


def _required_failures_for_policy(
    *,
    summary: SearchExecutionSummary,
    settings,
    compound_type: str = "",
) -> dict[str, str]:
    policy = getattr(settings, "source_failure_policy", "coverage_aware")
    modality_failures = _coverage_required_failures(
        health=summary.health,
        failures=summary.failures,
        compound_type=compound_type,
        require_genus_expansion=bool(getattr(settings, "search_enable_pubchem_genus", False)),
    )
    mandatory_modality_failure = {
        key: value
        for key, value in modality_failures.items()
        if key in {"coverage:sequence_identity", "coverage:genus_expansion"}
    }
    if policy == "best_effort":
        return mandatory_modality_failure
    if policy == "fail_fast":
        return mandatory_modality_failure | {
            source: message
            for source, message in summary.failures.items()
            if source not in OPTIONAL_EXPANDED_SEARCH_SOURCES
        }
    return modality_failures


async def execute_search_plan(
    plan: list[tuple[str, Awaitable[Any]]],
    run_source: RunSourceFn,
) -> SearchExecutionSummary:
    """Run the concurrent source plan and partition the outcomes."""
    planned_entries = list(getattr(plan, "planned_entries", []) or [])
    if plan:
        outcomes = await asyncio.gather(*[run_source(name, coro) for name, coro in plan])
        summary = partition_source_outcomes(list(outcomes))
    else:
        summary = SearchExecutionSummary()
    if planned_entries:
        summary.health.entries = [*planned_entries, *summary.health.entries]
        for entry in planned_entries:
            if entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}:
                summary.failures[entry.source] = entry.error_message
    return summary


async def run_source(
    name: str,
    coro: Awaitable[Any],
    *,
    timeout_s: float | None = None,
) -> SearchRunOutcome:
    t0 = time.monotonic()
    try:
        result = (
            await asyncio.wait_for(coro, timeout=timeout_s) if timeout_s is not None else await coro
        )
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.debug(
            "source_search_ok",
            source=name,
            result_count=len(result) if result else 0,
            elapsed_ms=elapsed_ms,
        )
        return name, result, None, elapsed_ms
    except TimeoutError as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        error = TimeoutError(f"source exceeded timeout_s={timeout_s:g}") if timeout_s else exc
        logger.error(
            "source_search_failed",
            source=name,
            error_type=safe_exception_type(error),
            elapsed_ms=elapsed_ms,
        )
        return name, None, error, elapsed_ms
    except (ConfigurationError, PatCIDDatabaseNotFoundError) as exc:
        # Expected "not configured" state — log at INFO, not ERROR, to avoid
        # false-alarm noise in production logs (e.g. PatCID DB not bundled).
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.info(
            "source_not_configured",
            source=name,
            error_type=safe_exception_type(exc),
            elapsed_ms=elapsed_ms,
        )
        return name, None, exc, elapsed_ms
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error(
            "source_search_failed",
            source=name,
            error_type=safe_exception_type(exc),
            elapsed_ms=elapsed_ms,
        )
        return name, None, exc, elapsed_ms


def prepare_search_results(
    *,
    summary: SearchExecutionSummary,
    compound,
    settings,
    build_source_map_fn,
    rank_patents_fn,
    assemble_hits_fn,
    build_search_contribution_summary_fn,
    normalize_patent_id,
) -> PreparedSearchResults:
    """Build the shared source map, ranked SDQ list, assembled hits, and contribution summary."""
    ranked_inputs = prepare_ranked_search_inputs(
        summary=summary,
        compound=compound,
        settings=settings,
        build_source_map_fn=build_source_map_fn,
        rank_patents_fn=rank_patents_fn,
    )
    return assemble_prepared_search_results(
        summary=summary,
        ranked_inputs=ranked_inputs,
        assemble_hits_fn=assemble_hits_fn,
        build_search_contribution_summary_fn=build_search_contribution_summary_fn,
        normalize_patent_id=normalize_patent_id,
    )


async def maybe_expand_via_citations(
    *,
    enabled: bool,
    summary: SearchExecutionSummary,
    hits: list[PatentHit],
    seen_norm_ids: set[str],
    source_map: dict[str, set[PatentSource]],
    settings,
    expand_via_citations_fn,
) -> None:
    """Run citation expansion only when the coordinator has enabled it."""
    if not enabled:
        return
    await expand_via_citations_fn(
        hits,
        seen_norm_ids,
        source_map,
        supplementary_rows=[summary.cpc_search_rows, summary.assignee_search_rows],
        settings=settings,
    )


async def finalize_search_run(
    hits: list[PatentHit],
    *,
    collect_audit: bool,
    ranking_audit_rows: list[dict] | None = None,
    enrich_hits_fn,
) -> tuple[SearchEnrichmentCounts, list[SearchFunnelEntry]]:
    """Run the final deterministic enrichment steps and build the audit funnel."""
    enrichment_counts = await enrich_hits_fn(hits)
    search_funnel = build_search_funnel(
        hits,
        collect_audit=collect_audit,
        ranking_audit_rows=ranking_audit_rows,
    )
    return enrichment_counts, search_funnel


async def execute_search_coordinator(
    *,
    compound: ResolvedCompound,
    expanded_queries: ExpandedSearchQueries,
    has_expansion: bool,
    settings,
    build_search_plan_fn,
    execute_search_plan_fn,
    run_source_fn,
    prepare_search_results_fn,
    build_source_map_fn,
    rank_patents_fn,
    assemble_hits_fn,
    build_search_contribution_summary_fn,
    normalize_patent_id,
    maybe_expand_via_citations_fn,
    expand_via_citations_fn,
    finalize_search_run_fn,
    enrich_hits_fn,
    emit_search_completion_logs_fn,
) -> tuple[list[PatentHit], SourceHealth, list[SearchFunnelEntry]]:
    """Run the full Step 2 coordinator with injected facade dependencies."""
    plan = build_search_plan_fn(
        compound=compound,
        expanded_queries=expanded_queries,
        has_expansion=has_expansion,
    )
    summary = await execute_search_plan_fn(plan, run_source_fn)
    health = summary.health
    logger.info(
        "step2_source_health",
        sources_ok=[entry.source for entry in health.entries if entry.status.value == "ok"],
        sources_failed=[
            entry.source
            for entry in health.entries
            if entry.status.value in {"failed", "not_configured"}
        ],
        sdq_count=len(summary.sdq_results),
        surechembl_count=len(summary.surechembl_results),
        bigquery_count=len(summary.bigquery_rows),
        bq_annotations_count=len(summary.bq_annotation_results),
        patcid_count=len(summary.patcid_results),
        cpc_search_count=len(summary.cpc_search_rows),
        assignee_search_count=len(summary.assignee_search_rows),
        epo_search_count=len(summary.epo_search_results),
        lens_count=len(summary.lens_results),
        kipris_count=len(summary.kipris_results),
        patentscope_count=len(summary.patentscope_results),
        bq_translated_count=len(summary.bq_translated_results),
        pubchem_genus_count=len(summary.pubchem_genus_results),
        ncbi_patent_sequence_count=len(summary.ncbi_patent_sequence_results),
    )

    if getattr(health, "all_failed", False):
        raise AllSourcesFailedError(summary.failures)
    required_failures = _required_failures_for_policy(
        summary=summary,
        settings=settings,
        compound_type=getattr(compound, "compound_type", "small_molecule"),
    )
    if required_failures:
        raise SearchSourceFailedError(required_failures)

    prepared = prepare_search_results_fn(
        summary=summary,
        compound=compound,
        settings=settings,
        build_source_map_fn=build_source_map_fn,
        rank_patents_fn=rank_patents_fn,
        assemble_hits_fn=assemble_hits_fn,
        build_search_contribution_summary_fn=build_search_contribution_summary_fn,
        normalize_patent_id=normalize_patent_id,
    )
    hits = prepared.hits

    logger.info(
        "source_contribution_analysis",
        total_unique_patents=prepared.contribution_summary.total_unique_patents,
        sdq_total=prepared.contribution_summary.sdq_total,
        non_sdq_total=len(prepared.source_map),
        source_metrics=prepared.contribution_summary.source_metrics,
        source_timings=summary.source_timings,
    )

    await maybe_expand_via_citations_fn(
        enabled=settings.search_citation_traversal_enabled,
        summary=summary,
        hits=hits,
        seen_norm_ids=prepared.seen_norm_ids,
        source_map=prepared.source_map,
        settings=settings,
        expand_via_citations_fn=expand_via_citations_fn,
    )

    logger.info(
        "step2_enrichment_starting",
        hit_count=len(hits),
        us_count=sum(1 for h in hits if h.patent_id.startswith("US")),
        ep_count=sum(1 for h in hits if h.patent_id.startswith("EP")),
        wo_count=sum(1 for h in hits if h.patent_id.startswith("WO")),
    )
    finalize_kwargs: dict[str, Any] = {
        "collect_audit": settings.collect_audit_trail,
        "enrich_hits_fn": enrich_hits_fn,
    }
    ranking_audit_rows = list(getattr(prepared, "ranking_audit_rows", []) or [])
    if ranking_audit_rows:
        finalize_kwargs["ranking_audit_rows"] = ranking_audit_rows
    enrichment_counts, search_funnel = await finalize_search_run_fn(
        hits,
        **finalize_kwargs,
    )

    emit_search_completion_logs_fn(
        compound_name=compound.name,
        hits=hits,
        summary=summary,
        contribution_summary=prepared.contribution_summary,
        enrichment_counts=enrichment_counts,
        ranked_sdq_count=len(prepared.ranked_sdq),
    )

    return hits, health, search_funnel
