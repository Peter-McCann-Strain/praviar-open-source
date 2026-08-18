"""Pipeline audit-trail response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.reports_tracking_search import ExpandedSearchQueriesResponse


class SearchSourcePlanEntryResponse(BaseModel):
    """One source's role and final execution disposition."""

    source: str
    roles: list[str] = Field(default_factory=list)
    criticality: Literal["core", "optional"] = "optional"
    query_categories: list[str] = Field(default_factory=list)
    execution_status: str
    result_count: int = 0
    reason: str = ""


class SearchQueryIterationResponse(BaseModel):
    """Structured query expansion used for one retrieval iteration."""

    iteration_number: int
    queries: ExpandedSearchQueriesResponse


class SearchRankingConfigurationResponse(BaseModel):
    """Exact ranking cutoffs and weights used by the retrieval funnel."""

    score_model_version: str = "composite-bm25-embedding-v1"
    max_sdq_patents: int
    max_ranked_results: int
    include_expired: bool
    expired_grace_years: int
    bm25_pool_size: int
    embedding_enabled: bool
    hybrid_retrieval_enabled: bool
    composite_cpc_weight: float
    composite_compound_count_weight: float
    composite_recency_weight: float
    composite_title_weight: float
    composite_multi_source_weight: float
    blend_composite_2way: float
    blend_bm25_2way: float
    blend_composite_3way: float
    blend_bm25_3way: float
    blend_embedding_3way: float


class SearchExecutionConfigurationResponse(BaseModel):
    """Exact structure, graph, and iterative-search controls used."""

    source_failure_policy: str
    tanimoto_threshold: float
    surechembl_substructure_enabled: bool
    citation_traversal_enabled: bool
    citation_max_depth: int
    citation_max_per_level: int
    continuation_expansion_enabled: bool
    continuation_max_depth: int
    continuation_max_patents: int
    search_loop_enabled: bool
    search_loop_max_iterations: int
    search_loop_coverage_threshold: float
    ncbi_patent_sequence_enabled: bool
    ncbi_patent_sequence_max_hits: int
    ncbi_patent_sequence_min_identity: float
    ncbi_patent_sequence_min_query_coverage: float
    pubchem_genus_enabled: bool
    pubchem_genus_max_compounds: int
    pubchem_genus_max_patents: int
    pubchem_genus_max_seconds: int


class SearchSequenceQueryReceiptResponse(BaseModel):
    """Hash/length receipt for one public FDA GSRS sequence query."""

    subunit_index: int
    sequence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence_length: int
    identity_source: str = "fda_gsrs_public"


class SearchGenusQueryReceiptResponse(BaseModel):
    """Hash-only receipt for one PubChem scaffold/substructure query."""

    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_role: str
    search_type: str = "pubchem_fastsubstructure"


