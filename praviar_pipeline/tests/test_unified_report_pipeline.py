"""Integration tests for Step 8 unified multi-stage agentic report pipeline."""

from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import ReportIntegrityError, SourceUnavailableError
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.patent import (
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
)
from praviar_pipeline.models.regulatory_exclusivity import PTEEntry, RegulatoryExclusivity
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.models.report_sections import (
    ValidationIssue,
    ValidationResult,
    VerificationReport,
)
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.step8_unified_report import generate_unified_report

from .helpers import make_claude_client_mock


def _make_section_text(section_id: str) -> str:
    """Generate plausible section text that references the test patent."""
    disclaimer = " This screening summary does not constitute legal advice."
    base = {
        "executive_summary": (
            "Overall Risk: HIGH\n\n"
            "This FTO analysis for osimertinib identified a HIGH posture. "
            "Patent US10000001B2 (Acme Corp) poses significant risk. "
            "Expires 2030-06-15. " + " ".join(["analysis"] * 100) + disclaimer
        ),
        "key_patents": (
            "### US10000001B2\n"
            "Patent US10000001B2 (Acme Corp) covers the target compound. "
            "Risk level: HIGH risk. Expiry: 2030-06-15. " + " ".join(["detail"] * 80) + disclaimer
        ),
        "damages_injunction": (
            "Damages analysis for US10000001B2 suggests substantial risk. "
            + " ".join(["damages"] * 50)
            + disclaimer
        ),
        "invalidity": (
            "Invalidity analysis for US10000001B2 shows limited prior art. "
            + " ".join(["invalidity"] * 50)
            + disclaimer
        ),
        "recommendations": (
            "We recommend obtaining a license for US10000001B2. "
            + " ".join(["recommend"] * 50)
            + disclaimer
        ),
        "data_quality": (
            "Data quality is sufficient for this analysis. "
            + " ".join(["quality"] * 50)
            + disclaimer
        ),
    }
    return base.get(section_id, f"Section {section_id} content " + " ".join(["word"] * 50))


def _mock_verification_report() -> VerificationReport:
    return VerificationReport(
        total_claims_checked=10,
        claims_correct=10,
        claims_incorrect=0,
        factual_accuracy_rate=1.0,
        overall_assessment="PASS",
    )


def _mock_verification_json() -> str:
    """JSON string representing a passing VerificationReport."""
    vr = _mock_verification_report()
    return _json.dumps(
        {
            "total_claims_checked": vr.total_claims_checked,
            "claims_correct": vr.claims_correct,
            "claims_incorrect": vr.claims_incorrect,
            "claims_unverifiable": 0,
            "factual_accuracy_rate": vr.factual_accuracy_rate,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": vr.overall_assessment,
        }
    )


@pytest.fixture(autouse=True)
def _stub_receipt_bound_verifier_for_pipeline_integration_tests(
    request: pytest.FixtureRequest,
):
    """Keep report orchestration tests independent of verifier unit semantics."""
    if request.node.name == "test_unified_fails_closed_on_failed_verification":
        yield
        return
    with patch(
        "praviar_pipeline.pipeline.report.verification_flow.verify_report",
        new=AsyncMock(
            return_value=(
                _mock_verification_report(),
                2500,
                1000,
            )
        ),
    ):
        yield


def _build_mock_claude():
    """Build a mock ClaudeClient that returns section text and verification."""
    mock_claude = make_claude_client_mock(deep_model="claude-opus-4-6")
    mock_claude.load_prompt.return_value = "You are a report writer."

    # complete_text is called for:
    # - Section generation (6 calls, toolkit=None, system does not contain "JSON extractor")
    # - Phase 1 verification analysis (toolkit is not None)
    # - Phase 2 verification extraction (toolkit=None, system contains "JSON extractor")
    section_call_count = 0

    async def _mock_complete_text(
        *,
        system,
        user,
        model,
        max_tokens,
        toolkit=None,
        effort=None,
        cache_system=False,
        role="unknown",
        **_ignored,
    ):
        nonlocal section_call_count

        # Phase 2 extraction (role="verification_extraction"): return JSON
        if role == "verification_extraction":
            return _mock_verification_json(), {"input_tokens": 500, "output_tokens": 200}

        # Phase 1 analysis (role="verification"): return prose
        if role == "verification":
            return (
                "All claims verified correct. No factual errors found.",
                {"input_tokens": 2000, "output_tokens": 800},
            )

        # Section generation and everything else
        sections_order = [
            "executive_summary",
            "key_patents",
            "damages_injunction",
            "invalidity",
            "recommendations",
            "data_quality",
        ]
        idx = section_call_count % len(sections_order)
        section_call_count += 1
        text = _make_section_text(sections_order[idx])
        return text, {"input_tokens": 1000, "output_tokens": 500}

    mock_claude.complete_text.side_effect = _mock_complete_text
    return mock_claude


@pytest.fixture
def mock_claude():
    return _build_mock_claude()


