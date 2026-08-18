from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from praviar_pipeline.certification_policy import CertificationPolicySnapshot
from praviar_pipeline.certification_receipt import CertifiedLane, VerifiedCertificationReceipt
from praviar_pipeline.clients.primary_legal_status import (
    build_primary_legal_status_receipt,
)
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.critic import CriticFinding, CriticIssueSeverity, CriticReport
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult, FWRAssessment
from praviar_pipeline.models.invalidity import InvalidityAssessment
from praviar_pipeline.models.patent import (
    LegalEvent,
    LegalStatus,
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
    PatentTermInfo,
    PTABProceeding,
    TransactionEvent,
)
from praviar_pipeline.models.report import (
    AnalysisFailure,
    DataLimitation,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    FTOReport,
    MatterEdge,
    MatterEdgeType,
    MatterGraph,
    MatterGraphSummary,
    MatterNode,
    MatterNodeType,
    RiskSummary,
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.models.search_loop import SearchLoopResult
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.pipeline.analysis.context_binding import analysis_context_sha256
from praviar_pipeline.pipeline.runtime.decisioning import build_clearance_outputs
from praviar_pipeline.pipeline.runtime.decisioning_metrics import build_scope_contract
from praviar_pipeline.pipeline.runtime.decisioning_outputs import build_claim_program_summary
from praviar_pipeline.pipeline.runtime.decisioning_references import build_decisive_references
from praviar_pipeline.pipeline.runtime.evidence_claims import (
    legal_status_decision_state,
)
from tests.claim_text_test_helpers import trusted_claim_text_fields
from tests.legal_status_test_helpers import (
    trusted_ops_provenance,
    trusted_register_provenance,
)

_PRIMARY_STATUS_KEY = b"runtime-primary-status-fixture-key"


class _PrimaryStatusKeyring:
    def verification_key(self, key_id: str) -> bytes:
        if key_id != "runtime-primary":
            raise ValueError("unknown fixture key")
        return _PRIMARY_STATUS_KEY


_PRIMARY_STATUS_KEYRING = _PrimaryStatusKeyring()


def _primary_status_artifact(
    patent_id: str,
    spec: dict[str, object],
) -> bytes:
    payload = {
        "schema_version": ("primary-legal-status-canonical-artifact-v1"),
        "source": spec["source"],
        "evidence_scope": spec["evidence_scope"],
        "source_record_identifier": spec["source_record_identifier"],
        "source_record_patent_number": patent_id,
        "application_number": ("16123456" if spec["source"] == "uspto_odp_application" else ""),
        "target_jurisdiction": "",
        "raw_status": spec["raw_status"],
    }
    for field_name in (
        "term_end_date",
        "term_basis_document_ids",
        "effective_claim_ids",
        "current_claim_text_sha256",
        "controlling_claim_document_ids",
        "affected_claim_ids",
        "adjudication_document_id",
    ):
        if field_name in spec:
            value = spec[field_name]
            payload[field_name] = value.isoformat() if isinstance(value, date) else value
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _primary_status_fields(
    patent_id: str,
    *,
    maintenance_outcome: str = "paid",
    claims_text: str = "1. claim text",
    term_end_date: date = date(2035, 1, 1),
) -> dict:
    common = {
        "patent_id": patent_id,
        "collected_at": datetime.now(UTC),
        "artifact_media_type": "application/json",
        "limitations": ["Fixture exact official-record outcome."],
        "attestation_key_id": "runtime-primary",
        "attestation_key": _PRIMARY_STATUS_KEY,
    }
    receipt_specs = [
        {
            "source": "uspto_odp_application",
            "evidence_scope": "application_prosecution",
            "collection_mode": "api",
            "source_url": "https://api.uspto.gov/api/v1/patent/applications/16123456",
            "source_record_identifier": "16123456",
            "raw_status": "Patented Case",
            "normalized_outcome": "patented",
            "parser_identity": "uspto-odp-application-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "patent_term",
            "collection_mode": "api",
            "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456/adjustment"),
            "source_record_identifier": "16123456",
            "raw_status": "Current term",
            "normalized_outcome": "term_current",
            "parser_identity": "uspto-odp-application-v1",
            "term_end_date": term_end_date,
            "term_basis_document_ids": [f"{patent_id}:grant-and-adjustment"],
        },
        {
            "source": "uspto_maintenance_storefront",
            "evidence_scope": "patent_maintenance",
            "collection_mode": "supervised_manual",
            "source_url": "https://fees.uspto.gov/MaintenanceFees",
            "source_record_identifier": f"{patent_id}:maintenance",
            "raw_status": {
                "paid": "Maintenance fee paid",
                "not_applicable": "Maintenance fees not applicable",
            }[maintenance_outcome],
            "normalized_outcome": maintenance_outcome,
            "parser_identity": "supervised-uspto-maintenance-v1",
        },
        {
            "source": "uspto_odp_ptab",
            "evidence_scope": "post_grant_proceeding",
            "collection_mode": "api",
            "source_url": ("https://api.uspto.gov/api/v1/patent/trials/proceedings/search"),
            "source_record_identifier": f"{patent_id}:ptab",
            "raw_status": "No proceeding found",
            "normalized_outcome": "none_found",
            "parser_identity": "uspto-odp-ptab-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "current_claim_set",
            "collection_mode": "api",
            "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456/documents"),
            "source_record_identifier": "16123456",
            "raw_status": "Current issued claims verified",
            "normalized_outcome": "claims_current",
            "parser_identity": "uspto-odp-application-v1",
            "effective_claim_ids": ["1"],
            "current_claim_text_sha256": hashlib.sha256(claims_text.encode("utf-8")).hexdigest(),
            "controlling_claim_document_ids": [f"{patent_id}:grant-claims"],
        },
    ]
    receipts = [
        build_primary_legal_status_receipt(
            **common,
            **spec,
            parser_result="conclusive",
            artifact=_primary_status_artifact(patent_id, spec),
        ).model_dump(mode="json")
        for spec in receipt_specs
    ]
    return {"primary_legal_status_receipts": receipts}


def _planned_sale_context(jurisdiction: str = "US") -> dict[str, object]:
    start_date = (date.today() + timedelta(days=365)).isoformat()
    return {
        "commercial_territories": [jurisdiction],
        "accused_acts": [
            {
                "act": "sale",
                "jurisdiction": jurisdiction,
                "start_date": start_date,
                "actor": "Praviar Pharma Ltd",
                "status": "planned",
                "purpose": "commercial",
                "regulatory_path": "none",
                "instrumentality": "The analyzed product",
                "liability_theory": "direct",
            }
        ],
    }


@pytest.fixture(autouse=True)
def _verified_release_certification(monkeypatch) -> None:
    """Exercise decision logic under an explicitly verified release receipt."""
    policy = CertificationPolicySnapshot(
        version="test-release-receipt",
        certified_modalities=("small_molecule", "formulation", "process_or_synthesis"),
        certified_matter_types=("small_molecule", "formulation", "process"),
        certified_decision_jurisdictions=("US", "EP"),
        certified_asset_classes=("compound", "formulation", "process"),
        supported_jurisdictions=("US", "EP", "UK", "IN", "JP", "CN"),
        counsel_certification_matrix={
            "small_molecule": ("US", "EP"),
            "formulation": ("US", "EP"),
            "process_or_synthesis": ("US", "EP"),
        },
    )
    receipt = VerifiedCertificationReceipt(
        verified=True,
        failures=(),
        receipt_id="test-release-receipt",
        receipt_sha256="a" * 64,
        pipeline_git_sha="b" * 40,
        source_tree_sha256="c" * 64,
        expires_at="2099-01-01T00:00:00Z",
        issuer_verifier_id="test-verifier",
        key_id="test-key",
        gate_run_id="test-gate-run",
        benchmark_aggregate_sha256="d" * 64,
        certified_lanes=tuple(
            CertifiedLane(
                lane_id=f"{jurisdiction.lower()}-{matter_type}",
                matter_type=matter_type,
                asset_class=asset_class,
                jurisdiction=jurisdiction,
                execution_profile="adaptive",
                required_record_components_sha256="e" * 64,
            )
            for matter_type, asset_class in (
                ("small_molecule", "compound"),
                ("formulation", "formulation"),
                ("process", "process"),
            )
            for jurisdiction in ("US", "EP")
        ),
        policy=policy,
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.decisioning_metrics.verify_certification_receipt",
        lambda settings: receipt,
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.decisioning_metrics._required_record_components_sha256",
        lambda settings, coverage_context: "e" * 64,
    )


def _make_compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="aspirin",
        original_input="aspirin",
        input_type="name",
    )


def test_scope_contract_fails_closed_without_verified_release_receipt(monkeypatch) -> None:
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.decisioning_metrics.verify_certification_receipt",
        lambda settings: VerifiedCertificationReceipt(
            verified=False,
            failures=("certification_release_receipt_missing",),
        ),
    )
    report = SimpleNamespace(compound=SimpleNamespace(compound_type="small_molecule"))
    coverage = SimpleNamespace(jurisdiction_patents={"US": ["US7654321B2"]})

    decision, supporting, certification, cohort_status, gate_reason = build_scope_contract(
        report, coverage
    )

    assert decision.supports_positive_clearance is False
    assert decision.jurisdictions == []
    assert supporting.jurisdictions == ["US"]
    assert certification.evidence_verified is False
    assert certification.certified_jurisdictions == []
    assert certification.attorney_supervision_required is True
    assert cohort_status.value == "attorney_supervised"
    assert "No verified release-certification receipt" in gate_reason


def _make_report(
    *,
    overall_risk: RiskLevel,
    analyses: list[PatentAnalysis],
    source_health: SourceHealth,
    analysis_failures: list[AnalysisFailure] | None = None,
    data_limitations: list[DataLimitation] | None = None,
    search_loop_result: SearchLoopResult | None = None,
    verification: VerificationResult | None = None,
    critic_report: CriticReport | None = None,
    prosecution_dossiers: list | None = None,
    doe_assessments: list[DoEAssessment] | None = None,
) -> FTOReport:
    if doe_assessments is None:
        doe_assessments = [
            DoEAssessment(
                patent_id=analysis.patent_id,
                claim_number=claim.claim_number,
                element_number=element.element_number,
                element_text=element.element_text,
                estoppel=EstoppelResult(
                    estoppel_applies=False,
                    file_wrapper_available=True,
                ),
                fwr=FWRAssessment(
                    same_function=False,
                    function_reasoning="Fixture evidence establishes a different function.",
                    same_way=True,
                    way_reasoning="Fixture comparison.",
                    same_result=True,
                    result_reasoning="Fixture comparison.",
                    equivalent=False,
                ),
                overall_equivalent=False,
                confidence=0.9,
                confidence_band="HIGH",
                reasoning="Fixture supplies a governed negative DoE assessment.",
            )
            for analysis in analyses
            for claim in analysis.claims_analyzed
            for element in claim.elements
            if element.status in {ElementStatus.NOT_MET, ElementStatus.PARTIALLY_MET}
        ]
    return FTOReport(
        compound=_make_compound(),
        risk_summary=RiskSummary(
            overall_risk=overall_risk,
            total_patents_analyzed=len(analyses),
            executive_summary="summary",
        ),
        patent_analyses=analyses,
        source_health=source_health,
        analysis_failures=analysis_failures or [],
        data_limitations=data_limitations or [],
        search_loop_result=search_loop_result,
        verification=verification or _passing_verification(),
        critic_report=critic_report,
        prosecution_dossiers=prosecution_dossiers or [],
        doe_assessments=doe_assessments,
    )


