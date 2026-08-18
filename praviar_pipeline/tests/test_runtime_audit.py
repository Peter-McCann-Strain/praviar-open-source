from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.models.search import (
    ExpandedSearchQueries,
    QueryExpansionProvenance,
)
from praviar_pipeline.models.search_loop import SearchIterationLog, SearchLoopResult
from praviar_pipeline.models.triage import TriageResult
from praviar_pipeline.pipeline.runtime.audit import (
    build_analysis_audit,
    build_prior_step_tokens,
    build_search_query_plan,
    build_triage_audit,
    map_relevant_patents,
)


def test_build_triage_audit_uses_all_triage_results():
    relevant = TriageResult(
        patent_id="US123",
        relevance="relevant",
        reason="Primary blocking claim",
        blocking_potential="high",
        key_claims=[1],
        confidence=0.95,
    )
    rejected = TriageResult(
        patent_id="US456",
        relevance="not_relevant",
        reason="Unrelated scaffold",
        blocking_potential="low",
        key_claims=[],
        confidence=0.1,
    )

    audit = build_triage_audit([relevant, rejected], [relevant])

    assert [entry.patent_id for entry in audit] == ["US123", "US456"]
    assert audit[0].passed_triage is True
    assert audit[1].passed_triage is False


def test_map_relevant_patents_filters_by_triage_result_ids():
    patent_hits = [
        SimpleNamespace(patent_id="US123"),
        SimpleNamespace(patent_id="US456"),
    ]
    triage_results = [
        TriageResult(
            patent_id="US456",
            relevance="relevant",
            reason="Relevant patent",
            blocking_potential="medium",
            key_claims=[2],
            confidence=0.8,
        )
    ]

    relevant_patents = map_relevant_patents(patent_hits, triage_results)

    assert [patent.patent_id for patent in relevant_patents] == ["US456"]


def test_build_analysis_audit_marks_follow_on_reviews_from_risk_level():
    relevant_patents = [
        SimpleNamespace(patent_id="US123"),
        SimpleNamespace(patent_id="US456"),
    ]
    analyses = [
        SimpleNamespace(
            patent_id="US123",
            risk_level=SimpleNamespace(value="high"),
        )
    ]

    audit = build_analysis_audit(relevant_patents, analyses)

    assert audit[0].selected_for_analysis is True
    assert audit[0].selected_for_doe is True
    assert audit[0].selected_for_invalidity is True
    assert audit[1].selected_for_analysis is False
    assert audit[1].selection_reason == "excluded"


def test_build_prior_step_tokens_includes_critic_usage():
    step_tokens = build_prior_step_tokens(
        triage_input_tokens=10,
        triage_output_tokens=2,
        critic_input_tokens=5,
        critic_output_tokens=1,
        doe_input_tokens=7,
        doe_output_tokens=3,
        invalidity_input_tokens=11,
        invalidity_output_tokens=4,
    )

    assert [step.step_name for step in step_tokens] == [
        "step3_triage",
        "step4b_critic",
        "step5_doe",
        "step6_invalidity",
    ]
    assert step_tokens[1].input_tokens == 5
    assert step_tokens[1].output_tokens == 1


def test_build_search_query_plan_records_exact_iterations_sources_and_digest() -> None:
    initial_queries = ExpandedSearchQueries(
        patent_synonyms=["acetylsalicylic acid"],
        cpc_codes=["A61K31/616"],
        provenance=QueryExpansionProvenance(
            origin="web_grounded_agent",
            grounded=True,
            model_name="test-model",
            grounding_queries=["aspirin CPC classification"],
            source_urls=["https://www.uspto.gov/patents/search"],
        ),
    )
    follow_up = ExpandedSearchQueries(
        key_assignees=["Bayer"],
        provenance=QueryExpansionProvenance(
            origin="coverage_assessment_agent",
        ),
    )
    loop = SearchLoopResult(
        iterations_completed=2,
        iteration_logs=[
            SearchIterationLog(iteration_number=1, queries_used=initial_queries),
            SearchIterationLog(iteration_number=2, queries_used=follow_up),
        ],
    )
    settings = SimpleNamespace(
        search_allowed_jurisdictions=["US", "EP"],
        search_enable_pubchem=True,
        search_enable_surechembl=True,
        search_enable_bigquery=True,
        search_enable_patcid=False,
        ops_consumer_key="ops-key",
        ops_consumer_secret="ops-secret",
        patentsview_api_key="patentsview-key",
        kipris_api_key="",
        patentscope_username="",
        patentscope_password="",
        search_enable_ncbi_patent_sequence=True,
        embedding_ranking_enabled=True,
        hybrid_retrieval_enabled=True,
        search_citation_traversal_enabled=True,
    )
    plan = build_search_query_plan(
        compound=SimpleNamespace(
            name="aspirin",
            canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
            inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            pubchem_cid=2244,
            synonyms=["acetylsalicylic acid"],
            cas_numbers=["50-78-2"],
            compound_type="biologic",
            protein_subunit_sequences=["ACDEFGHIKLMNPQRSTVWY"],
        ),
        expanded_queries=initial_queries,
        search_loop_result=loop,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_sdq",
                    status=SourceStatus.OK,
                    patent_count=12,
                ),
                SourceHealthEntry(
                    source="bigquery",
                    status=SourceStatus.OK,
                    patent_count=8,
                ),
                SourceHealthEntry(
                    source="ncbi_patent_sequence",
                    status=SourceStatus.OK,
                    patent_count=3,
                ),
            ]
        ),
        settings=settings,
    )

    assert [item.iteration_number for item in plan.iterations] == [1, 2]
    assert plan.iterations[0].queries.provenance.source_urls == [
        "https://www.uspto.gov/patents/search"
    ]
    assert plan.target_jurisdictions == ["US", "EP"]
    assert {"composite", "bm25", "embedding", "indexed_lexical", "dense_vector", "rrf"} <= set(
        plan.ranking_signals
    )
    assert plan.ranking_configuration.max_ranked_results == 1000
    assert plan.ranking_configuration.blend_composite_2way == 0.6
    assert plan.execution_configuration.citation_traversal_enabled is True
    assert any("Markush" in limitation for limitation in plan.known_retrieval_limitations)
    assert any(
        "jointly calibrated" in limitation for limitation in plan.known_retrieval_limitations
    )
    assert len(plan.plan_sha256) == 64
    source_by_name = {entry.source: entry for entry in plan.sources}
    assert source_by_name["pubchem_sdq"].execution_status == "ok"
    assert source_by_name["pubchem_sdq"].result_count == 12
    assert source_by_name["kipris"].execution_status == "not_requested"
    assert source_by_name["ncbi_patent_sequence"].execution_status == "ok"
    assert plan.sequence_queries[0].sequence_length == 20
    assert len(plan.sequence_queries[0].sequence_sha256) == 64
    assert any(
        "pre-grant patent sequences" in limitation
        for limitation in plan.known_retrieval_limitations
    )

    tampered = plan.model_dump(mode="json")
    tampered["compound_name"] = "ibuprofen"
    with pytest.raises(ValidationError, match="digest mismatch"):
        type(plan).model_validate(tampered)