@pytest.fixture
def sample_analysis():
    return PatentAnalysis(
        patent_id="US10000001B2",
        title="Test Patent",
        assignee="Acme Corp",
        expiry_date=__import__("datetime").date(2030, 6, 15),
        risk_level=RiskLevel.HIGH,
        risk_summary="HIGH risk — covers compound class",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status=ElementStatus.MET,
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="compound of Formula I",
                        status=ElementStatus.MET,
                        reasoning="Target falls within Markush genus",
                    ),
                ],
            ),
        ],
        input_tokens=500,
        output_tokens=300,
    )


@pytest.fixture
def sample_verification():
    return VerificationResult()


class TestV2GeneratesReport:
    async def test_unified_generates_report(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )
        regulatory_exclusivity = RegulatoryExclusivity(
            pte_extensions=[
                PTEEntry(
                    patent_number=sample_analysis.patent_id,
                    product_name="succinic acid",
                    nda_bla_number="NDA-1",
                    extension_days="123",
                    status="granted",
                )
            ],
            data_sources_queried=["pte"],
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                execution_profile="world_class_adaptive",
                total_patents_found=5,
                search_sources=["pubchem"],
                source_health=health,
                regulatory_exclusivity=regulatory_exclusivity,
                prosecution_cache={
                    sample_analysis.patent_id: {
                        "office_actions": "- [CTNF] Non-final office action (2025-01-02)",
                        "amendments": "- [AMND] Amendment after final (2025-03-04)",
                        "office_action_events": [
                            {
                                "document_code": "CTNF",
                                "description": "Non-final office action under 35 U.S.C. 103",
                                "event_date": "2025-01-02",
                                "office_action_type": "non_final_office_action",
                                "rejection_bases": ["103", "prior_art"],
                            }
                        ],
                        "amendment_events": [
                            {
                                "transaction_code": "AMND",
                                "description": "Amendment after final",
                                "event_date": "2025-03-04",
                                "event_type": "after_final_response",
                            }
                        ],
                        "office_action_types": ["non_final_office_action"],
                        "amendment_types": ["after_final_response"],
                        "rejection_bases": ["103", "prior_art"],
                        "estoppel_risk_flags": [
                            "after_final_response_history",
                            "prior_art_rejection_history",
                            "amendment_after_office_action_history",
                        ],
                        "response_after_final_count": 1,
                    }
                },
                patent_hits=[
                    PatentHit(
                        patent_id=sample_analysis.patent_id,
                        title=sample_analysis.title,
                        claims_text="claim text",
                        sources=[PatentSource.PUBCHEM],
                        jurisdiction="US",
                        application_number="12/345678",
                        family=PatentFamily(
                            family_id="fam-v2",
                            members=[
                                PatentFamilyMember(country="US", doc_number="10000001", kind="B2")
                            ],
                        ),
                    )
                ],
            )

        assert report.report_id
        assert report.compound.name == "succinic acid"
        assert not hasattr(report, "pipeline_mode")
        assert not hasattr(report, "analysis_depth")
        assert report.execution_profile == "world_class_adaptive"
        assert report.report_pipeline == "world_class_adaptive"
        assert report.prosecution_dossiers[0].sections_available == [
            "office_actions",
            "amendments",
        ]
        assert report.prosecution_dossiers[0].office_action_events[0].document_code == "CTNF"
        assert report.prosecution_dossiers[0].estoppel_risk_flags == [
            "after_final_response_history",
            "prior_art_rejection_history",
            "amendment_after_office_action_history",
        ]
        assert report.matter_evidence_index.patent_records[0].has_us_file_wrapper_dossier is True
        assert report.matter_evidence_index.patent_records[0].prosecution_dossier_sections == [
            "office_actions",
            "amendments",
        ]
        assert report.matter_evidence_index.material_patent_count == 1
        assert report.matter_evidence_index.patent_records[0].family_id == "fam-v2"
        assert report.regulatory_exclusivity == regulatory_exclusivity


