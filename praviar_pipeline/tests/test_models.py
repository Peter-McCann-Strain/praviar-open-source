"""Tests for all Pydantic models — validation, serialization, extra-field rejection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    DesignAroundSuggestion,
    ElementStatus,
    EvaluationIssue,
    RiskLevel,
)
from praviar_pipeline.models.compound import RelatedCompound, ResolvedCompound
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult, FWRAssessment
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityAssessment,
    InvalidityLLMResponse,
    PriorArtReference,
    PTABProceeding,
    PTABResult,
)
from praviar_pipeline.models.patent import LegalStatus, PatentHit, PatentSource
from praviar_pipeline.models.report import (
    AttorneyFeedback,
    ClaimCorrection,
    RiskSummary,
)
from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult

# ---------------------------------------------------------------------------
# Compound models
# ---------------------------------------------------------------------------


class TestResolvedCompound:
    def test_valid_construction(self, succinic_acid: ResolvedCompound):
        assert succinic_acid.name == "succinic acid"
        assert succinic_acid.pubchem_cid == 1110
        assert succinic_acid.input_type == "name"
        assert len(succinic_acid.related_compounds) == 1

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            ResolvedCompound(
                name="test",
                canonical_smiles="C",
                inchi="InChI=1S/CH4/h1H4",
                inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                pubchem_cid=297,
                original_input="test",
                input_type="name",
                bogus_field="should fail",
            )

    def test_related_compound_tanimoto_bounds(self):
        with pytest.raises(ValidationError):
            RelatedCompound(cid=1, canonical_smiles="C", tanimoto_similarity=1.5)

    def test_serialization_roundtrip(self, succinic_acid: ResolvedCompound):
        data = succinic_acid.model_dump(mode="json")
        restored = ResolvedCompound.model_validate(data)
        assert restored.pubchem_cid == succinic_acid.pubchem_cid
        assert restored.canonical_smiles == succinic_acid.canonical_smiles


# ---------------------------------------------------------------------------
# Patent models
# ---------------------------------------------------------------------------


class TestPatentHit:
    def test_valid_construction(self, sample_patent_hit: PatentHit):
        assert sample_patent_hit.patent_id == "US7851188B2"
        assert PatentSource.PUBCHEM in sample_patent_hit.sources

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            PatentHit(patent_id="US0000001", confidence_score=2.0)

    def test_legal_status_enum(self):
        hit = PatentHit(patent_id="US123", legal_status=LegalStatus.EXPIRED)
        assert hit.legal_status == LegalStatus.EXPIRED

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            PatentHit(patent_id="US123", unknown_field="nope")


# ---------------------------------------------------------------------------
# Triage models
# ---------------------------------------------------------------------------


class TestTriageResult:
    def test_valid(self):
        tr = TriageResult(
            patent_id="US123",
            relevance=Relevance.RELEVANT,
            reason="Directly relevant",
            confidence=0.9,
        )
        assert tr.relevance == Relevance.RELEVANT

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            TriageResult(
                patent_id="US123",
                relevance=Relevance.NOT_RELEVANT,
                reason="Not relevant",
                confidence=-0.1,
            )

    def test_triage_batch(self):
        batch = TriageBatch(
            results=[
                TriageResult(patent_id="US1", relevance=Relevance.RELEVANT, reason="yes"),
            ],
            model_used="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        assert len(batch.results) == 1
        assert batch.model_used == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Analysis models
# ---------------------------------------------------------------------------


class TestClaimAnalysis:
    def test_element_status_enum(self):
        assert ElementStatus.MET.value == "met"
        assert ElementStatus.NOT_MET.value == "not_met"

    def test_claim_analysis_construction(
        self, sample_claim_element_met, sample_claim_element_not_met
    ):
        ca = ClaimAnalysis(
            claim_number=1,
            claim_type="independent",
            elements=[sample_claim_element_met, sample_claim_element_not_met],
            overall_status=ElementStatus.NOT_MET,
        )
        assert len(ca.elements) == 2
        assert ca.overall_status == ElementStatus.NOT_MET

    def test_patent_analysis_risk_levels(self, sample_analysis):
        assert sample_analysis.risk_level == RiskLevel.MEDIUM

    def test_design_around_suggestion(self):
        das = DesignAroundSuggestion(
            element_avoided=2,
            suggestion="Use E. coli instead of Mannheimia",
        )
        assert das.element_avoided == 2


# ---------------------------------------------------------------------------
# Equivalents models
# ---------------------------------------------------------------------------


class TestDoEAssessment:
    def test_fwr_all_true_means_equivalent(self):
        fwr = FWRAssessment(
            same_function=True,
            function_reasoning="Same",
            same_way=True,
            way_reasoning="Same",
            same_result=True,
            result_reasoning="Same",
            equivalent=True,
        )
        assert fwr.equivalent is True

    def test_estoppel_defaults(self):
        e = EstoppelResult()
        assert e.estoppel_applies is None
        assert e.file_wrapper_available is False

    def test_doe_overall(self, sample_doe_assessment):
        assert sample_doe_assessment.overall_equivalent is False


# ---------------------------------------------------------------------------
# Invalidity models
# ---------------------------------------------------------------------------


class TestInvalidityModels:
    def test_ptab_result_no_challenge(self, sample_ptab_result):
        assert sample_ptab_result.has_been_challenged is False
        assert len(sample_ptab_result.proceedings) == 0

    def test_ptab_proceeding(self):
        proc = PTABProceeding(
            proceeding_number="IPR2019-00123",
            type="IPR",
            status="Final Written Decision",
            claims_cancelled=[1, 3],
        )
        assert proc.claims_cancelled == [1, 3]

    def test_prior_art_reference(self):
        ref = PriorArtReference(
            reference_id="US5,000,000",
            title="Prior art patent",
            anticipation_score=0.8,
        )
        assert ref.anticipation_score == 0.8

    def test_invalidity_assessment(self, sample_invalidity_assessment):
        assert sample_invalidity_assessment.overall_invalidity_strength == "weak"


# ---------------------------------------------------------------------------
# Verification models
# ---------------------------------------------------------------------------


class TestVerification:
    def test_all_passed_false_with_grounding_gap(self, sample_verification_result):
        # all_claims_grounded is False (honest default), so all_passed is False
        assert sample_verification_result.all_passed is False

    def test_all_passed_false_when_issue(self):
        vr = VerificationResult(
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=False,
            dates_consistent=True,
            risk_levels_justified=True,
            issues=["Invalid SMILES found"],
        )
        assert vr.all_passed is False


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_construction(self, sample_report):
        assert sample_report.report_id == "test-report-001"
        assert sample_report.risk_summary.overall_risk == RiskLevel.MEDIUM

    def test_report_serialization(self, sample_report):
        data = sample_report.model_dump(mode="json")
        assert data["report_id"] == "test-report-001"
        assert "compound" in data
        assert "risk_summary" in data

    def test_attorney_feedback(self):
        fb = AttorneyFeedback(
            report_id="test-001",
            attorney_id="atty-1",
            overall_accuracy=0.85,
            corrections=[
                ClaimCorrection(
                    patent_id="US7851188B2",
                    claim_number=1,
                    original_status="not_met",
                    corrected_status="met",
                    attorney_reasoning="Element is actually met under broad interpretation",
                ),
            ],
        )
        assert fb.overall_accuracy == 0.85
        assert len(fb.corrections) == 1

    def test_risk_summary(self):
        rs = RiskSummary(
            overall_risk=RiskLevel.HIGH,
            blocking_patents_count=3,
            total_patents_analyzed=10,
            key_risks=["Patent A is blocking"],
            executive_summary="High risk identified.",
        )
        assert rs.overall_risk == RiskLevel.HIGH

    def test_risk_summary_validation_issues_default(self):
        rs = RiskSummary(
            overall_risk=RiskLevel.CLEAR,
            executive_summary="No risk.",
        )
        assert rs.summary_validation_issues == []


# ---------------------------------------------------------------------------
# Invalidity LLM response models
# ---------------------------------------------------------------------------


class TestInvalidityLLMResponse:
    def test_valid_construction(self):
        resp = InvalidityLLMResponse(
            arguments=[
                InvalidityArgument(
                    type="anticipation",
                    statute="35 U.S.C. § 102",
                    strength="strong",
                    key_evidence=["Lee et al. (2005)"],
                    reasoning="Prior art discloses all elements",
                ),
            ],
            overall_strength="strong",
            overall_reasoning="Clear anticipation by Lee et al.",
        )
        assert resp.overall_strength == "strong"
        assert len(resp.arguments) == 1

    def test_strength_coercion_unknown_value(self):
        arg = InvalidityArgument(
            type="obviousness",
            strength="unclear",  # Not valid — should coerce to "weak"
            key_evidence=[],
            reasoning="Test",
        )
        assert arg.strength == "weak"

    def test_overall_strength_coercion(self):
        resp = InvalidityLLMResponse(
            arguments=[],
            overall_strength="VERY STRONG",  # Not valid — should coerce to "weak"
            overall_reasoning="Test",
        )
        assert resp.overall_strength == "weak"

    def test_valid_strengths_accepted(self):
        for s in ("weak", "moderate", "strong"):
            arg = InvalidityArgument(
                type="anticipation",
                strength=s,
                key_evidence=[],
                reasoning="Test",
            )
            assert arg.strength == s

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            InvalidityLLMResponse(
                arguments=[],
                overall_strength="weak",
                overall_reasoning="Test",
                bogus_field="should fail",
            )

    def test_written_description_issues_default(self):
        resp = InvalidityLLMResponse(
            arguments=[],
            overall_strength="weak",
            overall_reasoning="No strong arguments",
        )
        assert resp.written_description_issues == []


# ---------------------------------------------------------------------------
# Evaluator models
# ---------------------------------------------------------------------------


class TestEvaluationModels:
    def test_evaluation_issue(self):
        issue = EvaluationIssue(
            issue_type="risk_claim_mismatch",
            description="HIGH risk but no claims met",
            suggested_fix="Change to CLEAR",
            severity="critical",
        )
        assert issue.severity == "critical"

    def test_severity_coercion(self):
        with pytest.raises(ValidationError):
            EvaluationIssue(
                issue_type="risk_claim_mismatch",
                description="Test",
                suggested_fix="Test",
                severity="URGENT",
            )

    def test_analysis_evaluation_good(self):
        ev = AnalysisEvaluation(
            issues=[],
            overall_quality="good",
        )
        assert ev.overall_quality == "good"
        assert ev.revised_risk_level is None

    def test_quality_coercion(self):
        with pytest.raises(ValidationError):
            AnalysisEvaluation(issues=[], overall_quality="terrible")

    def test_with_revised_risk(self):
        ev = AnalysisEvaluation(
            issues=[
                EvaluationIssue(
                    issue_type="risk_claim_mismatch",
                    description="Test",
                    suggested_fix="Test",
                    severity="critical",
                ),
            ],
            overall_quality="needs_revision",
            revised_risk_level="low",
        )
        assert ev.revised_risk_level == RiskLevel.LOW
        assert len(ev.issues) == 1


# ---------------------------------------------------------------------------
# Validator tests for report and analysis models
# ---------------------------------------------------------------------------


class TestTriageCoercion:
    """Tests for _coerce_relevance validator."""

    def test_relevance_case_insensitive(self):
        tr = TriageResult(patent_id="US123", relevance="RELEVANT", reason="test")
        assert tr.relevance == Relevance.RELEVANT

    def test_relevance_lowercase(self):
        tr = TriageResult(patent_id="US123", relevance="not_relevant", reason="test")
        assert tr.relevance == Relevance.NOT_RELEVANT

    def test_relevance_enum_passthrough(self):
        tr = TriageResult(patent_id="US123", relevance=Relevance.POSSIBLY_RELEVANT, reason="test")
        assert tr.relevance == Relevance.POSSIBLY_RELEVANT


class TestFWRConsistencyValidator:
    """Tests for FWRAssessment model_validator."""

    def test_inconsistent_equivalent_corrected(self):
        """If same_function=True, same_way=True, same_result=True but equivalent=False, fix it."""
        fwr = FWRAssessment(
            same_function=True,
            function_reasoning="Same",
            same_way=True,
            way_reasoning="Same",
            same_result=True,
            result_reasoning="Same",
            equivalent=False,  # Should be corrected to True
        )
        assert fwr.equivalent is True

    def test_inconsistent_not_equivalent_corrected(self):
        """If a prong fails but equivalent=True, fix it."""
        fwr = FWRAssessment(
            same_function=True,
            function_reasoning="Same",
            same_way=False,
            way_reasoning="Different",
            same_result=True,
            result_reasoning="Same",
            equivalent=True,  # Should be corrected to False
        )
        assert fwr.equivalent is False


class TestFWRBoolCoercion:
    """Tests for _coerce_bool validator on FWR boolean fields."""

    def test_string_yes_coerced(self):
        fwr = FWRAssessment(
            same_function="yes",
            function_reasoning="test",
            same_way="no",
            way_reasoning="test",
            same_result="true",
            result_reasoning="test",
            equivalent=False,
        )
        assert fwr.same_function is True
        assert fwr.same_way is False
        assert fwr.same_result is True


class TestDoEEstoppelOverride:
    """Tests for DoEAssessment estoppel model_validator."""

    def test_estoppel_forces_not_equivalent(self):
        doe = DoEAssessment(
            patent_id="US123",
            claim_number=1,
            element_number=1,
            element_text="test",
            estoppel=EstoppelResult(
                estoppel_applies=True,
                file_wrapper_available=True,
                surrendered_scope="subject matter outside the amended genus",
            ),
            overall_equivalent=True,  # Should be overridden to False
            reasoning="test",
        )
        assert doe.overall_equivalent is False


class TestInvalidityStrengthCoercion:
    """Tests for _coerce_strength on InvalidityAssessment."""

    def test_valid_strengths_pass(self):
        for s in ("weak", "moderate", "strong"):
            ia = InvalidityAssessment(
                patent_id="US123",
                claim_numbers=[1],
                ptab=PTABResult(),
                overall_invalidity_strength=s,
                reasoning="test",
            )
            assert ia.overall_invalidity_strength == s

    def test_invalid_strength_coerced_to_weak(self):
        ia = InvalidityAssessment(
            patent_id="US123",
            claim_numbers=[1],
            ptab=PTABResult(),
            overall_invalidity_strength="VERY_STRONG",
            reasoning="test",
        )
        assert ia.overall_invalidity_strength == "weak"


class TestVerificationAllPassed:
    """Tests for VerificationResult.all_passed property with checks list."""

    def test_all_passed_with_checks(self):
        vr = VerificationResult(
            checks=[
                VerificationCheck(check_name="test1", passed=True, details="ok"),
                VerificationCheck(check_name="test2", passed=True, details="ok"),
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        )
        assert vr.all_passed is True

    def test_all_passed_false_when_check_fails(self):
        vr = VerificationResult(
            checks=[
                VerificationCheck(check_name="test1", passed=True, details="ok"),
                VerificationCheck(check_name="test2", passed=False, details="fail"),
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        )
        assert vr.all_passed is False


class TestCompoundInputType:
    """Tests for Literal input_type on ResolvedCompound."""

    def test_valid_input_types(self):
        for it in ("name", "smiles", "cas", "inchi", "inchikey"):
            c = ResolvedCompound(
                name="test",
                canonical_smiles="C",
                inchi="InChI=1S/CH4/h1H4",
                inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                pubchem_cid=297,
                original_input="test",
                input_type=it,
            )
            assert c.input_type == it

    def test_invalid_input_type_rejected(self):
        with pytest.raises(ValidationError):
            ResolvedCompound(
                name="test",
                canonical_smiles="C",
                inchi="InChI=1S/CH4/h1H4",
                inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                pubchem_cid=297,
                original_input="test",
                input_type="invalid_type",
            )


class TestInchiKeyValidator:
    """Tests for InChIKey format validation."""

    def test_valid_inchi_key(self):
        c = ResolvedCompound(
            name="test",
            canonical_smiles="C",
            inchi="InChI=1S/CH4/h1H4",
            inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
            pubchem_cid=297,
            original_input="test",
            input_type="name",
        )
        assert c.inchi_key == "VNWKTOKETHGBQD-UHFFFAOYSA-N"

    def test_invalid_inchi_key_rejected(self):
        with pytest.raises(ValidationError, match="InChIKey"):
            ResolvedCompound(
                name="test",
                canonical_smiles="C",
                inchi="InChI=1S/CH4/h1H4",
                inchi_key="invalid-key",
                pubchem_cid=297,
                original_input="test",
                input_type="name",
            )


# ---------------------------------------------------------------------------
# Shared base classes (praviar_pipeline.models._base)
# ---------------------------------------------------------------------------


class TestPatentBase:
    """Behavioural tests for the shared PatentBase fragment.

    These tests cover the contract that every consolidated subclass
    relies on: ``patent_id`` is required, ``jurisdiction`` defaults to
    "", and the default config is ``extra="forbid"``. We test through
    concrete subclasses (TriageResult, PatentEvidenceRecord) so a
    regression in either the base or a subclass surfaces here.
    """

    def test_patent_id_required_via_subclass(self):
        with pytest.raises(ValidationError, match="patent_id"):
            TriageResult(  # type: ignore[call-arg]
                relevance=Relevance.RELEVANT,
                reason="x",
                blocking_potential="y",
            )

    def test_jurisdiction_defaults_to_empty_string(self):
        # PatentEvidenceRecord inherits jurisdiction from PatentBase with default "".
        from praviar_pipeline.models.report_evidence_records import PatentEvidenceRecord

        rec = PatentEvidenceRecord(patent_id="US7851188B2")
        assert rec.jurisdiction == ""

    def test_subclass_extra_forbid_inherited(self):
        # TriageResult does not override extra=, so the inherited "forbid" applies.
        with pytest.raises(ValidationError, match="extra"):
            TriageResult(
                patent_id="US1",
                relevance=Relevance.RELEVANT,
                reason="x",
                blocking_potential="y",
                bogus_field="should fail",  # type: ignore[call-arg]
            )

    def test_governed_patent_analysis_rejects_extra_fields(self):
        from praviar_pipeline.models.analysis import PatentAnalysis

        with pytest.raises(ValidationError, match="extra"):
            PatentAnalysis(
                patent_id="US1",
                risk_level=RiskLevel.LOW,
                risk_summary="ok",
                stray_field="must fail",  # type: ignore[call-arg]
            )


class TestToolDefinition:
    """Tests for the typed ToolDefinition replacement for ad-hoc dicts."""

    def test_construction_and_dump(self):
        from praviar_pipeline.models._base import ToolDefinition

        td = ToolDefinition(
            name="web_search",
            description="Search the web.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        wire = td.model_dump()
        assert wire["name"] == "web_search"
        assert wire["input_schema"]["required"] == ["query"]

    def test_extra_fields_rejected(self):
        from praviar_pipeline.models._base import ToolDefinition

        with pytest.raises(ValidationError, match="extra"):
            ToolDefinition(
                name="t",
                description="d",
                input_schema={},
                extra_field="nope",  # type: ignore[call-arg]
            )
