"""Tests for Step 8: Report Generation shared helpers.

Note: TestGenerateReport (which tested legacy report dispatch logic) was removed
on 2026-05-29 when the old report assembly path was archived. generate_report
now unconditionally delegates to step8_unified_report.
"""

from __future__ import annotations

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.audit import StepTokenUsage
from praviar_pipeline.models.equivalents import EstoppelResult, FWRAssessment
from praviar_pipeline.models.invalidity import (
    InvalidityArgument,
    InvalidityAssessment,
    PriorArtReference,
)
from praviar_pipeline.models.patent import (
    LegalStatus,
    PatentHit,
    PatentSource,
)
from praviar_pipeline.models.report import (
    ActionPriority,
    ActionType,
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.pipeline.step8_report import (
    _aggregate_step_tokens,
    _build_data_limitations,
    _determine_overall_risk,
    _extract_action_items,
    _identify_key_risks,
    _validate_executive_summary,
)
from tests.claim_text_test_helpers import trusted_claim_text_fields
from tests.legal_status_test_helpers import trusted_ops_provenance


def _verified_active_hit(analysis: PatentAnalysis) -> PatentHit:
    claims_text = "authoritative claim text"
    return PatentHit(
        patent_id=analysis.patent_id,
        **trusted_claim_text_fields(analysis.patent_id, claims_text),
        sources=[PatentSource.EPO_SEARCH],
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=analysis.patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_code": "B1",
                    "event_description": "Patent granted and active",
                }
            ],
        ),
    )


def _verified_action_items(
    analyses: list[PatentAnalysis],
    invalidity_assessments: list[InvalidityAssessment],
):
    return _extract_action_items(
        analyses,
        invalidity_assessments,
        patent_hits=[_verified_active_hit(analysis) for analysis in analyses],
        intended_actions=["commercial_launch"],
    )


class TestDetermineOverallRisk:
    def test_high_if_any_high(self, sample_high_risk_analysis):
        risk = _determine_overall_risk([sample_high_risk_analysis], [])
        assert risk == RiskLevel.HIGH

    def test_medium_if_only_medium(self, sample_analysis):
        risk = _determine_overall_risk([sample_analysis], [])
        assert risk == RiskLevel.MEDIUM

    def test_clear_if_no_analyses(self):
        risk = _determine_overall_risk([], [])
        assert risk == RiskLevel.CLEAR

    def test_low_if_primary_source_failed(self):
        """When primary source failed and no analyses, report LOW not CLEAR."""
        health = SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_sdq",
                    status=SourceStatus.FAILED,
                    error_message="down",
                ),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=5),
            ]
        )
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.LOW

    def test_clear_when_primary_succeeded_and_no_risk(self):
        """CLEAR is valid when primary source succeeded and no risky patents found."""
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.CLEAR

    def test_doe_can_upgrade_medium_to_high(self, sample_analysis, sample_doe_assessment):
        """Only a fully supported affirmative DoE record may upgrade MEDIUM."""
        sample_doe_assessment.overall_equivalent = True
        sample_doe_assessment.claim_number = sample_analysis.claims_analyzed[0].claim_number
        sample_doe_assessment.confidence_band = "HIGH"
        sample_doe_assessment.estoppel = EstoppelResult(
            estoppel_applies=False,
            file_wrapper_available=True,
        )
        sample_doe_assessment.fwr = FWRAssessment(
            same_function=True,
            function_reasoning="record-supported",
            same_way=True,
            way_reasoning="record-supported",
            same_result=True,
            result_reasoning="record-supported",
            equivalent=True,
        )
        risk = _determine_overall_risk([sample_analysis], [sample_doe_assessment])
        assert risk == RiskLevel.HIGH


class TestIdentifyKeyRisks:
    def test_returns_high_and_medium(
        self, sample_analysis, sample_high_risk_analysis, mock_settings
    ):
        risks = _identify_key_risks([sample_analysis, sample_high_risk_analysis])
        assert len(risks) == 2

    def test_empty_for_clear(self, mock_settings):
        risks = _identify_key_risks([])
        assert risks == []


# TestGenerateReport was removed 2026-05-29: it tested the legacy report dispatch
# branch in generate_report(), which is permanently dead now that the old report
# assembly path has been archived.


