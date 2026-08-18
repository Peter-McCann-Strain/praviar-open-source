"""Tests for Markdown section facade exports."""

from __future__ import annotations

from datetime import UTC, datetime

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.rendering.markdown_sections import render_executive_summary, render_header


def _report() -> FTOReport:
    now = datetime.now(UTC)
    return FTOReport(
        report_id="section-test",
        generated_at=now,
        compound=ResolvedCompound(
            name="demo",
            canonical_smiles="C",
            inchi="InChI=1S/C",
            inchi_key="KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            pubchem_cid=1,
            molecular_formula="C",
            molecular_weight=12.0,
            original_input="demo",
            input_type="name",
        ),
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.LOW,
            blocking_patents_count=0,
            total_patents_analyzed=0,
            key_risks=[],
            executive_summary="OK",
        ),
        patent_analyses=[
            PatentAnalysis(
                patent_id="US1",
                title="Demo",
                assignee="Acme",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="demo element",
                                status=ElementStatus.MET,
                                reasoning="demo",
                                confidence=1.0,
                            )
                        ],
                        overall_status=ElementStatus.MET,
                        overall_confidence=1.0,
                    )
                ],
                risk_level=RiskLevel.LOW,
                risk_summary="low",
            )
        ],
    )


def test_facade_exports_render_header() -> None:
    lines: list[str] = []
    render_header(lines, _report())
    assert lines[0] == "# Freedom-to-Operate Analysis Report"
    assert "section-test" in "\n".join(lines)


def test_facade_exports_render_executive_summary() -> None:
    lines: list[str] = []
    render_executive_summary(lines, _report())
    output = "\n".join(lines)
    assert "## Executive Summary" in output
    assert "## Compound Profile" in output
