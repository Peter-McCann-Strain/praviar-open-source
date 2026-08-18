"""Tests for Fix 5: Verification check warning severity.

Tests the new severity field on VerificationCheck and vacuous pass detection.
A vacuous pass is when a check trivially passes because its input is empty
(e.g., 0 DoE assessments means DoE consistency trivially passes).
"""

from __future__ import annotations

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.verification import VerificationCheck
from praviar_pipeline.pipeline.step7_verify import (
    _detect_vacuous_pass,
    verify_analysis,
)


class TestVerificationCheckSeverity:
    """Test the new severity field on VerificationCheck."""

    def test_default_severity_is_pass(self):
        check = VerificationCheck(
            check_name="test",
            passed=True,
            details="ok",
        )
        assert check.severity == "pass"

    def test_severity_can_be_warning(self):
        check = VerificationCheck(
            check_name="test",
            passed=True,
            severity="warning",
            details="vacuous",
        )
        assert check.severity == "warning"

    def test_severity_can_be_fail(self):
        check = VerificationCheck(
            check_name="test",
            passed=False,
            severity="fail",
            details="bad",
        )
        assert check.severity == "fail"

    def test_severity_serialized(self):
        check = VerificationCheck(
            check_name="test",
            passed=True,
            severity="warning",
            details="vacuous",
        )
        data = check.model_dump()
        assert data["severity"] == "warning"


class TestDetectVacuousPass:
    """Test the _detect_vacuous_pass function."""

    def _make_check(self, name: str) -> VerificationCheck:
        return VerificationCheck(check_name=name, passed=True, details="ok")

    def _make_analysis(self) -> PatentAnalysis:
        return PatentAnalysis(
            patent_id="US123",
            risk_level=RiskLevel.LOW,
            risk_summary="test",
        )

    def test_doe_consistency_vacuous_when_no_assessments(self):
        check = self._make_check("doe_consistency")
        severity = _detect_vacuous_pass(check, [self._make_analysis()], [], [])
        assert severity == "warning"

    def test_doe_consistency_real_when_has_assessments(self):
        from praviar_pipeline.models.equivalents import (
            DoEAssessment,
            EstoppelResult,
            FWRAssessment,
        )

        check = self._make_check("doe_consistency")
        doe = DoEAssessment(
            patent_id="US123",
            claim_number=1,
            element_number=1,
            element_text="test",
            estoppel=EstoppelResult(estoppel_applies=False, file_wrapper_available=False),
            fwr=FWRAssessment(
                same_function=True,
                function_reasoning="",
                same_way=True,
                way_reasoning="",
                same_result=True,
                result_reasoning="",
                equivalent=True,
            ),
            overall_equivalent=True,
            confidence=0.8,
            reasoning="test",
        )
        severity = _detect_vacuous_pass(check, [self._make_analysis()], [doe], [])
        assert severity == "pass"

    def test_invalidity_consistency_vacuous_when_no_assessments(self):
        check = self._make_check("invalidity_consistency")
        severity = _detect_vacuous_pass(check, [self._make_analysis()], [], [])
        assert severity == "warning"

    def test_claim_chart_consistency_vacuous_when_no_invalidity(self):
        check = self._make_check("claim_chart_consistency")
        severity = _detect_vacuous_pass(check, [self._make_analysis()], [], [])
        assert severity == "warning"

    def test_prosecution_history_vacuous_when_no_doe(self):
        check = self._make_check("prosecution_history_consistency")
        severity = _detect_vacuous_pass(check, [self._make_analysis()], [], [])
        assert severity == "warning"

    def test_risk_level_consistency_vacuous_when_no_analyses(self):
        check = self._make_check("risk_level_consistency")
        severity = _detect_vacuous_pass(check, [], [], [])
        assert severity == "warning"

    def test_non_vacuous_checks_always_pass(self):
        """Checks not in the vacuous list always return 'pass'."""
        for name in ["citation_grounding", "date_consistency", "legal_status_consistency"]:
            check = self._make_check(name)
            severity = _detect_vacuous_pass(check, [], [], [])
            assert severity == "pass"


class TestVerifyAnalysisSeverity:
    """Integration test: verify_analysis sets severity correctly."""

    def test_vacuous_checks_get_warning_severity(self, mock_settings):
        """When running with empty DoE/invalidity, those checks should be warnings."""
        analysis = PatentAnalysis(
            patent_id="US7851188B2",
            risk_level=RiskLevel.LOW,
            risk_summary="test",
        )
        hit = PatentHit(
            patent_id="US7851188B2",
            title="test",
            sources=[PatentSource.PUBCHEM],
            confidence_score=0.5,
        )

        result = verify_analysis(
            analyses=[analysis],
            doe_assessments=[],  # Empty — should trigger vacuous warnings
            invalidity_assessments=[],  # Empty — should trigger vacuous warnings
            search_results=[hit],
        )

        # Find specific checks and verify severity
        checks_by_name = {c.check_name: c for c in result.checks}

        assert checks_by_name["doe_consistency"].severity == "warning"
        assert checks_by_name["invalidity_consistency"].severity == "warning"
        assert checks_by_name["claim_chart_consistency"].severity == "warning"
        assert checks_by_name["prosecution_history_consistency"].severity == "warning"

        # These should be regular passes (not vacuous)
        assert checks_by_name["citation_grounding"].severity == "pass"

    def test_failed_checks_get_fail_severity(self, mock_settings):
        """Failed checks should have severity='fail'."""
        # Analysis with hallucinated patent ID
        analysis = PatentAnalysis(
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
        hit = PatentHit(
            patent_id="US7851188B2",
            title="test",
            sources=[PatentSource.PUBCHEM],
            confidence_score=0.5,
        )

        result = verify_analysis(
            analyses=[analysis],
            doe_assessments=[],
            invalidity_assessments=[],
            search_results=[hit],
        )

        checks_by_name = {c.check_name: c for c in result.checks}
        # Citation grounding should fail (hallucinated patent ID)
        assert checks_by_name["citation_grounding"].severity == "fail"
        # Risk consistency should fail (HIGH risk with all NOT_MET)
        assert checks_by_name["risk_level_consistency"].severity == "fail"
