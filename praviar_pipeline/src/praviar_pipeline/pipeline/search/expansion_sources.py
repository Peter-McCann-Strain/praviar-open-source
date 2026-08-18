"""Expanded-query search adapters for the Step 2 patent search pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.search import ExpandedSearchQueries


async def search_bigquery_cpc(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=BigQueryClient,
) -> list[dict]:
    if not expanded.cpc_codes:
        return []

    keywords = [compound.name, *expanded.process_keywords[:10]]
    keywords.extend(expanded.patent_synonyms[:5])

    async with client_factory() as client:
        settings = get_settings()
        return cast(
            "list[dict]",
            await client.search_by_cpc_and_keywords(
                cpc_codes=expanded.cpc_codes,
                keywords=keywords,
                max_results=settings.search_bigquery_max_results,
                jurisdictions=settings.search_allowed_jurisdictions,
            ),
        )


async def search_bigquery_assignee(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=BigQueryClient,
) -> list[dict]:
    del compound
    if not expanded.key_assignees:
        return []

    async with client_factory() as client:
        settings = get_settings()
        return cast(
            "list[dict]",
            await client.search_by_assignee(
                assignees=expanded.key_assignees,
                cpc_codes=expanded.cpc_codes or None,
                max_results=settings.search_bigquery_max_results,
                jurisdictions=settings.search_allowed_jurisdictions,
            ),
        )


async def search_epo_claims(
    compound: ResolvedCompound,
    expanded: ExpandedSearchQueries,
    *,
    client_factory=EPOOPSClient,
) -> list[dict]:
    settings = get_settings()
    if not settings.ops_consumer_key or not settings.ops_consumer_secret:
        raise ConfigurationError(
            "EPO OPS credentials not configured",
            source="epo_search",
            step="search",
        )

    # Build claim keywords: prefer compound.synonyms (contains trade/common names
    # like "Bakuchiol") over expanded.patent_synonyms (LLM-generated IUPAC
    # variants) — trade names appear far more often in actual patent claims.
    seen: set[str] = set()
    claim_keywords: list[str] = []
    candidate_terms = (
        list(compound.synonyms[:3]) + [compound.name] + (expanded.patent_synonyms or [])
    )
    for term in candidate_terms:
        clean = term.strip()
        if not clean or clean.lower() in seen:
            continue
        # Skip CAS numbers and InChI-like strings — not valid CQL claim terms
        if clean[:3].isdigit() or clean.startswith("InChI"):
            continue
        seen.add(clean.lower())
        claim_keywords.append(clean)
        if len(claim_keywords) == 3:
            break

    async with client_factory() as client:
        return cast(
            "list[dict]",
            await client.search_published_data(
                cpc_codes=expanded.cpc_codes[:3] if expanded.cpc_codes else None,
                claim_keywords=claim_keywords,
                applicants=expanded.key_assignees[:2] if expanded.key_assignees else None,
                max_results=100,
            ),
        )
