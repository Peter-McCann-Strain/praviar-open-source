"""Direct tests for extracted Step 2b final blending helpers."""

from __future__ import annotations

import pytest

from praviar_pipeline.pipeline.ranking.blending import build_final_ranking


def _patent(pub_num: str) -> dict:
    return {"publicationnumber": pub_num}


def test_build_final_ranking_uses_two_way_weights():
    bm25_ranked = [(_patent("US1"), 4.0), (_patent("US2"), 1.0)]
    composite_scores = {"US1": 0.0, "US2": 1.0}

    result = build_final_ranking(
        bm25_ranked,
        composite_scores,
        None,
        max_results=2,
        blend_composite_3way=0.3,
        blend_bm25_3way=0.2,
        blend_embedding_3way=0.5,
        blend_composite_2way=0.8,
        blend_bm25_2way=0.2,
    )

    assert [pat["publicationnumber"] for pat in result] == ["US2", "US1"]
    assert result[0]["_retrieval_scores"] == {
        "composite": 1.0,
        "bm25_raw": 1.0,
        "bm25_normalized": 0.25,
        "embedding_raw": None,
        "embedding_normalized": None,
        "final_blend": pytest.approx(0.85),
    }


def test_build_final_ranking_uses_three_way_weights():
    bm25_ranked = [(_patent("US1"), 4.0), (_patent("US2"), 1.0)]
    composite_scores = {"US1": 0.0, "US2": 0.0}
    embedding_ranked = [(_patent("US1"), 0.1), (_patent("US2"), 1.0)]

    result = build_final_ranking(
        bm25_ranked,
        composite_scores,
        embedding_ranked,
        max_results=2,
        blend_composite_3way=0.1,
        blend_bm25_3way=0.2,
        blend_embedding_3way=0.7,
        blend_composite_2way=0.8,
        blend_bm25_2way=0.2,
    )

    assert [pat["publicationnumber"] for pat in result] == ["US2", "US1"]
    assert result[0]["_retrieval_scores"]["embedding_raw"] == 1.0
    assert result[0]["_retrieval_scores"]["embedding_normalized"] == 1.0
    assert result[0]["_retrieval_scores"]["final_blend"] == pytest.approx(0.75)


def test_build_final_ranking_minmax_normalizes_negative_cosine_scores() -> None:
    patents = [(_patent("US1"), 1.0), (_patent("US2"), 1.0)]

    result = build_final_ranking(
        patents,
        {"US1": 0.0, "US2": 0.0},
        [(_patent("US1"), -0.5), (_patent("US2"), 0.5)],
        max_results=2,
        blend_composite_3way=0.0,
        blend_bm25_3way=0.0,
        blend_embedding_3way=1.0,
        blend_composite_2way=0.0,
        blend_bm25_2way=1.0,
    )

    assert [patent["publicationnumber"] for patent in result] == ["US2", "US1"]
    assert result[0]["_retrieval_scores"]["embedding_normalized"] == 1.0
    assert result[1]["_retrieval_scores"]["embedding_normalized"] == 0.0
