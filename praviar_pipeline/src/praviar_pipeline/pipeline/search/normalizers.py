"""Normalization and merge helpers for the Step 2 patent search pipeline."""

from __future__ import annotations

from collections import defaultdict

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.patent import (
    ClaimTextCollectorIdentity,
    GenusPatentMatch,
    LegalStatus,
    PatentHit,
    PatentSource,
    SequencePatentMatch,
    build_claim_text_provenance,
)
from praviar_pipeline.pipeline.step2b_rank import _parse_cpc_codes
from praviar_pipeline.utils.dates import parse_date as _parse_date
from praviar_pipeline.utils.legal_status_events import derive_legal_status_from_events
from praviar_pipeline.utils.patent_ids import normalize_patent_id as _normalize_patent_id


def _compute_confidence(sources: list[PatentSource]) -> float:
    """Score confidence based on how many independent sources found this patent."""
    settings = get_settings()
    unique = len(set(sources))
    if unique >= 4:
        return settings.confidence_4_sources
    if unique >= 3:
        return settings.confidence_3_sources
    if unique >= 2:
        return settings.confidence_2_sources
    return settings.confidence_1_source


def _sdq_to_patent_hit(
    pat: dict,
    source_map: dict[str, set[PatentSource]],
) -> PatentHit:
    """Convert an SDQ result dict into a PatentHit model."""
    pub_num = str(pat.get("publicationnumber", ""))
    norm = _normalize_patent_id(pub_num)

    sources = {PatentSource.PUBCHEM}
    sources |= source_map.get(norm, set())

    cpc_codes = _parse_cpc_codes(pat.get("classification"))
    priority_date = _parse_date(pat.get("prioritydate"))

    assignees_raw = pat.get("assignees", "")
    if isinstance(assignees_raw, str):
        assignees = [a.strip() for a in assignees_raw.split(";") if a.strip()]
    elif isinstance(assignees_raw, list):
        assignees = assignees_raw
    else:
        assignees = []

    ranking_payload = pat.get("_retrieval_scores")
    ranking = ranking_payload if isinstance(ranking_payload, dict) else {}

    return PatentHit(
        patent_id=pub_num,
        title=str(pat.get("title", "")),
        abstract=str(pat.get("abstract", "")),
        sources=sorted(sources, key=lambda s: s.value),
        confidence_score=_compute_confidence(list(sources)),
        priority_date=priority_date,
        assignees=assignees,
        cpc_codes=cpc_codes,
        ranking_composite_score=ranking.get("composite"),
        ranking_bm25_score=ranking.get("bm25_raw"),
        ranking_bm25_normalized_score=ranking.get("bm25_normalized"),
        ranking_embedding_score=ranking.get("embedding_raw"),
        ranking_embedding_normalized_score=ranking.get("embedding_normalized"),
        ranking_final_blend_score=ranking.get("final_blend"),
    )


def _derive_legal_status(events: list[dict]) -> LegalStatus:
    """Derive simplified legal status from INPADOC events."""
    return derive_legal_status_from_events(events)


def _bq_row_to_patent_hit(
    row: dict,
    source: PatentSource,
    source_map: dict[str, set[PatentSource]],
) -> PatentHit:
    """Convert a BigQuery/EPO result row into a first-class PatentHit object."""
    pid = row.get("publication_number", "")
    norm = _normalize_patent_id(pid)

    sources: set[PatentSource] = {source}
    if norm in source_map:
        sources |= source_map[norm]

    assignees = row.get("assignee_harmonized", [])
    if isinstance(assignees, list):
        assignees = [a.get("name", a) if isinstance(a, dict) else str(a) for a in assignees]
    else:
        assignees = []

    cpc = row.get("cpc_codes", [])
    if isinstance(cpc, str):
        cpc = [cpc]
    elif not isinstance(cpc, list):
        cpc = []

    inventors_raw = row.get("inventor_harmonized") or []
    inventors = [i.get("name", i) if isinstance(i, dict) else str(i) for i in inventors_raw]

    claims_text = str(row.get("claims_text", "") or "")
    hit = PatentHit(
        patent_id=pid,
        title=row.get("title", ""),
        abstract=row.get("abstract", ""),
        claims_text=claims_text,
        sources=sorted(sources, key=lambda s: s.value),
        confidence_score=_compute_confidence(list(sources)),
        filing_date=_parse_date(row.get("filing_date")),
        priority_date=_parse_date(row.get("priority_date")),
        expiry_date=_parse_date(row.get("expiry_date")),
        assignees=assignees,
        inventors=inventors,
        cpc_codes=cpc,
        match_type=(
            "sequence"
            if source == PatentSource.NCBI_PATENT_SEQUENCE
            else "substructure"
            if source == PatentSource.PUBCHEM_GENUS
            else ""
        ),
        sequence_matches=row.get("sequence_matches", []),
        genus_matches=row.get("genus_matches", []),
    )
    if claims_text and source == PatentSource.BIGQUERY_TRANSLATED:
        # Translation is useful for reviewer display but cannot satisfy the
        # controlling-language claim-text gate.
        hit.claims_text_source = source.value
    elif claims_text and source in {
        PatentSource.BIGQUERY,
        PatentSource.EPO_SEARCH,
        PatentSource.PATENTSVIEW,
    }:
        source_name = source
        locator_by_source = {
            PatentSource.BIGQUERY: (
                "https://console.cloud.google.com/bigquery?project="
                f"patents-public-data&patent={pid}"
            ),
            PatentSource.EPO_SEARCH: (
                "https://ops.epo.org/3.2/rest-services/published-data/"
                f"publication/epodoc/{pid}/claims"
            ),
            PatentSource.PATENTSVIEW: (
                f"https://search.patentsview.org/api/v1/patent/?patent_id={pid}"
            ),
        }
        collector_by_source: dict[PatentSource, ClaimTextCollectorIdentity] = {
            PatentSource.BIGQUERY: "search.bigquery_result",
            PatentSource.EPO_SEARCH: "search.epo_search_result",
            PatentSource.PATENTSVIEW: "search.patentsview_result",
        }
        hit.claims_text_source = source_name.value
        hit.claims_text_provenance = build_claim_text_provenance(
            patent_id=pid,
            claims_text=claims_text,
            source=source_name,
            artifact_locator=locator_by_source[source_name],
            collector_identity=collector_by_source[source],
        )
    return hit


