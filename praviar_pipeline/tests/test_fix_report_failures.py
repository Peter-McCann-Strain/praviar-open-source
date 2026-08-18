"""Tests for Fix 3 & 8: Analysis failures and data limitations in reports.

Tests:
- AnalysisFailure model
- DataLimitation model
- Failed patents tracked in FTOReport
- Data limitations auto-generated from source health
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report import (
    AnalysisFailure,
    DataLimitation,
    FTOReport,
    RiskSummary,
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.models.report_sections import VerificationReport
from praviar_pipeline.pipeline.step8_report import generate_report

from .helpers import make_claude_client_mock


def _passing_verification_report() -> VerificationReport:
    return VerificationReport(
        total_claims_checked=3,
        claims_correct=3,
        claims_incorrect=0,
        claims_unverifiable=0,
        factual_accuracy_rate=1.0,
        overall_assessment="PASS",
    )


_PASS_VERIFICATION_JSON = _passing_verification_report().model_dump_json()


@pytest.fixture(autouse=True)
def _stub_receipt_bound_verifier_for_report_integration_tests():
    """Verifier receipt semantics are covered in dedicated adversarial tests."""
    with patch(
        "praviar_pipeline.pipeline.report.verification_flow.verify_report",
        new=AsyncMock(
            return_value=(
                _passing_verification_report(),
                250,
                120,
            )
        ),
    ):
        yield


async def _make_complete_text_side_effect(**kwargs):
    role = kwargs.get("role", "unknown")
    if role == "verification_extraction":
        return (_PASS_VERIFICATION_JSON, {"input_tokens": 50, "output_tokens": 20})
    if role == "verification":
        return (
            "All claims verified. No factual errors.",
            {"input_tokens": 200, "output_tokens": 100},
        )
    return (_valid_generated_section_text(), {"input_tokens": 300, "output_tokens": 200})


def _valid_generated_section_text() -> str:
    return (
        "Overall Risk: MEDIUM\n\n"
        "ATTORNEY WORK PRODUCT. This draft FTO analysis for succinic acid maintains a "
        "MEDIUM posture because US7851188B2 remains the material reviewed "
        "reference and the claim chart shows one process element not met. US7851188B2 "
        "is treated consistently as MEDIUM risk, not as a clearance finding, because the "
        "record supports continued attorney review before commercial launch decisions. "
        "The practical recommendation is to consider targeted claim construction review, "
        "monitor family status, preserve invalidity research, and document any process "
        "differences that separate the target route from the fermentation limitations. "
        "The data quality note is that source coverage was sufficient for this test run, "
        "but failed sources or incomplete dossiers should be disclosed as limitations in "
        "the final report. This report does not constitute legal advice and should not be "
        "relied upon as a substitute for review by qualified patent counsel."
    )


class TestAnalysisFailureModel:
    def test_create_failure(self):
        failure = AnalysisFailure(
            patent_id="US7851188B2",
            step="step4_analyze",
            error_type="ValidationError",
            error_message="Failed to parse response",
            recoverable=False,
        )
        assert failure.patent_id == "US7851188B2"
        assert failure.step == "step4_analyze"
        assert failure.recoverable is False

    def test_serialization(self):
        failure = AnalysisFailure(
            patent_id="US123",
            step="step4_analyze",
            error_type="TimeoutError",
            error_message="Request timed out after 30s",
            recoverable=True,
        )
        data = failure.model_dump()
        assert data["patent_id"] == "US123"
        assert data["recoverable"] is True


class TestDataLimitationModel:
    def test_create_limitation(self):
        lim = DataLimitation(
            category="source_unavailable",
            description="SureChEMBL was down during search",
            impact="Structural similarity matches may be missing",
        )
        assert lim.category == "source_unavailable"

    def test_enrichment_gap(self):
        lim = DataLimitation(
            category="enrichment_gap",
            description="No invalidity assessments produced",
            impact="Potential invalidity arguments not evaluated",
        )
        assert lim.category == "enrichment_gap"


class TestFTOReportWithFailures:
    def test_report_includes_failures(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification_result,
    ):
        """FTOReport should store analysis failures."""
        failures = [
            AnalysisFailure(
                patent_id="US-FAILED-1",
                step="step4_analyze",
                error_type="ValueError",
                error_message="Parse error",
            ),
        ]
        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.MEDIUM,
                executive_summary="test",
            ),
            patent_analyses=[sample_analysis],
            verification=sample_verification_result,
            analysis_failures=failures,
        )
        assert len(report.analysis_failures) == 1
        assert report.analysis_failures[0].patent_id == "US-FAILED-1"

    def test_report_includes_limitations(self, succinic_acid, sample_verification_result):
        limitations = [
            DataLimitation(
                category="source_unavailable",
                description="SureChEMBL down",
                impact="Missing structure matches",
            ),
        ]
        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.CLEAR,
                executive_summary="test",
            ),
            verification=sample_verification_result,
            data_limitations=limitations,
        )
        assert len(report.data_limitations) == 1

    def test_empty_by_default(self, succinic_acid, sample_verification_result):
        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.CLEAR,
                executive_summary="test",
            ),
            verification=sample_verification_result,
        )
        assert report.analysis_failures == []
        assert report.data_limitations == []


class TestGenerateReportWithFailures:
    """Integration: generate_report accepts and passes through failures."""

    async def test_failures_in_generated_report(
        self,
        succinic_acid,
        sample_analysis,
        sample_doe_assessment,
        sample_invalidity_assessment,
        sample_verification_result,
        mock_settings,
    ):
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a report writer."
        mock_claude.complete_text.side_effect = _make_complete_text_side_effect

        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        failures = [
            AnalysisFailure(
                patent_id="US-DROPPED-1",
                step="step4_analyze",
                error_type="ValueError",
                error_message="JSON parse failure",
            ),
        ]

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[sample_doe_assessment],
                invalidity_assessments=[sample_invalidity_assessment],
                verification=sample_verification_result,
                source_health=health,
                analysis_failures=failures,
            )

        assert len(report.analysis_failures) == 1
        assert report.analysis_failures[0].patent_id == "US-DROPPED-1"

    async def test_data_limitations_from_failed_sources(
        self,
        succinic_acid,
        sample_analysis,
        sample_doe_assessment,
        sample_invalidity_assessment,
        sample_verification_result,
        mock_settings,
    ):
        """When a search source fails, report should include data limitation."""
        mock_claude = make_claude_client_mock(
            analysis_model="claude-haiku-4-5-20251001",
            deep_model="claude-haiku-4-5-20251001",
        )
        mock_claude.load_prompt.return_value = "You are a report writer."
        mock_claude.complete_text.side_effect = _make_complete_text_side_effect

        # SureChEMBL failed; ratio (1 failed / 3 queried = 33%) stays below
        # SOURCE_FAILURE_ABORT_THRESHOLD so the report still renders with a
        # data-limitation note. This test exercises the degraded-confidence
        # path; the SG-112 abort gate is covered in
        # test_report_policy_data_sufficiency.py.
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
                SourceHealthEntry(source="lens", status=SourceStatus.OK, patent_count=40),
                SourceHealthEntry(
                    source="surechembl",
                    status=SourceStatus.FAILED,
                    error_message="Connection timeout",
                ),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[sample_doe_assessment],
                invalidity_assessments=[sample_invalidity_assessment],
                verification=sample_verification_result,
                source_health=health,
            )

        # Should have a data limitation about the failed source
        assert len(report.data_limitations) >= 1
        lim = report.data_limitations[0]
        assert lim.category == "source_unavailable"
        assert "surechembl" in lim.description.lower()
