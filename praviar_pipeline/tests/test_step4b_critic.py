"""Tests for Step 4.5: Critic/Reviewer Agent — portfolio-level quality review."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    DesignAroundSuggestion,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.critic import (
    CriticFinding,
    CriticIssueSeverity,
    CriticIssueType,
    CriticReport,
)
from praviar_pipeline.models.reasoning import ReasoningTrace
from praviar_pipeline.models.report import FTOReport, RiskSummary

from .helpers import make_claude_client_mock

# ── Model validation tests ──────────────────────────────────────────────────


class TestCriticFinding:
    def test_valid_construction(self):
        finding = CriticFinding(
            issue_type=CriticIssueType.RISK_CLAIM_MISMATCH,
            patent_id="US7851188B2",
            severity=CriticIssueSeverity.CRITICAL,
            description="HIGH risk but most elements are PARTIALLY_MET",
            suggested_correction="Consider downgrading to MEDIUM",
            claim_numbers=[1, 3],
            related_patent_ids=["US8888888B2"],
        )
        assert finding.issue_type == CriticIssueType.RISK_CLAIM_MISMATCH
        assert finding.severity == CriticIssueSeverity.CRITICAL
        assert finding.claim_numbers == [1, 3]

    def test_issue_type_coercion_valid(self):
        """Standard issue types should pass through."""
        finding = CriticFinding(
            issue_type="risk_claim_mismatch",
            patent_id="US1234",
            severity="major",
            description="test",
        )
        assert finding.issue_type == CriticIssueType.RISK_CLAIM_MISMATCH

    def test_issue_type_coercion_whitespace(self):
        """Whitespace and dashes should be normalized."""
        finding = CriticFinding(
            issue_type="  Risk-Claim-Mismatch  ",
            patent_id="US1234",
            severity="major",
            description="test",
        )
        assert finding.issue_type == CriticIssueType.RISK_CLAIM_MISMATCH

    def test_issue_type_coercion_unknown(self):
        """Unknown issue types must not invent an internal inconsistency."""
        with pytest.raises(ValidationError):
            CriticFinding(
                issue_type="totally_unknown_type",
                patent_id="US1234",
                severity="minor",
                description="test",
            )

    def test_severity_coercion_valid(self):
        finding = CriticFinding(
            issue_type="missing_limitation",
            patent_id="US1234",
            severity="CRITICAL",
            description="test",
        )
        assert finding.severity == CriticIssueSeverity.CRITICAL

    def test_severity_coercion_unknown(self):
        """Unknown severity must not be downgraded to minor."""
        with pytest.raises(ValidationError):
            CriticFinding(
                issue_type="missing_limitation",
                patent_id="US1234",
                severity="catastrophic",
                description="test",
            )

    def test_defaults(self):
        finding = CriticFinding(
            issue_type="confidence_calibration",
            patent_id="US1234",
            severity="info",
            description="test",
        )
        assert finding.suggested_correction == ""
        assert finding.claim_numbers == []
        assert finding.related_patent_ids == []


class TestCriticReport:
    def test_valid_construction(self):
        report = CriticReport(
            findings=[
                CriticFinding(
                    issue_type="risk_claim_mismatch",
                    patent_id="US1234",
                    severity="critical",
                    description="test",
                ),
            ],
            patents_reviewed=5,
            patents_flagged_for_revision=["US1234"],
            overall_quality_score=0.65,
            portfolio_level_observations=["Small portfolio"],
        )
        assert len(report.findings) == 1
        assert report.patents_reviewed == 5
        assert report.overall_quality_score == 0.65

    def test_quality_score_rejected_above(self):
        with pytest.raises(ValidationError):
            CriticReport(overall_quality_score=1.5)

    def test_quality_score_rejected_below(self):
        with pytest.raises(ValidationError):
            CriticReport(overall_quality_score=-0.3)

    def test_quality_score_non_numeric(self):
        with pytest.raises(ValidationError):
            CriticReport(overall_quality_score="not_a_number")

    def test_defaults(self):
        report = CriticReport()
        assert report.findings == []
        assert report.patents_reviewed == 0
        assert report.patents_flagged_for_revision == []
        assert report.overall_quality_score == 0.0
        assert report.portfolio_level_observations == []
        assert report.input_tokens == 0
        assert report.output_tokens == 0

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CriticReport(
                overall_quality_score=0.8,
                extra_field_not_in_schema="should be rejected",
            )


# ── Portfolio summary formatting tests ───────────────────────────────────────


class TestFormatPortfolioSummary:
    def test_empty_analyses(self):
        from praviar_pipeline.pipeline.step4b_critic import _format_portfolio_summary

        result = _format_portfolio_summary([])
        assert result == ""

    def test_single_analysis(self, sample_analysis):
        from praviar_pipeline.pipeline.step4b_critic import _format_portfolio_summary

        result = _format_portfolio_summary([sample_analysis])
        assert "BioAmber Inc." in result
        assert "US7851188B2" in result
        assert "MEDIUM" in result
        assert "Claim 1" in result

    def test_groups_by_assignee(self, sample_analysis, sample_high_risk_analysis):
        from praviar_pipeline.pipeline.step4b_critic import _format_portfolio_summary

        result = _format_portfolio_summary([sample_analysis, sample_high_risk_analysis])
        assert "BioAmber Inc." in result
        assert "GreenChem Corp" in result
        assert "1 patents" in result  # Each assignee has 1

    def test_design_around_included(self):
        from praviar_pipeline.pipeline.step4b_critic import _format_portfolio_summary

        analysis = PatentAnalysis(
            patent_id="US9999999B2",
            title="Test Patent",
            assignee="TestCo",
            risk_level=RiskLevel.HIGH,
            risk_summary="All elements met",
            claims_analyzed=[],
            design_around_suggestions=[
                DesignAroundSuggestion(
                    element_avoided=1,
                    suggestion="Replace hydroxyl group with methyl ether",
                    feasibility="Chemically viable",
                ),
            ],
        )
        result = _format_portfolio_summary([analysis])
        assert "Design-arounds:" in result
        assert "Replace hydroxyl" in result

    def test_unknown_assignee(self):
        from praviar_pipeline.pipeline.step4b_critic import _format_portfolio_summary

        analysis = PatentAnalysis(
            patent_id="US1111111B2",
            title="Test",
            assignee="",  # Empty assignee
            risk_level=RiskLevel.LOW,
            risk_summary="Low risk",
            claims_analyzed=[],
        )
        result = _format_portfolio_summary([analysis])
        assert "Unknown" in result


# ── Pipeline integration tests ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestReviewAnalysesEmpty:
    async def test_empty_analyses_returns_default(self, succinic_acid):
        from praviar_pipeline.pipeline.step4b_critic import review_analyses

        report, in_tok, out_tok = await review_analyses([], succinic_acid)
        assert report.patents_reviewed == 0
        assert report.overall_quality_score == 1.0
        assert in_tok == 0
        assert out_tok == 0


@pytest.mark.asyncio
class TestReviewAnalysesCompact:
    async def test_compact_portfolio_review_calls_complete(
        self,
        succinic_acid,
        sample_analysis,
        mock_settings,
    ):
        from praviar_pipeline.pipeline.step4b_critic import review_analyses

        mock_report = CriticReport(
            findings=[
                CriticFinding(
                    issue_type="risk_claim_mismatch",
                    patent_id="US7851188B2",
                    severity="major",
                    description="Risk may be underrated",
                ),
            ],
            overall_quality_score=0.75,
            patents_flagged_for_revision=["US7851188B2"],
            portfolio_level_observations=["Small portfolio with one patent"],
        )

        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "You are a senior patent attorney..."
        mock_claude.complete.return_value = (
            mock_report,
            {"input_tokens": 1000, "output_tokens": 500},
        )

        with patch(
            "praviar_pipeline.pipeline.step4b_critic.ClaudeClient",
            return_value=mock_claude,
        ):
            report, in_tok, out_tok = await review_analyses(
                [sample_analysis],
                succinic_acid,
            )

        assert report.patents_reviewed == 1
        assert len(report.findings) == 1
        assert report.findings[0].patent_id == "US7851188B2"
        assert report.overall_quality_score == 0.75
        assert in_tok == 1000
        assert out_tok == 500
        mock_claude.complete.assert_called_once()

    async def test_compact_portfolio_review_loads_critic_prompt(
        self,
        succinic_acid,
        sample_analysis,
        mock_settings,
    ):
        from praviar_pipeline.pipeline.step4b_critic import review_analyses

        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt.return_value = "critic system prompt"
        mock_claude.complete.return_value = (
            CriticReport(overall_quality_score=0.9),
            {"input_tokens": 100, "output_tokens": 50},
        )

        with patch(
            "praviar_pipeline.pipeline.step4b_critic.ClaudeClient",
            return_value=mock_claude,
        ):
            await review_analyses([sample_analysis], succinic_acid)

        mock_claude.load_prompt.assert_called_with("critic_system.txt")


@pytest.mark.asyncio
class TestReviewAnalysesAgentic:
    async def test_escalated_portfolio_uses_critic_agent(
        self,
        succinic_acid,
        sample_analysis,
        mock_settings,
    ):
        from praviar_pipeline.pipeline.step4b_critic import review_analyses

        escalated_analysis = sample_analysis.model_copy(
            update={
                "analysis_escalated": True,
                "analysis_escalation_reasons": ["high_risk_triage"],
            }
        )

        mock_trace = ReasoningTrace(
            agent_type="critic",
            model="claude-sonnet-4-6",
            total_input_tokens=2000,
            total_output_tokens=1000,
        )

        mock_report = CriticReport(
            findings=[
                CriticFinding(
                    issue_type="confidence_calibration",
                    patent_id="US7851188B2",
                    severity="minor",
                    description="Confidence seems high",
                ),
            ],
            overall_quality_score=0.85,
        )

        mock_claude = make_claude_client_mock()
        mock_claude.load_prompt = MagicMock(return_value="You are a senior patent attorney...")
        # complete is used to extract structured report from agent text output
        mock_claude.complete.return_value = (
            mock_report,
            {"input_tokens": 200, "output_tokens": 100},
        )

        with (
            patch(
                "praviar_pipeline.pipeline.step4b_critic.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.agents.critic.CriticAgent",
            ) as mock_agent_cls,
        ):
            mock_agent = AsyncMock()
            mock_agent.research.return_value = (
                "Review findings: confidence seems high on US7851188B2",
                mock_trace,
            )
            mock_agent_cls.return_value = mock_agent

            report, in_tok, out_tok = await review_analyses(
                [escalated_analysis],
                succinic_acid,
            )

        assert report.patents_reviewed == 1
        assert len(report.findings) == 1
        # Token counts should include both agent and extraction call
        assert in_tok == 2200  # 2000 agent + 200 extraction
        assert out_tok == 1100  # 1000 agent + 100 extraction
        mock_agent.research.assert_called_once()


# ── CriticAgent unit tests ──────────────────────────────────────────────────


class TestCriticAgent:
    def test_agent_properties(self, mock_settings):
        from praviar_pipeline.agents.critic import CriticAgent

        mock_claude = MagicMock()
        agent = CriticAgent(mock_claude)

        assert agent.agent_type == "critic"
        assert agent.max_rounds == 3
        assert agent.prompt_file == "critic_agent_system.txt"

    def test_build_toolkit_with_data(self, mock_settings):
        from praviar_pipeline.agents.critic import CriticAgent

        mock_claude = MagicMock()
        agent = CriticAgent(mock_claude)

        context = {
            "patent_data": {
                "US1234": {"title": "Test Patent", "assignee": "TestCo"},
            },
        }
        toolkit = agent.build_toolkit(context)
        assert toolkit is not None
        # Should have get_current_date and lookup_patent tools
        tool_names = [t["name"] for t in toolkit.tool_definitions]
        assert "get_current_date" in tool_names
        assert "lookup_patent" in tool_names

    def test_build_toolkit_without_data(self, mock_settings):
        from praviar_pipeline.agents.critic import CriticAgent

        mock_claude = MagicMock()
        agent = CriticAgent(mock_claude)

        toolkit = agent.build_toolkit({"patent_data": {}})
        assert toolkit is None

    def test_format_task(self, mock_settings):
        from praviar_pipeline.agents.critic import CriticAgent

        mock_claude = MagicMock()
        agent = CriticAgent(mock_claude)

        context = {
            "compound_context": "Succinic acid (OC(=O)CCC(O)=O)",
            "portfolio_summary": "## Assignee: BioAmber\n### US1234: Test",
        }
        result = agent.format_task("Review all analyses", context)
        assert "Review all analyses" in result
        assert 'type="compound_context"' in result
        assert "Succinic acid" in result
        assert 'type="prior_model_portfolio_analyses"' in result
        assert "BioAmber" in result
        assert "cross-patent consistency" in result


# ── FTOReport integration tests ─────────────────────────────────────────────


class TestCriticReportInFTOReport:
    def test_report_with_critic_fields(self, succinic_acid, sample_analysis):
        """CriticReport and review_issues should be valid FTOReport fields."""
        critic = CriticReport(
            findings=[
                CriticFinding(
                    issue_type="risk_claim_mismatch",
                    patent_id="US7851188B2",
                    severity="major",
                    description="Test issue",
                ),
            ],
            patents_reviewed=1,
            overall_quality_score=0.8,
        )

        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.MEDIUM,
                blocking_patents_count=1,
                total_patents_analyzed=1,
                key_risks=["US7851188B2: medium risk"],
                executive_summary="Moderate FTO risk.",
            ),
            patent_analyses=[sample_analysis],
            critic_report=critic,
            review_issues=critic.findings,
            total_patents_found=3,
            patents_after_triage=1,
        )

        assert report.critic_report is not None
        assert report.critic_report.overall_quality_score == 0.8
        assert len(report.review_issues) == 1
        assert report.review_issues[0].patent_id == "US7851188B2"

    def test_report_without_critic_fields(self, succinic_acid, sample_analysis):
        """FTOReport should work without critic fields (backward compat)."""
        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.MEDIUM,
                blocking_patents_count=1,
                total_patents_analyzed=1,
                key_risks=["US7851188B2: medium risk"],
                executive_summary="Moderate FTO risk.",
            ),
            patent_analyses=[sample_analysis],
            total_patents_found=3,
            patents_after_triage=1,
        )

        assert report.critic_report is None
        assert report.review_issues == []

    def test_report_serialization_roundtrip(self, succinic_acid, sample_analysis):
        """CriticReport should survive JSON serialization."""
        critic = CriticReport(
            findings=[
                CriticFinding(
                    issue_type="cross_patent_inconsistency",
                    patent_id="US7851188B2",
                    severity="critical",
                    description="Inconsistent logic",
                    related_patent_ids=["US8888888B2"],
                ),
            ],
            patents_reviewed=2,
            overall_quality_score=0.5,
        )

        report = FTOReport(
            compound=succinic_acid,
            risk_summary=RiskSummary(
                overall_risk=RiskLevel.MEDIUM,
                blocking_patents_count=1,
                total_patents_analyzed=1,
                key_risks=["US7851188B2: medium risk"],
                executive_summary="Moderate FTO risk.",
            ),
            patent_analyses=[sample_analysis],
            critic_report=critic,
            review_issues=critic.findings,
            total_patents_found=3,
            patents_after_triage=1,
        )

        data = report.model_dump(mode="json")
        assert data["critic_report"]["overall_quality_score"] == 0.5
        assert len(data["review_issues"]) == 1
        assert data["review_issues"][0]["issue_type"] == "cross_patent_inconsistency"


# ── Cross-patent consistency scenario tests ──────────────────────────────────


class TestCrossPatentScenarios:
    def test_same_assignee_different_risk_detected(self):
        """Two patents from same assignee with inconsistent risk logic should be flaggable."""
        [
            PatentAnalysis(
                patent_id="US1111111B2",
                title="Compound A Process",
                assignee="AcmePharma",
                risk_level=RiskLevel.HIGH,
                risk_summary="All elements met",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="a compound of formula I",
                                status=ElementStatus.MET,
                                reasoning="Direct structural match",
                                confidence=0.95,
                            ),
                        ],
                        overall_status=ElementStatus.MET,
                        overall_confidence=0.95,
                    ),
                ],
            ),
            PatentAnalysis(
                patent_id="US2222222B2",
                title="Compound A Formulation",
                assignee="AcmePharma",
                risk_level=RiskLevel.LOW,
                risk_summary="Elements not fully met",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        elements=[
                            ClaimElement(
                                element_number=1,
                                element_text="a compound of formula I",
                                status=ElementStatus.MET,
                                reasoning="Same structural match as related patent",
                                confidence=0.95,
                            ),
                        ],
                        overall_status=ElementStatus.MET,
                        overall_confidence=0.95,
                    ),
                ],
            ),
        ]

        # Both patents from AcmePharma have the same element status (MET)
        # but different risk levels. This is an inconsistency the critic should catch.
        # The finding below represents what the critic LLM would produce.
        finding = CriticFinding(
            issue_type=CriticIssueType.ASSIGNEE_LOGIC_INCONSISTENCY,
            patent_id="US2222222B2",
            severity=CriticIssueSeverity.MAJOR,
            description=(
                "US2222222B2 has same claim element met as US1111111B2 (same assignee) "
                "but rated LOW vs HIGH risk — inconsistent logic"
            ),
            related_patent_ids=["US1111111B2"],
        )
        assert finding.issue_type == CriticIssueType.ASSIGNEE_LOGIC_INCONSISTENCY
        assert "US1111111B2" in finding.related_patent_ids

    def test_expired_patent_high_risk_is_critical(self):
        """An expired patent rated HIGH risk should be a CRITICAL finding."""
        finding = CriticFinding(
            issue_type=CriticIssueType.RISK_CLAIM_MISMATCH,
            patent_id="US6265190B1",
            severity=CriticIssueSeverity.CRITICAL,
            description="Patent expired 2019 but rated HIGH risk — should be CLEAR",
            suggested_correction="Change risk level to CLEAR for expired patents",
        )
        assert finding.severity == CriticIssueSeverity.CRITICAL


# ── Config settings tests ────────────────────────────────────────────────────


class TestCriticConfig:
    def test_critic_defaults(self, mock_settings):
        from praviar_pipeline.config import get_settings

        settings = get_settings()
        assert settings.critic_enabled is True
        assert settings.critic_max_tokens == 16384
        assert settings.critic_reanalysis_enabled is False
        assert settings.critic_reanalysis_max_patents == 3

    def test_critic_reanalysis_max_patents_bounds(self, mock_settings):
        """critic_reanalysis_max_patents must be between 0 and 5."""
        from praviar_pipeline.config import Settings

        # Valid range
        s = Settings(
            anthropic_api_key="sk-ant-test-key",
            patentsview_api_key="test",
            uspto_odp_api_key="test",
            critic_reanalysis_max_patents=5,
        )
        assert s.critic_reanalysis_max_patents == 5

        # Below range should fail
        with pytest.raises(ValidationError):
            Settings(
                anthropic_api_key="sk-ant-test-key",
                patentsview_api_key="test",
                uspto_odp_api_key="test",
                critic_reanalysis_max_patents=-1,
            )


# ── Prompt file existence tests ──────────────────────────────────────────────


class TestPromptFiles:
    def test_critic_system_prompt_exists(self):
        from pathlib import Path

        prompts_dir = (
            Path(__file__).resolve().parent.parent / "src" / "praviar_pipeline" / "prompts"
        )
        assert (prompts_dir / "critic_system.txt").exists()
        content = (prompts_dir / "critic_system.txt").read_text()
        assert "portfolio" in content.lower()
        assert "cross-patent" in content.lower()
        assert len(content) > 500  # Should be substantial

    def test_critic_agent_system_prompt_exists(self):
        from pathlib import Path

        prompts_dir = (
            Path(__file__).resolve().parent.parent / "src" / "praviar_pipeline" / "prompts"
        )
        assert (prompts_dir / "critic_agent_system.txt").exists()
        content = (prompts_dir / "critic_agent_system.txt").read_text()
        assert "lookup_patent" in content
        assert "multi-turn" in content.lower() or "research" in content.lower()
        assert len(content) > 500


# ── All issue types and severities are valid ─────────────────────────────────


class TestEnumCompleteness:
    def test_all_issue_types_constructable(self):
        for issue_type in CriticIssueType:
            finding = CriticFinding(
                issue_type=issue_type,
                patent_id="US0000000",
                severity=CriticIssueSeverity.INFO,
                description=f"Test {issue_type.value}",
            )
            assert finding.issue_type == issue_type

    def test_all_severities_constructable(self):
        for severity in CriticIssueSeverity:
            finding = CriticFinding(
                issue_type=CriticIssueType.INTERNAL_INCONSISTENCY,
                patent_id="US0000000",
                severity=severity,
                description=f"Test {severity.value}",
            )
            assert finding.severity == severity
