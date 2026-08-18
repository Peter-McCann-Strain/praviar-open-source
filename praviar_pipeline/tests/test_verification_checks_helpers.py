"""Tests for deterministic verification helper functions."""

from __future__ import annotations

from datetime import date

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.pipeline.verification.checks_helpers import (
    find_date_issues,
    find_risk_inconsistencies,
    is_vacuous_check,
    looks_like_smiles,
)


class TestLooksLikeSmiles:
    def test_real_smiles(self):
        assert looks_like_smiles("CC(=O)O") is True
        assert looks_like_smiles("c1ccccc1") is True

    def test_english_rejected(self):
        assert looks_like_smiles("compound") is False
        assert looks_like_smiles("(optional)") is False


class TestFindRiskInconsistencies:
    def test_high_risk_without_blocking_claim_is_flagged(self):
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.HIGH,
            risk_summary="test",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="x",
                            status=ElementStatus.NOT_MET,
                            reasoning="no",
                        ),
                    ],
                    overall_status=ElementStatus.NOT_MET,
                ),
            ],
        )

        issues = find_risk_inconsistencies([analysis])

        assert issues == ["US123: HIGH risk but all claims are NOT_MET"]

    def test_high_risk_with_unclear_claim_passes(self):
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.HIGH,
            risk_summary="test",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.UNCLEAR,
                ),
            ],
        )

        assert find_risk_inconsistencies([analysis]) == []


class TestFindDateIssues:
    def test_out_of_range_year_is_flagged(self):
        analysis = PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.LOW,
            risk_summary="test",
            expiry_date=date(1800, 1, 1),
        )

        issues = find_date_issues([analysis], 1900, 2100)

        assert issues == ["US123: implausible expiry year 1800"]


class TestVacuousCheck:
    def test_known_vacuous_checks(self):
        assert is_vacuous_check("doe_consistency", 1, 0, 1) is True
        assert is_vacuous_check("risk_level_consistency", 0, 1, 1) is True

    def test_unknown_check_is_not_vacuous(self):
        assert is_vacuous_check("citation_grounding", 0, 0, 0) is False
