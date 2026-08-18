from __future__ import annotations

from api.schemas import reports as reports_facade
from api.schemas.reports_core import RiskSummaryResponse as RiskSummaryResponseImpl
from api.schemas.reports_core_analysis import (
    PatentAnalysisResponse as PatentAnalysisResponseImpl,
)
from api.schemas.reports_core_quality import (
    RiskSummaryResponse as RiskSummaryResponseQualityImpl,
)
from api.schemas.reports_fto import ExportRequest as ExportRequestImpl
from api.schemas.reports_fto import FTOReportResponse as FTOReportResponseImpl
from api.schemas.reports_fto_io import ExportRequest as ExportRequestSplitImpl
from api.schemas.reports_fto_report import FTOReportResponse as FTOReportResponseSplitImpl
from api.schemas.reports_tracking import (
    CoverageAssessmentResponse as CoverageAssessmentResponseImpl,
)
from api.schemas.reports_tracking import (
    MatterEvidenceIndexResponse as MatterEvidenceIndexResponseImpl,
)
from api.schemas.reports_tracking import (
    SearchLoopResultResponse as SearchLoopResultResponseImpl,
)
from api.schemas.reports_tracking_audit import (
    ClearanceDecisionResponse as ClearanceDecisionResponseImpl,
)
from api.schemas.reports_tracking_evidence import (
    MatterEvidenceIndexResponse as MatterEvidenceIndexResponseSplitImpl,
)
from api.schemas.reports_types import RiskLevel, SourceStatus


def test_reports_facade_reexports_split_models():
    assert reports_facade.RiskSummaryResponse is RiskSummaryResponseImpl
    assert RiskSummaryResponseImpl is RiskSummaryResponseQualityImpl
    assert reports_facade.FTOReportResponse is FTOReportResponseImpl
    assert FTOReportResponseImpl is FTOReportResponseSplitImpl
    assert reports_facade.ExportRequest is ExportRequestImpl
    assert ExportRequestImpl is ExportRequestSplitImpl
    assert reports_facade.PatentAnalysisResponse is PatentAnalysisResponseImpl
    assert reports_facade.CoverageAssessmentResponse is CoverageAssessmentResponseImpl
    assert reports_facade.SearchLoopResultResponse is SearchLoopResultResponseImpl
    assert reports_facade.ClearanceDecisionResponse is ClearanceDecisionResponseImpl
    assert reports_facade.MatterEvidenceIndexResponse is MatterEvidenceIndexResponseImpl
    assert MatterEvidenceIndexResponseImpl is MatterEvidenceIndexResponseSplitImpl


def test_reports_facade_retains_literal_contract():
    assert "high" in RiskLevel.__args__
    assert "clear" in RiskLevel.__args__
    assert "not_configured" in SourceStatus.__args__


def test_source_health_preserves_not_configured_status():
    from api.schemas.reports_core_quality import SourceHealthEntryResponse
    from api.schemas.reports_tracking_evidence import EvidenceAdapterResultResponse

    health_entry = SourceHealthEntryResponse.model_validate(
        {
            "source": "lens",
            "status": "not_configured",
            "patent_count": 0,
            "attempted_count": 7,
            "covered_count": 0,
            "error_message": "LENS_API_KEY is required",
        }
    )
    adapter_result = EvidenceAdapterResultResponse.model_validate(
        {
            "adapter_name": "patcid",
            "status": "not_configured",
            "collection_state": "missing",
        }
    )

    assert health_entry.status == "not_configured"
    assert health_entry.attempted_count == 7
    assert health_entry.covered_count == 0
    assert adapter_result.status == "not_configured"


def test_clearance_decision_response_preserves_canonical_blocker_families():
    decision = ClearanceDecisionResponseImpl.model_validate(
        {
            "decision": "blocked",
            "decision_audit": {
                "claim_program_summary": {
                    "blocking_claim_ids": ["US12345678A1#claim1"],
                    "blocking_patent_ids": ["US12345678A1"],
                },
                "blocker_families": [
                    {
                        "blocker_id": "bf_5e65c4a1e941d51e",
                        "family_id": "fam-123",
                        "primary_blocking_patent_id": "US12345678A1",
                        "material_family_patent_ids": ["US12345678A1"],
                        "blocking_patent_ids": ["US12345678A1"],
                        "jurisdictions": ["US"],
                        "blocking_claims": [
                            {
                                "claim_id": "US12345678A1#claim1",
                                "patent_id": "US12345678A1",
                                "claim_number": 1,
                                "jurisdiction": "US",
                                "literal_risk": "high",
                                "legal_status": "active",
                                "legal_status_provenance_verified": True,
                                "prospective_enforceability": "active",
                                "accused_acts": ["sale"],
                                "accused_acts_verified": True,
                                "evidence_sufficient": True,
                                "record_basis": ["verified_claim_text"],
                            }
                        ],
                    }
                ],
            },
        }
    )

    serialized = decision.model_dump(mode="json")

    assert serialized["decision_audit"]["blocker_families"][0]["family_id"] == "fam-123"
    assert (
        serialized["decision_audit"]["blocker_families"][0]["blocking_claims"][0]["claim_id"]
        == "US12345678A1#claim1"
    )