def _passing_verification() -> VerificationResult:
    return VerificationResult(
        checks=[
            VerificationCheck(check_name="citations", passed=True, severity="pass"),
            VerificationCheck(check_name="claims_grounded", passed=True, severity="pass"),
            VerificationCheck(check_name="dates_consistent", passed=True, severity="pass"),
        ],
        all_citations_valid=True,
        all_claims_grounded=True,
        all_entities_valid=True,
        dates_consistent=True,
        risk_levels_justified=True,
    )


def _claim_analysis(
    status: ElementStatus = ElementStatus.NOT_MET,
    *,
    claim_number: int = 1,
    element_text: str = "claim text",
) -> ClaimAnalysis:
    return ClaimAnalysis(
        claim_number=claim_number,
        claim_type="independent",
        overall_status=status,
        overall_confidence=0.8,
        elements=[
            ClaimElement(
                element_number=1,
                element_text=element_text,
                status=status,
                reasoning="Fixture element supports the governed overall status.",
                confidence=0.8,
                evidence="fixture evidence",
            )
        ],
    )


def test_application_publication_cannot_inherit_grant_status_as_active() -> None:
    patent_id = "US20200123456A1"
    detail = PatentHit(
        patent_id=patent_id,
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        is_granted=False,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_code": "B1",
                    "event_description": "A related grant event was returned.",
                }
            ],
        ),
    )

    assert legal_status_decision_state(detail) == (
        LegalStatus.ACTIVE.value,
        False,
        "pending",
    )


def test_old_grant_without_current_term_or_maintenance_cannot_block() -> None:
    patent_id = "US5555555B1"
    detail = PatentHit(
        patent_id=patent_id,
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        is_granted=True,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_code": "B1",
                    "event_description": "Patent granted in 1995.",
                }
            ],
        ),
    )

    assert legal_status_decision_state(detail) == (
        LegalStatus.ACTIVE.value,
        False,
        "unresolved",
    )


def test_active_grant_requires_known_maintenance_status() -> None:
    patent_id = "US9999999B2"
    primary_status_fields = _primary_status_fields(
        patent_id,
        claims_text="claim text",
    )
    primary_status_fields["primary_legal_status_receipts"] = [
        receipt
        for receipt in primary_status_fields["primary_legal_status_receipts"]
        if receipt["evidence_scope"] != "patent_maintenance"
    ]
    detail = PatentHit(
        patent_id=patent_id,
        **primary_status_fields,
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        claims_text="claim text",
        is_granted=True,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "B2", "event_description": "Patent granted."}],
        ),
        patent_term_info=PatentTermInfo(
            patent_id=patent_id,
            base_expiry=date(2035, 1, 1),
            maintenance_fee_status="unknown",
        ),
    )

    assert legal_status_decision_state(
        detail,
        receipt_verification_keys=_PRIMARY_STATUS_KEYRING,
    ) == (
        LegalStatus.ACTIVE.value,
        False,
        "unresolved",
    )


def test_adjusted_term_is_the_controlling_expiry() -> None:
    patent_id = "US9999998B2"
    detail = PatentHit(
        patent_id=patent_id,
        **_primary_status_fields(
            patent_id,
            term_end_date=date(2028, 1, 1),
            claims_text="claim text",
        ),
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        claims_text="claim text",
        is_granted=True,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "B2", "event_description": "Patent granted."}],
        ),
        expiry_date=date(2025, 1, 1),
        patent_term_info=PatentTermInfo(
            patent_id=patent_id,
            base_expiry=date(2025, 1, 1),
            pte_days=1095,
            maintenance_fee_status="paid",
        ),
    )

    assert legal_status_decision_state(
        detail,
        receipt_verification_keys=_PRIMARY_STATUS_KEYRING,
    ) == (
        LegalStatus.ACTIVE.value,
        True,
        "active",
    )


def test_invalid_newer_term_receipt_cannot_replace_verified_older_winner() -> None:
    patent_id = "US9999997B2"
    primary_status_fields = _primary_status_fields(
        patent_id,
        term_end_date=date(2035, 1, 1),
        claims_text="claim text",
    )
    receipts = [
        receipt
        for receipt in primary_status_fields["primary_legal_status_receipts"]
        if receipt["evidence_scope"] != "patent_term"
    ]
    valid_expired_spec = {
        "source": "uspto_odp_application",
        "evidence_scope": "patent_term",
        "collection_mode": "api",
        "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456/adjustment"),
        "source_record_identifier": "16123456",
        "raw_status": "Expired term",
        "normalized_outcome": "term_expired",
        "parser_identity": "uspto-odp-application-v1",
        "term_end_date": date(2025, 1, 1),
        "term_basis_document_ids": ["grant", "pta-adjustment"],
    }
    valid_expired = build_primary_legal_status_receipt(
        patent_id=patent_id,
        collected_at=datetime.now(UTC) - timedelta(hours=1),
        artifact_media_type="application/json",
        limitations=["Fixture exact official-record outcome."],
        attestation_key_id="runtime-primary",
        attestation_key=_PRIMARY_STATUS_KEY,
        parser_result="conclusive",
        artifact=_primary_status_artifact(
            patent_id,
            valid_expired_spec,
        ),
        **valid_expired_spec,
    ).model_dump(mode="json")
    invalid_current_spec = {
        **valid_expired_spec,
        "raw_status": "Current term",
        "normalized_outcome": "term_current",
        "term_end_date": date(2035, 1, 1),
    }
    invalid_current = build_primary_legal_status_receipt(
        patent_id=patent_id,
        collected_at=datetime.now(UTC),
        artifact_media_type="application/json",
        limitations=["Fixture exact official-record outcome."],
        attestation_key_id="runtime-primary",
        attestation_key=_PRIMARY_STATUS_KEY,
        parser_result="conclusive",
        artifact=_primary_status_artifact(
            patent_id,
            invalid_current_spec,
        ),
        **invalid_current_spec,
    ).model_dump(mode="json")
    invalid_current["attestation_hmac_sha256"] = "0" * 64
    primary_status_fields["primary_legal_status_receipts"] = [
        *receipts,
        valid_expired,
        invalid_current,
    ]
    detail = PatentHit(
        patent_id=patent_id,
        **primary_status_fields,
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        claims_text="claim text",
        is_granted=True,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "B2", "event_description": "Patent granted."}],
        ),
        patent_term_info=PatentTermInfo(
            patent_id=patent_id,
            base_expiry=date(2035, 1, 1),
            maintenance_fee_status="paid",
        ),
    )

    assert legal_status_decision_state(
        detail,
        receipt_verification_keys=_PRIMARY_STATUS_KEYRING,
    ) == (
        LegalStatus.EXPIRED.value,
        True,
        "inactive",
    )


@pytest.mark.parametrize("patent_id", ["USD999999S1", "USPP99999P2"])
def test_design_and_plant_patents_do_not_require_maintenance_fees(
    patent_id: str,
) -> None:
    detail = PatentHit(
        patent_id=patent_id,
        **_primary_status_fields(
            patent_id,
            maintenance_outcome="not_applicable",
            claims_text="claim text",
        ),
        jurisdiction="US",
        sources=[PatentSource.EPO_SEARCH],
        claims_text="claim text",
        is_granted=True,
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "GRANT", "event_description": "Patent granted."}],
        ),
        patent_term_info=PatentTermInfo(
            patent_id=patent_id,
            base_expiry=date(2035, 1, 1),
        ),
    )

    assert legal_status_decision_state(
        detail,
        receipt_verification_keys=_PRIMARY_STATUS_KEYRING,
    ) == (
        LegalStatus.ACTIVE.value,
        True,
        "active",
    )


def _bind_report_analysis_context(report: FTOReport, settings: object) -> None:
    """Stamp hand-built test analyses as the real Step 4 runtime does."""
    for analysis in report.patent_analyses:
        analysis.analysis_context_sha256 = analysis_context_sha256(
            patent_id=analysis.patent_id,
            compound_identity=report.compound,
            product_context=getattr(settings, "product_context", None),
            intended_actions=getattr(settings, "intended_actions", None),
            target_jurisdictions=getattr(settings, "target_jurisdictions", None),
            development_stage=getattr(settings, "development_stage", ""),
        )


def _verified_claim_fields(
    patent_id: str,
    claims_text: str,
    *,
    source: PatentSource | None = None,
) -> dict:
    return trusted_claim_text_fields(
        patent_id,
        claims_text,
        source=source,
    )


def _failing_verification() -> VerificationResult:
    return VerificationResult(
        checks=[
            VerificationCheck(
                check_name="citations",
                passed=False,
                severity="fail",
                details="Citation to EP9999999B1 could not be grounded.",
            ),
            VerificationCheck(check_name="claims_grounded", passed=True, severity="pass"),
            VerificationCheck(check_name="dates_consistent", passed=True, severity="pass"),
        ],
        all_citations_valid=False,
        all_claims_grounded=True,
        all_entities_valid=True,
        dates_consistent=True,
        risk_levels_justified=True,
        issues=["Citation grounding failed for EP9999999B1."],
    )


def test_markush_gate_failure_enters_governed_insufficiency_reasons() -> None:
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=[],
        source_health=SourceHealth(),
    )
    settings = SimpleNamespace(
        require_verified_manual_markush=True,
        markush_evidence_max_age_days=35,
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
    )

    outputs = build_clearance_outputs(report, [], settings=settings)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False
    assert any(
        "verified manual PATENTSCOPE Markush search receipt is required" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )


