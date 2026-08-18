"""Shared models and type aliases for Step 2 search orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit, PatentSource


@dataclass
class SearchExecutionSummary:
    sdq_results: list[dict] = field(default_factory=list)
    surechembl_results: list[tuple[str, PatentSource]] = field(default_factory=list)
    bigquery_rows: list[dict] = field(default_factory=list)
    bq_annotation_results: list[tuple[str, PatentSource]] = field(default_factory=list)
    patcid_results: list[tuple[str, PatentSource]] = field(default_factory=list)
    pubchem_similar_results: list[tuple[str, PatentSource]] = field(default_factory=list)
    pubchem_genus_results: list[dict] = field(default_factory=list)
    cpc_search_rows: list[dict] = field(default_factory=list)
    assignee_search_rows: list[dict] = field(default_factory=list)
    epo_search_results: list[dict] = field(default_factory=list)
    lens_results: list[dict] = field(default_factory=list)
    kipris_results: list[dict] = field(default_factory=list)
    patentscope_results: list[dict] = field(default_factory=list)
    bq_translated_results: list[dict] = field(default_factory=list)
    patentsview_results: list[dict] = field(default_factory=list)
    ncbi_patent_sequence_results: list[dict] = field(default_factory=list)
    health: SourceHealth = field(default_factory=lambda: SourceHealth(entries=[]))
    failures: dict[str, str] = field(default_factory=dict)
    source_timings: dict[str, int] = field(default_factory=dict)


@dataclass
class SearchContributionSummary:
    source_metrics: dict[str, dict[str, int]]
    total_unique_patents: int
    sdq_total: int
    final_source_counts: dict[str, int]
    final_sole_source: dict[str, int]


@dataclass
class PreparedSearchResults:
    source_map: dict[str, set[PatentSource]]
    multi_source_ids: set[str]
    ranked_sdq: list[dict]
    hits: list[PatentHit]
    seen_norm_ids: set[str]
    contribution_summary: SearchContributionSummary
    ranking_audit_rows: list[dict] = field(default_factory=list)


@dataclass
class PreparedRankingInputs:
    source_map: dict[str, set[PatentSource]]
    multi_source_ids: set[str]
    ranked_sdq: list[dict]
    ranking_audit_rows: list[dict] = field(default_factory=list)


SearchRunOutcome = tuple[str, Any | None, Exception | None, int]
RunSourceFn = Callable[[str, Awaitable[Any]], Awaitable[SearchRunOutcome]]


class SearchPlan(list[tuple[str, Awaitable[Any]]]):
    """Runnable source tasks plus health entries for sources skipped before I/O."""

    def __init__(
        self,
        tasks: list[tuple[str, Awaitable[Any]]] | None = None,
        *,
        planned_entries: list[SourceHealthEntry] | None = None,
    ) -> None:
        super().__init__(tasks or [])
        self.planned_entries = planned_entries or []
