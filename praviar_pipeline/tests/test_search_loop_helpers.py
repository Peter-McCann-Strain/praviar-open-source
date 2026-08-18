"""Tests for pure search-loop helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.triage import Relevance
from praviar_pipeline.pipeline.search.loop_helpers import (
    compute_search_stats,
    compute_triage_stats,
    merge_queries,
)


def test_merge_queries_deduplicates_and_preserves_order() -> None:
    base = ExpandedSearchQueries(
        patent_synonyms=["aspirin", "acetylsalicylic acid"],
        cpc_codes=["C07C"],
        key_assignees=["Bayer"],
        process_keywords=["synthesis"],
        compound_class_terms=["NSAID"],
    )
    new = ExpandedSearchQueries(
        patent_synonyms=["aspirin", "ASA"],
        cpc_codes=["C07C", "A61K"],
        key_assignees=["Pfizer"],
        process_keywords=["synthesis", "acetylation"],
        compound_class_terms=["analgesic"],
    )

    merged = merge_queries(base, new)

    assert merged.patent_synonyms == ["aspirin", "acetylsalicylic acid", "ASA"]
    assert merged.cpc_codes == ["C07C", "A61K"]
    assert merged.key_assignees == ["Bayer", "Pfizer"]
    assert merged.process_keywords == ["synthesis", "acetylation"]
    assert merged.compound_class_terms == ["NSAID", "analgesic"]


def test_compute_search_stats_formats_empty_state() -> None:
    assert compute_search_stats([]) == "No patents found."


def test_compute_search_stats_includes_distributions() -> None:
    hit = MagicMock()
    hit.patent_id = "US123"
    hit.assignees = ["Corp A", "Corp A", "Corp B"]
    hit.cpc_codes = ["C12P7/46", "A61K31/00"]
    hit.sources = [MagicMock(value="pubchem"), MagicMock(value="lens")]
    hit.filing_date = "2024-01-01"
    hit.confidence_score = 0.9

    stats = compute_search_stats([hit])

    assert "Total unique patents: 1" in stats
    assert "Confidence distribution: high=1, medium=0, low=0" in stats
    assert "US: 1" in stats
    assert "Corp A: 2" in stats
    assert "C12P: 1" in stats
    assert "pubchem: 1" in stats


def test_compute_triage_stats_formats_empty_state() -> None:
    assert compute_triage_stats([], []) == "No patents triaged yet."


def test_compute_triage_stats_includes_counts() -> None:
    relevant = MagicMock()
    relevant.relevance = Relevance.RELEVANT
    relevant.confidence = 0.9
    possibly = MagicMock()
    possibly.relevance = Relevance.POSSIBLY_RELEVANT
    possibly.confidence = 0.6
    not_rel = MagicMock()
    not_rel.relevance = Relevance.NOT_RELEVANT
    not_rel.confidence = 0.1

    stats = compute_triage_stats([relevant, possibly], [relevant, possibly, not_rel])

    assert "Total triaged: 3" in stats
    assert "Relevant: 1" in stats
    assert "Possibly relevant: 1" in stats
    assert "Not relevant: 1" in stats
    assert "Average confidence (relevant): 0.90" in stats
    assert "2 triaged, 2 relevant/possibly" in stats
