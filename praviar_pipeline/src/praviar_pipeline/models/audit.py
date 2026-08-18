"""Audit trail models — provenance tracking for the FTO pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from praviar_pipeline.models.markush_evidence import (
    MarkushEvidenceReceipt,
    MarkushEvidenceStatus,
    markush_query_structure_sha256,
)
from praviar_pipeline.models.patent import GenusQueryRole
from praviar_pipeline.models.search import ExpandedSearchQueries

SearchSourceExecutionStatus = Literal[
    "ok",
    "failed",
    "skipped",
    "not_configured",
    "not_requested",
    "not_applicable",
    "missing_audit",
]
SearchSourceFailurePolicy = Literal["coverage_aware", "fail_fast", "best_effort"]
SearchFunnelDisposition = Literal[
    "legacy",
    "included_in_triage",
    "hard_filter_rejected",
    "composite_pool_cut",
    "final_rank_cut",
    "supplementary_included",
]


class SearchSourcePlanEntry(BaseModel):
    """One source's role and final execution disposition in the query plan."""

    model_config = ConfigDict(extra="forbid")

    source: str
    roles: list[str] = Field(default_factory=list)
    criticality: Literal["core", "optional"] = "optional"
    query_categories: list[str] = Field(default_factory=list)
    execution_status: SearchSourceExecutionStatus
    result_count: int = Field(default=0, ge=0)
    reason: str = ""


class SearchQueryIteration(BaseModel):
    """The exact structured query set executed for one retrieval iteration."""

    model_config = ConfigDict(extra="forbid")

    iteration_number: int = Field(ge=1)
    queries: ExpandedSearchQueries


class SearchRankingConfiguration(BaseModel):
    """Exact ranking cutoffs and weights used by the retrieval funnel."""

    model_config = ConfigDict(extra="forbid")

    score_model_version: Literal["composite-bm25-embedding-v1"] = "composite-bm25-embedding-v1"
    max_sdq_patents: int = Field(ge=1)
    max_ranked_results: int = Field(ge=1)
    include_expired: bool
    expired_grace_years: int = Field(ge=0)
    bm25_pool_size: int = Field(ge=1)
    embedding_enabled: bool
    hybrid_retrieval_enabled: bool
    composite_cpc_weight: float = Field(ge=0.0, le=1.0)
    composite_compound_count_weight: float = Field(ge=0.0, le=1.0)
    composite_recency_weight: float = Field(ge=0.0, le=1.0)
    composite_title_weight: float = Field(ge=0.0, le=1.0)
    composite_multi_source_weight: float = Field(ge=0.0, le=1.0)
    blend_composite_2way: float = Field(ge=0.0, le=1.0)
    blend_bm25_2way: float = Field(ge=0.0, le=1.0)
    blend_composite_3way: float = Field(ge=0.0, le=1.0)
    blend_bm25_3way: float = Field(ge=0.0, le=1.0)
    blend_embedding_3way: float = Field(ge=0.0, le=1.0)


class SearchExecutionConfiguration(BaseModel):
    """Exact structure, graph, and iterative-search controls used."""

    model_config = ConfigDict(extra="forbid")

    source_failure_policy: SearchSourceFailurePolicy
    tanimoto_threshold: float = Field(gt=0.0, le=1.0)
    surechembl_substructure_enabled: bool
    citation_traversal_enabled: bool
    citation_max_depth: int = Field(ge=1)
    citation_max_per_level: int = Field(ge=1)
    continuation_expansion_enabled: bool
    continuation_max_depth: int = Field(ge=1)
    continuation_max_patents: int = Field(ge=1)
    search_loop_enabled: bool
    search_loop_max_iterations: int = Field(ge=1)
    search_loop_coverage_threshold: float = Field(ge=0.0, le=1.0)
    ncbi_patent_sequence_enabled: bool
    ncbi_patent_sequence_max_hits: int = Field(ge=1)
    ncbi_patent_sequence_min_identity: float = Field(ge=0.0, le=1.0)
    ncbi_patent_sequence_min_query_coverage: float = Field(ge=0.0, le=1.0)
    pubchem_genus_enabled: bool
    pubchem_genus_max_compounds: int = Field(ge=1)
    pubchem_genus_max_patents: int = Field(ge=1)
    pubchem_genus_max_seconds: int = Field(ge=1)


