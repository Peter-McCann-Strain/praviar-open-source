from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.pipeline.runtime.decisioning_signals import (
    PatentDetailSignals,
    build_future_risk_findings,
    build_prosecution_finding,
    extract_patent_detail_signals,
)


def test_extract_patent_detail_signals_collects_basis_and_ep_events() -> None:
    detail = SimpleNamespace(
        application_number="US10/000001",
        transactions=[
            SimpleNamespace(event_description="Amendment after final"),
            SimpleNamespace(event_description="Notice of allowance"),
        ],
        examiner="Examiner",
        attorney="Attorney",
        ptab_proceedings=[SimpleNamespace(proceeding_number="IPR2025-0001")],
        family=SimpleNamespace(
            members=[
                SimpleNamespace(
                    country="US",
                    doc_number="1234567",
                    kind="A1",
                    application_number="US16123456",
                    application_identity_verified=True,
                ),
                SimpleNamespace(country="EP", doc_number="EP7654321", kind="B1"),
            ]
        ),
        legal_events=[
            SimpleNamespace(
                event_date="2025-01-01", event_code="OPP", event_description="Opposition filed"
            ),
            SimpleNamespace(
                event_date="2025-01-01", event_code="OPP", event_description="Opposition filed"
            ),
            SimpleNamespace(
                event_date="2025-02-01", event_code="REV", event_description="Patent revoked"
            ),
        ],
        ep_register_status="Pending",
        patent_term_info=SimpleNamespace(
            terminal_disclaimer=True,
            td_linked_patent="US7654321B2",
        ),
    )

    signals = extract_patent_detail_signals(detail)

    assert signals.transaction_count == 2
    assert signals.amendment_event_count == 1
    assert signals.pending_family_member_ids == ["US1234567A1"]
    assert signals.ep_opposition_event_count == 1
    assert signals.ep_revocation_event_count == 1
    assert signals.record_basis == [
        "application_number",
        "uspto_transactions",
        "examiner_metadata",
        "attorney_metadata",
        "ptab_proceedings",
        "family_members",
        "epo_register",
        "patent_term_info",
    ]


def test_granted_publication_supersedes_same_application_family_a_publication() -> None:
    detail = SimpleNamespace(
        application_number="US10/000001",
        transactions=[],
        ptab_proceedings=[],
        family=SimpleNamespace(
            members=[
                SimpleNamespace(
                    country="US",
                    doc_number="20200123456",
                    kind="A1",
                    application_number="US16123456",
                    application_identity_verified=True,
                ),
                SimpleNamespace(
                    country="US",
                    doc_number="11223344",
                    kind="B2",
                    application_number="US16123456",
                    application_identity_verified=True,
                ),
            ]
        ),
        legal_events=[],
        opposition_events=[],
        ep_register_status="",
    )

    signals = extract_patent_detail_signals(detail)

    assert signals.pending_family_signal is False
    assert signals.pending_family_member_ids == []


def test_unverified_a_publication_is_unresolved_not_assumed_pending() -> None:
    detail = SimpleNamespace(
        application_number="US10/000001",
        transactions=[],
        ptab_proceedings=[],
        family=SimpleNamespace(
            members=[
                SimpleNamespace(country="US", doc_number="20200123456", kind="A1"),
                SimpleNamespace(country="US", doc_number="11223344", kind="B2"),
            ]
        ),
        legal_events=[],
        opposition_events=[],
        ep_register_status="",
    )

    signals = extract_patent_detail_signals(detail)

    assert signals.pending_family_signal is False
    assert signals.pending_family_member_ids == []
    assert signals.unresolved_family_identity_signal is True
    assert signals.unresolved_family_member_ids == ["US20200123456A1"]


def test_build_prosecution_finding_uses_dossier_and_signal_basis() -> None:
    signals = PatentDetailSignals(
        application_number="US10/000001",
        prosecution_available=True,
        transaction_count=3,
        amendment_event_count=2,
        narrowing_signal=True,
        terminal_disclaimer=True,
        terminal_disclaimer_linked_patent="US7654321B2",
        ptab_challenged=True,
        ptab_proceeding_numbers=["IPR2025-0001"],
        pending_family_signal=True,
        pending_family_member_ids=["US1234567A1"],
        ep_register_status="",
        ep_opposition_event_count=0,
        ep_limitation_event_count=0,
        ep_revocation_event_count=0,
        ep_lapse_event_count=0,
        record_basis=["application_number", "uspto_transactions", "ptab_proceedings"],
    )
    dossier = {
        "source_name": "uspto_odp",
        "sections_available": ["office_actions", "continuity"],
        "office_action_types": ["non_final_office_action"],
        "amendment_types": ["claim_amendment"],
        "continuity_types": ["continuation"],
        "rejected_claim_numbers": ["1", "3"],
        "narrowing_claim_numbers": [1],
        "rejection_bases": ["103"],
        "estoppel_risk_flags": ["after_final_response_history"],
        "office_action_count": 2,
        "continuity_entry_count": 1,
        "continuation_parent_count": 1,
        "response_after_final_count": 1,
        "rce_count": 1,
    }

    finding = build_prosecution_finding(
        patent_id="US1234567B2",
        jurisdiction="US",
        signals=signals,
        dossier=dossier,
    )

    assert finding is not None
    assert finding.record_basis == [
        "uspto_odp",
        "application_number",
        "uspto_transactions",
        "ptab_proceedings",
    ]
    assert finding.office_action_types == ["non_final_office_action"]
    assert finding.rejected_claim_numbers == [1, 3]
    assert "rejection bases: 103" in finding.summary
    assert "doctrine flags: after final response history" in finding.summary


def test_build_future_risk_findings_captures_us_and_ep_future_signals() -> None:
    signals = PatentDetailSignals(
        application_number="",
        prosecution_available=False,
        transaction_count=0,
        amendment_event_count=0,
        narrowing_signal=False,
        terminal_disclaimer=True,
        terminal_disclaimer_linked_patent="US7654321B2",
        ptab_challenged=False,
        ptab_proceeding_numbers=[],
        pending_family_signal=True,
        pending_family_member_ids=["US1234567A1"],
        ep_register_status="Pending",
        ep_opposition_event_count=1,
        ep_limitation_event_count=0,
        ep_revocation_event_count=0,
        ep_lapse_event_count=0,
        record_basis=["family_members", "patent_term_info", "epo_register"],
    )

    findings = build_future_risk_findings(
        patent_id="EP1234567B1",
        jurisdiction="EP",
        risk_level=RiskLevel.MEDIUM,
        signals=signals,
    )

    assert {finding.risk_type for finding in findings} == {
        "pending_family",
        "terminal_disclaimer",
        "ep_opposition",
    }
    by_type = {finding.risk_type: finding for finding in findings}
    assert by_type["pending_family"].severity == "high"
    assert by_type["terminal_disclaimer"].related_patent_ids == ["US7654321B2"]
    assert by_type["ep_opposition"].record_basis == ["epo_register"]
