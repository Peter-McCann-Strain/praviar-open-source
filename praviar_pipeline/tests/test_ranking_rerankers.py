"""Direct tests for extracted Step 2b reranker helpers."""

from __future__ import annotations

import pytest

from praviar_pipeline.pipeline.ranking.rerankers import bm25_rerank, embedding_rerank

pytestmark = pytest.mark.usefixtures("mock_settings")


def test_bm25_rerank_empty_input_returns_empty(succinic_acid):
    assert bm25_rerank([], succinic_acid) == []


def test_embedding_rerank_disabled_returns_none(succinic_acid):
    patent = {"title": "Succinic acid process", "abstract": ""}
    assert embedding_rerank([patent], succinic_acid) is None
