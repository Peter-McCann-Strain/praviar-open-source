"""Tests for report bibliography builder and assembler."""

from __future__ import annotations

from datetime import date

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.invalidity import (
    InvalidityAssessment,
    PriorArtReference,
    PTABProceeding,
    PTABResult,
)
from praviar_pipeline.models.report_sections import ReportSection
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report_bibliography import (
    BibliographyBuilder,
    _doi_url,
    _google_patents_url,
    _ptab_url,
    assemble_report,
)
from praviar_pipeline.pipeline.report_bibliography_helpers import (
    collect_mentioned_patent_ids,
)
from praviar_pipeline.pipeline.report_data_store import ReportDataStore


def _make_compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="osimertinib",
        canonical_smiles="C=CC(=O)Nc1cc",
        original_input="osimertinib",
        input_type="name",
        compound_type="small_molecule",
    )


def _make_analysis(
    patent_id: str = "US10000001B2",
    risk: RiskLevel = RiskLevel.HIGH,
    assignee: str = "Acme Corp",
    expiry: date | None = None,
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title="Test Patent Title",
        assignee=assignee,
        expiry_date=expiry or date(2030, 6, 15),
        risk_level=risk,
        risk_summary=f"{risk.value} risk",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status=ElementStatus.MET,
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="compound",
                        status=ElementStatus.MET,
                        reasoning="Match",
                    ),
                ],
            ),
        ],
    )


def _make_store(
    analyses: list[PatentAnalysis] | None = None,
    invalidity: list[InvalidityAssessment] | None = None,
) -> ReportDataStore:
    return ReportDataStore(
        compound=_make_compound(),
        analyses=analyses or [_make_analysis()],
        doe_assessments=[],
        invalidity_assessments=invalidity or [],
        verification=VerificationResult(),
        overall_risk=RiskLevel.HIGH,
    )


def _section(sid: str, content: str) -> ReportSection:
    return ReportSection(
        section_id=sid,
        section_title=sid,
        content=content,
        word_count=len(content.split()),
    )


# ── URL generators ──────────────────────────────────────────────────────


class TestGooglePatentsUrl:
    def test_generates_correct_url(self):
        url = _google_patents_url("US10000001B2")
        assert url == "https://patents.google.com/patent/US10000001B2"

    def test_normalizes_dashes_and_spaces(self):
        url = _google_patents_url("US-10,000,001-B2")
        assert url == "https://patents.google.com/patent/US10000001B2"


def test_collects_multi_jurisdiction_patent_references():
    sections = [
        _section(
            "key_patents",
            "EP1234567B1, WO2024/112312A1, CN120187720A, and JP7654321B2 are material.",
        )
    ]

    assert collect_mentioned_patent_ids(sections) == {
        "EP1234567B1",
        "WO2024112312A1",
        "CN120187720A",
        "JP7654321B2",
    }


class TestDoiUrl:
    def test_generates_correct_url(self):
        url = _doi_url("10.1234/test.5678")
        assert url == "https://doi.org/10.1234/test.5678"

    def test_handles_empty(self):
        url = _doi_url("")
        assert url == ""


class TestPtabUrl:
    def test_generates_correct_url(self):
        url = _ptab_url("IPR2020-00123")
        assert url == "https://ptab.uspto.gov/#/case/IPR2020-00123"

    def test_handles_empty(self):
        url = _ptab_url("")
        assert url == ""


# ── BibliographyBuilder ─────────────────────────────────────────────────


