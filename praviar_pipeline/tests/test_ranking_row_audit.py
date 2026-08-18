from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.audit import SearchFunnelEntry
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.ranking.blending import build_final_ranking
from praviar_pipeline.pipeline.ranking.pipeline import rank_patents_impl
from praviar_pipeline.pipeline.search.orchestration import build_search_funnel


def test_every_input_row_gets_a_content_addressable_disposition() -> None:
    rows = [
        {"publicationnumber": "US1A1", "score": 1.0},
        {"publicationnumber": "CN2A", "score": 0.99},
        {"publicationnumber": "US3A1", "score": 0.9},
        {"publicationnumber": "US4A1", "score": 0.1},
    ]

    def hard_filter(patents, **_kwargs):
        return [patents[0], patents[2], patents[3]], {"CN2A": "non_allowed_jurisdiction"}

    settings = SimpleNamespace(
        search_include_expired=True,
        search_expired_grace_years=5,
        rank_bm25_pool_size=2,
        rank_blend_composite_3way=0.4,
        rank_blend_bm25_3way=0.3,
        rank_blend_embedding_3way=0.3,
        rank_blend_composite_2way=0.6,
        rank_blend_bm25_2way=0.4,
    )
    ranked = rank_patents_impl(
        rows,
        SimpleNamespace(),
        settings=settings,
        logger=SimpleNamespace(
            info=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None
        ),
        multi_source_ids=set(),
        max_results=1,
        collect_audit=True,
        apply_hard_filters_fn=hard_filter,
        parse_cpc_codes_fn=lambda _value: [],
        count_cids_fn=lambda _value: 0,
        parse_date_fn=lambda _value: None,
        compute_composite_score_fn=lambda cpc, *_args: cpc,
        score_cpc_relevance_fn=lambda _codes: 0.0,
        score_compound_count_fn=lambda _count: 0.0,
        score_recency_fn=lambda _date: 0.0,
        score_title_keyword_fn=lambda _title, _compound: 0.0,
        score_multi_source_fn=lambda patent_id, _ids: next(
            row["score"] for row in rows if row["publicationnumber"] == patent_id
        ),
        bm25_rerank_fn=lambda patents, _compound, top_k: [
            (patent, float(len(patents) - index)) for index, patent in enumerate(patents[:top_k])
        ],
        embedding_rerank_fn=lambda _patents, _compound: None,
        build_final_ranking_fn=build_final_ranking,
    )

    assert [row["publicationnumber"] for row in ranked] == ["US1A1"]
    assert all("_audit_candidate_index" not in row for row in ranked)
    assert [row["disposition"] for row in ranked.audit_rows] == [
        "included_in_triage",
        "hard_filter_rejected",
        "final_rank_cut",
        "composite_pool_cut",
    ]
    assert len({row["input_row_sha256"] for row in ranked.audit_rows}) == 4

    funnel = build_search_funnel(
        [PatentHit(patent_id="US1A1", sources=[PatentSource.PUBCHEM])],
        collect_audit=True,
        ranking_audit_rows=ranked.audit_rows,
    )
    assert len(funnel) == len(rows)
    assert all(entry.audit_entry_sha256 for entry in funnel)
    assert funnel[1].filter_reason == "non_allowed_jurisdiction"
    assert funnel[2].filter_reason == "rank_cut_max_results"

    tampered = funnel[2].model_dump()
    tampered["filter_reason"] = "changed-after-run"
    with pytest.raises(ValidationError, match="digest mismatch"):
        SearchFunnelEntry.model_validate(tampered)


def test_duplicate_input_patent_rows_remain_independently_auditable() -> None:
    rows = [
        {"publicationnumber": "US1A1", "variant": "first"},
        {"publicationnumber": "US1A1", "variant": "second"},
    ]

    settings = SimpleNamespace(
        search_include_expired=True,
        search_expired_grace_years=5,
        rank_bm25_pool_size=2,
        rank_blend_composite_3way=0.4,
        rank_blend_bm25_3way=0.3,
        rank_blend_embedding_3way=0.3,
        rank_blend_composite_2way=0.6,
        rank_blend_bm25_2way=0.4,
    )
    ranked = rank_patents_impl(
        rows,
        SimpleNamespace(),
        settings=settings,
        logger=SimpleNamespace(
            info=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None
        ),
        multi_source_ids=set(),
        max_results=1,
        collect_audit=True,
        apply_hard_filters_fn=lambda patents, **_kwargs: (patents, {}),
        parse_cpc_codes_fn=lambda _value: [],
        count_cids_fn=lambda _value: 0,
        parse_date_fn=lambda _value: None,
        compute_composite_score_fn=lambda *_args: 1.0,
        score_cpc_relevance_fn=lambda _codes: 1.0,
        score_compound_count_fn=lambda _count: 1.0,
        score_recency_fn=lambda _date: 1.0,
        score_title_keyword_fn=lambda _title, _compound: 1.0,
        score_multi_source_fn=lambda _patent_id, _ids: 1.0,
        bm25_rerank_fn=lambda patents, _compound, top_k: [
            (patent, float(top_k - index)) for index, patent in enumerate(patents)
        ],
        embedding_rerank_fn=lambda _patents, _compound: None,
        build_final_ranking_fn=build_final_ranking,
    )

    assert [row["candidate_index"] for row in ranked.audit_rows] == [0, 1]
    assert [row["disposition"] for row in ranked.audit_rows] == [
        "included_in_triage",
        "final_rank_cut",
    ]
    assert ranked.audit_rows[0]["input_row_sha256"] != ranked.audit_rows[1]["input_row_sha256"]
