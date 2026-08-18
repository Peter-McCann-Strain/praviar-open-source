"""Step 8 unified: Multi-stage agentic report generation pipeline.

5 stages: DATA INDEX → SECTION GENERATION → DETERMINISTIC VERIFY → LLM VERIFY → ASSEMBLE

Each section is generated with tool access to query pipeline data on demand.
Verification ensures every factual claim is backed by source data.
Bibliography auto-generated with Google Patents / DOI / PTAB links.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.models.report import (
    SourceHealth,
)
from praviar_pipeline.pipeline.report import (
    _bootstrap_unified_report,
    _build_data_limitations,
    _build_retry_context,
    _collect_validation_issue_descriptions,
    _compute_cost,
    _determine_overall_risk,
    _extract_action_items,
    _extract_per_patent_narratives,
    _finalize_unified_report,
    _generate_section_unified,
    _generate_sections_unified,
    _group_validation_issues_by_section,
    _run_report_session_flow,
    _run_report_verification_flow,
    _run_validation_retry_flow,
    _sections_needing_retry,
    _validate_data_sufficiency,
)
from praviar_pipeline.pipeline.report_validators import (
    apply_corrections,
    run_deterministic_validators,
)

if TYPE_CHECKING:
    from praviar_pipeline.agents.tools.report_data_tools import ReportDataToolkit
    from praviar_pipeline.models.audit import PipelineAuditTrail, StepTokenUsage
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import AnalysisFailure, FTOReport
    from praviar_pipeline.models.report_sections import ReportSection
    from praviar_pipeline.models.verification import VerificationResult

logger = structlog.get_logger()

# Section definitions: (section_id, section_title, prompt_file, config_key)
_SECTIONS = [
    (
        "executive_summary",
        "1. EXECUTIVE SUMMARY",
        "report_s1_executive.txt",
        "report_s1_max_tokens",
    ),
    ("key_patents", "2. KEY PATENT ANALYSIS", "report_s2_key_patents.txt", "report_s2_max_tokens"),
    (
        "damages_injunction",
        "3. DAMAGES AND INJUNCTION RISK",
        "report_s3_damages_injunction.txt",
        "report_s3_max_tokens",
    ),
    (
        "invalidity",
        "4. INVALIDITY, DOE, AND PTAB",
        "report_s4_invalidity.txt",
        "report_s4_max_tokens",
    ),
    (
        "recommendations",
        "5. RECOMMENDATIONS AND MONITORING",
        "report_s5_recommendations.txt",
        "report_s5_max_tokens",
    ),
    (
        "data_quality",
        "6. DATA QUALITY AND LIMITATIONS",
        "report_s6_data_quality.txt",
        "report_s6_max_tokens",
    ),
]


async def _generate_section(
    claude: ClaudeClient,
    section_id: str,
    section_title: str,
    prompt_file: str,
    max_tokens: int,
    toolkit: ReportDataToolkit,
    context: str,
) -> ReportSection:
    """Stable wrapper for single-section generation."""
    return await _generate_section_unified(
        claude,
        section_id,
        section_title,
        prompt_file,
        max_tokens,
        toolkit,
        context,
    )


async def generate_unified_report(
    compound: ResolvedCompound,
    analyses: list,
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
    verification: VerificationResult,
    execution_profile: Literal["world_class_adaptive"] = "world_class_adaptive",
    total_patents_found: int = 0,
    search_sources: list[str] | None = None,
    source_health: SourceHealth | None = None,
    prior_llm_tokens: tuple[int, int] = (0, 0),
    audit_trail: PipelineAuditTrail | None = None,
    prior_step_tokens: list[StepTokenUsage] | None = None,
    analysis_failures: list[AnalysisFailure] | None = None,
    prosecution_cache: dict[str, dict[str, object]] | None = None,
    regulatory_exclusivity=None,
    patent_hits: list | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    critic_report: CriticReport | None = None,
) -> FTOReport:
    """Multi-stage agentic report generation pipeline.

    Stage 0: Build data index + toolkit
    Stage 1: Generate 6 sections in parallel with tool access
    Stage 2: Deterministic verification (patent IDs, risk levels, completeness)
    Stage 3: LLM verification (atomic claim fact-checking)
    Stage 4: Bibliography + assembly
    """
    settings = get_settings()
    logger.info("unified_report_start")

    if source_health is None:
        source_health = SourceHealth()

    _validate_data_sufficiency(source_health)

    # ── Stage 0: Data Index ─────────────────────────────────────────────

    bootstrap = _bootstrap_unified_report(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        verification=verification,
        patent_hits=patent_hits,
        drawing_evidence=drawing_evidence,
        source_health=source_health,
        analysis_failures=analysis_failures,
        critic_report=critic_report,
        determine_overall_risk_fn=_determine_overall_risk,
        extract_action_items_fn=_extract_action_items,
        intended_actions=list(settings.intended_actions),
        product_context=settings.product_context,
    )
    overall_risk = bootstrap.overall_risk
    action_items = bootstrap.action_items
    data_store = bootstrap.data_store
    toolkit = bootstrap.toolkit
    blocking = bootstrap.blocking
    context = bootstrap.context

    logger.info(
        "unified_report_stage0_complete",
        overall_risk=overall_risk.value,
        analyses=len(analyses),
        blocking=blocking,
    )

    total_input = prior_llm_tokens[0]
    total_output = prior_llm_tokens[1]
    session_flow = await _run_report_session_flow(
        claude_factory=ClaudeClient,
        settings=settings,
        toolkit=toolkit,
        context=context,
        data_store=data_store,
        section_defs=_SECTIONS,
        generate_section_fn=_generate_section,
        validation_fn=run_deterministic_validators,
        collect_validation_issue_descriptions_fn=_collect_validation_issue_descriptions,
        group_validation_issues_by_section_fn=_group_validation_issues_by_section,
        sections_needing_retry_fn=_sections_needing_retry,
        build_retry_context_fn=_build_retry_context,
        apply_corrections_fn=lambda s, v: apply_corrections(s, v, data_store),
        generate_sections_fn=_generate_sections_unified,
        validation_retry_fn=_run_validation_retry_flow,
        verification_flow_fn=_run_report_verification_flow,
        total_input=total_input,
        total_output=total_output,
    )
    sections = session_flow.sections
    validation_issues = session_flow.validation_issues
    verification_report = session_flow.verification_report
    verify_in = session_flow.verify_input
    verify_out = session_flow.verify_output
    total_input = session_flow.total_input
    total_output = session_flow.total_output
    llm_models_used = session_flow.llm_models_used

    # ── Stage 4: Bibliography + Assembly ─────────────────────────────────

    report = _finalize_unified_report(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        verification=verification,
        total_patents_found=total_patents_found,
        search_sources=search_sources,
        source_health=source_health,
        audit_trail=audit_trail,
        prior_step_tokens=prior_step_tokens,
        analysis_failures=analysis_failures,
        prosecution_cache=prosecution_cache,
        regulatory_exclusivity=regulatory_exclusivity,
        patent_hits=patent_hits,
        drawing_evidence=drawing_evidence,
        critic_report=critic_report,
        execution_profile=execution_profile,
        overall_risk=overall_risk,
        blocking=blocking,
        sections=sections,
        data_store=data_store,
        verification_report=verification_report,
        validation_issues=validation_issues,
        llm_models_used=llm_models_used,
        action_items=action_items,
        total_input=total_input,
        total_output=total_output,
        verify_in=verify_in,
        verify_out=verify_out,
        bibliography_enabled=settings.report_bibliography_enabled,
        invalidity_display_top_n=settings.invalidity_display_top_n,
        build_data_limitations_fn=_build_data_limitations,
        compute_cost_fn=_compute_cost,
        extract_patent_narratives_fn=_extract_per_patent_narratives,
    )

    logger.info(
        "unified_report_complete",
        overall_risk=overall_risk.value,
        sections=len(sections),
        bibliography_entries=len(report.bibliography),
        factual_accuracy=report.factual_accuracy_rate,
        total_tokens=report.total_input_tokens + report.total_output_tokens,
        estimated_cost=report.estimated_cost_usd,
    )

    return report
