"""Deterministic finalization helpers for unified report pipeline."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.audit import PipelineAuditTrail, StepTokenUsage
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.pipeline.report.evidence_index import build_matter_evidence_index
from praviar_pipeline.pipeline.report.narratives import _build_patent_details
from praviar_pipeline.pipeline.report.prosecution_dossier import build_prosecution_dossiers
from praviar_pipeline.pipeline.report_bibliography import BibliographyBuilder, assemble_report

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import (
        ActionItem,
        AnalysisFailure,
        DataLimitation,
        SourceHealth,
    )
    from praviar_pipeline.models.report_sections import ReportSection, VerificationReport
    from praviar_pipeline.models.verification import VerificationResult
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore


def _build_drawing_outputs(
    drawing_evidence: DrawingEvidenceStore | None,
) -> tuple[list, dict]:
    drawing_analyses_list = []
    drawing_summary_dict: dict = {}
    if drawing_evidence:
        for patent_id in drawing_evidence.patent_ids:
            patent_analysis = drawing_evidence.get(patent_id)
            if patent_analysis is not None:
                drawing_analyses_list.append(patent_analysis)
        patents_with_structures = sum(
            1
            for patent_id in drawing_evidence.patent_ids
            if drawing_evidence.has_structures(patent_id)
        )
        structures = [
            structure
            for patent_id in drawing_evidence.patent_ids
            for patent_analysis in [drawing_evidence.get(patent_id)]
            if patent_analysis is not None
            for structure in patent_analysis.structures
        ]
        confidence_bands: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        per_tool_counts: dict[str, int] = {}
        stereo_flag_counts: dict[str, int] = {}
        for structure in structures:
            band = _confidence_band(structure.confidence)
            confidence_bands[band] = confidence_bands.get(band, 0) + 1
            tool = structure.extraction_tool or "unknown"
            per_tool_counts[tool] = per_tool_counts.get(tool, 0) + 1
            stereo_flag = getattr(structure, "stereo_flag", "")
            if stereo_flag:
                stereo_flag_counts[stereo_flag] = stereo_flag_counts.get(stereo_flag, 0) + 1

        drawing_summary_dict = {
            "patents_analyzed": len(drawing_evidence),
            "patents_with_structures": patents_with_structures,
            "total_structures": sum(
                (patent_analysis.structures_found or 0)
                for patent_id in drawing_evidence.patent_ids
                for patent_analysis in [drawing_evidence.get(patent_id)]
                if patent_analysis is not None
            ),
            "confidence_bands": confidence_bands,
            "per_tool_extraction_counts": per_tool_counts,
            "stereo_flag_counts": stereo_flag_counts,
            "text_validated_count": sum(1 for structure in structures if structure.pubchem_match),
            "high_risk_structures": sum(
                1
                for structure in structures
                if getattr(structure.drawing_risk_signal, "value", structure.drawing_risk_signal)
                == "high"
            ),
        }

    return drawing_analyses_list, drawing_summary_dict


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.9:
        return "HIGH"
    if confidence >= 0.7:
        return "MEDIUM"
    return "LOW"


def _build_step_token_usage(
    prior_step_tokens: list[StepTokenUsage] | None,
    analyses: list[PatentAnalysis],
    sections: list[ReportSection],
    verify_in: int,
    verify_out: int,
) -> list[StepTokenUsage]:
    step_token_usage = list(prior_step_tokens or [])
    analysis_in = sum(analysis.input_tokens for analysis in analyses)
    analysis_out = sum(analysis.output_tokens for analysis in analyses)
    if analysis_in or analysis_out:
        step_token_usage.append(
            StepTokenUsage(
                step_name="step4_analyze",
                model_role="deep",
                input_tokens=analysis_in,
                output_tokens=analysis_out,
            )
        )

    report_in = sum(section.input_tokens for section in sections) + verify_in
    report_out = sum(section.output_tokens for section in sections) + verify_out
    if report_in or report_out:
        step_token_usage.append(
            StepTokenUsage(
                step_name="step8_unified_report",
                model_role="analysis",
                input_tokens=report_in,
                output_tokens=report_out,
            )
        )

    return step_token_usage


_RISK_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2, RiskLevel.CLEAR: 3}


def _build_key_risks(analyses: list) -> list[str]:
    sorted_analyses = sorted(analyses, key=lambda a: _RISK_ORDER.get(a.risk_level, 9))
    key_risks = []
    for analysis in sorted_analyses:
        if analysis.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
            key_risks.append(
                f"{analysis.patent_id} ({analysis.assignee}): "
                f"{analysis.risk_level.value} risk — {analysis.risk_summary}"
            )
    return key_risks


def _finalize_unified_report(
    *,
    compound: ResolvedCompound,
    analyses: list,
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
    verification: VerificationResult,
    total_patents_found: int,
    search_sources: list[str] | None,
    source_health: SourceHealth,
    audit_trail: PipelineAuditTrail | None,
    prior_step_tokens: list[StepTokenUsage] | None,
    analysis_failures: list[AnalysisFailure] | None,
    prosecution_cache: dict[str, dict[str, object]] | None,
    regulatory_exclusivity,
    patent_hits: list | None,
    drawing_evidence: DrawingEvidenceStore | None,
    critic_report: CriticReport | None,
    execution_profile: Literal["world_class_adaptive"],
    overall_risk: RiskLevel,
    blocking: int,
    sections: list[ReportSection],
    data_store: ReportDataStore,
    verification_report: VerificationReport,
    validation_issues: list[str],
    llm_models_used: dict[str, str],
    action_items: list[ActionItem],
    total_input: int,
    total_output: int,
    verify_in: int,
    verify_out: int,
    bibliography_enabled: bool,
    invalidity_display_top_n: int,
    build_data_limitations_fn: Callable[
        [
            SourceHealth | None,
            list[InvalidityAssessment],
            list[PatentAnalysis],
        ],
        list[DataLimitation],
    ],
    compute_cost_fn: Callable[[list[StepTokenUsage]], float],
    extract_patent_narratives_fn: Callable[[str], dict[str, str]],
) -> FTOReport:
    bibliography_builder = BibliographyBuilder(data_store)
    bibliography_text, bibliography_entries = bibliography_builder.build(sections)

    assembled_text = assemble_report(
        sections=sections,
        bibliography_text=bibliography_text if bibliography_enabled else "",
        compound_name=compound.name,
        verification_score=verification_report.factual_accuracy_rate,
    )

    key_patents_section = next(
        (section for section in sections if section.section_id == "key_patents"),
        None,
    )
    patent_narratives = {}
    if key_patents_section:
        patent_narratives = extract_patent_narratives_fn(key_patents_section.content)

    data_limitations = build_data_limitations_fn(source_health, invalidity_assessments, analyses)
    drawing_analyses, drawing_summary = _build_drawing_outputs(drawing_evidence)
    step_token_usage = _build_step_token_usage(
        prior_step_tokens,
        analyses,
        sections,
        verify_in,
        verify_out,
    )
    estimated_cost = compute_cost_fn(step_token_usage)
    key_risks = _build_key_risks(analyses)
    patent_details = _build_patent_details(analyses, patent_hits)
    prosecution_dossiers = build_prosecution_dossiers(
        analyses=analyses,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache,
    )
    matter_evidence_index = build_matter_evidence_index(
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        patent_hits=patent_hits,
        prosecution_dossiers=prosecution_dossiers,
        critic_report=critic_report,
        source_health=source_health,
    )
    scholarly_count = sum(len(assessment.prior_art) for assessment in invalidity_assessments)

    risk_summary = RiskSummary(
        overall_risk=overall_risk,
        blocking_patents_count=blocking,
        total_patents_analyzed=len(analyses),
        key_risks=key_risks[:invalidity_display_top_n],
        executive_summary=assembled_text,
        summary_validation_issues=validation_issues,
    )

    return FTOReport(
        report_id=str(uuid.uuid4()),
        compound=compound,
        risk_summary=risk_summary,
        patent_analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        verification=verification,
        total_patents_found=total_patents_found,
        patents_after_triage=len(analyses) + len(analysis_failures or []),
        search_sources_used=search_sources or [],
        source_health=source_health,
        audit_trail=audit_trail or PipelineAuditTrail(),
        patent_narratives=patent_narratives,
        llm_models_used=llm_models_used,
        scholarly_prior_art_count=scholarly_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        estimated_cost_usd=estimated_cost,
        step_token_usage=step_token_usage,
        analysis_failures=analysis_failures or [],
        data_limitations=data_limitations,
        action_items=action_items,
        patent_details=patent_details,
        prosecution_dossiers=prosecution_dossiers,
        regulatory_exclusivity=regulatory_exclusivity,
        matter_evidence_index=matter_evidence_index,
        drawing_analyses=drawing_analyses,
        drawing_summary=drawing_summary,
        critic_report=critic_report,
        execution_profile=execution_profile,
        report_pipeline=execution_profile,
        bibliography=[entry.model_dump() for entry in bibliography_entries],
        verification_summary=verification_report.model_dump(),
        factual_accuracy_rate=verification_report.factual_accuracy_rate,
    )
