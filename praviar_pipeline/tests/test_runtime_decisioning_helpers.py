from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.patent import LegalStatus, PatentSource
from praviar_pipeline.models.report import (
    ClearanceOutcome,
    DecisionEvidenceCategory,
    EvidenceCoverageSummary,
)
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.pipeline.runtime.decisioning_coverage import (
    _future_risk_sort_key,
    _prosecution_sort_key,
    build_verification_gaps,
)
from praviar_pipeline.pipeline.runtime.decisioning_references import build_decisive_references
from tests.legal_status_test_helpers import trusted_ops_provenance


def test_build_verification_gaps_collects_check_and_summary_failures() -> None:
    report = SimpleNamespace(
        verification=VerificationResult(
            checks=[
                VerificationCheck(
                    check_name="citations",
                    passed=False,
                    severity="fail",
                    details="Missing grounding",
                ),
                VerificationCheck(check_name="claims", passed=True, severity="pass"),
            ],
            all_citations_valid=False,
            all_claims_grounded=True,
            all_entities_valid=False,
            dates_consistent=True,
            risk_levels_justified=False,
            issues=["Primary verification issue"],
        )
    )

    gaps = build_verification_gaps(report)

    assert "Primary verification issue" in gaps
    assert "citations: Missing grounding" in gaps
    assert "Citation validation did not fully pass." in gaps
    assert "Entity validation did not fully pass." in gaps
    assert "Risk-justification validation did not fully pass." in gaps


def test_build_decisive_references_captures_empty_record_gaps() -> None:
    references = build_decisive_references(
        decision=ClearanceOutcome.UNCLEAR,
        analyses_by_id={},
        detail_map={},
        coverage_summary=EvidenceCoverageSummary(),
        blocking_patent_ids=[],
        prosecution_findings=[],
        future_risk=[],
    )

    assert {reference.category for reference in references} == {
        DecisionEvidenceCategory.COVERAGE_GAP
    }
    assert {reference.signal for reference in references} == {
        "no_material_patents",
        "no_search_sources",
    }


def test_build_decisive_references_uses_record_basis_and_new_gap_signals() -> None:
    legal_status_provenance = trusted_ops_provenance(
        patent_id="US1234567B2",
        legal_status=LegalStatus.REVOKED,
        artifact=[
            {
                "event_date": "2025-01-01",
                "event_code": "REVOKED_FINAL",
                "event_description": "Patent revoked",
            }
        ],
    )
    references = build_decisive_references(
        decision=ClearanceOutcome.UNCLEAR,
        analyses_by_id={
            "US1234567B2": SimpleNamespace(
                patent_id="US1234567B2",
                risk_level=RiskLevel.HIGH,
                risk_summary="blocking composition claim",
            )
        },
        detail_map={
            "US1234567B2": SimpleNamespace(
                patent_id="US1234567B2",
                legal_status=LegalStatus.REVOKED,
                legal_status_provenance=legal_status_provenance,
                sources=[PatentSource.EPO_SEARCH],
                ep_register_status="",
            )
        },
        coverage_summary=EvidenceCoverageSummary(
            reviewed_patent_ids=["US1234567B2"],
            patents_missing_claim_level_analysis=["US1234567B2"],
            patents_missing_authoritative_records=["US1234567B2"],
            us_patents_missing_file_wrapper_dossier=["US1234567B2"],
        ),
        blocking_patent_ids=["US1234567B2"],
        prosecution_findings=[
            SimpleNamespace(
                patent_id="US1234567B2",
                jurisdiction="US",
                narrowing_signal=True,
                terminal_disclaimer=True,
                pending_family_signal=False,
                ptab_challenged=False,
                record_basis=["application_number", "patent_term_info"],
                summary="terminal disclaimer present",
            )
        ],
        future_risk=[
            SimpleNamespace(
                patent_id="US1234567B2",
                jurisdiction="US",
                risk_type="pending_family",
                record_basis=["family_members"],
                summary="pending family members remain open",
            )
        ],
    )

    assert any(
        reference.category == DecisionEvidenceCategory.PROSECUTION_SIGNAL
        and reference.source_name == "patent_term_info"
        for reference in references
    )
    assert any(
        reference.category == DecisionEvidenceCategory.FUTURE_RISK
        and reference.source_name == "family_members"
        for reference in references
    )
    assert {
        reference.signal
        for reference in references
        if reference.category == DecisionEvidenceCategory.COVERAGE_GAP
    } >= {
        "authoritative_legal_status_conflict",
        "missing_claim_level_analysis",
        "missing_authoritative_record_support",
        "missing_file_wrapper_dossier",
    }


def test_sort_keys_keep_us_prosecution_and_pending_family_first() -> None:
    prosecution = sorted(
        [
            SimpleNamespace(jurisdiction="EP", patent_id="EP2345678B1"),
            SimpleNamespace(jurisdiction="US", patent_id="US1234567B2"),
        ],
        key=_prosecution_sort_key,
    )
    assert [finding.patent_id for finding in prosecution] == [
        "US1234567B2",
        "EP2345678B1",
    ]

    future_risk = sorted(
        [
            SimpleNamespace(
                jurisdiction="US",
                patent_id="US1234567B2",
                risk_type="terminal_disclaimer",
            ),
            SimpleNamespace(
                jurisdiction="EP",
                patent_id="EP2345678B1",
                risk_type="ep_opposition",
            ),
            SimpleNamespace(
                jurisdiction="US",
                patent_id="US1234567B2",
                risk_type="pending_family",
            ),
        ],
        key=_future_risk_sort_key,
    )
    assert [finding.risk_type for finding in future_risk] == [
        "pending_family",
        "terminal_disclaimer",
        "ep_opposition",
    ]
