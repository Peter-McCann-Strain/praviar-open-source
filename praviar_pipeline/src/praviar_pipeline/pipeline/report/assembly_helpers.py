"""Shared deterministic helpers for adaptive report assembly."""

from __future__ import annotations

from dataclasses import dataclass

from praviar_pipeline.models.report import DataLimitation
from praviar_pipeline.tools import FTOToolkit


def build_report_toolkit(*, analyses: list, tools_enabled: bool) -> FTOToolkit | None:
    """Create the report-generation toolkit when tool use is enabled."""
    if not tools_enabled:
        return None

    known_patents = {
        analysis.patent_id: {
            "title": analysis.title,
            "assignee": analysis.assignee,
            "risk_level": analysis.risk_level.value,
            "risk_summary": analysis.risk_summary,
        }
        for analysis in analyses
    }
    return FTOToolkit(
        known_patents=known_patents,
        enabled_tools=["get_current_date", "lookup_patent"],
    )


@dataclass(slots=True)
class DrawingReportData:
    analyses: list
    summary: dict
    limitations: list[DataLimitation]


def build_drawing_report_data(drawing_evidence) -> DrawingReportData:
    """Build drawing analyses, summary metrics, and any coverage limitation."""
    if not drawing_evidence:
        return DrawingReportData(analyses=[], summary={}, limitations=[])

    drawing_analyses = []
    for patent_id in drawing_evidence.patent_ids:
        patent_analysis = drawing_evidence.get(patent_id)
        if patent_analysis is not None:
            drawing_analyses.append(patent_analysis)

    patents_with_structures = sum(
        1 for patent_id in drawing_evidence.patent_ids if drawing_evidence.has_structures(patent_id)
    )
    summary = {
        "patents_analyzed": len(drawing_evidence),
        "patents_with_structures": patents_with_structures,
        "total_structures": sum(
            (drawing_evidence.get(patent_id).structures_found or 0)
            for patent_id in drawing_evidence.patent_ids
            if drawing_evidence.get(patent_id)
        ),
        "patents_with_high_risk": sum(
            1
            for patent_id in drawing_evidence.patent_ids
            if drawing_evidence.get_highest_tanimoto(patent_id) >= 0.7
        ),
    }

    limitations: list[DataLimitation] = []
    no_drawing_count = len(drawing_evidence) - patents_with_structures
    if no_drawing_count > len(drawing_evidence) * 0.5:
        limitations.append(
            DataLimitation(
                category="drawing_coverage",
                description=(
                    f"{no_drawing_count} of {len(drawing_evidence)} patents "
                    "had no extractable chemical structures in drawings"
                ),
                impact="Structural evidence may be incomplete for some patents",
            )
        )

    return DrawingReportData(
        analyses=drawing_analyses,
        summary=summary,
        limitations=limitations,
    )