def _merge_supplementary_rows(
    rows: list[dict],
    source: PatentSource,
    hits: list[PatentHit],
    seen_norm_ids: set[str],
    source_map: dict[str, set[PatentSource]],
) -> None:
    """Merge supplementary search results into the main hit list."""
    hits_by_norm_id = {_normalize_patent_id(h.patent_id): h for h in hits}

    for row in rows:
        pid = row.get("publication_number", "")
        if not pid:
            continue
        norm_id = _normalize_patent_id(pid)
        if norm_id in seen_norm_ids:
            existing = hits_by_norm_id.get(norm_id)
            if existing and source not in existing.sources:
                existing.sources.append(source)
                existing.confidence_score = _compute_confidence(existing.sources)
            if existing and source == PatentSource.NCBI_PATENT_SEQUENCE:
                known_matches = {
                    (
                        match.query_sha256,
                        match.subject_accession,
                        match.query_subunit_index,
                    )
                    for match in existing.sequence_matches
                }
                for payload in row.get("sequence_matches", []):
                    match = SequencePatentMatch.model_validate(payload)
                    match_key = (
                        match.query_sha256,
                        match.subject_accession,
                        match.query_subunit_index,
                    )
                    if match_key not in known_matches:
                        existing.sequence_matches.append(match)
                        known_matches.add(match_key)
                if existing.sequence_matches:
                    existing.match_type = "sequence"
            if existing and source == PatentSource.PUBCHEM_GENUS:
                genus_known_matches = {
                    (
                        genus_match.query_sha256,
                        genus_match.matched_pubchem_cid,
                        genus_match.query_role,
                    )
                    for genus_match in existing.genus_matches
                }
                for payload in row.get("genus_matches", []):
                    genus_match = GenusPatentMatch.model_validate(payload)
                    genus_match_key = (
                        genus_match.query_sha256,
                        genus_match.matched_pubchem_cid,
                        genus_match.query_role,
                    )
                    if genus_match_key not in genus_known_matches:
                        existing.genus_matches.append(genus_match)
                        genus_known_matches.add(genus_match_key)
                if existing.genus_matches and existing.match_type != "sequence":
                    existing.match_type = "substructure"
            continue
        hit = _bq_row_to_patent_hit(row, source, source_map)
        hits.append(hit)
        seen_norm_ids.add(norm_id)
        hits_by_norm_id[norm_id] = hit


def build_source_map(
    *,
    surechembl_results: list[tuple[str, PatentSource]],
    patcid_results: list[tuple[str, PatentSource]],
    bq_annotation_results: list[tuple[str, PatentSource]],
    pubchem_similar_results: list[tuple[str, PatentSource]],
    bigquery_rows: list[dict],
    cpc_search_rows: list[dict],
    assignee_search_rows: list[dict],
    epo_search_results: list[dict],
    lens_results: list[dict],
    kipris_results: list[dict],
    patentscope_results: list[dict],
    bq_translated_results: list[dict],
    patentsview_results: list[dict],
    pubchem_genus_results: list[dict] | None = None,
    ncbi_patent_sequence_results: list[dict] | None = None,
) -> dict[str, set[PatentSource]]:
    """Build normalized patent ID → source set mappings for all non-primary sources."""
    source_map: dict[str, set[PatentSource]] = defaultdict(set)
    for pid, _ in surechembl_results:
        source_map[_normalize_patent_id(pid)].add(PatentSource.SURECHEMBL)
    for pid, _ in patcid_results:
        source_map[_normalize_patent_id(pid)].add(PatentSource.PATCID)
    for pid, _ in bq_annotation_results:
        source_map[_normalize_patent_id(pid)].add(PatentSource.BIGQUERY)
    for pid, _ in pubchem_similar_results:
        source_map[_normalize_patent_id(pid)].add(PatentSource.PUBCHEM)
    for rows, source in [
        (bigquery_rows, PatentSource.BIGQUERY),
        (cpc_search_rows, PatentSource.CPC_SEARCH),
        (assignee_search_rows, PatentSource.ASSIGNEE_SEARCH),
        (epo_search_results, PatentSource.EPO_SEARCH),
        (lens_results, PatentSource.LENS),
        (kipris_results, PatentSource.KIPRIS),
        (patentscope_results, PatentSource.PATENTSCOPE),
        (bq_translated_results, PatentSource.BIGQUERY_TRANSLATED),
        (patentsview_results, PatentSource.PATENTSVIEW),
        (
            pubchem_genus_results or [],
            PatentSource.PUBCHEM_GENUS,
        ),
        (
            ncbi_patent_sequence_results or [],
            PatentSource.NCBI_PATENT_SEQUENCE,
        ),
    ]:
        for row in rows:
            pid = row.get("publication_number", "")
            if pid:
                source_map[_normalize_patent_id(pid)].add(source)
    return source_map