class TestBibliographyBuilderBuild:
    def test_build_with_mentioned_patents(self):
        store = _make_store()
        builder = BibliographyBuilder(store)
        sections = [_section("key_patents", "Patent US10000001B2 is HIGH risk.")]
        text, entries = builder.build(sections)
        assert len(entries) >= 1
        patent_entries = [e for e in entries if e.ref_type == "patent"]
        assert len(patent_entries) == 1
        assert patent_entries[0].patent_id == "US10000001B2"
        assert "US10000001B2" in text

    def test_build_deduplicates_entries(self):
        store = _make_store()
        builder = BibliographyBuilder(store)
        # Same patent mentioned twice in different sections
        sections = [
            _section("executive_summary", "US10000001B2 is the biggest risk."),
            _section("key_patents", "Analysis of US10000001B2 shows HIGH risk."),
        ]
        _, entries = builder.build(sections)
        patent_entries = [e for e in entries if e.ref_type == "patent"]
        assert len(patent_entries) == 1

    def test_build_with_no_patents_mentioned(self):
        store = _make_store()
        builder = BibliographyBuilder(store)
        sections = [_section("data_quality", "No patents to report.")]
        _text, entries = builder.build(sections)
        patent_entries = [e for e in entries if e.ref_type == "patent"]
        assert len(patent_entries) == 0

    def test_build_with_prior_art(self):
        ia = InvalidityAssessment(
            patent_id="US10000001B2",
            claim_numbers=[1],
            ptab=PTABResult(has_been_challenged=False),
            prior_art=[
                PriorArtReference(
                    reference_id="ref-001",
                    title="Important Prior Art Paper",
                    doi="10.1234/test",
                    publication_date=date(2015, 5, 1),
                ),
            ],
            overall_invalidity_strength="moderate",
            reasoning="Prior art found",
            confidence=0.6,
        )
        store = _make_store(invalidity=[ia])
        builder = BibliographyBuilder(store)
        sections = [_section("invalidity", "Patent US10000001B2 has prior art.")]
        _text, entries = builder.build(sections)
        prior_art_entries = [e for e in entries if e.ref_type == "prior_art"]
        assert len(prior_art_entries) == 1
        assert prior_art_entries[0].title == "Important Prior Art Paper"
        assert prior_art_entries[0].doi == "10.1234/test"

    def test_build_with_ptab(self):
        ia = InvalidityAssessment(
            patent_id="US10000001B2",
            claim_numbers=[1],
            ptab=PTABResult(
                has_been_challenged=True,
                proceedings=[
                    PTABProceeding(
                        proceeding_number="IPR2021-00555",
                        type="IPR",
                        status="Instituted",
                    ),
                ],
            ),
            overall_invalidity_strength="strong",
            reasoning="PTAB challenge",
            confidence=0.8,
        )
        store = _make_store(invalidity=[ia])
        builder = BibliographyBuilder(store)
        sections = [_section("invalidity", "Patent US10000001B2 challenged.")]
        _text, entries = builder.build(sections)
        ptab_entries = [e for e in entries if e.ref_type == "ptab"]
        assert len(ptab_entries) == 1
        assert ptab_entries[0].proceeding_number == "IPR2021-00555"

    def test_all_entry_types_represented(self):
        ia = InvalidityAssessment(
            patent_id="US10000001B2",
            claim_numbers=[1],
            ptab=PTABResult(
                has_been_challenged=True,
                proceedings=[
                    PTABProceeding(
                        proceeding_number="IPR2021-00555",
                        type="IPR",
                        status="Instituted",
                    ),
                ],
            ),
            prior_art=[
                PriorArtReference(
                    reference_id="ref-002",
                    title="Scholarly Paper",
                    doi="10.1234/x",
                ),
            ],
            overall_invalidity_strength="moderate",
            reasoning="Multiple vectors",
            confidence=0.7,
        )
        store = _make_store(invalidity=[ia])
        builder = BibliographyBuilder(store)
        sections = [_section("key_patents", "US10000001B2 analysis")]
        _, entries = builder.build(sections)
        ref_types = {e.ref_type for e in entries}
        assert "patent" in ref_types
        assert "prior_art" in ref_types
        assert "ptab" in ref_types


# ── assemble_report ──────────────────────────────────────────────────────


class TestAssembleReport:
    def test_concatenates_sections(self):
        sections = [
            _section("executive_summary", "Executive summary content here."),
            _section("key_patents", "Key patents content here."),
        ]
        text = assemble_report(
            sections=sections,
            bibliography_text="",
            compound_name="test compound",
        )
        assert "Executive summary content here." in text
        assert "Key patents content here." in text

    def test_includes_header(self):
        sections = [_section("executive_summary", "Summary.")]
        text = assemble_report(
            sections=sections,
            bibliography_text="",
            compound_name="osimertinib",
        )
        assert "FREEDOM-TO-OPERATE ANALYSIS" in text
        assert "OSIMERTINIB" in text
        assert "Generated:" in text
        assert "Praviar FTO Analysis" in text
        assert "Praviar Pipeline" not in text

    def test_includes_verification_score(self):
        sections = [_section("executive_summary", "Summary.")]
        text = assemble_report(
            sections=sections,
            bibliography_text="",
            compound_name="test",
            verification_score=0.95,
        )
        assert "95%" in text

    def test_includes_bibliography(self):
        sections = [_section("executive_summary", "Summary.")]
        bib = "REFERENCE APPENDIX\nUS10000001B2 - Acme Corp"
        text = assemble_report(
            sections=sections,
            bibliography_text=bib,
            compound_name="test",
        )
        assert "REFERENCE APPENDIX" in text

    def test_includes_disclaimer(self):
        sections = [_section("executive_summary", "Summary.")]
        text = assemble_report(
            sections=sections,
            bibliography_text="",
            compound_name="test",
        )
        assert "DISCLAIMER" in text
        assert "does not constitute legal advice" in text.lower() or "NOT constitute" in text

    def test_no_verification_score(self):
        sections = [_section("executive_summary", "Summary.")]
        text = assemble_report(
            sections=sections,
            bibliography_text="",
            compound_name="test",
            verification_score=None,
        )
        assert "Verified:" not in text
