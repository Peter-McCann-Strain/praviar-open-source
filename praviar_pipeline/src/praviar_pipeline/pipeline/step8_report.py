"""Step 8: Report Generation -- assemble all outputs into FTOReport.

Report generation has one active engine: the governed adaptive report path.

This module re-exports the shared report helpers from
praviar_pipeline.pipeline.report so that step8_unified_report and existing tests
can continue to import them from a single stable location.

ClaudeClient and get_settings are re-exported here so that tests can patch
them at this namespace (``praviar_pipeline.pipeline.step8_report.ClaudeClient``
and ``praviar_pipeline.pipeline.step8_report.get_settings``) matching the
patch paths established before v1 was archived.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.report import (
    _aggregate_step_tokens,
    _build_data_limitations,
    _build_patent_details,
    _compute_cost,
    _determine_overall_risk,
    _extract_action_items,
    _generate_patent_narratives,
    _generate_validated_executive_summary,
    _identify_key_risks,
    _model_name_to_pricing_key,
    _validate_data_sufficiency,
    _validate_executive_summary,
    build_drawing_report_data,
    build_matter_evidence_index,
    build_prosecution_dossiers,
    build_report_toolkit,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.audit import PipelineAuditTrail, StepTokenUsage
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import AnalysisFailure, FTOReport, SourceHealth
    from praviar_pipeline.models.verification import VerificationResult

__all__ = [
    "ClaudeClient",
    "_aggregate_step_tokens",
    "_build_data_limitations",
    "_build_patent_details",
    "_compute_cost",
    "_determine_overall_risk",
    "_extract_action_items",
    "_generate_patent_narratives",
    "_generate_validated_executive_summary",
    "_identify_key_risks",
    "_model_name_to_pricing_key",
    "_validate_data_sufficiency",
    "_validate_executive_summary",
    "build_drawing_report_data",
    "build_matter_evidence_index",
    "build_prosecution_dossiers",
    "build_report_toolkit",
    "generate_report",
    "get_settings",
]


async def generate_report(
    compound: ResolvedCompound,
    analyses: list[PatentAnalysis],
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
    """Assemble all pipeline outputs into a complete FTO report."""
    from praviar_pipeline.pipeline.step8_unified_report import generate_unified_report

    return await generate_unified_report(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        verification=verification,
        execution_profile=execution_profile,
        total_patents_found=total_patents_found,
        search_sources=search_sources,
        source_health=source_health,
        prior_llm_tokens=prior_llm_tokens,
        audit_trail=audit_trail,
        prior_step_tokens=prior_step_tokens,
        analysis_failures=analysis_failures,
        prosecution_cache=prosecution_cache,
        regulatory_exclusivity=regulatory_exclusivity,
        patent_hits=patent_hits,
        drawing_evidence=drawing_evidence,
        critic_report=critic_report,
    )
