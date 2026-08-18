from __future__ import annotations

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.critic import CriticFinding, CriticIssueSeverity, CriticReport
from praviar_pipeline.models.patent import (
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
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.pipeline.report.evidence_index import build_matter_evidence_index
from tests.claim_text_test_helpers import trusted_claim_text_fields


def _verified_claim_fields(
    patent_id: str,
    claims_text: str,
    *,
    source: PatentSource,
) -> dict:
    return trusted_claim_text_fields(
        patent_id,
        claims_text,
        source=source,
    )


def test_build_matter_evidence_index_collects_material_patent_and_family_inventory():
    analyses = [
        PatentAnalysis(
            patent_id="US1234567B2",
            title="US blocking patent",
            risk_level=RiskLevel.HIGH,
            risk_summary="blocking",
            analysis_quality_gate_failures=["evaluator_initial_evaluation_failed"],
            analysis_review_required=True,
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.82,
                )
            ],
        ),
        PatentAnalysis(
            patent_id="EP2345678B1",
            title="EP monitoring patent",
            risk_level=RiskLevel.LOW,
            risk_summary="monitor",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.NOT_MET,
                    overall_confidence=0.71,
                )
            ],
        ),
    ]
    doe_assessments = []
    invalidity_assessments = []
    analysis_failures = [
        AnalysisFailure(
            patent_id="US9999999A1",
            step="step4",
            error_type="TimeoutError",
            error_message="timed out",
        )
    ]
    patent_hits = [
        PatentHit(
            patent_id="US1234567B2",
            title="US blocking patent",
            **_verified_claim_fields(
                "US1234567B2",
                "claim text",
                source=PatentSource.BIGQUERY,
            ),
            sources=[PatentSource.PUBCHEM, PatentSource.BIGQUERY],
            jurisdiction="US",
            assignees=["Acme Pharma"],
            application_number="12/345678",
            transactions=[TransactionEvent(event_description="Amendment after final")],
            family=PatentFamily(
                family_id="fam-1",
                members=[
                    PatentFamilyMember(country="US", doc_number="1234567", kind="B2"),
                    PatentFamilyMember(country="US", doc_number="9999999", kind="A1"),
                    PatentFamilyMember(country="EP", doc_number="2345678", kind="B1"),
                ],
            ),
            family_broadest=True,
            ptab_proceedings=[PTABProceeding(proceeding_number="IPR2025-0001")],
            orange_book_listed=True,
            patent_term_info=PatentTermInfo(
                patent_id="US1234567B2",
                terminal_disclaimer=True,
            ),
        ),
        PatentHit(
            patent_id="EP2345678B1",
            title="EP monitoring patent",
            **_verified_claim_fields(
                "EP2345678B1",
                "ep claims",
                source=PatentSource.EPO_SEARCH,
            ),
            sources=[PatentSource.EPO_SEARCH],
            jurisdiction="EP",
            family=PatentFamily(
                family_id="fam-1",
                members=[
                    PatentFamilyMember(country="US", doc_number="1234567", kind="B2"),
                    PatentFamilyMember(country="EP", doc_number="2345678", kind="B1"),
                ],
            ),
            designated_states=["DE", "FR"],
            opposition_events=[],
            priority_claims=[],
        ),
    ]
    critic_report = CriticReport(
        patents_reviewed=2,
        overall_quality_score=0.8,
        findings=[
            CriticFinding(
                issue_type="confidence_calibration",
                patent_id="US1234567B2",
                severity=CriticIssueSeverity.MAJOR,
                description="Risk calibration still needs review.",
            )
        ],
    )
    source_health = SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=2),
            SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=2),
            SourceHealthEntry(source="epo_search", status=SourceStatus.OK, patent_count=1),
        ]
    )

    index = build_matter_evidence_index(
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        patent_hits=patent_hits,
        prosecution_dossiers=[
            {
                "patent_id": "US1234567B2",
                "jurisdiction": "US",
                "application_number": "12/345678",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions", "continuity", "amendments"],
                "office_actions_summary": "- [CTNF] Non-final office action",
                "continuity_summary": "- Parent: 11/111111",
                "amendments_summary": "- [AMND] Amendment after final",
                "office_action_count": 1,
                "continuity_entry_count": 1,
                "amendment_entry_count": 1,
                "narrowing_signal": True,
                "terminal_disclaimer": True,
                "terminal_disclaimer_linked_patent": "",
                "ptab_challenged": True,
                "pending_family_signal": True,
                "record_basis": ["uspto_odp", "application_number", "uspto_transactions"],
                "summary": "file-wrapper dossier captured",
            }
        ],
        critic_report=critic_report,
        source_health=source_health,
    )

    assert index.material_patent_count == 3
    assert index.family_count == 1
    assert index.analysis_failure_patent_ids == ["US9999999A1"]
    assert index.critic_flagged_patent_ids == ["US1234567B2"]

    us_record = next(record for record in index.patent_records if record.patent_id == "US1234567B2")
    assert us_record.has_us_prosecution_context is True
    assert us_record.has_us_file_wrapper_dossier is True
    assert us_record.prosecution_dossier_sections == [
        "office_actions",
        "continuity",
        "amendments",
    ]
    assert us_record.has_ptab_proceedings is True
    assert us_record.has_orange_book_listing is True
    assert us_record.family_id == "fam-1"
    assert set(us_record.authoritative_source_names) == {"orange_book", "ptab", "uspto_odp"}
    assert us_record.supporting_source_names == ["bigquery", "pubchem"]
    assert set(us_record.authoritative_record_categories) >= {
        "family_record",
        "orange_book_record",
        "ptab_record",
        "us_file_wrapper_dossier",
        "us_prosecution_record",
    }
    assert set(us_record.prosecution_signals) >= {
        "file_wrapper_dossier",
        "narrowing_signal",
        "pending_family_signal",
        "ptab_challenged",
        "terminal_disclaimer",
    }
    assert {status.component: status.status.value for status in us_record.component_statuses} == {
        "claims_text": "collected",
        "family_context": "collected",
        "authoritative_records": "collected",
        "claim_level_analysis": "collected",
        "doe_assessment": "missing",
        "invalidity_assessment": "missing",
        "ptab_record": "collected",
        "orange_book_record": "collected",
        "us_prosecution_context": "collected",
        "us_file_wrapper_dossier": "collected",
        "ep_register_context": "not_applicable",
    }
    assert set(us_record.future_risk_signals) >= {"pending_family", "terminal_disclaimer"}
    assert us_record.critic_issue_severities == ["major"]
    assert us_record.clearance_grade_ready is False
    assert set(us_record.gate_failures) >= {
        "blocking_patent_missing_doe_assessment",
        "blocking_patent_missing_invalidity_assessment",
        "critic_major_issue",
        "evaluator_initial_evaluation_failed",
    }

    ep_record = next(record for record in index.patent_records if record.patent_id == "EP2345678B1")
    assert ep_record.has_ep_register_context is True
    assert ep_record.authoritative_source_names == ["epo_search", "epo_register"]
    assert ep_record.clearance_grade_ready is False
    assert ep_record.gate_failures == ["missing_claims_text"]

    failed_record = next(
        record for record in index.patent_records if record.patent_id == "US9999999A1"
    )
    assert failed_record.analysis_completed is False
    assert failed_record.analysis_failed is True
    assert failed_record.clearance_grade_ready is False
    assert set(failed_record.gate_failures) >= {"analysis_failed"}
    assert {status.component: status.status.value for status in failed_record.component_statuses}[
        "claim_level_analysis"
    ] == "failed"

    family_record = index.family_records[0]
    assert family_record.family_id == "fam-1"
    assert family_record.broadest_patent_id == "US1234567B2"
    assert family_record.pending_member_count == 1
    assert family_record.blocking_patent_ids == ["US1234567B2"]
    assert family_record.orange_book_listed_patent_ids == ["US1234567B2"]
    assert set(family_record.authoritative_record_categories) >= {
        "ep_register_record",
        "family_record",
        "orange_book_record",
        "ptab_record",
        "us_file_wrapper_dossier",
        "us_prosecution_record",
    }
    assert family_record.clearance_grade_ready is False
    assert family_record.clearance_grade_ready_patent_ids == []
    assert family_record.incomplete_patent_ids == ["US1234567B2", "EP2345678B1"]
    assert family_record.gate_failures == ["incomplete_material_patent_records"]
    assert {
        status.component: status.status.value for status in family_record.component_statuses
    } == {
        "family_context": "collected",
        "claims_text": "missing",
        "claim_level_analysis": "collected",
        "authoritative_records": "collected",
    }

    assert set(index.authoritative_source_names) == {
        "epo_register",
        "epo_search",
        "orange_book",
        "ptab",
        "uspto_odp",
    }
    assert set(index.supporting_source_names) == {"bigquery", "pubchem"}
    assert index.clearance_grade_ready_patent_ids == []
    assert set(index.incomplete_patent_ids) == {
        "EP2345678B1",
        "US1234567B2",
        "US9999999A1",
    }
    assert index.clearance_grade_ready_family_ids == []
    assert index.incomplete_family_ids == ["fam-1"]
