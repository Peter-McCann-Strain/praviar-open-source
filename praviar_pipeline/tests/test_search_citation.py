"""Tests for citation traversal helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from praviar_pipeline.pipeline.search.citation import (
    _build_citation_seed_ids,
    expand_via_citations,
)


def _make_hit(patent_id: str, confidence_score: float) -> SimpleNamespace:
    return SimpleNamespace(patent_id=patent_id, confidence_score=confidence_score)


def test_build_citation_seed_ids_orders_by_confidence_and_appends_unique_rows() -> None:
    hits = [
        _make_hit("US100", 0.2),
        _make_hit("US200", 0.9),
        _make_hit("US300", 0.5),
    ]
    supplementary_rows = [
        [{"publication_number": "US400"}, {"publication_number": "US200"}],
        [{"publication_number": "US500"}, {"publication_number": ""}],
    ]

    seeds = _build_citation_seed_ids(hits, supplementary_rows, max_seed_patents=2)

    assert seeds == ["US200", "US300", "US400", "US500"]


@pytest.mark.asyncio
async def test_expand_via_citations_returns_immediately_without_seeds() -> None:
    settings = SimpleNamespace(
        citation_seed_max_patents=3,
        search_citation_max_depth=2,
        search_citation_max_per_level=10,
    )
    client_factory = MagicMock()

    hits: list[SimpleNamespace] = []
    seen_norm_ids: set[str] = set()

    await expand_via_citations(
        hits,
        seen_norm_ids=seen_norm_ids,
        source_map={},
        supplementary_rows=[],
        settings=settings,
        client_factory=client_factory,
        row_to_patent_hit=MagicMock(),
        patent_source=MagicMock(),
    )

    client_factory.assert_not_called()
    assert hits == []
