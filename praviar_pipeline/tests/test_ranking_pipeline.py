"""Direct tests for extracted Step 2b ranking funnel orchestration."""

from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.ranking.pipeline import rank_patents_impl


def test_rank_patents_impl_passes_scored_candidates_to_blending() -> None:
    captured: dict[str, object] = {}

    def build_final_ranking_fn(bm25_ranked, composite_scores, embedding_ranked, **kwargs):
        captured["bm25_ranked"] = bm25_ranked
        captured["composite_scores"] = composite_scores
        captured["embedding_ranked"] = embedding_ranked
        captured["kwargs"] = kwargs
        return [{"publicationnumber": "US1", "_rank_score": 0.9}]

    result = rank_patents_impl(
        [
            {
                "publicationnumber": "US1",
                "classification": "C07D",
                "cids": "1,2",
                "prioritydate": "2015-01-01",
                "title": "Succinic acid method",
            }
        ],
        SimpleNamespace(name="succinic acid"),
        settings=SimpleNamespace(
            search_include_expired=True,
            search_expired_grace_years=5,
            rank_bm25_pool_size=500,
            rank_blend_composite_3way=0.3,
            rank_blend_bm25_3way=0.2,
            rank_blend_embedding_3way=0.5,
            rank_blend_composite_2way=0.8,
            rank_blend_bm25_2way=0.2,
        ),
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None
        ),
        multi_source_ids={"US1"},
        max_results=10,
        collect_audit=False,
        apply_hard_filters_fn=lambda patents, **kwargs: (patents, {}),
        parse_cpc_codes_fn=lambda classification: [classification],
        count_cids_fn=lambda cids: 2,
        parse_date_fn=lambda raw: raw,
        compute_composite_score_fn=lambda *scores: sum(scores),
        score_cpc_relevance_fn=lambda cpc_codes: 0.1,
        score_compound_count_fn=lambda cid_count: 0.2,
        score_recency_fn=lambda priority_date: 0.3,
        score_title_keyword_fn=lambda title, compound: 0.4,
        score_multi_source_fn=lambda publication_number, multi_source_ids: 0.5,
        bm25_rerank_fn=lambda patents, compound, top_k: [(patents[0], 1.0)],
        embedding_rerank_fn=lambda patents, compound: [(patents[0], 0.7)],
        build_final_ranking_fn=build_final_ranking_fn,
    )

    assert result == [{"publicationnumber": "US1", "_rank_score": 0.9}]
    assert captured["composite_scores"] == {"US1": 1.5}
    assert captured["kwargs"] == {
        "max_results": 10,
        "blend_composite_3way": 0.3,
        "blend_bm25_3way": 0.2,
        "blend_embedding_3way": 0.5,
        "blend_composite_2way": 0.8,
        "blend_bm25_2way": 0.2,
    }