class MarkushEvidenceReceiptResponse(BaseModel):
    """Tamper-evident supervised PATENTSCOPE Markush evidence."""

    schema_version: Literal["patentscope-markush-evidence-v3"] = "patentscope-markush-evidence-v3"
    source: Literal["wipo_patentscope_manual"] = "wipo_patentscope_manual"
    source_url: str
    status: Literal["verified_manual", "not_run", "incomplete", "unavailable"]
    organization_id: str
    target_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_role: Literal["target_compound", "murcko_scaffold"]
    chemical_search_mode: Literal["exact", "substructure", "scaffold"]
    markush_enabled: Literal[True] = True
    markush_method: Literal["enumeration", "formula_matching"]
    markush_match_mode: Literal["exact", "substructure", "fuzzy"]
    wipo_query_field: Literal["ENUM"] | None = None
    family_grouping_enabled: bool
    executed_at: datetime | None = None
    server_imported_at: datetime | None = None
    analyst_identity: str | None = None
    reviewer_identity: str | None = None
    artifact_filename: str | None = None
    artifact_media_type: str | None = None
    imported_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    imported_artifact_size_bytes: int | None = None
    controls_artifact_filename: str | None = None
    controls_artifact_media_type: Literal["image/png"] | None = None
    controls_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    controls_artifact_size_bytes: int | None = None
    result_count: int | None = None
    selected_publication_ids: list[str] = Field(default_factory=list)
    selected_publication_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: list[str] = Field(default_factory=list)
    attestation_key_id: str | None = None
    attestation_hmac_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SearchQueryPlanResponse(BaseModel):
    """Content-addressed, reproducible search plan."""

    schema_version: Literal["search-query-plan-v2"] = "search-query-plan-v2"
    compound_name: str = ""
    compound_type: str = "small_molecule"
    canonical_smiles: str = ""
    inchi_key: str = ""
    pubchem_cid: int | None = None
    synonyms: list[str] = Field(default_factory=list)
    cas_numbers: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    iterations: list[SearchQueryIterationResponse] = Field(default_factory=list)
    sources: list[SearchSourcePlanEntryResponse] = Field(default_factory=list)
    ranking_signals: list[str] = Field(default_factory=list)
    ranking_configuration: SearchRankingConfigurationResponse | None = None
    execution_configuration: SearchExecutionConfigurationResponse | None = None
    sequence_queries: list[SearchSequenceQueryReceiptResponse] = Field(default_factory=list)
    genus_queries: list[SearchGenusQueryReceiptResponse] = Field(default_factory=list)
    true_markush_coverage_status: Literal[
        "verified_manual",
        "not_run",
        "incomplete",
        "unavailable",
        "not_applicable",
    ] = "not_run"
    markush_evidence: MarkushEvidenceReceiptResponse | None = None
    known_retrieval_limitations: list[str] = Field(default_factory=list)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SearchFunnelEntryResponse(BaseModel):
    """One patent's disposition through the search funnel."""

    patent_id: str
    candidate_index: int | None = None
    sources_found_in: list[str] = Field(default_factory=list)
    disposition: str = "legacy"
    exclusion_stage: str = ""
    passed_hard_filter: bool = True
    filter_reason: str = ""
    composite_score: float | None = None
    bm25_score: float | None = None
    bm25_normalized_score: float | None = None
    embedding_score: float | None = None
    embedding_normalized_score: float | None = None
    final_blend_score: float | None = None
    composite_rank: int | None = None
    bm25_rank: int | None = None
    embedding_rank: int | None = None
    pre_cut_rank: int | None = None
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


class TriageAuditEntryResponse(BaseModel):
    """One triage decision record."""

    patent_id: str
    relevance: str
    reason: str
    confidence: float = 0.0
    passed_triage: bool = False


class AnalysisAuditEntryResponse(BaseModel):
    """One deep-analysis selection record."""

    patent_id: str
    selected_for_analysis: bool
    selection_reason: str = ""
    risk_level: str | None = None
    selected_for_doe: bool = False
    selected_for_invalidity: bool = False


class StepTimingResponse(BaseModel):
    """Timing metadata for one pipeline step."""

    step_name: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    items_processed: int = 0
    items_output: int = 0


class PipelineAuditTrailResponse(BaseModel):
    """Full deterministic pipeline audit trail."""

    search_funnel: list[SearchFunnelEntryResponse] = Field(default_factory=list)
    query_plan: SearchQueryPlanResponse | None = None
    triage_audit: list[TriageAuditEntryResponse] = Field(default_factory=list)
    analysis_audit: list[AnalysisAuditEntryResponse] = Field(default_factory=list)
    timing_data: list[StepTimingResponse] = Field(default_factory=list)
    total_patents_discovered: int = 0
    patents_after_hard_filter: int = 0
    patents_after_ranking: int = 0
    patents_after_triage: int = 0
    patents_analyzed: int = 0
    prompt_hashes: dict[str, str] = Field(
        default_factory=dict,
        description=("Map of prompt filename -> SHA-256 hex of file contents at load time."),
    )
