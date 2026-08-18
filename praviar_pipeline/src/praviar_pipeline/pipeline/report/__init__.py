"""Deterministic helpers for report generation."""

from praviar_pipeline.pipeline.report.assembly_helpers import (
    DrawingReportData,
    build_drawing_report_data,
    build_report_toolkit,
)
from praviar_pipeline.pipeline.report.bootstrap import _bootstrap_unified_report
from praviar_pipeline.pipeline.report.costing import (
    _aggregate_step_tokens,
    _compute_cost,
    _model_name_to_pricing_key,
)
from praviar_pipeline.pipeline.report.evidence_index import build_matter_evidence_index
from praviar_pipeline.pipeline.report.finalization import _finalize_unified_report
from praviar_pipeline.pipeline.report.narratives import (
    _build_patent_details,
    _extract_per_patent_narratives,
    _generate_patent_narratives,
)
from praviar_pipeline.pipeline.report.policy import (
    _build_data_limitations,
    _determine_overall_risk,
    _extract_action_items,
    _identify_key_risks,
    _validate_data_sufficiency,
)
from praviar_pipeline.pipeline.report.prosecution_dossier import (
    build_prosecution_dossiers,
)
from praviar_pipeline.pipeline.report.prosecution_helpers import (
    dossier_sections,
    dossier_source_name,
    has_file_wrapper_dossier,
)
from praviar_pipeline.pipeline.report.retry_flow import (
    ValidationRetryFlowResult,
    _run_validation_retry_flow,
)
from praviar_pipeline.pipeline.report.section_generation import (
    _generate_section_unified,
    _generate_sections_unified,
)
from praviar_pipeline.pipeline.report.session_flow import (
    ReportSessionFlowResult,
    _run_report_session_flow,
)
from praviar_pipeline.pipeline.report.summary import (
    _build_invalidity_summary_lines,
    _validate_executive_summary,
)
from praviar_pipeline.pipeline.report.summary_generation import (
    _generate_validated_executive_summary,
)
from praviar_pipeline.pipeline.report.validation_flow import (
    _build_retry_context,
    _collect_validation_issue_descriptions,
    _group_validation_issues_by_section,
    _sections_needing_retry,
)
from praviar_pipeline.pipeline.report.verification_flow import (
    VerificationFlowResult,
    _run_report_verification_flow,
)

__all__ = [
    "DrawingReportData",
    "ReportSessionFlowResult",
    "ValidationRetryFlowResult",
    "VerificationFlowResult",
    "_aggregate_step_tokens",
    "_bootstrap_unified_report",
    "_build_data_limitations",
    "_build_invalidity_summary_lines",
    "_build_patent_details",
    "_build_retry_context",
    "_collect_validation_issue_descriptions",
    "_compute_cost",
    "_determine_overall_risk",
    "_extract_action_items",
    "_extract_per_patent_narratives",
    "_finalize_unified_report",
    "_generate_patent_narratives",
    "_generate_section_unified",
    "_generate_sections_unified",
    "_generate_validated_executive_summary",
    "_group_validation_issues_by_section",
    "_identify_key_risks",
    "_model_name_to_pricing_key",
    "_run_report_session_flow",
    "_run_report_verification_flow",
    "_run_validation_retry_flow",
    "_sections_needing_retry",
    "_validate_data_sufficiency",
    "_validate_executive_summary",
    "build_drawing_report_data",
    "build_matter_evidence_index",
    "build_prosecution_dossiers",
    "build_report_toolkit",
    "dossier_sections",
    "dossier_source_name",
    "has_file_wrapper_dossier",
]
