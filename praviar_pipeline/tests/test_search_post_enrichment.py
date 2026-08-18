from __future__ import annotations

from praviar_pipeline.pipeline.search.enrichment import (
    enrich_hits,
    run_step2_post_enrichment,
)


async def test_enrich_hits_returns_all_step_counts(sample_patent_hits):
    async def _return(value):
        return value

    counts = await enrich_hits(
        sample_patent_hits,
        enrich_legal_status=lambda hits: _return(1),
        expand_families=lambda hits: _return(2),
        enrich_patent_term=lambda hits: _return(3),
        enrich_application_data=lambda hits: _return(4),
        enrich_epo_register=lambda hits: _return(5),
        enrich_ptab_proceedings=lambda hits: _return(6),
        enrich_orange_book=lambda hits: _return(7),
    )

    assert counts.legal == 1
    assert counts.families == 2
    assert counts.patent_term == 3
    assert counts.application_data == 4
    assert counts.epo_register == 5
    assert counts.ptab == 6
    assert counts.orange_book == 7


async def test_run_step2_post_enrichment_reuses_standard_enrichment(sample_patent_hits):
    async def _return(value):
        return value

    counts = await run_step2_post_enrichment(
        sample_patent_hits,
        enrich_legal_status=lambda hits: _return(1),
        expand_families=lambda hits: _return(2),
        enrich_patent_term=lambda hits: _return(3),
        enrich_application_data=lambda hits: _return(4),
        enrich_epo_register=lambda hits: _return(5),
        enrich_ptab_proceedings=lambda hits: _return(6),
        enrich_orange_book=lambda hits: _return(7),
    )

    assert counts.legal == 1
    assert counts.orange_book == 7


async def test_enrich_hits_invokes_expand_continuations_when_provided(sample_patent_hits):
    async def _return(value):
        return value

    called = {}

    async def _expand(hits):
        called["hits"] = hits
        return 11

    counts = await enrich_hits(
        sample_patent_hits,
        enrich_legal_status=lambda hits: _return(1),
        expand_families=lambda hits: _return(2),
        enrich_patent_term=lambda hits: _return(3),
        enrich_application_data=lambda hits: _return(4),
        enrich_epo_register=lambda hits: _return(5),
        enrich_ptab_proceedings=lambda hits: _return(6),
        enrich_orange_book=lambda hits: _return(7),
        expand_continuations=_expand,
    )

    assert called["hits"] is sample_patent_hits
    assert counts.continuations == 11


async def test_enrich_hits_backward_compat_without_expand_continuations(
    sample_patent_hits,
):
    async def _return(value):
        return value

    counts = await enrich_hits(
        sample_patent_hits,
        enrich_legal_status=lambda hits: _return(1),
        expand_families=lambda hits: _return(2),
        enrich_patent_term=lambda hits: _return(3),
        enrich_application_data=lambda hits: _return(4),
        enrich_epo_register=lambda hits: _return(5),
        enrich_ptab_proceedings=lambda hits: _return(6),
        enrich_orange_book=lambda hits: _return(7),
    )

    assert counts.continuations == 0


async def test_run_step2_post_enrichment_threads_expand_continuations(
    sample_patent_hits,
):
    async def _return(value):
        return value

    async def _expand(hits):
        return 42

    counts = await run_step2_post_enrichment(
        sample_patent_hits,
        enrich_legal_status=lambda hits: _return(1),
        expand_families=lambda hits: _return(2),
        enrich_patent_term=lambda hits: _return(3),
        enrich_application_data=lambda hits: _return(4),
        enrich_epo_register=lambda hits: _return(5),
        enrich_ptab_proceedings=lambda hits: _return(6),
        enrich_orange_book=lambda hits: _return(7),
        expand_continuations=_expand,
    )

    assert counts.continuations == 42