def test_build_clearance_outputs_blocks_only_verified_active_claim_exposure():
    analyses = [
        PatentAnalysis(
            patent_id="US1234567B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking",
            claims_analyzed=[_claim_analysis(ElementStatus.MET)],
        ),
        PatentAnalysis(
            patent_id="EP2345678B1",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        ),
    ]
    report = _make_report(
        overall_risk=RiskLevel.MEDIUM,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=2),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=2),
            ]
        ),
        search_loop_result=SearchLoopResult(iterations_completed=2),
    )
    patent_hits = [
        PatentHit(
            patent_id="US1234567B2",
            **_primary_status_fields("US1234567B2"),
            **_verified_claim_fields("US1234567B2", "claim text"),
            sources=[
                PatentSource.PUBCHEM,
                PatentSource.PATENTSVIEW,
                PatentSource.EPO_SEARCH,
            ],
            jurisdiction="US",
            legal_status=LegalStatus.ACTIVE,
            legal_status_provenance=trusted_ops_provenance(
                patent_id="US1234567B2",
                legal_status=LegalStatus.ACTIVE,
                artifact=[
                    {
                        "event_code": "B1",
                        "event_description": "Patent granted and active",
                    }
                ],
            ),
            application_number="US10/000001",
            examiner="Examiner",
            transactions=[TransactionEvent(event_description="Amendment after final")],
            family=PatentFamily(
                family_id="fam-1",
                members=[
                    PatentFamilyMember(
                        country="US",
                        doc_number="US123",
                        kind="A1",
                        application_number="US16123456",
                        application_identity_verified=True,
                        application_identity_source="uspto_odp",
                    )
                ],
            ),
            patent_term_info=PatentTermInfo(
                patent_id="US1234567B2",
                base_expiry=date(2038, 1, 1),
                terminal_disclaimer=True,
                td_linked_patent="US7654321B2",
                td_linked_expiry=date(2035, 1, 1),
                maintenance_fee_status="paid",
            ),
            ptab_proceedings=[PTABProceeding(proceeding_number="IPR2025-0001")],
            orange_book_listed=True,
        ),
        PatentHit(
            patent_id="EP2345678B1",
            claims_text="ep claims",
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
            family=PatentFamily(
                family_id="fam-2",
                members=[PatentFamilyMember(country="EP", doc_number="EP234")],
            ),
            designated_states=["DE", "FR"],
            ep_register_status="Pending",
            legal_events=[
                LegalEvent(
                    event_code="OPP",
                    event_description="Opposition filed",
                    country="EP",
                )
            ],
            opposition_events=[
                LegalEvent(
                    event_code="OPP",
                    event_description="Opposition filed",
                    country="EP",
                )
            ],
        ),
    ]

    settings = SimpleNamespace(
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
        matter_type="small_molecule",
        jurisdiction_policy="us_ep_core",
        clearance_threshold_profile="screening",
        source_authority_policy="official_plus_licensed",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "family_context",
            "verification",
        ],
        checkpoint_integrity_keys=_PRIMARY_STATUS_KEYRING,
    )
    _bind_report_analysis_context(report, settings)

    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "blocked"
    assert outputs["commercial_exposure"].damages_injunction_risk == "elevated"
    assert outputs["commercial_exposure"].blocking_patent_ids == ["US1234567B2"]
    assert outputs["jurisdiction_decisions"][0].jurisdiction == "US"
    assert outputs["jurisdiction_decisions"][0].decision.value == "blocked"
    assert outputs[
        "clearance_decision"
    ].decision_audit.claim_program_summary.blocking_patent_ids == ["US1234567B2"]
    assert {finding.risk_type for finding in outputs["future_risk"]} == {
        "pending_family",
        "terminal_disclaimer",
        "ep_opposition",
    }
    assert outputs["prosecution_findings"][0].narrowing_signal is True
    assert outputs["prosecution_findings"][0].transaction_count == 1
    assert outputs["prosecution_findings"][0].amendment_event_count == 1
    assert outputs["prosecution_findings"][0].pending_family_member_count == 1
    assert outputs["prosecution_findings"][0].record_basis == [
        "application_number",
        "uspto_transactions",
        "examiner_metadata",
        "ptab_proceedings",
        "family_members",
        "patent_term_info",
    ]
    assert outputs["future_risk"][0].monitoring_required is True
    assert outputs["future_risk"][0].record_basis == ["family_members"]
    assert outputs["future_risk"][0].related_patent_ids == ["US123A1"]
    assert outputs["future_risk"][1].related_patent_ids == ["US7654321B2"]
    assert outputs["future_risk"][2].record_basis == ["epo_register"]
    assert outputs["future_risk"][2].jurisdiction == "EP"
    assert outputs["claim_construction_record"].jurisdictions == ["US", "EP"]
    assert outputs["clearance_decision"].decision_audit.search_iterations == 2
    assert outputs["clearance_decision"].decision_audit.coverage_summary.reviewed_us_patent_ids == [
        "US1234567B2"
    ]
    assert outputs["clearance_decision"].decision_audit.coverage_summary.reviewed_ep_patent_ids == [
        "EP2345678B1"
    ]
    assert {
        reference.category.value
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    } >= {"blocking_patent", "prosecution_signal", "future_risk"}
    assert any(
        reference.category.value == "prosecution_signal"
        and reference.source_name == "patent_term_info"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )
    assert any(
        reference.category.value == "future_risk" and reference.source_name == "family_members"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )
    assert outputs["record_completeness"].clearance_grade_ready is False
    assert outputs["authority_coverage"].policy == "official_plus_licensed"
    assert outputs["matter_graph_summary"].node_count >= 5
    assert outputs["matter_graph"].nodes[0].node_type.value == "compound_variant"
    assert outputs["claim_program_decisions"][0].patent_id == "US1234567B2"
    assert "ep_opposition_history" in outputs["claim_program_decisions"][1].prosecution_risk_flags
    assert {directive.directive_type for directive in outputs["evidence_collection_plan"]} >= {
        "complete_claim_analysis",
    }
    assert outputs["evidence_artifacts"][0].artifact_type.value == "search_hit"
    assert any(
        result.adapter_name == "pubchem_sdq" for result in outputs["evidence_adapter_results"]
    )
    assert any(
        target.patent_id == "US1234567B2"
        for run in outputs["collector_runs"]
        for target in run.collection_targets
    )
    assert (
        outputs["matter_store"].matter_graph_summary.node_count
        == outputs["matter_graph_summary"].node_count
    )
    assert outputs["matter_store"].record_completeness.clearance_grade_ready is False
    assert [
        contradiction.summary for contradiction in outputs["matter_store"].record_contradictions
    ] == outputs["run_observability"].unresolved_contradictions


def test_build_clearance_outputs_marks_clear_when_evidence_is_complete():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US7654321B2",
                "jurisdiction": "US",
                "application_number": "US10/000002",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions", "amendments"],
                "office_actions_summary": "- [CTNF] Non-final rejection",
                "amendments_summary": "- [AMND] Amendment after final",
                "office_action_events": [
                    {
                        "document_code": "CTNF",
                        "description": "Non-final rejection under 35 U.S.C. 103",
                        "event_date": "2025-01-12",
                        "office_action_type": "non_final_office_action",
                        "claims_rejected": [1],
                        "rejection_bases": ["103", "prior_art"],
                    }
                ],
                "amendment_events": [
                    {
                        "transaction_code": "AMND",
                        "description": "Amendment after final to claim 1",
                        "event_date": "2025-02-14",
                        "event_type": "after_final_response",
                        "claim_numbers": [1],
                    },
                    {
                        "transaction_code": "RCE",
                        "description": "Request for Continued Examination",
                        "event_date": "2025-02-28",
                        "event_type": "rce",
                        "claim_numbers": [],
                    },
                ],
                "office_action_count": 1,
                "continuity_entry_count": 0,
                "amendment_entry_count": 2,
                "office_action_types": ["non_final_office_action"],
                "amendment_types": ["after_final_response", "rce"],
                "rejected_claim_numbers": [1],
                "narrowing_claim_numbers": [1],
                "rejection_bases": ["103", "prior_art"],
                "estoppel_risk_flags": [
                    "after_final_response_history",
                    "rce_history",
                    "prior_art_rejection_history",
                    "amendment_after_office_action_history",
                ],
                "response_after_final_count": 1,
                "rce_count": 1,
                "record_basis": ["uspto_odp", "application_number", "uspto_transactions"],
                "summary": "file-wrapper dossier captured",
            }
        ],
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            **_verified_claim_fields(
                "US7654321B2",
                "claim text",
                source=PatentSource.PATENTSVIEW,
            ),
            sources=[PatentSource.PUBCHEM, PatentSource.PATENTSVIEW],
            jurisdiction="US",
            application_number="US10/000002",
            transactions=[TransactionEvent(event_description="Non-final rejection")],
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    settings = SimpleNamespace(
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
        require_verified_manual_markush=False,
    )
    _bind_report_analysis_context(report, settings)
    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "clear"
    assert outputs["decision_scope"].jurisdictions == ["US"]
    assert outputs["decision_scope"].supports_positive_clearance is True
    assert outputs["supporting_scope"].jurisdictions == []
    assert outputs["certification_scope"].certified_jurisdictions == ["US", "EP"]
    assert outputs["certification_scope"].current_matter_type_certified is True
    assert outputs["cohort_status"].value == "certified"
    assert outputs["clearance_decision"].decision_confidence == 0.9
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is True
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.blocking_claim_ids == []
    )
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.medium_risk_claim_ids
        == []
    )
    assert outputs["clearance_decision"].decision_audit.clearance_grade_ready_patents == 1
    assert outputs["run_observability"].false_clear_risk_flags == []
    assert outputs["clearance_decision"].decision_audit.incomplete_material_patents == 0
    assert outputs["clearance_decision"].decision_audit.us_patents_with_file_wrapper_dossier == 1
    assert outputs["jurisdiction_decisions"][0].decision.value == "clear"
    assert outputs["jurisdiction_decisions"][0].evidence_sufficient_for_clearance is True
    assert outputs["jurisdiction_decisions"][0].gate_failures == []
    assert outputs["future_risk"] == []
    assert outputs["commercial_exposure"].business_severity == "low"
    assert outputs["clearance_decision"].decision_audit.coverage_summary.verification_gaps == []
    assert (
        outputs[
            "clearance_decision"
        ].decision_audit.coverage_summary.patents_missing_claim_level_analysis
        == []
    )
    assert (
        outputs[
            "clearance_decision"
        ].decision_audit.coverage_summary.us_patents_missing_file_wrapper_dossier
        == []
    )
    assert any(
        reference.category.value == "clearance_support"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )
    assert outputs["record_completeness"].clearance_grade_ready is True
    assert outputs["authority_coverage"].authoritative_categories_missing == []
    assert outputs["claim_program_decisions"][0].claim_number == 1
    assert set(outputs["claim_program_decisions"][0].prosecution_risk_flags) >= {
        "after_final_response_history",
        "rce_history",
        "prior_art_rejection_history",
        "rejected_during_prosecution",
        "narrowed_claim_scope",
        "rejection_103",
        "rejection_prior_art",
    }
    assert outputs["claim_program_decisions"][0].prosecution_risk_level == "high"
    assert outputs["claim_program_decisions"][0].post_grant_risk_level == ""
    assert outputs["claim_program_decisions"][0].scope_constrained is True
    assert outputs["claim_program_decisions"][0].record_basis == [
        "uspto_odp",
        "application_number",
        "uspto_transactions",
        "family_members",
        "accused_act:sale",
    ]
    assert outputs["prosecution_findings"][0].office_action_types == ["non_final_office_action"]
    assert outputs["prosecution_findings"][0].rejection_bases == ["103", "prior_art"]
    assert outputs["matter_graph_summary"].node_count >= 4
    assert {node.node_type.value for node in outputs["matter_graph"].nodes} >= {
        "compound_variant",
        "patent",
        "application",
        "office_action",
        "amendment",
    }
    assert any(
        edge.edge_type.value == "amended_by" and edge.from_node_id == "application:US10/000002"
        for edge in outputs["matter_graph"].edges
    )
    assert outputs["coverage_gaps"] == []
    assert any(
        artifact.artifact_type.value == "claims_text" for artifact in outputs["evidence_artifacts"]
    )
    assert any(
        result.adapter_name == "pubchem_sdq" for result in outputs["evidence_adapter_results"]
    )
    collector_runs = {run.definition.collector_name: run for run in outputs["collector_runs"]}
    assert collector_runs["uspto_odp"].attempts[0].summary == (
        "Collector satisfied the currently targeted matter records."
    )
    assert outputs["matter_store"].record_contradictions == []
    assert outputs["matter_store"].authority_coverage.authoritative_categories_missing == []


