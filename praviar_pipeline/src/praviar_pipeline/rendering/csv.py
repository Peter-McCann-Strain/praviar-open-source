"""CSV export — flat claim chart and risk matrix for maximum interoperability.

Produces two CSV files returned as a dict of {filename: csv_string}.
Any tool (Excel, Google Sheets, Patlytics, ClaimMaster) can import these.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from praviar_pipeline.models.report_common import REPORT_DISCLAIMER
from praviar_pipeline.rendering.audience_projection import (
    AUDIENCE_PROJECTION_SCHEMA_VERSION,
    AudienceField,
)
from praviar_pipeline.rendering.evidence_scope import (
    source_status_detail,
    source_status_label,
    summarize_evidence_scope,
)
from praviar_pipeline.rendering.governed_decision import (
    governed_decision_label,
    governed_patent_basis,
    governed_patent_posture,
)
from praviar_pipeline.rendering.spreadsheet_safety import neutralize_spreadsheet_row

if TYPE_CHECKING:
    from collections.abc import Sequence

    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.export_options import ExportRenderOptions


def _write_row(writer: object, values: Sequence[object]) -> None:
    """Write one row after neutralizing every string cell."""
    writer.writerow(neutralize_spreadsheet_row(list(values)))  # type: ignore[attr-defined]


def _render_risk_matrix_csv(report: FTOReport, options: ExportRenderOptions) -> str:
    """Render the risk matrix as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    scientist_projection = options.audience == "scientist"
    headers = [
        "Patent ID",
        "Title",
        "Assignee",
        "Matter Clearance Decision",
        "Governed Patent Posture",
        "Claim-Coverage Screen",
        "Expiry Date",
    ]
    if not scientist_projection:
        headers.extend(
            [
                "Claims Analyzed",
                "Governed Basis",
                "Upstream Screen Summary",
            ]
        )
    _write_row(writer, headers)

    sorted_analyses = sorted(
        report.patent_analyses,
        key=lambda analysis: (
            {
                "BLOCKING": 0,
                "UNRESOLVED": 1,
                "NON-BLOCKING": 2,
                "SUPPORTING ONLY": 3,
            }.get(governed_patent_posture(report, analysis.patent_id), 4),
            {"high": 0, "medium": 1, "low": 2, "clear": 3}.get(
                analysis.risk_level.value,
                4,
            ),
            analysis.patent_id,
        ),
    )

    for a in sorted_analyses:
        claims = ", ".join(str(c.claim_number) for c in a.claims_analyzed)
        row = [
            a.patent_id,
            a.title,
            a.assignee,
            governed_decision_label(report),
            governed_patent_posture(report, a.patent_id),
            a.risk_level.value.upper(),
            a.expiry_date.isoformat() if a.expiry_date else "",
        ]
        if not scientist_projection:
            row.extend(
                [
                    claims,
                    governed_patent_basis(report, a.patent_id),
                    a.risk_summary,
                ]
            )
        _write_row(writer, row)

    return buf.getvalue()


def _render_claim_charts_csv(report: FTOReport) -> str:
    """Render all claim charts as a flat CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    _write_row(
        writer,
        [
            "Patent ID",
            "Claim Number",
            "Prior Art Reference",
            "Element Number",
            "Element Text",
            "Prior Art Disclosure",
            "Citation Location",
            "Disclosed",
            "Notes",
            "All Elements Disclosed",
            "Chart Summary",
        ],
    )

    for ia in report.invalidity_assessments:
        for chart in ia.claim_charts:
            for entry in chart.entries:
                _write_row(
                    writer,
                    [
                        chart.patent_id,
                        chart.claim_number,
                        chart.prior_art_reference_id,
                        entry.element_number,
                        entry.element_text,
                        entry.prior_art_disclosure,
                        entry.citation_location,
                        entry.disclosed,
                        entry.notes,
                        "Yes" if chart.all_elements_disclosed else "No",
                        chart.chart_summary,
                    ],
                )

    return buf.getvalue()


def _render_export_metadata_csv(
    report: FTOReport,
    options: ExportRenderOptions,
) -> str:
    """Render audience, scope, and legal context for governed CSV exports."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    _write_row(writer, ["Field", "Value"])
    _write_row(writer, ["Report ID", getattr(report, "report_id", "")])
    _write_row(writer, ["Compound", getattr(getattr(report, "compound", None), "name", "")])
    _write_row(writer, ["Audience", options.audience_label])
    _write_row(writer, ["Audience Schema Version", AUDIENCE_PROJECTION_SCHEMA_VERSION])
    _write_row(writer, ["Sections", "; ".join(options.section_labels)])
    _write_row(writer, ["Legal Marking", "CONFIDENTIAL DRAFT"])
    _write_row(writer, ["Caveat", "AI-assisted FTO screening; counsel review required"])
    _write_row(writer, ["Disclaimer", REPORT_DISCLAIMER])
    return buf.getvalue()


def _render_source_audit_csv(report: FTOReport) -> str:
    """Render source-health and evidence-scope caveats as CSV."""

    buf = io.StringIO()
    writer = csv.writer(buf)
    _write_row(writer, ["Record Type", "Source", "Status", "Patents Found", "Detail"])

    summary = summarize_evidence_scope(report)
    _write_row(writer, ["Summary", "Source status", "", "", summary.headline])
    _write_row(writer, ["Summary", "Confidence impact", "", "", summary.confidence_impact])
    _write_row(writer, ["Summary", "Counsel review note", "", "", summary.review_note])
    _write_row(
        writer,
        [
            "Summary",
            "Evidence caveat",
            "",
            "",
            (
                "Scope statements describe recorded source-health telemetry only; "
                "they do not certify exhaustive legal clearance."
            ),
        ],
    )

    entries = tuple(getattr(getattr(report, "source_health", None), "entries", ()) or ())
    if entries:
        for entry in entries:
            _write_row(
                writer,
                [
                    "Source",
                    getattr(entry, "source", ""),
                    source_status_label(entry),
                    getattr(entry, "patent_count", 0),
                    source_status_detail(entry),
                ],
            )
    else:
        sources = tuple(getattr(report, "search_sources_used", ()) or ())
        if sources:
            for source in sources:
                _write_row(
                    writer,
                    [
                        "Recorded source",
                        source,
                        "Telemetry not recorded",
                        "",
                        "No per-source completion status was recorded.",
                    ],
                )
        else:
            _write_row(
                writer,
                [
                    "Recorded source",
                    "",
                    "Telemetry not recorded",
                    "",
                    "No configured source telemetry was recorded.",
                ],
            )

    return buf.getvalue()


def render_csv(
    report: FTOReport,
    options: ExportRenderOptions | None = None,
) -> dict[str, str]:
    """Render FTO report as CSV files.

    Returns a dict of {filename: csv_content_string}.
    """
    from praviar_pipeline.rendering.export_options import default_export_options

    options = options or default_export_options()
    files = {
        "export_metadata.csv": _render_export_metadata_csv(report, options),
        "source_audit.csv": _render_source_audit_csv(report),
    }

    if options.allows(AudienceField.PATENT_LANDSCAPE) and options.includes("patent_analysis"):
        files["risk_matrix.csv"] = _render_risk_matrix_csv(report, options)
    if options.allows(AudienceField.CLAIM_CHARTS) and options.includes(
        "claim_charts", "invalidity_assessment"
    ):
        files["claim_charts.csv"] = _render_claim_charts_csv(report)

    return files
