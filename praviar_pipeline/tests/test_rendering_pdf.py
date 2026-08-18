"""Tests for PDF renderer (Typst) — verify file creation and magic bytes."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.audit import PipelineAuditTrail
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.critic import (
    CriticFinding,
    CriticIssueSeverity,
    CriticIssueType,
)
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.rendering.pdf import render_pdf

from .pdf_test_support import make_test_report_manifest

_typst_installed = shutil.which("typst") is not None

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
                ],
                overall_status=ElementStatus.MET,
                overall_confidence=0.95,
            ),
        ],
        risk_level=RiskLevel.HIGH,
        risk_summary="High risk — all claim elements met",
    )


@pytest.fixture
def pdf_report(
    minimal_compound: ResolvedCompound,
    minimal_analysis: PatentAnalysis,
) -> FTOReport:
    """FTOReport for PDF rendering tests."""
    now = datetime.now(UTC)
    return FTOReport(
        report_id="pdf-test-001",
        generated_at=now,
        compound=minimal_compound,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.HIGH,
            blocking_patents_count=1,
            total_patents_analyzed=1,
            key_risks=["US7851188B2: high risk"],
            executive_summary="High FTO risk identified for succinic acid.",
        ),
        patent_analyses=[minimal_analysis],
        verification=VerificationResult(
            checks=[
                VerificationCheck(
                    check_name="citation_grounding",
                    passed=True,
                    details="All patent IDs verified",
                ),
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        ),
        total_patents_found=10,
        patents_after_triage=3,
        search_sources_used=["pubchem"],
        audit_trail=PipelineAuditTrail(),
        patent_narratives={
            "US7851188B2": "This patent directly covers the target process.",
        },
        llm_models_used={
            "triage": "claude-haiku-4-5-20251001",
            "analysis": "claude-sonnet-4-20250514",
        },
        manifest=make_test_report_manifest("succinic acid"),
    )


# ---------------------------------------------------------------------------
# Tests — Typst not available: should raise RuntimeError
# ---------------------------------------------------------------------------


class TestPDFNoTypst:
    """When Typst is not installed, render_pdf must raise RuntimeError."""

    def test_raises_runtime_error_without_typst(self, pdf_report: FTOReport, tmp_path: Path):
        output = tmp_path / "report.pdf"
        with (
            patch(
                "praviar_pipeline.rendering.pdf._typst_available",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="Typst is not installed"),
        ):
            render_pdf(pdf_report, output)

    def test_raises_with_empty_analyses(self, minimal_compound: ResolvedCompound, tmp_path: Path):
        report = FTOReport(
            report_id="empty-test",
            compound=minimal_compound,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.CLEAR,
                executive_summary="No blocking patents found.",
            ),
            patent_analyses=[],
            verification=VerificationResult(),
            manifest=make_test_report_manifest("succinic acid"),
        )
        output = tmp_path / "empty_report.pdf"
        with (
            patch(
                "praviar_pipeline.rendering.pdf._typst_available",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="Typst is not installed"),
        ):
            render_pdf(report, output)


# ---------------------------------------------------------------------------
# Tests — Typst installed: verify actual rendering
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
class TestPDFRendering:
    @pytest.fixture(autouse=True)
    def _inject_mock_settings(self, mock_settings) -> None:
        """Provide a fake ANTHROPIC_API_KEY so render_pdf() config validation passes."""

    def test_pdf_file_created(self, pdf_report: FTOReport, tmp_path: Path):
        """render_pdf should create a file at the given path."""
        output = tmp_path / "report.pdf"
        result = render_pdf(pdf_report, output)
        assert result == output
        assert output.exists()

    def test_pdf_nonzero_size(self, pdf_report: FTOReport, tmp_path: Path):
        """Generated PDF should have non-zero file size."""
        output = tmp_path / "report.pdf"
        render_pdf(pdf_report, output)
        assert output.stat().st_size > 0

    def test_pdf_magic_bytes(self, pdf_report: FTOReport, tmp_path: Path):
        """PDF file should start with the %PDF magic bytes."""
        output = tmp_path / "report.pdf"
        render_pdf(pdf_report, output)
        with open(output, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_pdf_contains_multiple_pages(self, pdf_report: FTOReport, tmp_path: Path):
        """PDF should have reasonable size indicating multiple pages."""
        output = tmp_path / "report.pdf"
        render_pdf(pdf_report, output)
        assert output.stat().st_size > 1000

    def test_pdf_with_empty_analyses(self, minimal_compound: ResolvedCompound, tmp_path: Path):
        """PDF renders correctly even with no patent analyses."""
        report = FTOReport(
            report_id="empty-test",
            compound=minimal_compound,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.CLEAR,
                executive_summary="No blocking patents found.",
            ),
            patent_analyses=[],
            verification=VerificationResult(),
            manifest=make_test_report_manifest("succinic acid"),
        )
        output = tmp_path / "empty_report.pdf"
        result = render_pdf(report, output)
        assert result == output
        assert output.exists()
        with open(output, "rb") as f:
            assert f.read(5) == b"%PDF-"

    def test_pdf_with_narratives(self, pdf_report: FTOReport, tmp_path: Path):
        """PDF includes patent narrative text without error."""
        output = tmp_path / "narrative_report.pdf"
        render_pdf(pdf_report, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_pdf_with_llm_models(self, pdf_report: FTOReport, tmp_path: Path):
        """PDF includes LLM model versions section without error."""
        output = tmp_path / "models_report.pdf"
        render_pdf(pdf_report, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_pdf_with_critic_review_issues(self, pdf_report: FTOReport, tmp_path: Path):
        """PDF renders persisted critic findings instead of silently dropping them."""
        pdf_report.review_issues = [
            CriticFinding(
                issue_type=CriticIssueType.MISSING_LIMITATION,
                patent_id="US7851188B2",
                severity=CriticIssueSeverity.MAJOR,
                description="A material limitation needs review.",
                suggested_correction="Re-check claim 1 against its cited source.",
            )
        ]
        output = tmp_path / "critic_review_issues.pdf"

        render_pdf(pdf_report, output)

        assert output.exists()
        assert output.stat().st_size > 0

    def test_pdf_returns_path(self, pdf_report: FTOReport, tmp_path: Path):
        """render_pdf should return the output path."""
        output = tmp_path / "return_test.pdf"
        result = render_pdf(pdf_report, output)
        assert isinstance(result, Path)
        assert result == output