def test_build_clearance_outputs_scopes_claim_specific_prosecution_history():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[
                _claim_analysis(claim_number=1),
                _claim_analysis(claim_number=2),
            ],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="uspto_odp", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US7654321B2",
                "jurisdiction": "US",
                "application_number": "US10/000002",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions", "amendments", "continuity"],
                "office_action_events": [
                    {
                        "document_code": "CTNF",
                        "description": "Non-final rejection under 35 U.S.C. 103 of claim 1",
                        "event_date": "2025-01-12",
                        "office_action_type": "non_final_office_action",
                        "claims_rejected": [1],
                        "rejection_bases": ["103", "prior_art"],
                    }
                ],
                "amendment_events": [
                    {
                        "transaction_code": "AMND",
                        "description": "Amendment after final to claim 1",
                        "event_date": "2025-02-14",
                        "event_type": "after_final_response",
                        "claim_numbers": [1],
                    }
                ],
                "continuity_entries": [
                    {
                        "relationship": "parent",
                        "application_number": "US10/000002",
                        "related_application_number": "US09/999999",
                        "continuity_type": "continuation",
                        "filing_date": "2024-11-01",
                    }
                ],
                "office_action_count": 1,
                "continuity_entry_count": 1,
                "amendment_entry_count": 1,
                "rejected_claim_numbers": [1],
                "narrowing_claim_numbers": [1],
                "rejection_bases": ["103", "prior_art"],
                "estoppel_risk_flags": [
                    "after_final_response_history",
                    "prior_art_rejection_history",
                    "amendment_after_office_action_history",
                    "continuation_lineage",
                ],
                "continuation_parent_count": 1,
                "response_after_final_count": 1,
                "record_basis": ["uspto_odp", "application_number", "uspto_transactions"],
                "summary": "claim 1 was rejected and amended during prosecution",
            }
        ],
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            application_number="US10/000002",
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    settings = SimpleNamespace(
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
    )
    _bind_report_analysis_context(report, settings)
    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    by_claim = {decision.claim_number: decision for decision in outputs["claim_program_decisions"]}
    assert set(by_claim[1].prosecution_risk_flags) >= {
        "continuation_lineage",
        "after_final_response_history",
        "prior_art_rejection_history",
        "rejected_during_prosecution",
        "narrowed_claim_scope",
        "rejection_103",
        "rejection_prior_art",
    }
    assert "after_final_response_history" not in by_claim[2].prosecution_risk_flags
    assert "prior_art_rejection_history" not in by_claim[2].prosecution_risk_flags
    assert "rejected_during_prosecution" not in by_claim[2].prosecution_risk_flags
    assert "narrowed_claim_scope" not in by_claim[2].prosecution_risk_flags
    assert "rejection_103" not in by_claim[2].prosecution_risk_flags
    assert "continuation_lineage" in by_claim[2].prosecution_risk_flags
    assert by_claim[1].prosecution_risk_level == "high"
    assert by_claim[2].prosecution_risk_level == "medium"
    assert by_claim[1].scope_constrained is True
    assert by_claim[2].scope_constrained is True
    assert by_claim[1].record_basis == [
        "uspto_odp",
        "application_number",
        "family_members",
        "accused_act:sale",
    ]


def test_build_clearance_outputs_refuses_clear_for_attorney_supervised_cohort():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="uspto_odp", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US7654321B2",
                "jurisdiction": "US",
                "application_number": "US10/000002",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions", "amendments"],
                "office_action_events": [],
                "amendment_events": [],
                "office_action_count": 0,
                "continuity_entry_count": 0,
                "amendment_entry_count": 0,
                "record_basis": ["uspto_odp", "application_number"],
                "summary": "file-wrapper dossier captured",
            }
        ],
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            application_number="US10/000002",
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]
    settings = SimpleNamespace(
        matter_type="biologic",
        jurisdiction_policy="us_ep_core",
        clearance_threshold_profile="world_class_us_ep",
        source_authority_policy="official_plus_licensed",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "authoritative_records",
            "family_context",
            "us_file_wrapper_dossier",
            "verification",
        ],
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
    )
    _bind_report_analysis_context(report, settings)

    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["decision_scope"].jurisdictions == []
    assert outputs["decision_scope"].supports_positive_clearance is False
    assert outputs["supporting_scope"].jurisdictions == ["US"]
    assert outputs["certification_scope"].current_matter_type_certified is False
    assert outputs["cohort_status"].value == "attorney_supervised"
    assert any(
        "classification is missing or conflicts" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert outputs["jurisdiction_decisions"][0].decision.value == "unclear"
    assert any(
        "attorney supervision is required" in failure
        for failure in outputs["jurisdiction_decisions"][0].gate_failures
    )
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False


def test_build_clearance_outputs_reuses_persisted_matter_graph():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US7654321B2",
                "jurisdiction": "US",
                "application_number": "US10/000002",
                "sections_available": ["office_actions"],
                "office_action_events": [],
                "amendment_events": [],
                "record_basis": ["uspto_odp"],
            }
        ],
    )
    report.matter_graph = MatterGraph(
        nodes=[
            MatterNode(
                node_id="compound:aspirin",
                node_type=MatterNodeType.COMPOUND_VARIANT,
                label="aspirin",
            ),
            MatterNode(
                node_id="patent:US7654321B2",
                node_type=MatterNodeType.PATENT,
                label="US7654321B2",
                jurisdiction="US",
                patent_id="US7654321B2",
            ),
        ],
        edges=[
            MatterEdge(
                edge_type=MatterEdgeType.ROOTS,
                from_node_id="compound:aspirin",
                to_node_id="patent:US7654321B2",
                summary="persisted graph",
            )
        ],
    )
    report.matter_graph_summary = MatterGraphSummary(
        root_compound="aspirin",
        node_count=2,
        edge_count=1,
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            application_number="US10/000002",
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning.build_matter_graph",
            side_effect=AssertionError("matter graph should have been reused"),
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning.summarize_matter_graph",
            side_effect=AssertionError("matter graph summary should have been reused"),
        ),
    ):
        outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["matter_graph"] is report.matter_graph
    assert outputs["matter_graph_summary"] is report.matter_graph_summary


def test_build_clearance_outputs_reuses_persisted_evidence_adapter_results():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US7654321B2",
                "jurisdiction": "US",
                "application_number": "US10/000002",
                "sections_available": ["office_actions"],
                "office_action_events": [],
                "amendment_events": [],
                "record_basis": ["uspto_odp"],
            }
        ],
    )
    report.evidence_artifacts = [
        EvidenceArtifact(
            artifact_id="persisted-claims",
            artifact_type=EvidenceArtifactType.CLAIMS_TEXT,
            source_name="patentsview",
            authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
            patent_id="US7654321B2",
        )
    ]
    report.evidence_adapter_results = [
        EvidenceAdapterResult(
            adapter_name="patentsview",
            artifact_count=1,
            covered_components=["claims_text"],
            expected_components=["claims_text"],
            missing_components=[],
            supports_authoritative_findings=True,
        )
    ]
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            application_number="US10/000002",
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning.build_evidence_artifacts",
            side_effect=AssertionError("evidence artifacts should have been reused"),
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning.build_evidence_adapter_results",
            side_effect=AssertionError("adapter results should have been reused"),
        ),
    ):
        outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["evidence_artifacts"] == report.evidence_artifacts
    assert outputs["evidence_adapter_results"] == report.evidence_adapter_results


def test_build_clearance_outputs_does_not_trust_unbound_llm_invalidity_strength():
    analyses = [
        PatentAnalysis(
            patent_id="US4444444B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="Literal read appears strong on claim 1.",
            claims_analyzed=[_claim_analysis(ElementStatus.MET)],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="uspto_odp", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        prosecution_dossiers=[
            {
                "patent_id": "US4444444B2",
                "jurisdiction": "US",
                "application_number": "US10/000444",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions"],
                "office_actions_summary": "- [CTNF] Non-final rejection",
                "office_action_events": [
                    {
                        "document_code": "CTNF",
                        "description": "Non-final rejection under 35 U.S.C. 103",
                        "event_date": "2025-01-12",
                        "office_action_type": "non_final_office_action",
                        "rejection_bases": ["103"],
                    }
                ],
                "office_action_count": 1,
                "record_basis": ["uspto_odp", "application_number", "uspto_transactions"],
                "summary": "file-wrapper dossier captured",
            }
        ],
    )
    report.invalidity_assessments = [
        InvalidityAssessment(
            patent_id="US4444444B2",
            claim_numbers=[1],
            overall_invalidity_strength="strong",
            reasoning="Prior art appears to anticipate the independent claim.",
            confidence=0.78,
            confidence_band="HIGH",
        )
    ]
    patent_hits = [
        PatentHit(
            patent_id="US4444444B2",
            **_primary_status_fields("US4444444B2"),
            **_verified_claim_fields(
                "US4444444B2",
                "claim text",
                source=PatentSource.PATENTSVIEW,
            ),
            sources=[PatentSource.PATENTSVIEW, PatentSource.EPO_SEARCH],
            jurisdiction="US",
            legal_status=LegalStatus.ACTIVE,
            legal_status_provenance=trusted_ops_provenance(
                patent_id="US4444444B2",
                legal_status=LegalStatus.ACTIVE,
                artifact=[
                    {
                        "event_code": "B1",
                        "event_description": "Patent granted and active",
                    }
                ],
            ),
            application_number="US10/000444",
            transactions=[TransactionEvent(event_description="Non-final rejection")],
            family=PatentFamily(
                family_id="fam-44",
                members=[PatentFamilyMember(country="US", doc_number="US444", kind="B2")],
            ),
            patent_term_info=PatentTermInfo(
                patent_id="US4444444B2",
                base_expiry=date(2035, 1, 1),
                maintenance_fee_status="paid",
            ),
        )
    ]

    settings = SimpleNamespace(
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
        require_verified_manual_markush=False,
        checkpoint_integrity_keys=_PRIMARY_STATUS_KEYRING,
    )
    _bind_report_analysis_context(report, settings)
    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "blocked"
    assert outputs["jurisdiction_decisions"][0].decision.value == "blocked"
    assert outputs[
        "clearance_decision"
    ].decision_audit.claim_program_summary.blocking_claim_ids == ["US4444444B2#claim1"]
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.contested_claim_ids == []
    )
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.contested_patent_ids
        == []
    )
    assert "contested_high_risk_claims" not in outputs["run_observability"].false_clear_risk_flags
    assert not any(
        "contested by strong invalidity positions" in line
        for line in outputs["clearance_decision"].decision_reasoning
    )