# ─── Drawing analysis (Markush surfacing) ─────────────────────────────────────


def test_drawing_structure_response_round_trips_markush_fields():
    """is_markush, markush_cxsmiles, markush_r_groups must round-trip cleanly.

    Without these fields on the API response model, FastAPI's response_model
    serialization silently drops the Markush metadata, hiding R-group templates
    from the web UI.
    """
    from api.schemas.reports_drawings import DrawingStructureResponse

    payload = {
        "patent_id": "US92000005A1",
        "page_number": 4,
        "structure_index": 0,
        "canonical_smiles": "",
        "is_markush": True,
        "markush_cxsmiles": "C[*:1]C(=O)O[*:2] |$;R1;;;;R2$|",
        "markush_r_groups": ["R1", "R2"],
        "markush_target_in_scope": True,
        "extraction_tool": "markushgrapher",
        "tanimoto_to_target": 0.42,
        "drawing_risk_signal": "medium",
    }

    model = DrawingStructureResponse.model_validate(payload)
    assert model.is_markush is True
    assert model.markush_cxsmiles == "C[*:1]C(=O)O[*:2] |$;R1;;;;R2$|"
    assert model.markush_r_groups == ["R1", "R2"]
    assert model.markush_target_in_scope is True

    dumped = model.model_dump()
    assert dumped["is_markush"] is True
    assert dumped["markush_cxsmiles"] == "C[*:1]C(=O)O[*:2] |$;R1;;;;R2$|"
    assert dumped["markush_r_groups"] == ["R1", "R2"]


def test_drawing_structure_response_defaults_for_regular_molecule():
    from api.schemas.reports_drawings import DrawingStructureResponse

    model = DrawingStructureResponse.model_validate(
        {
            "patent_id": "US92000006A1",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "extraction_tool": "molscribe",
        }
    )
    assert model.is_markush is False
    assert model.markush_cxsmiles is None
    assert model.markush_r_groups == []
    assert model.markush_target_in_scope is None


def test_patent_drawing_analysis_response_carries_structures():
    from api.schemas.reports_drawings import (
        DrawingStructureResponse,
        PatentDrawingAnalysisResponse,
    )

    model = PatentDrawingAnalysisResponse.model_validate(
        {
            "patent_id": "US92000005A1",
            "structures_found": 2,
            "structures_valid": 2,
            "highest_tanimoto": 0.71,
            "highest_risk_signal": "high",
            "structures": [
                {
                    "patent_id": "US92000005A1",
                    "canonical_smiles": "CCO",
                    "is_markush": False,
                },
                {
                    "patent_id": "US92000005A1",
                    "is_markush": True,
                    "markush_cxsmiles": "C[*:1]C |$;R1;$|",
                    "markush_r_groups": ["R1"],
                },
            ],
        }
    )
    assert len(model.structures) == 2
    assert model.structures[0].is_markush is False
    assert model.structures[1].is_markush is True
    assert isinstance(model.structures[1], DrawingStructureResponse)
    assert model.structures[1].markush_cxsmiles == "C[*:1]C |$;R1;$|"


