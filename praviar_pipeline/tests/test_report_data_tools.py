"""Tests for ReportDataToolkit — tool dispatch and data formatting."""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.report_data_tools")

from praviar_pipeline.agents.tools.report_data_tools import ReportDataToolkit
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report_common import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report_data_store import ReportDataStore


def _make_store() -> ReportDataStore:
    compound = ResolvedCompound(
        name="osimertinib",
        canonical_smiles="C=CC(=O)Nc1cc(OC)c(Nc2ccc(F)c(Cl)c2)nc1",
        original_input="osimertinib",
        input_type="name",
        compound_type="small_molecule",
    )
    analyses = [
        PatentAnalysis(
            patent_id="US10000001B2",
            title="Test Patent",
            assignee="Acme Corp",
            expiry_date=date(2030, 6, 15),
            risk_level=RiskLevel.HIGH,
            risk_summary="HIGH risk — covers compound class",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.MET,
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="compound of Formula I",
                            status=ElementStatus.MET,
                            reasoning="Falls within genus",
                        ),
                    ],
                ),
            ],
        ),
    ]
    return ReportDataStore(
        compound=compound,
        analyses=analyses,
        doe_assessments=[],
        invalidity_assessments=[],
        verification=VerificationResult(),
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="surechembl",
                    status=SourceStatus.OK,
                    patent_count=0,
                )
            ]
        ),
        overall_risk=RiskLevel.HIGH,
    )


class TestToolDefinitions:
    def test_has_ten_tools(self):
        toolkit = ReportDataToolkit(_make_store())
        assert len(toolkit.tool_definitions) == 10

    def test_all_tools_have_required_fields(self):
        toolkit = ReportDataToolkit(_make_store())
        for tool in toolkit.tool_definitions:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_names(self):
        toolkit = ReportDataToolkit(_make_store())
        names = {t["name"] for t in toolkit.tool_definitions}
        assert "get_portfolio_summary" in names
        assert "get_report_scope_and_reliance" in names
        assert "get_patent_analysis" in names
        assert "get_current_date" in names


class TestExecute:
    @pytest.mark.asyncio
    async def test_portfolio_summary(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_portfolio_summary", {})
        assert "osimertinib" in result
        assert "HIGH" in result
        assert "US10000001B2" in result

    @pytest.mark.asyncio
    async def test_scope_and_reliance_tool(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_report_scope_and_reliance", {})
        assert "AI-assisted screening, not legal advice" in result
        assert "Privilege/work-product marking allowed: false" in result
        assert "surechembl: Successful | 0 patents" in result

    @pytest.mark.asyncio
    async def test_patent_analysis_found(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_patent_analysis", {"patent_id": "US10000001B2"})
        assert "US10000001B2" in result
        assert "MET" in result
        assert "Acme Corp" in result

    @pytest.mark.asyncio
    async def test_patent_analysis_not_found(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_patent_analysis", {"patent_id": "USNOTFOUND"})
        assert "No analysis found" in result

    @pytest.mark.asyncio
    async def test_patent_analysis_missing_id(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_patent_analysis", {})
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_current_date(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_current_date", {})
        assert "UTC" in result
        assert "202" in result  # Year starts with 202x

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("nonexistent_tool", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_doe_empty(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_doe_assessment", {"patent_id": "US10000001B2"})
        assert "No Doctrine" in result

    @pytest.mark.asyncio
    async def test_critic_findings_empty(self):
        toolkit = ReportDataToolkit(_make_store())
        result = await toolkit.execute("get_critic_findings", {})
        assert "No critic report" in result

    @pytest.mark.asyncio
    async def test_execute_uses_store_patch_surface(self, monkeypatch):
        store = _make_store()
        toolkit = ReportDataToolkit(store)

        def _patched(_: str) -> str:
            return "patched-analysis"

        monkeypatch.setattr(store, "format_analysis", _patched)

        result = await toolkit.execute(
            "get_patent_analysis",
            {"patent_id": "US10000001B2"},
        )
        assert result == "patched-analysis"