def test_build_clearance_outputs_respects_required_record_component_policy():
    analyses = [
        PatentAnalysis(
            patent_id="US8888888B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US8888888B2",
            **_verified_claim_fields(
                "US8888888B2",
                "claim text",
                source=PatentSource.PATENTSVIEW,
            ),
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            family=PatentFamily(
                family_id="fam-8",
                members=[PatentFamilyMember(country="US", doc_number="US888", kind="B2")],
            ),
        )
    ]
    settings = SimpleNamespace(
        matter_type="small_molecule",
        jurisdiction_policy="us_ep_core",
        clearance_threshold_profile="screening",
        source_authority_policy="official_plus_licensed",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "authoritative_records",
            "family_context",
            "verification",
        ],
        intended_actions=["commercial_launch"],
        product_context=_planned_sale_context(),
        require_verified_manual_markush=False,
    )
    _bind_report_analysis_context(report, settings)

    outputs = build_clearance_outputs(report, patent_hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "clear"
    assert outputs["record_completeness"].required_components == [
        "claims_text",
        "claim_level_analysis",
        "authoritative_records",
        "family_context",
        "verification",
    ]
    assert outputs["record_completeness"].missing_components == []
    assert outputs[
        "clearance_decision"
    ].decision_audit.coverage_summary.required_record_components == [
        "claims_text",
        "claim_level_analysis",
        "authoritative_records",
        "family_context",
        "verification",
    ]
    assert outputs["coverage_gaps"] == []


def test_build_clearance_outputs_refuses_clear_when_verification_fails():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        verification=_failing_verification(),
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            application_number="US10/000002",
            transactions=[TransactionEvent(event_description="Non-final rejection")],
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert any(
        "Verification did not fully pass" in warning
        for warning in outputs["clearance_decision"].decision_audit.evidence_warnings
    )
    assert outputs[
        "clearance_decision"
    ].decision_audit.coverage_summary.patents_missing_claim_level_analysis == ["US7654321B2"]
    assert outputs[
        "clearance_decision"
    ].decision_audit.coverage_summary.us_patents_missing_file_wrapper_dossier == ["US7654321B2"]
    assert "Citation grounding failed for EP9999999B1." in (
        outputs["clearance_decision"].decision_audit.coverage_summary.verification_gaps
    )
    assert any(
        reference.category.value == "verification_gap"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )
    assert any(
        reference.signal == "missing_file_wrapper_dossier"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )


def test_build_clearance_outputs_surfaces_warnings_for_incomplete_evidence():
    analyses = [
        PatentAnalysis(
            patent_id="EP9999999B1",
            risk_level=RiskLevel.LOW,
            risk_summary="low risk",
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.LOW,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.FAILED, patent_count=0),
            ]
        ),
        analysis_failures=[
            AnalysisFailure(
                patent_id="EP0000001A1",
                step="step4",
                error_type="RuntimeError",
                error_message="boom",
            )
        ],
        data_limitations=[
            DataLimitation(
                category="coverage_gap",
                description="Register history missing",
                impact="medium",
            )
        ],
        verification=_failing_verification(),
    )
    patent_hits = [
        PatentHit(
            patent_id="EP9999999B1",
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_audit.failed_sources == ["bigquery"]
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False
    assert any(
        "claims text" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "claim-level analysis" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "Deterministic verification did not fully pass" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "Not every analyzed patent had full claims text" in warning
        for warning in outputs["clearance_decision"].decision_audit.evidence_warnings
    )
    assert (
        "Register history missing" in outputs["clearance_decision"].decision_audit.evidence_warnings
    )
    assert outputs["jurisdiction_decisions"][1].jurisdiction == "EP"
    assert outputs["jurisdiction_decisions"][1].decision.value == "unclear"
    assert outputs["jurisdiction_decisions"][1].evidence_sufficient_for_clearance is False
    assert any(
        "lack full claims text" in failure
        for failure in outputs["jurisdiction_decisions"][1].gate_failures
    )
    assert outputs["clearance_decision"].decision_audit.coverage_summary.failed_source_names == [
        "bigquery"
    ]
    assert outputs["clearance_decision"].decision_audit.coverage_summary.patents_missing_claims == [
        "EP9999999B1",
        "EP0000001A1",
    ]
    assert outputs[
        "clearance_decision"
    ].decision_audit.coverage_summary.patents_missing_claim_level_analysis == [
        "EP9999999B1",
        "EP0000001A1",
    ]
    assert (
        outputs[
            "clearance_decision"
        ].decision_audit.coverage_summary.clearance_grade_ready_patent_ids
        == []
    )
    assert any(
        "Verification did not fully pass" in warning
        for warning in outputs["clearance_decision"].decision_audit.evidence_warnings
    )
    assert {
        reference.category.value
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    } >= {"source_failure", "coverage_gap", "verification_gap"}
    assert {
        reference.signal
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    } >= {
        "missing_claim_level_analysis",
        "missing_authoritative_record_support",
    }
    assert outputs["commercial_exposure"].damages_injunction_risk == "uncertain"
    assert {directive.directive_type for directive in outputs["evidence_collection_plan"]} >= {
        "collect_claims_text",
        "complete_claim_analysis",
        "collect_ep_register_context",
        "rerun_verification",
    }
    assert {flag for flag in outputs["run_observability"].false_clear_risk_flags} >= {
        "claims_text_missing",
        "claim_level_analysis_missing",
        "verification_failed",
        "analysis_failures_present",
        "record_incomplete",
    }


def test_build_clearance_outputs_surfaces_runtime_budget_and_search_loop_incompleteness():
    analyses = [
        PatentAnalysis(
            patent_id="US2222222B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear on the reviewed record",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        data_limitations=[
            DataLimitation(
                category="runtime_budget_exceeded",
                description="Run stopped before completion.",
                impact="Record remains incomplete.",
            )
        ],
        search_loop_result=SearchLoopResult(
            iterations_completed=2,
            termination_reason="record_collection_required",
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US2222222B2",
            claims_text="claim text",
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            family=PatentFamily(
                family_id="fam-222",
                members=[PatentFamilyMember(country="US", doc_number="US222", kind="B2")],
            ),
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert {flag for flag in outputs["run_observability"].false_clear_risk_flags} >= {
        "runtime_budget_exceeded",
        "search_loop_incomplete",
        "record_incomplete",
    }
    assert outputs["run_observability"].unresolved_contradictions == [
        "Run terminated before completion because the configured runtime budget expired.",
        "Search loop stopped while required evidence-collection directives were still open.",
    ]


def test_build_clearance_outputs_refuses_clear_when_no_material_evidence_exists():
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=[],
        source_health=SourceHealth(entries=[]),
    )

    outputs = build_clearance_outputs(report, [])

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_confidence <= 0.45
    assert outputs["clearance_decision"].evidence_quality == 0.25
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False
    assert outputs["clearance_decision"].decision_audit.queried_sources_count == 0
    assert outputs["clearance_decision"].decision_audit.successful_sources_count == 0
    assert any(
        "No material patents were reviewed" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "No search sources were recorded" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert outputs["clearance_decision"].decision_audit.coverage_summary.reviewed_patent_ids == []


def test_ep_inactive_status_cannot_clear_without_controlling_language_claims():
    analyses = [
        PatentAnalysis(
            patent_id="EP9999999B1",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking on current record",
            claims_analyzed=[_claim_analysis(ElementStatus.MET)],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="epo_register", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="EP9999999B1",
            **_verified_claim_fields("EP9999999B1", "claim text"),
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
            legal_status=LegalStatus.REVOKED,
            legal_status_provenance=trusted_register_provenance(
                patent_id="EP9999999B1",
                artifact={"status": "Revoked"},
            ),
            ep_register_status="Revoked",
            family=PatentFamily(
                family_id="fam-999",
                members=[PatentFamilyMember(country="EP", doc_number="9999999", kind="B1")],
            ),
            designated_states=["DE", "FR"],
        )
    ]

    outputs = build_clearance_outputs(
        report,
        patent_hits,
        settings=SimpleNamespace(intended_actions=["commercial_launch"]),
    )

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["jurisdiction_decisions"][1].decision.value == "unclear"
    summary = outputs["clearance_decision"].decision_audit.claim_program_summary
    assert summary.blocking_claim_ids == []
    assert summary.inactive_coverage_claim_ids == []
    assert summary.claims_with_insufficient_evidence == ["EP9999999B1#claim1"]


def test_trusted_inactive_status_does_not_clear_historical_exposure():
    patent_id = "EP9999999B1"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="high claim-coverage screen",
                claims_analyzed=[_claim_analysis(ElementStatus.MET)],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="epo_register", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(patent_id, "claim text"),
        sources=[PatentSource.EPO_SEARCH],
        jurisdiction="EP",
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=trusted_register_provenance(
            patent_id=patent_id,
            artifact={"status": "Revoked"},
        ),
        ep_register_status="Revoked",
        family=PatentFamily(
            family_id="fam-999",
            members=[PatentFamilyMember(country="EP", doc_number="9999999", kind="B1")],
        ),
        designated_states=["DE", "FR"],
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(
            intended_actions=["commercial_launch"],
            product_context={
                "commercial_action": "Already used in 2024",
                "commercial_territories": ["EP"],
                "accused_acts": [
                    {
                        "act": "use",
                        "jurisdiction": "EP",
                        "start_date": "2024-01-01",
                        "end_date": "2024-12-31",
                        "actor": "Legacy user",
                        "status": "actual",
                        "purpose": "commercial",
                        "regulatory_path": "none",
                        "instrumentality": "The analyzed product",
                        "liability_theory": "direct",
                    }
                ],
            },
        ),
    )

    assert outputs["clearance_decision"].decision.value == "unclear"
    summary = outputs["clearance_decision"].decision_audit.claim_program_summary
    assert summary.inactive_coverage_claim_ids == []
    assert summary.claims_with_insufficient_evidence == [f"{patent_id}#claim1"]
    assert "historical_exposure_review" in outputs["claim_program_decisions"][0].missing_components


def test_trusted_inactive_status_does_not_clear_pending_family_exposure():
    patent_id = "EP9999999B1"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="high claim-coverage screen",
                claims_analyzed=[_claim_analysis(ElementStatus.MET)],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="epo_register", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(patent_id, "claim text"),
        sources=[PatentSource.EPO_SEARCH],
        jurisdiction="EP",
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=trusted_register_provenance(
            patent_id=patent_id,
            artifact={"status": "Revoked"},
        ),
        ep_register_status="Revoked",
        family=PatentFamily(
            family_id="fam-999",
            members=[
                PatentFamilyMember(country="EP", doc_number="9999999", kind="B1"),
                PatentFamilyMember(
                    country="EP",
                    doc_number="1234567",
                    kind="A1",
                    application_number="EP21123456",
                    application_identity_verified=True,
                    application_identity_source="epo_register",
                ),
            ],
        ),
        designated_states=["DE", "FR"],
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(intended_actions=["commercial_launch"]),
    )

    assert outputs["clearance_decision"].decision.value == "unclear"
    summary = outputs["clearance_decision"].decision_audit.claim_program_summary
    assert summary.inactive_coverage_claim_ids == []
    assert summary.medium_risk_claim_ids == [f"{patent_id}#claim1"]
    assert outputs["claim_program_decisions"][0].future_risk_flags == ["pending_family"]


def test_explicit_target_jurisdiction_isolates_supporting_blocker_from_top_decision():
    us_patent_id = "US7654321B2"
    ep_patent_id = "EP2345678B1"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=us_patent_id,
                risk_level=RiskLevel.CLEAR,
                risk_summary="No US claim limitation is met.",
                claims_analyzed=[
                    _claim_analysis(
                        ElementStatus.NOT_MET,
                        element_text="US claim text",
                    )
                ],
            ),
            PatentAnalysis(
                patent_id=ep_patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Active EP claim reads on the product.",
                claims_analyzed=[
                    _claim_analysis(
                        ElementStatus.MET,
                        element_text="EP claim text",
                    )
                ],
            ),
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="epo_register", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    hits = [
        PatentHit(
            patent_id=us_patent_id,
            **_verified_claim_fields(
                us_patent_id,
                "US claim text",
                source=PatentSource.PATENTSVIEW,
            ),
            sources=[PatentSource.PATENTSVIEW],
            jurisdiction="US",
            family=PatentFamily(
                family_id="fam-us",
                members=[PatentFamilyMember(country="US", doc_number="7654321", kind="B2")],
            ),
        ),
        PatentHit(
            patent_id=ep_patent_id,
            **_verified_claim_fields(ep_patent_id, "EP claim text"),
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
            legal_status=LegalStatus.ACTIVE,
            legal_status_provenance=trusted_register_provenance(
                patent_id=ep_patent_id,
                artifact={"status": "Active"},
            ),
            ep_register_status="Active",
            family=PatentFamily(
                family_id="fam-ep",
                members=[PatentFamilyMember(country="EP", doc_number="2345678", kind="B1")],
            ),
            designated_states=["DE", "FR"],
        ),
    ]
    settings = SimpleNamespace(
        intended_actions=["commercial_launch"],
        target_jurisdictions=["US"],
        product_context=_planned_sale_context(),
        require_verified_manual_markush=False,
        matter_type="small_molecule",
        clearance_threshold_profile="screening",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "family_context",
            "verification",
        ],
    )
    _bind_report_analysis_context(report, settings)

    outputs = build_clearance_outputs(report, hits, settings=settings)

    assert outputs["clearance_decision"].decision.value == "clear"
    assert outputs["decision_scope"].jurisdictions == ["US"]
    assert outputs["supporting_scope"].jurisdictions == ["EP"]
    assert "cannot change" in outputs["supporting_scope"].summary
    jurisdiction_decisions = {
        item.jurisdiction: item.decision.value for item in outputs["jurisdiction_decisions"]
    }
    assert jurisdiction_decisions == {"US": "clear", "EP": "unclear"}
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.blocking_patent_ids == []
    )


