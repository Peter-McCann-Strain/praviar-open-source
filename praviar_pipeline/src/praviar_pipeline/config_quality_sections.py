"""Quality, scoring, and display settings mixins for the Praviar Pipeline runtime."""

from __future__ import annotations

from pydantic import Field


class QualityAndDisplaySettingsMixin:
    # Ranking and confidence scoring
    rank_weight_cpc: float = Field(default=0.30, ge=0.0, le=1.0)
    rank_weight_compound_count: float = Field(default=0.20, ge=0.0, le=1.0)
    rank_weight_recency: float = Field(default=0.15, ge=0.0, le=1.0)
    rank_weight_title: float = Field(default=0.15, ge=0.0, le=1.0)
    rank_weight_multi_source: float = Field(default=0.20, ge=0.0, le=1.0)
    rank_compound_count_low: int = Field(default=5, ge=1)
    rank_compound_count_medium: int = Field(default=20, ge=1)
    rank_compound_count_high: int = Field(default=100, ge=1)
    rank_recency_max_age_years: int = Field(default=25, ge=1)
    rank_blend_composite_2way: float = Field(default=0.6, ge=0.0, le=1.0)
    rank_blend_bm25_2way: float = Field(default=0.4, ge=0.0, le=1.0)
    rank_blend_composite_3way: float = Field(default=0.4, ge=0.0, le=1.0)
    rank_blend_bm25_3way: float = Field(default=0.3, ge=0.0, le=1.0)
    rank_blend_embedding_3way: float = Field(default=0.3, ge=0.0, le=1.0)
    cost_per_million_input_haiku: float = Field(default=1.0, ge=0.0)
    cost_per_million_output_haiku: float = Field(default=5.0, ge=0.0)
    cost_per_million_input_sonnet: float = Field(default=3.0, ge=0.0)
    cost_per_million_output_sonnet: float = Field(default=15.0, ge=0.0)
    cost_per_million_input_opus: float = Field(default=5.0, ge=0.0)
    cost_per_million_output_opus: float = Field(default=25.0, ge=0.0)
    confidence_1_source: float = Field(default=0.30, ge=0.0, le=1.0)
    confidence_2_sources: float = Field(default=0.60, ge=0.0, le=1.0)
    confidence_3_sources: float = Field(default=0.85, ge=0.0, le=1.0)
    confidence_4_sources: float = Field(default=0.95, ge=0.0, le=1.0)
    doe_fwr_scale: float = Field(default=0.8, ge=0.0, le=1.0)
    doe_fwr_boost: float = Field(default=0.1, ge=0.0, le=0.5)
    doe_fwr_fallback: float = Field(default=0.3, ge=0.0, le=1.0)
    doe_fwr_cap: float = Field(default=0.8, ge=0.0, le=1.0)
    doe_confidence_high: float = Field(default=0.65, ge=0.0, le=1.0)
    doe_confidence_moderate: float = Field(default=0.40, ge=0.0, le=1.0)
    invalidity_weight_prosecution: float = Field(default=0.35, ge=0.0, le=1.0)
    invalidity_weight_prior_art_exists: float = Field(default=0.15, ge=0.0, le=1.0)
    invalidity_weight_ref_bonus_each: float = Field(default=0.03, ge=0.0, le=0.1)
    invalidity_weight_ref_bonus_cap: float = Field(default=0.15, ge=0.0, le=1.0)
    invalidity_weight_ex_bonus_each: float = Field(default=0.03, ge=0.0, le=0.1)
    invalidity_weight_ex_bonus_cap: float = Field(default=0.15, ge=0.0, le=1.0)
    invalidity_weight_ptab_challenged: float = Field(default=0.15, ge=0.0, le=1.0)
    invalidity_weight_ptab_success: float = Field(default=0.10, ge=0.0, le=1.0)
    invalidity_weight_narrow_claims: float = Field(default=0.05, ge=0.0, le=0.5)
    invalidity_weight_continuation: float = Field(default=0.05, ge=0.0, le=0.5)
    invalidity_confidence_cap: float = Field(default=0.95, ge=0.0, le=1.0)
    invalidity_confidence_high: float = Field(default=0.70, ge=0.0, le=1.0)
    invalidity_confidence_moderate: float = Field(default=0.45, ge=0.0, le=1.0)
    invalidity_prior_art_moderate_threshold: int = Field(default=5, ge=1)

    # Validation and display limits
    summary_word_count_min: int = Field(default=100, ge=10)
    summary_word_count_max: int = Field(default=1500, ge=100)
    patent_expiry_year_min: int = Field(default=1990, ge=1900)
    patent_expiry_year_max: int = Field(default=2050, ge=2000)
    scholarly_primary_max_results: int = Field(default=20, ge=1)
    scholarly_secondary_max_results: int = Field(default=10, ge=1)
    log_truncation_max_chars: int = Field(default=1000, ge=100)
    tool_abstract_truncation: int = Field(default=2000, ge=500)
    tool_claims_truncation: int = Field(default=3000, ge=500)
    render_title_max_chars: int = Field(default=200, ge=50)
    render_summary_max_chars: int = Field(default=500, ge=100)
    render_graham_max_chars: int = Field(default=200, ge=50)
    pdf_typst_timeout: int = Field(
        default=60,
        ge=10,
        description="Typst compiler timeout in seconds",
    )
    chart_dpi: int = Field(
        default=300,
        ge=72,
        le=600,
        description="DPI for chart images in reports",
    )
    structure_dpi: int = Field(
        default=300,
        ge=72,
        le=600,
        description="DPI for chemical structure images",
    )
    invalidity_max_tokens: int = Field(default=16384, ge=1000)
    invalidity_authors_max: int = Field(default=5, ge=1)
    invalidity_prior_art_context_max: int = Field(default=20, ge=1)
    invalidity_examiner_refs_display: int = Field(default=25, ge=1)
    invalidity_applicant_refs_display: int = Field(default=15, ge=1)
    analysis_element_reasoning_max_chars: int = Field(default=500, ge=50)
    analysis_context_max_synonyms: int = Field(default=15, ge=1)
    analysis_title_log_max_chars: int = Field(default=100, ge=20)
    analysis_error_msg_max_chars: int = Field(default=500, ge=50)
    narrative_concurrency: int = Field(default=2, ge=1)
    narrative_max_retries: int = Field(default=3, ge=1)
    narrative_retry_max_wait: int = Field(default=10, ge=1)
    invalidity_display_top_n: int = Field(default=10, ge=1)
    verification_max_items_detail: int = Field(default=10, ge=1)
    verification_max_orphaned_display: int = Field(default=5, ge=1)
    verification_max_ob_products: int = Field(default=3, ge=1)
    verification_max_ob_findings: int = Field(default=5, ge=1)
    log_level: str = "INFO"
