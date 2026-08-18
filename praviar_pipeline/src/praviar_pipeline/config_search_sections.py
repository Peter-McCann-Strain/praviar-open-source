"""Search and source settings mixins for the Praviar Pipeline runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import Field


class SearchSourceSettingsMixin:
    # Rate limits
    pubchem_requests_per_second: float = Field(default=5.0, gt=0.0)
    surechembl_requests_per_second: float = Field(default=2.0, gt=0.0)
    patentsview_requests_per_minute: float = Field(default=45.0, gt=0.0)

    # BigQuery safety and caching
    bigquery_max_bytes_billed: int = Field(
        default=10 * 1024**3,
        description="Maximum bytes scanned per BigQuery query",
    )
    bigquery_cache_enabled: bool = Field(
        default=True,
        description="Cache BigQuery search results to avoid redundant scans",
    )
    bigquery_cache_ttl_days: int = Field(default=7, description="Cache TTL in days")
    bigquery_cache_dir: str = Field(
        default="~/.praviar_pipeline/cache/bigquery",
        description="Directory for BigQuery result cache files",
    )

    # Search funnel limits
    search_max_sdq_patents: int = Field(
        default=50000,
        description="Max patents to fetch from PubChem SDQ API",
    )
    search_max_ranked_results: int = Field(
        default=1000,
        description="Top N patents to keep after ranking funnel",
    )
    search_include_expired: bool = Field(
        default=True,
        description="Include recently-expired patents in results",
    )
    search_expired_grace_years: int = Field(
        default=5,
        description="How many years past expiry to still include",
    )
    search_max_synonyms_bigquery: int = Field(default=25, ge=1)
    search_max_cas_bigquery: int = Field(default=10, ge=1)
    search_max_family_patents: int = Field(default=50, ge=1)
    search_max_legal_status_patents: int = Field(default=200, ge=1)
    search_max_epo_claims_patents: int = Field(
        default=150,
        ge=1,
        description=(
            "Max EP patents to fetch claims from EPO OPS during live claims collection. "
            "The cap bounds sequential upstream work and protects the configured "
            "runtime budget for broad result sets."
        ),
    )
    search_max_patentsview_claims_patents: int = Field(
        default=100,
        ge=1,
        description=(
            "Max US patents to fetch claims from PatentsView during live claims collection. "
            "The cap bounds fallback-source work and protects the configured runtime "
            "and upstream-request budgets."
        ),
    )
    rank_bm25_pool_size: int = Field(default=1000, ge=100)
    rank_bm25_synonyms: int = Field(default=15, ge=1)
    rank_bm25_cas: int = Field(default=10, ge=1)
    rank_title_synonyms: int = Field(default=50, ge=1)
    rank_min_synonym_length: int = Field(default=3, ge=1)

    # Resolution and triage
    resolve_max_related_compounds: int = Field(default=20, ge=1)
    resolve_max_synonyms: int = Field(default=100, ge=1)
    resolve_similarity_threshold: float = Field(default=0.7, gt=0.0, le=1.0)
    triage_batch_size: int = Field(default=10, ge=1)
    triage_max_abstract_chars: int = Field(default=5000, ge=100)
    triage_max_claims_chars: int = Field(default=30000, ge=100)
    scholarly_early_exit_threshold: int = Field(default=20, ge=1)
    scholarly_max_synonyms: int = Field(default=5, ge=1)

    # Prior-art literature branch (SG-130): OpenAlex + Semantic Scholar as a
    # sibling search to patent search, feeding step 6 invalidity analysis only.
    literature_search_enabled: bool = Field(
        default=True,
        description="Enable OpenAlex + Semantic Scholar literature search alongside patent search",
    )
    literature_max_per_source: int = Field(
        default=25,
        ge=5,
        le=100,
        description="Max references to fetch per literature source (OpenAlex, Semantic Scholar)",
    )
    search_source_timeout_s: float = Field(
        default=90.0,
        ge=1.0,
        description="Hard timeout in seconds for each concurrent patent search source task",
    )
    source_failure_policy: Literal["coverage_aware", "fail_fast", "best_effort"] = Field(
        default="coverage_aware",
        description=(
            "How source failures affect a run. coverage_aware fails only when minimum "
            "legal-search coverage is absent; fail_fast preserves strict required-source "
            "behavior; best_effort records failures without stopping search/reporting."
        ),
    )

    # Upstream source integrations
    ops_consumer_key: str = ""
    ops_consumer_secret: str = ""
    ops_requests_per_minute: float = Field(default=30.0, gt=0.0)
    ncbi_api_key: str = ""
    pubmed_requests_per_second: float = Field(default=3.0, gt=0.0)
    semantic_scholar_api_key: str = ""
    semantic_scholar_requests_per_second: float = Field(default=0.8, gt=0.0)
    openalex_api_key: str = Field(
        default="",
        description=(
            "OpenAlex API key. Required when the OpenAlex client is used; an empty "
            "value fails closed before any request is attempted."
        ),
    )
    openalex_requests_per_second: float = Field(
        default=10.0,
        gt=0.0,
        description="Operator-configured local request-rate cap for OpenAlex",
    )
    lens_requests_per_second: float = Field(default=10.0, gt=0.0)
    lens_max_patent_results: int = Field(default=200, ge=1)
    kipris_api_key: str = ""
    kipris_requests_per_minute: float = Field(default=30.0, gt=0.0)
    kipris_max_results: int = Field(default=100, ge=1)
    patentscope_username: str = ""
    patentscope_password: str = ""
    patentscope_requests_per_minute: float = Field(default=10.0, gt=0.0)
    patentscope_max_results: int = Field(default=100, ge=1)
    uspto_odp_requests_per_minute: float = Field(default=50.0, gt=0.0)
    tavily_requests_per_minute: float = Field(default=10.0, gt=0.0)

    # Search models and broadening
    specter_model_name: str = "mpi-inno-comp/paecter"
    specter_cache_dir: str = ""
    embedding_ranking_enabled: bool = True
    resolve_tanimoto_step: float = Field(default=0.02, gt=0.0, le=0.1)
    search_allowed_jurisdictions: list[str] = Field(
        default=["US", "WO", "EP", "JP", "KR", "CN", "IN", "CA", "AU"],
        description="Patent jurisdictions to include in ranking filter",
    )
    search_tanimoto_threshold: float = Field(
        default=0.55,
        gt=0.0,
        le=1.0,
        description="Tanimoto similarity threshold for structure search",
    )
    search_enable_pubchem: bool = Field(
        default=True,
        description="Enable PubChem-backed search sources (SDQ + similar compounds)",
    )
    search_enable_pubchem_genus: bool = Field(
        default=True,
        description=(
            "Require PubChem scaffold/substructure corpus expansion for small-molecule "
            "matters. This finds developed-structure genus candidates, not true Markush "
            "definitions."
        ),
    )
    pubchem_genus_max_compounds: int = Field(default=2000, ge=1, le=2000)
    pubchem_genus_max_patents: int = Field(default=5000, ge=1, le=5000)
    pubchem_genus_max_seconds: int = Field(default=60, ge=1, le=300)
    search_enable_bigquery: bool = Field(
        default=True,
        description="Enable Google Patents BigQuery-backed search sources",
    )
    search_enable_surechembl: bool = Field(
        default=True,
        description="Enable SureChEMBL structure search",
    )
    search_enable_patcid: bool = Field(default=True, description="Enable PatCID search")
    search_surechembl_substructure_enabled: bool = Field(
        default=True,
        description="Enable SureChEMBL substructure search in addition to similarity",
    )
    search_enable_ncbi_patent_sequence: bool = Field(
        default=True,
        description=(
            "Require the NCBI GenBank Patent protein BLAST lane for biologic and "
            "peptide matters with an exact public FDA GSRS sequence."
        ),
    )
    ncbi_patent_sequence_max_hits: int = Field(default=100, ge=1, le=500)
    ncbi_patent_sequence_min_identity: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
    )
    ncbi_patent_sequence_min_query_coverage: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
    )
    ncbi_patent_sequence_max_polls: int = Field(default=2, ge=1, le=3)
    ncbi_patent_sequence_poll_interval_seconds: float = Field(
        default=60.0,
        ge=60.0,
        description="NCBI requires at least one minute between polls for one BLAST RID.",
    )
    search_citation_traversal_enabled: bool = Field(
        default=True,
        description="Enable examiner citation network traversal via BigQuery",
    )
    search_citation_max_depth: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Max depth for citation network traversal",
    )
    search_citation_max_per_level: int = Field(
        default=50,
        ge=10,
        description="Max patents to follow per citation level",
    )
    search_max_patent_term_calc: int = Field(
        default=50,
        ge=1,
        description="Max patents to run patent term calculation on",
    )
    continuation_expansion_enabled: bool = Field(
        default=True,
        description="Expand Step 2 hits with continuations / divisionals / reissues (SG-122)",
    )
    continuation_max_patents: int = Field(
        default=50,
        ge=1,
        description="Max parent hits to traverse when expanding continuations",
    )
    continuation_max_depth: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Max BFS depth when chasing continuation children",
    )
    continuation_expansion_timeout_s: float = Field(
        default=300.0,
        gt=0.0,
        description="Hard wall-clock timeout for the whole continuation expansion phase",
    )
    citation_seed_max_patents: int = Field(default=20, ge=1)
    ptab_requests_per_minute: float = Field(default=60.0, gt=0.0)
    fingerprint_radius: int = Field(default=2, ge=1)
    fingerprint_nbits: int = Field(default=2048, ge=256)
    molecular_weight_broadening_threshold: float = Field(default=500.0, ge=0.0)