class TestV2SectionsGenerated:
    async def test_unified_sections_generated(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        # Executive summary should contain section content
        assert (
            "FTO" in report.risk_summary.executive_summary
            or "FREEDOM" in report.risk_summary.executive_summary
        )


class TestV2BibliographyPopulated:
    async def test_unified_bibliography_populated(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        assert report.bibliography is not None
        assert len(report.bibliography) >= 1


class TestV2VerificationPopulated:
    async def test_unified_verification_populated(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        assert report.verification_summary is not None
        assert report.verification_summary["overall_assessment"] == "PASS"
        assert report.factual_accuracy_rate == 1.0


class TestV2VerificationFailsClosed:
    async def test_unified_fails_closed_on_failed_verification(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
    ):
        mock_claude = _build_mock_claude()

        # Override complete_text so Phase 2 returns a FAIL JSON — triggers the gate.
        _fail_json = _json.dumps(
            {
                "total_claims_checked": 10,
                "claims_correct": 8,
                "claims_incorrect": 2,
                "claims_unverifiable": 0,
                "factual_accuracy_rate": 0.8,
                "corrections_needed": [],
                "omissions_found": [],
                "overall_assessment": "FAIL",
            }
        )
        section_call_count = 0

        async def _failing_verification_text(
            *,
            system,
            user,
            model,
            max_tokens,
            toolkit=None,
            effort=None,
            cache_system=False,
            role="unknown",
            **_ignored,
        ):
            nonlocal section_call_count
            if role == "verification_extraction":
                return _fail_json, {"input_tokens": 500, "output_tokens": 200}
            if role == "verification":
                return "Analysis done.", {"input_tokens": 2000, "output_tokens": 800}
            sections_order = [
                "executive_summary",
                "key_patents",
                "damages_injunction",
                "invalidity",
                "recommendations",
                "data_quality",
            ]
            idx = section_call_count % len(sections_order)
            section_call_count += 1
            return _make_section_text(sections_order[idx]), {
                "input_tokens": 1000,
                "output_tokens": 500,
            }

        mock_claude.complete_text.side_effect = _failing_verification_text
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            with pytest.raises(ReportIntegrityError, match="verification failed closed"):
                await generate_unified_report(
                    compound=succinic_acid,
                    analyses=[sample_analysis],
                    doe_assessments=[],
                    invalidity_assessments=[],
                    verification=sample_verification,
                    source_health=health,
                )


class TestV2BackwardCompatible:
    async def test_unified_report_metadata(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        # patent_narratives dict should be populated from Key Patents section
        assert isinstance(report.patent_narratives, dict)


class TestV2HandlesSectionFailure:
    async def test_unified_fails_closed_on_section_failure(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
    ):
        """One section failure blocks customer-visible report generation."""
        mock_claude = _build_mock_claude()
        call_count = 0
        sentinel = "section-provider-key-and-customer-claim-sentinel"

        async def _failing_complete_text(
            *,
            system,
            user,
            model,
            max_tokens,
            toolkit=None,
            effort=None,
            cache_system=False,
            **kwargs,
        ):
            del system, user, model, max_tokens, toolkit, effort, cache_system, kwargs
            nonlocal call_count
            call_count += 1
            if call_count == 3:  # Third section fails
                raise RuntimeError(f"LLM call failed: {sentinel}")
            sections_order = [
                "executive_summary",
                "key_patents",
                "damages_injunction",
                "invalidity",
                "recommendations",
                "data_quality",
            ]
            idx = (call_count - 1) % len(sections_order)
            text = _make_section_text(sections_order[idx])
            return text, {"input_tokens": 1000, "output_tokens": 500}

        mock_claude.complete_text.side_effect = _failing_complete_text

        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            with pytest.raises(SourceUnavailableError) as exc_info:
                await generate_unified_report(
                    compound=succinic_acid,
                    analyses=[sample_analysis],
                    doe_assessments=[],
                    invalidity_assessments=[],
                    verification=sample_verification,
                    source_health=health,
                )

        error = exc_info.value
        assert str(error) == "report_section unavailable: section generation failed"
        assert sentinel not in repr(error)
        assert error.__cause__ is None
        assert error.__context__ is None


class TestV2ValidationIssuesLogged:
    async def test_unified_validation_issues_logged(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        # Validation issues are captured in risk_summary
        assert isinstance(report.risk_summary.summary_validation_issues, list)

    async def test_unified_fails_closed_on_residual_error_validation_issue(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        def _error_validator(_sections, _data_store):
            return [
                ValidationResult(
                    validator_name="risk-check",
                    passed=False,
                    issues=[
                        ValidationIssue(
                            validator_name="risk-check",
                            severity="error",
                            section_id="executive_summary",
                            description="Missing HIGH risk patent from summary.",
                        )
                    ],
                )
            ]

        with (
            patch(
                "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
                return_value=mock_claude,
            ),
            patch(
                "praviar_pipeline.pipeline.step8_unified_report.run_deterministic_validators",
                side_effect=_error_validator,
            ),
        ):
            with pytest.raises(ReportIntegrityError, match="validation failed closed"):
                await generate_unified_report(
                    compound=succinic_acid,
                    analyses=[sample_analysis],
                    doe_assessments=[],
                    invalidity_assessments=[],
                    verification=sample_verification,
                    source_health=health,
                )


class TestV2TokenTracking:
    async def test_unified_token_tracking(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        # Should have section tokens + verification tokens
        assert report.total_input_tokens > 0
        assert report.total_output_tokens > 0


class TestV2CostComputation:
    async def test_unified_cost_computation(
        self,
        succinic_acid,
        sample_analysis,
        sample_verification,
        mock_settings,
        mock_claude,
    ):
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            ]
        )

        with patch(
            "praviar_pipeline.pipeline.step8_unified_report.ClaudeClient",
            return_value=mock_claude,
        ):
            report = await generate_unified_report(
                compound=succinic_acid,
                analyses=[sample_analysis],
                doe_assessments=[],
                invalidity_assessments=[],
                verification=sample_verification,
                source_health=health,
            )

        # estimated_cost should be computed
        assert report.estimated_cost_usd >= 0.0