class TestExtractActionItems:
    def test_high_risk_with_design_around(self, sample_high_risk_analysis):
        """Raw design suggestions cannot create mitigation before governance."""
        from praviar_pipeline.models.analysis import DesignAroundSuggestion

        sample_high_risk_analysis.design_around_suggestions = [
            DesignAroundSuggestion(
                element_avoided=1,
                suggestion="Use alternative catalyst",
                feasibility="high",
            ),
        ]
        items = _verified_action_items([sample_high_risk_analysis], [])
        assert [item.action_type for item in items] == [ActionType.MONITOR]

    def test_high_risk_with_invalidity(
        self, sample_high_risk_analysis, sample_invalidity_assessment
    ):
        """IPR advice is withheld until post-report governed reconciliation."""
        sample_invalidity_assessment.patent_id = sample_high_risk_analysis.patent_id
        sample_invalidity_assessment.overall_invalidity_strength = "moderate"
        sample_invalidity_assessment.ipr_prior_art_scope_verified = True
        sample_invalidity_assessment.ipr_timing_verified = True
        sample_invalidity_assessment.ipr_estoppel_and_rpi_verified = True
        sample_invalidity_assessment.ipr_discretionary_denial_reviewed = True
        sample_invalidity_assessment.arguments = [
            InvalidityArgument(
                type="anticipation",
                statute="35 U.S.C. § 102",
                strength="moderate",
                key_evidence=["US20010000001A1"],
                reasoning="Claim-specific screening analysis.",
            )
        ]
        sample_invalidity_assessment.prior_art = [
            PriorArtReference(
                reference_id="US20010000001A1",
                ipr_eligible_printed_publication=True,
                ipr_eligibility_basis="Counsel-verified patent publication.",
            )
        ]
        items = _verified_action_items(
            [sample_high_risk_analysis],
            [sample_invalidity_assessment],
        )
        assert [item.action_type for item in items] == [ActionType.MONITOR]

    def test_invalidity_strength_alone_does_not_recommend_ipr(
        self, sample_high_risk_analysis, sample_invalidity_assessment
    ):
        sample_invalidity_assessment.patent_id = sample_high_risk_analysis.patent_id
        sample_invalidity_assessment.overall_invalidity_strength = "strong"

        items = _verified_action_items(
            [sample_high_risk_analysis],
            [sample_invalidity_assessment],
        )

        assert all(a.action_type != ActionType.CHALLENGE_IPR for a in items)
        assert [item.action_type for item in items] == [ActionType.MONITOR]

    def test_high_risk_no_mitigation(self, sample_high_risk_analysis):
        """Raw HIGH screen cannot name a license route before governance."""
        items = _verified_action_items([sample_high_risk_analysis], [])
        assert [item.action_type for item in items] == [ActionType.MONITOR]

    def test_medium_risk_accept(self, sample_analysis):
        """A MEDIUM screen remains a review/monitor action, not automatic acceptance."""
        from datetime import date

        # Set expiry far enough that MONITOR doesn't trigger
        sample_analysis.expiry_date = date(2040, 1, 1)
        items = _extract_action_items([sample_analysis], [])
        assert any(
            a.action_type == ActionType.MONITOR and a.priority == ActionPriority.MEDIUM
            for a in items
        )
        assert all(a.action_type != ActionType.ACCEPT_RISK for a in items)

    def test_inactive_high_coverage_screen_does_not_recommend_mitigation(
        self, sample_high_risk_analysis
    ):
        patent_id = sample_high_risk_analysis.patent_id
        claims_text = "authoritative claim text"
        hit = PatentHit(
            patent_id=patent_id,
            **trusted_claim_text_fields(patent_id, claims_text),
            sources=[PatentSource.EPO_SEARCH],
            legal_status=LegalStatus.REVOKED,
            legal_status_provenance=trusted_ops_provenance(
                patent_id=patent_id,
                legal_status=LegalStatus.REVOKED,
            ),
        )

        items = _extract_action_items(
            [sample_high_risk_analysis],
            [],
            patent_hits=[hit],
            intended_actions=["commercial_launch"],
        )

        assert [item.action_type for item in items] == [ActionType.MONITOR]
        assert "withheld" in items[0].reasoning.lower()

    def test_empty_analyses(self):
        """No analyses → no action items."""
        items = _extract_action_items([], [])
        assert items == []

    def test_items_sorted_by_priority(self, sample_analysis, sample_high_risk_analysis):
        """Action items are sorted: CRITICAL before HIGH before MEDIUM."""
        items = _extract_action_items(
            [sample_high_risk_analysis, sample_analysis],
            [],
            patent_hits=[_verified_active_hit(sample_high_risk_analysis)],
            intended_actions=["commercial_launch"],
        )
        priorities = [a.priority for a in items]
        priority_order = {
            ActionPriority.CRITICAL: 0,
            ActionPriority.HIGH: 1,
            ActionPriority.MEDIUM: 2,
            ActionPriority.LOW: 3,
        }
        assert priorities == sorted(
            priorities,
            key=lambda p: priority_order.get(p, 4),
        )

    def test_patent_ids_populated(self, sample_high_risk_analysis):
        """Action items have patent_ids from the analysis."""
        items = _verified_action_items([sample_high_risk_analysis], [])
        assert all(sample_high_risk_analysis.patent_id in a.patent_ids for a in items)