def test_missing_explicit_target_cannot_be_replaced_by_supporting_jurisdiction():
    ep_patent_id = "EP2345678B1"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=ep_patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Supporting EP record only.",
                claims_analyzed=[_claim_analysis(ElementStatus.MET)],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="epo_register", status=SourceStatus.OK, patent_count=1)
            ]
        ),
    )
    hit = PatentHit(
        patent_id=ep_patent_id,
        **_verified_claim_fields(ep_patent_id, "EP claim text"),
        sources=[PatentSource.EPO_SEARCH],
        jurisdiction="EP",
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=trusted_register_provenance(
            patent_id=ep_patent_id,
            artifact={"status": "Revoked"},
        ),
        ep_register_status="Revoked",
        family=PatentFamily(
            family_id="fam-ep",
            members=[PatentFamilyMember(country="EP", doc_number="2345678", kind="B1")],
        ),
        designated_states=["DE", "FR"],
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(
            intended_actions=["commercial_launch"],
            target_jurisdictions=["US"],
            matter_type="small_molecule",
            clearance_threshold_profile="screening",
            required_record_components=[
                "claims_text",
                "claim_level_analysis",
                "family_context",
                "verification",
            ],
        ),
    )

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["decision_scope"].jurisdictions == ["US"]
    assert outputs["supporting_scope"].jurisdictions == ["EP"]
    assert any(
        "No material patent record was reviewed for target jurisdiction(s): US" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )


def test_dependent_claim_cannot_block_when_an_inherited_parent_limitation_is_not_met():
    patent_id = "US4567890B2"
    parent = _claim_analysis(ElementStatus.NOT_MET, claim_number=1)
    dependent = ClaimAnalysis(
        claim_number=2,
        claim_type="dependent",
        depends_on=1,
        overall_status=ElementStatus.MET,
        overall_confidence=0.9,
        elements=[
            ClaimElement(
                element_number=1,
                element_text="additional dependent limitation",
                status=ElementStatus.MET,
                reasoning="The added limitation is present.",
                confidence=0.9,
                evidence="fixture evidence",
            )
        ],
    )
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Upstream screen intentionally overstates the dependent claim.",
                claims_analyzed=[parent, dependent],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1)
            ]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "Claims 1 and 2",
            source=PatentSource.PATENTSVIEW,
        ),
        sources=[PatentSource.PATENTSVIEW],
        jurisdiction="US",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "B1", "event_description": "Patent granted and active"}],
        ),
        family=PatentFamily(
            family_id="fam-dependent",
            members=[PatentFamilyMember(country="US", doc_number="4567890", kind="B2")],
        ),
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(
            intended_actions=["commercial_launch"],
            clearance_threshold_profile="screening",
            required_record_components=[
                "claims_text",
                "claim_level_analysis",
                "family_context",
                "verification",
            ],
        ),
    )

    decisions = {item.claim_number: item for item in outputs["claim_program_decisions"]}
    assert decisions[1].literal_outcome == "not_met"
    assert decisions[2].literal_outcome == "not_met"
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.blocking_claim_ids == []
    )
    assert outputs["clearance_decision"].decision.value != "blocked"


def test_doe_requires_every_unmet_limitation_to_be_affirmatively_equivalent():
    patent_id = "US5678901B2"
    claim = ClaimAnalysis(
        claim_number=1,
        claim_type="independent",
        overall_status=ElementStatus.NOT_MET,
        overall_confidence=0.9,
        elements=[
            ClaimElement(
                element_number=1,
                element_text="first absent limitation",
                status=ElementStatus.NOT_MET,
                reasoning="Not literally met.",
                confidence=0.9,
                evidence="fixture evidence",
            ),
            ClaimElement(
                element_number=2,
                element_text="second absent limitation",
                status=ElementStatus.NOT_MET,
                reasoning="Not literally met.",
                confidence=0.9,
                evidence="fixture evidence",
            ),
        ],
    )
    affirmative = DoEAssessment(
        patent_id=patent_id,
        claim_number=1,
        element_number=1,
        element_text="first absent limitation",
        estoppel=EstoppelResult(
            estoppel_applies=False,
            file_wrapper_available=True,
        ),
        fwr=FWRAssessment(
            same_function=True,
            function_reasoning="Same function.",
            same_way=True,
            way_reasoning="Same way.",
            same_result=True,
            result_reasoning="Same result.",
            equivalent=True,
        ),
        overall_equivalent=True,
        confidence=0.9,
        confidence_band="HIGH",
        reasoning="Only the first limitation is equivalent.",
    )
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Upstream screen.",
                claims_analyzed=[claim],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1)
            ]
        ),
        doe_assessments=[affirmative],
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "1. A compound comprising first and second limitations.",
            source=PatentSource.PATENTSVIEW,
        ),
        sources=[PatentSource.PATENTSVIEW],
        jurisdiction="US",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[{"event_code": "B1", "event_description": "Patent granted and active"}],
        ),
        family=PatentFamily(
            family_id="fam-doe",
            members=[PatentFamilyMember(country="US", doc_number="5678901", kind="B2")],
        ),
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(
            intended_actions=["commercial_launch"],
            clearance_threshold_profile="screening",
            required_record_components=[
                "claims_text",
                "claim_level_analysis",
                "family_context",
                "verification",
            ],
        ),
    )

    decision = outputs["claim_program_decisions"][0]
    assert decision.doe_risk == "medium"
    assert "doe_all_limitations" in decision.missing_components
    assert (
        outputs["clearance_decision"].decision_audit.claim_program_summary.blocking_claim_ids == []
    )
    assert outputs["clearance_decision"].decision.value == "unclear"


