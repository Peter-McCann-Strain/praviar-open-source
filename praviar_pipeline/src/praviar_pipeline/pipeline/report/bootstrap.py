"""Bootstrap helpers for unified report pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from praviar_pipeline.agents.tools.report_data_tools import ReportDataToolkit
from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.pipeline.report_data_store import ReportDataStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import ActionItem, AnalysisFailure, SourceHealth
    from praviar_pipeline.models.verification import VerificationResult


@dataclass(slots=True)
class ReportBootstrapContext:
    overall_risk: RiskLevel
    action_items: list[ActionItem]
    data_store: ReportDataStore
    toolkit: ReportDataToolkit
    blocking: int
    context: str


def _bootstrap_unified_report(
    *,
    compound: ResolvedCompound,
    analyses: list,
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
    verification: VerificationResult,
    patent_hits: list | None,
    drawing_evidence: DrawingEvidenceStore | None,
    source_health: SourceHealth,
    analysis_failures: list[AnalysisFailure] | None,
    critic_report: CriticReport | None,
    determine_overall_risk_fn: Callable,
    extract_action_items_fn: Callable,
    intended_actions: list[str] | None,
    product_context: object,
) -> ReportBootstrapContext:
    overall_risk = determine_overall_risk_fn(analyses, doe_assessments, source_health)
    action_items = extract_action_items_fn(
        analyses,
        invalidity_assessments,
        patent_hits=patent_hits,
        intended_actions=intended_actions,
        product_context=product_context,
    )
    high_risk_ids = {
        analysis.patent_id for analysis in analyses if analysis.risk_level == RiskLevel.HIGH
    }
    prospective_blocking_patent_ids = {
        patent_id
        for action in action_items
        if action.action_type.value != "monitor"
        for patent_id in action.patent_ids
        if patent_id in high_risk_ids
    }

    data_store = ReportDataStore(
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
        action_items=action_items,
        overall_risk=overall_risk,
        prospective_blocking_patent_ids=prospective_blocking_patent_ids,
    )
    toolkit = ReportDataToolkit(data_store)
    blocking = data_store.blocking_count()

    # Preserve upstream coverage screens without presenting them as final
    # enforceability or commercial-exposure decisions.
    risk_lines: list[str] = []
    for pid in sorted(data_store.all_patent_ids()):
        analysis = data_store.get_analysis(pid)
        if analysis:
            risk_lines.append(f"  {analysis.patent_id}: {analysis.risk_level.value.upper()}")
    canonical_risk_table = (
        (
            "\n\nUPSTREAM CLAIM-COVERAGE SCREENS (not final enforceability decisions — "
            "retain these labels but apply status, act, temporal, and evidence gates):\n"
            + "\n".join(risk_lines)
        )
        if risk_lines
        else ""
    )

    context = (
        f"Compound: {compound.name}\n"
        f"Upstream Claim-Coverage Screen: {overall_risk.value.upper()}\n"
        f"Patents Analyzed: {len(analyses)}\n"
        f"Verified Prospective Blockers: {blocking}\n"
        f"Analysis Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"{canonical_risk_table}\n"
        f"\nGenerate this section of the FTO report. "
        f"Use your tools to query the pipeline data for specifics."
    )

    return ReportBootstrapContext(
        overall_risk=overall_risk,
        action_items=action_items,
        data_store=data_store,
        toolkit=toolkit,
        blocking=blocking,
        context=context,
    )
