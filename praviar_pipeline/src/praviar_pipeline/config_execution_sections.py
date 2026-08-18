"""Execution and policy settings mixins for the Praviar Pipeline runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from praviar_pipeline.models.accused_acts import AccusedActRecord
from praviar_pipeline.models.markush_evidence import MarkushEvidenceReceipt  # noqa: TC001


class PipelineExecutionSettingsMixin:
    # Analysis and concurrency
    max_analysis_patents: int = Field(default=100, ge=1)
    spec_text_max_patents: int = Field(
        default=40,
        ge=1,
        description=(
            "Max patents for which specification text is fetched during Step 4 "
            "enrichment. Specification text is large; this caps BigQuery cost "
            "while covering well beyond the historical first-10 limit."
        ),
    )
    spec_text_max_chars: int = Field(
        default=240000,
        ge=10000,
        description=(
            "Per-patent specification budget. When a specification exceeds this, "
            "it is reduced by definition-aware chunking rather than blunt "
            "truncation so claim terms can still be construed against the "
            "relevant passages (Phillips v. AWH Corp.)."
        ),
    )
    max_doe_candidates: int = Field(default=15, ge=1)
    triage_concurrency: int = Field(default=3, ge=1)
    analysis_concurrency: int = Field(
        default=5,
        ge=1,
        description=(
            "Maximum concurrent Claude analysis calls in Step 4. The bounded "
            "default limits in-flight work; deployment-specific provider quotas "
            "and measured resource evidence must govern any change."
        ),
    )
    multi_perspective_enabled: bool = Field(
        default=False,
        description="Enable multi-perspective analysis (attorney, chemist, business analyst)",
    )
    perspective_concurrency: int = Field(
        default=3,
        ge=1,
        le=3,
        description="Max concurrent perspective agent calls during adaptive review",
    )
    perspective_max_tokens: int = Field(
        default=8192,
        description="Max output tokens per perspective analysis",
    )
    doe_concurrency: int = Field(default=2, ge=1)
    critic_enabled: bool = Field(
        default=True,
        description="Enable portfolio-level critic review after Step 4 analysis",
    )
    critic_max_tokens: int = Field(
        default=16384,
        description="Max output tokens for critic review",
    )
    critic_reanalysis_enabled: bool = Field(
        default=False,
        description="Allow critic to trigger re-analysis of flagged patents",
    )
    critic_reanalysis_max_patents: int = Field(
        default=3,
        ge=0,
        le=5,
        description="Max patents to re-analyze based on critic findings",
    )

    # LLM execution budgets
    pipeline_llm_hard_budget_usd: float = Field(
        default=50.0,
        gt=0.0,
        le=1000.0,
        description=(
            "Hard per-run ceiling for priced LLM calls. Live calls reserve their "
            "worst-case output cost before contacting the provider."
        ),
    )
    analysis_thinking_budget_tokens: int = Field(default=32000, ge=1000)
    analysis_max_tokens: int = Field(
        default=64000,
        description="Max output tokens for Step 4 adaptive claim analysis. Sonnet/Opus: 64K/128K.",
    )
    evaluator_max_tokens: int = Field(
        default=8192,
        description="Max output tokens for evaluator pass (Haiku). Typically <2K.",
    )
    doe_max_tokens: int = Field(
        default=8192,
        description="Max output tokens for DoE FWR assessment",
    )
    report_summary_max_tokens: int = Field(
        default=8192,
        description="Max output tokens for executive summary generation",
    )
    report_narrative_max_tokens: int = Field(
        default=4096,
        description="Max output tokens for per-patent narrative generation",
    )
    triage_max_tokens: int = Field(
        default=8192,
        description="Max output tokens for triage calls",
    )
    report_max_retries: int = Field(
        default=3,
        description="Max retries for report generation on validation failure",
    )
    report_section_concurrency: int = Field(
        default=6,
        ge=1,
        le=10,
        description="Max concurrent section generation calls",
    )
    report_verification_enabled: bool = Field(
        default=True,
        description="Enable LLM verification of report facts",
    )
    report_bibliography_enabled: bool = Field(
        default=True,
        description="Enable auto-generated reference appendix",
    )
    report_verification_thinking_budget: int = Field(
        default=32768,
        description="Extended thinking budget for verification agent",
    )
    report_max_section_retries: int = Field(
        default=2,
        ge=0,
        le=3,
        description="Max retries per section after validation failure in the unified pipeline",
    )
    report_s1_max_tokens: int = Field(default=16384, description="Executive Summary output budget")
    report_s2_max_tokens: int = Field(default=32768, description="Key Patents output budget")
    report_s3_max_tokens: int = Field(default=16384, description="Damages+Injunction output budget")
    report_s4_max_tokens: int = Field(default=32768, description="Invalidity output budget")
    report_s5_max_tokens: int = Field(default=16384, description="Recommendations output budget")
    report_s6_max_tokens: int = Field(default=8192, description="Data Quality output budget")

    # Policy and execution controls
    matter_type: str = Field(
        default="small_molecule",
        description="Matter class used to tune evidence sufficiency expectations",
    )
    trust_mode: str = Field(
        default="explorer",
        description="Product trust posture used for adaptive depth selection",
    )
    intended_actions: list[str] = Field(
        default_factory=list,
        description="Business actions that shape adaptive evidence requirements",
    )
    product_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Product, formulation, use, process, and known-art launch context",
    )

    @field_validator("product_context", mode="after")
    @classmethod
    def validate_structured_accused_acts(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate the nested governing act set at the runtime boundary."""
        raw_records = value.get("accused_acts")
        if raw_records is None:
            return value
        if not isinstance(raw_records, list):
            raise ValueError("product_context.accused_acts must be a list")
        normalized = dict(value)
        normalized["accused_acts"] = [
            AccusedActRecord.model_validate(record).model_dump(mode="json")
            for record in raw_records
        ]
        return normalized

    target_jurisdictions: list[str] = Field(
        default_factory=list,
        description="Customer-selected target jurisdictions for the matter",
    )
    jurisdiction_bundle: str = Field(
        default="us_ep",
        description="Customer-selected jurisdiction bundle retained for launch-context audit.",
    )
    development_stage: str = Field(
        default="discovery",
        description="Customer program stage used for regulatory-purpose and remedy gates.",
    )
    asset_type_hint: str = Field(
        default="unknown",
        description="Customer-provided asset type hint used for adaptive routing",
    )
    jurisdiction_policy: str = Field(
        default="us_ep_core",
        description="Jurisdiction policy controlling which records are clearance-critical",
    )
    clearance_threshold_profile: str = Field(
        default="world_class_us_ep",
        description="Evidence threshold profile for top-line clearance conclusions",
    )
    max_run_duration_hours: int = Field(
        default=24,
        ge=1,
        le=72,
        description="Maximum allowed run duration for long-running clearance jobs",
    )
    source_authority_policy: str = Field(
        default="official_plus_licensed",
        description=(
            "Authority policy for deciding which sources can support a positive "
            "clearance conclusion"
        ),
    )
    required_record_components: list[str] = Field(
        default_factory=list,
        description="Explicit record components required before a matter can be labeled clear",
    )
    require_verified_manual_markush: bool = Field(
        default=True,
        description=(
            "Require a fresh, independently reviewed PATENTSCOPE Markush receipt before "
            "a small-molecule matter may support a positive clearance conclusion."
        ),
    )
    markush_evidence_max_age_days: int = Field(
        default=35,
        ge=1,
        le=180,
        description="Maximum age of verified manual Markush evidence for clearance use.",
    )
    markush_evidence_receipt: MarkushEvidenceReceipt | None = Field(
        default=None,
        description=(
            "Per-matter, content-addressed receipt for a supervised PATENTSCOPE "
            "Markush search. This is evidence input, never a global fallback."
        ),
    )
    tools_enabled: bool = Field(
        default=True,
        description="Enable tool use for LLM agents (patent lookup, date, status)",
    )
    max_tool_rounds: int = Field(
        default=10,
        ge=1,
        le=10,
        description="Max tool use rounds per LLM call before forcing final output",
    )
    claim_pre_parsing_enabled: bool = Field(
        default=True,
        description="Deterministic claim pre-parsing before LLM analysis",
    )
    deterministic_risk_computation: bool = Field(
        default=True,
        description="Compute risk level from element statuses (override LLM risk)",
    )
    differential_verification_enabled: bool = Field(
        default=True,
        description="Run Haiku verification pass on borderline (MEDIUM+) patents",
    )
    verification_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Patents with avg confidence below this trigger verification",
    )
    agentic_max_agent_rounds: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max research rounds per agentic escalation",
    )
    agentic_observation_masking: bool = Field(
        default=True,
        description="Mask old tool outputs to stay within context budget",
    )
    agentic_scratchpad_enabled: bool = Field(
        default=True,
        description="Maintain structured scratchpad across agent rounds",
    )
    search_loop_enabled: bool = Field(
        default=False,
        description=(
            "Enable the iterative search loop. Adaptive runtime signals may "
            "also turn this on during run bootstrap."
        ),
    )
    # Enable hybrid retrieval only under an explicitly reviewed rollout policy
    # bound to an immutable evaluation receipt for the exact corpus and revision.
    # Requires the patents table to have an embedding ARRAY<FLOAT64> column populated
    # before activation. Keep it disabled unless that governed evidence is available.
    hybrid_retrieval_enabled: bool = Field(
        default=False,
        description=(
            "Enable hybrid indexed lexical+dense retrieval using BigQuery "
            "SEARCH and VECTOR_SEARCH. "
            "Requires the patents table to have an embedding ARRAY<FLOAT64> column. "
            "Only enable with a reviewed, immutable evaluation receipt."
        ),
    )
    search_loop_max_iterations: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max search loop iterations before stopping",
    )
    search_loop_coverage_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum coverage confidence to exit loop early",
    )
    hitl_enabled: bool = Field(
        default=False,
        description="Enable human-in-the-loop checkpoints",
    )
    identity_review_required: bool = Field(
        default=False,
        description=(
            "Require approval of the authoritative resolved identity before query "
            "expansion. API-launched analyses enable this fail-closed gate; direct "
            "library and CLI callers must opt in with a decision provider."
        ),
    )
    hitl_checkpoints: list[str] = Field(
        default_factory=list,
        description="Which checkpoints to activate (search_review, triage_review, etc.)",
    )
    hitl_auto_skip_minutes: int = Field(
        default=60,
        ge=1,
        description="Auto-proceed after this many minutes if no human response",
    )
    checkpoint_enabled: bool = Field(
        default=True,
        description="Save checkpoints after each pipeline step for resume-on-failure",
    )
    checkpoint_dir: str = Field(
        default="",
        description="Base directory for checkpoints. Defaults to <project>/checkpoints/",
    )
    response_cache_mode: Literal["record", "replay", "replay_then_record"] = Field(
        default="record",
        description="Internal exact-response capture/replay mode.",
    )
    response_cache_dir: str = Field(
        default="",
        description="Internal owner-only response-cache directory override.",
    )
    response_cache_expected_digest: str = Field(
        default="",
        pattern=r"^$|^[0-9a-f]{64}$",
        description="Expected complete response-cache digest during exact replay.",
    )
    response_cache_expected_hmac: str = Field(
        default="",
        pattern=r"^$|^[0-9a-f]{64}$",
        description="Expected authenticated response-cache digest during replay.",
    )
    response_cache_expected_key_id: str = Field(
        default="",
        description="Expected audit-key ID for exact response-cache replay.",
    )
    require_attorney_role_for_risk_ratings: bool = Field(
        default=True,
        description="Filter risk ratings from non-attorney API responses",
    )
    thinking_effort_analysis: str = Field(
        default="high",
        description="Thinking effort for adaptive claim analysis (high/medium/low)",
    )
    thinking_effort_triage: str = Field(
        default="medium",
        description="Thinking effort for triage (high/medium/low)",
    )
    thinking_effort_report: str = Field(
        default="high",
        description="Thinking effort for report generation (high/medium/low)",
    )
    collect_audit_trail: bool = Field(
        default=True,
        description="Collect detailed audit trail during pipeline execution",
    )
    deterministic_seed: int = Field(
        default=42,
        description=(
            "Seed used for all Python/NumPy RNG in the runtime pipeline for "
            "reproducibility. LLM sampling is pinned separately via "
            "``temperature=0`` on every analysis/verification call."
        ),
    )
    paragraph_iv_pdf_url: str = Field(
        default="",
        description=(
            "Direct URL to the current FDA Paragraph IV ANDA certifications PDF. "
            "The URL contains a media ID that changes with each FDA biweekly release; "
            "operators must keep this current. When empty, Paragraph IV enrichment is "
            "skipped and the source is not recorded as queried. "
            "Example: https://www.fda.gov/media/77509/download"
        ),
    )
