"""Compatibility wrappers and dependency wiring for Step 2 search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.clients.ncbi_patent_sequence import NCBIPatentSequenceClient
from praviar_pipeline.clients.pubchem import PubChemClient
from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.pipeline.search import citation as search_citation
from praviar_pipeline.pipeline.search import (
    enrichment as search_enrichment,
)
from praviar_pipeline.pipeline.search import (
    expansion_sources,
    global_sources,
    primary_sources,
)
from praviar_pipeline.pipeline.search.normalizers import _derive_legal_status

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit, PatentSource
    from praviar_pipeline.models.search import ExpandedSearchQueries


async def _traverse_citation_network(
    seed_patent_ids: list[str],
    max_depth: int = 2,
    max_per_level: int = 50,
    *,
    client_factory=BigQueryClient,
) -> set[str]:
    return await search_citation._traverse_citation_network(
        seed_patent_ids=seed_patent_ids,
        max_depth=max_depth,
        max_per_level=max_per_level,
        client_factory=client_factory,
    )


async def _search_pubchem_sdq(
    compound: ResolvedCompound,
) -> list[dict]:
    return await primary_sources.search_pubchem_sdq(compound)


async def _search_surechembl(
    compound: ResolvedCompound,
) -> list[tuple[str, PatentSource]]:
    return await primary_sources.search_surechembl(compound)


async def _search_pubchem_similar(
    compound: ResolvedCompound,
) -> list[tuple[str, PatentSource]]:
    return await primary_sources.search_pubchem_similar(compound)


async def _search_pubchem_genus(
    compound: ResolvedCompound,
    *,
    client_factory=PubChemClient,
) -> list[dict]:
    return await primary_sources.search_pubchem_genus(
        compound,
        client_factory=client_factory,
    )


async def _search_bigquery(
    compound: ResolvedCompound,
) -> list[dict]:
    return await primary_sources.search_bigquery(compound)


async def _search_bigquery_annotations(
    compound: ResolvedCompound,
) -> list[tuple[str, PatentSource]]:
    return await primary_sources.search_bigquery_annotations(compound)


async def _search_patcid(
    compound: ResolvedCompound,
) -> list[tuple[str, PatentSource]]:
    return await primary_sources.search_patcid(compound)


async def _search_bigquery_cpc(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=BigQueryClient,
) -> list[dict]:
    return await expansion_sources.search_bigquery_cpc(
        compound,
        expanded,
        client_factory=client_factory,
    )


async def _search_bigquery_assignee(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=BigQueryClient,
) -> list[dict]:
    return await expansion_sources.search_bigquery_assignee(
        compound,
        expanded,
        client_factory=client_factory,
    )


async def _search_epo_claims(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=EPOOPSClient,
) -> list[dict]:
    return await expansion_sources.search_epo_claims(
        compound,
        expanded,
        client_factory=client_factory,
    )


async def _search_kipris(
    compound: ResolvedCompound,
) -> list[dict]:
    return await global_sources.search_kipris(compound)


async def _search_patentscope(
    compound: ResolvedCompound,
) -> list[dict]:
    return await global_sources.search_patentscope(compound)


async def _search_bigquery_translated(
    compound: ResolvedCompound,
) -> list[dict]:
    return await global_sources.search_bigquery_translated(compound)


async def _search_patentsview(
    compound: ResolvedCompound,
) -> list[dict]:
    return await global_sources.search_patentsview(compound)


async def _search_ncbi_patent_sequence(
    compound: ResolvedCompound,
    *,
    client_factory=NCBIPatentSequenceClient,
) -> list[dict]:
    """Run the required public patent-protein lane for biologic/peptide matters."""
    if compound.compound_type not in {"biologic", "peptide"}:
        return []
    if not compound.protein_subunit_sequences:
        raise ConfigurationError(
            "Exact FDA GSRS identity has no supported public protein subunit sequence",
            source="ncbi_patent_sequence",
            step="search",
        )
    settings = get_settings()
    async with client_factory() as client:
        result: list[dict] = await client.search_protein_patents(
            compound.protein_subunit_sequences,
            allowed_jurisdictions=settings.search_allowed_jurisdictions,
            max_hits=settings.ncbi_patent_sequence_max_hits,
            min_identity=settings.ncbi_patent_sequence_min_identity,
            min_query_coverage=settings.ncbi_patent_sequence_min_query_coverage,
            max_polls=settings.ncbi_patent_sequence_max_polls,
            poll_interval_seconds=(settings.ncbi_patent_sequence_poll_interval_seconds),
        )
    return result


async def _enrich_legal_status(
    hits: list[PatentHit],
    max_patents: int | None = None,
) -> int:
    return await search_enrichment.enrich_legal_status(
        hits,
        max_patents=max_patents,
        derive_legal_status=_derive_legal_status,
    )


async def _expand_families(
    hits: list[PatentHit],
    max_patents: int | None = None,
    *,
    client_factory=EPOOPSClient,
) -> search_enrichment.EnrichmentOutcome:
    return await search_enrichment.expand_families(
        hits,
        max_patents=max_patents,
        client_factory=client_factory,
    )


async def _expand_continuations(hits: list[PatentHit]) -> int:
    """Thread ``expand_continuations`` into Step 2 enrichment with captured factories.

    Disabled mode returns zero. Enabled mode propagates configuration, timeout,
    authentication, and source failures so missing lineage coverage is never
    represented as a genuine zero-result search.
    """
    import asyncio

    import structlog

    from praviar_pipeline.config import get_settings
    from praviar_pipeline.pipeline.search.continuation_expansion import expand_continuations

    logger = structlog.get_logger()
    settings = get_settings()
    if not getattr(settings, "continuation_expansion_enabled", True):
        return 0
    timeout_s = settings.continuation_expansion_timeout_s
    try:
        return await asyncio.wait_for(
            expand_continuations(
                hits,
                max_patents=getattr(settings, "continuation_max_patents", 50),
                max_depth=getattr(settings, "continuation_max_depth", 2),
                odp_client_factory=USPTOODPClient,
                epo_client_factory=EPOOPSClient,
            ),
            timeout=timeout_s,
        )
    except TimeoutError:
        logger.warning("continuation_expansion_timeout", timeout_s=timeout_s)
        raise SourceUnavailableError(
            "continuation_expansion",
            "continuation expansion timed out",
        ) from None


async def _enrich_patent_term(
    hits: list[PatentHit],
    max_patents: int | None = None,
) -> int:
    return await search_enrichment.enrich_patent_term(hits, max_patents=max_patents)


async def _enrich_application_data(
    hits: list[PatentHit],
    max_patents: int | None = None,
    *,
    client_factory=USPTOODPClient,
) -> int:
    return await search_enrichment.enrich_application_data(
        hits,
        max_patents=max_patents,
        client_factory=client_factory,
    )


async def _enrich_epo_register(
    hits: list[PatentHit],
    max_patents: int = 50,
    *,
    client_factory=EPOOPSClient,
) -> search_enrichment.EnrichmentOutcome:
    return await search_enrichment.enrich_epo_register(
        hits,
        max_patents=max_patents,
        client_factory=client_factory,
    )


async def _enrich_ptab_proceedings(
    hits: list[PatentHit],
    max_patents: int = 50,
) -> search_enrichment.EnrichmentOutcome:
    return await search_enrichment.enrich_ptab_proceedings(hits, max_patents=max_patents)


async def _enrich_orange_book(
    hits: list[PatentHit],
) -> search_enrichment.EnrichmentOutcome:
    return await search_enrichment.enrich_orange_book(hits)


async def _expand_via_citations(
    hits: list[PatentHit],
    seen_norm_ids: set[str],
    source_map: dict[str, set[PatentSource]],
    supplementary_rows: list[list[dict]],
    settings,
    *,
    client_factory=BigQueryClient,
) -> None:
    from praviar_pipeline.models.patent import PatentSource
    from praviar_pipeline.pipeline.search.normalizers import _bq_row_to_patent_hit

    await search_citation.expand_via_citations(
        hits,
        seen_norm_ids=seen_norm_ids,
        source_map=source_map,
        supplementary_rows=supplementary_rows,
        settings=settings,
        client_factory=client_factory,
        row_to_patent_hit=_bq_row_to_patent_hit,
        patent_source=PatentSource.BIGQUERY,
    )
