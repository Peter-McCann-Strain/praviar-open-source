"""Audit-trail builders for the Praviar Pipeline runtime."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, cast

from praviar_pipeline.models.audit import (
    AnalysisAuditEntry,
    PipelineAuditTrail,
    SearchExecutionConfiguration,
    SearchFunnelEntry,
    SearchQueryIteration,
    SearchQueryPlan,
    SearchRankingConfiguration,
    SearchSourceExecutionStatus,
    SearchSourceFailurePolicy,
    SearchSourcePlanEntry,
    StepTokenUsage,
    TriageAuditEntry,
)
from praviar_pipeline.models.markush_evidence import MarkushEvidenceReceipt
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.pipeline.search.source_registry import (
    SOURCE_CAPABILITIES,
    missing_required_settings,
    source_is_enabled,
    source_is_requested,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry
    from praviar_pipeline.models.search_loop import SearchLoopResult
    from praviar_pipeline.pipeline.search.source_registry import SourceCapability


def build_triage_audit(all_triage_results: list, triage_results: list) -> list[TriageAuditEntry]:
    triage_audit_source = all_triage_results if all_triage_results else triage_results
    relevant_ids = {result.patent_id for result in triage_results}
    return [
        TriageAuditEntry(
            patent_id=result.patent_id,
            relevance=result.relevance.value
            if hasattr(result.relevance, "value")
            else str(result.relevance),
            reason=result.reason,
            confidence=result.confidence,
            passed_triage=result.patent_id in relevant_ids,
        )
        for result in triage_audit_source
    ]


def map_relevant_patents(patent_hits: list, triage_results: list) -> list:
    relevant_ids = {result.patent_id for result in triage_results}
    return [hit for hit in patent_hits if hit.patent_id in relevant_ids]


def build_analysis_audit(relevant_patents: list, analyses: list) -> list[AnalysisAuditEntry]:
    analyses_by_patent_id = {analysis.patent_id: analysis for analysis in analyses}
    return [
        AnalysisAuditEntry(
            patent_id=patent.patent_id,
            selected_for_analysis=patent.patent_id in analyses_by_patent_id,
            selection_reason=(
                "triage_relevant" if patent.patent_id in analyses_by_patent_id else "excluded"
            ),
            risk_level=(
                analyses_by_patent_id[patent.patent_id].risk_level.value
                if patent.patent_id in analyses_by_patent_id
                else None
            ),
            selected_for_doe=(
                patent.patent_id in analyses_by_patent_id
                and analyses_by_patent_id[patent.patent_id].risk_level.value in ("high", "medium")
            ),
            selected_for_invalidity=(
                patent.patent_id in analyses_by_patent_id
                and analyses_by_patent_id[patent.patent_id].risk_level.value in ("high", "medium")
            ),
        )
        for patent in relevant_patents
    ]


_SOURCE_QUERY_CATEGORIES: dict[str, list[str]] = {
    "pubchem_sdq": ["pubchem_cid"],
    "surechembl": ["canonical_smiles", "identity_variants", "similarity", "substructure"],
    "bigquery": ["compound_name", "synonyms", "cas_numbers"],
    "bigquery_annotations": ["compound_name", "inchi_key"],
    "patcid": ["inchi_key", "inchi_key_connectivity_layer"],
    "pubchem_similar": ["canonical_smiles", "similarity"],
    "pubchem_genus": ["murcko_scaffold", "canonical_smiles_fallback", "substructure"],
    "cpc_search": ["cpc_codes", "process_keywords", "compound_class_terms"],
    "assignee_search": ["key_assignees", "cpc_codes"],
    "epo_search": ["patent_synonyms", "process_keywords", "compound_class_terms"],
    "kipris": ["compound_name", "synonyms"],
    "patentscope": ["compound_name", "synonyms"],
    "bigquery_translated": ["compound_name", "synonyms"],
    "patentsview": ["compound_name", "synonyms"],
    "ncbi_patent_sequence": ["fda_gsrs_protein_subunit_sequences"],
}


def _search_query_iterations(
    expanded_queries,
    search_loop_result,
) -> list[SearchQueryIteration]:
    logs = list(getattr(search_loop_result, "iteration_logs", []) or [])
    iterations: list[SearchQueryIteration] = []
    for index, log in enumerate(logs, start=1):
        queries = getattr(log, "queries_used", None)
        if queries is None:
            continue
        iterations.append(
            SearchQueryIteration(
                iteration_number=int(getattr(log, "iteration_number", index) or index),
                queries=ExpandedSearchQueries.model_validate(queries),
            )
        )
    if iterations:
        return iterations
    if expanded_queries is None:
        return []
    return [
        SearchQueryIteration(
            iteration_number=1,
            queries=ExpandedSearchQueries.model_validate(expanded_queries),
        )
    ]


def _has_expanded_query_terms(iterations: list[SearchQueryIteration]) -> bool:
    return any(
        iteration.queries.cpc_codes
        or iteration.queries.key_assignees
        or iteration.queries.process_keywords
        for iteration in iterations
    )


def _source_health_by_name(
    source_health: SourceHealth | None,
) -> dict[str, SourceHealthEntry]:
    health_entries = cast(
        "list[SourceHealthEntry]",
        list(getattr(source_health, "entries", []) or []),
    )
    return {
        str(getattr(entry, "source", "")): entry
        for entry in health_entries
        if str(getattr(entry, "source", ""))
    }


def _source_execution_state(
    *,
    requested: bool,
    enabled: bool,
    missing_settings: list[str],
    expansion_only: bool,
    sequence_only: bool,
    has_expansion: bool,
    compound_type: str,
    health: SourceHealthEntry | None,
    enabled_attr: str | None,
) -> tuple[SearchSourceExecutionStatus, str]:
    if not requested:
        return "not_requested", "Outside requested jurisdiction/source scope"
    if expansion_only and not has_expansion:
        return "not_applicable", "No expanded query terms were available"
    if sequence_only and compound_type not in {"biologic", "peptide"}:
        return "not_applicable", "Not applicable to a small-molecule matter"
    if not enabled:
        return "skipped", f"Disabled by {enabled_attr}"
    if missing_settings:
        return "not_configured", f"Missing required setting(s): {', '.join(missing_settings)}"
    if health is None:
        return "missing_audit", "Source was planned but no final health record was retained"
    raw_status = getattr(getattr(health, "status", ""), "value", None)
    status = cast(
        "SearchSourceExecutionStatus",
        raw_status or str(getattr(health, "status", "")),
    )
    return status, str(getattr(health, "error_message", "") or "")


def _source_plan_entry(
    name: str,
    capability: SourceCapability,
    *,
    settings: Settings,
    health_by_source: dict[str, SourceHealthEntry],
    has_expansion: bool,
    compound_type: str,
) -> SearchSourcePlanEntry:
    requested = source_is_requested(capability, settings)
    enabled = source_is_enabled(capability, settings)
    missing = missing_required_settings(capability, settings) if requested and enabled else []
    expansion_only = "expanded" in capability.roles
    sequence_only = "sequence_identity" in capability.roles
    health = health_by_source.get(name)
    status, reason = _source_execution_state(
        requested=requested,
        enabled=enabled,
        missing_settings=missing,
        expansion_only=expansion_only,
        sequence_only=sequence_only,
        has_expansion=has_expansion,
        compound_type=compound_type,
        health=health,
        enabled_attr=capability.enabled_attr,
    )
    return SearchSourcePlanEntry(
        source=name,
        roles=list(capability.roles),
        criticality=capability.criticality,
        query_categories=_SOURCE_QUERY_CATEGORIES.get(name, []),
        execution_status=status,
        result_count=int(getattr(health, "patent_count", 0) or 0),
        reason=reason,
    )


def _source_plan_entries(
    *,
    settings: Settings,
    health_by_source: dict[str, SourceHealthEntry],
    has_expansion: bool,
    compound_type: str,
) -> list[SearchSourcePlanEntry]:
    return [
        _source_plan_entry(
            name,
            capability,
            settings=settings,
            health_by_source=health_by_source,
            has_expansion=has_expansion,
            compound_type=compound_type,
        )
        for name, capability in SOURCE_CAPABILITIES.items()
    ]


def _ranking_signals(settings: Settings) -> list[str]:
    signals = ["composite", "bm25"]
    if bool(getattr(settings, "embedding_ranking_enabled", False)):
        signals.append("embedding")
    if bool(getattr(settings, "hybrid_retrieval_enabled", False)):
        signals.extend(["indexed_lexical", "dense_vector", "rrf"])
    return signals


def _ranking_configuration(settings: Settings) -> SearchRankingConfiguration:
    return SearchRankingConfiguration(
        max_sdq_patents=int(getattr(settings, "search_max_sdq_patents", 50000)),
        max_ranked_results=int(getattr(settings, "search_max_ranked_results", 1000)),
        include_expired=bool(getattr(settings, "search_include_expired", True)),
        expired_grace_years=int(getattr(settings, "search_expired_grace_years", 5)),
        bm25_pool_size=int(getattr(settings, "rank_bm25_pool_size", 1000)),
        embedding_enabled=bool(getattr(settings, "embedding_ranking_enabled", False)),
        hybrid_retrieval_enabled=bool(getattr(settings, "hybrid_retrieval_enabled", False)),
        composite_cpc_weight=float(getattr(settings, "rank_weight_cpc", 0.30)),
        composite_compound_count_weight=float(
            getattr(settings, "rank_weight_compound_count", 0.20)
        ),
        composite_recency_weight=float(getattr(settings, "rank_weight_recency", 0.15)),
        composite_title_weight=float(getattr(settings, "rank_weight_title", 0.15)),
        composite_multi_source_weight=float(getattr(settings, "rank_weight_multi_source", 0.20)),
        blend_composite_2way=float(getattr(settings, "rank_blend_composite_2way", 0.60)),
        blend_bm25_2way=float(getattr(settings, "rank_blend_bm25_2way", 0.40)),
        blend_composite_3way=float(getattr(settings, "rank_blend_composite_3way", 0.40)),
        blend_bm25_3way=float(getattr(settings, "rank_blend_bm25_3way", 0.30)),
        blend_embedding_3way=float(getattr(settings, "rank_blend_embedding_3way", 0.30)),
    )


def _execution_configuration(settings: Settings) -> SearchExecutionConfiguration:
    return SearchExecutionConfiguration(
        source_failure_policy=cast(
            "SearchSourceFailurePolicy",
            str(getattr(settings, "source_failure_policy", "coverage_aware")),
        ),
        tanimoto_threshold=float(getattr(settings, "search_tanimoto_threshold", 0.55)),
        surechembl_substructure_enabled=bool(
            getattr(settings, "search_surechembl_substructure_enabled", True)
        ),
        citation_traversal_enabled=bool(
            getattr(settings, "search_citation_traversal_enabled", False)
        ),
        citation_max_depth=int(getattr(settings, "search_citation_max_depth", 2)),
        citation_max_per_level=int(getattr(settings, "search_citation_max_per_level", 50)),
        continuation_expansion_enabled=bool(
            getattr(settings, "continuation_expansion_enabled", True)
        ),
        continuation_max_depth=int(getattr(settings, "continuation_max_depth", 2)),
        continuation_max_patents=int(getattr(settings, "continuation_max_patents", 50)),
        search_loop_enabled=bool(getattr(settings, "search_loop_enabled", False)),
        search_loop_max_iterations=int(getattr(settings, "search_loop_max_iterations", 3)),
        search_loop_coverage_threshold=float(
            getattr(settings, "search_loop_coverage_threshold", 0.7)
        ),
        ncbi_patent_sequence_enabled=bool(
            getattr(settings, "search_enable_ncbi_patent_sequence", True)
        ),
        ncbi_patent_sequence_max_hits=int(getattr(settings, "ncbi_patent_sequence_max_hits", 100)),
        ncbi_patent_sequence_min_identity=float(
            getattr(settings, "ncbi_patent_sequence_min_identity", 0.75)
        ),
        ncbi_patent_sequence_min_query_coverage=float(
            getattr(settings, "ncbi_patent_sequence_min_query_coverage", 0.75)
        ),
        pubchem_genus_enabled=bool(getattr(settings, "search_enable_pubchem_genus", True)),
        pubchem_genus_max_compounds=int(getattr(settings, "pubchem_genus_max_compounds", 2000)),
        pubchem_genus_max_patents=int(getattr(settings, "pubchem_genus_max_patents", 5000)),
        pubchem_genus_max_seconds=int(getattr(settings, "pubchem_genus_max_seconds", 60)),
    )


def _sequence_queries(compound: ResolvedCompound) -> list[dict[str, int | str]]:
    return [
        {
            "subunit_index": index,
            "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
            "sequence_length": len(sequence),
            "identity_source": "fda_gsrs_public",
        }
        for index, sequence in enumerate(
            list(getattr(compound, "protein_subunit_sequences", []) or []),
            start=1,
        )
    ]


def _initial_genus_queries(
    compound: ResolvedCompound,
    *,
    compound_type: str,
) -> list[dict[str, str]]:
    genus_query_smiles = str(getattr(compound, "scaffold_smiles", "") or "") or str(
        getattr(compound, "canonical_smiles", "") or ""
    )
    return (
        [
            {
                "query_sha256": hashlib.sha256(genus_query_smiles.encode("utf-8")).hexdigest(),
                "query_role": (
                    "murcko_scaffold"
                    if str(getattr(compound, "scaffold_smiles", "") or "")
                    else "canonical_fallback"
                ),
                "search_type": "pubchem_fastsubstructure",
            }
        ]
        if compound_type == "small_molecule" and genus_query_smiles
        else []
    )


def _genus_queries(
    compound: ResolvedCompound,
    *,
    compound_type: str,
    patent_hits: Iterable[PatentHit],
) -> list[dict[str, str]]:
    queries = _initial_genus_queries(compound, compound_type=compound_type)
    recorded_queries = {(query["query_sha256"], query["query_role"]) for query in queries}
    for hit in patent_hits:
        for match in list(getattr(hit, "genus_matches", []) or []):
            query_sha256 = str(getattr(match, "query_sha256", "") or "")
            query_role = str(getattr(match, "query_role", "") or "")
            key = (query_sha256, query_role)
            if not query_sha256 or not query_role or key in recorded_queries:
                continue
            queries.append(
                {
                    "query_sha256": query_sha256,
                    "query_role": query_role,
                    "search_type": "pubchem_fastsubstructure",
                }
            )
            recorded_queries.add(key)
    return queries


def _retrieval_limitations_and_markush_evidence(
    *,
    compound_type: str,
    source_entries: list[SearchSourcePlanEntry],
    settings: Settings,
) -> tuple[list[str], MarkushEvidenceReceipt | None]:
    limitations = [
        (
            "PubChem scaffold/substructure expansion searches developed compounds linked "
            "to patents; it does not search generic Markush definitions or establish "
            "legal claim scope. WIPO PATENTSCOPE Markush verification remains a manual "
            "analyst workflow because WIPO prohibits robots and exposes no free Markush API."
        ),
        (
            "Only PubChem-SDQ candidates receive the composite/BM25/embedding funnel; "
            "supplemental-source candidates are deduplicated rather than jointly calibrated."
        ),
    ]
    if compound_type in {"biologic", "peptide"}:
        sequence_source = next(
            (entry for entry in source_entries if entry.source == "ncbi_patent_sequence"),
            None,
        )
        if sequence_source is None or sequence_source.execution_status != "ok":
            limitations.append(
                "The required NCBI patent-protein sequence lane did not complete; "
                "sequence-claim coverage is unavailable and the run must fail closed."
            )
        else:
            limitations.append(
                "NCBI states that some USPTO pre-grant patent sequences are not "
                "incorporated in GenBank; BLAST similarity therefore does not establish "
                "exhaustive sequence-claim recall or legal claim scope."
            )

    raw_markush_evidence = getattr(settings, "markush_evidence_receipt", None)
    markush_evidence = (
        MarkushEvidenceReceipt.model_validate(raw_markush_evidence)
        if raw_markush_evidence is not None
        else None
    )
    if markush_evidence is not None:
        limitations.append(
            "The supervised PATENTSCOPE receipt proves what was searched and selected; "
            "it does not by itself establish legal claim construction or exhaustive recall."
        )
    return limitations, markush_evidence


def _search_query_plan_payload(
    *,
    compound: ResolvedCompound,
    settings: Settings,
    compound_type: str,
    iterations: list[SearchQueryIteration],
    source_entries: list[SearchSourcePlanEntry],
    ranking_signals: list[str],
    ranking_configuration: SearchRankingConfiguration,
    execution_configuration: SearchExecutionConfiguration,
    sequence_queries: list[dict[str, int | str]],
    genus_queries: list[dict[str, str]],
    markush_evidence: MarkushEvidenceReceipt | None,
    known_retrieval_limitations: list[str],
) -> dict[str, object]:
    return {
        "schema_version": "search-query-plan-v2",
        "compound_name": str(getattr(compound, "name", "") or ""),
        "compound_type": compound_type,
        "canonical_smiles": str(getattr(compound, "canonical_smiles", "") or ""),
        "inchi_key": str(getattr(compound, "inchi_key", "") or ""),
        "pubchem_cid": getattr(compound, "pubchem_cid", None),
        "synonyms": list(getattr(compound, "synonyms", []) or []),
        "cas_numbers": list(getattr(compound, "cas_numbers", []) or []),
        "target_jurisdictions": list(getattr(settings, "search_allowed_jurisdictions", []) or []),
        "iterations": [iteration.model_dump(mode="json") for iteration in iterations],
        "sources": [entry.model_dump(mode="json") for entry in source_entries],
        "ranking_signals": list(dict.fromkeys(ranking_signals)),
        "ranking_configuration": ranking_configuration.model_dump(mode="json"),
        "execution_configuration": execution_configuration.model_dump(mode="json"),
        "sequence_queries": sequence_queries,
        "genus_queries": genus_queries,
        "true_markush_coverage_status": (
            markush_evidence.status
            if compound_type == "small_molecule" and markush_evidence is not None
            else ("not_run" if compound_type == "small_molecule" else "not_applicable")
        ),
        "markush_evidence": (
            markush_evidence.model_dump(mode="json") if markush_evidence is not None else None
        ),
        "known_retrieval_limitations": known_retrieval_limitations,
    }


def _search_query_plan_sha256(plan_payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            plan_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def build_search_query_plan(
    *,
    compound,
    expanded_queries,
    search_loop_result,
    source_health,
    settings,
    patent_hits=(),
) -> SearchQueryPlan:
    """Build a content-addressed record of exact terms, sources, and ranking modes."""
    typed_compound = cast("ResolvedCompound", compound)
    typed_search_loop_result = cast("SearchLoopResult | None", search_loop_result)
    typed_source_health = cast("SourceHealth | None", source_health)
    typed_settings = cast("Settings", settings)
    typed_patent_hits = cast("Iterable[PatentHit]", patent_hits)
    iterations = _search_query_iterations(expanded_queries, typed_search_loop_result)
    has_expansion = _has_expanded_query_terms(iterations)
    health_by_source = _source_health_by_name(typed_source_health)
    compound_type = str(getattr(typed_compound, "compound_type", "small_molecule"))
    source_entries = _source_plan_entries(
        settings=typed_settings,
        health_by_source=health_by_source,
        has_expansion=has_expansion,
        compound_type=compound_type,
    )
    ranking_signals = _ranking_signals(typed_settings)
    ranking_configuration = _ranking_configuration(typed_settings)
    execution_configuration = _execution_configuration(typed_settings)
    sequence_queries = _sequence_queries(typed_compound)
    genus_queries = _genus_queries(
        typed_compound,
        compound_type=compound_type,
        patent_hits=typed_patent_hits,
    )
    known_retrieval_limitations, markush_evidence = _retrieval_limitations_and_markush_evidence(
        compound_type=compound_type,
        source_entries=source_entries,
        settings=typed_settings,
    )
    plan_payload = _search_query_plan_payload(
        compound=typed_compound,
        settings=typed_settings,
        compound_type=compound_type,
        iterations=iterations,
        source_entries=source_entries,
        ranking_signals=ranking_signals,
        ranking_configuration=ranking_configuration,
        execution_configuration=execution_configuration,
        sequence_queries=sequence_queries,
        genus_queries=genus_queries,
        markush_evidence=markush_evidence,
        known_retrieval_limitations=known_retrieval_limitations,
    )
    return SearchQueryPlan.model_validate(
        {**plan_payload, "plan_sha256": _search_query_plan_sha256(plan_payload)}
    )


def build_pipeline_audit_trail(
    *,
    search_funnel: list,
    triage_audit: list[TriageAuditEntry],
    analysis_audit: list[AnalysisAuditEntry],
    timing_data: list,
    patent_hits: list,
    triage_results: list,
    analyses: list,
    prompt_hashes: dict[str, str] | None = None,
    compound=None,
    expanded_queries=None,
    search_loop_result=None,
    source_health=None,
    settings=None,
) -> PipelineAuditTrail:
    normalized_search_funnel = [
        entry if isinstance(entry, SearchFunnelEntry) else SearchFunnelEntry.model_validate(entry)
        for entry in search_funnel
    ]
    query_plan = None
    if compound is not None and settings is not None:
        query_plan = build_search_query_plan(
            compound=compound,
            expanded_queries=expanded_queries,
            search_loop_result=search_loop_result,
            source_health=source_health,
            settings=settings,
            patent_hits=patent_hits,
        )
    return PipelineAuditTrail(
        search_funnel=normalized_search_funnel,
        query_plan=query_plan,
        triage_audit=triage_audit,
        analysis_audit=analysis_audit,
        timing_data=timing_data,
        total_patents_discovered=(
            len(normalized_search_funnel) if normalized_search_funnel else len(patent_hits)
        ),
        patents_after_hard_filter=(
            sum(bool(entry.passed_hard_filter) for entry in normalized_search_funnel)
            if normalized_search_funnel
            else len(patent_hits)
        ),
        patents_after_ranking=(
            sum(bool(entry.included_in_triage) for entry in normalized_search_funnel)
            if normalized_search_funnel
            else len(patent_hits)
        ),
        patents_after_triage=len(triage_results),
        patents_analyzed=len(analyses),
        prompt_hashes=prompt_hashes or {},
    )


def build_prior_step_tokens(
    *,
    triage_input_tokens: int,
    triage_output_tokens: int,
    critic_input_tokens: int,
    critic_output_tokens: int,
    search_loop_input_tokens: int = 0,
    search_loop_output_tokens: int = 0,
    doe_input_tokens: int,
    doe_output_tokens: int,
    invalidity_input_tokens: int,
    invalidity_output_tokens: int,
) -> list[StepTokenUsage]:
    tokens = [
        StepTokenUsage(
            step_name="step3_triage",
            model_role="triage",
            input_tokens=triage_input_tokens,
            output_tokens=triage_output_tokens,
        ),
        StepTokenUsage(
            step_name="step4b_critic",
            model_role="analysis",
            input_tokens=critic_input_tokens,
            output_tokens=critic_output_tokens,
        ),
        StepTokenUsage(
            step_name="step5_doe",
            model_role="analysis",
            input_tokens=doe_input_tokens,
            output_tokens=doe_output_tokens,
        ),
        StepTokenUsage(
            step_name="step6_invalidity",
            model_role="analysis",
            input_tokens=invalidity_input_tokens,
            output_tokens=invalidity_output_tokens,
        ),
    ]
    if search_loop_input_tokens or search_loop_output_tokens:
        tokens.insert(
            0,
            StepTokenUsage(
                step_name="step2_search_loop",
                model_role="triage",
                input_tokens=search_loop_input_tokens,
                output_tokens=search_loop_output_tokens,
            ),
        )
    return tokens
