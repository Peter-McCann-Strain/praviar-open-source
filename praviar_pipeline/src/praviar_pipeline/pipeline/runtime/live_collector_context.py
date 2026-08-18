"""Runtime collector helpers for prosecution and regulatory context."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.runtime.live_collector_helpers import failed_entry, ok_entry
from praviar_pipeline.pipeline.search.enrichment import EnrichmentOutcome
from praviar_pipeline.utils.safe_diagnostics import (
    safe_exception_type,
    safe_failure_message,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


def _sections_available(value: object) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(section) for section in value if str(section)}


async def collect_uspto_odp_runtime_context_impl(
    *,
    patent_ids: list[str],
    prosecution_cache: dict[str, dict[str, object]],
    fetch_prosecution_context_fn,
) -> tuple[SourceHealthEntry, dict[str, dict[str, object]]]:
    updated_cache = dict(prosecution_cache)
    uncached_ids = [
        patent_id
        for patent_id in patent_ids
        if patent_id not in updated_cache
        or "us_file_wrapper_dossier"
        not in _sections_available(updated_cache[patent_id].get("sections_available"))
    ]
    if not uncached_ids:
        return ok_entry("uspto_odp", len(patent_ids)), updated_cache

    results = await asyncio.gather(
        *(fetch_prosecution_context_fn(patent_id) for patent_id in uncached_ids),
        return_exceptions=True,
    )
    first_error = ""
    for patent_id, result in zip(uncached_ids, results, strict=False):
        if isinstance(result, BaseException):
            if not first_error:
                first_error = safe_failure_message("live collector", result)
            logger.warning(
                "runtime_uspto_odp_collection_failed",
                error_type=safe_exception_type(result),
            )
            continue
        if isinstance(result, dict) and result:
            updated_cache[patent_id] = result
        elif not first_error:
            first_error = "live collector returned no coverage"

    collected_count = sum(1 for patent_id in patent_ids if updated_cache.get(patent_id))
    status = (
        SourceStatus.OK
        if collected_count == len(patent_ids) and not first_error
        else SourceStatus.FAILED
    )
    return (
        SourceHealthEntry(
            source="uspto_odp",
            status=status,
            patent_count=collected_count,
            attempted_count=len(patent_ids),
            covered_count=collected_count,
            error_message=first_error,
        ),
        updated_cache,
    )


async def collect_family_context_runtime_impl(
    *,
    patent_hits: list[PatentHit],
    expand_families_fn,
) -> SourceHealthEntry:
    if not patent_hits:
        return ok_entry("family_record", 0)
    try:
        outcome = await expand_families_fn(patent_hits)
        if not isinstance(outcome, EnrichmentOutcome):
            raise TypeError("Family collector must return EnrichmentOutcome")
        if outcome.attempted_count != len(patent_hits):
            raise ValueError("Family collector attempted-count mismatch")
        if outcome.covered_count != outcome.attempted_count:
            return SourceHealthEntry(
                source="family_record",
                status=SourceStatus.FAILED,
                patent_count=outcome.evidence_count,
                attempted_count=outcome.attempted_count,
                covered_count=outcome.covered_count,
                error_message="family collector coverage incomplete",
            )
        return ok_entry(
            "family_record",
            outcome.evidence_count,
            attempted_count=outcome.attempted_count,
            covered_count=outcome.covered_count,
        )
    except Exception as exc:
        return failed_entry(
            "family_record",
            exc,
            attempted_count=len(patent_hits),
        )


async def collect_counting_enrichment_runtime(
    *,
    source: str,
    patent_hits: list[PatentHit],
    collector_fn,
) -> SourceHealthEntry:
    if not patent_hits:
        return ok_entry(source, 0)
    try:
        outcome = await collector_fn(patent_hits)
        if not isinstance(outcome, EnrichmentOutcome):
            raise TypeError("Counting collector must return EnrichmentOutcome")
        if outcome.attempted_count != len(patent_hits):
            raise ValueError("Counting collector attempted-count mismatch")
        if outcome.covered_count != outcome.attempted_count:
            return SourceHealthEntry(
                source=source,
                status=SourceStatus.FAILED,
                patent_count=outcome.evidence_count,
                attempted_count=outcome.attempted_count,
                covered_count=outcome.covered_count,
                error_message="live collector coverage incomplete",
            )
        return ok_entry(
            source,
            outcome.evidence_count,
            attempted_count=outcome.attempted_count,
            covered_count=outcome.covered_count,
        )
    except Exception as exc:
        return failed_entry(
            source,
            exc,
            attempted_count=len(patent_hits),
        )