class SearchSequenceQueryReceipt(BaseModel):
    """Non-secret receipt for an exact public sequence submitted to BLAST."""

    model_config = ConfigDict(extra="forbid")

    subunit_index: int = Field(ge=1)
    sequence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence_length: int = Field(ge=1, le=10000)
    identity_source: Literal["fda_gsrs_public"] = "fda_gsrs_public"


class SearchGenusQueryReceipt(BaseModel):
    """Non-secret receipt for one PubChem developed-structure genus query."""

    model_config = ConfigDict(extra="forbid")

    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_role: GenusQueryRole
    search_type: Literal["pubchem_fastsubstructure"] = "pubchem_fastsubstructure"


class SearchQueryPlan(BaseModel):
    """Reproducible query/source plan retained with the report audit trail."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["search-query-plan-v2"] = "search-query-plan-v2"
    compound_name: str = ""
    compound_type: Literal["small_molecule", "biologic", "peptide"] = "small_molecule"
    canonical_smiles: str = ""
    inchi_key: str = ""
    pubchem_cid: int | None = None
    synonyms: list[str] = Field(default_factory=list)
    cas_numbers: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    iterations: list[SearchQueryIteration] = Field(default_factory=list)
    sources: list[SearchSourcePlanEntry] = Field(default_factory=list)
    ranking_signals: list[str] = Field(default_factory=list)
    ranking_configuration: SearchRankingConfiguration
    execution_configuration: SearchExecutionConfiguration
    sequence_queries: list[SearchSequenceQueryReceipt] = Field(default_factory=list)
    genus_queries: list[SearchGenusQueryReceipt] = Field(default_factory=list)
    true_markush_coverage_status: MarkushEvidenceStatus | Literal["not_applicable"] = "not_run"
    markush_evidence: MarkushEvidenceReceipt | None = None
    known_retrieval_limitations: list[str] = Field(default_factory=list)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _verify_plan_digest(self) -> SearchQueryPlan:
        if self.compound_type != "small_molecule":
            if self.true_markush_coverage_status != "not_applicable":
                raise ValueError("non-small-molecule query plan has a Markush coverage status")
            if self.markush_evidence is not None:
                raise ValueError("non-small-molecule query plan cannot carry Markush evidence")
        elif self.markush_evidence is None:
            if self.true_markush_coverage_status != "not_run":
                raise ValueError("Markush coverage status lacks its evidence receipt")
        else:
            if self.true_markush_coverage_status != self.markush_evidence.status:
                raise ValueError("Markush coverage status does not match its evidence receipt")
            if not self.canonical_smiles:
                raise ValueError("Markush evidence lacks a bound target structure")
            expected_target_digest = markush_query_structure_sha256(self.canonical_smiles)
            if self.markush_evidence.target_structure_sha256 != expected_target_digest:
                raise ValueError(
                    "Markush evidence target structure is not bound to this query plan"
                )
            query_structure = (
                self.canonical_smiles
                if self.markush_evidence.query_role == "target_compound"
                else next(
                    (
                        query.query_sha256
                        for query in self.genus_queries
                        if query.query_role == "murcko_scaffold"
                    ),
                    "",
                )
            )
            if self.markush_evidence.query_role == "target_compound":
                if not query_structure:
                    raise ValueError("target-compound Markush evidence lacks a bound structure")
                expected_query_digest = markush_query_structure_sha256(query_structure)
            else:
                expected_query_digest = query_structure
            if self.markush_evidence.query_structure_sha256 != expected_query_digest:
                raise ValueError("Markush evidence query is not bound to this query plan")

        payload = self.model_dump(mode="json", exclude={"plan_sha256"})
        expected = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if self.plan_sha256 != expected:
            raise ValueError("search query plan digest mismatch")
        return self


class SearchFunnelEntry(BaseModel):
    """Tracks the row-level disposition of one retrieval candidate."""

    patent_id: str
    candidate_index: int | None = Field(default=None, ge=0)
    sources_found_in: list[str] = Field(default_factory=list)
    disposition: SearchFunnelDisposition = "legacy"
    exclusion_stage: Literal["", "hard_filter", "composite_pool", "final_rank"] = ""
    passed_hard_filter: bool = True
    filter_reason: str = ""  # "non-US", "expired_beyond_grace", etc.
    composite_score: float | None = None
    bm25_score: float | None = None
    bm25_normalized_score: float | None = None
    embedding_score: float | None = None
    embedding_normalized_score: float | None = None
    final_blend_score: float | None = None
    composite_rank: int | None = Field(default=None, ge=1)
    bm25_rank: int | None = Field(default=None, ge=1)
    embedding_rank: int | None = Field(default=None, ge=1)
    pre_cut_rank: int | None = Field(default=None, ge=1)
    final_rank: int | None = None
    included_in_triage: bool = False
    input_row_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    audit_entry_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _check_filter_reason(self) -> SearchFunnelEntry:
        """Validate new row-level dispositions and their content address."""
        if self.disposition == "hard_filter_rejected":
            if self.passed_hard_filter or not self.filter_reason:
                raise ValueError("hard-filter rejection requires a reason and failed status")
            if self.included_in_triage or self.exclusion_stage != "hard_filter":
                raise ValueError("hard-filter rejection has an invalid disposition")
        elif self.disposition in {"composite_pool_cut", "final_rank_cut"}:
            expected_stage = (
                "composite_pool" if self.disposition == "composite_pool_cut" else "final_rank"
            )
            if not self.passed_hard_filter or self.included_in_triage:
                raise ValueError("rank-cut candidate has an invalid disposition")
            if self.exclusion_stage != expected_stage or not self.filter_reason:
                raise ValueError("rank-cut candidate requires its exact exclusion stage")
        elif self.disposition in {"included_in_triage", "supplementary_included"}:
            if not self.passed_hard_filter or not self.included_in_triage:
                raise ValueError("included candidate has an invalid disposition")
            if self.exclusion_stage or self.filter_reason:
                raise ValueError("included candidate cannot carry an exclusion reason")

        if self.audit_entry_sha256 is not None:
            payload = self.model_dump(mode="json", exclude={"audit_entry_sha256"})
            expected = hashlib.sha256(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            if self.audit_entry_sha256 != expected:
                raise ValueError("search funnel audit entry digest mismatch")
        if not self.passed_hard_filter and not self.filter_reason:
            import structlog

            structlog.get_logger().warning(
                "funnel_entry_missing_filter_reason",
            )
        return self


def build_search_funnel_entry(**payload: object) -> SearchFunnelEntry:
    """Build a content-addressed search-funnel decision receipt."""
    canonical = SearchFunnelEntry.model_validate(payload).model_dump(
        mode="json",
        exclude={"audit_entry_sha256"},
    )
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return SearchFunnelEntry.model_validate({**canonical, "audit_entry_sha256": digest})


class TriageAuditEntry(BaseModel):
    """Tracks triage decisions for a single patent."""

    patent_id: str
    relevance: str
    reason: str
    confidence: float = 0.0
    passed_triage: bool = False


class AnalysisAuditEntry(BaseModel):
    """Tracks which patents were selected for claim analysis and why."""

    patent_id: str
    selected_for_analysis: bool
    selection_reason: str = ""
    risk_level: str | None = None
    selected_for_doe: bool = False
    selected_for_invalidity: bool = False


class StepTokenUsage(BaseModel):
    """Token usage for a single pipeline step, with model role for cost attribution."""

    step_name: str
    model_role: str = Field(description="triage, analysis, or deep")
    model_name: str = Field(
        default="",
        description="Actual model identifier used (e.g. claude-haiku-4-5-20251001)",
    )
    input_tokens: int = 0
    output_tokens: int = 0


class StepTiming(BaseModel):
    """Execution timing for a single pipeline step."""

    step_name: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    items_processed: int = 0
    items_output: int = 0


class PipelineAuditTrail(BaseModel):
    """Governed audit trail for a pipeline run.

    Captures row-level discovery → filtering → ranking → triage → analysis
    provenance, aggregate counts, plus timing data for each step. Rank-cut and
    hard-filtered SDQ candidates retain content-addressed decision receipts.
    The ``prompt_hashes`` field pins the exact prompt-file revisions used
    so the run can be reproduced and audited against EU AI Act
    record-keeping obligations (Workstream 3).
    """

    search_funnel: list[SearchFunnelEntry] = Field(default_factory=list)
    query_plan: SearchQueryPlan | None = None
    triage_audit: list[TriageAuditEntry] = Field(default_factory=list)
    analysis_audit: list[AnalysisAuditEntry] = Field(default_factory=list)
    timing_data: list[StepTiming] = Field(default_factory=list)
    total_patents_discovered: int = 0
    patents_after_hard_filter: int = 0
    patents_after_ranking: int = 0
    patents_after_triage: int = 0
    patents_analyzed: int = 0
    prompt_hashes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of prompt filename -> SHA-256 hex of file contents at load time. "
            "Populated from the process-wide PromptHasher singleton at finalisation."
        ),
    )
