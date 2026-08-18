"""Tests for Step 7: Verification — deterministic checks, no mocks needed."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.pipeline.step7_verify import (
    _check_citations,
    _check_date_consistency,
    _check_orange_book,
    _check_risk_consistency,
    _looks_like_smiles,
    verify_analysis,
)


class TestCheckCitations:
    def test_all_found(self, sample_analysis, sample_patent_hits):
        check = _check_citations([sample_analysis], sample_patent_hits)
        assert check.passed is True

    def test_missing_citation(self, sample_patent_hits):
        fake_analysis = PatentAnalysis(
            patent_id="US_HALLUCINATED_123",
            risk_level=RiskLevel.LOW,
            risk_summary="Fake",
        )
        check = _check_citations([fake_analysis], sample_patent_hits)
        assert check.passed is False
        assert "HALLUCINATED" in check.details


class TestCheckRiskConsistency:
    def test_high_risk_with_blocking_claim(self, sample_high_risk_analysis):
        check = _check_risk_consistency([sample_high_risk_analysis])
        assert check.passed is True

    def test_high_risk_without_blocking_claim(self):
        """HIGH risk with all claims NOT_MET should fail."""
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.HIGH,
            risk_summary="Marked high but no claims met",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="test",
                            status=ElementStatus.NOT_MET,
                            reasoning="not met",
                        ),
                    ],
                    overall_status=ElementStatus.NOT_MET,
                ),
            ],
        )
        check = _check_risk_consistency([analysis])
        assert check.passed is False

    def test_high_risk_with_partially_met_passes(self):
        """HIGH risk with PARTIALLY_MET claims is valid — conservative FTO practice."""
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.HIGH,
            risk_summary="Most elements met, some unclear",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.PARTIALLY_MET,
                ),
            ],
        )
        check = _check_risk_consistency([analysis])
        assert check.passed is True

    def test_high_risk_with_unclear_passes(self):
        """HIGH risk with UNCLEAR claims is valid — err on the side of caution."""
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.HIGH,
            risk_summary="Claim interpretation uncertain",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.UNCLEAR,
                ),
            ],
        )
        check = _check_risk_consistency([analysis])
        assert check.passed is True

    def test_medium_risk_passes(self, sample_analysis):
        """MEDIUM risk doesn't require a blocking claim."""
        check = _check_risk_consistency([sample_analysis])
        assert check.passed is True


class TestCheckDateConsistency:
    def test_valid_dates(self, sample_analysis, mock_settings):
        check = _check_date_consistency([sample_analysis])
        assert check.passed is True

    def test_implausible_date(self, mock_settings):
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.LOW,
            risk_summary="test",
            expiry_date=date(1800, 1, 1),
        )
        check = _check_date_consistency([analysis])
        assert check.passed is False

    def test_invalid_date_rejected_by_model(self):
        """Invalid date strings are now rejected at the Pydantic model level."""
        with pytest.raises(ValidationError):
            PatentAnalysis(
                patent_id="US123",
                risk_level=RiskLevel.LOW,
                risk_summary="test",
                expiry_date="not-a-date",
            )

    def test_no_expiry_passes(self, mock_settings):
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.LOW,
            risk_summary="test",
        )
        check = _check_date_consistency([analysis])
        assert check.passed is True


class TestVerifyAnalysis:
    def test_full_verification_pass(
        self,
        sample_analysis,
        sample_doe_assessment,
        sample_invalidity_assessment,
        sample_patent_hits,
        mock_settings,
    ):
        result = verify_analysis(
            [sample_analysis],
            [sample_doe_assessment],
            [sample_invalidity_assessment],
            sample_patent_hits,
        )
        assert result.all_citations_valid is True
        assert result.risk_levels_justified is True
        assert result.dates_consistent is True

    def test_full_verification_with_issues(self, sample_patent_hits, mock_settings):
        bad_analysis = PatentAnalysis(
            patent_id="US_FAKE_999",
            risk_level=RiskLevel.HIGH,
            risk_summary="fake",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.NOT_MET,
                ),
            ],
        )
        result = verify_analysis([bad_analysis], [], [], sample_patent_hits)
        assert result.all_citations_valid is False
        assert result.risk_levels_justified is False
        assert len(result.issues) >= 2


class TestLooksLikeSmiles:
    """Test the SMILES detection heuristic avoids false positives on English text."""

    def test_real_smiles(self):
        assert _looks_like_smiles("CC(=O)O") is True  # acetic acid
        assert _looks_like_smiles("c1ccccc1") is True  # benzene
        assert _looks_like_smiles("CC(=O)[O-]") is True  # acetate

    def test_english_words_rejected(self):
        assert _looks_like_smiles("feedstocks)") is False
        assert _looks_like_smiles("(meth)acrylate") is False
        assert _looks_like_smiles("process(es)") is False
        assert _looks_like_smiles("compound") is False

    def test_short_strings_rejected(self):
        assert _looks_like_smiles("C=O") is False  # too short
        assert _looks_like_smiles("CC") is False

    def test_parenthetical_english_rejected(self):
        assert _looks_like_smiles("(optional)") is False
        assert _looks_like_smiles("(described") is False


class TestOrangeBookCrossReference:
    def test_listed_patent_enriches_analysis(self, mock_settings):
        from praviar_pipeline.clients.orange_book import OrangeBookEntry, OrangeBookIndex
        from praviar_pipeline.models.patent import OrangeBookExclusivity

        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking composition patent",
        )
        orange_book = OrangeBookIndex(
            {
                "7851188": [
                    OrangeBookEntry(
                        patent_number="7851188",
                        raw_patent_number="7851188",
                        application_type="N",
                        application_number="123456",
                        product_number="001",
                        nda_number="N123456",
                        product_name="TestDrug",
                        active_ingredient="Osimertinib",
                        dosage_form_route="TABLET;ORAL",
                        reference_listed_drug=True,
                        reference_standard=True,
                        exclusivities=[
                            OrangeBookExclusivity(
                                code="NCE",
                                expiration_date="Nov 13, 2020",
                            )
                        ],
                        patent_use_code="U-1234",
                        delist_requested=True,
                    )
                ]
            }
        )

        check = _check_orange_book([analysis], orange_book)

        assert check.passed is True
        assert "LISTED" in check.details
        assert analysis.orange_book_info is not None
        assert analysis.orange_book_info.is_listed is True
        assert analysis.orange_book_info.nda_numbers == ["N123456"]
        assert analysis.orange_book_info.dosage_forms_routes == ["TABLET;ORAL"]
        assert analysis.orange_book_info.reference_listed_drug is True
        assert analysis.orange_book_info.reference_standard is True
        assert analysis.orange_book_info.exclusivity_codes == ["NCE"]
        assert analysis.orange_book_info.exclusivities[0].expiration_date == ("Nov 13, 2020")
        assert analysis.orange_book_info.delist_requested is True
        assert "LISTED — DELIST REQUESTED" in check.details