class TestValidateExecutiveSummary:
    def _make_analysis(
        self,
        patent_id: str = "US7851188B2",
        risk: RiskLevel = RiskLevel.HIGH,
    ) -> PatentAnalysis:
        return PatentAnalysis(
            patent_id=patent_id,
            title="Test patent",
            assignee="TestCo",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="test element",
                            status=ElementStatus.MET,
                            reasoning="Met",
                            confidence=0.9,
                        ),
                    ],
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.9,
                ),
            ],
            risk_level=risk,
            risk_summary="Test risk summary",
        )

    def test_valid_summary_passes(self, mock_settings):
        analysis = self._make_analysis()
        summary = (
            "This compound presents a HIGH freedom-to-operate risk "
            "based on analysis of 10 patents. "
            "US7851188B2 (TestCo) poses direct infringement risk with all claim elements met. "
            "The patent claims a broad composition that encompasses the target compound. "
            "We recommend commissioning a detailed file wrapper analysis for this patent. "
            "Additional analysis should focus on potential design-around strategies. "
            "The claims are broad enough that alternative formulations should be considered. "
            "A thorough prior art search may reveal invalidating references for the key claims. "
            "Counsel should also consider whether prosecution history estoppel limits the scope. "
            "Overall the patent landscape presents significant but manageable risks. "
            "Next steps should include consultation with a registered patent attorney. "
            "The analysis covers composition claims, method claims, and use claims. "
            "Several dependent claims add further limitations that may narrow exposure. "
        )
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert is_valid
        assert issues == []

    def test_missing_risk_level(self, mock_settings):
        analysis = self._make_analysis()
        summary = (
            "This compound has some patent issues. "
            "US7851188B2 (TestCo) is concerning. "
            "We recommend further analysis. " + "Additional context. " * 20
        )
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert not is_valid
        assert any("risk level" in i.lower() for i in issues)

    def test_hallucinated_patent_id(self, mock_settings):
        analysis = self._make_analysis()
        summary = (
            "This compound presents a HIGH risk. "
            "US7851188B2 (TestCo) and US9999999B2 (FakeCo) pose risk. "
            "We recommend further analysis. " + "Additional context. " * 20
        )
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert not is_valid
        assert any("unknown patent" in i.lower() for i in issues)

    def test_too_short(self, mock_settings):
        analysis = self._make_analysis()
        summary = "HIGH risk. US7851188B2 is blocking. We recommend analysis."
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert not is_valid
        assert any("too short" in i.lower() for i in issues)

    def test_missing_recommendations(self, mock_settings):
        analysis = self._make_analysis()
        summary = (
            "This compound presents a HIGH freedom-to-operate risk. "
            "US7851188B2 (TestCo) poses direct infringement risk. "
            + "The patent claims are broad. "
            * 25
        )
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert not is_valid
        assert any("recommendation" in i.lower() for i in issues)

    def test_missing_high_risk_patent_mention(self, mock_settings):
        analysis = self._make_analysis()
        summary = (
            "This compound presents a HIGH freedom-to-operate risk. "
            "We recommend further analysis of the patent landscape. " + "Additional context. " * 25
        )
        is_valid, issues = _validate_executive_summary(
            summary,
            [analysis],
            RiskLevel.HIGH,
        )
        assert not is_valid
        assert any("US7851188B2" in i for i in issues)


# ── _aggregate_step_tokens ────────────────────────────────────────────────────


