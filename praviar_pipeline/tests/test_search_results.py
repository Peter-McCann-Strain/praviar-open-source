from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.search.results import (
    assemble_hits_from_summary,
    assemble_step2_hits,
    build_final_source_counts,
)


def test_assemble_hits_from_summary_deduplicates_bigquery_rows(sample_patent_hit):
    summary = SimpleNamespace(
        bigquery_rows=[
            {"publication_number": "US7851188B2", "title": "duplicate"},
            {"publication_number": "US2222222B1", "title": "supplement"},
        ],
        cpc_search_rows=[],
        assignee_search_rows=[],
        epo_search_results=[],
        lens_results=[],
        kipris_results=[],
        patentscope_results=[],
        bq_translated_results=[],
        patentsview_results=[],
    )
    source_map = {
        "US7851188B2": {PatentSource.PUBCHEM},
        "US2222222B1": {PatentSource.BIGQUERY},
    }

    def sdq_to_patent_hit(_patent, _source_map):
        return sample_patent_hit.model_copy(deep=True)

    def bq_row_to_patent_hit(row, _source, _source_map):
        hit = sample_patent_hit.model_copy(deep=True)
        hit.patent_id = row["publication_number"]
        hit.sources = [PatentSource.BIGQUERY]
        return hit

    hits, seen_norm_ids = assemble_hits_from_summary(
        summary=summary,
        ranked_sdq=[{"publicationnumber": "US7851188B2"}],
        source_map=source_map,
        normalize_patent_id=lambda patent_id: patent_id,
        sdq_to_patent_hit=sdq_to_patent_hit,
        bq_row_to_patent_hit=bq_row_to_patent_hit,
        merge_supplementary_rows=lambda *_args: None,
        surechembl_similarity_lookup=lambda _patent_id: None,
    )

    assert [hit.patent_id for hit in hits] == ["US7851188B2", "US2222222B1"]
    assert seen_norm_ids == {"US7851188B2", "US2222222B1"}


def test_build_final_source_counts_counts_total_and_sole_sources(sample_patent_hits):
    source_counts, sole_counts = build_final_source_counts(sample_patent_hits)

    assert source_counts["pubchem"] == 1
    assert source_counts["bigquery"] == 2
    assert source_counts["surechembl"] == 1
    assert sole_counts["bigquery"] == 1
    assert sole_counts["surechembl"] == 1


def test_assemble_step2_hits_forwards_to_summary_assembler(sample_patent_hit):
    summary = SimpleNamespace(
        bigquery_rows=[],
        cpc_search_rows=[],
        assignee_search_rows=[],
        epo_search_results=[],
        lens_results=[],
        kipris_results=[],
        patentscope_results=[],
        bq_translated_results=[],
        patentsview_results=[],
    )

    hits, seen_norm_ids = assemble_step2_hits(
        summary=summary,
        ranked_sdq=[{"publicationnumber": "US7851188B2"}],
        source_map={"US7851188B2": {PatentSource.PUBCHEM}},
        normalize_patent_id=lambda patent_id: patent_id,
        sdq_to_patent_hit=lambda _patent, _source_map: sample_patent_hit.model_copy(deep=True),
        bq_row_to_patent_hit=lambda *_args: sample_patent_hit.model_copy(deep=True),
        merge_supplementary_rows=lambda *_args: None,
        surechembl_similarity_lookup=lambda _patent_id: None,
    )

    assert [hit.patent_id for hit in hits] == ["US7851188B2"]
    assert seen_norm_ids == {"US7851188B2"}
