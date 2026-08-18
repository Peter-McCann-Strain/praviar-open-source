"""Search-plan builders for the Step 2 patent search pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from praviar_pipeline.pipeline.search.models import SearchPlan
from praviar_pipeline.pipeline.search.source_registry import (
    SOURCE_CAPABILITIES,
    missing_required_settings,
    source_is_enabled,
    source_is_requested,
    source_not_configured_entry,
    source_skipped_entry,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.report import SourceHealthEntry
    from praviar_pipeline.models.search import ExpandedSearchQueries


def build_search_plan(
    *,
    compound: ResolvedCompound,
    expanded_queries: ExpandedSearchQueries,
    has_expansion: bool,
    settings: Any,
    search_pubchem_sdq: Callable[[ResolvedCompound], Awaitable[Any]],
    search_surechembl: Callable[[ResolvedCompound], Awaitable[Any]],
    search_bigquery: Callable[[ResolvedCompound], Awaitable[Any]],
    search_bigquery_annotations: Callable[[ResolvedCompound], Awaitable[Any]],
    search_patcid: Callable[[ResolvedCompound], Awaitable[Any]],
    search_pubchem_similar: Callable[[ResolvedCompound], Awaitable[Any]],
    search_bigquery_cpc: Callable[[ResolvedCompound, ExpandedSearchQueries], Awaitable[Any]],
    search_bigquery_assignee: Callable[[ResolvedCompound, ExpandedSearchQueries], Awaitable[Any]],
    search_epo_claims: Callable[[ResolvedCompound, ExpandedSearchQueries], Awaitable[Any]],
    search_kipris: Callable[[ResolvedCompound], Awaitable[Any]],
    search_patentscope: Callable[[ResolvedCompound], Awaitable[Any]],
    search_bigquery_translated: Callable[[ResolvedCompound], Awaitable[Any]],
    search_patentsview: Callable[[ResolvedCompound], Awaitable[Any]],
    search_ncbi_patent_sequence: (Callable[[ResolvedCompound], Awaitable[Any]] | None) = None,
    search_pubchem_genus: Callable[[ResolvedCompound], Awaitable[Any]] | None = None,
) -> SearchPlan:
    """Build the ordered source plan for Step 2 search execution."""
    tasks: list[tuple[str, Awaitable[Any]]] = []
    planned_entries: list[SourceHealthEntry] = []

    def _append_source(name: str, coro_factory: Callable[[], Awaitable[Any]]) -> None:
        capability = SOURCE_CAPABILITIES[name]
        if not source_is_requested(capability, settings):
            return
        if not source_is_enabled(capability, settings):
            planned_entries.append(
                source_skipped_entry(
                    capability,
                    reason=f"Disabled by {capability.enabled_attr}",
                )
            )
            return
        missing = missing_required_settings(capability, settings)
        if missing:
            planned_entries.append(source_not_configured_entry(capability, missing_fields=missing))
            return
        tasks.append((name, coro_factory()))

    _append_source("pubchem_sdq", lambda: search_pubchem_sdq(compound))

    _append_source("surechembl", lambda: search_surechembl(compound))

    _append_source("bigquery", lambda: search_bigquery(compound))
    _append_source("bigquery_annotations", lambda: search_bigquery_annotations(compound))

    _append_source("patcid", lambda: search_patcid(compound))

    _append_source("pubchem_similar", lambda: search_pubchem_similar(compound))
    if getattr(compound, "compound_type", "small_molecule") == "small_molecule":
        if (
            source_is_enabled(SOURCE_CAPABILITIES["pubchem_genus"], settings)
            and search_pubchem_genus is None
        ):
            raise RuntimeError("PubChem genus search adapter is not wired")
        if search_pubchem_genus is not None:
            _append_source("pubchem_genus", lambda: search_pubchem_genus(compound))
    else:
        planned_entries.append(
            source_skipped_entry(
                SOURCE_CAPABILITIES["pubchem_genus"],
                reason="Not applicable to a biologic or peptide matter",
            )
        )

    if has_expansion:
        _append_source("cpc_search", lambda: search_bigquery_cpc(compound, expanded_queries))
        _append_source(
            "assignee_search",
            lambda: search_bigquery_assignee(compound, expanded_queries),
        )
        _append_source("epo_search", lambda: search_epo_claims(compound, expanded_queries))

    _append_source("kipris", lambda: search_kipris(compound))
    _append_source("patentscope", lambda: search_patentscope(compound))
    _append_source("bigquery_translated", lambda: search_bigquery_translated(compound))
    _append_source("patentsview", lambda: search_patentsview(compound))
    if getattr(compound, "compound_type", "small_molecule") in {
        "biologic",
        "peptide",
    }:
        if search_ncbi_patent_sequence is None:
            raise RuntimeError("NCBI patent-sequence search adapter is not wired")
        _append_source(
            "ncbi_patent_sequence",
            lambda: search_ncbi_patent_sequence(compound),
        )
    else:
        planned_entries.append(
            source_skipped_entry(
                SOURCE_CAPABILITIES["ncbi_patent_sequence"],
                reason="Not applicable to a small-molecule matter",
            )
        )
    return SearchPlan(tasks, planned_entries=planned_entries)
