from __future__ import annotations

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    PatentDrawingAnalysis,
)
from praviar_pipeline.pipeline.report.assembly_helpers import (
    build_drawing_report_data,
    build_report_toolkit,
)


def test_build_report_toolkit_respects_tools_enabled() -> None:
    analyses = [
        PatentAnalysis(
            patent_id="US123",
            title="Patent",
            assignee="Acme",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking",
        )
    ]

    toolkit = build_report_toolkit(analyses=analyses, tools_enabled=True)

    assert toolkit is not None
    assert toolkit._cache["US123"]["title"] == "Patent"
    assert toolkit._cache["US123"]["risk_level"] == "high"
    assert build_report_toolkit(analyses=analyses, tools_enabled=False) is None


def test_build_drawing_report_data_adds_coverage_limitation_when_most_have_no_structures() -> None:
    evidence = DrawingEvidenceStore(
        DrawingAnalysisResults(
            patent_analyses=[
                PatentDrawingAnalysis(
                    patent_id="US1",
                    structures_found=1,
                    highest_tanimoto=0.8,
                    highest_risk_signal=DrawingRiskLevel.HIGH,
                ),
                PatentDrawingAnalysis(
                    patent_id="US2",
                    structures_found=0,
                    highest_tanimoto=0.0,
                    highest_risk_signal=DrawingRiskLevel.NONE,
                ),
                PatentDrawingAnalysis(
                    patent_id="US3",
                    structures_found=0,
                    highest_tanimoto=0.0,
                    highest_risk_signal=DrawingRiskLevel.NONE,
                ),
            ]
        )
    )

    report_data = build_drawing_report_data(evidence)

    assert report_data.summary["patents_analyzed"] == 3
    assert report_data.summary["patents_with_structures"] == 1
    assert report_data.summary["patents_with_high_risk"] == 1
    assert len(report_data.limitations) == 1
    assert report_data.limitations[0].category == "drawing_coverage"
