"""Tests for deterministic report validators."""

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
from praviar_pipeline.models.invalidity import InvalidityAssessment, PTABProceeding, PTABResult
from praviar_pipeline.models.report_sections import ReportSection
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report_data_store import ReportDataStore
from praviar_pipeline.pipeline.report_validators import (
    AssigneeValidator,
    CrossSectionRiskConsistencyValidator,
    DateValidator,
    DisclaimerValidator,
    HighRiskCompletenessValidator,
    OverallRiskValidator,
    PatentIdValidator,
    PtabFormatValidator,
    RiskLevelValidator,
    WordCountValidator,
    apply_corrections,
    run_deterministic_validators,
)


def _make_store(risk: RiskLevel = RiskLevel.HIGH) -> ReportDataStore:
    return ReportDataStore(
        compound=ResolvedCompound(
            name="test",
            canonical_smiles="C",
            original_input="test",
            input_type="name",
            compound_type="small_molecule",
        ),
        analyses=[
            PatentAnalysis(
                patent_id="US10000001B2",
                title="Test",
                assignee="Acme",
                risk_level=risk,
                risk_summary="test risk",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        overall_status=ElementStatus.MET,
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="x",
                                status=ElementStatus.MET,
                                reasoning="y",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        doe_assessments=[],
        invalidity_assessments=[],
        verification=VerificationResult(),
        overall_risk=risk,
    )


def _section(sid: str, content: str) -> ReportSection:
    return ReportSection(
        section_id=sid,
        section_title=sid,
        content=content,
        word_count=len(content.split()),
    )


class TestPatentIdValidator:
    def test_known_patent_passes(self):
        store = _make_store()
        sections = [_section("executive_summary", "Patent US10000001B2 is HIGH risk.")]
        result = PatentIdValidator().validate(sections, store)
        assert result.passed

    def test_unknown_patent_fails(self):
        store = _make_store()
        sections = [_section("executive_summary", "Patent US99999999B2 is HIGH risk.")]
        result = PatentIdValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) >= 1

    def test_no_patents_in_text_passes(self):
        store = _make_store()
        sections = [_section("data_quality", "No patents to report.")]
        result = PatentIdValidator().validate(sections, store)
        assert result.passed


class TestHighRiskCompletenessValidator:
    def test_high_patent_mentioned_passes(self):
        store = _make_store(RiskLevel.HIGH)
        sections = [
            _section("executive_summary", "US10000001B2 is high risk"),
            _section("key_patents", "Details for US10000001B2"),
        ]
        result = HighRiskCompletenessValidator().validate(sections, store)
        assert result.passed

    def test_high_patent_missing_fails(self):
        store = _make_store(RiskLevel.HIGH)
        sections = [
            _section("executive_summary", "No patents mentioned"),
            _section("key_patents", "Nothing here either"),
        ]
        result = HighRiskCompletenessValidator().validate(sections, store)
        assert not result.passed

    def test_no_high_patents_passes(self):
        store = _make_store(RiskLevel.CLEAR)
        sections = [_section("executive_summary", "All clear")]
        result = HighRiskCompletenessValidator().validate(sections, store)
        assert result.passed


class TestOverallRiskValidator:
    def test_risk_stated_passes(self):
        store = _make_store(RiskLevel.HIGH)
        sections = [_section("executive_summary", "Overall risk: HIGH")]
        result = OverallRiskValidator().validate(sections, store)
        assert result.passed

    def test_risk_not_stated_fails(self):
        store = _make_store(RiskLevel.HIGH)
        sections = [_section("executive_summary", "This compound looks fine")]
        result = OverallRiskValidator().validate(sections, store)
        assert not result.passed

    def test_negated_clear_and_high_risk_cannot_pass_clear(self):
        store = _make_store(RiskLevel.CLEAR)
        sections = [
            _section(
                "executive_summary",
                "This matter is NOT CLEAR; overall risk remains HIGH.",
            )
        ]
        result = OverallRiskValidator().validate(sections, store)
        assert not result.passed

    def test_duplicate_contradictory_anchored_verdicts_fail(self):
        store = _make_store(RiskLevel.CLEAR)
        sections = [
            _section(
                "executive_summary",
                "Overall Risk: CLEAR\nOverall Risk: HIGH",
            )
        ]
        result = OverallRiskValidator().validate(sections, store)
        assert not result.passed

    def test_unanchored_overall_risk_contradiction_fails(self):
        store = _make_store(RiskLevel.CLEAR)
        sections = [
            _section(
                "executive_summary",
                "Overall Risk: CLEAR\nHowever, overall risk remains HIGH.",
            )
        ]
        assert not OverallRiskValidator().validate(sections, store).passed

    def test_no_exec_summary_fails(self):
        store = _make_store()
        sections = [_section("key_patents", "some content")]
        result = OverallRiskValidator().validate(sections, store)
        assert not result.passed


class TestWordCountValidator:
    def test_sufficient_words_passes(self):
        store = _make_store()
        content = " ".join(["word"] * 200)
        sections = [_section("executive_summary", content)]
        result = WordCountValidator().validate(sections, store)
        assert result.passed

    def test_too_few_words_fails(self):
        store = _make_store()
        sections = [_section("executive_summary", "Too short")]
        result = WordCountValidator().validate(sections, store)
        assert not result.passed


class TestRunAll:
    def test_all_validators_run(self):
        store = _make_store()
        content = " ".join(["word"] * 200) + " Overall risk: HIGH US10000001B2"
        sections = [
            _section("executive_summary", content),
            _section("key_patents", "US10000001B2 " + " ".join(["word"] * 100)),
        ]
        results = run_deterministic_validators(sections, store)
        assert len(results) >= 5
        assert all(isinstance(r.validator_name, str) for r in results)

    def test_all_10_validators_run(self):
        store = _make_store()
        content = " ".join(["word"] * 200) + " Overall risk: HIGH US10000001B2"
        sections = [
            _section("executive_summary", content),
            _section("key_patents", "US10000001B2 " + " ".join(["word"] * 100)),
        ]
        results = run_deterministic_validators(sections, store)
        assert len(results) == 10
        assert {result.validator_name for result in results} == {
            "patent_id_exists",
            "high_risk_completeness",
            "overall_risk_match",
            "disclaimer_present",
            "word_count_bounds",
            "ptab_format",
            "risk_level_match",
            "cross_section_risk_consistency",
            "date_match",
            "assignee_match",
        }


# ── New validator tests ──────────────────────────────────────────────────


def _make_store_with_expiry(
    risk: RiskLevel = RiskLevel.HIGH,
    assignee: str = "Acme Corp",
    expiry: date | None = None,
) -> ReportDataStore:
    return ReportDataStore(
        compound=ResolvedCompound(
            name="test",
            canonical_smiles="C",
            original_input="test",
            input_type="name",
            compound_type="small_molecule",
        ),
        analyses=[
            PatentAnalysis(
                patent_id="US10000001B2",
                title="Test",
                assignee=assignee,
                expiry_date=expiry or date(2030, 6, 15),
                risk_level=risk,
                risk_summary="test risk",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        overall_status=ElementStatus.MET,
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="x",
                                status=ElementStatus.MET,
                                reasoning="y",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        doe_assessments=[],
        invalidity_assessments=[],
        verification=VerificationResult(),
        overall_risk=risk,
    )


def _make_store_with_ptab() -> ReportDataStore:
    return ReportDataStore(
        compound=ResolvedCompound(
            name="test",
            canonical_smiles="C",
            original_input="test",
            input_type="name",
            compound_type="small_molecule",
        ),
        analyses=[
            PatentAnalysis(
                patent_id="US10000001B2",
                title="Test",
                assignee="Acme Corp",
                risk_level=RiskLevel.HIGH,
                risk_summary="test risk",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        overall_status=ElementStatus.MET,
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="x",
                                status=ElementStatus.MET,
                                reasoning="y",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        doe_assessments=[],
        invalidity_assessments=[
            InvalidityAssessment(
                patent_id="US10000001B2",
                ptab=PTABResult(
                    has_been_challenged=True,
                    proceedings=[
                        PTABProceeding(
                            proceeding_number="IPR2020-00001",
                            type="IPR",
                            status="Instituted",
                        )
                    ],
                ),
            )
        ],
        verification=VerificationResult(),
        overall_risk=RiskLevel.HIGH,
    )


class TestDisclaimerValidator:
    def test_disclaimer_present_passes(self):
        store = _make_store()
        sections = [
            _section(
                "executive_summary",
                (
                    "This report does not constitute legal advice and should not be relied "
                    "upon as a substitute for consultation with counsel."
                ),
            )
        ]
        result = DisclaimerValidator().validate(sections, store)
        assert result.passed

    def test_missing_disclaimer_fails(self):
        store = _make_store()
        sections = [_section("executive_summary", "Overall risk: HIGH for US10000001B2.")]
        result = DisclaimerValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) == 1
        assert "Mandatory legal disclaimer is missing" in result.issues[0].description

    def test_attorney_work_product_phrase_alone_does_not_pass(self):
        store = _make_store()
        sections = [
            _section(
                "executive_summary",
                "PRIVILEGED AND CONFIDENTIAL — ATTORNEY WORK PRODUCT",
            )
        ]
        result = DisclaimerValidator().validate(sections, store)
        assert not result.passed


class TestPtabFormatValidator:
    def test_known_ptab_proceeding_passes(self):
        store = _make_store_with_ptab()
        sections = [_section("invalidity", "Related PTAB matter IPR2020-00001 remains active.")]
        result = PtabFormatValidator().validate(sections, store)
        assert result.passed

    def test_unknown_ptab_proceeding_fails(self):
        store = _make_store_with_ptab()
        sections = [_section("invalidity", "Related PTAB matter IPR2021-99999 remains active.")]
        result = PtabFormatValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) == 1
        assert "IPR2021-99999" in result.issues[0].description


class TestRiskLevelValidator:
    def test_correct_risk_passes(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("key_patents", "US10000001B2 is HIGH risk and needs attention.")]
        result = RiskLevelValidator().validate(sections, store)
        assert result.passed

    def test_wrong_risk_fails(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("key_patents", "US10000001B2 is LOW risk and can be ignored.")]
        result = RiskLevelValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) >= 1
        assert "LOW" in result.issues[0].actual
        assert "HIGH" in result.issues[0].expected

    def test_no_risk_mentions_passes(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("data_quality", "No risk analysis performed.")]
        result = RiskLevelValidator().validate(sections, store)
        assert result.passed


class TestCrossSectionRiskConsistencyValidator:
    def test_consistent_risk_passes(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [
            _section("executive_summary", "US10000001B2 is HIGH risk."),
            _section("key_patents", "US10000001B2 is HIGH risk patent."),
        ]
        result = CrossSectionRiskConsistencyValidator().validate(sections, store)
        assert result.passed

    def test_inconsistent_risk_fails(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [
            _section("executive_summary", "US10000001B2 is HIGH risk."),
            _section("key_patents", "US10000001B2 is LOW risk patent."),
        ]
        result = CrossSectionRiskConsistencyValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) >= 1
        assert "inconsistent" in result.issues[0].description.lower()

    def test_no_mentions_passes(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("data_quality", "All data looks good.")]
        result = CrossSectionRiskConsistencyValidator().validate(sections, store)
        assert result.passed


class TestDateValidator:
    def test_correct_date_passes(self):
        store = _make_store_with_expiry(expiry=date(2030, 6, 15))
        sections = [
            _section("key_patents", "US10000001B2 has an expiry 2030-06-15 for the compound.")
        ]
        result = DateValidator().validate(sections, store)
        assert result.passed

    def test_wrong_date_fails(self):
        store = _make_store_with_expiry(expiry=date(2030, 6, 15))
        sections = [_section("key_patents", "US10000001B2 has an expiry 2025-01-01 which is soon.")]
        result = DateValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) >= 1
        assert "2030-06-15" in result.issues[0].expected

    def test_one_day_tolerance(self):
        store = _make_store_with_expiry(expiry=date(2030, 6, 15))
        # Off by one day should still pass
        sections = [
            _section("key_patents", "US10000001B2 has an expiry 2030-06-16 for the compound.")
        ]
        result = DateValidator().validate(sections, store)
        assert result.passed

    def test_no_dates_passes(self):
        store = _make_store_with_expiry()
        sections = [_section("data_quality", "No expiry information available.")]
        result = DateValidator().validate(sections, store)
        assert result.passed


class TestAssigneeValidator:
    def test_correct_assignee_passes(self):
        store = _make_store_with_expiry(assignee="Acme Corp")
        sections = [_section("key_patents", "US10000001B2 (Acme Corp) covers the compound.")]
        result = AssigneeValidator().validate(sections, store)
        assert result.passed

    def test_wrong_assignee_fails(self):
        store = _make_store_with_expiry(assignee="Acme Corp")
        sections = [
            _section("key_patents", "US10000001B2 (Totally Different Inc.) covers the compound.")
        ]
        result = AssigneeValidator().validate(sections, store)
        assert not result.passed
        assert len(result.issues) >= 1
        assert "Acme Corp" in result.issues[0].expected

    def test_normalized_match_passes(self):
        store = _make_store_with_expiry(assignee="Acme Corporation")
        # "Acme Corp" normalizes same as "Acme Corporation"
        sections = [_section("key_patents", "US10000001B2 (Acme Corp) covers the compound.")]
        result = AssigneeValidator().validate(sections, store)
        # After normalization both become "acme" — should pass
        assert result.passed

    def test_no_assignee_mentions_passes(self):
        store = _make_store_with_expiry(assignee="Acme Corp")
        sections = [_section("data_quality", "No assignee information available.")]
        result = AssigneeValidator().validate(sections, store)
        assert result.passed

    def test_substring_match_passes(self):
        store = _make_store_with_expiry(assignee="Acme Pharmaceutical Corp")
        sections = [_section("key_patents", "US10000001B2 (Acme Pharmaceutical) is blocking.")]
        result = AssigneeValidator().validate(sections, store)
        assert result.passed


class TestApplyCorrections:
    def test_corrects_wrong_risk(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("key_patents", "US10000001B2 is LOW risk and safe.")]
        validation_results = RiskLevelValidator().validate(sections, store)
        corrected = apply_corrections(sections, [validation_results])
        assert "HIGH risk" in corrected[0].content

    def test_corrects_wrong_date(self):
        store = _make_store_with_expiry(expiry=date(2030, 6, 15))
        sections = [_section("key_patents", "US10000001B2 has an expiry 2025-01-01 which is soon.")]
        validation_results = DateValidator().validate(sections, store)
        corrected = apply_corrections(sections, [validation_results])
        assert "2030-06-15" in corrected[0].content

    def test_corrects_wrong_assignee(self):
        store = _make_store_with_expiry(assignee="Acme Corp")
        sections = [_section("key_patents", "US10000001B2 (WrongCo Ltd.) covers the compound.")]
        validation_results = AssigneeValidator().validate(sections, store)
        corrected = apply_corrections(sections, [validation_results])
        assert "Acme Corp" in corrected[0].content

    def test_no_corrections_needed(self):
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("key_patents", "US10000001B2 is HIGH risk.")]
        validation_results = RiskLevelValidator().validate(sections, store)
        corrected = apply_corrections(sections, [validation_results])
        # Should be unchanged
        assert corrected[0].content == sections[0].content

    def test_exhaustive_backward_scan_fixes_risk_before_patent(self):
        # "MEDIUM risk ... US10000001B2" — risk word BEFORE patent ID, no other patent
        # in the sentence. The backward scan should catch this.
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [
            _section("key_patents", "MEDIUM risk is posed to compound use by US10000001B2.")
        ]
        corrected = apply_corrections(sections, [], store)
        assert "HIGH risk" in corrected[0].content
        assert "MEDIUM risk" not in corrected[0].content

    def test_exhaustive_backward_scan_skips_when_other_patent_present(self):
        # "US20000002B2 MEDIUM risk ... US10000001B2" — another patent precedes the risk
        # word so attribution is ambiguous: backward scan must skip.
        store = _make_store_with_expiry(RiskLevel.HIGH)
        content = "US20000002B2 MEDIUM risk while US10000001B2 is also mentioned."
        sections = [_section("key_patents", content)]
        # Supply empty validation_results so only exhaustive scan runs
        corrected = apply_corrections(sections, [], store)
        # US20000002B2 is unknown → backward scan should NOT replace the MEDIUM
        # (attribution unclear) while forward scan from US10000001B2 finds nothing wrong
        assert "MEDIUM risk" in corrected[0].content

    def test_exhaustive_multipass_converges(self):
        # Two corrections in the same sentence that require the backward scan on first
        # pass and a forward scan on the second pass.
        store = _make_store_with_expiry(RiskLevel.HIGH)
        sections = [_section("key_patents", "LOW risk patent US10000001B2 poses MEDIUM risk.")]
        corrected = apply_corrections(sections, [], store)
        assert "HIGH risk" in corrected[0].content
        assert "LOW risk" not in corrected[0].content
        assert "MEDIUM risk" not in corrected[0].content
