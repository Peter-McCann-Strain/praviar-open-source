"""Global source adapters for the Step 2 patent search pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.kipris import KIPRISClient
from praviar_pipeline.clients.lens import LensClient
from praviar_pipeline.clients.patentscope import PatentScopeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound


async def search_lens(compound: ResolvedCompound) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.lens_api_key:
        raise ConfigurationError("Lens API key not configured", source="lens", step="search")

    async with LensClient() as client:
        keywords = [compound.name, *compound.synonyms[:5]]
        return cast(
            "list[dict[str, Any]]",
            await client.search_patents(
                keywords=keywords,
                max_results=settings.lens_max_patent_results,
            ),
        )


async def search_kipris(compound: ResolvedCompound) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.kipris_api_key:
        raise ConfigurationError("KIPRIS API key not configured", source="kipris", step="search")
    if "KR" not in settings.search_allowed_jurisdictions:
        raise ConfigurationError(
            "KIPRIS source scheduled without KR in search_allowed_jurisdictions",
            source="kipris",
            step="search",
        )

    async with KIPRISClient() as client:
        keywords = [compound.name, *compound.synonyms[:3]]
        return cast(
            "list[dict[str, Any]]",
            await client.search_patents(
                keywords=keywords,
                max_results=settings.kipris_max_results,
            ),
        )


async def search_patentscope(compound: ResolvedCompound) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.patentscope_username or not settings.patentscope_password:
        raise ConfigurationError(
            "PatentScope credentials not configured",
            source="patentscope",
            step="search",
        )

    non_english = {"JP", "KR", "CN", "IN", "DE", "FR"}
    if not non_english.intersection(settings.search_allowed_jurisdictions):
        raise ConfigurationError(
            "PatentScope source scheduled without non-English jurisdictions",
            source="patentscope",
            step="search",
        )

    async with PatentScopeClient() as client:
        keywords = [compound.name, *compound.synonyms[:5]]
        return cast(
            "list[dict[str, Any]]",
            await client.cross_lingual_search(
                keywords=keywords,
                source_lang="EN",
                target_langs=["JA", "KO", "ZH"],
                max_results=settings.patentscope_max_results,
            ),
        )


async def search_bigquery_translated(compound: ResolvedCompound) -> list[dict[str, Any]]:
    async with BigQueryClient() as client:
        settings = get_settings()
        search_terms = [compound.name, *compound.synonyms[:10]]
        non_english_jurisdictions = [
            jurisdiction
            for jurisdiction in settings.search_allowed_jurisdictions
            if jurisdiction in ("JP", "KR", "CN", "IN", "DE", "FR")
        ]
        if not non_english_jurisdictions:
            return []
        return cast(
            "list[dict[str, Any]]",
            await client.search_translated_patents(
                synonyms=search_terms,
                jurisdictions=non_english_jurisdictions,
                max_results=settings.search_bigquery_max_results,
            ),
        )


async def search_patentsview(compound: ResolvedCompound) -> list[dict]:
    settings = get_settings()
    if not settings.patentsview_api_key:
        raise ConfigurationError(
            "PatentsView API key not configured",
            source="patentsview",
            step="search",
        )

    from praviar_pipeline.clients.patentsview import PatentsViewClient

    async with PatentsViewClient() as client:
        results = await client.search_by_compound_keywords(
            compound_name=compound.name,
            synonyms=compound.synonyms[:10],
            size=100,
        )

        normalized: list[dict] = []
        for row in results:
            patent_id = row.get("patent_id", "")
            if not patent_id:
                continue
            kind = row.get("patent_kind", "B2")
            publication_number = patent_id if patent_id.startswith("US") else f"US{patent_id}{kind}"

            normalized.append(
                {
                    "publication_number": publication_number,
                    "title_localized": row.get("patent_title"),
                    "abstract_localized": row.get("patent_abstract"),
                    "assignee_organization": row.get("assignee_organization"),
                    "cpc": row.get("cpc_subgroup_ids", []),
                    "publication_date": row.get("patent_date"),
                }
            )

        return normalized
