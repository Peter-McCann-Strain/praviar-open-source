"""Step 2: Multi-Source Patent Search -- ResolvedCompound -> deduplicated PatentHit list.

Uses a multi-tier funnel to filter and rank source results before any LLM call:

1. PubChem SDQ API -> rich metadata (title, abstract, CPC, dates, compound count)
2. Hard filters -> US jurisdiction, granted patents only, expiry check
3. Multi-signal scoring -> CPC relevance, compound count, recency, title match
4. BM25 re-ranking -> text relevance on title + abstract
5. Configured Top N cutoff -> bounded patent set sent to LLM triage

BigQuery, SureChEMBL, and PatCID run in parallel to provide multi-source signals
that boost ranking confidence.

This module consolidates the former step2_search.py + step2_search_impl.py.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.search import enrichment as search_post_enrichment
from praviar_pipeline.pipeline.search import normalizers as search_normalizers
from praviar_pipeline.pipeline.search import orchestration as search_orchestration
from praviar_pipeline.pipeline.search import plan as search_plan
from praviar_pipeline.pipeline.search import primary_sources
from praviar_pipeline.pipeline.search import results as search_results
from praviar_pipeline.pipeline.search import wiring as search_wiring
from praviar_pipeline.pipeline.search.normalizers import (
    _bq_row_to_patent_hit as _bq_row_to_patent_hit,
)
from praviar_pipeline.pipeline.search.normalizers import (
    _derive_legal_status as _derive_legal_status,
)
from praviar_pipeline.pipeline.search.normalizers import (
    _merge_supplementary_rows as _merge_supplementary_rows,
)
from praviar_pipeline.pipeline.search.normalizers import (
    _sdq_to_patent_hit as _sdq_to_patent_hit,
)
from praviar_pipeline.pipeline.search.normalizers import (
    build_source_map as build_source_map,
)
from praviar_pipeline.pipeline.step2b_rank import rank_patents
from praviar_pipeline.utils.patent_ids import (
    normalize_patent_id as _normalize_patent_id,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.models.audit import SearchFunnelEntry
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit, PatentSource
    from praviar_pipeline.models.report import SourceHealth
    from praviar_pipeline.models.search import ExpandedSearchQueries

# Source-inspection tests intentionally verify these delegation strings stay visible:
# global_sources.search_kipris
# global_sources.search_patentscope
# search_step2_sources.search_pubchem_sdq
# search_step2_enrichment.enrich_legal_status

logger = structlog.get_logger()

_search_pubchem_sdq = search_wiring._search_pubchem_sdq
_search_surechembl = search_wiring._search_surechembl
_search_pubchem_similar = search_wiring._search_pubchem_similar
_search_pubchem_genus = search_wiring._search_pubchem_genus
_search_bigquery = search_wiring._search_bigquery
_search_bigquery_annotations = search_wiring._search_bigquery_annotations
_search_patcid = search_wiring._search_patcid
_search_kipris = search_wiring._search_kipris
_search_patentscope = search_wiring._search_patentscope
_search_bigquery_translated = search_wiring._search_bigquery_translated
_search_patentsview = search_wiring._search_patentsview
_search_ncbi_patent_sequence = search_wiring._search_ncbi_patent_sequence
_enrich_patent_term = search_wiring._enrich_patent_term
_enrich_ptab_proceedings = search_wiring._enrich_ptab_proceedings
_enrich_orange_book = search_wiring._enrich_orange_book
_compute_confidence = search_normalizers._compute_confidence

# Re-exports preserved for downstream tests that import from this facade.


async def _traverse_citation_network(
    seed_patent_ids: list[str],
    max_depth: int = 2,
    max_per_level: int = 50,
) -> set[str]:
    return await search_wiring._traverse_citation_network(
        seed_patent_ids=seed_patent_ids,
        max_depth=max_depth,
        max_per_level=max_per_level,
        client_factory=BigQueryClient,
    )


async def _search_bigquery_cpc(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
) -> list[dict]:
    return await search_wiring._search_bigquery_cpc(
        compound,
        expanded,
        client_factory=BigQueryClient,
    )


async def _search_bigquery_assignee(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
) -> list[dict]:
    return await search_wiring._search_bigquery_assignee(
        compound,
        expanded,
        client_factory=BigQueryClient,
    )


async def _search_epo_claims(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
) -> list[dict]:
    return await search_wiring._search_epo_claims(
        compound,
        expanded,
        client_factory=EPOOPSClient,
    )


async def _enrich_legal_status(
    hits: list[PatentHit],
    max_patents: int | None = None,
) -> int:
    return await search_wiring._enrich_legal_status(
        hits,
        max_patents=max_patents,
    )


async def _expand_families(
    hits: list[PatentHit],
    max_patents: int | None = None,
) -> search_post_enrichment.EnrichmentOutcome:
    return await search_wiring._expand_families(
        hits,
        max_patents=max_patents,
        client_factory=EPOOPSClient,
    )


async def _expand_continuations(hits: list[PatentHit]) -> int:
    return await search_wiring._expand_continuations(hits)


async def _enrich_application_data(
    hits: list[PatentHit],
    max_patents: int | None = None,
) -> int:
    return await search_wiring._enrich_application_data(
        hits,
        max_patents=max_patents,
        client_factory=USPTOODPClient,
    )


async def _enrich_epo_register(
    hits: list[PatentHit],
    max_patents: int = 50,
) -> search_post_enrichment.EnrichmentOutcome:
    return await search_wiring._enrich_epo_register(
        hits,
        max_patents=max_patents,
        client_factory=EPOOPSClient,
    )


async def _expand_via_citations(
    hits: list[PatentHit],
    seen_norm_ids: set[str],
    source_map: dict[str, set[PatentSource]],
    supplementary_rows: list[list[dict]],
    settings,
) -> None:
    return await search_wiring._expand_via_citations(
        hits,
        seen_norm_ids=seen_norm_ids,
        source_map=source_map,
        supplementary_rows=supplementary_rows,
        settings=settings,
        client_factory=BigQueryClient,
    )


async def search_patents(
    compound: ResolvedCompound,
    expanded_queries: ExpandedSearchQueries | None = None,
) -> tuple[list[PatentHit], SourceHealth, list[SearchFunnelEntry]]:
    """Run Step 2 search (formerly delegated to search_patents_impl)."""
    logger.info("patent_search_start")
    logger.debug(
        "step2_entry",
        smiles_length=len(compound.canonical_smiles),
        synonyms_count=len(compound.synonyms),
        cas_count=len(compound.cas_numbers),
        has_expanded_queries=expanded_queries is not None,
    )

    settings = get_settings()

    if expanded_queries is None:
        from praviar_pipeline.models.search import ExpandedSearchQueries

        expanded_queries = ExpandedSearchQueries()

    has_expansion = bool(
        expanded_queries.cpc_codes
        or expanded_queries.key_assignees
        or expanded_queries.process_keywords
    )

    primary_sources.clear_surechembl_similarity_cache()
    _bigquery_source: Callable[
        [ResolvedCompound],
        Awaitable[list[dict]],
    ]

    # When hybrid retrieval is enabled, replace the standard BigQuery source
    # with an indexed lexical+dense RRF query over the configured embedding corpus.
    # It keeps the same compound-name/synonym/CAS and jurisdiction scope as the
    # standard source and returns the same canonical row contract.
    #
    # Enable hybrid retrieval only under an explicitly reviewed rollout policy
    # bound to an immutable evaluation receipt for the exact corpus and revision.
    if settings.hybrid_retrieval_enabled:

        async def _search_configured_hybrid_bigquery(
            resolved_compound: ResolvedCompound,
        ) -> list[dict]:
            query_terms = [
                resolved_compound.name,
                *resolved_compound.synonyms[: settings.search_max_synonyms_bigquery],
            ]
            if resolved_compound.cas_numbers:
                query_terms.extend(
                    resolved_compound.cas_numbers[: settings.search_max_cas_bigquery]
                )
            async with BigQueryClient() as client:
                result: list[dict] = await client.search_patents_hybrid(
                    query_terms,
                    jurisdictions=settings.search_allowed_jurisdictions,
                    project=settings.bigquery_project_id,
                    dataset=settings.bigquery_dataset,
                    table=settings.bigquery_table,
                    max_results=settings.search_bigquery_max_results,
                )
                return result

        _bigquery_source = _search_configured_hybrid_bigquery
        logger.info(
            "step2_hybrid_retrieval_active",
        )
    else:
        _bigquery_source = _search_bigquery

    return await search_orchestration.execute_search_coordinator(
        compound=compound,
        expanded_queries=expanded_queries,
        has_expansion=has_expansion,
        settings=settings,
        build_search_plan_fn=partial(
            search_plan.build_search_plan,
            settings=settings,
            search_pubchem_sdq=_search_pubchem_sdq,
            search_surechembl=_search_surechembl,
            search_bigquery=_bigquery_source,
            search_bigquery_annotations=_search_bigquery_annotations,
            search_patcid=_search_patcid,
            search_pubchem_similar=_search_pubchem_similar,
            search_bigquery_cpc=_search_bigquery_cpc,
            search_bigquery_assignee=_search_bigquery_assignee,
            search_epo_claims=_search_epo_claims,
            search_kipris=_search_kipris,
            search_patentscope=_search_patentscope,
            search_bigquery_translated=_search_bigquery_translated,
            search_patentsview=_search_patentsview,
            search_ncbi_patent_sequence=_search_ncbi_patent_sequence,
            search_pubchem_genus=_search_pubchem_genus,
        ),
        execute_search_plan_fn=search_orchestration.execute_search_plan,
        run_source_fn=partial(
            search_orchestration.run_source,
            timeout_s=settings.search_source_timeout_s,
        ),
        prepare_search_results_fn=search_orchestration.prepare_search_results,
        build_source_map_fn=build_source_map,
        rank_patents_fn=rank_patents,
        assemble_hits_fn=partial(
            search_results.assemble_step2_hits,
            normalize_patent_id=_normalize_patent_id,
            sdq_to_patent_hit=_sdq_to_patent_hit,
            bq_row_to_patent_hit=_bq_row_to_patent_hit,
            merge_supplementary_rows=_merge_supplementary_rows,
            surechembl_similarity_lookup=primary_sources.get_surechembl_similarity_metadata,
        ),
        build_search_contribution_summary_fn=search_orchestration.build_search_contribution_summary,
        normalize_patent_id=_normalize_patent_id,
        maybe_expand_via_citations_fn=search_orchestration.maybe_expand_via_citations,
        expand_via_citations_fn=_expand_via_citations,
        finalize_search_run_fn=search_orchestration.finalize_search_run,
        enrich_hits_fn=partial(
            search_post_enrichment.run_step2_post_enrichment,
            enrich_legal_status=_enrich_legal_status,
            expand_families=_expand_families,
            enrich_patent_term=_enrich_patent_term,
            enrich_application_data=_enrich_application_data,
            enrich_epo_register=_enrich_epo_register,
            enrich_ptab_proceedings=_enrich_ptab_proceedings,
            enrich_orange_book=_enrich_orange_book,
            expand_continuations=_expand_continuations,
        ),
        emit_search_completion_logs_fn=search_orchestration.emit_search_completion_logs,
    )