class TestAggregateStepTokens:
    def _make_analysis(self, input_tokens=100, output_tokens=50):
        a = PatentAnalysis(
            patent_id="US1234567B2",
            title="Test",
            assignee="Acme",
            risk_level=RiskLevel.LOW,
            risk_summary="Low risk",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return a

    def test_empty_inputs_returns_empty(self):
        result = _aggregate_step_tokens([], [], 0, 0, 0, 0)
        assert result == []

    def test_prior_steps_passed_through(self):
        prior = [
            StepTokenUsage(
                step_name="step3_triage", model_role="triage", input_tokens=200, output_tokens=100
            ),
        ]
        result = _aggregate_step_tokens(prior, [], 0, 0, 0, 0)
        assert len(result) == 1
        assert result[0].step_name == "step3_triage"

    def test_analysis_tokens_added_as_step4(self):
        analysis = self._make_analysis(input_tokens=500, output_tokens=250)
        result = _aggregate_step_tokens([], [analysis], 0, 0, 0, 0)
        assert any(u.step_name == "step4_analyze" for u in result)
        step4 = next(u for u in result if u.step_name == "step4_analyze")
        assert step4.input_tokens == 500
        assert step4.output_tokens == 250
        assert step4.model_role == "deep"

    def test_summary_and_narrative_tokens_added_as_step8(self):
        result = _aggregate_step_tokens(
            [], [], summary_in=300, summary_out=150, narr_in=100, narr_out=50
        )
        step8 = next((u for u in result if u.step_name == "step8_report"), None)
        assert step8 is not None
        assert step8.input_tokens == 400  # 300 + 100
        assert step8.output_tokens == 200  # 150 + 50
        assert step8.model_role == "analysis"

    def test_zero_analysis_tokens_not_added(self):
        result = _aggregate_step_tokens([], [], 0, 0, 0, 0)
        assert not any(u.step_name == "step4_analyze" for u in result)

    def test_zero_report_tokens_not_added(self):
        result = _aggregate_step_tokens([], [], 0, 0, 0, 0)
        assert not any(u.step_name == "step8_report" for u in result)

    def test_multiple_analyses_tokens_summed(self):
        analyses = [
            self._make_analysis(input_tokens=100, output_tokens=50),
            self._make_analysis(input_tokens=200, output_tokens=80),
        ]
        result = _aggregate_step_tokens([], analyses, 0, 0, 0, 0)
        step4 = next(u for u in result if u.step_name == "step4_analyze")
        assert step4.input_tokens == 300
        assert step4.output_tokens == 130


# ── _build_data_limitations ───────────────────────────────────────────────────


class TestBuildDataLimitations:
    def _make_analysis(self, risk_level=RiskLevel.LOW):
        return PatentAnalysis(
            patent_id="US1234567B2",
            title="Test",
            assignee="Acme",
            risk_level=risk_level,
            risk_summary="Test risk",
        )

    def _make_failed_source_health(self, source="BigQuery", error="quota exceeded"):
        entry = SourceHealthEntry(source=source, status=SourceStatus.FAILED, error_message=error)
        sh = SourceHealth(entries=[entry])
        return sh

    def test_no_failures_returns_empty(self):
        sh = SourceHealth()
        result = _build_data_limitations(sh, [], [])
        assert result == []

    def test_failed_source_adds_limitation(self):
        sh = self._make_failed_source_health("BigQuery", "quota exceeded")
        result = _build_data_limitations(sh, [], [])
        assert len(result) == 1
        assert result[0].category == "source_unavailable"
        assert "BigQuery" in result[0].description
        assert "protected diagnostics are available to operators" in result[0].description
        assert "quota exceeded" not in result[0].description

    def test_none_source_health_returns_empty(self):
        result = _build_data_limitations(None, [], [])
        assert result == []

    def test_high_risk_no_invalidity_adds_gap(self):
        analysis = self._make_analysis(RiskLevel.HIGH)
        sh = SourceHealth()
        result = _build_data_limitations(sh, [], [analysis])
        assert any(r.category == "enrichment_gap" for r in result)

    def test_medium_risk_no_invalidity_adds_gap(self):
        analysis = self._make_analysis(RiskLevel.MEDIUM)
        sh = SourceHealth()
        result = _build_data_limitations(sh, [], [analysis])
        assert any(r.category == "enrichment_gap" for r in result)

    def test_low_risk_no_invalidity_no_gap(self):
        analysis = self._make_analysis(RiskLevel.LOW)
        sh = SourceHealth()
        result = _build_data_limitations(sh, [], [analysis])
        assert not any(r.category == "enrichment_gap" for r in result)

    def test_high_risk_with_invalidity_no_gap(self):
        analysis = self._make_analysis(RiskLevel.HIGH)
        inv = InvalidityAssessment(patent_id="US1234567B2")
        sh = SourceHealth()
        result = _build_data_limitations(sh, [inv], [analysis])
        assert not any(r.category == "enrichment_gap" for r in result)

    def test_multiple_failed_sources(self):
        entries = [
            SourceHealthEntry(source="BigQuery", status=SourceStatus.FAILED, error_message="quota"),
            SourceHealthEntry(
                source="SureChEMBL", status=SourceStatus.FAILED, error_message="timeout"
            ),
        ]
        sh = SourceHealth(entries=entries)
        result = _build_data_limitations(sh, [], [])
        assert len(result) == 2