def test_fto_report_response_surfaces_drawing_analyses():
    """The top-level FTOReportResponse must carry drawing_analyses through serialization."""
    from datetime import datetime

    from api.schemas.reports_fto_report import FTOReportResponse

    payload = {
        "report_id": "rep_1",
        "generated_at": datetime(2026, 4, 28, 12, 0, 0),
        "compound": {"name": "test"},
        "risk_summary": {
            "overall_risk": "low",
            "blocking_patents_count": 0,
            "key_risks": [],
            "executive_summary": "",
            "summary_validation_issues": [],
        },
        "drawing_analyses": [
            {
                "patent_id": "US92000005A1",
                "structures_found": 1,
                "structures": [
                    {
                        "patent_id": "US92000005A1",
                        "is_markush": True,
                        "markush_cxsmiles": "C[*:1] |$;R1$|",
                        "markush_r_groups": ["R1"],
                    }
                ],
            }
        ],
        "drawing_summary": {"total_structures": 1, "markush_count": 1},
    }

    model = FTOReportResponse.model_validate(payload)
    assert len(model.drawing_analyses) == 1
    only = model.drawing_analyses[0]
    assert only.patent_id == "US92000005A1"
    assert only.structures[0].is_markush is True
    assert only.structures[0].markush_cxsmiles == "C[*:1] |$;R1$|"

    dumped = model.model_dump()
    assert dumped["drawing_analyses"][0]["structures"][0]["is_markush"] is True
    assert dumped["drawing_analyses"][0]["structures"][0]["markush_cxsmiles"] == "C[*:1] |$;R1$|"
    assert dumped["drawing_summary"] == {"total_structures": 1, "markush_count": 1}


def test_fto_report_response_rejects_legacy_report_identity():
    """Report response identity is the single unified adaptive profile."""
    from datetime import datetime

    import pytest
    from pydantic import ValidationError

    from api.schemas.reports_fto_report import FTOReportResponse

    payload = {
        "report_id": "rep_legacy",
        "generated_at": datetime(2026, 6, 5, 12, 0, 0),
        "compound": {"name": "test"},
        "risk_summary": {
            "overall_risk": "low",
            "blocking_patents_count": 0,
            "key_risks": [],
            "executive_summary": "",
            "summary_validation_issues": [],
        },
        "report_pipeline": "v1",
    }

    with pytest.raises(ValidationError, match="world_class_adaptive"):
        FTOReportResponse.model_validate(payload)

    payload["report_pipeline"] = "world_class_adaptive"
    payload["execution_profile"] = "report_pipeline_v2"
    with pytest.raises(ValidationError, match="world_class_adaptive"):
        FTOReportResponse.model_validate(payload)


def test_fto_report_response_surfaces_claim_source_span_map():
    """The top-level FTOReportResponse must not drop claim-span review evidence."""
    from datetime import datetime

    from api.schemas.reports_fto_report import FTOReportResponse

    payload = {
        "report_id": "rep_claim_source_1",
        "generated_at": datetime(2026, 6, 2, 12, 0, 0),
        "compound": {"name": "test"},
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "key_risks": [],
            "executive_summary": "",
            "summary_validation_issues": [],
        },
        "claim_source_span_map": {
            "generated_from": "test_fixture",
            "entries": [
                {
                    "assertion_id": "assertion-needs-review-1",
                    "patent_id": "US91000017A1",
                    "claim_number": 1,
                    "element_number": 2,
                    "report_section": "claim_element_analysis",
                    "assertion_text": "Claim 1 element 2 was assessed as unclear.",
                    "source_span_ids": [],
                    "support_status": "needs_review",
                    "customer_visible": True,
                    "review_required": True,
                }
            ],
            "spans": {},
            "unsupported_customer_visible_claim_count": 0,
            "needs_review_count": 1,
        },
    }

    model = FTOReportResponse.model_validate(payload)
    assert model.claim_source_span_map.entries[0].assertion_id == "assertion-needs-review-1"

    dumped = model.model_dump()
    assert (
        dumped["claim_source_span_map"]["entries"][0]["assertion_id"] == "assertion-needs-review-1"
    )


def test_fto_report_response_preserves_regulatory_and_review_evidence():
    """API serialization must not strip evidence already persisted by the worker."""
    from datetime import datetime

    from api.schemas.reports_fto_report import FTOReportResponse

    payload = {
        "report_id": "rep_regulatory_1",
        "generated_at": datetime(2026, 8, 3, 12, 0, 0),
        "compound": {"name": "test"},
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "key_risks": [],
            "executive_summary": "",
            "summary_validation_issues": [],
        },
        "regulatory_exclusivity": {
            "data_sources_queried": ["Orange Book"],
            "pte_extensions": [],
            "paragraph_iv_challenges": [],
            "source_statuses": [],
        },
        "review_issues": [
            {
                "issue_type": "missing_limitation",
                "patent_id": "US92000005A1",
                "severity": "major",
                "description": "A material limitation needs review.",
            }
        ],
    }

    dumped = FTOReportResponse.model_validate(payload).model_dump(mode="json")

    assert dumped["regulatory_exclusivity"]["data_sources_queried"] == ["Orange Book"]
    assert dumped["review_issues"][0]["patent_id"] == "US92000005A1"
