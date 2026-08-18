from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report_decisioning import ClearanceDecision, ClearanceOutcome
from praviar_pipeline.rendering.governed_decision import (
    governed_decision_label,
    governed_risk_level,
)
from praviar_pipeline.rendering.markdown_sections_overview import render_executive_summary


def test_governed_display_ignores_drifting_risk_summary() -> None:
    report = SimpleNamespace(
        risk_summary=SimpleNamespace(overall_risk=RiskLevel.CLEAR),
        clearance_decision=ClearanceDecision(decision=ClearanceOutcome.BLOCKED),
    )

    assert governed_risk_level(report) == RiskLevel.HIGH
    assert governed_decision_label(report) == "BLOCKED"


def test_unclear_display_fails_safe_to_medium_risk() -> None:
    report = SimpleNamespace(
        risk_summary=SimpleNamespace(overall_risk=RiskLevel.CLEAR),
        clearance_decision=ClearanceDecision(decision=ClearanceOutcome.UNCLEAR),
    )

    assert governed_risk_level(report) == RiskLevel.MEDIUM


def test_markdown_uses_governed_verdict_not_legacy_clear_prose() -> None:
    report = SimpleNamespace(
        compound=SimpleNamespace(
            name="Example",
            canonical_smiles="CCO",
            inchi_key="KEY",
            molecular_formula="C2H6O",
            molecular_weight=46.07,
            cas_numbers=[],
            functional_groups=[],
        ),
        risk_summary=SimpleNamespace(
            overall_risk=RiskLevel.CLEAR,
            executive_summary="CLEAR: no material concerns.",
            total_patents_analyzed=1,
        ),
        clearance_decision=ClearanceDecision(decision=ClearanceOutcome.UNCLEAR),
        total_patents_found=1,
        patents_after_triage=1,
        patent_analyses=[],
        source_health=SimpleNamespace(entries=[]),
        search_sources_used=[],
    )
    lines: list[str] = []

    render_executive_summary(lines, report)
    markdown = "\n".join(lines)

    assert "Clearance Decision: UNCLEAR" in markdown
    assert "Overall Risk Level: MODERATE" in markdown
    assert "CLEAR: no material concerns" not in markdown