def test_past_act_before_patent_term_cannot_create_blocking_exposure():
    patent_id = "US8888001B2"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Literal product-claim screen is high.",
                claims_analyzed=[
                    ClaimAnalysis(
                        claim_number=1,
                        claim_type="independent",
                        preamble="A compound",
                        preamble_limiting="limiting",
                        preamble_limitation_reasoning="The preamble supplies the claimed article.",
                        preamble_limitation_evidence="Claim 1 text.",
                        transitional_phrase="comprising",
                        overall_status=ElementStatus.MET,
                        overall_confidence=0.9,
                        elements=[
                            ClaimElement(
                                element_number=0,
                                element_text="A compound",
                                status=ElementStatus.MET,
                                reasoning="The accused article is a compound.",
                                confidence=0.9,
                                evidence="Bound product context.",
                            ),
                            ClaimElement(
                                element_number=1,
                                element_text="the active moiety",
                                status=ElementStatus.MET,
                                reasoning="The active moiety is present.",
                                confidence=0.9,
                                evidence="Bound structure evidence.",
                            ),
                        ],
                    )
                ],
            )
        ],
        source_health=SourceHealth(
            entries=[SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1)]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "1. A compound comprising the active moiety.",
            source=PatentSource.BIGQUERY,
        ),
        sources=[PatentSource.BIGQUERY, PatentSource.EPO_SEARCH],
        jurisdiction="US",
        filing_date="2023-01-01",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_date": "2024-01-01",
                    "event_code": "B1",
                    "event_description": "Patent granted",
                }
            ],
        ),
        family=PatentFamily(
            family_id="fam-temporal",
            members=[PatentFamilyMember(country="US", doc_number="8888001", kind="B2")],
        ),
    )

    settings = SimpleNamespace(
        intended_actions=[],
        product_context={
            "commercial_action": "Already sold in 2018",
            "commercial_territories": ["US"],
            "accused_acts": [
                {
                    "act": "sale",
                    "jurisdiction": "US",
                    "start_date": "2018-01-01",
                    "end_date": "2018-12-31",
                    "actor": "Legacy seller",
                    "status": "actual",
                    "purpose": "commercial",
                    "regulatory_path": "none",
                    "instrumentality": "The accused compound",
                    "liability_theory": "direct",
                }
            ],
        },
        clearance_threshold_profile="screening",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "family_context",
            "verification",
        ],
    )
    _bind_report_analysis_context(report, settings)
    outputs = build_clearance_outputs(report, [hit], settings=settings)

    claim_decision = outputs["claim_program_decisions"][0]
    assert claim_decision.accused_acts == ["past_sale"]
    assert claim_decision.accused_acts_verified is False
    assert "accused_instrumentality_nexus" in claim_decision.missing_components
    assert outputs["clearance_decision"].decision.value == "unclear"


def test_manufacture_and_import_do_not_satisfy_method_of_treatment_claim_nexus():
    patent_id = "US8888002B2"
    method_claim = ClaimAnalysis(
        claim_number=1,
        claim_type="independent",
        preamble="A method of treating a patient",
        preamble_limiting="limiting",
        preamble_limitation_reasoning="The preamble states the method's required purpose.",
        preamble_limitation_evidence="Claim 1 expressly recites treating a patient.",
        transitional_phrase="comprising",
        overall_status=ElementStatus.MET,
        overall_confidence=0.9,
        elements=[
            ClaimElement(
                element_number=0,
                element_text="A method of treating a patient",
                status=ElementStatus.MET,
                reasoning="The claim construction treats the purpose as limiting.",
                confidence=0.9,
                evidence="Claim 1 preamble.",
            ),
            ClaimElement(
                element_number=1,
                element_text="administering compound X to the patient",
                status=ElementStatus.MET,
                reasoning="The compound identity matches, but actor facts are separate.",
                confidence=0.9,
                evidence="fixture evidence",
            ),
        ],
    )
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Literal screen lacks accused-use facts.",
                claims_analyzed=[method_claim],
            )
        ],
        source_health=SourceHealth(
            entries=[SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1)]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "1. A method of treating a patient comprising administering compound X.",
            source=PatentSource.BIGQUERY,
        ),
        sources=[PatentSource.BIGQUERY, PatentSource.EPO_SEARCH],
        jurisdiction="US",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_date": "2024-01-01",
                    "event_code": "B1",
                    "event_description": "Patent granted",
                }
            ],
        ),
        family=PatentFamily(
            family_id="fam-method",
            members=[PatentFamilyMember(country="US", doc_number="8888002", kind="B2")],
        ),
    )

    settings = SimpleNamespace(
        intended_actions=["manufacture_import"],
        product_context={
            "commercial_action": "Manufacture and import only; no treatment or administration",
            "commercial_territories": ["US"],
            "manufacturing_route": "Defined API process",
            "accused_acts": [
                {
                    "act": act,
                    "jurisdiction": "US",
                    "start_date": "2027-01-01",
                    "actor": "Praviar Pharma Ltd",
                    "status": "planned",
                    "purpose": "commercial",
                    "regulatory_path": "none",
                    "instrumentality": "The accused compound",
                    "liability_theory": "direct",
                }
                for act in ("manufacture", "import")
            ],
        },
        development_stage="commercial",
        clearance_threshold_profile="screening",
        required_record_components=[
            "claims_text",
            "claim_level_analysis",
            "family_context",
            "verification",
        ],
    )
    _bind_report_analysis_context(report, settings)
    outputs = build_clearance_outputs(report, [hit], settings=settings)

    claim_decision = outputs["claim_program_decisions"][0]
    assert claim_decision.accused_acts_verified is False
    assert "accused_instrumentality_nexus" in claim_decision.missing_components
    assert outputs["clearance_decision"].decision.value == "unclear"


def test_expired_term_conflicts_with_stale_active_status_and_prevents_blocking():
    patent_id = "US8888003B2"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="Literal product-claim screen is high.",
                claims_analyzed=[_claim_analysis(ElementStatus.MET)],
            )
        ],
        source_health=SourceHealth(
            entries=[SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1)]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "1. A compound comprising the active moiety.",
            source=PatentSource.BIGQUERY,
        ),
        sources=[PatentSource.BIGQUERY, PatentSource.EPO_SEARCH],
        jurisdiction="US",
        expiry_date="2020-01-01",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_date": "1999-01-01",
                    "event_code": "B1",
                    "event_description": "Patent granted",
                }
            ],
        ),
        family=PatentFamily(
            family_id="fam-expired",
            members=[PatentFamilyMember(country="US", doc_number="8888003", kind="B2")],
        ),
    )

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(
            intended_actions=["commercial_launch"],
            clearance_threshold_profile="screening",
            required_record_components=[
                "claims_text",
                "claim_level_analysis",
                "family_context",
                "verification",
            ],
        ),
    )

    claim_decision = outputs["claim_program_decisions"][0]
    assert claim_decision.prospective_enforceability == "unresolved"
    assert "trusted_active_legal_status" in claim_decision.missing_components
    assert outputs["clearance_decision"].decision.value == "unclear"


def test_build_clearance_outputs_fails_closed_on_source_status_conflict():
    patent_id = "EP9999998B1"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="blocking on current record",
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="epo_search",
                    status=SourceStatus.OK,
                    patent_count=1,
                ),
                SourceHealthEntry(
                    source="epo_register",
                    status=SourceStatus.OK,
                    patent_count=1,
                ),
            ]
        ),
    )
    ops_observation = trusted_ops_provenance(
        patent_id=patent_id,
        legal_status=LegalStatus.ACTIVE,
        artifact=[
            {
                "event_code": "B1",
                "event_description": "Patent granted",
            }
        ],
    )
    register_observation = trusted_register_provenance(
        patent_id=patent_id,
        artifact={"status": "Revoked"},
    )
    hit = PatentHit(
        patent_id=patent_id,
        claims_text="claim text",
        sources=[PatentSource.EPO_SEARCH],
        jurisdiction="EP",
        legal_status=LegalStatus.UNKNOWN,
        legal_status_observations=[ops_observation, register_observation],
        ep_register_status="Revoked",
        designated_states=["DE", "FR"],
    )

    outputs = build_clearance_outputs(report, [hit])

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["run_observability"].unresolved_contradictions == [
        (
            f"Decision evidence for {patent_id} conflicts with authoritative "
            "legal status observations: active, revoked."
        )
    ]
    assert "contradictory_authoritative_records" in (
        outputs["run_observability"].false_clear_risk_flags
    )
    assert any(
        reference.signal == "authoritative_legal_status_source_conflict"
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    )


def test_build_clearance_outputs_ignores_mutated_mismatched_status_provenance():
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id="EP9999999B1",
                risk_level=RiskLevel.HIGH,
                risk_summary="blocking on current record",
            )
        ],
        source_health=SourceHealth(
            entries=[SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1)]
        ),
    )
    hit = PatentHit(
        patent_id="EP9999999B1",
        claims_text="claim text",
        sources=[PatentSource.EPO_SEARCH],
        jurisdiction="EP",
        legal_status=LegalStatus.REVOKED,
        legal_status_provenance=trusted_register_provenance(
            patent_id="EP9999999B1",
            artifact={"status": "Revoked"},
        ),
        ep_register_status="Revoked",
        designated_states=["DE"],
    )
    # Defend the decision boundary even if a mutable model is corrupted after
    # construction and therefore bypasses model-time validation.
    assert hit.legal_status_provenance is not None
    object.__setattr__(hit.legal_status_provenance, "artifact_sha256", "b" * 64)

    outputs = build_clearance_outputs(report, [hit])

    assert outputs["run_observability"].unresolved_contradictions == []
    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs[
        "clearance_decision"
    ].decision_audit.claim_program_summary.claims_with_insufficient_evidence


def test_build_clearance_outputs_ignores_mutated_claim_text_provenance():
    patent_id = "US9999998B2"
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=[
            PatentAnalysis(
                patent_id=patent_id,
                risk_level=RiskLevel.HIGH,
                risk_summary="high claim-coverage screen",
                claims_analyzed=[_claim_analysis(ElementStatus.MET)],
            )
        ],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="patentsview", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    hit = PatentHit(
        patent_id=patent_id,
        **_verified_claim_fields(
            patent_id,
            "claim text",
            source=PatentSource.PATENTSVIEW,
        ),
        sources=[PatentSource.PATENTSVIEW, PatentSource.EPO_SEARCH],
        jurisdiction="US",
        legal_status=LegalStatus.ACTIVE,
        legal_status_provenance=trusted_ops_provenance(
            patent_id=patent_id,
            legal_status=LegalStatus.ACTIVE,
            artifact=[
                {
                    "event_code": "B1",
                    "event_description": "Patent granted and active",
                }
            ],
        ),
        family=PatentFamily(
            family_id="fam-998",
            members=[PatentFamilyMember(country="US", doc_number="9999998", kind="B2")],
        ),
    )
    assert hit.claims_text_provenance is not None
    object.__setattr__(hit.claims_text_provenance, "artifact_sha256", "b" * 64)

    outputs = build_clearance_outputs(
        report,
        [hit],
        settings=SimpleNamespace(intended_actions=["commercial_launch"]),
    )

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_audit.coverage_summary.patents_missing_claims == [
        patent_id
    ]
    assert outputs[
        "clearance_decision"
    ].decision_audit.claim_program_summary.claims_with_insufficient_evidence == [
        f"{patent_id}#claim1"
    ]


def test_non_authoritative_status_cannot_create_clear_or_blocked_decision():
    analyses = [
        PatentAnalysis(
            patent_id="US9999999B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking on current record",
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1)
            ]
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US9999999B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            legal_status=LegalStatus.EXPIRED,
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["run_observability"].unresolved_contradictions == []