def test_small_molecule_query_plan_records_genus_query_and_manual_markush_gap() -> None:
    settings = SimpleNamespace(
        search_allowed_jurisdictions=["US", "EP"],
        search_enable_pubchem=True,
        search_enable_pubchem_genus=True,
        search_enable_surechembl=False,
        search_enable_bigquery=True,
        search_enable_patcid=False,
        search_enable_ncbi_patent_sequence=True,
        ops_consumer_key="",
        ops_consumer_secret="",
        patentsview_api_key="",
        kipris_api_key="",
        patentscope_username="",
        patentscope_password="",
    )
    plan = build_search_query_plan(
        compound=SimpleNamespace(
            name="aspirin",
            canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
            scaffold_smiles="c1ccccc1",
            inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            pubchem_cid=2244,
            synonyms=[],
            cas_numbers=["50-78-2"],
            compound_type="small_molecule",
            protein_subunit_sequences=[],
        ),
        expanded_queries=ExpandedSearchQueries(),
        search_loop_result=SearchLoopResult(),
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_genus",
                    status=SourceStatus.OK,
                    patent_count=25,
                )
            ]
        ),
        settings=settings,
    )

    assert plan.true_markush_coverage_status == "not_run"
    assert plan.markush_evidence is None
    assert plan.genus_queries[0].query_role == "murcko_scaffold"
    assert len(plan.genus_queries[0].query_sha256) == 64
    assert (
        next(source for source in plan.sources if source.source == "pubchem_genus").execution_status
        == "ok"
    )
    assert any("WIPO PATENTSCOPE" in limitation for limitation in plan.known_retrieval_limitations)


def test_small_molecule_query_plan_records_executed_canonical_refinement() -> None:
    canonical_smiles = "CCc1ccccc1"
    canonical_digest = hashlib.sha256(canonical_smiles.encode("utf-8")).hexdigest()
    plan = build_search_query_plan(
        compound=SimpleNamespace(
            name="example",
            canonical_smiles=canonical_smiles,
            scaffold_smiles="c1ccccc1",
            inchi_key="TESTKEY",
            pubchem_cid=1,
            synonyms=[],
            cas_numbers=[],
            compound_type="small_molecule",
            protein_subunit_sequences=[],
        ),
        expanded_queries=ExpandedSearchQueries(),
        search_loop_result=SearchLoopResult(),
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_genus",
                    status=SourceStatus.OK,
                    patent_count=1,
                )
            ]
        ),
        settings=SimpleNamespace(
            search_allowed_jurisdictions=["US"],
            search_enable_pubchem=True,
            search_enable_pubchem_genus=True,
            search_enable_surechembl=False,
            search_enable_bigquery=True,
            search_enable_patcid=False,
            search_enable_ncbi_patent_sequence=True,
            ops_consumer_key="",
            ops_consumer_secret="",
            patentsview_api_key="",
            kipris_api_key="",
            patentscope_username="",
            patentscope_password="",
        ),
        patent_hits=[
            SimpleNamespace(
                genus_matches=[
                    SimpleNamespace(
                        query_sha256=canonical_digest,
                        query_role="canonical_refinement_after_scaffold_cap",
                    )
                ]
            )
        ],
    )

    assert [query.query_role for query in plan.genus_queries] == [
        "murcko_scaffold",
        "canonical_refinement_after_scaffold_cap",
    ]
    assert plan.genus_queries[1].query_sha256 == canonical_digest
