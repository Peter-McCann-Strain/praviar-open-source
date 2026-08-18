"""Tests for Markdown renderer — verify key sections and risk display."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.audit import PipelineAuditTrail, SearchFunnelEntry, StepTiming
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.models.report_common import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.rendering.markdown import render_markdown

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="succinic acid",
        canonical_smiles="OC(=O)CCC(O)=O",
        inchi="InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
        inchi_key="KDYFGRWQOYBRFD-UHFFFAOYSA-N",
        pubchem_cid=1110,
        molecular_formula="C4H6O4",
        molecular_weight=118.09,
        cas_numbers=["110-15-6"],
        functional_groups=["carboxylic_acid"],
        original_input="succinic acid",
        input_type="name",
    )


@pytest.fixture
def minimal_analysis() -> PatentAnalysis:
    return PatentAnalysis(
        patent_id="US7851188B2",
        title="Methods for producing succinic acid from fermentation",
        assignee="BioAmber Inc.",
        expiry_date=date(2028, 3, 15),
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="A method for producing succinic acid",
                        status=ElementStatus.MET,
                        reasoning="Target compound is succinic acid",
                        confidence=0.95,
                    ),
                    ClaimElement(
                        element_number=2,
                        element_text="comprising fermenting a microorganism",
                        status=ElementStatus.NOT_MET,
                        reasoning="Different organism used",
                        confidence=0.9,
                    ),
                ],
                overall_status=ElementStatus.NOT_MET,
                overall_confidence=0.9,
            ),
        ],
        risk_level=RiskLevel.MEDIUM,
        risk_summary="Moderate risk — one claim element not met",
    )


@pytest.fixture
def rendering_report(
    minimal_compound: ResolvedCompound,
    minimal_analysis: PatentAnalysis,
) -> FTOReport:
    """FTOReport with all fields populated for rendering tests."""
    now = datetime.now(UTC)
    return FTOReport(
        report_id="render-test-001",
        generated_at=now,
        compound=minimal_compound,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.MEDIUM,
            blocking_patents_count=1,
            total_patents_analyzed=1,
            key_risks=["US7851188B2: medium risk"],
            executive_summary="Moderate FTO risk identified for succinic acid production.",
        ),
        patent_analyses=[minimal_analysis],
        verification=VerificationResult(
            checks=[
                VerificationCheck(
                    check_name="citation_grounding",
                    passed=True,
                    details="All patent IDs found in search results",
                ),
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        ),
        total_patents_found=50,
        patents_after_triage=5,
        search_sources_used=["pubchem", "bigquery"],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem",
                    status=SourceStatus.OK,
                    patent_count=42,
                ),
                SourceHealthEntry(
                    source="bigquery",
                    status=SourceStatus.FAILED,
                    patent_count=0,
                    error_message="HTTP 504 timeout from BigQuery",
                ),
                SourceHealthEntry(
                    source="lens",
                    status=SourceStatus.NOT_CONFIGURED,
                    patent_count=0,
                    error_message="API key missing",
                ),
            ]
        ),
        audit_trail=PipelineAuditTrail(
            search_funnel=[
                SearchFunnelEntry(patent_id="US7851188B2", included_in_triage=True),
            ],
            timing_data=[
                StepTiming(
                    step_name="step2_search",
                    started_at=now,
                    completed_at=now,
                    duration_seconds=3.5,
                    items_processed=100,
                    items_output=50,
                ),
            ],
            total_patents_discovered=100,
        ),
        patent_narratives={
            "US7851188B2": "This patent covers fermentation-based succinic acid production.",
        },
        llm_models_used={
            "triage": "claude-haiku-4-5-20251001",
            "analysis": "claude-sonnet-4-20250514",
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    def test_title_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "# Freedom-to-Operate Analysis Report" in md

    def test_disclaimer_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "DISCLAIMER" in md
        assert "NOT constitute" in md or "does NOT constitute" in md

    def test_executive_summary_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Executive Summary" in md
        assert "Clearance Decision: UNCLEAR" in md
        assert "Overall Risk Level: MODERATE" in md
        assert "Clearance decision: UNCLEAR" in md
        assert "Moderate FTO risk" not in md

    def test_compound_profile_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Compound Profile" in md
        assert "succinic acid" in md
        assert "OC(=O)CCC(O)=O" in md
        assert "KDYFGRWQOYBRFD-UHFFFAOYSA-N" in md
        assert "C4H6O4" in md
        assert "118.09" in md

    def test_cas_numbers_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "110-15-6" in md

    def test_search_coverage_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Search Coverage" in md
        assert "50" in md  # total_patents_found
        assert "Configured source requests" in md
        assert "pubchem" in md
        assert "bigquery" in md
        assert "lens" in md
        assert "Provider request failed" in md
        assert "HTTP 504 timeout from BigQuery" not in md
        assert "Not configured" in md

    def test_provider_query_credentials_are_not_rendered(self, rendering_report: FTOReport):
        rendering_report.source_health.entries[
            1
        ].error_message = "401 https://api.openalex.org/works?api_key=SUPERSECRET"

        md = render_markdown(rendering_report)

        assert "Provider request failed" in md
        assert "SUPERSECRET" not in md
        assert "api_key=" not in md

    def test_unresolved_doe_is_not_rendered_as_not_equivalent(
        self,
        rendering_report: FTOReport,
        sample_doe_assessment,
    ):
        sample_doe_assessment.overall_equivalent = None
        rendering_report.doe_assessments = [sample_doe_assessment]

        md = render_markdown(rendering_report)

        assert "**Unresolved**" in md
        assert "**Not equivalent**" not in md

    def test_risk_matrix_present(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Risk Matrix" in md
        assert "US7851188B2" in md
        assert "BioAmber Inc." in md

    def test_risk_display_mapping(self, rendering_report: FTOReport):
        """Risk levels should display as HIGH/MODERATE/LOW, not high/medium/low."""
        md = render_markdown(rendering_report)
        # The MEDIUM risk should display as MODERATE
        assert "MODERATE" in md

    def test_risk_display_high(self):
        """Verify HIGH risk maps correctly."""
        from praviar_pipeline.rendering.markdown import _risk_display

        assert _risk_display(RiskLevel.HIGH) == "HIGH"
        assert _risk_display(RiskLevel.MEDIUM) == "MODERATE"
        assert _risk_display(RiskLevel.LOW) == "LOW"
        assert _risk_display(RiskLevel.CLEAR) == "CLEAR"

    def test_no_numerical_confidence_in_output(self, rendering_report: FTOReport):
        """Report should use bands, not raw numerical scores like 0.95."""
        md = render_markdown(rendering_report)
        # The confidence values (0.95, 0.9) from ClaimElements should not
        # appear as raw numbers in the rendered output
        assert "0.95" not in md
        # 0.9 can appear in dates like 2024-09-xx, so only check it's not a confidence value
        assert "confidence: 0.9" not in md.lower()

    def test_detailed_patent_analysis_section(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Detailed Patent Analysis" in md
        assert "### US7851188B2" in md
        assert "Claim 1" in md

    def test_claim_elements_table(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "Element" in md
        assert "Status" in md
        assert "MET" in md
        assert "NOT MET" in md

    def test_patent_narrative_included(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "fermentation-based succinic acid production" in md

    def test_verification_section(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Verification Results" in md
        assert "citation_grounding" in md
        assert "PASS" in md

    def test_pipeline_summary_with_timing(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "## Pipeline Summary" in md
        assert "step2_search" in md

    def test_appendix_search_parameters(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "Appendix B: Search Parameters" in md
        assert "succinic acid" in md

    def test_appendix_llm_models(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "Appendix C: LLM Model Versions" in md
        assert "claude-haiku-4-5-20251001" in md
        assert "claude-sonnet-4-20250514" in md

    def test_appendix_patent_disposition(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "Appendix A: Patent Disposition Summary" in md

    def test_report_id_in_output(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert "render-test-001" in md

    def test_output_is_string(self, rendering_report: FTOReport):
        md = render_markdown(rendering_report)
        assert isinstance(md, str)
        assert len(md) > 100  # Non-trivial output
