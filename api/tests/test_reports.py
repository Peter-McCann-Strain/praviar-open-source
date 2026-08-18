"""Tests for /api/v1/reports endpoints."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, valid_report_data, valid_report_data_for_patents

from api.db.models import (
    AnalysisStatus,
    AuditLog,
    ExportFormat,
    ExportJob,
    ExportStatus,
    ReviewStatus,
    UserRole,
)
from api.deps import PERMISSION_MATRIX
from api.services.export_receipts import export_manifest_hash, export_manifest_signature
from api.services.licensed_family_overlay import LicensedFamilyOverlayRuntimeConfig
from api.services.report_access import report_payload_fingerprint


def _configure_report_content_queries(db: AsyncMock, analysis: MagicMock) -> None:
    """Model the status, JSON payload, and full-row reads used by report loading."""
    status_result = MagicMock()
    status_result.scalar_one_or_none.return_value = analysis.status
    report_data_result = MagicMock()
    report_data_result.scalar_one_or_none.return_value = analysis.report_data
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    db.execute.side_effect = [status_result, report_data_result, analysis_result]


# ---------------------------------------------------------------------------
# GET /api/v1/reports/resolve/{identifier}
# ---------------------------------------------------------------------------


class TestResolveReportIdentity:
    @pytest.mark.asyncio
    async def test_resolves_uuid_report_id_to_owning_analysis(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_id = str(uuid.uuid4())
        report = valid_report_data(report_id=report_id)
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=report,
        )
        direct_lookup = MagicMock()
        direct_lookup.scalar_one_or_none.return_value = None
        report_lookup = MagicMock()
        report_lookup.scalar_one_or_none.return_value = analysis
        db.execute.side_effect = [direct_lookup, report_lookup]

        response = await c.get(f"/api/v1/reports/resolve/{report_id}")

        assert response.status_code == 200
        assert response.json() == {
            "analysis_id": str(analysis_id),
            "report_id": report_id,
            "matched_by": "report_id",
        }
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_prefers_direct_analysis_identity(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_id = str(uuid.uuid4())
        report = valid_report_data(report_id=report_id)
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=report,
        )
        direct_lookup = MagicMock()
        direct_lookup.scalar_one_or_none.return_value = analysis
        db.execute.return_value = direct_lookup

        response = await c.get(f"/api/v1/reports/resolve/{analysis_id}")

        assert response.status_code == 200
        assert response.json() == {
            "analysis_id": str(analysis_id),
            "report_id": report_id,
            "matched_by": "analysis_id",
        }
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_unknown_reference_is_terminal_not_found(self, attorney_client):
        c, db = attorney_client
        missing_lookup = MagicMock()
        missing_lookup.scalar_one_or_none.return_value = None
        db.execute.return_value = missing_lookup

        response = await c.get(f"/api/v1/reports/resolve/{uuid.uuid4()}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Report reference not found"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status_value", "report_data"),
        [
            (AnalysisStatus.RUNNING, None),
            (AnalysisStatus.COMPLETED, {}),
            (AnalysisStatus.COMPLETED, {"report_id": "unverified-report"}),
        ],
    )
    async def test_incomplete_or_unpublishable_reference_is_terminal_not_found(
        self,
        attorney_client,
        status_value,
        report_data,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            status=status_value,
            report_data=report_data,
        )
        direct_lookup = MagicMock()
        direct_lookup.scalar_one_or_none.return_value = analysis
        db.execute.return_value = direct_lookup

        response = await c.get(f"/api/v1/reports/resolve/{analysis_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Report reference not found"


# ---------------------------------------------------------------------------
# GET /api/v1/reports/{analysis_id}
# ---------------------------------------------------------------------------


class TestGetReport:
    @pytest.mark.asyncio
    async def test_get_report_restricts_non_attorney_conclusions(self, scientist_client):
        c, db = scientist_client
        aid = uuid.uuid4()
        report = valid_report_data()
        analysis = make_analysis_mock(id=aid, report_data=report)
        _configure_report_content_queries(db, analysis)

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 403
        assert "use the report summary" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_preserves_canonical_blocker_families(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        report = valid_report_data_for_patents(
            [
                {
                    "patent_id": "US12345678A1",
                    "risk_level": "high",
                }
            ]
        )
        analysis = make_analysis_mock(id=aid, report_data=report)
        _configure_report_content_queries(db, analysis)

        response = await c.get(f"/api/v1/reports/{aid}")

        assert response.status_code == 200
        blocker_families = response.json()["clearance_decision"]["decision_audit"][
            "blocker_families"
        ]
        assert blocker_families[0]["family_id"] == "fam-123"
        assert blocker_families[0]["blocking_claims"][0]["claim_id"] == ("US12345678A1#claim1")

    @pytest.mark.asyncio
    async def test_get_report_attorney_sees_structured_decision(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        report = valid_report_data(
            patent_analyses=[
                {
                    "patent_id": "US12345678A1",
                    "title": "Aspirin formulation patent",
                    "assignee": "Example Pharma",
                    "risk_level": "medium",
                    "risk_summary": "Scaffold overlap remains plausible.",
                    "input_tokens": 210,
                    "output_tokens": 55,
                }
            ],
            doe_assessments=[
                {
                    "patent_id": "US12345678A1",
                    "claim_number": 1,
                    "element_number": 2,
                    "element_text": "acetylsalicylic acid core",
                    "estoppel": {
                        "amendments_found": ["Narrowing amendment to claim 1"],
                        "estoppel_applies": False,
                        "surrendered_scope": "",
                        "file_wrapper_available": True,
                        "rejections_found": ["103"],
                        "prosecution_narrowing_count": 1,
                    },
                    "fwr": {
                        "same_function": True,
                        "function_reasoning": "Performs the same antiplatelet function.",
                        "same_way": True,
                        "way_reasoning": "Acts through the same acetylating mechanism.",
                        "same_result": True,
                        "result_reasoning": "Produces the same therapeutic result.",
                        "equivalent": True,
                        "chemical_context": {
                            "structural_relationship": "bioisostere",
                            "relationship_reasoning": "Close scaffold substitution.",
                            "known_interchangeability": True,
                            "interchangeability_evidence": "Literature supports interchangeability.",
                        },
                    },
                    "overall_equivalent": True,
                    "confidence": 0.74,
                    "confidence_band": "MODERATE",
                    "reasoning": "Equivalent under the FWR test with no estoppel bar identified.",
                }
            ],
            invalidity_assessments=[
                {
                    "patent_id": "US12345678A1",
                    "claim_numbers": [1],
                    "ptab": {
                        "has_been_challenged": True,
                        "proceedings": [
                            {
                                "proceeding_number": "IPR2025-0001",
                                "type": "IPR",
                                "status": "Instituted",
                                "claims_challenged": [1],
                                "claims_cancelled": [],
                                "claims_survived": [],
                                "outcome_summary": "Institution decision found a reasonable likelihood of success.",
                            }
                        ],
                        "all_claims_cancelled": [],
                    },
                    "prior_art": [
                        {
                            "reference_id": "WO2020123456A1",
                            "title": "Earlier aspirin formulation disclosure",
                            "relevance": "Discloses overlapping scaffold and dosage form.",
                            "anticipation_score": 0.41,
                            "obviousness_score": 0.77,
                            "reference_type": "patent",
                            "source_database": "lens",
                        }
                    ],
                    "written_description_issues": [
                        "Genus support appears thin for the full claim scope."
                    ],
                    "claim_charts": [
                        {
                            "patent_id": "US12345678A1",
                            "claim_number": 1,
                            "prior_art_reference_id": "WO2020123456A1",
                            "entries": [
                                {
                                    "element_number": 1,
                                    "element_text": "Aspirin composition",
                                    "prior_art_reference_id": "WO2020123456A1",
                                    "prior_art_disclosure": "Discloses aspirin composition in Example 3.",
                                    "citation_location": "Example 3",
                                    "disclosed": "yes",
                                    "notes": "",
                                }
                            ],
                            "all_elements_disclosed": True,
                            "chart_summary": "Reference discloses the key independent claim element.",
                        }
                    ],
                    "graham_factors": {
                        "scope_and_content": "Prior art shows closely related aspirin formulations.",
                        "differences_from_prior_art": "Limited excipient differences remain.",
                        "level_of_ordinary_skill": "Formulation scientist with patent drafting support.",
                        "overall_obviousness_assessment": "Moderate to strong obviousness argument.",
                    },
                    "enablement_screening": {
                        "genus_claim_detected": True,
                        "genus_indicators": ["broad excipient class"],
                        "specification_enables_full_scope": "unclear",
                        "amgen_v_sanofi_flags": [
                            "working examples are narrow relative to the claim breadth"
                        ],
                        "reasoning": "Enablement support is mixed.",
                    },
                    "overall_invalidity_strength": "moderate",
                    "reasoning": "Prior art and PTAB posture support a non-frivolous invalidity challenge.",
                    "confidence": 0.69,
                    "confidence_band": "MODERATE",
                    "screening_disclaimer": "screening only",
                }
            ],
            verification_summary={
                "total_claims_checked": 8,
                "claims_correct": 8,
                "claims_incorrect": 0,
                "claims_unverifiable": 0,
                "factual_accuracy_rate": 1.0,
                "corrections_needed": [],
                "omissions_found": [],
                "overall_assessment": "PASS_WITH_CORRECTIONS",
            },
        )
        analysis = make_analysis_mock(id=aid, report_data=report)
        _configure_report_content_queries(db, analysis)

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["clearance_decision"]["decision"] == "unclear"
        assert data["decision_scope"]["jurisdictions"] == ["US"]
        assert data["decision_scope"]["supports_positive_clearance"] is True
        assert data["supporting_scope"]["jurisdictions"] == []
        assert data["certification_scope"]["certified_jurisdictions"] == ["US", "EP"]
        assert data["certification_scope"]["supported_jurisdictions"] == [
            "US",
            "EP",
            "UK",
            "IN",
            "JP",
            "CN",
        ]
        assert data["certification_scope"]["current_matter_type_certified"] is True
        assert data["cohort_status"] == "certified"
        assert data["jurisdiction_decisions"][0]["jurisdiction"] == "US"
        assert data["jurisdiction_decisions"][0]["evidence_sufficient_for_clearance"] is False
        assert data["jurisdiction_decisions"][0]["supports_positive_clearance"] is True
        assert data["jurisdiction_decisions"][0]["lane_status"] == "counsel_ready"
        assert data["jurisdiction_decisions"][0]["local_review_required"] is False
        assert data["jurisdiction_decisions"][0]["authority_grade"] == "authoritative"
        assert data["jurisdiction_decisions"][0]["gate_failures"] == [
            "Evidence remains mixed across the reviewed US record."
        ]
        assert data["matter_evidence_index"]["material_patent_count"] == 1
        assert data["matter_evidence_index"]["authoritative_source_names"] == ["patentsview"]
        assert data["matter_evidence_index"]["incomplete_family_ids"] == ["fam-123"]
        assert data["matter_evidence_index"]["family_records"][0]["family_id"] == "fam-123"
        assert data["matter_evidence_index"]["patent_records"][0]["clearance_grade_ready"] is False
        assert data["matter_evidence_index"]["patent_records"][0]["gate_failures"] == [
            "blocking_patent_missing_doe_assessment",
            "blocking_patent_missing_invalidity_assessment",
            "critic_major_issue",
        ]
        patent_component_statuses = {
            item["component"]: item
            for item in data["matter_evidence_index"]["patent_records"][0]["component_statuses"]
        }
        family_component_statuses = {
            item["component"]: item
            for item in data["matter_evidence_index"]["family_records"][0]["component_statuses"]
        }
        assert patent_component_statuses["claims_text"] == {
            "component": "claims_text",
            "status": "collected",
            "source_name": "patentsview",
            "authority_expected": True,
            "required_before_clear": True,
            "note": "Claims text is present for this patent.",
        }
        assert patent_component_statuses["authoritative_records"] == {
            "component": "authoritative_records",
            "status": "collected",
            "source_name": "authoritative_record",
            "authority_expected": True,
            "required_before_clear": True,
            "note": "Authoritative record support is available for this patent.",
        }
        assert family_component_statuses["claim_level_analysis"] == {
            "component": "claim_level_analysis",
            "status": "collected",
            "source_name": "step4_analyze",
            "authority_expected": False,
            "required_before_clear": True,
            "note": "Claim-level analysis is complete across the material family.",
        }
        assert data["clearance_decision"]["decision_audit"]["coverage_summary"][
            "reviewed_patent_ids"
        ] == ["US12345678A1"]
        assert data["clearance_decision"]["decision_audit"]["authoritative_sources_count"] == 1
        assert data["clearance_decision"]["decision_audit"]["coverage_summary"][
            "authoritative_source_names"
        ] == ["patentsview"]
        assert data["clearance_decision"]["decision_audit"]["coverage_summary"][
            "incomplete_patent_ids"
        ] == ["US12345678A1"]
        assert (
            data["clearance_decision"]["decision_audit"]["decisive_references"][0]["category"]
            == "prosecution_signal"
        )
        assert data["prosecution_findings"][0]["transaction_count"] == 4
        assert data["prosecution_findings"][0]["office_action_types"] == ["non_final_office_action"]
        assert data["prosecution_findings"][0]["estoppel_risk_flags"] == [
            "after_final_response_history",
            "rce_history",
            "continuation_lineage",
            "prior_art_rejection_history",
        ]
        assert data["prosecution_findings"][0]["record_basis"] == [
            "application_number",
            "uspto_transactions",
            "family_members",
        ]
        assert data["prosecution_dossiers"][0]["sections_available"] == [
            "office_actions",
            "continuity",
            "amendments",
        ]
        assert data["prosecution_dossiers"][0]["office_action_count"] == 1
        assert data["prosecution_dossiers"][0]["office_action_events"][0]["document_code"] == "CTNF"
        assert data["prosecution_dossiers"][0]["amendment_events"][1]["event_type"] == "rce"
        assert data["prosecution_dossiers"][0]["record_basis"] == [
            "uspto_odp",
            "application_number",
            "uspto_transactions",
            "family_members",
        ]
        assert data["future_risk"][0]["monitoring_required"] is True
        assert data["future_risk"][0]["record_basis"] == ["family_members"]
        assert data["claim_program_decisions"][0]["claim_number"] == 1
        assert data["claim_program_decisions"][0]["missing_components"] == [
            "us_file_wrapper_dossier"
        ]
        assert data["claim_program_decisions"][0]["prosecution_risk_level"] == "medium"
        assert data["claim_program_decisions"][0]["scope_constrained"] is False
        assert data["claim_program_decisions"][0]["record_basis"] == [
            "application_number",
            "family_members",
        ]
        assert data["evidence_artifacts"][0]["artifact_type"] == "search_hit"
        assert data["evidence_adapter_results"][0]["adapter_name"] == "pubchem_sdq"
        assert data["collector_runs"][0]["definition"]["collector_name"] == "pubchem_sdq"
        assert data["collector_runs"][1]["definition"]["collector_name"] == "patentsview"
        assert data["collector_runs"][1]["collection_state"] == "missing"
        assert data["collector_runs"][1]["collection_targets"][0]["patent_id"] == "US12345678A1"
        assert data["collector_runs"][1]["attempts"][0]["summary"] == (
            "Collector has not yet satisfied all required targets."
        )
        assert data["evidence_adapter_results"][0]["adapter_kind"] == "search"
        assert data["evidence_adapter_results"][0]["status"] == "ok"
        assert data["evidence_adapter_results"][0]["collection_state"] == "collected"
        assert data["evidence_adapter_results"][0]["covered_patent_ids"] == ["US12345678A1"]
        assert data["evidence_adapter_results"][1]["expected_components"] == ["claims_text"]
        assert data["evidence_adapter_results"][1]["missing_components"] == ["claims_text"]
        assert data["evidence_adapter_results"][1]["collection_state"] == "missing"
        assert data["evidence_adapter_results"][1]["target_patent_ids"] == ["US12345678A1"]
        assert (
            data["evidence_collection_plan"][0]["directive_type"]
            == "collect_us_file_wrapper_dossier"
        )
        assert data["clearance_decision"]["decision_audit"]["claim_program_summary"][
            "medium_risk_claim_ids"
        ] == ["US12345678A1#claim1"]
        assert data["coverage_gaps"][0]["gap_type"] == "missing_us_file_wrapper_dossier"
        assert data["matter_graph"]["nodes"][0]["node_id"] == "compound:aspirin"
        assert data["matter_graph_summary"]["node_count"] == 5
        assert data["matter_store"]["matter_graph_summary"]["node_count"] == 5
        assert data["matter_store"]["claim_program_decisions"][0]["claim_number"] == 1
        assert data["matter_store"]["collector_runs"][0]["definition"]["collector_name"] == (
            "pubchem_sdq"
        )
        assert data["matter_store"]["record_completeness"]["clearance_grade_ready"] is False
        assert data["authority_coverage"]["authoritative_categories_missing"] == [
            "us_file_wrapper_dossier"
        ]
        assert data["record_completeness"]["clearance_grade_ready"] is False
        assert data["run_observability"]["false_clear_risk_flags"] == [
            "medium_risk_claims",
            "record_incomplete",
        ]
        assert data["patent_analyses"][0]["patent_id"] == "US12345678A1"
        assert data["patent_analyses"][0]["risk_level"] == "medium"
        assert data["doe_assessments"][0]["overall_equivalent"] is True
        assert data["invalidity_assessments"][0]["ptab"]["proceedings"][0]["type"] == "IPR"
        assert data["verification"]["checks"][0]["check_name"] == "citations"
        assert data["source_health"]["entries"][1]["status"] == "failed"
        assert data["analysis_failures"][0]["recoverable"] is True
        assert data["data_limitations"][0]["category"] == "coverage_gap"
        assert data["audit_trail"]["search_funnel"][0]["patent_id"] == "US12345678A1"
        assert data["audit_trail"]["timing_data"][0]["step_name"] == "step3_triage"
        assert data["step_token_usage"][0]["model_role"] == "triage"
        assert data["critic_report"]["overall_quality_score"] == 0.82
        assert data["critic_report"]["findings"][0]["issue_type"] == "confidence_calibration"
        assert (
            data["search_loop_result"]["iteration_logs"][0]["assessment"]["coverage_adequate"]
            is False
        )
        assert (
            data["search_loop_result"]["iteration_logs"][0]["assessment"][
                "evidence_collection_directives"
            ][0]["directive_type"]
            == "collect_authoritative_records"
        )
        assert data["search_loop_result"]["pending_collection_directives"] == []
        assert data["search_loop_result"]["termination_reason"] == "coverage_adequate"
        assert data["verification_summary"]["overall_assessment"] == "PASS_WITH_CORRECTIONS"
        assert data["bibliography"][0]["ref_type"] == "patent"
        assert data["report_pipeline"] == "world_class_adaptive"

    @pytest.mark.asyncio
    async def test_get_report_without_certifiable_identity_is_not_available(self, attorney_client):
        """A report without an ID cannot carry a valid owner-bound certification."""
        c, db = attorney_client
        aid = uuid.uuid4()
        bad_report = valid_report_data()
        bad_report.pop("report_id")
        analysis = make_analysis_mock(id=aid, report_data=bad_report)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_invalid_nested_decision_is_not_publishable(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        bad_report = valid_report_data(
            clearance_decision={
                "decision": "not_a_valid_outcome",
                "decision_confidence": 0.9,
            }
        )
        analysis = make_analysis_mock(id=aid, report_data=bad_report)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Report not yet available"


# ---------------------------------------------------------------------------
# GET /api/v1/reports/{analysis_id}/workspace-summary
# ---------------------------------------------------------------------------


class TestGetReportWorkspaceSummary:
    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_success(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        report = valid_report_data(
            trust_mode="counsel",
            risk_summary={
                "overall_risk": "medium",
                "blocking_patents_count": 0,
                "total_patents_analyzed": 1,
                "key_risks": ["Patent US12345678 covers core structure"],
                "executive_summary": (
                    "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed."
                ),
            },
            target_jurisdictions=["US", "EP"],
            jurisdiction_bundle="us_europe",
            routing_profile={
                "modality": "small_molecule",
                "capability_profile": "core_certified",
                "doctrine_packs": ["US", "EP"],
            },
            jurisdiction_matrix=[
                {
                    "jurisdiction": "US",
                    "lane_status": "counsel_ready",
                    "local_review_required": False,
                    "authority_grade": "authoritative",
                },
                {
                    "jurisdiction": "EP",
                    "lane_status": "counsel_ready",
                    "local_review_required": False,
                    "authority_grade": "authoritative",
                },
            ],
            jurisdiction_certification=[
                {
                    "jurisdiction": "US",
                    "selected": True,
                    "lane_status": "counsel_ready",
                    "supports_positive_clearance": True,
                    "local_review_required": False,
                    "decision": "unclear",
                },
                {
                    "jurisdiction": "EP",
                    "selected": True,
                    "lane_status": "counsel_ready",
                    "supports_positive_clearance": True,
                    "local_review_required": False,
                    "decision": "unclear",
                },
            ],
            jurisdiction_source_coverage=[
                {
                    "jurisdiction": "US",
                    "authority_grade": "authoritative",
                    "authoritative_sources": ["uspto_odp", "patentsview"],
                    "supporting_sources": ["bigquery"],
                    "local_review_required": False,
                    "lane_status": "counsel_ready",
                }
            ],
            opinion_readiness={
                "trust_mode": "counsel",
                "attorney_supervision_required": True,
                "clearance_grade_ready": True,
                "approval_required": True,
                "export_ready": True,
                "summary": "Attorney supervision is required before relying on a positive clearance conclusion.",
            },
            search_loop_result={
                "iterations_completed": 2,
                "iteration_logs": [],
                "final_assessment": {
                    "coverage_adequate": True,
                    "confidence": 0.88,
                    "suggested_queries": {
                        "patent_synonyms": ["acetylsalicylic acid"],
                        "cpc_codes": ["A61K"],
                        "key_assignees": ["Example Pharma"],
                        "process_keywords": ["tablet coating"],
                        "compound_class_terms": ["analgesic"],
                    },
                },
                "pending_collection_directives": [],
                "termination_reason": "coverage_adequate",
                "total_input_tokens": 5,
                "total_output_tokens": 2,
            },
            data_coverage={"coverage_score": 0.91, "completed_components": ["claims_text"]},
            source_convergence={"score": 0.87, "source_count": 3},
        )
        analysis = make_analysis_mock(
            id=aid,
            report_data=report,
            overall_risk="high",
            blocking_patents_count=5,
            total_patents_found=12,
            executive_summary="High risk due to multiple blocking patents.",
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_id"] == str(aid)
        assert data["report_summary"]["overall_risk"] == "medium"
        assert data["report_summary"]["blocking_patents_count"] == 0
        assert data["report_summary"]["risk_ratings_restricted"] is False
        assert data["trust_mode"] == "counsel"
        assert data["jurisdiction_bundle"] == "us_europe"
        assert data["target_jurisdictions"] == ["US", "EP"]
        assert data["capability_metadata"]["trust_mode"] == "counsel"
        assert "export_summary" in data["capability_metadata"]["allowed_capabilities"]
        assert data["monitor_seed_defaults"]["schedule"] == "weekly"
        assert data["monitor_seed_defaults"]["compound_name"] == "aspirin"
        assert data["monitor_seed_defaults"]["compound_smiles"] == "CC(=O)Oc1ccccc1C(O)=O"
        assert data["monitor_seed_defaults"]["source_trust_mode"] == "counsel"
        assert data["monitor_seed_defaults"]["requires_manual_input"] is False
        queries = data["suggested_evidence_queries"]
        assert len(queries) >= 3
        assert queries[0]["kind"] == "compound"
        assert queries[0]["query"] == "aspirin patent"
        assert queries[1]["kind"] == "modality"
        assert queries[1]["query"] == "aspirin composition claims"
        assert queries[2]["kind"] == "jurisdiction"
        assert queries[2]["query"] == "aspirin US patent"
        assert any(query["kind"] == "search_strategy" for query in queries)
        assert data["routing_profile"]["modality"] == "small_molecule"
        assert data["jurisdiction_matrix"][0]["jurisdiction"] == "US"
        assert data["jurisdiction_certification"][0]["lane_status"] == "counsel_ready"
        assert data["jurisdiction_source_coverage"][0]["jurisdiction"] == "US"
        assert data["opinion_readiness"]["export_ready"] is True
        assert data["data_coverage"]["coverage_score"] == 0.91
        assert data["source_convergence"]["score"] == 0.87
        assert data["evidence_scope"]["mode"] == "report_evidence"
        assert data["evidence_scope"]["external_live_retrieval"] is True
        assert (
            data["evidence_scope"]["provider_capabilities"] == data["evidence_scope"]["providers"]
        )
        assert (
            data["evidence_scope"]["provider_capabilities"][0]["provider_class"] == "report_derived"
        )
        assert any(
            item["provider_name"] == "pubchem" and item["live_retrieval_supported"] is True
            for item in data["evidence_scope"]["provider_capabilities"]
        )
        assert data["evidence_scope"]["hybrid_evidence_ready"] is True

    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_exposes_configured_licensed_overlay(
        self, attorney_client
    ):
        c, db = attorney_client
        aid = uuid.uuid4()
        report = valid_report_data(
            trust_mode="counsel",
            target_jurisdictions=["US", "EP"],
            routing_profile={
                "modality": "small_molecule",
                "capability_profile": "core_certified",
                "doctrine_packs": ["US", "EP"],
            },
        )
        analysis = make_analysis_mock(id=aid, report_data=report)
        db.execute.return_value.scalar_one_or_none.return_value = analysis
        runtime_config = LicensedFamilyOverlayRuntimeConfig(
            provider_name="Acme Family Overlay",
            search_url="https://licensed.example/search",
            api_key="secret",
            allowed_org_ids=frozenset({str(analysis.org_id)}),
            timeout_seconds=12.0,
        )

        with patch(
            "api.services.report_external_evidence.get_licensed_family_overlay_runtime_config",
            return_value=runtime_config,
        ):
            resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 200
        data = resp.json()
        family_overlay = next(
            item
            for item in data["evidence_scope"]["provider_capabilities"]
            if item["provider_id"] == "licensed_family_overlay"
        )
        assert family_overlay["configured"] is True
        assert family_overlay["provider_status"] in {"active", "caution_only"}
        assert family_overlay["live_retrieval_supported"] == (
            family_overlay["provider_status"] == "active"
        )
        assert family_overlay["execution_mode"] == "live_api"

    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_forbidden_for_client(
        self,
        client_role_client,
    ):
        c, db = client_role_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(id=aid, report_data=valid_report_data())
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_filters_non_attorney_risk(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        aid = uuid.uuid4()
        report = valid_report_data(
            trust_mode="counsel",
            risk_summary={
                "overall_risk": "medium",
                "blocking_patents_count": 0,
                "total_patents_analyzed": 1,
                "key_risks": ["Patent US12345678 covers core structure"],
                "executive_summary": (
                    "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed."
                ),
            },
            routing_profile={
                "modality": "small_molecule",
                "capability_profile": "core_certified",
                "doctrine_packs": ["US", "EP"],
            },
            opinion_readiness={
                "trust_mode": "counsel",
                "attorney_supervision_required": True,
                "clearance_grade_ready": True,
                "approval_required": True,
                "export_ready": True,
            },
            jurisdiction_matrix=[
                {
                    "jurisdiction": "US",
                    "lane_status": "counsel_ready",
                    "local_review_required": False,
                }
            ],
            jurisdiction_certification=[
                {
                    "jurisdiction": "US",
                    "selected": True,
                    "lane_status": "counsel_ready",
                    "supports_positive_clearance": True,
                    "local_review_required": False,
                    "decision": "unclear",
                }
            ],
            jurisdiction_source_coverage=[
                {
                    "jurisdiction": "US",
                    "authority_grade": "authoritative",
                    "authoritative_sources": ["uspto_odp", "patentsview"],
                    "supporting_sources": ["bigquery"],
                    "local_review_required": False,
                    "lane_status": "counsel_ready",
                }
            ],
            data_coverage={"coverage_score": 0.91, "completed_components": ["claims_text"]},
            source_convergence={"score": 0.87, "source_count": 3},
        )
        analysis = make_analysis_mock(
            id=aid,
            report_data=report,
            overall_risk="high",
            blocking_patents_count=5,
            total_patents_found=12,
            executive_summary="High risk due to multiple blocking patents.",
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["report_summary"]["overall_risk"] is None
        assert data["report_summary"]["blocking_patents_count"] is None
        assert data["report_summary"]["risk_ratings_restricted"] is True
        assert "restricted to attorney-role users" in data["report_summary"]["executive_summary"]
        assert data["trust_mode"] == "explorer"
        assert data["capability_metadata"]["trust_mode"] == "explorer"
        assert "export_summary" not in data["capability_metadata"]["allowed_capabilities"]
        assert "signable_opinion_summary" not in data["capability_metadata"]["allowed_capabilities"]
        assert data["routing_profile"] == {}
        assert data["opinion_readiness"] == {}
        assert data["data_coverage"] == {}
        assert data["source_convergence"] == {}
        assert data["jurisdiction_matrix"] == []
        assert data["jurisdiction_certification"] == []
        assert data["jurisdiction_source_coverage"] == []
        assert data["evidence_scope"]["external_live_retrieval"] is False
        assert data["monitor_seed_defaults"]["schedule"] == "weekly"

    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_missing_report(self, scientist_client):
        c, db = scientist_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(id=aid, report_data=None)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_workspace_summary_rejects_non_completed_report_payload(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            status=AnalysisStatus.DELETED,
            report_data=valid_report_data(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/workspace-summary")

        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("override_key", "override_value"),
        [
            (
                "critic_report",
                {
                    "overall_quality_score": 0.82,
                    "findings": [
                        {
                            "issue_type": "not_real",
                            "patent_id": "US92000001A1",
                            "severity": "minor",
                            "description": "bad",
                        }
                    ],
                },
            ),
            (
                "search_loop_result",
                {
                    "iterations_completed": 1,
                    "iteration_logs": "not-a-list",
                    "total_input_tokens": 10,
                    "total_output_tokens": 5,
                },
            ),
            (
                "source_health",
                {
                    "entries": [
                        {
                            "source": "pubchem_sdq",
                            "status": "not_real",
                            "patent_count": 1,
                            "error_message": "",
                        }
                    ]
                },
            ),
            (
                "step_token_usage",
                [{"step_name": "step3_triage", "model_role": "triage", "input_tokens": "bad"}],
            ),
            (
                "audit_trail",
                {
                    "search_funnel": "not-a-list",
                    "triage_audit": [],
                    "analysis_audit": [],
                    "timing_data": [],
                },
            ),
            (
                "patent_analyses",
                [{"patent_id": 123, "risk_level": "medium", "risk_summary": "bad patent id type"}],
            ),
            (
                "doe_assessments",
                [{"patent_id": "US92000001A1", "claim_number": "bad", "element_number": 1}],
            ),
            (
                "invalidity_assessments",
                [
                    {
                        "patent_id": "US92000001A1",
                        "claim_numbers": [1],
                        "ptab": {"has_been_challenged": True, "proceedings": "bad"},
                    }
                ],
            ),
            (
                "matter_evidence_index",
                {
                    "source_names": ["pubchem_sdq"],
                    "material_patent_count": 1,
                    "family_count": 0,
                    "analysis_failure_patent_ids": [],
                    "critic_flagged_patent_ids": [],
                    "clearance_grade_ready_patent_ids": [],
                    "incomplete_patent_ids": [],
                    "clearance_grade_ready_family_ids": [],
                    "incomplete_family_ids": [],
                    "patent_records": [
                        {
                            "patent_id": "US12345678A1",
                            "component_statuses": "not-a-list",
                        }
                    ],
                    "family_records": [],
                },
            ),
            (
                "matter_graph_summary",
                {
                    "root_compound": "aspirin",
                    "node_count": "bad",
                    "edge_count": 1,
                },
            ),
            (
                "authority_coverage",
                {
                    "policy": "official_plus_licensed",
                    "authoritative_source_names": "not-a-list",
                },
            ),
            (
                "record_completeness",
                {
                    "profile": "world_class_us_ep",
                    "matter_type": "small_molecule",
                    "required_components": "not-a-list",
                },
            ),
            (
                "matter_graph",
                {
                    "nodes": "not-a-list",
                    "edges": [],
                },
            ),
            (
                "decision_scope",
                {
                    "matter_type": "small_molecule",
                    "jurisdictions": "not-a-list",
                    "asset_classes": ["compound"],
                    "supports_positive_clearance": True,
                },
            ),
            (
                "certification_scope",
                {
                    "certified_jurisdictions": ["US", "EP"],
                    "certified_matter_types": "not-a-list",
                },
            ),
            (
                "claim_program_decisions",
                [{"patent_id": "US92000001A1", "claim_number": "bad"}],
            ),
            (
                "evidence_artifacts",
                [{"artifact_id": "x", "artifact_type": "not_real"}],
            ),
            (
                "evidence_adapter_results",
                [
                    {
                        "adapter_name": "pubchem_sdq",
                        "authority_tier": "supporting",
                        "artifacts": "bad",
                    }
                ],
            ),
            (
                "collector_runs",
                [
                    {
                        "definition": {"collector_name": "patentsview"},
                        "collection_state": "missing",
                        "attempts": "bad",
                    }
                ],
            ),
            (
                "matter_store",
                {
                    "matter_graph": {"nodes": [], "edges": []},
                    "matter_graph_summary": {"node_count": "bad"},
                },
            ),
            (
                "prosecution_dossiers",
                [
                    {
                        "patent_id": "US12345678A1",
                        "sections_available": "not-a-list",
                    }
                ],
            ),
        ],
    )
    async def test_get_report_invalid_nested_metadata_returns_500(
        self,
        attorney_client,
        override_key,
        override_value,
    ):
        c, db = attorney_client
        aid = uuid.uuid4()
        if override_key == "patent_analyses":
            bad_report = valid_report_data_for_patents(override_value)
        else:
            bad_report = valid_report_data(**{override_key: override_value})
        analysis = make_analysis_mock(id=aid, report_data=bad_report)
        _configure_report_content_queries(db, analysis)

        resp = await c.get(f"/api/v1/reports/{aid}")
        if override_key in {
            "source_health",
            "audit_trail",
            "patent_analyses",
            "claim_program_decisions",
            "matter_evidence_index",
            "authority_coverage",
            "record_completeness",
            "matter_store",
        }:
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Report not yet available"
        else:
            assert resp.status_code == 500
            assert "schema validation" in resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("override_key", "override_value"),
        [
            (
                "verification_summary",
                {
                    "total_claims_checked": 1,
                    "claims_correct": 1,
                    "claims_incorrect": 0,
                    "claims_unverifiable": 0,
                    "factual_accuracy_rate": 1.0,
                    "corrections_needed": "not-a-list",
                    "omissions_found": [],
                    "overall_assessment": "PASS",
                },
            ),
            (
                "verification",
                {
                    "checks": "not-a-list",
                    "all_citations_valid": True,
                    "all_claims_grounded": True,
                    "all_entities_valid": True,
                    "dates_consistent": True,
                    "risk_levels_justified": True,
                    "issues": [],
                },
            ),
        ],
    )
    async def test_get_report_rejects_unpublishable_verification_metadata(
        self,
        attorney_client,
        override_key,
        override_value,
    ):
        c, db = attorney_client
        aid = uuid.uuid4()
        bad_report = valid_report_data(**{override_key: override_value})
        analysis = make_analysis_mock(id=aid, report_data=bad_report)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/reports/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_report_forbidden_for_client(self, client_role_client):
        c, db = client_role_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(id=aid, report_data={"some": "data"})
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_report_not_yet_available(self, scientist_client):
        c, db = scientist_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(id=aid, report_data=None)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}")
        assert resp.status_code == 404
        assert "not yet available" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/reports/{analysis_id}/summary
# ---------------------------------------------------------------------------


class TestGetReportSummary:
    @pytest.mark.asyncio
    async def test_summary_success(self, scientist_client):
        c, db = scientist_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(),
            overall_risk="high",
            blocking_patents_count=5,
            total_patents_found=100,
            executive_summary="Significant risk.",
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_risk"] is None
        assert data["blocking_patents_count"] is None
        assert data["total_patents_found"] == 42
        assert data["risk_ratings_restricted"] is True
        assert "restricted to attorney-role users" in data["executive_summary"]

    @pytest.mark.asyncio
    async def test_summary_available_to_client(self, client_role_client):
        """Clients CAN view summaries — no role restriction."""
        c, db = client_role_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(id=aid, report_data=valid_report_data())
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/summary")
        assert resp.status_code == 200
        assert resp.json()["risk_ratings_restricted"] is True

    @pytest.mark.asyncio
    async def test_summary_rejects_non_completed_report_payload(self, scientist_client):
        c, db = scientist_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            status=AnalysisStatus.RUNNING,
            report_data=valid_report_data(),
            overall_risk="high",
            blocking_patents_count=7,
            total_patents_found=42,
            executive_summary="stale running report summary",
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.get(f"/api/v1/reports/{aid}/summary")

        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_summary_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/reports/{uuid.uuid4()}/summary")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/reports/{analysis_id}/export
# ---------------------------------------------------------------------------


def _reviewer_decision_mock(
    *,
    finding_ref: str,
    decision: str = "accept",
    reviewer_user_id: str = "clerk_reviewer_1",
    finding_type: str = "patent",
    report_fingerprint: str = "",
) -> MagicMock:
    row = MagicMock()
    row.finding_type = finding_type
    row.finding_ref = finding_ref
    row.report_fingerprint = report_fingerprint
    row.decision = decision
    row.reviewer_user_id = reviewer_user_id
    return row


def _reviewer_decisions_result(decisions: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = decisions
    return result


class TestExportReport:
    def test_report_export_permission_excludes_client_role(self):
        assert UserRole.CLIENT not in PERMISSION_MATRIX["report.export"]

    @pytest.mark.asyncio
    async def test_export_pdf_as_attorney(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        with patch("api.workers.tasks.run_export") as mock_task:
            mock_task.delay = MagicMock()
            resp = await c.post(
                f"/api/v1/reports/{aid}/export",
                json={"format": "pdf"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "job_id" in data
        added = [call.args[0] for call in db.add.call_args_list]
        export_jobs = [obj for obj in added if isinstance(obj, ExportJob)]
        audit_rows = [obj for obj in added if isinstance(obj, AuditLog)]
        assert len(export_jobs) == 1
        assert len(audit_rows) == 1
        assert str(export_jobs[0].id) == data["job_id"]
        assert audit_rows[0].action == "report.export.queued"
        assert audit_rows[0].analysis_id == aid
        assert audit_rows[0].details["job_id"] == data["job_id"]
        assert audit_rows[0].details["format"] == "pdf"
        db.commit.assert_awaited_once()
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_rejects_non_completed_report_payload(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            status=AnalysisStatus.RUNNING,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        db.execute.return_value = analysis_result

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "completed report payload" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_client_docx_forbidden(self, client_role_client):
        c, db = client_role_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={"export_ready": True},
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "docx"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]  # Client gets 403 for non-PDF formats

    @pytest.mark.asyncio
    async def test_export_client_pdf_forbidden(self, client_role_client):
        c, db = client_role_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis

        with patch("api.workers.tasks.run_export") as mock_task:
            mock_task.delay = MagicMock()
            resp = await c.post(
                f"/api/v1/reports/{aid}/export",
                json={"format": "pdf"},
            )
        assert resp.status_code == 403
        assert "report.export" in resp.json()["detail"]
        mock_task.delay.assert_not_called()
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("export_format", ["docx", "pptx"])
    async def test_export_scientist_risk_gate_takes_precedence_over_format_copy(
        self,
        scientist_client,
        export_format,
    ):
        c, db = scientist_client
        aid = uuid.uuid4()

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": export_format},
        )

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("export_format", ["docx", "pptx"])
    async def test_export_scientist_format_copy_when_risk_gate_is_disabled(
        self,
        scientist_client,
        export_format,
    ):
        c, db = scientist_client

        with patch(
            "api.routes.reports._must_filter_risk_for_user",
            return_value=False,
        ):
            resp = await c.post(
                f"/api/v1/reports/{uuid.uuid4()}/export",
                json={"format": export_format},
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == ("Scientists can export PDF, JSON, CSV, or XLSX")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("export_format", ["pdf", "json", "csv", "xlsx"])
    async def test_export_scientist_risk_restricted_for_all_formats(
        self,
        scientist_client,
        export_format,
    ):
        c, db = scientist_client

        resp = await c.post(
            f"/api/v1/reports/{uuid.uuid4()}/export",
            json={"format": export_format, "audience": "full"},
        )

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_blocks_when_high_medium_findings_have_no_decisions(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US90000001A1", "risk_level": "high"},
                    {"patent_id": "US90000002A1", "risk_level": "medium"},
                    {"patent_id": "US90000003A1", "risk_level": "low"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [
            analysis_result,
            review_status_result,
            _reviewer_decisions_result([]),
        ]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "Reviewer decisions are incomplete" in resp.json()["detail"]
        assert "US90000001A1 has no reviewer decision" in resp.json()["detail"]
        assert "US90000002A1 has no reviewer decision" in resp.json()["detail"]
        assert "US90000003A1" not in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_blocks_high_finding_without_dual_review(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US90000001A1", "risk_level": "high"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [
            analysis_result,
            review_status_result,
            _reviewer_decisions_result(
                [
                    _reviewer_decision_mock(
                        finding_ref="US90000001A1",
                        report_fingerprint=report_fingerprint,
                    ),
                ]
            ),
        ]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "US90000001A1 requires dual review" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_blocks_when_claim_source_span_needs_review(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        report_data = valid_report_data(
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        report_data["claim_source_span_map"]["entries"].append(
            {
                "assertion_id": "assertion-needs-review-1",
                "patent_id": "US90000001A1",
                "claim_number": 1,
                "element_number": 2,
                "report_section": "claim_element_analysis",
                "assertion_text": "Claim 1 element 2 was assessed as unclear.",
                "source_span_ids": [],
                "support_status": "needs_review",
                "customer_visible": True,
                "review_required": True,
            }
        )
        report_data["claim_source_span_map"]["needs_review_count"] = 1
        analysis = make_analysis_mock(id=aid, report_data=report_data)
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [
            analysis_result,
            review_status_result,
            _reviewer_decisions_result([]),
        ]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "Reviewer decisions are incomplete" in resp.json()["detail"]
        assert "assertion-needs-review-1 has no reviewer decision" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_allows_fully_reviewed_high_medium_findings(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US90000001A1", "risk_level": "high"},
                    {"patent_id": "US90000002A1", "risk_level": "medium"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [
            analysis_result,
            review_status_result,
            _reviewer_decisions_result(
                [
                    _reviewer_decision_mock(
                        finding_ref="US90000001A1",
                        reviewer_user_id="clerk_reviewer_1",
                        report_fingerprint=report_fingerprint,
                    ),
                    _reviewer_decision_mock(
                        finding_ref="US90000001A1",
                        reviewer_user_id="clerk_reviewer_2",
                        report_fingerprint=report_fingerprint,
                    ),
                    _reviewer_decision_mock(
                        finding_ref="US90000002A1",
                        reviewer_user_id="clerk_reviewer_1",
                        report_fingerprint=report_fingerprint,
                    ),
                ]
            ),
        ]

        with patch("api.workers.tasks.run_export") as mock_task:
            mock_task.delay = MagicMock()
            resp = await c.post(
                f"/api/v1/reports/{aid}/export",
                json={"format": "pdf"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_blocks_when_lane_export_ready_is_closed(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": False,
                    "jurisdictions_blocking_export": ["UK"],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "blocked until counsel-mode export readiness is open" in resp.json()["detail"]
        assert "UK" in resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("export_ready", ["false", "no", "0", 1, [], {}])
    async def test_export_blocks_when_lane_export_ready_is_malformed(
        self,
        attorney_client,
        export_ready,
    ):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": export_ready,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        with patch("api.workers.tasks.run_export") as mock_task:
            mock_task.delay = MagicMock()
            resp = await c.post(
                f"/api/v1/reports/{aid}/export",
                json={"format": "pdf"},
            )

        assert resp.status_code == 409
        assert "clearance-grade evidence is still incomplete" in resp.json()["detail"]
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_blocks_when_review_status_is_not_approved(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.UNDER_REVIEW
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "Persisted legal review status is under_review" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_blocks_when_not_in_counsel_mode(self, attorney_client):
        c, db = attorney_client
        aid = uuid.uuid4()
        analysis = make_analysis_mock(
            id=aid,
            report_data=valid_report_data(
                trust_mode="explorer",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status = MagicMock()
        review_status.status = ReviewStatus.APPROVED
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute.side_effect = [analysis_result, review_status_result]

        resp = await c.post(
            f"/api/v1/reports/{aid}/export",
            json={"format": "pdf"},
        )

        assert resp.status_code == 409
        assert "not in counsel export mode" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_not_found(self, attorney_client):
        c, db = attorney_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.post(
            f"/api/v1/reports/{uuid.uuid4()}/export",
            json={"format": "pdf"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_status_marks_retryable_failed_jobs(self, attorney_client):
        c, db = attorney_client
        job_id = uuid.uuid4()
        lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
        job = MagicMock()
        job.id = job_id
        job.status = ExportStatus.FAILED
        job.format = ExportFormat.PDF
        job.file_url = ""
        job.file_size_bytes = 0
        job.error_message = "Export failed: See worker logs for traceback"
        job.processing_lease_expires_at = lease_expires_at
        db.execute.return_value.scalar_one_or_none.return_value = job

        resp = await c.get(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["retryable"] is True
        assert data["retry_after_seconds"] is not None
        assert data["retry_after_seconds"] >= 0
        assert "processing_lease_expires_at" not in data
        assert data["error_message"] is None
        assert data["download_url"] is None

    @pytest.mark.asyncio
    async def test_export_status_restricted_for_scientist_when_risk_gate_is_enabled(
        self,
        scientist_client,
    ):
        c, db = scientist_client

        resp = await c.get(f"/api/v1/exports/{uuid.uuid4()}")

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_status_returns_manifest_receipt_for_completed_job(self, attorney_client):
        c, db = attorney_client
        job_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        completed_at = datetime.now(UTC)
        job = MagicMock()
        job.id = job_id
        job.analysis_id = analysis_id
        job.status = ExportStatus.COMPLETED
        job.format = ExportFormat.PDF
        job.file_url = "/tmp/export.pdf"
        job.file_size_bytes = 1234
        job.error_message = ""
        job.processing_lease_expires_at = None
        job.manifest_schema_version = "export-manifest-v1"
        job.artifact_sha256 = "b" * 64
        job.report_payload_sha256 = "c" * 64
        job.completed_at = completed_at
        job.manifest_snapshot = {
            "version": "export-manifest-v1",
            "generated_at": completed_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "job": {"id": str(job_id), "analysis_id": str(analysis_id)},
            "artifact": {
                "format": "pdf",
                "file_size_bytes": 1234,
                "sha256": "b" * 64,
                "sections": ["executive_summary"],
                "storage_locator_hash": hashlib.sha256(job.file_url.encode()).hexdigest(),
                "file_url": "gs://private-bucket/export.pdf",
                "local_path": "/tmp/export.pdf",
            },
            "report": {"fingerprint": "c" * 64},
            "branding": {
                "display_name": "Praviar",
                "has_custom_logo": True,
                "logo_path": "/tmp/acme-logo.png",
            },
            "source_health": {
                "healthy_count": 1,
                "total_count": 1,
                "entries": [{"source": "/srv/private/source.json", "status": "ok"}],
                "status_counts": {"ok": 1},
            },
        }
        job.manifest_hash = export_manifest_hash(job.manifest_snapshot)
        job.manifest_signature = export_manifest_signature(job.manifest_hash)
        db.execute.return_value.scalar_one_or_none.return_value = job

        resp = await c.get(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["download_url"] == f"/api/v1/exports/{job_id}/download"
        assert data["manifest_schema_version"] == "export-manifest-v1"
        assert data["manifest_hash"] == job.manifest_hash
        assert data["artifact_sha256"] == "b" * 64
        assert data["report_payload_sha256"] == "c" * 64
        assert data["manifest_snapshot"]["artifact"]["format"] == "pdf"
        assert data["manifest_snapshot"]["artifact"]["sections"] == ["executive_summary"]
        assert data["manifest_snapshot"]["branding"]["display_name"] == "Praviar"
        assert data["manifest_snapshot"]["branding"]["has_custom_logo"] is True
        assert data["manifest_snapshot"]["source_health"]["healthy_count"] == 1
        serialized_snapshot = json.dumps(data["manifest_snapshot"])
        assert "job" not in data["manifest_snapshot"]
        assert "storage_locator_hash" not in serialized_snapshot
        assert "file_url" not in serialized_snapshot
        assert "local_path" not in serialized_snapshot
        assert "logo_path" not in serialized_snapshot
        assert "/tmp/acme-logo.png" not in serialized_snapshot
        assert "/srv/private/source.json" not in serialized_snapshot
        assert data["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_export_status_marks_terminal_failed_jobs(self, attorney_client):
        c, db = attorney_client
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.status = ExportStatus.FAILED
        job.format = ExportFormat.PDF
        job.file_url = ""
        job.file_size_bytes = 0
        job.error_message = "Export blocked: review is not approved"
        job.processing_lease_expires_at = None
        db.execute.return_value.scalar_one_or_none.return_value = job

        resp = await c.get(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["retryable"] is False
        assert data["retry_after_seconds"] is None
        assert "processing_lease_expires_at" not in data

    @pytest.mark.asyncio
    async def test_export_status_redacts_unsafe_terminal_error_messages(self, attorney_client):
        c, db = attorney_client
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.status = ExportStatus.FAILED
        job.format = ExportFormat.PDF
        job.file_url = ""
        job.file_size_bytes = 0
        job.error_message = "Traceback at /srv/private/export.py"
        job.processing_lease_expires_at = None
        db.execute.return_value.scalar_one_or_none.return_value = job

        resp = await c.get(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Export failed. Please try again or contact support."
        assert "Traceback" not in data["error_message"]
        assert "/srv/private/export.py" not in data["error_message"]

    @pytest.mark.asyncio
    async def test_export_status_redacts_paths_inside_allowed_error_messages(self, attorney_client):
        c, db = attorney_client
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.status = ExportStatus.FAILED
        job.format = ExportFormat.PDF
        job.file_url = ""
        job.file_size_bytes = 0
        job.error_message = (
            "Export blocked: Branding logo not found: /tmp/acme-logo.png "
            "or gs://private-bucket/export.pdf"
        )
        job.processing_lease_expires_at = None
        db.execute.return_value.scalar_one_or_none.return_value = job

        resp = await c.get(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_message"].startswith("Export blocked:")
        assert "[redacted]" in data["error_message"]
        assert "/tmp/acme-logo.png" not in data["error_message"]
        assert "gs://private-bucket/export.pdf" not in data["error_message"]

    @pytest.mark.asyncio
    async def test_export_status_forbidden_for_client(self, client_role_client):
        c, db = client_role_client

        resp = await c.get(f"/api/v1/exports/{uuid.uuid4()}")

        assert resp.status_code == 403
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_export_dispatches_authenticated_cleanup(self, attorney_client):
        c, _db = attorney_client
        job_id = uuid.uuid4()

        with patch(
            "api.routes.reports.delete_export_job",
            new=AsyncMock(),
        ) as delete_export:
            resp = await c.delete(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 204
        delete_export.assert_awaited_once()
        assert delete_export.await_args.kwargs["job_id"] == job_id
        assert isinstance(delete_export.await_args.kwargs["org_id"], uuid.UUID)
        assert isinstance(delete_export.await_args.kwargs["user_id"], uuid.UUID)
        assert delete_export.await_args.kwargs["allow_org_wide"] is True

    @pytest.mark.asyncio
    async def test_delete_export_forbidden_for_client(self, client_role_client):
        c, db = client_role_client

        resp = await c.delete(f"/api/v1/exports/{uuid.uuid4()}")

        assert resp.status_code == 403
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_export_restricted_for_scientist_when_risk_gate_is_enabled(
        self,
        scientist_client,
    ):
        c, db = scientist_client

        resp = await c.delete(f"/api/v1/exports/{uuid.uuid4()}")

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_export_scientist_is_limited_to_owned_exports_when_gate_disabled(
        self,
        scientist_client,
    ):
        c, _db = scientist_client
        job_id = uuid.uuid4()

        with (
            patch(
                "api.routes.reports._must_filter_risk_for_user",
                return_value=False,
            ),
            patch(
                "api.routes.reports.delete_export_job",
                new=AsyncMock(),
            ) as delete_export,
        ):
            resp = await c.delete(f"/api/v1/exports/{job_id}")

        assert resp.status_code == 204
        assert delete_export.await_args.kwargs["allow_org_wide"] is False

    @pytest.mark.asyncio
    async def test_export_download_forbidden_for_client(self, client_role_client):
        c, db = client_role_client

        resp = await c.get(f"/api/v1/exports/{uuid.uuid4()}/download")

        assert resp.status_code == 403
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_download_restricted_for_scientist_when_risk_gate_is_enabled(
        self,
        scientist_client,
    ):
        c, db = scientist_client

        resp = await c.get(f"/api/v1/exports/{uuid.uuid4()}/download")

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_download_streams_private_gcs_artifact_from_api_origin(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        job_id = uuid.uuid4()
        content = b"%PDF-1.7\ntrusted export"
        job = MagicMock(
            format=ExportFormat.PDF,
            file_size_bytes=len(content),
        )
        download = MagicMock(
            job=job,
            filename="reviewed-report.pdf",
            local_path=None,
            gcs_uri=MagicMock(
                bucket="praviar-exports",
                blob_path="exports/org/analysis/job/execution/reviewed-report.pdf",
            ),
        )
        prepared = MagicMock()

        with (
            patch(
                "api.routes.reports.resolve_export_download",
                new=AsyncMock(return_value=download),
            ) as resolve_download,
            patch(
                "api.routes.reports.prepare_export_download",
                return_value=prepared,
            ) as prepare_download,
            patch(
                "api.routes.reports.iter_prepared_export_download",
                return_value=iter([content[:8], content[8:]]),
            ) as iter_download,
        ):
            resp = await c.get(f"/api/v1/exports/{job_id}/download")

        assert resp.status_code == 200
        assert resp.content == content
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-length"] == str(len(content))
        assert resp.headers["content-disposition"].startswith(
            'attachment; filename="reviewed-report.pdf"'
        )
        assert resp.headers["cache-control"] == "private, no-store"
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "location" not in resp.headers
        resolve_download.assert_awaited_once_with(
            db,
            job_id=job_id,
            org_id=db._auth_user.org_id,
        )
        prepare_download.assert_called_once_with(download)
        iter_download.assert_called_once_with(prepared)
        prepared.close.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_export_download_rejects_tampered_artifact_before_2xx_or_bytes(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        job_id = uuid.uuid4()
        expected = b"trusted"
        tampered = b"untrust"
        job = MagicMock(
            format=ExportFormat.PDF,
            file_size_bytes=len(expected),
            artifact_sha256=hashlib.sha256(expected).hexdigest(),
        )
        download = MagicMock(
            job=job,
            filename="reviewed-report.pdf",
            local_path=None,
            gcs_uri=MagicMock(
                bucket="praviar-exports",
                blob_path="exports/org/analysis/job/execution/reviewed-report.pdf",
            ),
        )
        storage = MagicMock()
        storage.iter_blob.return_value = iter([tampered])

        with (
            patch(
                "api.routes.reports.resolve_export_download",
                new=AsyncMock(return_value=download),
            ),
            patch("api.services.reports.ObjectStorage", return_value=storage),
        ):
            resp = await c.get(f"/api/v1/exports/{job_id}/download")

        assert resp.status_code == 409
        assert tampered not in resp.content
        assert "content-disposition" not in resp.headers
        assert resp.json()["detail"] == "Export artifact failed integrity verification"
        storage.iter_blob.assert_called_once_with(download.gcs_uri.blob_path)
        db.execute.assert_not_called()
