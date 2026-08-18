"""Citation traversal helpers for the Step 2 patent search pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from google.api_core.exceptions import GoogleAPIError

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.patent_ids import normalize_patent_id as _normalize_patent_id
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


def _build_citation_seed_ids(
    hits: list[PatentHit],
    supplementary_rows: list[list[dict]],
    max_seed_patents: int,
) -> list[str]:
    """Collect citation seed IDs from top hits and supplementary rows."""
    top_hits_sorted = sorted(hits, key=lambda hit: hit.confidence_score, reverse=True)
    seed_ids = [hit.patent_id for hit in top_hits_sorted[:max_seed_patents]]

    for rows in supplementary_rows:
        for row in rows[:10]:
            patent_id = row.get("publication_number", "")
            if patent_id and patent_id not in seed_ids:
                seed_ids.append(patent_id)

    return seed_ids


async def _traverse_citation_network(
    seed_patent_ids: list[str],
    max_depth: int = 2,
    max_per_level: int = 50,
    client_factory=BigQueryClient,
) -> set[str]:
    """Traverse examiner citation network via BigQuery."""
    discovered: set[str] = set()
    # Normalize seeds so exclusion checks compare apples-to-apples.
    norm_seeds: set[str] = {_normalize_patent_id(s) for s in seed_patent_ids}
    current_level = set(seed_patent_ids)
    failure_type: str | None = None

    try:
        async with client_factory() as bq:
            for depth in range(max_depth):
                if not current_level:
                    break

                citations_map = await bq.get_examiner_citations_batch(
                    list(current_level)[:max_per_level]
                )

                next_level: set[str] = set()
                settings = get_settings()
                for _pid, citations in citations_map.items():
                    for ref in citations.get("examiner", [])[: settings.citation_examiner_max_refs]:
                        norm = _normalize_patent_id(ref)
                        if norm not in discovered and norm not in norm_seeds:
                            next_level.add(norm)

                discovered.update(next_level)
                current_level = next_level

                logger.debug(
                    "citation_traversal_level",
                    depth=depth + 1,
                    discovered=len(next_level),
                    total=len(discovered),
                )

    except (GoogleAPIError, KeyError, ValueError) as exc:
        failure_type = safe_exception_type(exc)
        logger.error(
            "citation_traversal_failed",
            error_type=failure_type,
        )

    if failure_type is not None:
        raise SourceUnavailableError("bigquery", "citation traversal failed") from None

    logger.info("citation_traversal_complete", total_discovered=len(discovered))
    return discovered


async def expand_via_citations(
    hits: list,
    *,
    seen_norm_ids: set[str],
    source_map: dict[str, set],
    supplementary_rows: list[list[dict]],
    settings,
    client_factory=BigQueryClient,
    row_to_patent_hit,
    patent_source,
) -> None:
    seed_ids = _build_citation_seed_ids(
        hits,
        supplementary_rows,
        settings.citation_seed_max_patents,
    )

    if not seed_ids:
        return

    citation_ids = await _traverse_citation_network(
        seed_patent_ids=seed_ids,
        max_depth=settings.search_citation_max_depth,
        max_per_level=settings.search_citation_max_per_level,
        client_factory=client_factory,
    )

    new_citation_ids = [
        patent_id
        for patent_id in citation_ids
        if _normalize_patent_id(patent_id) not in seen_norm_ids
    ]
    if not new_citation_ids:
        return

    failure_type: str | None = None
    try:
        async with client_factory() as bq:
            citation_metadata = await bq.get_patent_metadata_batch(new_citation_ids[:100])
        for row in citation_metadata:
            patent_id = row.get("publication_number", "")
            if not patent_id:
                continue
            normalized_patent_id = _normalize_patent_id(patent_id)
            if normalized_patent_id in seen_norm_ids:
                continue
            hit = row_to_patent_hit(row, patent_source, source_map)
            hits.append(hit)
            seen_norm_ids.add(normalized_patent_id)
    except (GoogleAPIError, KeyError, ValueError) as exc:
        failure_type = safe_exception_type(exc)
        logger.error(
            "citation_metadata_fetch_failed",
            count=len(new_citation_ids),
            error_type=failure_type,
        )

    if failure_type is not None:
        raise SourceUnavailableError("bigquery", "citation metadata lookup failed") from None
