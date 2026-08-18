"""Result-assembly helpers for the Step 2 patent search pipeline."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from praviar_pipeline.models.patent import PatentHit, PatentSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.pipeline.search.orchestration import SearchExecutionSummary


def assemble_hits_from_summary(
    *,
    summary: SearchExecutionSummary,
    ranked_sdq: list[dict],
    source_map: dict[str, set[PatentSource]],
    normalize_patent_id: Callable[[str], str],
    sdq_to_patent_hit: Callable[[dict, dict[str, set[PatentSource]]], PatentHit],
    bq_row_to_patent_hit: Callable[[dict, PatentSource, dict[str, set[PatentSource]]], PatentHit],
    merge_supplementary_rows: Callable[
        [list[dict], PatentSource, list[PatentHit], set[str], dict[str, set[PatentSource]]],
        None,
    ],
    surechembl_similarity_lookup: Callable[[str], dict | None],
) -> tuple[list[PatentHit], set[str]]:
    """Build the final Step 2 hit list from ranked and supplementary search results."""
    seen_norm_ids: set[str] = set()
    hits: list[PatentHit] = []
    hits_by_norm_id: dict[str, PatentHit] = {}

    for patent in ranked_sdq:
        hit = sdq_to_patent_hit(patent, source_map)
        hits.append(hit)
        norm = normalize_patent_id(hit.patent_id)
        seen_norm_ids.add(norm)
        hits_by_norm_id[norm] = hit

    for row in summary.bigquery_rows:
        publication_number = row.get("publication_number", "")
        if not publication_number:
            continue
        normalized_id = normalize_patent_id(publication_number)
        if normalized_id in seen_norm_ids:
            # Merge BQ data into the existing hit: add source attribution and
            # backfill fields the SDQ-built hit lacks (claims_text, filing_date,
            # abstract, inventors). Without this, triage receives a hit with no
            # claims text even though BigQuery had it.
            existing = hits_by_norm_id.get(normalized_id)
            if existing is not None:
                bq_hit = bq_row_to_patent_hit(row, PatentSource.BIGQUERY, source_map)
                if PatentSource.BIGQUERY not in existing.sources:
                    existing.sources.append(PatentSource.BIGQUERY)
                if not existing.claims_text and bq_hit.claims_text:
                    existing.claims_text = bq_hit.claims_text
                    existing.claims_text_source = bq_hit.claims_text_source
                    existing.claims_text_provenance = bq_hit.claims_text_provenance
                if not existing.abstract and bq_hit.abstract:
                    existing.abstract = bq_hit.abstract
                if not existing.filing_date and bq_hit.filing_date:
                    existing.filing_date = bq_hit.filing_date
                if not existing.inventors and bq_hit.inventors:
                    existing.inventors = bq_hit.inventors
            continue
        hit = bq_row_to_patent_hit(row, PatentSource.BIGQUERY, source_map)
        hits.append(hit)
        seen_norm_ids.add(normalized_id)
        hits_by_norm_id[normalized_id] = hit

    for rows, source in [
        (summary.cpc_search_rows, PatentSource.CPC_SEARCH),
        (summary.assignee_search_rows, PatentSource.ASSIGNEE_SEARCH),
        (summary.epo_search_results, PatentSource.EPO_SEARCH),
        (summary.lens_results, PatentSource.LENS),
        (summary.kipris_results, PatentSource.KIPRIS),
        (summary.patentscope_results, PatentSource.PATENTSCOPE),
        (summary.bq_translated_results, PatentSource.BIGQUERY_TRANSLATED),
        (summary.patentsview_results, PatentSource.PATENTSVIEW),
        (
            getattr(summary, "pubchem_genus_results", []),
            PatentSource.PUBCHEM_GENUS,
        ),
        (
            getattr(summary, "ncbi_patent_sequence_results", []),
            PatentSource.NCBI_PATENT_SEQUENCE,
        ),
    ]:
        merge_supplementary_rows(rows, source, hits, seen_norm_ids, source_map)

    _apply_grant_status_flags(hits)
    _apply_surechembl_similarity_metadata(hits, surechembl_similarity_lookup)
    return hits, seen_norm_ids


def assemble_step2_hits(
    *,
    summary: SearchExecutionSummary,
    ranked_sdq: list[dict],
    source_map: dict[str, set[PatentSource]],
    normalize_patent_id: Callable[[str], str],
    sdq_to_patent_hit: Callable[[dict, dict[str, set[PatentSource]]], PatentHit],
    bq_row_to_patent_hit: Callable[[dict, PatentSource, dict[str, set[PatentSource]]], PatentHit],
    merge_supplementary_rows: Callable[
        [list[dict], PatentSource, list[PatentHit], set[str], dict[str, set[PatentSource]]],
        None,
    ],
    surechembl_similarity_lookup: Callable[[str], dict | None],
) -> tuple[list[PatentHit], set[str]]:
    """Assemble final Step 2 hits with the standard default adapters."""
    return assemble_hits_from_summary(
        summary=summary,
        ranked_sdq=ranked_sdq,
        source_map=source_map,
        normalize_patent_id=normalize_patent_id,
        sdq_to_patent_hit=sdq_to_patent_hit,
        bq_row_to_patent_hit=bq_row_to_patent_hit,
        merge_supplementary_rows=merge_supplementary_rows,
        surechembl_similarity_lookup=surechembl_similarity_lookup,
    )


def build_final_source_counts(hits: list[PatentHit]) -> tuple[dict[str, int], dict[str, int]]:
    """Compute source-contribution counts for the emitted hit list."""
    final_source_counts: dict[str, int] = defaultdict(int)
    final_sole_source: dict[str, int] = defaultdict(int)
    for hit in hits:
        for source in hit.sources:
            final_source_counts[source.value] += 1
        if len(hit.sources) == 1:
            final_sole_source[next(iter(hit.sources)).value] += 1
    return dict(final_source_counts), dict(final_sole_source)


def _apply_grant_status_flags(hits: list[PatentHit]) -> None:
    for hit in hits:
        kind_match = re.search(r"([A-Z]\d?)$", hit.patent_id.strip())
        if kind_match:
            kind = kind_match.group(1)
            hit.is_granted = kind.startswith("B") or kind.startswith("E")


def _apply_surechembl_similarity_metadata(
    hits: list[PatentHit],
    surechembl_similarity_lookup: Callable[[str], dict | None],
) -> None:
    for hit in hits:
        cached = surechembl_similarity_lookup(hit.patent_id)
        if not cached:
            continue
        if "tanimoto_score" in cached and hit.tanimoto_score is None:
            hit.tanimoto_score = cached["tanimoto_score"]
        if "match_type" in cached and not hit.match_type:
            hit.match_type = cached["match_type"]