def test_mixed_discovery_sources_cannot_launder_unbound_legal_status():
    analyses = [
        PatentAnalysis(
            patent_id="US9999999B2",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking",
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.HIGH,
        analyses=analyses,
        source_health=SourceHealth(entries=[]),
    )
    hit = PatentHit(
        patent_id="US9999999B2",
        claims_text="claim text",
        sources=[PatentSource.PUBCHEM, PatentSource.PATENTSVIEW],
        jurisdiction="US",
        legal_status=LegalStatus.EXPIRED,
    )

    outputs = build_clearance_outputs(report, [hit])

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["run_observability"].unresolved_contradictions == []


def test_build_clearance_outputs_refuses_clear_when_family_and_file_wrapper_context_are_missing():
    analyses = [
        PatentAnalysis(
            patent_id="US1111111B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        ),
        PatentAnalysis(
            patent_id="EP2222222B1",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        ),
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=2),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=2),
                SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=2),
            ]
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US1111111B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
        ),
        PatentHit(
            patent_id="EP2222222B1",
            claims_text="claim text",
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
        ),
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False
    assert any(
        "lack complete family context" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "claim-level analysis" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "lack dossier-grade file-wrapper coverage" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "lack complete register/opposition context" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert outputs["jurisdiction_decisions"][0].jurisdiction == "US"
    assert outputs["jurisdiction_decisions"][0].evidence_sufficient_for_clearance is False
    assert any(
        "lack claim-level analysis" in failure
        for failure in outputs["jurisdiction_decisions"][0].gate_failures
    )
    assert any(
        "lack dossier-grade file-wrapper coverage" in failure
        for failure in outputs["jurisdiction_decisions"][0].gate_failures
    )
    assert outputs["jurisdiction_decisions"][1].jurisdiction == "EP"
    assert outputs["jurisdiction_decisions"][1].evidence_sufficient_for_clearance is False
    assert any(
        "lack claim-level analysis" in failure
        for failure in outputs["jurisdiction_decisions"][1].gate_failures
    )
    assert any(
        "lack complete register/opposition context" in failure
        for failure in outputs["jurisdiction_decisions"][1].gate_failures
    )
    assert outputs["commercial_exposure"].damages_injunction_risk == "uncertain"
    assert {
        reference.signal
        for reference in outputs["clearance_decision"].decision_audit.decisive_references
    } >= {"missing_family_context", "missing_prosecution_context", "missing_register_context"}


def test_build_clearance_outputs_elevates_commercial_exposure_for_incomplete_orange_book_record():
    analyses = [
        PatentAnalysis(
            patent_id="US3333333B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
            claims_analyzed=[_claim_analysis()],
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US3333333B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            application_number="US10/000003",
            family=PatentFamily(
                family_id="fam-4",
                members=[PatentFamilyMember(country="US", doc_number="US333", kind="B2")],
            ),
            orange_book_listed=True,
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["commercial_exposure"].damages_injunction_risk == "uncertain"
    assert outputs["commercial_exposure"].business_severity == "medium"
    assert "does not independently elevate" in outputs["commercial_exposure"].summary


def test_build_clearance_outputs_refuses_clear_when_critic_flags_major_issue():
    analyses = [
        PatentAnalysis(
            patent_id="US7654321B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        )
    ]
    critic_report = CriticReport(
        patents_reviewed=1,
        overall_quality_score=0.62,
        findings=[
            CriticFinding(
                issue_type="confidence_calibration",
                patent_id="US7654321B2",
                severity=CriticIssueSeverity.MAJOR,
                description="Risk level appears understated relative to the claim chart.",
            )
        ],
    )
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        critic_report=critic_report,
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654321B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            application_number="US10/000002",
            transactions=[TransactionEvent(event_description="Non-final rejection")],
            family=PatentFamily(
                family_id="fam-3",
                members=[PatentFamilyMember(country="US", doc_number="US765", kind="B2")],
            ),
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert outputs["clearance_decision"].decision_audit.evidence_sufficient_for_clearance is False
    assert any(
        reason == "Critic review quality score remained below clearance grade."
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert any(
        "Critic review surfaced major or critical analysis issues" in reason
        for reason in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )
    assert outputs["jurisdiction_decisions"][0].evidence_sufficient_for_clearance is False
    assert any(
        failure == "Critic review surfaced major or critical US analysis issues."
        for failure in outputs["jurisdiction_decisions"][0].gate_failures
    )


def test_build_clearance_outputs_requires_world_class_critic_score():
    analyses = [
        PatentAnalysis(
            patent_id="US7654322B2",
            risk_level=RiskLevel.CLEAR,
            risk_summary="clear",
        )
    ]
    report = _make_report(
        overall_risk=RiskLevel.CLEAR,
        analyses=analyses,
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=1),
                SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=1),
            ]
        ),
        critic_report=CriticReport(
            patents_reviewed=1,
            overall_quality_score=0.94,
        ),
    )
    patent_hits = [
        PatentHit(
            patent_id="US7654322B2",
            claims_text="claim text",
            sources=[PatentSource.PUBCHEM],
            jurisdiction="US",
            application_number="US10/000004",
            transactions=[TransactionEvent(event_description="Non-final rejection")],
            family=PatentFamily(
                family_id="fam-world-class",
                members=[PatentFamilyMember(country="US", doc_number="US766", kind="B2")],
            ),
        )
    ]

    outputs = build_clearance_outputs(report, patent_hits)

    assert outputs["clearance_decision"].decision.value == "unclear"
    assert (
        "Critic review quality score remained below clearance grade."
        in outputs["clearance_decision"].decision_audit.insufficiency_reasons
    )


def test_claim_program_summary_uses_deterministic_patent_risk_precedence() -> None:
    patent_id = "US12345678A1"
    decisions = [
        SimpleNamespace(
            patent_id=patent_id,
            claim_number=1,
            literal_risk="high",
            doe_risk="not_assessed",
            invalidity_strength="strong",
            evidence_sufficient=True,
            legal_status_provenance_verified=True,
            prospective_enforceability="active",
            accused_acts_verified=True,
        ),
        SimpleNamespace(
            patent_id=patent_id,
            claim_number=2,
            literal_risk="high",
            doe_risk="not_assessed",
            invalidity_strength="",
            evidence_sufficient=True,
            legal_status_provenance_verified=True,
            prospective_enforceability="active",
            accused_acts_verified=True,
        ),
    ]

    summary = build_claim_program_summary(decisions + decisions)

    assert summary.total_claim_programs_reviewed == 2
    assert summary.blocking_patent_ids == [patent_id]
    assert summary.contested_patent_ids == []
    assert summary.blocking_claim_ids == [f"{patent_id}#claim2"]
    assert summary.contested_claim_ids == [f"{patent_id}#claim1"]


def test_claim_program_summary_rejects_contradictory_duplicate_decisions() -> None:
    base = {
        "patent_id": "US12345678A1",
        "claim_number": 1,
        "doe_risk": "not_assessed",
        "invalidity_strength": "",
        "evidence_sufficient": True,
        "missing_components": [],
    }
    decisions = [
        SimpleNamespace(**base, literal_risk="medium"),
        SimpleNamespace(**base, literal_risk="high"),
    ]

    with pytest.raises(ValueError, match="contradictory duplicate"):
        build_claim_program_summary(decisions)


def test_claim_program_summary_canonicalizes_identity_and_rejects_negative_claims() -> None:
    decision = SimpleNamespace(
        patent_id="US 12345678 A1",
        claim_number=1,
        literal_risk="high",
        doe_risk="not_assessed",
        invalidity_strength="",
        evidence_sufficient=True,
        missing_components=[],
        legal_status_provenance_verified=True,
        prospective_enforceability="active",
        accused_acts_verified=True,
    )
    summary = build_claim_program_summary([decision, decision])
    assert summary.total_claim_programs_reviewed == 1
    assert summary.blocking_patent_ids == ["US12345678A1"]

    decision.claim_number = -1
    with pytest.raises(ValueError, match="cannot be negative"):
        build_claim_program_summary([decision])


@pytest.mark.parametrize("reverse", [False, True])
def test_claim_program_summary_rejects_whole_document_and_positive_claim_coexistence(
    reverse: bool,
) -> None:
    base = {
        "patent_id": "US12345678A1",
        "literal_risk": "medium",
        "doe_risk": "not_assessed",
        "invalidity_strength": "",
        "evidence_sufficient": False,
        "missing_components": ["claims_text"],
    }
    decisions = [
        SimpleNamespace(**base, claim_number=0),
        SimpleNamespace(**base, claim_number=1),
    ]
    if reverse:
        decisions.reverse()

    with pytest.raises(ValueError, match="fallback cannot coexist"):
        build_claim_program_summary(decisions)


def test_claim_program_summary_counts_whole_document_only_as_fallback() -> None:
    decision = SimpleNamespace(
        patent_id="US12345678A1",
        claim_number=0,
        literal_risk="medium",
        doe_risk="not_assessed",
        invalidity_strength="",
        evidence_sufficient=False,
        missing_components=["claims_text"],
    )

    summary = build_claim_program_summary([decision, decision])

    assert summary.total_claim_programs_reviewed == 0
    assert summary.patent_level_fallback_count == 1
    assert summary.medium_risk_claim_ids == ["US12345678A1"]


def test_decisive_references_include_every_blocking_patent() -> None:
    patent_ids = [f"US{index:08d}A1" for index in range(1, 6)]
    coverage = SimpleNamespace(
        reviewed_patent_ids=patent_ids,
        queried_source_names=["patentsview"],
        successful_source_names=["patentsview"],
        failed_source_names=[],
        patents_missing_claims=[],
        patents_missing_claim_level_analysis=[],
        patents_missing_authoritative_records=[],
        patents_missing_family_context=[],
        us_patents_missing_prosecution_context=[],
        us_patents_missing_file_wrapper_dossier=[],
        ep_patents_missing_register_context=[],
        failed_analysis_patent_ids=[],
        verification_gaps=[],
        reviewed_us_patent_ids=patent_ids,
        reviewed_ep_patent_ids=[],
    )
    analyses = {
        patent_id: SimpleNamespace(
            risk_level=SimpleNamespace(value="high"),
            risk_summary="Material blocker.",
        )
        for patent_id in patent_ids
    }

    references = build_decisive_references(
        decision=SimpleNamespace(value="blocked"),
        analyses_by_id=analyses,
        detail_map={},
        coverage_summary=coverage,
        blocking_patent_ids=patent_ids,
        prosecution_findings=[],
        future_risk=[],
    )

    assert {
        reference.patent_id
        for reference in references
        if reference.category.value == "blocking_patent"
    } == set(patent_ids)
