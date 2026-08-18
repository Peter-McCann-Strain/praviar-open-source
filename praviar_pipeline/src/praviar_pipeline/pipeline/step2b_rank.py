"""Step 2b: Patent Ranking Funnel — score and rank SDQ results before LLM triage.

Pipeline: SDQ results -> Hard filters -> Multi-signal scoring -> BM25 re-rank -> Top N

The configured hard filters, ranking signals and final result cap bound the set
passed to downstream triage. This module makes no runtime cost or volume claim.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.ranking.blending import (
    build_final_ranking as _build_final_ranking,
)
from praviar_pipeline.pipeline.ranking.pipeline import (
    rank_patents_impl,
)
from praviar_pipeline.pipeline.ranking.rerankers import (
    bm25_rerank as _bm25_rerank_impl,
)
from praviar_pipeline.pipeline.ranking.rerankers import (
    embedding_rerank as _embedding_rerank_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    apply_hard_filters as _apply_hard_filters_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    compute_composite_score as _compute_composite_score_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    count_cids as _count_cids_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    parse_cpc_codes as _parse_cpc_codes_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    score_compound_count as _score_compound_count_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    score_cpc_relevance as _score_cpc_relevance_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    score_multi_source as _score_multi_source_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    score_recency as _score_recency_impl,
)
from praviar_pipeline.pipeline.ranking.scoring import (
    score_title_keyword as _score_title_keyword_impl,
)
from praviar_pipeline.utils.dates import parse_date as _parse_date

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()


def _count_cids(cids_field: str | list | None) -> int:
    """Compatibility wrapper for extracted CID counting."""
    return _count_cids_impl(cids_field)


def _parse_cpc_codes(classification: str | list | None) -> list[str]:
    """Compatibility wrapper for extracted CPC parsing."""
    return _parse_cpc_codes_impl(classification)


# -- Hard Filters -------------------------------------------------------------


def _apply_hard_filters(
    patents: list[dict],
    include_expired: bool = True,
    expired_grace_years: int = 5,
    allowed_jurisdictions: list[str] | None = None,
    collect_audit: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    """Compatibility wrapper for extracted hard filters."""
    return _apply_hard_filters_impl(
        patents,
        include_expired=include_expired,
        expired_grace_years=expired_grace_years,
        allowed_jurisdictions=allowed_jurisdictions,
        collect_audit=collect_audit,
    )


# -- Scoring Signals -----------------------------------------------------------


def _score_cpc_relevance(cpc_codes: list[str]) -> float:
    """Compatibility wrapper for extracted CPC scoring."""
    return _score_cpc_relevance_impl(cpc_codes)


def _score_compound_count(cid_count: int) -> float:
    """Compatibility wrapper for extracted compound-count scoring."""
    return _score_compound_count_impl(cid_count)


def _score_recency(priority_date: date | None) -> float:
    """Compatibility wrapper for extracted recency scoring."""
    return _score_recency_impl(priority_date)


def _score_title_keyword(title: str, compound: ResolvedCompound) -> float:
    """Compatibility wrapper for extracted title-keyword scoring."""
    return _score_title_keyword_impl(title, compound)


def _score_multi_source(patent_id: str, multi_source_ids: set[str]) -> float:
    """Compatibility wrapper for extracted multi-source scoring."""
    return _score_multi_source_impl(patent_id, multi_source_ids)


def _compute_composite_score(
    cpc_score: float,
    compound_count_score: float,
    recency_score: float,
    title_score: float,
    multi_source_score: float,
) -> float:
    """Compatibility wrapper for extracted composite-score blending."""
    return _compute_composite_score_impl(
        cpc_score,
        compound_count_score,
        recency_score,
        title_score,
        multi_source_score,
    )


# -- BM25 Re-ranking ----------------------------------------------------------


def _bm25_rerank(
    patents: list[dict],
    compound: ResolvedCompound,
    top_k: int = 500,
) -> list[tuple[dict, float]]:
    """Compatibility wrapper for extracted BM25 reranking."""
    return _bm25_rerank_impl(patents, compound, top_k=top_k)


# -- Embedding Re-ranking (optional) -------------------------------------------


def _embedding_rerank(
    patents: list[dict],
    compound: ResolvedCompound,
    top_k: int = 500,
) -> list[tuple[dict, float]] | None:
    """Compatibility wrapper for extracted embedding reranking."""
    return _embedding_rerank_impl(patents, compound, top_k=top_k)


# -- Main Ranking Function -----------------------------------------------------


def rank_patents(
    sdq_results: list[dict],
    compound: ResolvedCompound,
    multi_source_ids: set[str] | None = None,
    max_results: int | None = None,
    collect_audit: bool = False,
) -> list[dict]:
    """Multi-signal ranking funnel: hard filters -> composite scoring -> BM25 re-rank.

    Args:
        sdq_results: Raw patent dicts from PubChem SDQ API.
        compound: The resolved compound being analyzed.
        multi_source_ids: Normalized patent IDs found by BigQuery/PatCID/SureChEMBL.
        max_results: Maximum patents to return (default from settings).
        collect_audit: Whether to collect audit trail data.

    Returns:
        Ranked patent dicts with a ``_retrieval_scores`` provenance payload.
    """
    settings = get_settings()
    if max_results is None:
        max_results = settings.search_max_ranked_results
    if multi_source_ids is None:
        multi_source_ids = set()

    return rank_patents_impl(
        sdq_results,
        compound,
        settings=settings,
        logger=logger,
        multi_source_ids=multi_source_ids,
        max_results=max_results,
        collect_audit=collect_audit,
        apply_hard_filters_fn=_apply_hard_filters,
        parse_cpc_codes_fn=_parse_cpc_codes,
        count_cids_fn=_count_cids,
        parse_date_fn=_parse_date,
        compute_composite_score_fn=_compute_composite_score,
        score_cpc_relevance_fn=_score_cpc_relevance,
        score_compound_count_fn=_score_compound_count,
        score_recency_fn=_score_recency,
        score_title_keyword_fn=_score_title_keyword,
        score_multi_source_fn=_score_multi_source,
        bm25_rerank_fn=_bm25_rerank,
        embedding_rerank_fn=_embedding_rerank,
        build_final_ranking_fn=_build_final_ranking,
    )
